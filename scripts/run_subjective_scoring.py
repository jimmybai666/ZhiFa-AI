"""
run_subjective_scoring.py
对 6 个主观任务的智法AI答案进行 LLM-as-Judge Rubric 评分。

前置条件：zhifa_outputs/ 中已有答案文件（由 run_zhifa_eval.py 生成）

用法：
    # 评分全部 6 个主观任务
    python scripts/run_subjective_scoring.py

    # 指定任务
    python scripts/run_subjective_scoring.py --tasks legal_qa.application.case_analysis

    # 指定 Judge（默认用 JUDGE_1）
    python scripts/run_subjective_scoring.py --judge 2
"""

import sys, os, json, time, argparse, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

from zhifa_eval.data_loader import TASK_MAP, load_task_data
from zhifa_eval.inference.openai_inference import OpenAIInference
from zhifa_eval.scorers.subjective.llm_judge import LLMJudge

OUTPUT_DIR = PROJECT_ROOT / "zhifa_outputs"
SCORES_DIR = OUTPUT_DIR / "scores"

SUBJECTIVE_TASKS = [
    "legal_qa.application.consultation_fact_inquiry",
    "legal_qa.application.case_analysis",
    "legal_qa.application.legal_document_generation",
    "contract_review.risk_detection",
    "contract_review.risk_revision",
    "case_prediction.comprehensive_judgment_prediction",
]

MAX_JUDGE_RETRY = 2


def parse_judge_config(config_str):
    """解析 JUDGE_N='BASE_URL|API_KEY|MODEL|DISPLAY_NAME' """
    if not config_str or not config_str.strip():
        return None
    parts = config_str.strip().split("|")
    if len(parts) < 3 or not parts[1]:
        return None
    return {
        "url": parts[0],
        "key": parts[1],
        "model": parts[2],
        "name": parts[3] if len(parts) > 3 else parts[2],
    }


def get_answer_path(task_id, difficulty="standard"):
    if difficulty == "standard":
        return OUTPUT_DIR / f"{task_id}.json"
    return OUTPUT_DIR / f"{task_id}_{difficulty}.json"


def get_score_path(task_id, difficulty="standard"):
    if difficulty == "standard":
        return SCORES_DIR / f"{task_id}_scores.json"
    return SCORES_DIR / f"{task_id}_{difficulty}_scores.json"


def load_existing_scores(score_path):
    if score_path.exists():
        with open(score_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {s["id"]: s for s in data.get("scores", [])}
    return {}


def save_scores(score_path, task_id, difficulty, scores_list):
    meta = {
        "task_id": task_id,
        "display_name": TASK_MAP[task_id].display_name,
        "difficulty": difficulty,
        "count": len(scores_list),
    }
    SCORES_DIR.mkdir(parents=True, exist_ok=True)
    with open(score_path, "w", encoding="utf-8") as f:
        json.dump({"meta": meta, "scores": scores_list}, f, ensure_ascii=False, indent=2)


# ─── PLACEHOLDER_SCORE_TASK ───


def score_task(task_id, judge_client, difficulty):
    """对一个主观任务评分"""
    task = TASK_MAP[task_id]

    # 1. 加载答案文件
    ans_path = get_answer_path(task_id, difficulty)
    if not ans_path.exists():
        print(f"  [SKIP] {task.display_name}: 答案文件不存在 {ans_path.name}")
        return None

    with open(ans_path, "r", encoding="utf-8") as f:
        ans_data = json.load(f)
    answers_by_id = {a["id"]: a["answer"] for a in ans_data.get("answers", [])}

    # 2. 加载原始数据（含 rubric）
    try:
        all_data = load_task_data(task_id, difficulty)
    except (ValueError, FileNotFoundError) as e:
        print(f"  [SKIP] {task.display_name}: {e}")
        return None
    n = min(len(all_data), len(answers_by_id))

    # 3. 断点续跑
    score_path = get_score_path(task_id, difficulty)
    existing = load_existing_scores(score_path)

    judge = LLMJudge(judge_client)
    scores_list = []
    new_count = 0

    print(f"\n  [{task.display_name}] {n} 条待评"
          f"（已有 {len(existing)} 条）", flush=True)

    for i in range(n):
        if i not in answers_by_id:
            continue

        # 断点续跑
        if i in existing:
            scores_list.append(existing[i])
            continue

        item = all_data[i]
        answer = answers_by_id[i]
        question = item.get("question", item.get("conversation", ""))

        # Judge 评分（带重试）
        sr = {}
        for attempt in range(1 + MAX_JUDGE_RETRY):
            try:
                sr = judge.score(task_id, question, answer, item)
                if sr.get("judge_raw", ""):
                    break
                print(f"    [{i+1}/{n}] judge retry {attempt+1}: empty", flush=True)
            except Exception as e:
                sr = {}
                print(f"    [{i+1}/{n}] judge error {attempt+1}: {e}", flush=True)

        ratio_val = max(0, sr.get("score_ratio", 0))
        val = sr.get("validation", "judge_failed")

        score_entry = {
            "id": i,
            "score_ratio": ratio_val,
            "total_score": sr.get("total_score", 0),
            "max_score": sr.get("max_score", 0),
            "item_scores": sr.get("item_scores", []),
            "validation": val,
            "attempts": sr.get("attempts", 0),
            "judge_raw": sr.get("judge_raw", ""),
        }
        scores_list.append(score_entry)
        new_count += 1

        tag = "ok" if val == "ok" else val[:20]
        print(f"    [{i+1}/{n}] ratio={ratio_val:.3f} [{tag}]", flush=True)

        # 每条实时保存
        save_scores(score_path, task_id, difficulty, scores_list)

    # 最终保存
    save_scores(score_path, task_id, difficulty, scores_list)

    avg = sum(s["score_ratio"] for s in scores_list) / len(scores_list) if scores_list else 0
    ok_count = sum(1 for s in scores_list if s["validation"] == "ok")
    print(f"  -> {score_path.name} | avg={avg:.4f} | {ok_count}/{len(scores_list)} ok"
          f" | {new_count} new", flush=True)

    return {
        "task_id": task_id,
        "display_name": task.display_name,
        "count": len(scores_list),
        "avg_ratio": round(avg, 4),
        "ok_rate": f"{ok_count}/{len(scores_list)}",
    }


# ─── PLACEHOLDER_MAIN ───


def main():
    parser = argparse.ArgumentParser(description="主观任务 Rubric 评分")
    parser.add_argument("--difficulty", default="standard",
                        choices=["standard", "challenge", "adversarial"])
    parser.add_argument("--tasks", nargs="*", default=None)
    parser.add_argument("--judge", type=int, default=1,
                        help="使用 JUDGE_N（1-3），默认 JUDGE_1")
    parser.add_argument("--scores-dir", default=None,
                        help="评分输出目录（默认 zhifa_outputs/scores/）")
    args = parser.parse_args()

    global SCORES_DIR
    if args.scores_dir:
        SCORES_DIR = Path(args.scores_dir)
    SCORES_DIR.mkdir(parents=True, exist_ok=True)
    task_ids = args.tasks or SUBJECTIVE_TASKS

    # 解析 Judge 配置
    judge_cfg = parse_judge_config(os.getenv(f"RUBRIC_API_{args.judge}", ""))
    if not judge_cfg:
        print(f"ERROR: RUBRIC_API_{args.judge} 未配置或格式错误")
        sys.exit(1)

    judge_client = OpenAIInference(
        judge_cfg["url"], judge_cfg["key"], judge_cfg["model"],
        temperature=0.0, max_tokens=16384,
    )
    print(f"Judge: {judge_cfg['name']} ({judge_cfg['model']})")

    diff_str = f" [{args.difficulty}]" if args.difficulty != "standard" else ""
    print(f"\n{'='*55}")
    print(f" 主观评分 | {len(task_ids)} 个任务{diff_str}")
    print(f"{'='*55}")

    start = time.time()
    results = []

    for tid in task_ids:
        if tid not in TASK_MAP:
            print(f"  [SKIP] 未知任务: {tid}")
            continue
        r = score_task(tid, judge_client, args.difficulty)
        if r:
            results.append(r)

    elapsed = round(time.time() - start, 1)

    # 汇总
    print(f"\n{'='*55}")
    print(f" 评分结果 ({elapsed}s)")
    print(f"{'='*55}")
    print(f"  {'任务':<28} {'avg_ratio':>10} {'ok_rate':>10}")
    print(f"  {'-'*50}")
    for r in results:
        print(f"  {r['display_name']:<26} {r['avg_ratio']:>10.4f} {r['ok_rate']:>10}")

    if results:
        overall = sum(r["avg_ratio"] for r in results) / len(results)
        print(f"  {'-'*50}")
        print(f"  {'总平均':<26} {overall:>10.4f}")

    # 保存汇总
    summary = {
        "elapsed": elapsed,
        "judge": f"JUDGE_{args.judge}",
        "difficulty": args.difficulty,
        "results": results,
    }
    summary_path = SCORES_DIR / "_subjective_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"\n  汇总 -> {summary_path}")


if __name__ == "__main__":
    main()
