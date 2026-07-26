"""
合同审查相关提示词模板
"""
from langchain_core.prompts import PromptTemplate


# 用于结构化拆解合同的 Prompt
contract_structure_template = """
你是一名专业律师，擅长将法律合同内容进行结构化和分类。
请阅读以下合同文本，首先理解其框架结构（章节、条款、款项），然后将其拆解为最小的独立审查单元。

**核心原则：**
1. **不要将纯标题作为独立的审查单元**。如果某一行只是章节标题（如"第四条 费用及结算方式"），请将其作为后续条款的 `section`（层级路径）的一部分，而不要将其作为 `content` 单独输出。
2. **处理多级标题**。对于嵌套结构（如"第四条"下包含"1. 服务费用"），应将"1. 服务费用"作为独立的审查单元，其 `section` 应包含"第四条 费用及结算方式"。
3. **完整性**。必须包含合同的全部实质性内容，包括首部和尾部。

请以 JSON 列表格式输出拆解结果。每个元素包含以下字段：
- "id": 编号（如 "0.0", "4.1", "4.2"）
- "type": 类型（"首部"、"条款"、"款项" 或 "尾部"）
- "theme": 主题（如 "服务费用", "支付方式"，需精准概括）
- "section": 所属章节/层级路径（如 "合同首部", "第四条 费用及结算方式"）。**注意：**这里应包含上级标题的完整文本。
- "content": 该单元的完整原文内容。**注意：**只包含实质性条款内容，不要包含已经放入 `section` 的上级标题。

JSON 格式示例：
[
  {{
    "id": "4.1",
    "type": "条款",
    "theme": "服务费用",
    "section": "第四条 费用及结算方式",
    "content": "1. 服务费用：服务费用为___，分为固定费用和考核费用两部分..."
  }},
  {{
    "id": "4.2",
    "type": "条款",
    "theme": "支付方式",
    "section": "第四条 费用及结算方式",
    "content": "2. 支付方式：固定费用每月___日前支付..."
  }}
]

注意：
1. 必须返回合法的 JSON 格式，不要包含 Markdown 代码块标记（如 ```json ... ```）。
2. 如果合同过长，请确保拆解的完整性。

合同内容：
{contract_text}
"""
CONTRACT_STRUCTURE_PROMPT = PromptTemplate(
    template=contract_structure_template, input_variables=["contract_text"]
)


# 合同条款分析提示词 - 用于分析各合同条款的风险
contract_clause_analysis_template = """你是一名经验丰富的法律顾问。请根据提供的相关法律条文，对以下合同条款进行严格的法律风险审查。

【相关法律条文】
{law_context}

【待审查条款】
{clause}

请分析该条款是否存在法律风险，并严格按照以下 JSON 格式输出分析结果（不要包含 Markdown 代码块标记）：

{{
    "risk_level": "高风险" | "中风险" | "低风险" | "无风险",
    "issue_description": "简要说明存在的问题（如条款模糊、违反法律强制性规定、权责不对等）",
    "legal_basis": "指出违反或依据的具体法律条文名称",
    "suggestion": "给出具体的修改建议说明",
    "revised_text": "在此处提供修改后的条款全文。如果无需修改，请原样返回原条款。"
}}

注意：
1. 必须返回合法的 JSON 格式。
2. `revised_text` 字段必须包含完整的条款内容，用于生成红线修订对比。
3. `revised_text` 中**绝对不要**包含【章节：...】【主题：...】等元数据标签，只返回纯净的合同文本。
4. **特殊规则**：如果待审查内容是"合同首部"（标题、当事人）或"合同尾部"（签字区）：
   - **禁止**在 `revised_text` 中添加正文条款（如工作时间、报酬、违约金等），这些内容应由用户在正文中补充。
   - 仅修正格式或主体信息的错误。
   - 如果缺少核心条款，请在 `suggestion` 中指出，不要直接补写在首尾部。
   - 对于签字区的日期、签名栏，尽量保持原样，除非有明显的法律效力问题（如缺少盖章位）。
"""
CONTRACT_CLAUSE_ANALYSIS_PROMPT = PromptTemplate(
    template=contract_clause_analysis_template, input_variables=["law_context", "clause"]
)


# 合同总结报告提示词
contract_summary_template = """
你是一名高级法律合伙人。请根据以下对合同各条款的详细审查结果，生成一份整体的合同审查报告。

【各条款审查结果】
{clauses_analysis}

请生成一份包含以下内容的审查报告：
1. **总体评价**：对合同整体风险的定性评价（如"风险可控"、"存在重大风险"）。
2. **主要风险点**：汇总高风险和中风险的条款，列出最关键的3-5个法律风险。
3. **修改建议汇总**：针对主要风险点，提供综合性的修改或谈判策略建议。
4. **结论**：是否建议签署，或签署的前提条件。

请保持专业、客观、简洁。

"""
CONTRACT_SUMMARY_PROMPT = PromptTemplate(
    template=contract_summary_template, input_variables=["clauses_analysis"]
)
