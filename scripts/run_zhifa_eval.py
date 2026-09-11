"""
run_zhifa_eval.py
用智法AI跑 LegalEval 17 个子任务的评测。

用法：
    # 跑全量数据（默认）
    python scripts/run_zhifa_eval.py

    # --difficulty 选择数据集：standard（默认）/ challenge / adversarial
    python scripts/run_zhifa_eval.py --difficulty challenge

    # --module 只跑一个模块（开 3 个终端，各用不同 --key 并行）
    python scripts/run_zhifa_eval.py --module legal_qa --key 1 --fast
    python scripts/run_zhifa_eval.py --module contract_review --key 2 --fast
    python scripts/run_zhifa_eval.py --module case_prediction --key 3 --fast

    # --key N 使用 .env 中的 ZHIFA_KEY_N 作为 API Key
    python scripts/run_zhifa_eval.py --key 1

    # --fast 关掉网页搜索，只用向量库检索（大幅加速）
    python scripts/run_zhifa_eval.py --fast

    # 全量跑所有难度（3 条命令依次执行）
    python scripts/run_zhifa_eval.py --difficulty standard
    python scripts/run_zhifa_eval.py --difficulty challenge
    python scripts/run_zhifa_eval.py --difficulty adversarial

    # 断点续跑：重复执行同一命令即可，已完成的题目自动跳过
"""

import sys, os, json, time, argparse
from pathlib import Path
from datetime import datetime

# 项目路径
EVAL_ROOT = Path(__file__).parent.parent  # ZhiFa-LegalEval/
ZHIFA_ROOT = EVAL_ROOT / "ZhiFa"         # ZhiFa-LegalEval/ZhiFa/

sys.path.insert(0, str(EVAL_ROOT))
sys.path.insert(0, str(ZHIFA_ROOT))

from zhifa_eval.data_loader import TASK_REGISTRY, TASK_MAP, load_task_data
from scripts.adapters.legal_qa_adapter import LegalQAAdapter, LEGAL_QA_TASKS
from scripts.adapters.contract_review_adapter import ContractReviewAdapter, CONTRACT_TASKS
from scripts.adapters.case_prediction_adapter import CasePredictionAdapter, CASE_PREDICTION_TASKS

OUTPUT_DIR = EVAL_ROOT / "zhifa_outputs"

# 模块 → 适配器 + 子任务列表
MODULE_CONFIG = {
    "legal_qa": {
        "adapter": LegalQAAdapter(),
        "tasks": sorted(LEGAL_QA_TASKS),
    },
    "contract_review": {
        "adapter": ContractReviewAdapter(),
        "tasks": sorted(CONTRACT_TASKS),
    },
    "case_prediction": {
        "adapter": CasePredictionAdapter(),
        "tasks": sorted(CASE_PREDICTION_TASKS),
    },
}


def get_output_path(task_id, difficulty="standard", shard_tag=""):
    tag = f"_{shard_tag}" if shard_tag else ""
    if difficulty == "standard":
        return OUTPUT_DIR / f"{task_id}{tag}.json"
    return OUTPUT_DIR / f"{task_id}_{difficulty}{tag}.json"


def load_existing(output_path):
    """加载已有输出，用于断点续跑"""
    if output_path.exists():
        with open(output_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        items = {a["id"]: a for a in data.get("answers", [])}
        return items
    return {}


def save_output(output_path, task, answers_list, difficulty="standard"):
    meta = {
        "task_id": task.task_id,
        "display_name": task.display_name,
        "difficulty": difficulty,
        "count": len(answers_list),
        "model": "zhifa-ai",
        "timestamp": datetime.now().isoformat(),
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump({"meta": meta, "answers": answers_list}, f, ensure_ascii=False, indent=2)


# ═══════════════════════════════════════════════════════════
#  智法AI Chain 懒加载
# ═══════════════════════════════════════════════════════════

_chains = {}
_fast_mode = False


def _patch_config_for_fast():
    from src.config.config import config
    config.WEB_VS_SEARCH_K = 0
    config.WEB_AI_REFINE_ENABLED = False
    config.WEB_SEARCH_FETCH_K = 0
    print("  [fast mode] 关闭网页搜索，只用向量库检索")


def set_api_key(key_index: int):
    """通过 --key N 切换 API Key"""
    if key_index:
        key = os.getenv(f"ZHIFA_KEY_{key_index}", "")
        if key:
            os.environ["HUNYUAN_API_KEY"] = key
            print(f"  [api key] 使用 ZHIFA_KEY_{key_index}: {key[:8]}...")
            return True
        print(f"  [api key] ZHIFA_KEY_{key_index} 为空，使用默认")
    return False


def get_chain(module_name):
    if module_name in _chains:
        return _chains[module_name]

    old_cwd = os.getcwd()
    os.chdir(str(ZHIFA_ROOT))

    try:
        if _fast_mode:
            _patch_config_for_fast()

        if module_name == "legal_qa":
            from evaluation.batch_legal_qa import BatchLegalQA
            batch = BatchLegalQA(max_retries=3, retry_delay=5.0)
            batch._get_chain()
            _chains[module_name] = batch
            print(f"  [legal_qa] Chain 初始化完成")

        elif module_name == "contract_review":
            from evaluation.batch_contract_review import BatchContractReview
            batch = BatchContractReview(max_retries=3, retry_delay=5.0)
            batch._get_chain()
            _chains[module_name] = batch
            print(f"  [contract_review] Chain 初始化完成")

        elif module_name == "case_prediction":
            from evaluation.batch_case_prediction import BatchCasePrediction
            batch = BatchCasePrediction(max_retries=3, retry_delay=5.0)
            batch._get_chain()
            _chains[module_name] = batch
            print(f"  [case_prediction] Chain 初始化完成")
    finally:
        os.chdir(old_cwd)

    return _chains.get(module_name)


def run_single_infer(batch_module, zhifa_input, index):
    """调用智法AI单条推理（带重试），cwd 切到 ZHIFA_ROOT"""
    old_cwd = os.getcwd()
    os.chdir(str(ZHIFA_ROOT))
    try:
        result = batch_module.infer_single_with_retry(zhifa_input, index)
    finally:
        os.chdir(old_cwd)
    if result["status"] == "success":
        return result["output"]
    else:
        return {"answer": f"[ERROR] {result.get('error', 'unknown')}", "ai_response": ""}


# ═══════════════════════════════════════════════════════════
#  主流程
# ═══════════════════════════════════════════════════════════

def run_task(task_id, adapter, batch_module, difficulty="standard", shard_tag=""):
    """跑一个子任务，默认断点续跑，每条实时保存"""
    task = TASK_MAP[task_id]
    all_data = load_task_data(task_id, difficulty)
    n = len(all_data)

    output_path = get_output_path(task_id, difficulty, shard_tag)

    # 自动加载已有结果（断点续跑）
    existing = load_existing(output_path)
    if len(existing) >= n:
        print(f"\n  [{task.display_name}] 已完成 {n}/{n}，跳过", flush=True)
        return len(existing), n

    answers_list = []
    skipped = 0

    print(f"\n  [{task.display_name}] {n} 条"
          f"（已有 {len(existing)} 条）", flush=True)

    for i, item in enumerate(all_data):
        question = item.get("question", item.get("conversation", ""))
        reference = item.get("answer", "")

        # 断点续跑：已有结果则跳过
        if i in existing:
            answers_list.append(existing[i])
            skipped += 1
            continue

        # 输入转换
        zhifa_input = adapter.to_zhifa_input(task_id, item)

        # 调用智法AI
        t0 = time.time()
        zhifa_output = run_single_infer(batch_module, zhifa_input, i)
        elapsed = time.time() - t0

        # 输出转换
        answer = adapter.from_zhifa_output(task_id, zhifa_output, item)
        answers_list.append({
            "id": i,
            "question": question,
            "reference": reference,
            "answer": answer,
        })

        status = "✓" if not answer.startswith("[ERROR]") else "✗"
        ans_preview = answer.replace("\n", " ")[:80]
        ref_preview = reference.replace("\n", " ")[:80]
        print(f"    [{i+1}/{n}] {status} ({elapsed:.1f}s) {len(answer)} chars", flush=True)
        print(f"      答案: {ans_preview}", flush=True)
        if ref_preview:
            print(f"      参考: {ref_preview}", flush=True)

        # 每条都保存，防止中断丢失
        save_output(output_path, task, answers_list, difficulty)

    # 最终保存
    save_output(output_path, task, answers_list, difficulty)
    success = sum(1 for a in answers_list if not a["answer"].startswith("[ERROR]"))
    print(f"  -> {output_path.name} ({success}/{n} 成功, {skipped} 跳过)")
    return success, n


# ───────────────────────────────────────────────────────────
#  合同风险检测 + 修订：共享同一次 API 调用
# ───────────────────────────────────────────────────────────
RISK_PAIR = ("contract_review.risk_detection", "contract_review.risk_revision")


def run_contract_risk_paired(adapter, batch_module, difficulty="standard", shard_tag=""):
    """risk_detection 与 risk_revision 共享相同合同数据和 API 调用，
    一次推理同时产出两个任务的答案。"""
    # 两个任务数据源相同，取任一即可
    task_det = TASK_MAP[RISK_PAIR[0]]
    task_rev = TASK_MAP[RISK_PAIR[1]]
    all_data = load_task_data(RISK_PAIR[0], difficulty)
    n = len(all_data)

    path_det = get_output_path(RISK_PAIR[0], difficulty, shard_tag)
    path_rev = get_output_path(RISK_PAIR[1], difficulty, shard_tag)

    existing_det = load_existing(path_det)
    existing_rev = load_existing(path_rev)

    # 两个任务都跑完了才跳过
    if len(existing_det) >= n and len(existing_rev) >= n:
        print(f"\n  [风险检测+修订] 已完成 {n}/{n}，跳过", flush=True)
        return len(existing_det) + len(existing_rev), n * 2

    answers_det, answers_rev = [], []
    skipped = 0

    print(f"\n  [风险检测+修订 paired] {n} 条"
          f"（检测已有 {len(existing_det)}, 修订已有 {len(existing_rev)}）",
          flush=True)

    for i, item in enumerate(all_data):
        question = item.get("question", item.get("conversation", ""))
        reference_det = item.get("answer", "")
        reference_rev = item.get("answer", "")

        # 两个任务的第 i 条都已有结果 → 跳过
        if i in existing_det and i in existing_rev:
            answers_det.append(existing_det[i])
            answers_rev.append(existing_rev[i])
            skipped += 1
            continue

        # 只调一次 API
        zhifa_input = adapter.to_zhifa_input(RISK_PAIR[0], item)
        t0 = time.time()
        zhifa_output = run_single_infer(batch_module, zhifa_input, i)
        elapsed = time.time() - t0

        # 从同一个结果中分别提取
        ans_det = adapter.from_zhifa_output(RISK_PAIR[0], zhifa_output, item)
        ans_rev = adapter.from_zhifa_output(RISK_PAIR[1], zhifa_output, item)

        answers_det.append({
            "id": i, "question": question,
            "reference": reference_det, "answer": ans_det,
        })
        answers_rev.append({
            "id": i, "question": question,
            "reference": reference_rev, "answer": ans_rev,
        })

        status = "✓" if not ans_det.startswith("[ERROR]") else "✗"
        print(f"    [{i+1}/{n}] {status} ({elapsed:.1f}s) "
              f"检测 {len(ans_det)} chars / 修订 {len(ans_rev)} chars",
              flush=True)

        save_output(path_det, task_det, answers_det, difficulty)
        save_output(path_rev, task_rev, answers_rev, difficulty)

    save_output(path_det, task_det, answers_det, difficulty)
    save_output(path_rev, task_rev, answers_rev, difficulty)

    success_det = sum(1 for a in answers_det if not a["answer"].startswith("[ERROR]"))
    success_rev = sum(1 for a in answers_rev if not a["answer"].startswith("[ERROR]"))
    print(f"  -> {path_det.name} ({success_det}/{n})")
    print(f"  -> {path_rev.name} ({success_rev}/{n})")
    return success_det + success_rev, n * 2


def main():
    from dotenv import load_dotenv
    load_dotenv(EVAL_ROOT / ".env")     # LegalEval 的 .env（ZHIFA_KEY_1~6）
    load_dotenv(ZHIFA_ROOT / ".env")    # ZhiFa 的 .env（HUNYUAN_API_KEY）

    parser = argparse.ArgumentParser(description="用智法AI跑 LegalEval 17 子任务")
    parser.add_argument("--module", choices=["legal_qa", "contract_review", "case_prediction"],
                        help="只跑指定模块")
    parser.add_argument("--tasks", nargs="*", help="只跑指定子任务")
    parser.add_argument("--difficulty", default="standard",
                        choices=["standard", "challenge", "adversarial"],
                        help="数据集难度（默认 standard）")
    parser.add_argument("--key", type=int, default=0,
                        help="使用 .env 中的 ZHIFA_KEY_N（1-6），不指定则用默认 HUNYUAN_API_KEY")
    parser.add_argument("--fast", action="store_true",
                        help="快速模式：关掉网页搜索，只用向量库检索")
    parser.add_argument("--shard-tag", default="",
                        help="分片标签，输出文件名加后缀（用于并行不冲突）")
    args = parser.parse_args()

    global _fast_mode
    _fast_mode = args.fast

    # 切换 API Key（在 chain 初始化前）
    if args.key:
        set_api_key(args.key)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # 确定要跑的任务
    if args.tasks:
        task_ids = args.tasks
    elif args.module:
        task_ids = MODULE_CONFIG[args.module]["tasks"]
    else:
        task_ids = []
        for cfg in MODULE_CONFIG.values():
            task_ids.extend(cfg["tasks"])

    # 按模块分组
    module_tasks = {}
    for tid in task_ids:
        for mod_name, cfg in MODULE_CONFIG.items():
            if tid in cfg["tasks"]:
                module_tasks.setdefault(mod_name, []).append(tid)
                break

    # 预览总条数
    total_samples = 0
    print(f"{'='*60}")
    diff_str = f" [{args.difficulty}]" if args.difficulty != "standard" else ""
    print(f"智法AI 评测{diff_str} | {len(task_ids)} 个子任务")
    print(f"{'='*60}")
    for mod, tids in module_tasks.items():
        mod_total = 0
        for tid in tids:
            try:
                n = len(load_task_data(tid, args.difficulty))
            except ValueError:
                print(f"  [SKIP] {tid} 不支持 {args.difficulty} 难度")
                continue
            mod_total += n
        print(f"  {mod}: {len(tids)} 个子任务, {mod_total} 条")
        total_samples += mod_total
    print(f"  总计: {total_samples} 条")
    if args.key:
        print(f"  API Key: ZHIFA_KEY_{args.key}")

    total_success, total_count = 0, 0
    start = time.time()

    for mod_name, tids in module_tasks.items():
        print(f"\n{'#'*60}")
        print(f"# 模块: {mod_name}")
        print(f"{'#'*60}")

        adapter = MODULE_CONFIG[mod_name]["adapter"]
        batch_module = get_chain(mod_name)
        if batch_module is None:
            print(f"  [ERROR] {mod_name} chain 初始化失败，跳过")
            continue

        # 合同风险检测+修订：一次 API 调用同时产出两个任务
        risk_pair_tids = set(tids) & set(RISK_PAIR)
        if len(risk_pair_tids) == 2:
            success, count = run_contract_risk_paired(
                adapter, batch_module,
                args.difficulty, args.shard_tag)
            total_success += success
            total_count += count
            tids = [t for t in tids if t not in RISK_PAIR]

        for tid in tids:
            task = TASK_MAP[tid]
            if args.difficulty not in task.difficulties:
                print(f"  [SKIP] {tid} 不支持 {args.difficulty} 难度")
                continue
            success, count = run_task(tid, adapter, batch_module,
                                      args.difficulty, args.shard_tag)
            total_success += success
            total_count += count

    elapsed = round(time.time() - start, 1)
    print(f"\n{'='*60}")
    print(f"完成 | {total_success}/{total_count} 成功 | {elapsed}s")
    print(f"输出目录: {OUTPUT_DIR}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
