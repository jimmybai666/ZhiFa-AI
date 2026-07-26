"""
文档格式化工具 - 将检索到的法律文档和网页文档格式化为结构化数据
"""
import re
from typing import List
from collections import defaultdict

from langchain_core.documents import Document


def combine_law_docs(docs: List[Document]) -> str:
    """按书籍分类整理法律文档并格式化"""
    law_books = defaultdict(list)
    for doc in docs:
        metadata = doc.metadata
        if 'book' in metadata:
            law_books[metadata["book"]].append(doc)

    law_str = ""
    for book, docs in law_books.items():
        law_str += f"相关法律：《{book}》\n"
        law_str += "\n".join([doc.page_content.strip("\n") for doc in docs])
        law_str += "\n"

    return law_str


def combine_web_docs(docs: List[Document]) -> str:
    """格式化网页文档"""
    web_str = ""
    for doc in docs:
        web_str += f"相关网页：{doc.metadata['title']}\n"
        web_str += f"网页地址：{doc.metadata['link']}\n"
        web_str += doc.page_content.strip("\n") + "\n"
        web_str += "\n"

    return web_str


def format_law_docs_with_source(docs: List[Document]) -> List[dict]:
    """
    将法律文档格式化为包含来源的字典列表，提取具体条款信息
    """
    if not docs:
        return []

    formatted_docs = []
    for doc in docs:
        metadata = doc.metadata if doc.metadata else {}
        book = metadata.get("book", metadata.get("source", "法律条文"))
        chapter = metadata.get("header2", "")

        article_match = re.match(r'(第\S+条)', doc.page_content)
        article = article_match.group(1) if article_match else ""

        if article:
            source = f"《{book}》{article}"
        else:
            source = f"《{book}》"

        formatted_docs.append({
            "source": source,
            "chapter": chapter,
            "content": doc.page_content
        })

    return formatted_docs


def format_web_docs_with_url(docs: List[Document]) -> List[dict]:
    """
    将网页文档格式化为包含URL的字典列表
    """
    if not docs:
        return []

    formatted_docs = []
    for doc in docs:
        metadata = doc.metadata if doc.metadata else {}
        url = metadata.get("link", metadata.get("url", ""))
        title = metadata.get("title", "网页来源")

        formatted_docs.append({
            "title": title,
            "url": url,
            "content": doc.page_content
        })

    return formatted_docs
