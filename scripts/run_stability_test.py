"""
run_stability_test.py
评分稳定性验证：同一裁判模型在不同 temperature 下对同一份答案评分，验证分数波动。

用法:
    python scripts/run_stability_test.py --run 1
    python scripts/run_stability_test.py --run 2
    python scripts/run_stability_test.py --run 3

每次跑一轮（6 tasks × 5 temps = 30 次评分），结果按 run_id 合并到 _stability_summary.json。
"""

import sys, os, io, json, time, argparse
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict
import math

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

from zhifa_eval.data_loader import TASK_MAP, load_task_data
from zhifa_eval.inference.openai_inference import OpenAIInference
from zhifa_eval.scorers.subjective.llm_judge import LLMJudge

ANSWERS_DIR = PROJECT_ROOT / "test_discrimination" / "answers"
OUTPUT_DIR = PROJECT_ROOT / "test_discrimination" / "stability"
SUMMARY_PATH = OUTPUT_DIR / "_stability_summary.json"

TASK_IDS = [
    "legal_qa.application.consultation_fact_inquiry",
    "legal_qa.application.case_analysis",
    "legal_qa.application.legal_document_generation",
    "contract_review.risk_detection",
    "contract_review.risk_revision",
    "case_prediction.comprehensive_judgment_prediction",
]

TEMPERATURES = [0.0, 0.1, 0.3, 0.5, 0.7]
GRADE = "medium"
SAMPLE_INDEX = 1


def load_api_keys():
    keys = []
    for i in range(1, 7):
        val = os.getenv(f"RUBRIC_API_{i}", "")
        if not val:
            continue
        parts = val.split("|")
        if len(parts) >= 3:
            keys.append({"base_url": parts[0], "api_key": parts[1], "model": parts[2]})
    return keys


def load_answers(tid):
    fpath = ANSWERS_DIR / f"{tid}_{GRADE}.json"
    if not fpath.exists():
        return None
    with open(fpath, "r", encoding="utf-8") as f:
        return json.load(f)


def judge_one(tid, temp, api_cfg, answer_item, data_item):
    client = OpenAIInference(
        base_url=api_cfg["base_url"],
        api_key=api_cfg["api_key"],
        model=api_cfg["model"],
        temperature=temp,
        max_tokens=16384,
    )
    judge = LLMJudge(client)
    question = data_item.get("question", data_item.get("conversation", ""))
    answer = answer_item.get("answer", "")

    try:
        sr = judge.score(tid, question, answer, data_item)
        return {
            "task_id": tid,
            "temperature": temp,
            "score_ratio": sr.get("score_ratio", 0),
            "total_score": sr.get("total_score", 0),
            "max_score": sr.get("max_score", 0),
            "validation": sr.get("validation", "ok"),
        }
    except Exception as e:
        return {
            "task_id": tid,
            "temperature": temp,
            "score_ratio": 0,
            "total_score": 0,
            "max_score": 0,
            "validation": f"error:{e}",
        }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", type=int, required=True, help="轮次编号 (1/2/3)")
    args = parser.parse_args()
    run_id = args.run

    api_keys = load_api_keys()
    if not api_keys:
        print("ERROR: 未找到 RUBRIC_API_1~6，请检查 .env")
        sys.exit(1)
    print(f"  第 {run_id} 轮，{len(api_keys)} 条 API Key 可用")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    jobs = []
    for tid in TASK_IDS:
        ans_data = load_answers(tid)
        if not ans_data or not ans_data.get("answers"):
            print(f"  [SKIP] {tid}: 答案文件不存在")
            continue

        task = TASK_MAP.get(tid)
        if not task:
            continue

        all_data = load_task_data(tid, "standard")

        idx = min(SAMPLE_INDEX, len(ans_data["answers"]) - 1)
        answer = ans_data["answers"][idx]
        sidx = min(SAMPLE_INDEX, len(all_data) - 1) if all_data else 0
        item = all_data[sidx] if all_data else {}

        for temp in TEMPERATURES:
            jobs.append((tid, temp, answer, item))

    print(f"  共 {len(jobs)} 次评分（{len(TASK_IDS)} 任务 × {len(TEMPERATURES)} 温度）")
    print(f"  开始评分...\n")

    results = []
    start = time.time()

    with ThreadPoolExecutor(max_workers=len(api_keys)) as pool:
        futures = {}
        for i, (tid, temp, ans, item) in enumerate(jobs):
            api_cfg = api_keys[i % len(api_keys)]
            f = pool.submit(judge_one, tid, temp, api_cfg, ans, item)
            futures[f] = (tid, temp)

        for f in as_completed(futures):
            tid, temp = futures[f]
            task_name = TASK_MAP[tid].display_name
            try:
                r = f.result()
                r["run_id"] = run_id
                results.append(r)
                tag = "OK" if r["validation"] == "ok" else "WARN"
                print(f"  [{tag}] {task_name} t={temp} ratio={r['score_ratio']:.3f}",
                      flush=True)
            except Exception as e:
                print(f"  [ERROR] {task_name} t={temp}: {e}")

    elapsed = round(time.time() - start, 1)

    # 合并到现有 summary（如果存在）
    if SUMMARY_PATH.exists():
        with open(SUMMARY_PATH, "r", encoding="utf-8") as f:
            summary = json.load(f)
        # 移除同 run_id 的旧数据
        summary["results"] = [r for r in summary["results"] if r.get("run_id") != run_id]
        summary["results"].extend(results)
    else:
        summary = {
            "grade": GRADE,
            "temperatures": TEMPERATURES,
            "task_ids": TASK_IDS,
            "results": results,
        }

    summary["results"] = sorted(summary["results"],
                                key=lambda r: (r["task_id"], r.get("run_id", 1), r["temperature"]))

    with open(SUMMARY_PATH, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    # 打印汇总
    print(f"\n{'='*70}")
    print(f" 第 {run_id} 轮结果 ({elapsed}s)")
    print(f"{'='*70}")

    by_task = defaultdict(list)
    for r in results:
        by_task[r["task_id"]].append(r)

    for tid in TASK_IDS:
        if tid not in by_task:
            continue
        task_name = TASK_MAP[tid].display_name
        scores = [r["score_ratio"] for r in sorted(by_task[tid], key=lambda x: x["temperature"])]
        mean = sum(scores) / len(scores)
        std = math.sqrt(sum((s - mean) ** 2 for s in scores) / len(scores))
        temps_str = " | ".join(f"t={t}:{s:.3f}" for t, s in zip(TEMPERATURES, scores))
        print(f"  {task_name}: {temps_str}  σ={std:.4f}")

    print(f"\n  结果 -> {SUMMARY_PATH}")


if __name__ == "__main__":
    main()
