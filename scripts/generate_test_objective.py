"""
generate_test_objective.py
为 ZhiFa-Eval 11 个客观子任务生成 good / medium / bad 三档测试答案（规则构造）。
"""

import sys, os, json, re, random, math
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
from zhifa_eval.data_loader import TASK_REGISTRY, TASK_MAP, load_task_data

OUTPUT_DIR = PROJECT_ROOT / "test_discrimination"
SEED_BASE = 42

# ─── 争议焦点类别池 ─────────────────────────────────────
ISSUE_CATEGORIES = [
    "婚姻家庭", "劳动纠纷", "交通事故", "债权债务", "刑事辩护",
    "合同纠纷", "房产纠纷", "侵权", "公司法", "医疗纠纷",
    "拆迁安置", "行政诉讼", "建设工程", "知识产权", "综合咨询",
    "人身损害", "涉外法律", "海事海商", "消费权益", "抵押担保",
]

# ─── 常见罪名池（用于 bad 答案） ────────────────────────
WRONG_CRIMES = [
    "盗窃", "抢劫", "故意杀人", "故意伤害", "诈骗", "贪污",
    "受贿", "走私", "放火", "绑架", "非法拘禁", "敲诈勒索",
]


# ───────────────────────────────────────────────────────────
# 工具函数
# ───────────────────────────────────────────────────────────

def make_rng(task_id: str, grade: str):
    """为每个 task+grade 创建独立 RNG"""
    grade_offset = {"good": 0, "medium": 1000, "bad": 2000}[grade]
    return random.Random(SEED_BASE + grade_offset + hash(task_id) % 10000)


def extract_option(answer_text: str) -> str:
    """从 '正确答案：D。' 或 '[正确答案]D<eoa>' 中提取选项字母"""
    m = re.search(r'[正确答案]?\s*[:：]?\s*([A-E])', answer_text)
    if m:
        return m.group(1)
    return "A"


def extract_category(answer_text: str) -> str:
    """从 '[类别]婚姻家庭<eoa>' 或纯类别文本中提取类别"""
    m = re.search(r'\[类别\](.+?)(?:<eoa>|$)', answer_text)
    if m:
        return m.group(1).strip()
    return answer_text.strip()


def extract_articles(answer_text: str) -> list:
    """从 '法条:刑法第348条' 或 '法条:刑法第128条、刑法第341条' 提取法条编号"""
    text = answer_text.replace("[法条]", "法条:").replace("<eoa>", "")
    nums = re.findall(r'第(\d+)条', text)
    return nums if nums else ["0"]


def extract_crimes(answer_text: str) -> list:
    """从 '罪名:盗窃;抢劫' 提取罪名列表"""
    text = answer_text.replace("[罪名]", "罪名:").replace("<eoa>", "")
    m = re.search(r'罪名[:：](.+)', text)
    if m:
        return [c.strip() for c in re.split(r'[;；、,，]', m.group(1)) if c.strip()]
    return [text.strip()]


def extract_months(answer_text: str) -> int:
    """从 '刑期:6个月' 或 '刑期:3年6个月' 提取总月数"""
    text = answer_text.replace("[刑期]", "刑期:").replace("<eoa>", "")
    years = 0
    months = 0
    ym = re.search(r'(\d+)\s*年', text)
    mm = re.search(r'(\d+)\s*(?:个)?月', text)
    if ym:
        years = int(ym.group(1))
    if mm:
        months = int(mm.group(1))
    total = years * 12 + months
    return max(total, 1)


def months_to_str(m: int) -> str:
    if m >= 12 and m % 12 == 0:
        return f"刑期:{m // 12}年"
    elif m >= 12:
        return f"刑期:{m // 12}年{m % 12}个月"
    else:
        return f"刑期:{max(1, m)}个月"


# ───────────────────────────────────────────────────────────
# 各指标类型的生成函数
# ───────────────────────────────────────────────────────────

def gen_em_rouge(items, grade, rng):
    """EM+Rouge-L 类 (factual_query): 好档80%原文/20%加前缀，中档45%原文/25%截半/30%乱答，差档15%原文/85%固定错答"""
    answers = []
    for item in items:
        ref = item["answer"]
        r = rng.random()
        if grade == "good":
            if r < 0.80:
                ans = ref
            else:
                ans = "根据法律规定，" + ref
        elif grade == "medium":
            if r < 0.45:
                ans = ref
            elif r < 0.70:
                # 截取前半
                prefix = ref[:len(ref) // 2]
                ans = prefix if prefix else ref
            else:
                ans = "答案:无法确定"
        else:  # bad
            if r < 0.15:
                ans = ref
            else:
                ans = rng.choice(["答案:不适用", "答案:以上都不是", "答案:无相关规定"])
        answers.append(ans)
    return answers


def gen_accuracy_abcd(items, grade, rng):
    """Accuracy-ABCD 类 (legal_knowledge_mcqa): 好档80%选对，中档45%选对，差档15%选对，其余随机选错"""
    options = list("ABCD")
    answers = []
    for item in items:
        correct = extract_option(item["answer"])
        r = rng.random()
        if grade == "good":
            picked = correct if r < 0.80 else rng.choice([o for o in options if o != correct])
        elif grade == "medium":
            picked = correct if r < 0.45 else rng.choice([o for o in options if o != correct])
        else:
            picked = correct if r < 0.15 else rng.choice([o for o in options if o != correct])
        answers.append(f"正确答案：{picked}。")
    return answers


def gen_accuracy_abcde(items, grade, rng):
    """Accuracy-ABCDE 类 (argument_understanding): 同ABCD逻辑，选项范围扩展到A-E"""
    options = list("ABCDE")
    answers = []
    for item in items:
        correct = extract_option(item["answer"])
        r = rng.random()
        if grade == "good":
            picked = correct if r < 0.80 else rng.choice([o for o in options if o != correct])
        elif grade == "medium":
            picked = correct if r < 0.45 else rng.choice([o for o in options if o != correct])
        else:
            picked = correct if r < 0.15 else rng.choice([o for o in options if o != correct])
        answers.append(f"[正确答案]{picked}<eoa>")
    return answers


def gen_accuracy_category(items, grade, rng):
    """Accuracy-Category 类 (issue_understanding): 好档80%正确类别，中档45%正确，差档15%正确，其余从预设类别池随机选错"""
    answers = []
    for item in items:
        correct = extract_category(item["answer"])
        r = rng.random()
        if grade == "good":
            picked = correct if r < 0.80 else rng.choice([c for c in ISSUE_CATEGORIES if c != correct])
        elif grade == "medium":
            picked = correct if r < 0.45 else rng.choice([c for c in ISSUE_CATEGORIES if c != correct])
        else:
            picked = correct if r < 0.15 else rng.choice([c for c in ISSUE_CATEGORIES if c != correct])
        answers.append(picked)
    return answers


def gen_rouge_l(items, grade, rng):
    """Rouge-L 类 (statute_recitation/case_summarization): 好档80%原文/20%截70%，中档50%截半/30%截30%/20%原文，差档15%原文/35%截20%/50%乱答"""
    answers = []
    for item in items:
        ref = item["answer"]
        r = rng.random()
        if grade == "good":
            if r < 0.80:
                ans = ref
            else:
                cut = int(len(ref) * 0.7)
                ans = ref[:cut] if cut > 0 else ref
        elif grade == "medium":
            if r < 0.50:
                cut = int(len(ref) * 0.5)
                ans = ref[:cut] if cut > 0 else ref
            elif r < 0.80:
                cut = int(len(ref) * 0.3)
                ans = ref[:cut] if cut > 0 else ref
            else:
                ans = ref
        else:  # bad
            if r < 0.15:
                ans = ref
            elif r < 0.50:
                cut = int(len(ref) * 0.2)
                ans = ref[:cut] if cut > 0 else ref[:5]
            else:
                ans = "该法条/案情的具体内容不详"
        answers.append(ans)
    return answers


def gen_rc_f1(items, grade, rng):
    """rc-F1 类 (reading_comprehension): 好档75%原文/25%加后缀，中档50%截60%/30%模糊回答/20%原文，差档15%原文/85%无法判断"""
    answers = []
    for item in items:
        ref = item["answer"]  # e.g. "回答:xxx"
        r = rng.random()
        if grade == "good":
            if r < 0.75:
                ans = ref
            else:
                ans = ref + "等相关内容"
        elif grade == "medium":
            if r < 0.50:
                # 截取 60%
                body = ref[3:] if ref.startswith("回答:") else ref
                cut = int(len(body) * 0.6)
                ans = "回答:" + body[:cut] if cut > 0 else ref
            elif r < 0.80:
                ans = "回答:根据材料中的相关描述可知"
            else:
                ans = ref
        else:
            if r < 0.15:
                ans = ref
            else:
                ans = "根据材料无法判断"
        answers.append(ans)
    return answers


def gen_f05(items, grade, rng):
    """F0.5 类 (clause_correction): 好档75%原文/25%微调标点，中档45%原文/30%截断/25%说无需修改，差档15%原文/40%无关回答/45%随机乱改"""
    answers = []
    for item in items:
        ref = item["answer"]
        r = rng.random()
        if grade == "good":
            if r < 0.75:
                ans = ref
            else:
                # 略微变更措辞
                ans = ref[:-1] + "。" if ref and ref[-1] == "。" else ref + "。"
        elif grade == "medium":
            if r < 0.45:
                ans = ref
            elif r < 0.75:
                cut = int(len(ref) * 0.6)
                ans = ref[:cut] if cut > 0 else ref
            else:
                ans = "该条款无需修改。"
        else:  # bad
            if r < 0.15:
                ans = ref
            elif r < 0.55:
                # 返回完全无关的内容
                ans = "该条款不存在法律风险，无需进行任何修改。"
            else:
                # 返回随机乱改的内容
                ans = rng.choice([
                    "本条款应删除。",
                    "双方另行协商。",
                    "以上条款作废。",
                    "此条款内容待定。",
                    "无效条款，建议重新拟定。",
                ])
        answers.append(ans)
    return answers


def gen_f1_articles(items, grade, rng):
    """F1 类-法条预测 (article_prediction): 好档80%全对/10%漏1条/10%多1条，中档40%全对/30%只答一半/30%全换随机法条号，差档15%全对/85%随机法条"""
    answers = []
    for item in items:
        ref_nums = extract_articles(item["answer"])
        r = rng.random()
        if grade == "good":
            if r < 0.80:
                nums = ref_nums
            elif r < 0.90:
                nums = ref_nums[:-1] if len(ref_nums) > 1 else ref_nums
            else:
                nums = ref_nums + [str(rng.randint(100, 450))]
        elif grade == "medium":
            if r < 0.40:
                nums = ref_nums
            elif r < 0.70:
                half = max(1, len(ref_nums) // 2)
                nums = rng.sample(ref_nums, half)
            else:
                nums = [str(rng.randint(100, 450)) for _ in ref_nums]
        else:  # bad
            if r < 0.15:
                nums = ref_nums
            else:
                nums = [str(rng.randint(100, 450)) for _ in range(rng.randint(1, 3))]
        articles = "、".join(f"刑法第{n}条" for n in nums)
        answers.append(f"法条:{articles}")
    return answers


def gen_f1_crimes(items, grade, rng):
    """F1 类-罪名预测 (clause_prediction): 好档80%全对/10%漏1个/10%多1个错罪名，中档40%全对/30%答一半/30%全换错，差档15%全对/85%随机错罪名"""
    answers = []
    for item in items:
        ref_crimes = extract_crimes(item["answer"])
        r = rng.random()
        if grade == "good":
            if r < 0.80:
                crimes = ref_crimes
            elif r < 0.90:
                crimes = ref_crimes[:-1] if len(ref_crimes) > 1 else ref_crimes
            else:
                extra = rng.choice([c for c in WRONG_CRIMES if c not in ref_crimes] or WRONG_CRIMES)
                crimes = ref_crimes + [extra]
        elif grade == "medium":
            if r < 0.40:
                crimes = ref_crimes
            elif r < 0.70:
                half = max(1, len(ref_crimes) // 2)
                crimes = rng.sample(ref_crimes, half)
            else:
                crimes = [rng.choice(WRONG_CRIMES) for _ in ref_crimes]
        else:
            if r < 0.15:
                crimes = ref_crimes
            else:
                crimes = [rng.choice(WRONG_CRIMES) for _ in range(rng.randint(1, 3))]
        answers.append("罪名:" + ";".join(crimes))
    return answers


def gen_nlog_distance(items, grade, rng):
    """nLog-distance 类 (prison_term_prediction): 好档80%精确/20%偏±1-3月，中档40%偏±1-3月/30%偏±12-24月/30%精确，差档15%精确/35%偏±12-24月/50%偏±36-60月"""
    answers = []
    for item in items:
        ref_months = extract_months(item["answer"])
        r = rng.random()
        if grade == "good":
            if r < 0.80:
                m = ref_months
            else:
                offset = rng.randint(1, 3) * rng.choice([-1, 1])
                m = max(1, ref_months + offset)
        elif grade == "medium":
            if r < 0.40:
                offset = rng.randint(1, 3) * rng.choice([-1, 1])
                m = max(1, ref_months + offset)
            elif r < 0.70:
                offset = rng.randint(12, 24) * rng.choice([-1, 1])
                m = max(1, ref_months + offset)
            else:
                m = ref_months
        else:  # bad
            if r < 0.15:
                m = ref_months
            elif r < 0.50:
                offset = rng.randint(12, 24) * rng.choice([-1, 1])
                m = max(1, ref_months + offset)
            else:
                offset = rng.randint(36, 60) * rng.choice([-1, 1])
                m = max(1, ref_months + offset)
        answers.append(months_to_str(m))
    return answers


# ───────────────────────────────────────────────────────────
# 指标 → 生成函数 映射
# ───────────────────────────────────────────────────────────

METRIC_GENERATORS = {
    "EM+Rouge-L": gen_em_rouge,
    "Accuracy-ABCD": gen_accuracy_abcd,
    "Accuracy-ABCDE": gen_accuracy_abcde,
    "Accuracy-Category": gen_accuracy_category,
    "Rouge-L": gen_rouge_l,
    "rc-F1": gen_rc_f1,
    "F0.5": gen_f05,
    "nLog-distance": gen_nlog_distance,
}

# F1 需按 task_id 区分
F1_GENERATORS = {
    "case_prediction.article_prediction": gen_f1_articles,
    "case_prediction.clause_prediction": gen_f1_crimes,
}


def get_generator(task):
    metric = task.metrics[0]
    if metric == "F1":
        return F1_GENERATORS[task.task_id]
    return METRIC_GENERATORS[metric]


# ───────────────────────────────────────────────────────────
# 主逻辑
# ───────────────────────────────────────────────────────────

def build_meta(task, count):
    return {
        "task_id": task.task_id,
        "display_name": task.display_name,
        "difficulty": "standard",
        "seed": SEED_BASE,
        "count": count,
    }


def save_json(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    grades = ["good", "medium", "bad"]
    file_count = 0

    for task in TASK_REGISTRY:
        tid = task.task_id

        # 跳过主观任务
        if task.eval_method != "objective":
            continue

        try:
            data = load_task_data(tid, "standard")
        except Exception as e:
            print(f"[SKIP] {tid}: {e}")
            continue

        sampled = data
        gen_func = get_generator(task)

        for grade in grades:
            rng = make_rng(tid, grade)
            ans_texts = gen_func(sampled, grade, rng)
            answers = [{"id": i, "answer": a} for i, a in enumerate(ans_texts)]
            meta = build_meta(task, len(answers))
            out = {"meta": meta, "answers": answers}
            fname = f"{tid}_{grade}.json"
            save_json(OUTPUT_DIR / fname, out)
            file_count += 1

        print(f"[objective] {tid}  ({len(sampled)} samples x 3 grades)")

    print(f"\nDone. Generated {file_count} files in {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
