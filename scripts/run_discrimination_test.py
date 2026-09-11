"""
run_discrimination_test.py
抽取题目 → 生成好/中/差答案 → 评分 → 输出结果。

覆盖范围：
    - 6 个主观任务：LLM 生成三档答案 → LLM-as-Judge 评分（需要 API Key）
    - 11 个客观任务：规则构造三档答案 → 客观评分器评分（纯本地，无需 API）

题目抽取逻辑：
    1. 从 load_task_data(task_id, "standard") 加载全量标准题
    2. 同一批题目生成 good/medium/bad 三档答案，确保评分可比

用法:
    python scripts/run_discrimination_test.py                    # 正式测试
    python scripts/run_discrimination_test.py --only subjective  # 只跑主观
    python scripts/run_discrimination_test.py --only objective   # 只跑客观（无需 API）
    python scripts/run_discrimination_test.py --tasks legal_qa.application.case_analysis # 单任务
"""

import sys, os, json, time, argparse, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed


# 把项目根目录加入 path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

from zhifa_eval.data_loader import TASK_MAP, TASK_REGISTRY, load_task_data
from zhifa_eval.inference.openai_inference import OpenAIInference
from zhifa_eval.scorers.subjective.llm_judge import LLMJudge
from zhifa_eval.scorers.objective.metrics import METRIC_FUNCTIONS
from scripts.generate_test_subjective import TASK_PROMPTS, TASK_IDS_ORDERED
from scripts.generate_test_objective import (
    get_generator as get_obj_generator, make_rng,
    SEED_BASE,
)

OUTPUT_DIR = PROJECT_ROOT / "test_discrimination"
ANSWERS_DIR = OUTPUT_DIR / "answers"
SCORES_DIR = OUTPUT_DIR / "scores"
SEED = 42


def parse_api_config(config_str, fb_url="", fb_key="", fb_model=""):
    """解析 'BASE_URL|API_KEY|MODEL' 格式"""
    if not config_str or not config_str.strip():
        return fb_url, fb_key, fb_model
    parts = config_str.strip().split("|")
    url = parts[0] if len(parts) > 0 and parts[0] else fb_url
    key = parts[1] if len(parts) > 1 and parts[1] else fb_key
    model = parts[2] if len(parts) > 2 and parts[2] else fb_model
    return url, key, model


# ═══════════════════════════════════════════════════════════
#  单任务流水线
# ═══════════════════════════════════════════════════════════

def run_task(tid, gen_client, judge_client):
    task = TASK_MAP[tid]
    all_data = load_task_data(tid, "standard")
    n = len(all_data)

    print(f"\n[{task.display_name}] 全量 {n} 条",
          flush=True)

    prompts = TASK_PROMPTS[tid]
    judge = LLMJudge(judge_client)

    MAX_GEN_RETRY = 2   # 生成答案为空时重试
    MAX_JUDGE_RETRY = 2  # Judge 返回空时重试

    task_results = {}
    for grade in ["good", "medium", "bad"]:
        prompt_fn = prompts[grade]

        # 加载已有答案（复用，不重新生成）
        ANSWERS_DIR.mkdir(parents=True, exist_ok=True)
        SCORES_DIR.mkdir(parents=True, exist_ok=True)
        ans_path = ANSWERS_DIR / f"{tid}_{grade}.json"
        existing_answers = {}
        if ans_path.exists():
            with open(ans_path, "r", encoding="utf-8") as f:
                old = json.load(f)
            for a in old.get("answers", []):
                aid = a.get("id")
                if aid is not None and a.get("answer", ""):
                    existing_answers[aid] = a["answer"]
            if existing_answers:
                print(f"  [{task.display_name}] {grade}: 复用 {len(existing_answers)} 条已有答案",
                      flush=True)

        answers = []
        scores = []

        for i, item in enumerate(all_data):
            # 如果已有答案则复用，否则生成
            if i in existing_answers:
                answer = existing_answers[i]
            else:
                sys_p, user_p, temp = prompt_fn(item)
                gen_client.temperature = temp
                answer = ""
                for gen_attempt in range(1 + MAX_GEN_RETRY):
                    try:
                        answer = gen_client.infer(instruction=sys_p, question=user_p)
                    except Exception as e:
                        answer = f"[ERROR] {e}"
                    if answer and not answer.startswith("[ERROR]"):
                        break
                    print(f"  [{task.display_name}] {grade} [{i+1}/{n}] "
                          f"gen retry {gen_attempt+1}: empty/error", flush=True)

            answers.append({"id": i, "answer": answer})

            # Judge 评分（带重试）
            question = item.get("question", item.get("conversation", ""))
            sr = {}
            for judge_attempt in range(1 + MAX_JUDGE_RETRY):
                try:
                    sr = judge.score(tid, question, answer, item)
                    ratio = max(0, sr.get("score_ratio", 0))
                    val = sr.get("validation", "ok")
                    # 检查 judge_raw 是否为空
                    if sr.get("judge_raw", ""):
                        break
                    print(f"  [{task.display_name}] {grade} [{i+1}/{n}] "
                          f"judge retry {judge_attempt+1}: empty judge_raw", flush=True)
                except Exception as e:
                    ratio, val, sr = 0, f"judge_error:{e}", {}
                    print(f"  [{task.display_name}] {grade} [{i+1}/{n}] "
                          f"judge retry {judge_attempt+1}: {e}", flush=True)

            scores.append({
                "id": i,
                "score_ratio": ratio,
                "total_score": sr.get("total_score", 0),
                "max_score": sr.get("max_score", 0),
                "item_scores": sr.get("item_scores", []),
                "validation": val,
                "attempts": sr.get("attempts", 0),
                "judge_raw": sr.get("judge_raw", ""),
            })

            tag = "✓" if val == "ok" else "⚠"
            print(f"  [{task.display_name}] {grade:6s} [{i+1}/{n}] "
                  f"ratio={ratio:.3f} {tag}", flush=True)

        # 保存答案
        ANSWERS_DIR.mkdir(parents=True, exist_ok=True)
        SCORES_DIR.mkdir(parents=True, exist_ok=True)
        meta = {"task_id": tid, "display_name": task.display_name,
                "difficulty": "standard",
                "seed": SEED, "count": n, "grade": grade}
        ans_path = ANSWERS_DIR / f"{tid}_{grade}.json"
        with open(ans_path, "w", encoding="utf-8") as f:
            json.dump({"meta": meta, "answers": answers}, f, ensure_ascii=False, indent=2)

        # 保存评分
        score_path = SCORES_DIR / f"{tid}_{grade}.json"
        with open(score_path, "w", encoding="utf-8") as f:
            json.dump({"meta": meta, "scores": scores}, f, ensure_ascii=False, indent=2)

        avg = sum(s["score_ratio"] for s in scores) / n if n else 0
        task_results[grade] = round(avg, 4)

    return tid, task_results


OBJECTIVE_TASK_IDS = [
    t.task_id for t in TASK_REGISTRY if t.eval_method == "objective"
]


def run_objective_task(tid):
    """对一个客观任务：生成/加载三档答案 → 客观评分器评分 → 返回平均分"""
    task = TASK_MAP[tid]
    metric_name = task.metrics[0]
    metric_fn = METRIC_FUNCTIONS.get(metric_name)
    if not metric_fn:
        print(f"  [SKIP] {task.display_name}: 未知指标 {metric_name}")
        return None

    try:
        all_data = load_task_data(tid, "standard")
    except Exception as e:
        print(f"  [SKIP] {task.display_name}: {e}")
        return None

    n = len(all_data)

    gen_func = get_obj_generator(task)
    task_results = {}

    for grade in ["good", "medium", "bad"]:
        ans_path = ANSWERS_DIR / f"{tid}_{grade}.json"

        # 复用已有答案或重新生成
        if ans_path.exists():
            with open(ans_path, "r", encoding="utf-8") as f:
                old = json.load(f)
            old_answers = old.get("answers", [])
            if len(old_answers) >= n:
                answers = [a["answer"] for a in old_answers[:n]]
            else:
                rng = make_rng(tid, grade)
                answers = gen_func(all_data, grade, rng)
        else:
            rng = make_rng(tid, grade)
            answers = gen_func(all_data, grade, rng)
            ANSWERS_DIR.mkdir(parents=True, exist_ok=True)
            meta = {"task_id": tid, "display_name": task.display_name,
                    "difficulty": "standard",
                    "seed": SEED, "count": n, "grade": grade}
            with open(ans_path, "w", encoding="utf-8") as f:
                json.dump({"meta": meta, "answers": [
                    {"id": i, "answer": a} for i, a in enumerate(answers)
                ]}, f, ensure_ascii=False, indent=2)

        # 评分
        scores = []
        for i in range(n):
            ref = all_data[i].get("answer", "")
            pred = answers[i] if i < len(answers) else ""
            result = metric_fn(pred, ref)
            primary_key = list(result.keys())[0]
            scores.append(result[primary_key])

        avg = sum(scores) / n if n else 0
        task_results[grade] = round(avg, 4)

        # 保存评分
        SCORES_DIR.mkdir(parents=True, exist_ok=True)
        score_path = SCORES_DIR / f"{tid}_{grade}.json"
        score_entries = [{"id": i, "score_ratio": scores[i]} for i in range(n)]
        with open(score_path, "w", encoding="utf-8") as f:
            json.dump({"meta": {"task_id": tid, "grade": grade, "metric": metric_name},
                        "scores": score_entries}, f, ensure_ascii=False, indent=2)

        print(f"  [{task.display_name}] {grade:6s} avg={avg:.4f} ({metric_name})", flush=True)

    return tid, task_results


# ═══════════════════════════════════════════════════════════
#  主流程
# ═══════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="判别力一站式验证（主观 + 客观）")
    parser.add_argument("--tasks", nargs="*", default=None,
                        help="指定任务 ID（默认全部 17 个）")
    parser.add_argument("--only", choices=["subjective", "objective"],
                        default=None, help="只跑主观或客观")
    parser.add_argument("--base-url", default=os.getenv("INFERENCE_BASE_URL", ""))
    parser.add_argument("--api-key", default=os.getenv("INFERENCE_API_KEY", ""))
    parser.add_argument("--model", default=os.getenv("INFERENCE_MODEL", ""))
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ANSWERS_DIR.mkdir(parents=True, exist_ok=True)
    SCORES_DIR.mkdir(parents=True, exist_ok=True)

    run_subj = args.only != "objective"
    run_obj = args.only != "subjective"

    import math
    def _std(vals):
        if len(vals) < 2:
            return 0.0
        mu = sum(vals) / len(vals)
        return math.sqrt(sum((v - mu) ** 2 for v in vals) / len(vals))

    start = time.time()
    all_results = {}       # tid -> {good, medium, bad}
    subj_results = {}
    obj_results = {}

    # ─── 客观题 ───────────────────────────────────────────
    if run_obj:
        obj_task_ids = args.tasks or OBJECTIVE_TASK_IDS
        obj_task_ids = [t for t in obj_task_ids if t in TASK_MAP and TASK_MAP[t].eval_method == "objective"]

        if obj_task_ids:
            print(f"\n{'='*70}")
            print(f" 客观题判别力验证：{len(obj_task_ids)} 个任务（纯本地评分）")
            print(f"{'='*70}")

            for tid in obj_task_ids:
                r = run_objective_task(tid)
                if r:
                    _, results = r
                    obj_results[tid] = results
                    all_results[tid] = results

    # ─── 主观题 ───────────────────────────────────────────
    if run_subj:
        subj_task_ids = args.tasks or TASK_IDS_ORDERED
        subj_task_ids = [t for t in subj_task_ids if t in TASK_PROMPTS]

        task_jobs = {}
        for i, tid in enumerate(subj_task_ids):
            env_val = os.getenv(f"RUBRIC_API_{i+1}", "")
            url, key, model = parse_api_config(env_val, args.base_url, args.api_key, args.model)
            if not key:
                print(f"[SKIP] {tid}: 无 API Key（设置 RUBRIC_API_{i+1}）")
                continue
            gc = OpenAIInference(url, key, model, max_tokens=16384)
            jc = OpenAIInference(url, key, model, temperature=0.0, max_tokens=16384)
            task_jobs[tid] = (gc, jc)
            total = len(load_task_data(tid, "standard"))
            print(f"  {TASK_MAP[tid].display_name}: {total} 条 -> {model}")

        if task_jobs:
            print(f"\n{'='*70}")
            print(f" 主观题判别力验证：{len(task_jobs)} 个任务并行（LLM Judge）")
            print(f"{'='*70}\n")

            with ThreadPoolExecutor(max_workers=len(task_jobs)) as pool:
                futures = {
                    pool.submit(run_task, tid, gc, jc): tid
                    for tid, (gc, jc) in task_jobs.items()
                }
                for f in as_completed(futures):
                    tid = futures[f]
                    try:
                        _, results = f.result()
                        subj_results[tid] = results
                        all_results[tid] = results
                    except Exception as e:
                        print(f"[ERROR] {tid}: {e}")
                        subj_results[tid] = {"good": 0, "medium": 0, "bad": 0}
                        all_results[tid] = {"good": 0, "medium": 0, "bad": 0}
        elif not args.only:
            print("\n  主观题：无可用 API Key，已跳过（可用 --only objective 只跑客观）")

    elapsed = round(time.time() - start, 1)

    if not all_results:
        print("\nERROR: 没有任何任务完成。")
        sys.exit(1)

    # ─── 汇总输出 ─────────────────────────────────────────
    def print_section(title, results_dict, task_order):
        if not results_dict:
            return 0
        print(f"\n  [{title}]")
        print(f"  {'任务':<30} {'good':>8} {'medium':>8} {'bad':>8}  状态")
        print(f"  {'-'*68}")
        ok = 0
        for tid in task_order:
            if tid not in results_dict:
                continue
            r = results_dict[tid]
            g, m, b = r["good"], r["medium"], r["bad"]
            if g > m > b:
                s = "✅ 通过"
                ok += 1
            elif g > b:
                s = "⚠️  部分"
            else:
                s = "❌ 失败"
            print(f"  {TASK_MAP[tid].display_name:<28} {g:>8.4f} {m:>8.4f} {b:>8.4f}  {s}")
        print(f"  通过: {ok}/{len(results_dict)}")

        all_g = [r["good"] for r in results_dict.values()]
        all_m = [r["medium"] for r in results_dict.values()]
        all_b = [r["bad"] for r in results_dict.values()]
        n = len(results_dict) or 1
        avg_g, avg_m, avg_b = sum(all_g)/n, sum(all_m)/n, sum(all_b)/n
        print(f"  平均: good={avg_g:.4f}  medium={avg_m:.4f}  bad={avg_b:.4f}  区分度={avg_g - avg_b:.4f}")
        print(f"  标准差: good={_std(all_g):.4f}  medium={_std(all_m):.4f}  bad={_std(all_b):.4f}")
        return ok

    print(f"\n{'='*70}")
    print(f" 判别力验证结果 ({elapsed}s)")
    print(f"{'='*70}")

    obj_ok = print_section("客观题", obj_results, OBJECTIVE_TASK_IDS)
    subj_ok = print_section("主观题", subj_results, TASK_IDS_ORDERED)

    total_ok = obj_ok + subj_ok
    total_n = len(all_results)
    print(f"\n  {'-'*68}")
    print(f"  总计通过: {total_ok}/{total_n}")

    # 逐任务样本内标准差
    print(f"\n  任务内样本标准差:")
    task_stds = {}
    for tid in list(OBJECTIVE_TASK_IDS) + list(TASK_IDS_ORDERED):
        if tid not in all_results:
            continue
        stds = {}
        for grade in ["good", "medium", "bad"]:
            score_path = SCORES_DIR / f"{tid}_{grade}.json"
            if score_path.exists():
                with open(score_path, "r", encoding="utf-8") as f:
                    sd = json.load(f)
                ratios = [s.get("score_ratio", 0) for s in sd.get("scores", [])]
                stds[grade] = round(_std(ratios), 4)
            else:
                stds[grade] = 0.0
        task_stds[tid] = stds
        print(f"    {TASK_MAP[tid].display_name:<24} good σ={stds['good']:.4f}  "
              f"medium σ={stds['medium']:.4f}  bad σ={stds['bad']:.4f}")

    # 保存
    summary = {
        "elapsed": elapsed,
        "results": all_results,
        "objective_results": obj_results,
        "subjective_results": subj_results,
        "pass_rate": f"{total_ok}/{total_n}",
        "std_within_tasks": task_stds,
    }
    with open(OUTPUT_DIR / "_discrimination_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"\n  汇总 -> {OUTPUT_DIR / '_discrimination_summary.json'}")


if __name__ == "__main__":
    main()
