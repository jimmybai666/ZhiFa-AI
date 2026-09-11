"""
generate_adversarial_trick_answers.py
构造表面欺骗对抗答案：篇幅注水、术语堆砌、伪造引用
测试评估方法是否会被"看起来专业但实质有误"的答案骗到高分。

用法:
    python scripts/generate_adversarial_trick_answers.py
"""

import sys, os, io, json, random
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from zhifa_eval.data_loader import load_task_data

OUTPUT_DIR = PROJECT_ROOT / "test_discrimination" / "adversarial_trick"
SEED = 42

LEGAL_JARGON_FILLER = (
    "根据我国法律体系的基本原则，结合相关司法解释和实务操作规范，"
    "在充分考虑法律适用的一般性原则与特殊性规定的前提下，"
    "依据民事诉讼法、刑事诉讼法及行政诉讼法等程序法的相关规定，"
    "参照最高人民法院关于审理相关案件的指导意见和典型案例裁判要旨，"
    "综合运用法律解释学中的文义解释、体系解释、目的解释和历史解释方法，"
    "在维护法律统一适用和司法公正的基本价值取向下，"
    "结合当事人的合法权益保护和社会公共利益维护的双重目标，"
    "遵循比例原则、诚实信用原则和公序良俗原则的基本要求，"
    "在法治国家、法治政府、法治社会一体建设的宏观背景下进行分析。"
)

LEGAL_BOILERPLATE = (
    "综上所述，根据法律规定和司法实践，本案应当依法作出公正裁判。"
    "在法治精神的指引下，严格遵循罪刑法定、罪责刑相适应等基本原则，"
    "切实保障当事人的合法权益，维护社会公平正义。"
    "人民法院在审理过程中应当充分听取各方当事人的意见，"
    "全面审查证据材料，准确认定案件事实，正确适用法律规定。"
)

HIGH_FREQ_LEGAL_CHARS = (
    "根据法律规定，当事人应当依法行使权利、履行义务。"
    "合同双方应遵循诚实信用原则，全面履行合同约定的各项条款。"
    "违反法律法规的强制性规定的行为无效。"
    "依据民法典相关规定，民事主体从事民事活动应当遵循自愿原则、公平原则。"
    "人民法院依法独立行使审判权，保障诉讼参与人的合法权益。"
    "国家保护公民的合法财产权利和人身权利不受侵犯。"
    "行政机关应当依法行政，保障行政相对人的合法权益。"
)


# ── 法条背诵 ─────────────────────────────────────────
def gen_statute_tricks(items, rng):
    results = {"trick_A": [], "trick_B": [], "trick_C": []}
    for idx, item in enumerate(items):
        sid = idx
        correct = item.get("answer", "")
        question = item.get("question", "")

        # trick_A: 正确法条 + 适度无关术语填充
        filler = LEGAL_JARGON_FILLER[:len(correct)]
        trick_a = correct + "\n" + filler

        # trick_B: 篡改关键数字/量词 + 少量术语包裹
        tampered = correct
        for old, new in [("三年", "八年"), ("五年", "十二年"), ("十年", "二十年"),
                         ("三十", "六十"), ("五十", "一百"), ("百分之", "千分之"),
                         ("三倍", "十倍"), ("30", "90"), ("50", "150"),
                         ("一年", "四年"), ("二年", "七年"), ("六个月", "三年")]:
            tampered = tampered.replace(old, new, 1)
        trick_b = tampered + "\n" + LEGAL_BOILERPLATE[:80]

        # trick_C: 完全编造 + 大量真实法律术语
        fake_article = (
            f"答案:根据相关法律规定，该条款明确规定了当事人在特定法律关系中的权利义务边界。"
            f"具体而言，该法律条文确立了以下基本原则：第一，权利行使应当遵循诚实信用原则；"
            f"第二，义务履行应当符合法律规定的方式和期限；"
            f"第三，违反上述规定的，应当承担相应的法律责任，包括但不限于民事赔偿责任、"
            f"行政处罚责任以及刑事责任。该条款的立法目的在于维护社会经济秩序的稳定，"
            f"保护当事人的合法权益，促进社会和谐发展。"
        )
        trick_c = fake_article

        results["trick_A"].append({"id": sid, "answer": trick_a})
        results["trick_B"].append({"id": sid, "answer": trick_b})
        results["trick_C"].append({"id": sid, "answer": trick_c})
    return results


# ── 阅读理解 ─────────────────────────────────────────
def gen_reading_tricks(items, rng):
    results = {"trick_A": [], "trick_B": [], "trick_C": []}
    for idx, item in enumerate(items):
        sid = idx
        correct = item.get("answer", "")
        question = item.get("question", "")

        # 从 question 中提取段落（段落:xxx 问题:xxx 格式）
        context = ""
        if "段落:" in question:
            parts = question.split("问题:")
            context = parts[0].replace("段落:", "").strip() if parts else question

        # trick_A: 正确答案 + 一小段无关法律分析（适度注水）
        filler = LEGAL_JARGON_FILLER[:len(correct)]
        trick_a = correct + "\n" + filler

        # trick_B: 从原文中随机摘取2-3个句子拼接（答非所问但高字符重叠）
        if context:
            sentences = [s.strip() for s in context.replace("。", "。\n").split("\n") if len(s.strip()) > 5]
            if len(sentences) > 2:
                picked = rng.sample(sentences, min(3, len(sentences)))
                trick_b = "回答:" + "".join(picked)
            else:
                trick_b = "回答:" + context[:150]
        else:
            trick_b = "回答:" + question[:150]

        # trick_C: 高频法律词汇万金油回答（适度长度）
        trick_c = "回答:" + HIGH_FREQ_LEGAL_CHARS

        results["trick_A"].append({"id": sid, "answer": trick_a})
        results["trick_B"].append({"id": sid, "answer": trick_b})
        results["trick_C"].append({"id": sid, "answer": trick_c})
    return results


# ── 案情分析（主观）─────────────────────────────────
def gen_case_analysis_tricks(items, rng):
    """案情分析需要 LLM 生成，这里只构造 prompt，实际生成在 run 脚本中完成"""
    results = {"trick_A": [], "trick_B": [], "trick_C": []}
    for idx, item in enumerate(items):
        sid = idx
        question = item.get("question", "")

        results["trick_A"].append({"id": sid, "question": question, "trick_type": "correct_conclusion_padded"})
        results["trick_B"].append({"id": sid, "question": question, "trick_type": "fake_citations"})
        results["trick_C"].append({"id": sid, "question": question, "trick_type": "professional_format_wrong"})
    return results


TRICK_PROMPTS = {
    "correct_conclusion_padded": (
        "你是一个法律AI助手。请对以下案情进行分析。\n"
        "要求：\n"
        "1. 给出正确的法律结论\n"
        "2. 但是在分析过程中，大量堆砌不相关的法律论述来充篇幅\n"
        "3. 引用大量不相关但真实存在的法条\n"
        "4. 分析部分要又长又空洞，用大量法律术语包装但不做实质性推理\n"
        "5. 字数至少1500字\n"
        "案情：{question}"
    ),
    "fake_citations": (
        "你是一个法律AI助手。请对以下案情进行分析。\n"
        "要求：\n"
        "1. 给出一个错误的法律结论（故意认定错误的罪名或错误的法律关系）\n"
        "2. 用大量伪造的法条编号来支撑你的错误结论（如《刑法》第999条、《民法典》第2000条等不存在的法条）\n"
        "3. 伪造判例引用（如'根据(2024)最高法刑终字第9999号判决'）\n"
        "4. 语气要非常自信和权威，格式要规范\n"
        "5. 字数至少1000字\n"
        "案情：{question}"
    ),
    "professional_format_wrong": (
        "你是一个法律AI助手。请对以下案情进行分析。\n"
        "要求：\n"
        "1. 给出一个错误的法律结论\n"
        "2. 使用非常专业的格式：一、二、三...分层编号，（一）（二）子项\n"
        "3. 每个分析模块都要有标题：【案情简述】【法律关系认定】【法律适用】【裁判建议】\n"
        "4. 内容要看起来很专业但实质上分析方向完全错误\n"
        "5. 字数至少1500字，格式越规范越好\n"
        "案情：{question}"
    ),
}


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    rng = random.Random(SEED)

    # 法条背诵
    print("生成法条背诵对抗答案...")
    data1 = load_task_data("legal_qa.memorization.statute_recitation", "standard")
    statute_tricks = gen_statute_tricks(data1, rng)

    for trick_name, answers in statute_tricks.items():
        out = {
            "meta": {"task_id": "legal_qa.memorization.statute_recitation", "trick": trick_name, "count": len(answers)},
            "answers": answers,
        }
        fpath = OUTPUT_DIR / f"statute_recitation_{trick_name}.json"
        with open(fpath, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        print(f"  {trick_name}: {len(answers)} answers -> {fpath.name}")

    # 阅读理解
    print("\n生成阅读理解对抗答案...")
    data2 = load_task_data("legal_qa.understanding.reading_comprehension", "standard")
    reading_tricks = gen_reading_tricks(data2, rng)

    for trick_name, answers in reading_tricks.items():
        out = {
            "meta": {"task_id": "legal_qa.understanding.reading_comprehension", "trick": trick_name, "count": len(answers)},
            "answers": answers,
        }
        fpath = OUTPUT_DIR / f"reading_comprehension_{trick_name}.json"
        with open(fpath, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        print(f"  {trick_name}: {len(answers)} answers -> {fpath.name}")

    # 案情分析（只保存 prompt 信息，实际 LLM 生成在 run 脚本中）
    print("\n准备案情分析对抗 prompt...")
    data3 = load_task_data("legal_qa.application.case_analysis", "standard")
    case_tricks = gen_case_analysis_tricks(data3, rng)

    for trick_name, items in case_tricks.items():
        out = {
            "meta": {"task_id": "legal_qa.application.case_analysis", "trick": trick_name, "count": len(items)},
            "prompt_template": TRICK_PROMPTS[items[0]["trick_type"]],
            "items": items,
        }
        fpath = OUTPUT_DIR / f"case_analysis_{trick_name}.json"
        with open(fpath, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        print(f"  {trick_name}: {len(items)} items -> {fpath.name}")

    # 同时保存 good 和 bad 基线答案引用（从 discrimination test 复用）
    print("\n保存 good/bad 基线索引...")
    baseline = {
        "statute_recitation": {"sampled_ids": [item.get("id", i) for i, item in enumerate(data1)]},
        "reading_comprehension": {"sampled_ids": [item.get("id", i) for i, item in enumerate(data2)]},
        "case_analysis": {"sampled_ids": [item.get("id", i) for i, item in enumerate(data3)]},
    }
    with open(OUTPUT_DIR / "_baseline_index.json", "w", encoding="utf-8") as f:
        json.dump(baseline, f, ensure_ascii=False, indent=2)

    print("\n完成！")


if __name__ == "__main__":
    main()
