"""
批量推理统一运行器

提供统一入口来运行三大模块的批量推理任务：
- 从 JSON 文件加载输入
- 支持指定模块和任务类型
- 支持断点续跑
- 输出结构化结果
"""

import json
import argparse
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from .batch_legal_qa import BatchLegalQA
from .batch_contract_review import BatchContractReview
from .batch_case_prediction import BatchCasePrediction


class BatchRunner:
    """批量推理统一运行器"""

    MODULE_MAP = {
        "legal_qa": BatchLegalQA,
        "contract_review": BatchContractReview,
        "case_prediction": BatchCasePrediction,
    }

    def __init__(
        self,
        max_retries: int = 3,
        retry_delay: float = 5.0,
        save_interval: int = 10,
        output_dir: str = "evaluation/outputs",
    ):
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.save_interval = save_interval
        self.output_dir = output_dir

    def _create_module(self, module_name: str):
        """创建指定模块的批量推理实例"""
        if module_name not in self.MODULE_MAP:
            raise ValueError(
                f"不支持的模块: {module_name}，"
                f"可选: {list(self.MODULE_MAP.keys())}"
            )
        cls = self.MODULE_MAP[module_name]
        return cls(
            max_retries=self.max_retries,
            retry_delay=self.retry_delay,
            save_interval=self.save_interval,
            output_dir=self.output_dir,
        )

    def run(
        self,
        module_name: str,
        inputs: List[Dict[str, Any]],
        output_file: Optional[str] = None,
        resume_from: int = 0,
    ) -> Dict[str, Any]:
        """
        运行批量推理

        Args:
            module_name: 模块名称 (legal_qa / contract_review / case_prediction)
            inputs: 输入数据列表
            output_file: 输出文件名
            resume_from: 断点续跑起始索引

        Returns:
            批量推理结果摘要
        """
        module = self._create_module(module_name)
        return module.run_batch(inputs, output_file, resume_from)

    def run_from_file(
        self,
        module_name: str,
        input_file: str,
        output_file: Optional[str] = None,
        resume_from: int = 0,
    ) -> Dict[str, Any]:
        """
        从 JSON 文件加载输入并运行批量推理

        Args:
            module_name: 模块名称
            input_file: 输入文件路径（JSON 格式，数组或含 "data" 键）
            output_file: 输出文件名
            resume_from: 断点续跑起始索引

        Returns:
            批量推理结果摘要
        """
        input_path = Path(input_file)
        if not input_path.exists():
            raise FileNotFoundError(f"输入文件不存在: {input_file}")

        print(f"正在加载输入文件: {input_path}")
        with open(input_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # 支持两种格式：直接数组 或 {"data": [...]}
        if isinstance(data, list):
            inputs = data
        elif isinstance(data, dict) and "data" in data:
            inputs = data["data"]
        else:
            raise ValueError(
                "输入文件格式错误：需要 JSON 数组或包含 'data' 键的对象"
            )

        print(f"已加载 {len(inputs)} 条输入数据")
        return self.run(module_name, inputs, output_file, resume_from)

    def run_all_modules(
        self,
        input_files: Dict[str, str],
        output_dir: Optional[str] = None,
    ) -> Dict[str, Dict[str, Any]]:
        """
        运行所有模块的批量推理

        Args:
            input_files: 模块名到输入文件路径的映射
                {
                    "legal_qa": "path/to/qa_inputs.json",
                    "contract_review": "path/to/contract_inputs.json",
                    "case_prediction": "path/to/case_inputs.json",
                }
            output_dir: 输出目录（覆盖默认值）

        Returns:
            各模块的推理结果摘要
        """
        if output_dir:
            self.output_dir = output_dir

        results = {}
        total_start = time.time()

        for module_name, input_file in input_files.items():
            print(f"\n{'#'*60}")
            print(f"# 模块: {module_name}")
            print(f"# 输入: {input_file}")
            print(f"{'#'*60}")

            try:
                result = self.run_from_file(module_name, input_file)
                results[module_name] = result
            except Exception as e:
                print(f"⚠ 模块 {module_name} 执行失败: {e}")
                results[module_name] = {"status": "error", "error": str(e)}

        total_elapsed = time.time() - total_start
        print(f"\n{'='*60}")
        print(f"所有模块执行完成，总耗时: {total_elapsed:.1f}s")
        print(f"{'='*60}\n")

        return results


def main():
    """命令行入口"""
    # 加载 .env 环境变量（API Key 等）
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")

    parser = argparse.ArgumentParser(
        description="智法AI 批量推理工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  # 运行法律问答批量推理
  python -m evaluation.batch_runner --module legal_qa --input data/eval/qa_inputs.json

  # 运行案情预测，从第 50 条断点续跑
  python -m evaluation.batch_runner --module case_prediction --input data/eval/case_inputs.json --resume 50

  # 自定义重试和保存参数
  python -m evaluation.batch_runner --module contract_review --input data/eval/contract_inputs.json --retries 5 --save-interval 5
        """,
    )

    parser.add_argument(
        "--module", "-m",
        required=True,
        choices=["legal_qa", "contract_review", "case_prediction"],
        help="推理模块名称",
    )
    parser.add_argument(
        "--input", "-i",
        required=True,
        help="输入文件路径（JSON 格式）",
    )
    parser.add_argument(
        "--output", "-o",
        default=None,
        help="输出文件名（默认自动生成）",
    )
    parser.add_argument(
        "--output-dir",
        default="evaluation/outputs",
        help="输出目录（默认 evaluation/outputs）",
    )
    parser.add_argument(
        "--resume",
        type=int,
        default=0,
        help="断点续跑：从第几条开始（0-indexed）",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=3,
        help="单条推理最大重试次数（默认 3）",
    )
    parser.add_argument(
        "--retry-delay",
        type=float,
        default=5.0,
        help="重试间隔秒数（默认 5.0，指数递增）",
    )
    parser.add_argument(
        "--save-interval",
        type=int,
        default=10,
        help="每处理多少条保存一次中间结果（默认 10）",
    )

    args = parser.parse_args()

    runner = BatchRunner(
        max_retries=args.retries,
        retry_delay=args.retry_delay,
        save_interval=args.save_interval,
        output_dir=args.output_dir,
    )

    runner.run_from_file(
        module_name=args.module,
        input_file=args.input,
        output_file=args.output,
        resume_from=args.resume,
    )


if __name__ == "__main__":
    main()
