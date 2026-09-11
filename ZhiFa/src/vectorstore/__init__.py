"""
vectorstore package - 向量数据库模块

包含：
- case_loader: 案例数据加载器
- loader: 法律文档加载器
- splitter: 文档分割器
- utils: 向量数据库工具函数
"""

from .utils import (
    get_cached_embedder,
    get_record_manager,
    get_vectorstore,
    clear_vectorstore,
    law_index,
    case_index,
)
from .case_loader import CaseLoader, extract_keywords
from .loader import LawLoader
from .splitter import LawSplitter

__all__ = [
    "get_cached_embedder",
    "get_record_manager",
    "get_vectorstore",
    "clear_vectorstore",
    "law_index",
    "case_index",
    "CaseLoader",
    "extract_keywords",
    "LawLoader",
    "LawSplitter",
]

