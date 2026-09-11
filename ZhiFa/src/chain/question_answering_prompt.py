"""
法律问答相关提示词模板
"""
from langchain_core.prompts import PromptTemplate


# 法律相关性检查提示词 - 判断问题是否与法律相关
check_law_prompt_template = """你是一个专业律师，请判断下面问题是否和法律相关，相关请回答YES，不想关请回答NO，不允许其它回答，不允许在答案中添加编造成分。
问题: {question}
"""
CHECK_LAW_PROMPT = PromptTemplate(
    template=check_law_prompt_template, input_variables=["question"]
)


# 多查询生成提示词 - 生成问题的多个变体以提高检索召回率
multi_query_prompt_template = """您是 AI 语言模型助手。您的任务是生成给定用户问题的3个不同版本，以从矢量数据库中检索相关文档。通过对用户问题生成多个视角，您的目标是帮助用户克服基于距离的相似性搜索的一些限制。提供这些用换行符分隔的替代问题，不要给出多余的回答。问题：{question}"""  # noqa
MULTI_QUERY_PROMPT_TEMPLATE = PromptTemplate(
    template=multi_query_prompt_template, input_variables=["question"]
)


# 法律问答提示词 - 结合法律文档和网页内容回答问题（支持对话历史上下文记忆）
law_prompt_template = """你是一个专业的律师，请你结合以下内容回答问题。

【相关法律条文】
{law_context}

【网络参考资料】
{web_context}

{chat_history}

当前问题: {question}

回答要求:
1. 结合上述法律条文和参考资料给出专业、准确的回答
2. 如果用户的问题涉及到之前对话中的内容，请结合对话历史理解用户意图
3. 回答应当清晰、有条理，必要时可以分点说明
4. 如果涉及具体法律条款，请明确引用
"""
LAW_PROMPT = PromptTemplate(
    template=law_prompt_template, input_variables=["law_context", "web_context", "question", "chat_history"]
)


# 网页内容质量过滤和提炼的提示词模板
WEB_CONTEXT_REFINE_PROMPT = PromptTemplate(
    input_variables=["question", "web_snippets"],
    template=(
        "你是法律检索助手。下面是 DuckDuckGo 网页搜索返回的若干网页摘要（snippet），"
        "它们可能包含广告、低质量页面或与问题无关的内容。\n"
        "请你对这些摘要进行 AI 处理，完成以下任务：\n"
        "1) 过滤掉明显无关/低质量/营销内容；\n"
        "2) 仅基于摘要内容提炼与问题最相关的要点（不要杜撰，不要引入摘要中没有的信息）；\n"
        "3) 输出用中文、精炼、可直接用于回答的资料；\n"
        '4) 若没有足够信息，请明确写"网页摘要中未找到直接依据"。\n\n'
        "【用户问题】\n{question}\n\n"
        "【网页摘要（编号列表）】\n{web_snippets}\n\n"
        "【请输出：精炼后的网页要点】\n"
    ),
)
