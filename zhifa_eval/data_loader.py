"""
ZhiFa-Eval 数据加载器

统一管理 17 个子任务的数据加载。
"""

import json
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .config import DATASET_PATH


@dataclass
class TaskInfo:
    """子任务元信息"""
    task_id: str                # e.g. "legal_qa.memorization.factual_query"
    display_name: str           # 中文名
    module: str                 # legal_qa / contract_review / case_prediction
    layer: Optional[str]        # memorization / understanding / application / None
    eval_method: str            # "objective" / "rubric"
    metrics: List[str]          # ["Accuracy"] / ["Rubric Score"]
    task_type: str              # SLC / MLC / Generation / Extraction / Regression
    data_dir: str               # 相对于 datasets/ 的路径
    difficulties: List[str] = field(default_factory=lambda: ["standard"])
    sample_counts: Dict[str, int] = field(default_factory=dict)
    subtypes: Optional[Dict[str, str]] = None


# ─── 17 个子任务注册表 ──────────────────────────────────

TASK_REGISTRY: List[TaskInfo] = [
    # ===== 法律问答 - 记忆层 =====
    TaskInfo("legal_qa.memorization.factual_query", "法条事实查询", "legal_qa", "memorization",
             "objective", ["EM+Rouge-L"], "Generation",
             "Legal_QA/memorization/factual_query", ["standard"], {"standard": 100}),
    TaskInfo("legal_qa.memorization.legal_knowledge_mcqa", "法律知识选择题", "legal_qa", "memorization",
             "objective", ["Accuracy-ABCD"], "SLC/MLC",
             "Legal_QA/memorization/legal_knowledge_mcqa", ["standard", "challenge"], {"standard": 150, "challenge": 50}),
    TaskInfo("legal_qa.memorization.statute_recitation", "法条背诵", "legal_qa", "memorization",
             "objective", ["Rouge-L"], "Generation",
             "Legal_QA/memorization/statute_recitation", ["standard", "challenge"], {"standard": 100, "challenge": 50}),
    # ===== 法律问答 - 理解层 =====
    TaskInfo("legal_qa.understanding.reading_comprehension", "阅读理解", "legal_qa", "understanding",
             "objective", ["rc-F1"], "Extraction",
             "Legal_QA/understanding/reading_comprehension", ["standard"], {"standard": 200}),
    TaskInfo("legal_qa.understanding.argument_understanding", "论点理解", "legal_qa", "understanding",
             "objective", ["Accuracy-ABCDE"], "SLC",
             "Legal_QA/understanding/argument_understanding", ["standard"], {"standard": 200}),
    TaskInfo("legal_qa.understanding.issue_understanding", "争议焦点识别", "legal_qa", "understanding",
             "objective", ["Accuracy-Category"], "SLC",
             "Legal_QA/understanding/issue_understanding",
             ["standard", "challenge", "adversarial"], {"standard": 300, "challenge": 100, "adversarial": 100},
             subtypes={"legal_consultation": "法律咨询", "disputed_issues": "争议焦点"}),
    TaskInfo("legal_qa.understanding.case_summarization", "案情摘要", "legal_qa", "understanding",
             "objective", ["Rouge-L"], "Generation",
             "Legal_QA/understanding/case_summarization",
             ["standard", "challenge", "adversarial"], {"standard": 300, "challenge": 100, "adversarial": 100}),
    # ===== 法律问答 - 应用层 =====
    TaskInfo("legal_qa.application.consultation_fact_inquiry", "咨询事实追问", "legal_qa", "application",
             "rubric", ["Rubric Score"], "Generation",
             "Legal_QA/application/consultation_fact_inquiry", ["standard"], {"standard": 50}),
    TaskInfo("legal_qa.application.case_analysis", "案情分析", "legal_qa", "application",
             "rubric", ["Rubric Score"], "Generation",
             "Legal_QA/application/case_analysis",
             ["standard", "challenge", "adversarial"], {"standard": 100, "challenge": 25, "adversarial": 25}),
    TaskInfo("legal_qa.application.legal_document_generation", "法律文书生成", "legal_qa", "application",
             "rubric", ["Rubric Score"], "Generation",
             "Legal_QA/application/legal_document_generation",
             ["standard", "challenge"], {"standard": 50, "challenge": 25}),
    # ===== 合同审查 =====
    TaskInfo("contract_review.clause_correction", "条款纠错", "contract_review", None,
             "objective", ["F0.5"], "Generation",
             "Contract_Review/clause_correction", ["standard"], {"standard": 200}),
    TaskInfo("contract_review.risk_detection", "合同风险检测", "contract_review", None,
             "rubric", ["Rubric Score"], "Generation",
             "Contract_Review/contract_risk_detection_and_revision",
             ["standard", "challenge", "adversarial"], {"standard": 80, "challenge": 20, "adversarial": 20}),
    TaskInfo("contract_review.risk_revision", "合同修订建议", "contract_review", None,
             "rubric", ["Rubric Score"], "Generation",
             "Contract_Review/contract_risk_detection_and_revision",
             ["standard", "challenge", "adversarial"], {"standard": 80, "challenge": 20, "adversarial": 20}),
    # ===== 案情预测 =====
    TaskInfo("case_prediction.article_prediction", "法条预测", "case_prediction", None,
             "objective", ["F1"], "MLC",
             "Case_Prediction/article_prediction",
             ["standard", "challenge"], {"standard": 200, "challenge": 100}),
    TaskInfo("case_prediction.clause_prediction", "罪名预测", "case_prediction", None,
             "objective", ["F1"], "MLC",
             "Case_Prediction/clause_prediction", ["standard"], {"standard": 200}),
    TaskInfo("case_prediction.prison_term_prediction", "刑期预测", "case_prediction", None,
             "objective", ["nLog-distance"], "Regression",
             "Case_Prediction/prison_term_prediction",
             ["standard", "challenge"], {"standard": 200, "challenge": 100}),
    TaskInfo("case_prediction.comprehensive_judgment_prediction", "综合判决预测", "case_prediction", None,
             "rubric", ["Rubric Score"], "Generation",
             "Case_Prediction/comprehensive_judgment_prediction",
             ["standard", "challenge", "adversarial"], {"standard": 200, "challenge": 50, "adversarial": 50}),
]

TASK_MAP: Dict[str, TaskInfo] = {t.task_id: t for t in TASK_REGISTRY}


def get_tasks_by_module(module: str) -> List[TaskInfo]:
    """按模块筛选任务"""
    return [t for t in TASK_REGISTRY if t.module == module]


def load_task_data(task_id: str, difficulty: str = "standard", subtype: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    加载指定任务和难度的数据。

    对于合同审查的 risk_detection / risk_revision，
    返回的每条数据包含合同原文 + rubric。
    """
    task = TASK_MAP.get(task_id)
    if task is None:
        raise ValueError(f"未知任务: {task_id}")
    if difficulty not in task.difficulties:
        raise ValueError(f"任务 {task_id} 不支持难度 {difficulty}，可选: {task.difficulties}")

    base_dir = DATASET_PATH / task.data_dir

    # 争议焦点识别：合并 legal_consultation + disputed_issues 两个子目录
    if task_id == "legal_qa.understanding.issue_understanding":
        return _load_issue_understanding(base_dir, difficulty, subtype)

    # 合同风险检测/修订：特殊加载逻辑
    if task_id in ("contract_review.risk_detection", "contract_review.risk_revision"):
        return _load_contract_risk_data(base_dir, difficulty, task_id)

    # 通用加载：直接读 standard.json / challenge.json / adversarial.json
    # 注意 case_analysis 的 challenge 文件名是 chanllege.json（原数据拼写错误）
    file_name = f"{difficulty}.json"
    if task_id == "legal_qa.application.case_analysis" and difficulty == "challenge":
        file_name = "chanllege.json"

    data_file = base_dir / file_name
    if not data_file.exists():
        raise FileNotFoundError(f"数据文件不存在: {data_file}")

    with open(data_file, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_contract_risk_data(
    base_dir: Path, difficulty: str, task_id: str
) -> List[Dict[str, Any]]:
    """加载合同风险检测/修订数据，合并合同原文与 rubric"""
    rubric_type = "rubric_detection" if "detection" in task_id else "rubric_revision"
    rubric_dir = base_dir / difficulty / rubric_type
    contracts_dir = base_dir / difficulty / "contracts"

    if not rubric_dir.exists():
        raise FileNotFoundError(f"Rubric 目录不存在: {rubric_dir}")

    results = []
    for rubric_file in sorted(rubric_dir.glob("*.json")):
        with open(rubric_file, "r", encoding="utf-8") as f:
            rubric = json.load(f)

        # 加载对应合同原文
        contract_ref = rubric.get("contract_file", "")
        contract_path = base_dir / difficulty / contract_ref
        if not contract_path.exists():
            # 尝试从 contracts/ 目录用同名查找
            contract_path = contracts_dir / rubric_file.stem
            for ext in [".md", ".txt", ".pdf"]:
                p = contracts_dir / (rubric_file.stem + ext)
                if p.exists():
                    contract_path = p
                    break

        contract_text = ""
        if contract_path.exists() and contract_path.suffix in (".md", ".txt"):
            with open(contract_path, "r", encoding="utf-8") as f:
                contract_text = f.read()

        rubric["_contract_text"] = contract_text
        rubric["_rubric_file"] = str(rubric_file.name)
        results.append(rubric)

    return results


def _load_issue_understanding(
    base_dir: Path, difficulty: str, subtype: Optional[str] = None
) -> List[Dict[str, Any]]:
    """合并 legal_consultation + disputed_issues 两个子目录的数据，支持 subtype 过滤"""
    sub_dirs = [subtype] if subtype in ("legal_consultation", "disputed_issues") \
        else ["legal_consultation", "disputed_issues"]
    combined = []
    for sub_dir in sub_dirs:
        f = base_dir / sub_dir / f"{difficulty}.json"
        if f.exists():
            with open(f, "r", encoding="utf-8") as fh:
                combined.extend(json.load(fh))
    return combined
