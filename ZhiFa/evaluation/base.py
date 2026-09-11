"""
批量推理基类

提供通用的批量推理基础设施：
- 标准化输入/输出
- 重试机制
- 进度追踪
- 结果持久化
"""

import json
import time
import traceback
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime


class BaseBatchInference(ABC):
    """批量推理基类"""

    def __init__(
        self,
        max_retries: int = 3,
        retry_delay: float = 5.0,
        save_interval: int = 10,
        output_dir: str = "evaluation/outputs",
    ):
        """
        Args:
            max_retries: 单条推理最大重试次数
            retry_delay: 重试间隔（秒），每次重试会翻倍
            save_interval: 每处理多少条保存一次中间结果
            output_dir: 输出目录
        """
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.save_interval = save_interval
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    @property
    @abstractmethod
    def module_name(self) -> str:
        """模块名称，用于日志和文件命名"""
        ...

    @abstractmethod
    def _infer_single(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """
        对单条输入执行推理

        Args:
            item: 单条标准化输入

        Returns:
            推理结果字典
        """
        ...

    @abstractmethod
    def validate_input(self, item: Dict[str, Any]) -> bool:
        """
        校验单条输入是否合法

        Args:
            item: 单条输入

        Returns:
            是否合法
        """
        ...

    def infer_single_with_retry(self, item: Dict[str, Any], index: int) -> Dict[str, Any]:
        """
        带重试的单条推理

        Args:
            item: 输入数据
            index: 当前索引（用于日志）

        Returns:
            包含推理结果和元信息的字典
        """
        for attempt in range(self.max_retries):
            try:
                start_time = time.time()
                result = self._infer_single(item)
                elapsed = time.time() - start_time

                return {
                    "index": index,
                    "input": item,
                    "output": result,
                    "status": "success",
                    "elapsed_seconds": round(elapsed, 2),
                    "attempts": attempt + 1,
                    "error": None,
                }
            except Exception as e:
                error_msg = f"{type(e).__name__}: {str(e)}"
                print(f"  ⚠ [{self.module_name}] 第 {index+1} 条推理失败 "
                      f"(尝试 {attempt+1}/{self.max_retries}): {error_msg}")

                if attempt < self.max_retries - 1:
                    wait = self.retry_delay * (2 ** attempt)
                    print(f"    等待 {wait:.1f}s 后重试...")
                    time.sleep(wait)
                else:
                    traceback.print_exc()
                    return {
                        "index": index,
                        "input": item,
                        "output": None,
                        "status": "failed",
                        "elapsed_seconds": 0,
                        "attempts": self.max_retries,
                        "error": error_msg,
                    }

    def run_batch(
        self,
        inputs: List[Dict[str, Any]],
        output_file: Optional[str] = None,
        resume_from: int = 0,
    ) -> Dict[str, Any]:
        """
        批量执行推理

        Args:
            inputs: 标准化输入列表
            output_file: 输出文件名（默认自动生成）
            resume_from: 从第几条开始（支持断点续跑）

        Returns:
            批量推理结果摘要
        """
        total = len(inputs)
        print(f"\n{'='*60}")
        print(f"[{self.module_name}] 批量推理开始")
        print(f"  总数: {total} 条 | 起始: 第 {resume_from+1} 条")
        print(f"  重试: {self.max_retries} 次 | 保存间隔: {self.save_interval} 条")
        print(f"{'='*60}\n")

        # 生成输出文件路径
        if output_file is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = f"{self.module_name}_results_{timestamp}.json"

        output_path = self.output_dir / output_file

        # 加载已有结果（断点续跑）
        results = []
        if resume_from > 0 and output_path.exists():
            with open(output_path, "r", encoding="utf-8") as f:
                saved_data = json.load(f)
                results = saved_data.get("results", [])[:resume_from]
            print(f"  已加载 {len(results)} 条历史结果")

        # 验证输入
        invalid_count = 0
        for i, item in enumerate(inputs[resume_from:], start=resume_from):
            if not self.validate_input(item):
                print(f"  ⚠ 第 {i+1} 条输入校验失败，跳过")
                results.append({
                    "index": i,
                    "input": item,
                    "output": None,
                    "status": "invalid_input",
                    "elapsed_seconds": 0,
                    "attempts": 0,
                    "error": "输入校验失败",
                })
                invalid_count += 1
                continue

            # 执行推理
            print(f"  [{i+1}/{total}] 正在推理...", end="", flush=True)
            result = self.infer_single_with_retry(item, i)
            results.append(result)

            status_icon = "✓" if result["status"] == "success" else "✗"
            print(f" {status_icon} ({result['elapsed_seconds']}s)")

            # 定期保存
            if (i + 1) % self.save_interval == 0:
                self._save_results(results, output_path, total)
                print(f"  💾 已保存中间结果 ({len(results)}/{total})")

        # 最终保存
        summary = self._save_results(results, output_path, total)

        # 打印统计
        success_count = sum(1 for r in results if r["status"] == "success")
        failed_count = sum(1 for r in results if r["status"] == "failed")

        print(f"\n{'='*60}")
        print(f"[{self.module_name}] 批量推理完成")
        print(f"  成功: {success_count} | 失败: {failed_count} | 无效: {invalid_count}")
        print(f"  输出: {output_path}")
        print(f"{'='*60}\n")

        return summary

    def _save_results(
        self, results: List[Dict], output_path: Path, total: int
    ) -> Dict[str, Any]:
        """保存结果到 JSON 文件"""
        success_count = sum(1 for r in results if r["status"] == "success")
        failed_count = sum(1 for r in results if r["status"] == "failed")
        invalid_count = sum(1 for r in results if r["status"] == "invalid_input")

        summary = {
            "module": self.module_name,
            "timestamp": datetime.now().isoformat(),
            "total": total,
            "processed": len(results),
            "success": success_count,
            "failed": failed_count,
            "invalid": invalid_count,
            "success_rate": round(success_count / max(len(results), 1) * 100, 2),
            "results": results,
        }

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)

        return summary
