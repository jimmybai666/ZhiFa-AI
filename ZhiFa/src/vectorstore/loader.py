import chardet
from typing import Any, List
from langchain_community.document_loaders import DirectoryLoader
from langchain_core.documents import Document


def safe_read_text(file_path: str) -> str:
    """自动检测文件编码并读取内容"""
    # 先检测编码
    with open(file_path, "rb") as f:
        raw = f.read()
        detect = chardet.detect(raw)
        enc = detect.get("encoding")
        # 有些中文文件检测会给出 GB2312，但 Python 实际用 gbk 兼容更好
        if enc and enc.lower() == "gb2312":
            enc = "gbk"

    # 尝试检测出来的编码
    try:
        return raw.decode(enc or "utf-8")
    except Exception:
        pass

    # 再尝试 UTF-8 / GBK / ANSI（latin-1）
    for encoding in ["utf-8", "gbk", "latin-1"]:
        try:
            return raw.decode(encoding)
        except:
            continue

    raise RuntimeError(f"无法识别编码: {file_path}")


class MyTextLoader:
    """替代 LangChain 默认 TextLoader，可以自动识别编码"""
    def __init__(self, file_path: str):
        self.file_path = file_path

    def load(self) -> List[Document]:
        text = safe_read_text(self.file_path)
        return [Document(page_content=text, metadata={"source": self.file_path})]

    def lazy_load(self):
        text = safe_read_text(self.file_path)
        yield Document(page_content=text, metadata={"source": self.file_path})



class LawLoader(DirectoryLoader):
    """自动加载法律文档（支持多编码）"""
    def __init__(self, path: str, **kwargs: Any) -> None:
        super().__init__(
            path,
            glob="**/*.md",
            loader_cls=MyTextLoader,  # 使用自定义的可自动解码 Loader
            **kwargs
        )
