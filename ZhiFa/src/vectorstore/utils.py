import os
import sys
import hashlib
from langchain_classic.storage import LocalFileStore
from langchain_classic.embeddings import CacheBackedEmbeddings
from langchain_classic.indexes import SQLRecordManager, index
from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings
from typing import List, Dict
from langchain_core.documents import Document
from langchain_classic.indexes._api import _batch
from collections import defaultdict

from ..config.config import Config

# 存储路径配置
STORAGE_DIR = "./storage"
CACHE_DIR = f"{STORAGE_DIR}/cache/embeddings"
CHROMA_DB_DIR = f"{STORAGE_DIR}/chroma_db"
RECORD_MANAGER_DB = f"sqlite:///{STORAGE_DIR}/record_manager.db"


# 获取带缓存的嵌入模型 - 使用本地文件缓存避免重复调用 API
def get_cached_embedder() -> CacheBackedEmbeddings:
    """
    获取带缓存的嵌入模型（腾讯混元 via 万码云 OpenAI 兼容端点）

    Returns:
        配置好的 CacheBackedEmbeddings 实例
    """
    fs = LocalFileStore(CACHE_DIR)

    embedding_model = Config.get_embedding_model()
    api_key = Config.get_api_key()

    print(f"[Embedding配置] 使用模型: {embedding_model}")

    underlying_embeddings = OpenAIEmbeddings(
        model=embedding_model,
        api_key=api_key,
        base_url=Config.DEFAULT_BASE_URL,
        check_embedding_ctx_length=False,
    )

    def custom_key_encoder(s: str) -> str:
        namespace = f"embedding-{embedding_model}"
        prefixed_input = f"{namespace}:{s}"
        return hashlib.sha256(prefixed_input.encode()).hexdigest()

    cached_embedder = CacheBackedEmbeddings.from_bytes_store(
        underlying_embeddings,
        fs,
        key_encoder=custom_key_encoder
    )
    return cached_embedder


# 获取记录管理器 - 用于跟踪向量数据库中文档的索引状态
def get_record_manager(namespace: str = "law") -> SQLRecordManager:
    return SQLRecordManager(
        f"vectorstore/{namespace}", db_url=RECORD_MANAGER_DB
    )


# 获取向量存储 - 用于存储和检索文档的向量表示
def get_vectorstore(collection_name: str = "law") -> Chroma:
    vectorstore = Chroma(
        persist_directory=CHROMA_DB_DIR,
        embedding_function=get_cached_embedder(),
        collection_name=collection_name)

    return vectorstore


# 清空向量存储 - 删除指定集合中的所有文档
def clear_vectorstore(collection_name: str = "law") -> None:
    record_manager = get_record_manager(collection_name)
    vectorstore = get_vectorstore(collection_name)

    index([], record_manager, vectorstore, cleanup="full", source_id_key="source")


# 将法律文档索引到向量数据库 - 批量处理文档并显示进度
def law_index(docs: List[Document], show_progress: bool = True) -> Dict:
    info = defaultdict(int)

    record_manager = get_record_manager("law")
    vectorstore = get_vectorstore("law")

    pbar = None
    if show_progress:
        from tqdm import tqdm
        pbar = tqdm(total=len(docs))

    for docs in _batch(100, docs):
        result = index(
            docs,
            record_manager,
            vectorstore,
            cleanup=None,
            # cleanup="full",
            source_id_key="source",
        )
        for k, v in result.items():
            info[k] += v

        if pbar:
            pbar.update(len(docs))

    if pbar:
        pbar.close()

    return dict(info)


# 将刑事案例索引到向量数据库 - 批量处理案例并显示进度
def case_index(docs: List[Document], show_progress: bool = True) -> Dict:
    """
    将刑事案例索引到向量数据库
    
    Args:
        docs: 案例Document列表
        show_progress: 是否显示进度条
        
    Returns:
        索引统计信息字典
    """
    info = defaultdict(int)

    record_manager = get_record_manager("criminal_cases")
    vectorstore = get_vectorstore("criminal_cases")

    pbar = None
    if show_progress:
        from tqdm import tqdm
        pbar = tqdm(total=len(docs))

    # 案例文本较长，使用较小的批次
    for batch_docs in _batch(50, docs):
        result = index(
            batch_docs,
            record_manager,
            vectorstore,
            cleanup=None,
            source_id_key="source",
        )
        for k, v in result.items():
            info[k] += v

        if pbar:
            pbar.update(len(batch_docs))

    if pbar:
        pbar.close()

    return dict(info)
