"""
法律文档组合链 - 将检索到的法律文档按来源分类并格式化

包含：
- LawStuffDocumentsChain: 法律文档组合链（按书籍/网页分类）
- get_check_law_chain: 法律相关性检查链
"""
from typing import Any, Optional, List
from collections import defaultdict
from langchain_classic.chains.combine_documents.stuff import StuffDocumentsChain
from langchain_core.documents import Document
from langchain_core.prompts import format_document
from langchain_classic.output_parsers import BooleanOutputParser
from langchain_classic.chains.base import Chain
from ..core.model_factory import get_model
from .question_answering_prompt import CHECK_LAW_PROMPT


class LawStuffDocumentsChain(StuffDocumentsChain):
    """
    继承自 LangChain 的 StuffDocumentsChain，用于将多个检索到的文档组合成一个字符串。

    特点：
    - 将法律条文(book metadata)和网页信息(link metadata)分别组织
    - 为不同来源的文档添加标题标签（《书名》、网页：标题）
    - 通过 document_prompt 格式化每个文档

    工作流程：
    1. 遍历所有检索到的文档
    2. 根据 metadata 中的 'book' 或 'link' 字段进行分类
    3. 为每个分类分别生成格式化字符串
    4. 按书籍→网页的顺序拼接
    """

    def _get_inputs(self, docs: List[Document], **kwargs: Any) -> dict:
        """
        将文档按来源分类并格式化，最终作为 'context' 输入给 LLMChain。
        """
        law_book = defaultdict(list)
        law_web = defaultdict(list)

        for doc in docs:
            metadata = doc.metadata
            if 'book' in metadata:
                law_book[metadata["book"]].append(
                    format_document(doc, self.document_prompt).strip("\n"))
            elif 'link' in metadata:
                law_web[metadata["title"]].append(
                    format_document(doc, self.document_prompt).strip("\n"))

        law_str = ""

        for book, page_contents in law_book.items():
            law_str += f"《{book}》\n"
            law_str += "\n".join(page_contents)
            law_str += "\n\n"

        for web, page_contents in law_web.items():
            law_str += f"网页：{web}\n"
            law_str += "\n".join(page_contents)
            law_str += "\n\n"

        inputs = {
            k: v
            for k, v in kwargs.items()
            if k in self.llm_chain.prompt.input_variables
        }
        inputs[self.document_variable_name] = law_str
        return inputs


def get_check_law_chain(config: Any) -> Chain:
    """获取法律相关性检查链 - 判断问题是否与法律相关"""
    model = get_model()
    check_chain = CHECK_LAW_PROMPT | model | BooleanOutputParser()
    return check_chain
