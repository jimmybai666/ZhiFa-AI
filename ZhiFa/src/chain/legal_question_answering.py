"""
legal_question_answering.py - 法律问答功能模块

本模块提供基于 RAG (检索增强生成) 的法律问答服务，结合向量数据库检索和网页搜索。

主要组件：
-----------
1. LawQAChain: 
   自定义的同步问答链，继承自 LangChain 的 BaseRetrievalQA
   支持多源检索（向量数据库 + 网页搜索）

2. get_law_chain: 
   创建法律问答主链的工厂函数
   实现完整的 RAG 流程：检索 -> 上下文构建 -> 答案生成

3. 辅助函数：
   - _build_web_snippets: 构建格式化的网页摘要（通用工具函数）
   - get_law_chain 内部闭包：使用模型实例的优化版本
     * build_web_snippets: 网页摘要构建（配置绑定）
     * refine_web_context: AI内容提炼（使用固定模型实例）
     * generate_answer: 答案生成（使用固定模型实例）

特性：
------
- 并行检索：同时从向量库和网页检索相关内容
- 智能过滤：使用 AI 过滤低质量网页内容
- 可配置：支持通过 config 对象自定义检索参数
- 热更新支持：配置变化时自动重新创建 chain
- 性能优化：chain 创建时固定模型实例，避免重复创建
- 向后兼容：保留 LawQAChain.from_llm 方法用于旧版本兼容

"""

import warnings
from typing import Any, Optional, List, Dict, Union
from operator import itemgetter

from langchain_classic.chains.retrieval_qa.base import BaseRetrievalQA
from langchain_core.language_models import BaseLanguageModel
from langchain_core.prompts import PromptTemplate
from langchain_core.callbacks import Callbacks
from langchain_classic.chains.question_answering.stuff_prompt import PROMPT_SELECTOR
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from pydantic import Field
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnableMap, RunnableLambda
from langchain_classic.chains.base import Chain
from langchain_community.utilities import DuckDuckGoSearchAPIWrapper
from langchain_core.callbacks import CallbackManagerForChainRun

from ..vectorstore.utils import get_vectorstore
from ..core.model_factory import get_model
from .law_document_chain import LawStuffDocumentsChain
from .question_answering_prompt import LAW_PROMPT, WEB_CONTEXT_REFINE_PROMPT
from .law_web_retriver import LawWebRetriever, get_multi_query_law_retriever, build_web_snippets
from .document_formatter import (
    combine_law_docs,
    combine_web_docs,
    format_law_docs_with_source,
    format_web_docs_with_url
)


# ==================== 常量定义 ====================

# 默认配置值
DEFAULT_WEB_SEARCH_FETCH_K = 50
DEFAULT_WEB_SEARCH_REGION = "cn-zh"
DEFAULT_WEB_SEARCH_SAFESEARCH = "strict"
DEFAULT_WEB_SEARCH_TIME = "y"

# 对话历史截断配置
MAX_HISTORY_TURNS = 10           # 最多保留最近 10 轮对话
MAX_HISTORY_TOTAL_CHARS = 5000  # 对话历史总字符预算
MAX_SINGLE_MSG_CHARS = 500      # 单条消息最大字符数

# 短问题阈值：低于此长度跳过 multi-query，直接单次检索
SHORT_QUESTION_THRESHOLD = 10

# ==================== 核心类定义 ====================

class LawQAChain(BaseRetrievalQA):
    """
    自定义的同步法律问答链，继承自 LangChain 的 BaseRetrievalQA。
    
    该类实现了多源检索的问答功能，能够同时从向量数据库（法律条文）
    和网页搜索引擎获取相关信息，为用户提供更全面的法律咨询服务。
    
    特性：
    -----
    1. 多源检索：同时支持向量库检索和网页搜索
    2. 并行处理：两个检索器可以并行工作，提高响应速度
    3. 灵活配置：支持独立配置两个检索器的参数
    4. 向后兼容：保留 from_llm 工厂方法用于旧版本兼容
    
    Attributes:
    -----------
    vs_retriever : BaseRetriever
        向量库检索器，用于检索法律条文数据库
    web_retriever : BaseRetriever
        网页检索器，用于检索实时网页信息
    
    Examples:
    ---------
    >>> chain = LawQAChain.from_llm(
    ...     llm=model,
    ...     vs_retriever=vector_retriever,
    ...     web_retriever=web_retriever
    ... )
    >>> result = chain.invoke({"query": "什么是合同法？"})
    
    Note:
    -----
    推荐使用 get_law_chain() 函数代替 from_llm() 方法，
    前者提供了更完整的 RAG 流程实现和更好的配置管理。
    """

    # 字段定义：两个检索器
    vs_retriever: BaseRetriever = Field(
        exclude=True,
        description="向量库检索器，用于检索法律条文数据库"
    )
    web_retriever: BaseRetriever = Field(
        exclude=True,
        description="网页检索器，用于检索实时网页信息"
    )

    def _get_docs(
        self,
        question: str,
        *,
        run_manager: CallbackManagerForChainRun,
    ) -> List[Document]:
        """
        同步检索两个数据源并合并返回。
        
        该方法是多源检索的核心实现，它会：
        1. 从向量数据库检索相关的法律条文
        2. 从网页搜索引擎检索相关的实时信息
        3. 将两个来源的结果合并返回
        
        Args:
            question: 用户的问题字符串
            run_manager: LangChain 回调管理器，用于追踪执行过程
        
        Returns:
            合并后的文档列表，格式为 [向量库结果] + [网页检索结果]
            
        Note:
            两个检索器按顺序执行（非并行），确保结果的稳定性。
            如果需要并行检索，可以使用 get_law_chain() 中的 RunnableMap。
        """
        # 1. 向量库检索：从法律条文数据库检索
        vs_docs = self.vs_retriever.get_relevant_documents(
            question, 
            callbacks=run_manager.get_child()
        )

        # 2. 网页检索：从搜索引擎获取实时信息
        web_docs = self.web_retriever.get_relevant_documents(
            question, 
            callbacks=run_manager.get_child()
        )

        # 3. 返回合并结果（向量库结果在前，网页结果在后）
        return vs_docs + web_docs

    @property
    def _chain_type(self) -> str:
        """返回链的类型标识符"""
        return "law_qa"

    @classmethod
    def from_llm(
        cls,
        llm: BaseLanguageModel,
        prompt: Optional[PromptTemplate] = None,
        callbacks: Callbacks = None,
        **kwargs: Any,
    ) -> BaseRetrievalQA:
        """
        从 LLM 创建 LawQAChain 实例的工厂方法。
        
        注意：此方法保留用于向后兼容，但不推荐在新代码中使用。
        推荐使用 get_law_chain() 函数，它提供了更完整的 RAG 流程实现。
        
        Args:
            llm: 语言模型实例
            prompt: 可选的提示词模板，如果不提供则使用默认模板
            callbacks: 可选的回调管理器
            **kwargs: 其他参数，包括 vs_retriever 和 web_retriever
        
        Returns:
            配置好的 LawQAChain 实例
        
        Raises:
            ValueError: 如果缺少必需的 retriever 参数
        
        Example:
            >>> from langchain_community.llms import OpenAI
            >>> llm = OpenAI()
            >>> chain = LawQAChain.from_llm(
            ...     llm=llm,
            ...     vs_retriever=my_vector_retriever,
            ...     web_retriever=my_web_retriever
            ... )
        
        Warning:
            此方法内部仍使用已弃用的 LLMChain，会产生弃用警告。
            这些警告已被过滤，但建议在未来迁移到新的 Runnable 接口。
        """
        # 选择提示词模板
        _prompt = prompt or PROMPT_SELECTOR.get_prompt(llm)

        # 由于 StuffDocumentsChain 依赖 LLMChain，这里仍使用旧接口
        # 过滤弃用警告以避免干扰用户
        warnings.filterwarnings(
            'ignore', 
            category=DeprecationWarning, 
            module='langchain_classic.chains.llm'
        )
        
        # 导入并使用 LegacyLLMChain
        from langchain_classic.chains.llm import LLMChain as _LegacyLLMChain
        llm_chain = _LegacyLLMChain(
            llm=llm, 
            prompt=_prompt, 
            callbacks=callbacks
        )

        # 创建文档格式化模板
        document_prompt = PromptTemplate(
            input_variables=["page_content"], 
            template="{page_content}"
        )

        # 创建文档合并链
        combine_documents_chain = LawStuffDocumentsChain(
            llm_chain=llm_chain,
            document_variable_name="context",
            document_prompt=document_prompt,
            callbacks=callbacks,
        )

        # 返回问答链实例
        return cls(
            combine_documents_chain=combine_documents_chain,
            callbacks=callbacks,
            **kwargs,
        )


# ==================== 主要函数 ====================

def get_law_chain(config: Any) -> Chain:
    """
    创建法律问答的主链，这是整个系统的核心函数。
    
    该函数实现了完整的 RAG (检索增强生成) 流程：
    1. 并行检索：同时从向量数据库和网页搜索获取相关信息
    2. 上下文构建：将检索结果格式化并进行质量过滤
    3. 答案生成：基于上下文使用 LLM 生成最终答案
    
    工作流程：
    ---------
    用户问题 
        ↓
    [并行检索阶段]
        ├─→ 多查询向量检索 → 法律条文
        └─→ 网页搜索 → 网页信息
        ↓
    [上下文构建阶段]
        ├─→ 法律条文格式化 → law_context
        ├─→ 网页内容AI提炼 → web_context
        └─→ 文档来源格式化 → formatted_docs
        ↓
    [答案生成阶段]
        └─→ LLM生成 → 最终答案
    
    Args:
        config: 配置对象，必须包含以下属性：
            必需属性：
            - LAW_VS_COLLECTION_NAME: 法律向量库集合名称
            - WEB_VS_COLLECTION_NAME: 网页向量库集合名称
            - LAW_VS_SEARCH_K: 法律向量检索返回的文档数量
            - WEB_VS_SEARCH_K: 网页检索返回的结果数量
            
            可选属性（有默认值）：
            - WEB_SEARCH_REGION: 搜索地区（默认 "cn-zh"）
            - WEB_SEARCH_SAFESEARCH: 安全搜索级别（默认 "strict"）
            - WEB_SEARCH_TIME: 搜索时间范围（默认 "y" 表示一年）
            - WEB_SEARCH_FETCH_K: 网页搜索抓取数量（默认 50）
            - WEB_SEARCH_REQUIRE_HTTPS: 是否要求 HTTPS（默认 True）
            - WEB_SEARCH_ENFORCE_WHITELIST: 是否强制白名单（默认 False）
            - WEB_SEARCH_ALLOWED_DOMAINS: 允许的域名列表
            - WEB_SEARCH_ALLOWED_TLDS: 允许的顶级域名列表
            - WEB_SEARCH_PREFER_DOMAINS: 优先的域名列表
            - WEB_SEARCH_PREFER_TLDS: 优先的顶级域名列表
            - WEB_AI_REFINE_ENABLED: 是否启用AI提炼（默认 False）
            - WEB_AI_REFINE_MAX_DOCS: AI提炼最大文档数（默认 3）
            - WEB_AI_REFINE_MAX_CHARS_PER_DOC: 单文档最大字符数（默认 800）
    
    Returns:
        配置好的 Chain 对象，调用时输入 {"question": "用户问题"}，
        返回包含以下键的字典：
        - answer: 生成的答案文本
        - law_context: 法律条文上下文
        - web_context: 网页信息上下文
        - question: 原始问题
        - law_docs_formatted: 格式化的法律文档（含来源）
        - web_docs_formatted: 格式化的网页文档（含URL）
    
    Examples:
        >>> from config import config
        >>> chain = get_law_chain(config)
        >>> result = chain.invoke({"question": "什么是合同诈骗罪？"})
        >>> print(result["answer"])
        
    Note:
        该函数使用 LangChain 的新版 Runnable 接口
    
    Performance:
        优化说明：
        - 在 chain 创建时预先创建模型实例并通过闭包传递
        - 避免每次调用时重复创建模型，提升性能
        - 配置变化时会重新创建整个 chain（包括新的模型实例）
        - 既保证了热更新支持，又优化了运行时性能
    
    See Also:
        - LawQAChain: 旧版问答链实现（向后兼容）
        - _build_web_snippets: 网页摘要构建函数（通用工具）
    """
    
    # ==================== 第一部分：初始化检索器和模型 ====================
    
    # 1.0 创建模型实例（在chain创建时固定，避免重复创建）
    # 当配置变化时，整个chain会重新创建，从而使用新的模型配置
    llm_model = get_model()  # 用于多查询生成和答案生成
    llm_model_no_stream = get_model(streaming=False)  # 用于网页内容提炼（非流式）
    llm_model_stream = get_model(streaming=True)  # 用于流式答案生成
    
    print(f"  ℹ️  已创建模型实例用于本次chain（支持热更新）")
    
    # 1.1 加载向量存储
    law_vs = get_vectorstore(config.LAW_VS_COLLECTION_NAME)  # 法律条文向量库
    web_vs = get_vectorstore(config.WEB_VS_COLLECTION_NAME)  # 网页内容向量库
    
    # 1.2 创建基础向量检索器
    # 从法律条文向量库检索最相关的 k 个文档
    vs_retriever = law_vs.as_retriever(
        search_kwargs={"k": config.LAW_VS_SEARCH_K}
    )
    
    # 1.3 创建网页检索器
    # 配置 DuckDuckGo 搜索引擎参数
    web_retriever = LawWebRetriever(
        vectorstore=web_vs,
        search=DuckDuckGoSearchAPIWrapper(
            # 地区设置：偏向中文页面和中文标题/摘要
            region=getattr(config, "WEB_SEARCH_REGION", DEFAULT_WEB_SEARCH_REGION),
            # 安全搜索：过滤不适内容和部分低质量内容
            safesearch=getattr(config, "WEB_SEARCH_SAFESEARCH", DEFAULT_WEB_SEARCH_SAFESEARCH),
            # 时间范围：y=一年内，m=一月内，w=一周内
            time=getattr(config, "WEB_SEARCH_TIME", DEFAULT_WEB_SEARCH_TIME),
        ),
        # 网页搜索参数
        fetch_k=int(getattr(config, "WEB_SEARCH_FETCH_K", DEFAULT_WEB_SEARCH_FETCH_K) if getattr(config, "WEB_SEARCH_FETCH_K", None) is not None else DEFAULT_WEB_SEARCH_FETCH_K),
        require_https=bool(getattr(config, "WEB_SEARCH_REQUIRE_HTTPS", True)),
        enforce_whitelist=bool(getattr(config, "WEB_SEARCH_ENFORCE_WHITELIST", False)),
        allowed_domains=getattr(config, "WEB_SEARCH_ALLOWED_DOMAINS", ()) or (),
        allowed_tlds=getattr(config, "WEB_SEARCH_ALLOWED_TLDS", ()) or (),
        prefer_domains=getattr(config, "WEB_SEARCH_PREFER_DOMAINS", ()) or (),
        prefer_tlds=getattr(config, "WEB_SEARCH_PREFER_TLDS", ()) or (),
        num_search_results=config.WEB_VS_SEARCH_K
    )
    
    # 1.4 创建多查询检索器
    # 自动生成问题的多个变体，从不同角度检索，提高召回率
    # 使用预先创建的模型实例，避免重复创建
    multi_query_retriver = get_multi_query_law_retriever(
        vs_retriever,
        llm_model  # 使用固定的模型实例
    )

    # ==================== 第二部分：定义处理函数 ====================

    # 这些函数被包装在闭包中以访问 config 对象和模型实例
    # 使用闭包捕获模型对象，避免每次调用时重新创建

    def smart_law_retrieval(question: str) -> List[Document]:
        """
        智能法律检索：短问题直接单次检索，长问题走多查询。

        短问题（< SHORT_QUESTION_THRESHOLD 字符）信息量有限，
        生成多查询变体收益低，直接走向量检索节省一次 LLM 调用。
        """
        if len(question.strip()) < SHORT_QUESTION_THRESHOLD:
            print(f"  [检索优化] 短问题({len(question.strip())}字)，跳过多查询，使用单次检索")
            return vs_retriever.invoke(question)
        return multi_query_retriver.invoke(question)
    
    def build_web_snippets_for_config(docs: List[Document]) -> str:
        """
        将网页文档列表转换为结构化的摘要文本。
        配置绑定版本，使用当前 config 实例。
        """
        return build_web_snippets(docs, config)
    
    def refine_web_context(question: str, web_docs: List[Document]) -> str:
        """
        使用 AI 提炼网页内容，过滤低质量信息。
        此函数使用预先创建的非流式模型实例。
        """
        # 检查是否启用 AI 提炼功能
        enabled = bool(getattr(config, "WEB_AI_REFINE_ENABLED", False))
        
        if not enabled:
            # 未启用时直接返回简单拼接结果
            return combine_web_docs(web_docs)
        
        # 构建结构化的网页摘要
        web_snippets = build_web_snippets_for_config(web_docs)
        if not web_snippets:
            return ""
        
        # 创建 AI 提炼链：使用固定的模型实例
        refine_chain = (
            WEB_CONTEXT_REFINE_PROMPT 
            | llm_model_no_stream  # 使用闭包捕获的模型实例
            | StrOutputParser()
        )
        
        try:
            # 调用 AI 进行内容提炼
            refined = refine_chain.invoke({
                "question": question, 
                "web_snippets": web_snippets
            })
            return (refined or "").strip()
        
        except Exception as e:
            # 捕获所有异常，确保系统鲁棒性
            print(f"⚠ 网页内容 AI 提炼失败，回退到原始拼接: {e}")
            return combine_web_docs(web_docs)
    
    def format_chat_history(history: List[Dict[str, str]]) -> str:
        """
        将对话历史格式化为可读的文本格式，带智能截断。

        截断策略（三层保护）：
        1. 只取最近 MAX_HISTORY_TURNS 轮对话
        2. 单条消息截断到 MAX_SINGLE_MSG_CHARS 字符
        3. 总字符数超过 MAX_HISTORY_TOTAL_CHARS 时停止

        Args:
            history: 对话历史列表，每个元素包含 role 和 content

        Returns:
            格式化的对话历史字符串
        """
        if not history:
            return ""

        # 只取最近 N 轮（每轮 = user + assistant = 2条消息）
        recent_history = history[-(MAX_HISTORY_TURNS * 2):]

        formatted_lines = ["【对话历史】"]
        total_chars = 0

        for msg in recent_history:
            role = msg.get("role", "")
            content = msg.get("content", "")

            # 单条消息截断
            if len(content) > MAX_SINGLE_MSG_CHARS:
                content = content[:MAX_SINGLE_MSG_CHARS] + "..."

            if role == "user":
                line = f"用户: {content}"
            elif role == "assistant":
                line = f"AI助手: {content}"
            else:
                continue

            # 总字符预算检查
            if total_chars + len(line) > MAX_HISTORY_TOTAL_CHARS:
                formatted_lines.append("...(更早的对话已省略)")
                break

            formatted_lines.append(line)
            total_chars += len(line)

        return "\n".join(formatted_lines)
    
    def generate_answer(inputs: Dict[str, Any]) -> str:
        """
        基于上下文生成最终答案。
        此函数使用预先创建的模型实例，避免重复创建。
        支持对话历史上下文记忆。
        """
        # 格式化对话历史
        history = inputs.get("history", [])
        chat_history = format_chat_history(history)
        
        # 准备提示词所需的输入
        prompt_input = {
            "law_context": inputs.get("law_context", ""),
            "web_context": inputs.get("web_context", ""),
            "question": inputs.get("question", ""),
            "chat_history": chat_history
        }
        
        # 创建答案生成链：使用固定的模型实例
        chain = LAW_PROMPT | llm_model | StrOutputParser()  # 使用闭包捕获的模型实例
        
        return chain.invoke(prompt_input)
    
    # ==================== 第三部分：构建处理链 ====================

    # Stage 1+2：检索 + 上下文构建（用于流式模式的前置同步执行）
    retrieval_chain = (
        # 阶段1：并行检索
        # 同时执行向量检索和网页搜索，提高响应速度
        RunnableMap({
            # 智能法律检索：短问题单次检索，长问题多查询
            "law_docs": itemgetter("question") | RunnableLambda(smart_law_retrieval),
            # 网页检索：从搜索引擎获取相关网页
            "web_docs": itemgetter("question") | web_retriever,
            # 保留原始问题供后续使用
            "question": itemgetter("question"),
            # 保留对话历史供上下文记忆使用
            "history": lambda x: x.get("history", [])
        })

        # 阶段2：上下文构建
        # 将原始检索结果转换为结构化的上下文文本
        | RunnableMap({
            # 法律条文格式化：拼接成连续文本
            "law_context": lambda x: combine_law_docs(x["law_docs"]),
            # 网页内容提炼：AI过滤并提炼关键信息
            "web_context": lambda x: refine_web_context(x["question"], x["web_docs"]),
            # 文档来源格式化：保留原始文档的来源信息
            "law_docs_formatted": lambda x: format_law_docs_with_source(x["law_docs"]),
            "web_docs_formatted": lambda x: format_web_docs_with_url(x["web_docs"]),
            # 保留问题供答案生成使用
            "question": itemgetter("question"),
            # 保留对话历史
            "history": itemgetter("history")
        })
    )

    # 完整 chain（非流式，向后兼容）
    # 使用 LangChain 的 Runnable 接口构建三阶段处理链
    full_chain = (
        retrieval_chain

        # 阶段3：答案生成
        # 基于构建的上下文，使用 LLM 生成最终答案（包含对话历史）
        | RunnableMap({
            # 调用 LLM 生成答案（传入对话历史）
            "answer": RunnableLambda(generate_answer),
            # 保留所有中间结果供前端展示和调试
            "law_context": itemgetter("law_context"),
            "web_context": itemgetter("web_context"),
            "question": itemgetter("question"),
            "law_docs_formatted": itemgetter("law_docs_formatted"),
            "web_docs_formatted": itemgetter("web_docs_formatted"),
        })
    )

    def stream_answer(inputs: Dict[str, Any]):
        """
        流式生成答案的生成器函数。

        接收 retrieval_chain 的输出（Stage 1+2 的结果），
        使用流式模型逐 chunk 生成答案。

        Args:
            inputs: retrieval_chain.invoke() 的返回字典，包含：
                - law_context, web_context, question, history 等

        Yields:
            str: 答案文本的每个 chunk
        """
        history = inputs.get("history", [])
        chat_history = format_chat_history(history)

        prompt_input = {
            "law_context": inputs.get("law_context", ""),
            "web_context": inputs.get("web_context", ""),
            "question": inputs.get("question", ""),
            "chat_history": chat_history
        }

        # 使用流式模型生成答案
        # 注：wcode.net API 流式结束时可能返回非标准格式（delta 为 list 而非 dict），
        # 导致 langchain_openai 解析报 AttributeError，此处捕获并优雅结束流。
        answer_chain = LAW_PROMPT | llm_model_stream | StrOutputParser()
        try:
            for chunk in answer_chain.stream(prompt_input):
                yield chunk
        except AttributeError:
            # API 返回的流结束标记格式不兼容，正常结束即可
            return

    return {
        "full_chain": full_chain,
        "retrieval_chain": retrieval_chain,
        "stream_answer": stream_answer,
    }


