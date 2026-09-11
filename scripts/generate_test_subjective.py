"""
generate_test_subjective.py
为 ZhiFa-Eval 6 个主观（Rubric）任务生成 good / medium / bad 三档测试答案。
需要 LLM API 调用。通过 .env 或命令行参数配置 API。

用法:
    python scripts/generate_test_subjective.py
"""

import sys, os, json, argparse, time, random
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
from zhifa_eval.data_loader import TASK_MAP, load_task_data
from zhifa_eval.inference.openai_inference import OpenAIInference

OUTPUT_DIR = Path(__file__).parent / "test_discrimination"
SEED = 42


def build_meta(task, count, grade):
    return {
        "task_id": task.task_id,
        "display_name": task.display_name,
        "difficulty": "standard",
        "seed": SEED,
        "count": count,
        "grade": grade,
    }


def save_json(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


# ═══════════════════════════════════════════════════════════
#  6 个任务的 Prompt 构建器
#  每个返回 (system_prompt, user_prompt, temperature)
# ═══════════════════════════════════════════════════════════

# --- consultation_fact_inquiry ---

def prompt_consultation_good(item):
    rubric_hints = "\n".join(
        f"- [{r['index']}] ({r['dimension']}) {r['criterion']}"
        for r in item.get("rubrics", [])
    )
    return (
        "你是一位资深律师，擅长在接待当事人时通过精准追问还原案件全貌、补齐证据链。",
        f"""以下是当事人的陈述：

{item['conversation']}

{item['question']}

请确保你的追问覆盖以下关键维度的问题：
{rubric_hints}

请输出完整的编号问题清单（10-25个问题）。""",
        0.0,
    )


def prompt_consultation_medium(item):
    return (
        "你是一位律师。",
        f"""以下是当事人的陈述：

{item['conversation']}

请只提出你认为最重要的 10-25 个跟进问题，简明扼要。仅输出编号问题清单。""",
        0.3,
    )


def prompt_consultation_bad(item):
    """给完整陈述但角色降质，问出来的问题不专业、覆盖少"""
    return (
        "你是一个热心但不懂法律的朋友。",
        f"""你的朋友跟你说了这些事情：

{item['conversation']}

你想帮他理清思路，请提出 3-5 个你觉得需要搞清楚的问题。
你不懂法律，所以不要问专业性的问题（比如证据、法条、权属登记之类的），只问你作为普通人好奇的事情。""",
        0.7,
    )


# --- case_analysis ---

def prompt_case_analysis_good(item):
    """给出完整 instruction + 模块结构 + 每个模块的条目数，逼模型逐条覆盖"""
    module_details = []
    for mod in item.get("rubrics", []):
        n_items = len(mod.get("items", []))
        module_details.append(f"  - 【{mod['module']}】（{mod['module_score']}分，{n_items}个评分点）")
    module_text = "\n".join(module_details)
    return (
        item.get("instruction", "你是一名资深法律从业者。"),
        f"""{item['question']}

请严格按照以下模块结构逐一展开作答，每个模块都必须详细论述，不可遗漏：
{module_text}

要求：
1. 【结论】必须明确给出最终结论
2. 【案情简述】完整复述关键事实（当事人、时间、金额、争议焦点）
3. 【分析过程】逐步推理，每一步都引用具体法条，不能跳步
4. 【依据法条】列出所有引用的法条全称和条文编号""",
        0.0,
    )


def prompt_case_analysis_medium(item):
    """给模块结构但只要求写其中两个模块，故意遗漏部分模块，分析过程简化不引用完整法条"""
    modules = [m["module"] for m in item.get("rubrics", [])]
    partial = modules[:2] if len(modules) >= 2 else modules
    return (
        "你是一名法律从业者。",
        f"""{item['question']}

请按以下模块结构作答，但只需要重点写【{'、'.join(partial)}】这两个模块，其他模块可以省略或一句话带过。
分析过程不需要逐条引用法条，概述主要法律依据即可。""",
        0.3,
    )


def prompt_case_analysis_bad(item):
    """不给任何结构要求，限制字数很短，不引用法条"""
    return (
        "",
        f"""{item['question'][:600]}

用一两句话说说你的直觉判断，不要分析，不要引用法条，100字以内。""",
        0.8,
    )


# --- legal_document_generation ---

def prompt_doc_gen_good(item):
    """给出完整的模块结构 + 每个模块要求，逼模型写完整文书"""
    doc_type = item.get("doc_type", "法律文书")
    module_details = []
    for mod in item.get("rubrics", []):
        items_desc = []
        for it in mod.get("items", []):
            items_desc.append(f"    {it['criterion'][:60]}")
        module_details.append(f"  【{mod['module']}】（{mod['module_score']}分）：")
        module_details.extend(items_desc[:3])  # 给前3个条目提示
    module_text = "\n".join(module_details)

    return (
        f"你是一位资深律师。请根据当事人陈述，起草一份完整、规范的{doc_type}。",
        f"""{item['question']}

请严格按照{doc_type}的标准格式撰写，必须涵盖以下所有模块：
{module_text}

特别要求：
1. 文书格式必须完整：标题、当事人信息、正文、证据清单、结尾落款
2. 当事人陈述中可能有法律陷阱（错误术语、不合理诉求、管辖错误等），务必识别并纠正
3. 所有引用的法条必须真实存在且编号正确
4. 证据清单必须列明每份证据的名称和证明目的
5. 请写完整，不要省略任何模块""",
        0.0,
    )


def prompt_doc_gen_medium(item):
    """只写核心部分，故意跳过格式、证据清单、程序抗辩"""
    doc_type = item.get("doc_type", "法律文书")
    return (
        "你是一位律师。",
        f"""{item['question']}

请起草一份{doc_type}的核心内容，只需要写：
1. 诉讼请求（或答辩请求）
2. 事实与理由

不需要写标题、当事人信息、证据清单、落款等格式内容。控制在 800 字以内。""",
        0.3,
    )


def prompt_doc_gen_bad(item):
    """降质但有内容：写一封非正式的投诉/请求信，有事实但无法律格式"""
    doc_type = item.get("doc_type", "文书")
    return (
        "",
        f"""有人遇到了下面这些事情，想给对方写封信表达自己的诉求：

{item['question'][:600]}

请帮他写一封 300 字左右的信件，用日常口语表达诉求和不满。
不要写成{doc_type}的格式，不要用法律术语，不要引用法条，就像给朋友写信一样，把事情经过和自己的想法说清楚就行。""",
        0.8,
    )

# --- risk_detection ---

def prompt_risk_detection_good(item):
    contract = item.get("_contract_text", "")
    risk_hints = "\n".join(
        f"- {r['risk_name']}（{r.get('clause_location', '')}）"
        for r in item.get("risks", [])
    )
    question = item.get("question", "请审阅以下合同，识别其中存在的法律风险。")
    return (
        "你是一位资深合同审查律师，精通《民法典》合同编。",
        f"""{question}

以下是合同原文：
{contract[:4000]}

请重点关注以下可能存在风险的条款：
{risk_hints}

对每个风险请指出：(1)风险名称 (2)对应的合同条款原文 (3)风险解释 (4)法律依据 (5)修改建议。""",
        0.0,
    )


def prompt_risk_detection_medium(item):
    """识别部分风险但不完整——只要求找一半左右的风险，且只要风险名称和简要解释，不要求法律依据和修改建议"""
    contract = item.get("_contract_text", "")
    n_risks = len(item.get("risks", []))
    half = max(2, n_risks // 2)
    return (
        "你是一位律师。请审阅以下合同中的法律风险。",
        f"""请审阅以下合同，找出其中 {half} 个最明显的法律风险。

对每个风险请说明：
1. 风险名称
2. 涉及的条款位置
3. 风险原因（简要解释即可）

不需要引用法条依据，不需要给修改建议。

合同原文：
{contract[:4000]}""",
        0.3,
    )


def prompt_risk_detection_bad(item):
    """降质但有内容：以非专业视角看合同，能发现一些表面问题但深度不够"""
    contract = item.get("_contract_text", "")
    return (
        "你是一个普通人，没学过法律。",
        f"""朋友让你帮忙看看这份合同有没有什么不对劲的地方：

{contract[:3000]}

请说说你觉得哪些地方看起来不太合理或者对签合同的人不太公平，列出 2-3 个你注意到的地方。
不需要专业分析，不需要引用法条，就说说你的直觉感受。""",
        0.7,
    )


# --- risk_revision ---

def prompt_risk_revision_good(item):
    contract = item.get("_contract_text", "")
    question = item.get("question", "请对存在法律风险的条款提出具体修改方案。")
    fix_hints = ""
    for f in item.get("fixes", []):
        checklist = "；".join(c["point"] for c in f.get("fix_checklist", []))
        fix_hints += f"\n- 风险：{f['risk_name']}（{f.get('clause_location', '')}）\n"
        fix_hints += f"  原条款：{f.get('risky_clause', '')[:100]}...\n"
        fix_hints += f"  修订要点：{checklist}\n"
    return (
        "你是一位资深合同审查律师，擅长起草和修订合同条款。",
        f"""{question}

以下是合同原文：
{contract[:4000]}

以下是已识别的风险点及修订要点，请逐条给出修订后的条款全文：
{fix_hints}""",
        0.0,
    )


def prompt_risk_revision_medium(item):
    contract = item.get("_contract_text", "")
    risks_brief = "、".join(f["risk_name"] for f in item.get("fixes", [])[:3])
    return (
        "你是一位律师。",
        f"""以下合同存在一些风险（{risks_brief}），请只针对最关键的 2-3 个风险给出简要修改建议。

合同原文：
{contract[:4000]}""",
        0.3,
    )


def prompt_risk_revision_bad(item):
    """降质但有内容：给出一些泛泛的修改建议，但不针对具体风险条款"""
    contract = item.get("_contract_text", "")
    return (
        "你是一个普通人，没学过法律。",
        f"""朋友让你帮忙看看这份合同，提点修改意见：

{contract[:3000]}

请给出 2-3 条你觉得应该改的地方，用大白话说说怎么改比较好。
不需要写出修改后的条款全文，也不需要引用法条，就说说你的想法。""",
        0.7,
    )


# --- comprehensive_judgment_prediction ---

def prompt_judgment_good(item):
    """给出完整 instruction + 模块结构 + 每个模块的条目数和关键要求"""
    module_details = []
    for mod in item.get("rubrics", []):
        n_items = len(mod.get("items", []))
        # 提取关键评分条目的前几个
        key_items = []
        for it in mod.get("items", [])[:3]:
            key_items.append(it["criterion"][:50])
        hints = "；".join(key_items)
        module_details.append(f"  - 【{mod['module']}】（{mod['module_score']}分，{n_items}个评分点）要点：{hints}")
    module_text = "\n".join(module_details)
    return (
        item.get("instruction", "你是一名资深刑事法官。"),
        f"""{item['question']}

请严格按照以下模块结构逐一展开，每个模块都必须详细论述：
{module_text}

特别要求：
1. 【罪名认定】必须论证此罪与彼罪的区分，明确罪数判断
2. 【量刑情节分析】必须按"量刑基准→法定情节→酌定情节→综合调节"四步展开
3. 【刑期预测】必须明确刑种、具体刑期、是否适用缓刑及理由
4. 【附带民事与赔偿】必须说明罚金金额、退赔退赃、是否有民事赔偿
5. 【法条适用】必须列出定罪法条和量刑法条的完整编号""",
        0.0,
    )


def prompt_judgment_medium(item):
    """只展开罪名认定和刑期预测，故意跳过量刑情节分析细节、附带民事、法条适用"""
    return (
        "你是一名法律从业者。请根据以下案情给出判决预测。",
        f"""{item['question']}

请按以下结构回答：
1. 【罪名认定】：分析被告人构成什么罪名，简要说明此罪与彼罪的区分
2. 【刑期预测】：给出建议刑种和刑期区间，说明是否适用缓刑

只需要回答以上两个模块，不需要分析量刑情节（法定/酌定），不需要讨论罚金和赔偿金额，不需要列出法条编号。""",
        0.3,
    )


def prompt_judgment_bad(item):
    """降质但有内容：以非专业视角猜测判决，有一些内容但缺乏法律推理"""
    return (
        "",
        f"""{item['question'][:600]}

你不是法律专业人士，但请根据上面的案件描述，谈谈你觉得会怎么判。
写 200 字左右，说说你觉得被告人犯了什么事、大概会判多久。
不需要分析量刑情节，不需要引用法律条文，就说说你的判断。""",
        0.8,
    )


# ═══════════════════════════════════════════════════════════
#  任务 → Prompt 构建器映射
# ═══════════════════════════════════════════════════════════

TASK_PROMPTS = {
    "legal_qa.application.consultation_fact_inquiry": {
        "good": prompt_consultation_good,
        "medium": prompt_consultation_medium,
        "bad": prompt_consultation_bad,
    },
    "legal_qa.application.case_analysis": {
        "good": prompt_case_analysis_good,
        "medium": prompt_case_analysis_medium,
        "bad": prompt_case_analysis_bad,
    },
    "legal_qa.application.legal_document_generation": {
        "good": prompt_doc_gen_good,
        "medium": prompt_doc_gen_medium,
        "bad": prompt_doc_gen_bad,
    },
    "contract_review.risk_detection": {
        "good": prompt_risk_detection_good,
        "medium": prompt_risk_detection_medium,
        "bad": prompt_risk_detection_bad,
    },
    "contract_review.risk_revision": {
        "good": prompt_risk_revision_good,
        "medium": prompt_risk_revision_medium,
        "bad": prompt_risk_revision_bad,
    },
    "case_prediction.comprehensive_judgment_prediction": {
        "good": prompt_judgment_good,
        "medium": prompt_judgment_medium,
        "bad": prompt_judgment_bad,
    },
}


# ═══════════════════════════════════════════════════════════
#  主流程
# ═══════════════════════════════════════════════════════════

TASK_IDS_ORDERED = list(TASK_PROMPTS.keys())


def parse_api_config(config_str: str, fallback_url="", fallback_key="", fallback_model=""):
    """解析 'BASE_URL|API_KEY|MODEL' 格式，缺失部分用 fallback"""
    if not config_str or not config_str.strip():
        return fallback_url, fallback_key, fallback_model
    parts = config_str.strip().split("|")
    url = parts[0] if len(parts) > 0 and parts[0] else fallback_url
    key = parts[1] if len(parts) > 1 and parts[1] else fallback_key
    model = parts[2] if len(parts) > 2 and parts[2] else fallback_model
    return url, key, model


def generate_answers(client: OpenAIInference, task_id: str, grade: str,
                     data: list, prompt_fn) -> list:
    """对采样数据逐条调用 LLM 生成答案"""
    answers = []
    for i, item in enumerate(data):
        sys_prompt, user_prompt, temp = prompt_fn(item)
        old_temp = client.temperature
        client.temperature = temp
        try:
            answer = client.infer(instruction=sys_prompt, question=user_prompt)
        except Exception as e:
            answer = f"[ERROR] {e}"
        client.temperature = old_temp
        answers.append({"id": i, "answer": answer})
        print(f"    [{i+1}/{len(data)}] {grade} done ({len(answer)} chars)")
    return answers


def run_one_task(tid: str, client: OpenAIInference, test_mode: bool = False):
    """生成一个任务的 good/medium/bad 三档答案"""
    task = TASK_MAP.get(tid)
    if not task:
        print(f"[SKIP] {tid}: 任务未注册")
        return 0

    print(f"\n{'='*60}")
    print(f"[{tid}] {task.display_name}")

    data = load_task_data(tid, "standard")

    if test_mode:
        data = data[:1]
        print(f"  [TEST MODE] 只取 1 条测试")
    else:
        print(f"  共 {len(data)} 条")

    count = 0
    for grade in ["good", "medium", "bad"]:
        print(f"  --- {grade} ---")
        prompt_fn = TASK_PROMPTS[tid][grade]
        answers = generate_answers(client, tid, grade, data, prompt_fn)

        meta = build_meta(task, len(answers), grade)
        output = {"meta": meta, "answers": answers}
        fname = f"{tid}_{grade}.json"
        save_json(OUTPUT_DIR / fname, output)
        count += 1
        print(f"  -> {fname}")
    return count


def run_parallel(clients: dict, test_mode: bool = False):
    """用 ThreadPoolExecutor 并行跑 6 个任务"""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    futures = {}
    with ThreadPoolExecutor(max_workers=6) as pool:
        for tid, client in clients.items():
            f = pool.submit(run_one_task, tid, client, test_mode)
            futures[f] = tid

        total = 0
        for f in as_completed(futures):
            tid = futures[f]
            try:
                total += f.result()
            except Exception as e:
                print(f"[ERROR] {tid}: {e}")
    return total


def main():
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")

    parser = argparse.ArgumentParser(description="生成 6 个 Rubric 任务的三档测试答案")
    parser.add_argument("--base-url", default=os.getenv("INFERENCE_BASE_URL", ""),
                        help="默认 API base URL")
    parser.add_argument("--api-key", default=os.getenv("INFERENCE_API_KEY", ""),
                        help="默认 API key")
    parser.add_argument("--model", default=os.getenv("INFERENCE_MODEL", ""),
                        help="默认模型名称")
    parser.add_argument("--test", action="store_true",
                        help="测试模式：每个任务只跑 1 条样本")
    parser.add_argument("--tasks", nargs="*", default=None,
                        help="指定任务 ID（默认全部 6 个）")
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # 构建每个任务的 client
    task_ids = args.tasks or TASK_IDS_ORDERED
    clients = {}

    for i, tid in enumerate(task_ids):
        if tid not in TASK_PROMPTS:
            print(f"[SKIP] {tid}: 不在 6 个 Rubric 任务中")
            continue

        # 优先用 RUBRIC_API_{i+1}
        env_key = f"RUBRIC_API_{i+1}"
        env_val = os.getenv(env_key, "")
        url, key, model = parse_api_config(
            env_val, args.base_url, args.api_key, args.model
        )

        if not key:
            print(f"[SKIP] {tid}: 无 API Key（设置 {env_key} 或 --api-key）")
            continue

        clients[tid] = OpenAIInference(
            base_url=url, api_key=key, model=model, max_tokens=16384,
        )
        src = env_key if env_val else "default"
        print(f"  {tid} -> {model} ({src})")

    if not clients:
        print("\nERROR: 没有可用的 API Key。请在 .env 中设置 RUBRIC_API_1~6 或 INFERENCE_API_KEY。")
        sys.exit(1)

    start = time.time()

    if len(clients) > 1 and not args.test:
        print(f"\n并行生成 {len(clients)} 个任务...")
        total = run_parallel(clients, test_mode=args.test)
    else:
        total = 0
        for tid, client in clients.items():
            total += run_one_task(tid, client, test_mode=args.test)

    elapsed = round(time.time() - start, 1)
    print(f"\nDone. Generated {total} files in {OUTPUT_DIR} ({elapsed}s)")


if __name__ == "__main__":
    main()