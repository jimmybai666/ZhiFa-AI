# 检索器模块 - 提供法律文档和网页搜索的检索功能
from typing import Any, List, Sequence, Tuple
from urllib.parse import urlparse

from langchain_core.vectorstores import VectorStore
from langchain_community.utilities import DuckDuckGoSearchAPIWrapper
from langchain_core.retrievers import BaseRetriever
from langchain_core.documents import Document
from langchain_core.callbacks import CallbackManagerForRetrieverRun
from pydantic import Field, BaseModel
from langchain_core.output_parsers import BaseOutputParser
from langchain_text_splitters import RecursiveCharacterTextSplitter, TextSplitter
from langchain_core.runnables import RunnablePassthrough, RunnableLambda
from langchain_classic.retrievers.multi_query import MultiQueryRetriever
from duckduckgo_search.exceptions import DuckDuckGoSearchException

from .question_answering_prompt import MULTI_QUERY_PROMPT_TEMPLATE


# ==================== 常量定义 ====================

DEFAULT_WEB_REFINE_MAX_DOCS = 3
DEFAULT_WEB_REFINE_MAX_CHARS_PER_DOC = 800


# ==================== 辅助函数 ====================

def build_web_snippets(docs: List[Document], config: Any) -> str:
    """
    将网页 Document 列表整理成可用于 LLM 提炼的编号摘要。

    此函数将原始的网页检索结果转换为结构化的文本格式，
    便于后续的 AI 处理和内容提炼。

    Args:
        docs: 网页文档列表，每个文档包含 page_content 和 metadata
        config: 配置对象，包含以下可选属性：
            - WEB_AI_REFINE_MAX_DOCS: 最多处理的文档数量（默认3）
            - WEB_AI_REFINE_MAX_CHARS_PER_DOC: 单个摘要的最大字符数（默认800）

    Returns:
        格式化的网页摘要字符串，格式如下：
        [1] 标题：xxx
            链接：xxx
            摘要：xxx

        [2] 标题：yyy
            链接：yyy
            摘要：yyy

    Examples:
        >>> docs = [Document(page_content="内容", metadata={"title": "标题", "link": "url"})]
        >>> result = build_web_snippets(docs, config)
    """
    if not docs:
        return ""

    # 从配置中获取参数，使用默认值作为后备
    max_docs = int(getattr(config, "WEB_AI_REFINE_MAX_DOCS", DEFAULT_WEB_REFINE_MAX_DOCS) or DEFAULT_WEB_REFINE_MAX_DOCS)
    max_chars = int(getattr(config, "WEB_AI_REFINE_MAX_CHARS_PER_DOC", DEFAULT_WEB_REFINE_MAX_CHARS_PER_DOC) or DEFAULT_WEB_REFINE_MAX_CHARS_PER_DOC)

    lines: List[str] = []
    for idx, doc in enumerate(docs[:max_docs], start=1):
        meta = doc.metadata or {}
        title = meta.get("title", "").strip() or "无标题"
        url = meta.get("link", meta.get("url", "")).strip()
        snippet = (doc.page_content or "").strip()

        # 限制单个摘要的长度，避免超长内容
        if len(snippet) > max_chars:
            snippet = snippet[:max_chars] + "..."

        lines.append(
            f"[{idx}] 标题：{title}\n"
            f"    链接：{url}\n"
            f"    摘要：{snippet}"
        )

    return "\n\n".join(lines)


# ==================== 核心检索器 ====================

# 法律网页检索器 - 使用DuckDuckGo搜索相关网页并分割成文档块
class LawWebRetriever(BaseRetriever):
    # Inputs
    vectorstore: VectorStore = Field(
        ..., description="Vector store for storing web pages"
    )

    search: DuckDuckGoSearchAPIWrapper = Field(..., description="DuckDuckGo Search API Wrapper")
    num_search_results: int = Field(1, description="Number of pages per Google search")

    # 先从 DDG 拉取更多候选，再按优先级排序后截断
    fetch_k: int = Field(30, description="How many raw results to fetch before ranking")
    require_https: bool = Field(True, description="Prefer https links (filters out non-https)")

    # 强制白名单：只允许命中 allowed_domains / allowed_tlds 的结果
    enforce_whitelist: bool = Field(False, description="If True, drop results not in allowlist")
    allowed_domains: Sequence[str] = Field(
        default_factory=tuple,
        description="Allowed domains (rank/allow), e.g. ('pkulaw.com',)",
    )
    allowed_tlds: Sequence[str] = Field(
        default_factory=tuple,
        description="Allowed suffixes, e.g. ('.gov.cn',)",
    )

    # 仅做优先排序（不会做白名单硬限制）
    prefer_domains: Sequence[str] = Field(
        default_factory=tuple,
        description="Preferred domains (rank higher), e.g. ('pkulaw.com',)",
    )
    prefer_tlds: Sequence[str] = Field(
        default_factory=tuple,
        description="Preferred suffixes (rank higher), e.g. ('.gov.cn',)",
    )

    text_splitter: TextSplitter = Field(
        RecursiveCharacterTextSplitter(chunk_size=1500, chunk_overlap=50),
        description="Text splitter for splitting web pages into chunks",
    )

    # 检索相关文档 - 通过DuckDuckGo搜索并返回网页内容
    def _get_relevant_documents(
        self,
        query: str,
        *,
        run_manager: CallbackManagerForRetrieverRun,
    ) -> List[Document]:

        fetch_k = max(int(self.fetch_k or 0), int(self.num_search_results or 0))

        try:
            results = self.search.results(query, fetch_k)
        except DuckDuckGoSearchException:
            results = []

        ranked: List[Tuple[int, dict]] = []
        for res in results or []:
            link = res.get("link", "") or ""
            host, scheme = self._host_and_scheme(link)
            if not host:
                continue
            if self.require_https and scheme != "https":
                continue
            if self.enforce_whitelist and not self._is_allowed_host(host):
                continue

            score = self._score_host(host)
            ranked.append((score, res))

        # 分数高的（.gov.cn / pkulaw.com）优先
        ranked.sort(key=lambda x: x[0], reverse=True)

        docs: List[Document] = []
        for _, res in ranked[: int(self.num_search_results or 0)]:
            docs.append(
                Document(
                    page_content=res.get("snippet", "") or "",
                    metadata={"link": res.get("link", "") or "", "title": res.get("title", "") or ""},
                )
            )

        docs = self.text_splitter.split_documents(docs)

        return docs

    def _host_and_scheme(self, link: str) -> Tuple[str, str]:
        try:
            u = urlparse(link or "")
            return (u.hostname or "").lower(), (u.scheme or "").lower()
        except Exception:
            return "", ""

    def _match_suffix(self, host: str, suffix: str) -> bool:
        host = (host or "").lower()
        suffix = (suffix or "").strip().lower().lstrip(".")
        if not host or not suffix:
            return False
        return host == suffix or host.endswith("." + suffix)

    def _score_host(self, host: str) -> int:
        score = 0
        # 优先域名（例如 pkulaw.com）
        for d in self.prefer_domains:
            if self._match_suffix(host, str(d)):
                score += 10
                break

        # 优先后缀（例如 .gov.cn）
        for t in self.prefer_tlds:
            if self._match_suffix(host, str(t)):
                score += 5
                break

        return score

    def _is_allowed_host(self, host: str) -> bool:
        """白名单判定：命中 allowed_domains 或 allowed_tlds 即允许。"""
        host = (host or "").lower()
        if not host:
            return False

        for d in self.allowed_domains:
            if self._match_suffix(host, str(d)):
                return True

        for t in self.allowed_tlds:
            if self._match_suffix(host, str(t)):
                return True

        return False


# ==================== 输出解析器 ====================

# 输出解析器 - 将LLM结果分割成查询列表
class LineList(BaseModel):
    # "lines" is the key (attribute name) of the parsed output
    lines: List[str] = Field(description="Lines of text")


# 行列表输出解析器 - 将文本按行分割
class LineListOutputParser(BaseOutputParser[List[str]]):
    """将文本按行分割的输出解析器，直接返回字符串列表"""

    @property
    def _type(self) -> str:
        return "line_list"

    # 解析文本为查询列表
    def parse(self, text: str) -> List[str]:
        # 清理并分割文本
        lines = [line.strip() for line in text.strip().split("\n") if line.strip()]
        # 过滤掉空行和过短的查询
        lines = [line for line in lines if len(line) > 5]
        return lines


# ==================== 工厂函数 ====================

# 获取多查询法律检索器 - 生成多个查询变体以提高检索效果
def get_multi_query_law_retriever(retriever: BaseRetriever, model: BaseModel) -> BaseRetriever:
    output_parser = LineListOutputParser()

    # 使用新的 RunnableSequence 语法替代已弃用的 LLMChain
    # 创建一个包装函数来处理输入格式
    def format_input(x):
        # 如果输入是字典且包含 'question' 键，则使用它
        if isinstance(x, dict) and 'question' in x:
            return x
        # 否则将输入包装成字典
        return {'question': x}

    llm_chain = (
        RunnableLambda(format_input)
        | MULTI_QUERY_PROMPT_TEMPLATE
        | model
        | output_parser
    )

    # 不需要设置 parser_key，因为输出直接是列表
    retriever = MultiQueryRetriever(
        retriever=retriever, llm_chain=llm_chain
    )

    return retriever


