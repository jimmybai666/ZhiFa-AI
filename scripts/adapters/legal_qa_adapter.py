"""
法律问答适配器 — 10 个 legal_qa 子任务

智法AI接口：BatchLegalQA._infer_single({"question": str}) → {"answer": str, ...}

输入：把 LegalEval 的 instruction + question 拼成一个 question 传入
输出：智法AI会输出长篇分析性回答（因为其 prompt 要求"结合法条和参考资料专业回答"）

注意：智法AI的 LAW_PROMPT 会在 question 前面加上检索到的法条和网页参考资料，
所以实际 LLM 看到的是 "你是专业律师...法条...网页...当前问题:{question}"。
对于客观题，我们把 instruction 里的格式要求也传进去，让智法AI尽量按格式输出，
但它可能还是会加很多分析文字。客观题评分器已经有模糊提取能力，能从长文本中找答案。
"""

import re
from typing import Any, Dict


LEGAL_QA_TASKS = {
    "legal_qa.memorization.factual_query",
    "legal_qa.memorization.legal_knowledge_mcqa",
    "legal_qa.memorization.statute_recitation",
    "legal_qa.understanding.reading_comprehension",
    "legal_qa.understanding.argument_understanding",
    "legal_qa.understanding.issue_understanding",
    "legal_qa.understanding.case_summarization",
    "legal_qa.application.consultation_fact_inquiry",
    "legal_qa.application.case_analysis",
    "legal_qa.application.legal_document_generation",
}

# 需要特殊输出格式的客观题（instruction 里有格式要求）
FORMAT_TASKS = {
    "legal_qa.memorization.legal_knowledge_mcqa",     # [正确答案]X<eoa>
    "legal_qa.understanding.argument_understanding",   # [正确答案]X<eoa>
    "legal_qa.understanding.issue_understanding",      # [类别]XXX<eoa>
}


class LegalQAAdapter:
    """法律问答适配器"""

    def get_zhifa_module(self) -> str:
        return "legal_qa"

    def to_zhifa_input(self, task_id: str, item: Dict[str, Any]) -> Dict[str, Any]:
        """拼接 instruction + question 作为智法AI的输入

        智法AI的 QA chain 会用 {question} 做 RAG 检索 + 生成回答。
        instruction 里的格式要求（如"将答案写在[正确答案]和<eoa>之间"）
        会被智法AI的 LLM 看到，但不保证严格遵守。
        """
        if task_id == "legal_qa.application.consultation_fact_inquiry":
            task_instruction = item.get("question", "")
            conversation = item.get("conversation", "")
            combined = f"{task_instruction}\n\n当事人陈述：\n{conversation}"

        elif task_id == "legal_qa.application.legal_document_generation":
            doc_type = item.get("doc_type", "法律文书")
            question = item.get("question", "")
            combined = f"请根据以下当事人陈述，起草一份{doc_type}。\n\n{question}"

        else:
            instruction = item.get("instruction", "")
            question = item.get("question", "")
            if instruction:
                combined = f"{instruction}\n\n{question}"
            else:
                combined = question

        return {"question": combined, "history": []}

    def from_zhifa_output(self, task_id: str, zhifa_result: Dict[str, Any],
                          item: Dict[str, Any]) -> str:
        """从智法AI回答中提取答案

        对于客观题：智法AI可能输出长篇分析+结论，尝试提取格式化答案
        对于主观题（Rubric评分）：直接用原始回答
        """
        answer = zhifa_result.get("answer", "")

        if task_id == "legal_qa.memorization.factual_query":
            return self._extract_factual_answer(answer)

        elif task_id == "legal_qa.memorization.legal_knowledge_mcqa":
            return self._extract_mcqa_answer(answer, "ABCD")

        elif task_id == "legal_qa.memorization.statute_recitation":
            return self._extract_statute_answer(answer)

        elif task_id == "legal_qa.understanding.argument_understanding":
            return self._extract_argument_answer(answer)

        elif task_id == "legal_qa.understanding.issue_understanding":
            return self._extract_category_answer(answer, item)

        elif task_id == "legal_qa.understanding.case_summarization":
            return self._extract_summarization_answer(answer)

        # 其他任务直接返回原始回答
        return answer

    def _extract_factual_answer(self, answer: str) -> str:
        """去掉智法AI回答中的法律名+条号前缀

        典型输出：
          '《中华人民共和国证券法》第二百零一条：处以十万元以上一百万元以下的罚款。'
          '《刑法》第六十五条：不满十八周岁'
        提取冒号后面的核心内容。
        """
        # 匹配 《...》第X条[第X款]：内容
        m = re.match(r'《[^》]+》[^：:]*[：:]\s*', answer)
        if m:
            return answer[m.end():].strip().rstrip('。')
        return answer

    def _extract_statute_answer(self, answer: str) -> str:
        """从智法AI回答中提取法条背诵的核心内容

        只去掉开头的法律名+条号前缀，保留法条正文。
        """
        answer = answer.strip()
        # 1) 开头 《法律名》第X条[第X款][第X项]：→ 只留后面
        m = re.match(r'《[^》]+》[^：:]*[：:]\s*', answer)
        if m:
            return answer[m.end():].strip()

        # 2) 开头 "第X条：内容"
        m = re.match(r'第[^：:，,。\n]+[：:]\s*', answer)
        if m:
            return answer[m.end():].strip()

        return answer


    def _extract_argument_answer(self, answer: str) -> str:
        """argument_understanding 单选题，提取最后出现的 A-E 字母"""
        m = re.search(r'\[正确答案\]\s*([A-E])', answer)
        if m:
            return f"正确答案：{m.group(1)}"
        found = re.findall(r'(?<![a-zA-Z])([A-E])(?![a-zA-Z])', answer)
        if found:
            return f"[正确答案]{found[-1]}<eoa>"
        return answer

    def _extract_mcqa_answer(self, answer: str, options: str) -> str:
        """从智法AI长文本回答中提取选择题答案（支持单选+多选）

        智法AI可能输出：
          单选："根据合同法...因此答案是B..."
          多选："正确答案：BC。"  "应当选ABD"
        需要提取出选项字母，格式化为 "[正确答案]B<eoa>" 或 "[正确答案]BC<eoa>"
        """
        # 已经是目标格式（单选或多选）
        m = re.search(r'\[正确答案\]\s*([A-E]+)', answer)
        if m:
            return f"正确答案：{m.group(1)}"

        # 常见模式提取（捕获连续多个选项字母）
        patterns = [
            r'正确答案[是为：:]\s*([A-E]+)',
            r'答案[是为：:]\s*([A-E]+)',
            r'应[该当]选\s*([A-E]+)',
            r'(?:故|因此|综上|所以)\s*[，,]?\s*(?:选择?|答案[是为]?)\s*([A-E]+)',
            r'选择?\s*([A-E])\s*[选项]',
        ]
        for p in patterns:
            m = re.search(p, answer)
            if m:
                letters = sorted(set(c for c in m.group(1) if c in options))
                if letters:
                    return f"[正确答案]{''.join(letters)}<eoa>"

        # 最后 fallback：收集所有独立出现的选项字母
        found = re.findall(rf'(?<![a-zA-Z])([{options}])(?![a-zA-Z])', answer)
        if found:
            # 多个不同字母 → 多选；只有一个 → 单选
            letters = sorted(set(found))
            return f"[正确答案]{''.join(letters)}<eoa>"

        # 实在提取不出来，返回原始回答让评分器尝试
        return answer


    def _extract_category_answer(self, answer: str, item: Dict[str, Any] = None) -> str:
        """从智法AI回答中提取类别答案（支持两种子任务）

        区分子任务：
        - disputed_issues: instruction 含"争议焦点" 或 question 以"句子:"开头
        - legal_consultation: 其余情况
        """
        item = item or {}
        instruction = item.get("instruction", "")
        question = item.get("question", "")
        is_dispute = ("争议焦点" in instruction
                      or question.lstrip().startswith("句子:")
                      or question.lstrip().startswith("句子："))

        DISPUTE_CATEGORIES = [
            "诉讼主体", "租金情况", "利息", "本金争议", "责任认定",
            "责任划分", "损失认定及处理", "原审判决是否适当", "合同效力",
            "财产分割", "责任承担", "鉴定结论采信问题", "诉讼时效",
            "违约", "合同解除", "肇事逃逸",
        ]

        CONSULTATION_CATEGORIES = [
            "婚姻家庭", "劳动纠纷", "交通事故", "债权债务", "刑事辩护",
            "合同纠纷", "房产纠纷", "侵权", "公司法", "医疗纠纷",
            "拆迁安置", "行政诉讼", "建设工程", "知识产权", "综合咨询",
            "人身损害", "涉外法律", "海事海商", "消费权益", "抵押担保",
        ]

        if is_dispute:
            m = re.search(r'\[争议焦点\](.+?)(?:<eoa>|$)', answer)
            if m:
                return m.group(1).strip()
            for cat in DISPUTE_CATEGORIES:
                if cat in answer:
                    return cat
            m = re.search(r'\[类别\](.+?)(?:<eoa>|$)', answer)
            if m:
                return m.group(1).strip()
            return answer

        m = re.search(r'\[类别\](.+?)(?:<eoa>|$)', answer)
        if m:
            return m.group(1).strip()
        for cat in CONSULTATION_CATEGORIES:
            if cat in answer:
                return cat
        return answer

    def _extract_summarization_answer(self, answer: str) -> str:
        """从智法AI回答中提取案情摘要，砍掉法律分析前缀和尾部分析"""
        text = answer.strip()

        # 1) 砍掉 "作为专业律师，结合...如下：" 前缀
        m = re.search(r'^作为专业律师[^：:]*[：:]\s*', text)
        if m:
            text = text[m.end():].strip()

        # 2) 砍掉 "根据您提供的...条文，...如下：" 前缀
        m = re.search(r'^根据您提供的[^：:]*[：:]\s*', text)
        if m:
            text = text[m.end():].strip()

        # 3) 砍掉 "结合...法律条文...分析如下：" 前缀
        m = re.search(r'^结合[^：:]*[：:]\s*', text)
        if m:
            text = text[m.end():].strip()

        # 4) 提取 **一句话摘要**：XXX 或 **报道摘要（一句话）：**XXX
        m = re.search(r'\*{0,2}(?:一句话摘要|报道摘要[^*]*)\*{0,2}\s*[：:]\s*\*{0,2}\s*', text)
        if m:
            text = text[m.end():].strip()

        # 5) 砍掉尾部的 "**律师专业分析..." / "**专业律师分析..." / "### 一、..." 及之后内容
        for sep in [r'\*{2}律师专业分析', r'\*{2}专业律师分析',
                    r'\*{2}结合法律条文的专业分析',
                    r'\n\s*#{1,4}\s', r'\n\s*\d+\.\s*\*{2}']:
            m = re.search(sep, text)
            if m:
                text = text[:m.start()].strip()
                break

        # 6) 去掉尾部 markdown 格式残留
        text = re.sub(r'\*{2,}$', '', text).strip()
        text = re.sub(r'^[\*\-]{2,}\s*', '', text).strip()

        return text if text else answer
