"""
7 维度能力评分计算脚本

从主观评测的 rubric（维度标签）+ 评分结果（item 级别得分）中，
按 7 个能力维度汇总 1-5 分。

7 个维度：事实准确性、法条引用正确性、证据可追溯性、
         法律推理逻辑性、完整性、安全合规性、用户可理解性
"""

import json
import glob
import os
import sys
import re
from collections import defaultdict

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DIMENSIONS = [
    "事实准确性", "法条引用正确性", "证据可追溯性",
    "法律推理逻辑性", "完整性", "安全合规性", "用户可理解性"
]

RISK_DET_SUBKEY_MAP = {
    "识别风险": [("完整性", 1.0)],
    "风险解释": [("法律推理逻辑性", 1.0)],
    "修改建议": [("法律推理逻辑性", 0.5), ("完整性", 0.5)],
    "法律依据": [("法条引用正确性", 1.0)],
}


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def parse_judge_raw(raw):
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        text = raw.strip()
        if text.startswith("```"):
            text = re.sub(r"^```\w*\n?", "", text)
            text = re.sub(r"\n?```$", "", text)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None
    return None


class DimensionAccumulator:
    def __init__(self):
        self.task_dims = defaultdict(lambda: defaultdict(lambda: {"earned": 0.0, "max": 0.0}))

    def add(self, task, dim, earned, max_pts):
        self.task_dims[task][dim]["earned"] += earned
        self.task_dims[task][dim]["max"] += max_pts

    def _task_overall_ratio(self):
        """每个任务的整体得分率 = 所有维度 earned 之和 / max 之和"""
        ratios = {}
        for task, dims in self.task_dims.items():
            total_earned = sum(v["earned"] for v in dims.values())
            total_max = sum(v["max"] for v in dims.values())
            ratios[task] = total_earned / total_max if total_max > 0 else 0.0
        return ratios

    def fill_missing_dims(self):
        """对缺失维度用任务整体 score_ratio 填充"""
        all_tasks = list(self.task_dims.keys())
        overall = self._task_overall_ratio()
        for task in all_tasks:
            for dim in DIMENSIONS:
                if self.task_dims[task][dim]["max"] == 0:
                    proxy = overall[task]
                    self.task_dims[task][dim]["earned"] = proxy
                    self.task_dims[task][dim]["max"] = 1.0

    def compute_final(self):
        self.fill_missing_dims()

        dim_ratios_by_task = defaultdict(list)
        for task, dims in self.task_dims.items():
            for dim, vals in dims.items():
                if vals["max"] > 0:
                    ratio = vals["earned"] / vals["max"]
                    dim_ratios_by_task[dim].append({
                        "task": task,
                        "ratio": ratio,
                        "earned": vals["earned"],
                        "max": vals["max"],
                        "is_proxy": vals["max"] == 1.0 and vals["earned"] <= 1.0,
                    })

        results = {}
        for dim in DIMENSIONS:
            entries = dim_ratios_by_task.get(dim, [])
            if entries:
                avg_ratio = sum(e["ratio"] for e in entries) / len(entries)
            else:
                avg_ratio = 0.0
            score_1_5 = round(1 + 4 * avg_ratio, 2)
            results[dim] = {
                "score_ratio": round(avg_ratio, 4),
                "score_1_5": score_1_5,
                "task_count": len(entries),
                "direct_count": sum(1 for e in entries if not e.get("is_proxy")),
                "per_task": entries,
            }
        return results


SCORE_DIR = os.path.join(BASE_DIR, "zhifa_output")
DATASET_DIR = os.path.join(BASE_DIR, "datasets")

SCORE_FILES = {
    "consultation_fact_inquiry": "legal_qa.application.consultation_fact_inquiry_scores.json",
    "case_analysis": "legal_qa.application.case_analysis_scores.json",
    "legal_document_generation": "legal_qa.application.legal_document_generation_scores.json",
    "comprehensive_judgment_prediction": "case_prediction.comprehensive_judgment_prediction_scores.json",
    "risk_detection": "contract_review.risk_detection_scores.json",
    "risk_revision": "contract_review.risk_revision_scores.json",
}

RUBRIC_PATHS = {
    "consultation_fact_inquiry": "Legal_QA/application/consultation_fact_inquiry/standard.json",
    "case_analysis": "Legal_QA/application/case_analysis/standard.json",
    "legal_document_generation": "Legal_QA/application/legal_document_generation/standard.json",
    "comprehensive_judgment_prediction": "Case_Prediction/comprehensive_judgment_prediction/standard.json",
    "risk_detection": "Contract_Review/contract_risk_detection_and_revision/standard/rubric_detection",
    "risk_revision": "Contract_Review/contract_risk_detection_and_revision/standard/rubric_revision",
}



def load_rubric_list(task):
    path = os.path.join(DATASET_DIR, RUBRIC_PATHS[task])
    if os.path.isfile(path):
        return load_json(path)
    files = sorted(os.listdir(path))
    result = []
    for f in files:
        if f.endswith(".json"):
            result.append(load_json(os.path.join(path, f)))
    return result


def load_scores(task):
    path = os.path.join(SCORE_DIR, SCORE_FILES[task])
    data = load_json(path)
    return data["scores"] if isinstance(data, dict) else data


def process_consultation_fact_inquiry(acc):
    task = "consultation_fact_inquiry"
    rubric_list = load_rubric_list(task)
    scores = load_scores(task)

    for entry in scores:
        idx = entry["id"]
        if idx >= len(rubric_list):
            continue
        rubric = rubric_list[idx]
        rubric_items = {r["index"]: r for r in rubric["rubrics"]}

        for item in entry["item_scores"]:
            iidx = item["index"]
            if iidx not in rubric_items:
                continue
            ri = rubric_items[iidx]
            dim = ri["dimension"]
            earned = item["score"]
            max_pts = ri["points"]
            acc.add(task, dim, earned, max_pts)


def process_module_task(acc, task):
    rubric_list = load_rubric_list(task)
    scores = load_scores(task)

    for entry in scores:
        idx = entry["id"]
        if idx >= len(rubric_list):
            continue
        rubric = rubric_list[idx]

        rubric_modules = {}
        for mod in rubric.get("rubrics", []):
            rubric_modules[mod["module"]] = mod

        raw = parse_judge_raw(entry.get("judge_raw", ""))
        if not raw or "modules" not in raw:
            continue

        for mod_result in raw["modules"]:
            mod_name = mod_result["module"]
            rubric_mod = rubric_modules.get(mod_name)
            if not rubric_mod:
                continue

            dims = rubric_mod.get("dimensions", [])
            if not dims:
                continue

            is_deduction = all(
                it.get("points", 0) < 0 for it in rubric_mod.get("items", [])
            )

            if is_deduction:
                max_deduction = sum(
                    abs(it["points"]) for it in rubric_mod["items"]
                )
                actual_score = mod_result.get("module_total", 0)
                earned = max_deduction + actual_score
                for dim in dims:
                    acc.add(task, dim, max(0, earned), max_deduction)
            else:
                for item in mod_result.get("items", []):
                    earned = item.get("score", 0)
                    max_pts = item.get("max", 0)
                    share = 1.0 / len(dims)
                    for dim in dims:
                        acc.add(task, dim, earned * share, max_pts * share)


def process_risk_detection(acc):
    task = "risk_detection"
    rubric_list = load_rubric_list(task)
    scores = load_scores(task)

    for entry in scores:
        idx = entry["id"]
        if idx >= len(rubric_list):
            continue
        rubric = rubric_list[idx]
        rubric_risks = {r["risk_id"]: r for r in rubric.get("risks", [])}

        for item in entry["item_scores"]:
            risk_id = item.get("risk_id", "")
            rubric_risk = rubric_risks.get(risk_id)
            if not rubric_risk:
                continue

            sub_scores = item.get("sub_scores", {})
            rubric_scoring = rubric_risk.get("scoring", {})

            for sub_key, sub_val in sub_scores.items():
                earned = sub_val.get("score", 0)
                max_pts = rubric_scoring.get(sub_key, {}).get("score", 0)
                if max_pts <= 0:
                    continue

                dim_map = RISK_DET_SUBKEY_MAP.get(sub_key, [])
                for dim, weight in dim_map:
                    acc.add(task, dim, earned * weight, max_pts * weight)


def process_risk_revision(acc):
    task = "risk_revision"
    rubric_list = load_rubric_list(task)
    scores = load_scores(task)

    for entry in scores:
        idx = entry["id"]
        if idx >= len(rubric_list):
            continue
        rubric = rubric_list[idx]
        rubric_fixes = {f["risk_id"]: f for f in rubric.get("fixes", [])}

        for item in entry["item_scores"]:
            risk_id = item.get("risk_id", "")
            rubric_fix = rubric_fixes.get(risk_id)
            if not rubric_fix:
                continue

            rubric_checklist = rubric_fix.get("fix_checklist", [])
            result_checklist = item.get("checklist_scores", [])

            for i, ck in enumerate(result_checklist):
                earned = ck.get("score", 0)
                max_pts = rubric_checklist[i]["score"] if i < len(rubric_checklist) else 1
                if max_pts <= 0:
                    max_pts = 1
                acc.add(task, "法律推理逻辑性", earned * 0.5, max_pts * 0.5)
                acc.add(task, "完整性", earned * 0.5, max_pts * 0.5)


def main():
    acc = DimensionAccumulator()

    print("Processing consultation_fact_inquiry...")
    process_consultation_fact_inquiry(acc)

    for task in ["case_analysis", "legal_document_generation",
                 "comprehensive_judgment_prediction"]:
        print(f"Processing {task}...")
        process_module_task(acc, task)

    print("Processing risk_detection...")
    process_risk_detection(acc)

    print("Processing risk_revision...")
    process_risk_revision(acc)

    results = acc.compute_final()

    print("\n" + "=" * 60)
    print("7 维度能力评分结果")
    print("=" * 60)
    print(f"{'维度':<16} {'得分率':>8} {'1-5分':>6} {'直接':>4} {'代理':>4}")
    print("-" * 44)
    for dim in DIMENSIONS:
        r = results[dim]
        proxy_count = r['task_count'] - r['direct_count']
        print(f"{dim:<16} {r['score_ratio']:>8.4f} {r['score_1_5']:>6.2f} {r['direct_count']:>4} {proxy_count:>4}")

    output = {
        "dimensions": DIMENSIONS,
        "scores": {},
    }
    for dim in DIMENSIONS:
        r = results[dim]
        output["scores"][dim] = {
            "score_ratio": r["score_ratio"],
            "score_1_5": r["score_1_5"],
            "task_count": r["task_count"],
            "direct_count": r["direct_count"],
            "per_task": [
                {"task": e["task"], "ratio": round(e["ratio"], 4),
                 "earned": round(e["earned"], 2), "max": round(e["max"], 2),
                 "is_proxy": e.get("is_proxy", False)}
                for e in r["per_task"]
            ],
        }

    out_path = os.path.join(BASE_DIR, "zhifa_output", "dimension_scores.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\nSaved to {out_path}")


if __name__ == "__main__":
    main()
