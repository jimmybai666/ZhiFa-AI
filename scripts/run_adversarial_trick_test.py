"""
run_adversarial_trick_test.py
对抗性表面欺骗测试：评分 + 汇总

客观任务（法条背诵、阅读理解）：本地指标函数直接评分
主观任务（案情分析）：LLM 生成对抗答案 + LLM Judge 评分

用法:
    python scripts/run_adversarial_trick_test.py
"""

import sys, os, io, json, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

from zhifa_eval.data_loader import load_task_data, TASK_MAP
from zhifa_eval.scorers.objective.metrics import rouge_l_score, rc_f1_score
from zhifa_eval.inference.openai_inference import OpenAIInference
from zhifa_eval.scorers.subjective.llm_judge import LLMJudge

TRICK_DIR = PROJECT_ROOT / "test_discrimination" / "adversarial_trick"
ANSWERS_DIR = PROJECT_ROOT / "test_discrimination" / "answers"

TRICKS = ["trick_A", "trick_B", "trick_C"]
GRADES = ["good", "bad"]


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


def load_trick_answers(task_short, trick_name):
    fpath = TRICK_DIR / f"{task_short}_{trick_name}.json"
    if not fpath.exists():
        return None
    with open(fpath, "r", encoding="utf-8") as f:
        return json.load(f)


def load_baseline_answers(task_id, grade):
    fpath = ANSWERS_DIR / f"{task_id}_{grade}.json"
    if not fpath.exists():
        return None
    with open(fpath, "r", encoding="utf-8") as f:
        return json.load(f)


# ── 客观评分 ─────────────────────────────────────────
def score_objective(task_id, task_short, metric_fn, metric_key):
    print(f"\n{'='*60}")
    print(f"  {TASK_MAP[task_id].display_name} ({metric_key})")
    print(f"{'='*60}")

    data = load_task_data(task_id, "standard")
    ref_by_id = {}
    for i, item in enumerate(data):
        sid = item.get("id", i)
        ref_by_id[sid] = item.get("answer", "")

    results = {}

    # good / bad 基线
    for grade in GRADES:
        baseline = load_baseline_answers(task_id, grade)
        if not baseline:
            print(f"  [SKIP] {grade} baseline not found")
            continue
        scores = []
        ans_by_id = {a["id"]: a["answer"] for a in baseline.get("answers", [])}
        for sid, ref in ref_by_id.items():
            pred = ans_by_id.get(sid, "")
            if not pred:
                continue
            s = metric_fn(pred, ref)
            scores.append(s.get(metric_key, s.get("score", 0)))
        avg = sum(scores) / len(scores) if scores else 0
        results[grade] = {"mean": round(avg, 4), "count": len(scores)}
        print(f"  {grade}: {avg:.4f} ({len(scores)} samples)")

    # trick 答案
    for trick in TRICKS:
        trick_data = load_trick_answers(task_short, trick)
        if not trick_data:
            print(f"  [SKIP] {trick} not found")
            continue
        scores = []
        for ans_item in trick_data.get("answers", []):
            sid = ans_item["id"]
            ref = ref_by_id.get(sid, "")
            if not ref:
                continue
            pred = ans_item["answer"]
            s = metric_fn(pred, ref)
            scores.append(s.get(metric_key, s.get("score", 0)))
        avg = sum(scores) / len(scores) if scores else 0
        results[trick] = {"mean": round(avg, 4), "count": len(scores)}
        print(f"  {trick}: {avg:.4f} ({len(scores)} samples)")

    return results


# ── 主观评分（案情分析）──────────────────────────────
def generate_and_score_subjective(api_keys):
    task_id = "legal_qa.application.case_analysis"
    print(f"\n{'='*60}")
    print(f"  {TASK_MAP[task_id].display_name} (LLM-as-Judge)")
    print(f"{'='*60}")

    data = load_task_data(task_id, "standard")
    item_by_id = {}
    for i, item in enumerate(data):
        sid = item.get("id", i)
        item_by_id[sid] = item

    results = {}

    # good / bad 基线
    for grade in GRADES:
        baseline = load_baseline_answers(task_id, grade)
        if not baseline:
            print(f"  [SKIP] {grade} baseline not found")
            continue
        ans_by_id = {a["id"]: a["answer"] for a in baseline.get("answers", [])}

        scores = []
        jobs = []
        for sid, item in item_by_id.items():
            ans = ans_by_id.get(sid, "")
            if not ans:
                continue
            jobs.append((sid, item, ans))

        with ThreadPoolExecutor(max_workers=len(api_keys)) as pool:
            futures = {}
            for i, (sid, item, ans) in enumerate(jobs):
                cfg = api_keys[i % len(api_keys)]
                client = OpenAIInference(base_url=cfg["base_url"], api_key=cfg["api_key"],
                                         model=cfg["model"], temperature=0.1, max_tokens=16384)
                judge = LLMJudge(client)
                question = item.get("question", "")
                f = pool.submit(judge.score, task_id, question, ans, item)
                futures[f] = sid

            for f in as_completed(futures):
                try:
                    sr = f.result()
                    scores.append(sr.get("score_ratio", 0))
                except Exception as e:
                    scores.append(0)

        avg = sum(scores) / len(scores) if scores else 0
        results[grade] = {"mean": round(avg, 4), "count": len(scores)}
        print(f"  {grade}: {avg:.4f} ({len(scores)} samples)")

    # trick 答案：先用 LLM 生成，再用 Judge 评分
    for trick in TRICKS:
        trick_data = load_trick_answers("case_analysis", trick)
        if not trick_data:
            print(f"  [SKIP] {trick} not found")
            continue

        prompt_template = trick_data.get("prompt_template", "")
        items_list = trick_data.get("items", [])

        print(f"\n  {trick}: 生成对抗答案...")

        # Step 1: LLM 生成对抗答案
        generated = {}
        with ThreadPoolExecutor(max_workers=len(api_keys)) as pool:
            futures = {}
            for i, trick_item in enumerate(items_list):
                sid = trick_item["id"]
                question = trick_item["question"]
                prompt = prompt_template.replace("{question}", question)
                cfg = api_keys[i % len(api_keys)]
                client = OpenAIInference(base_url=cfg["base_url"], api_key=cfg["api_key"],
                                         model=cfg["model"], temperature=0.7, max_tokens=4096)
                f = pool.submit(client.infer, "你是一个法律AI助手。", prompt)
                futures[f] = sid

            for f in as_completed(futures):
                sid = futures[f]
                try:
                    generated[sid] = f.result()
                except Exception as e:
                    generated[sid] = f"生成失败: {e}"

        print(f"  {trick}: 生成完成，开始评分...")

        # Step 2: Judge 评分
        scores = []
        jobs = []
        for trick_item in items_list:
            sid = trick_item["id"]
            item = item_by_id.get(sid)
            if not item or sid not in generated:
                continue
            jobs.append((sid, item, generated[sid]))

        with ThreadPoolExecutor(max_workers=len(api_keys)) as pool:
            futures = {}
            for i, (sid, item, ans) in enumerate(jobs):
                cfg = api_keys[i % len(api_keys)]
                client = OpenAIInference(base_url=cfg["base_url"], api_key=cfg["api_key"],
                                         model=cfg["model"], temperature=0.1, max_tokens=16384)
                judge = LLMJudge(client)
                question = item.get("question", "")
                f = pool.submit(judge.score, task_id, question, ans, item)
                futures[f] = sid

            for f in as_completed(futures):
                try:
                    sr = f.result()
                    scores.append(sr.get("score_ratio", 0))
                except Exception as e:
                    scores.append(0)

        avg = sum(scores) / len(scores) if scores else 0
        results[trick] = {"mean": round(avg, 4), "count": len(scores)}
        print(f"  {trick}: {avg:.4f} ({len(scores)} samples)")

    return results


def main():
    start = time.time()
    api_keys = load_api_keys()
    print(f"  {len(api_keys)} 条 API Key 可用")

    all_results = {}

    # 客观 1: 法条背诵
    all_results["statute_recitation"] = score_objective(
        "legal_qa.memorization.statute_recitation",
        "statute_recitation",
        rouge_l_score,
        "rouge_l",
    )

    # 客观 2: 阅读理解
    all_results["reading_comprehension"] = score_objective(
        "legal_qa.understanding.reading_comprehension",
        "reading_comprehension",
        rc_f1_score,
        "rc_f1",
    )

    # 主观: 案情分析
    if api_keys:
        all_results["case_analysis"] = generate_and_score_subjective(api_keys)
    else:
        print("\n  [SKIP] 案情分析：无 API Key")

    elapsed = round(time.time() - start, 1)

    # 保存汇总
    summary = {
        "elapsed": elapsed,
        "tasks": all_results,
    }
    out_path = TRICK_DIR / "_adversarial_trick_summary.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    # 打印汇总
    print(f"\n\n{'='*60}")
    print(f" 对抗性表面欺骗测试结果 ({elapsed}s)")
    print(f"{'='*60}")

    for task_name, task_results in all_results.items():
        print(f"\n  {task_name}:")
        for key in ["good", "trick_A", "trick_B", "trick_C", "bad"]:
            if key in task_results:
                r = task_results[key]
                print(f"    {key:10s}: {r['mean']:.4f}  (n={r['count']})")

    print(f"\n  结果 -> {out_path}")


if __name__ == "__main__":
    main()
