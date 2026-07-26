from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_text_splitters import MarkdownHeaderTextSplitter
from langchain_core.documents import Document
from typing import Any, Iterable, List

class LawSplitter(RecursiveCharacterTextSplitter):
    
    # 初始化法律文档分割器，配置按"第X条"分割和Markdown标题分割

    def __init__(self, **kwargs: Any) -> None:
        """Initialize a LawSplitter."""
        separators = [r"第\S*条 "]
        is_separator_regex = True

        headers_to_split_on = [
            ("#", "header1"),
            ("##", "header2"),
            ("###", "header3"),
            ("####", "header4"),
        ]

        self.md_splitter = MarkdownHeaderTextSplitter(headers_to_split_on=headers_to_split_on)
        super().__init__(separators=separators, is_separator_regex=is_separator_regex, **kwargs)

    # 将法律文档按Markdown标题和条款分割，并提取书籍名称到元数据
    
    def split_documents(self, documents: Iterable[Document]) -> List[Document]:
        """Split documents."""
        texts, metadatas = [], []
        for doc in documents:
            md_docs = self.md_splitter.split_text(doc.page_content)
            for md_doc in md_docs:
                texts.append(md_doc.page_content)

                metadatas.append(
                    md_doc.metadata | doc.metadata | {"book": md_doc.metadata.get("header1")})

        return self.create_documents(texts, metadatas=metadatas)
