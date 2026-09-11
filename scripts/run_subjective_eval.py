"""
run_subjective_eval.py
主观任务一站式评测：生成智法AI答案 + LLM-as-Judge Rubric 评分

生成阶段：3 个子进程并行调用 run_zhifa_eval.py（按模块 + API Key 隔离）
评分阶段：LLMJudge 逐任务串行评分（断点续跑，每条实时保存）

用法：
    python scripts/run_subjective_eval.py                       # 全部难度
    python scripts/run_subjective_eval.py standard              # 只跑 standard
    python scripts/run_subjective_eval.py --judge 2             # 指定 Judge
    python scripts/run_subjective_eval.py --skip-generate       # 跳过生成，只评分
"""

import sys, os, io, json, time, argparse, subprocess
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

from zhifa_eval.data_loader import TASK_MAP, load_task_data
from zhifa_eval.inference.openai_inference import OpenAIInference
from zhifa_eval.scorers.subjective.llm_judge import LLMJudge

OUTPUT_DIR = PROJECT_ROOT / "zhifa_outputs"
SCORES_DIR = OUTPUT_DIR / "scores"

COMMON = ["--fast"]
DIFFICULTIES = ["standard", "challenge", "adversarial"]

SUBJECTIVE_TASKS = [
    "legal_qa.application.consultation_fact_inquiry",
    "legal_qa.application.case_analysis",
    "legal_qa.application.legal_document_generation",
    "contract_review.risk_detection",
    "contract_review.risk_revision",
    "case_prediction.comprehensive_judgment_prediction",
]

GENERATE_CMDS = [
    {
        "name": "legal_qa (主观 3 题)",
        "args": ["--key", "1", "--tasks",
                 "legal_qa.application.consultation_fact_inquiry",
                 "legal_qa.application.case_analysis",
                 "legal_qa.application.legal_document_generation"],
    },
    {
        "name": "contract_review (主观 2 题)",
        "args": ["--key", "2", "--tasks",
                 "contract_review.risk_detection",
                 "contract_review.risk_revision"],
    },
    {
        "name": "case_prediction (主观 1 题)",
        "args": ["--key", "3", "--tasks",
                 "case_prediction.comprehensive_judgment_prediction"],
    },
]

MAX_JUDGE_RETRY = 2


# ═══════════════════════════════════════════════════════════
#  生成阶段
# ═══════════════════════════════════════════════════════════

def run_generate(difficulty):
    print(f"\n{'=' * 55}")
    print(f" 生成主观题答案 [{difficulty}]（3 进程并行）")
    print(f"{'=' * 55}")

    procs = []
    for cmd in GENERATE_CMDS:
        full = ([sys.executable, "scripts/run_zhifa_eval.py"]
                + COMMON + ["--difficulty", difficulty] + cmd["args"])
        print(f"  启动: {cmd['name']}")
        p = subprocess.Popen(full)
        procs.append((cmd["name"], p))

    for name, p in procs:
        p.wait()
        status = "OK" if p.returncode == 0 else f"ERROR (code {p.returncode})"
        print(f"  完成: {name} -> {status}")


# ═══════════════════════════════════════════════════════════
#  评分阶段
# ═══════════════════════════════════════════════════════════

def parse_judge_config(config_str):
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


def score_task(task_id, judge_client, difficulty):
    task = TASK_MAP[task_id]

    ans_path = get_answer_path(task_id, difficulty)
    if not ans_path.exists():
        print(f"  [SKIP] {task.display_name}: 答案文件不存在 {ans_path.name}")
        return None

    with open(ans_path, "r", encoding="utf-8") as f:
        ans_data = json.load(f)
    answers_by_id = {a["id"]: a["answer"] for a in ans_data.get("answers", [])}

    try:
        all_data = load_task_data(task_id, difficulty)
    except (ValueError, FileNotFoundError) as e:
        print(f"  [SKIP] {task.display_name}: {e}")
        return None
    n = min(len(all_data), len(answers_by_id))

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

        if i in existing:
            scores_list.append(existing[i])
            continue

        item = all_data[i]
        answer = answers_by_id[i]
        question = item.get("question", item.get("conversation", ""))

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

        save_scores(score_path, task_id, difficulty, scores_list)

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


def run_scoring(difficulty, judge_client):
    diff_str = f" [{difficulty}]" if difficulty != "standard" else ""
    print(f"\n{'=' * 55}")
    print(f" 主观评分{diff_str} | {len(SUBJECTIVE_TASKS)} 个任务")
    print(f"{'=' * 55}")

    results = []
    for tid in SUBJECTIVE_TASKS:
        if tid not in TASK_MAP:
            print(f"  [SKIP] 未知任务: {tid}")
            continue
        r = score_task(tid, judge_client, difficulty)
        if r:
            results.append(r)

    if results:
        print(f"\n  {'任务':<28} {'avg_ratio':>10} {'ok_rate':>10}")
        print(f"  {'-'*50}")
        for r in results:
            print(f"  {r['display_name']:<26} {r['avg_ratio']:>10.4f} {r['ok_rate']:>10}")
        overall = sum(r["avg_ratio"] for r in results) / len(results)
        print(f"  {'-'*50}")
        print(f"  {'总平均':<26} {overall:>10.4f}")

    return results


# ═══════════════════════════════════════════════════════════
#  主流程
# ═══════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="主观任务一站式评测（生成 + 评分）")
    parser.add_argument("target", nargs="?", default="all",
                        choices=["standard", "challenge", "adversarial", "all"],
                        help="难度（默认 all）")
    parser.add_argument("--judge", type=int, default=1,
                        help="使用 RUBRIC_API_N（1-3），默认 1")
    parser.add_argument("--skip-generate", action="store_true",
                        help="跳过生成阶段，只评分")
    parser.add_argument("--scores-dir", default=None,
                        help="评分输出目录（默认 zhifa_outputs/scores/）")
    args = parser.parse_args()

    global SCORES_DIR
    if args.scores_dir:
        SCORES_DIR = Path(args.scores_dir)
    SCORES_DIR.mkdir(parents=True, exist_ok=True)

    judge_cfg = parse_judge_config(os.getenv(f"RUBRIC_API_{args.judge}", ""))
    if not judge_cfg:
        print(f"ERROR: RUBRIC_API_{args.judge} 未配置或格式错误")
        sys.exit(1)

    judge_client = OpenAIInference(
        judge_cfg["url"], judge_cfg["key"], judge_cfg["model"],
        temperature=0.0, max_tokens=16384,
    )
    print(f"Judge: {judge_cfg['name']} ({judge_cfg['model']})")

    diffs = DIFFICULTIES if args.target == "all" else [args.target]

    start = time.time()
    all_results = []

    for diff in diffs:
        if not args.skip_generate:
            run_generate(diff)

        results = run_scoring(diff, judge_client)
        all_results.extend(results)

    elapsed = round(time.time() - start, 1)

    # 总汇总
    print(f"\n{'=' * 55}")
    print(f" 全部完成 ({elapsed}s)")
    print(f"{'=' * 55}")

    if all_results:
        overall = sum(r["avg_ratio"] for r in all_results) / len(all_results)
        print(f"  {len(all_results)} 个任务 | 总平均 avg_ratio={overall:.4f}")

    summary = {
        "elapsed": elapsed,
        "judge": f"JUDGE_{args.judge}",
        "difficulties": diffs,
        "results": all_results,
    }
    summary_path = SCORES_DIR / "_subjective_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"  汇总 -> {summary_path}")


if __name__ == "__main__":
    main()
