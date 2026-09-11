"""
case_loader.py - 案例数据加载器

功能说明：
1. 加载JSON格式的刑事案例数据集
2. 将案例转换为LangChain Document格式
3. 支持案例有效性过滤（字符长度限制）
"""

import json
from typing import List, Optional, Dict, Any
from langchain_core.documents import Document


class CaseLoader:
    """
    刑事案例数据加载器
    
    支持加载JSON Lines格式的案例数据集，每行一个JSON对象
    """
    
    def __init__(
        self, 
        file_path: str, 
        max_chars: int = 1500,
        max_cases: Optional[int] = None
    ):
        """
        初始化案例加载器
        
        Args:
            file_path: 数据集文件路径
            max_chars: 案情描述最大字符数（超过则过滤掉）
            max_cases: 最大加载案例数（None表示全部加载）
        """
        self.file_path = file_path
        self.max_chars = max_chars
        self.max_cases = max_cases
    
    def load(self) -> List[Document]:
        """
        加载案例数据集并转换为Document列表
        
        Returns:
            Document列表，每个Document包含案情描述和元数据
        """
        documents = []
        skipped_count = 0
        
        print(f"正在加载案例数据集: {self.file_path}")
        
        with open(self.file_path, 'r', encoding='utf-8') as f:
            for idx, line in enumerate(f):
                if line.strip():
                    try:
                        case = json.loads(line)
                        
                        # 检查案例有效性
                        fact = case.get('fact', '')
                        if not fact.strip() or len(fact) > self.max_chars:
                            skipped_count += 1
                            continue
                        
                        # 提取元数据
                        meta = case.get('meta', {})
                        term_of_imprisonment = meta.get('term_of_imprisonment', {})
                        
                        # 处理列表类型字段 - Chroma不支持列表，需要转为字符串
                        accusation_list = meta.get('accusation', [])
                        accusation_str = '、'.join(accusation_list) if accusation_list else ''
                        
                        criminals_list = meta.get('criminals', [])
                        criminals_str = '、'.join(criminals_list) if criminals_list else ''
                        
                        # 创建Document
                        doc = Document(
                            page_content=fact,
                            metadata={
                                "case_index": idx,
                                "accusation": accusation_str,  # 转为字符串
                                "imprisonment": term_of_imprisonment.get('imprisonment', 0),
                                "death_penalty": term_of_imprisonment.get('death_penalty', False),
                                "life_imprisonment": term_of_imprisonment.get('life_imprisonment', False),
                                "punish_of_money": meta.get('punish_of_money', 0),
                                "criminals": criminals_str,  # 转为字符串
                                "source": self.file_path
                            }
                        )
                        documents.append(doc)
                        
                        # 检查是否达到最大加载数
                        if self.max_cases and len(documents) >= self.max_cases:
                            break
                            
                    except json.JSONDecodeError as e:
                        print(f"警告: 第 {idx+1} 行JSON解析失败: {e}")
                        continue
        
        print(f"✓ 已加载 {len(documents)} 条有效案例")
        if skipped_count > 0:
            print(f"  跳过 {skipped_count} 条案例（fact过长或为空）")
        
        return documents
    
    def load_raw(self) -> List[Dict[str, Any]]:
        """
        加载原始案例数据（不转换为Document）
        
        Returns:
            案例字典列表
        """
        cases = []
        
        with open(self.file_path, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    try:
                        case = json.loads(line)
                        cases.append(case)
                    except json.JSONDecodeError:
                        continue
        
        return cases


def extract_keywords(text: str) -> List[str]:
    """
    从案情文本中提取量刑情节关键词
    
    Args:
        text: 案情描述文本
        
    Returns:
        关键词列表
    """
    keywords = []
    
    # 从轻情节
    if "自首" in text or "投案" in text:
        keywords.append("自首")
    if "坦白" in text or "如实供述" in text:
        keywords.append("坦白")
    if "赔偿" in text or "退赔" in text or "退赃" in text:
        keywords.append("赔偿")
    if "谅解" in text:
        keywords.append("取得谅解")
    if "从犯" in text:
        keywords.append("从犯")
    if "未遂" in text:
        keywords.append("犯罪未遂")
    if "中止" in text:
        keywords.append("犯罪中止")
    if "初犯" in text or "偶犯" in text:
        keywords.append("初犯")
    
    # 从重情节
    if "累犯" in text:
        keywords.append("累犯")
    if "主犯" in text:
        keywords.append("主犯")
    if "多次" in text:
        keywords.append("多次犯罪")
    if "团伙" in text or "共同犯罪" in text:
        keywords.append("共同犯罪")
    
    return keywords

