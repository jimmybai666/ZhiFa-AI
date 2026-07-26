"""
案情预测相关提示词模板

包含：
- 刑期预测提示词
- 罪名预测提示词
- 案件综合分析提示词
"""
from langchain_core.prompts import PromptTemplate

# ==================== 刑期预测提示词 ====================

imprisonment_prediction_template = """你是专业的刑事法官。请基于「刑法条文 + 案例库相似案件」进行链式分析并预测新案例的刑期，输出中需显式说明参考了哪些相似案件信息。

【待预测案例】
{query_fact}

【相关刑法条文】
{law_context}

【参考案例统计】
- 共{num_cases}个相似案例（来自案例库检索）
- 刑期范围：{min_imprisonment}-{max_imprisonment}个月
- 平均刑期：{avg_imprisonment:.0f}个月

【最相似的参考案例】
{similar_cases_text}

【预测要求】
1. 先列出刑法条文的量刑幅度与要点
2. 识别新案例的量刑情节（自首、坦白、赔偿、谅解、累犯等）
3. 对比案例库中相似案件的刑期与情节，说明与本案的异同（引用上方统计与列表）
4. 综合刑法规定、情节、案例库证据链给出预测，并写出清晰逻辑路径

【输出格式】（严格遵守）
罪名：[罪名]
法定刑：[根据刑法条文]
从轻情节：[如：自首、赔偿、取得谅解]（无则写"无"）
从重情节：[如：累犯、主犯]（无则写"无"）
参考刑期范围：{min_imprisonment}-{max_imprisonment}个月
参考案例分析：[用1-3句说明相似案件的量刑区间、情节异同及其对本案的影响]
预测刑期：__个月
理由：[按"法条 → 情节 → 案例库对比 → 结论"的逻辑说明]

请立即输出预测结果。
"""

IMPRISONMENT_PREDICTION_PROMPT = PromptTemplate(
    template=imprisonment_prediction_template,
    input_variables=[
        "query_fact", "law_context", "num_cases",
        "min_imprisonment", "max_imprisonment", "avg_imprisonment",
        "similar_cases_text"
    ]
)


# ==================== 罪名预测提示词 ====================

accusation_prediction_template = """你是专业的刑事法官。请根据案情描述、相关法律条文，并结合案例库中相似案件的罪名分布进行链式分析，输出时需提到已参考案例库数据。

【待分析案情】
{query_fact}

【相关刑法条文】
{law_context}

【参考案例】（来自案例库的相似案件罪名统计）
{accusation_stats}

【分析要求】
1. 解析案情的主要行为与构成要件
2. 结合相关刑法条文的罪名定义
3. 对比案例库相似案件的罪名分布，说明与本案的异同与启示
4. 按"法条 → 案情要件 → 案例库对比 → 结论"给出最可能的罪名及理由

【输出格式】
主要罪名：[罪名]
构成要件分析：[简要分析]
法律依据：[相关法条]
案例库参考说明：[说明案例库罪名分布如何支持/修正判断]
置信度：[高/中/低]
理由：[综合分析说明]
"""

ACCUSATION_PREDICTION_PROMPT = PromptTemplate(
    template=accusation_prediction_template,
    input_variables=["query_fact", "law_context", "accusation_stats"]
)


# ==================== 案例分析提示词 ====================

case_analysis_template = """你是专业的刑事律师。请对以下刑事案件进行全面分析，需显式引用案例库中检索到的相似案件，并说明这些案例如何支撑结论。

【案情描述】
{query_fact}

【相关刑法条文】
{law_context}

【相似判例参考】（来自案例库检索）
{similar_cases_text}

【分析要求】
请从以下几个方面进行分析，并保持"法律条文 → 案情要件 → 案例库对比 → 结论/建议"的逻辑链条：

1. **案情概述**：简要概括案件基本事实
2. **罪名分析**：可能构成的罪名及理由，并说明案例库中类似案件的罪名分布对判断的影响
3. **量刑情节**：
   - 从轻/减轻情节（如自首、坦白、赔偿、谅解等）
   - 从重/加重情节（如累犯、主犯等）
4. **刑期预测**：结合案例库相似案件的刑期区间与情节差异，给出逻辑清晰的预测
5. **辩护建议**：可能的辩护策略，并注明哪些建议是基于案例库对比得出的

请给出专业、客观的分析意见。
"""

CASE_ANALYSIS_PROMPT = PromptTemplate(
    template=case_analysis_template,
    input_variables=["query_fact", "law_context", "similar_cases_text"]
)
