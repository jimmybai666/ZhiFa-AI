"""
case_prediction.py - 案情预测功能

基于检索增强的刑事案件预测系统，包含：
- 刑期预测
- 罪名预测
- 案例综合分析

核心流程：
1. 从案例向量库检索相似案例
2. 从法律向量库检索相关刑法条文
3. 结合案例和法条进行LLM预测
"""

import re
import difflib
from typing import Any, List, Dict, Optional, Tuple
from collections import Counter

from langchain_classic.chains.base import Chain
from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import RunnableLambda
from langchain_classic.retrievers.multi_query import MultiQueryRetriever
from pydantic import BaseModel, Field

from ..vectorstore.utils import get_vectorstore
from ..vectorstore.case_loader import extract_keywords
from ..core.model_factory import get_model
from .case_prediction_prompt import (
    IMPRISONMENT_PREDICTION_PROMPT,
    ACCUSATION_PREDICTION_PROMPT,
    CASE_ANALYSIS_PROMPT
)
from .question_answering_prompt import MULTI_QUERY_PROMPT_TEMPLATE
from .law_web_retriver import LineListOutputParser


# ==================== 刑法条文处理 ====================

def load_criminal_law(file_path: str) -> Optional[str]:
    """加载刑法条文"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        print(f"⚠️ 无法加载刑法文件: {e}")
        return None


def parse_criminal_law_articles(criminal_law_content: str) -> Dict[str, List[Dict]]:
    """
    解析刑法条文，构建罪名-法条映射字典
    
    Returns:
        罪名到相关法条的映射字典
    """
    if not criminal_law_content:
        return {}
    
    crime_to_articles = {}
    
    # 提取所有的法条（第XXX条）
    article_pattern = r'第([一二三四五六七八九十百千零]+)条\s+(.*?)(?=第[一二三四五六七八九十百千零]+条|$)'
    articles = re.findall(article_pattern, criminal_law_content, re.DOTALL)
    
    # 常见罪名关键词映射
    common_crimes = {
        '故意杀人': ['杀人'],
        '故意伤害': ['伤害'],
        '强奸': ['强奸', '奸淫'],
        '抢劫': ['抢劫'],
        '盗窃': ['盗窃'],
        '诈骗': ['诈骗'],
        '贩卖毒品': ['毒品', '贩卖', '走私'],
        '抢夺': ['抢夺'],
        '敲诈勒索': ['敲诈勒索'],
        '交通肇事': ['交通', '肇事'],
        '危险驾驶': ['危险驾驶', '醉酒驾驶'],
        '非法拘禁': ['非法拘禁'],
        '寻衅滋事': ['寻衅滋事'],
        '聚众斗殴': ['聚众斗殴'],
        '绑架': ['绑架'],
        '拐卖妇女儿童': ['拐卖'],
        '走私': ['走私'],
        '受贿': ['受贿'],
        '贪污': ['贪污'],
        '挪用公款': ['挪用'],
        '职务侵占': ['职务侵占'],
        '妨害公务': ['妨害公务', '阻碍'],
        '容留吸毒': ['容留', '吸毒'],
        '开设赌场': ['赌博', '开设赌场'],
    }
    
    for article_num, article_content in articles:
        for crime, keywords in common_crimes.items():
            for keyword in keywords:
                if keyword in article_content:
                    if crime not in crime_to_articles:
                        crime_to_articles[crime] = []
                    
                    clean_content = re.sub(r'\s+', ' ', article_content.strip())
                    article_info = {
                        'article_num': article_num,
                        'content': clean_content[:500]
                    }
                    
                    if article_info not in crime_to_articles[crime]:
                        crime_to_articles[crime].append(article_info)
                    break
    
    return crime_to_articles


def find_relevant_law_articles(
    accusation: Any, 
    crime_to_articles: Dict[str, List[Dict]]
) -> List[Dict]:
    """根据罪名查找相关法律条文"""
    if not crime_to_articles:
        return []
    
    if isinstance(accusation, list):
        if not accusation:
            return []
        accusation = accusation[0]
    
    # 直接匹配
    if accusation in crime_to_articles:
        return crime_to_articles[accusation]
    
    # 模糊匹配
    all_crimes = list(crime_to_articles.keys())
    matches = difflib.get_close_matches(accusation, all_crimes, n=1, cutoff=0.6)
    
    if matches:
        return crime_to_articles[matches[0]]
    
    # 部分匹配
    for crime in all_crimes:
        if crime in accusation or accusation in crime:
            return crime_to_articles[crime]
    
    return []


def format_law_articles(articles: List[Dict], max_articles: int = 3) -> str:
    """格式化法律条文"""
    if not articles:
        return "未找到直接相关的刑法条文"
    
    formatted = []
    for article in articles[:max_articles]:
        formatted.append(f"第{article['article_num']}条：{article['content']}")
    
    return '\n'.join(formatted)


# ==================== 结构化输出 Schema ====================

class ImprisonmentPrediction(BaseModel):
    """刑期预测结构化输出"""
    crime: str = Field(description="罪名")
    statutory_range: str = Field(description="法定刑幅度")
    mitigating_factors: List[str] = Field(description="从轻情节列表，无则为空列表")
    aggravating_factors: List[str] = Field(description="从重情节列表，无则为空列表")
    reference_range_min: int = Field(description="参考刑期范围下限（月）")
    reference_range_max: int = Field(description="参考刑期范围上限（月）")
    reference_analysis: str = Field(description="参考案例分析（相似案件量刑区间、情节异同）")
    predicted_months: int = Field(description="预测刑期（月）")
    reasoning: str = Field(description="预测理由（法条→情节→案例库对比→结论）")


class CaseAnalysisSummary(BaseModel):
    """案情综合分析摘要结构化输出"""
    predicted_accusation: str = Field(description="推测的罪名")
    sentence_range_min: int = Field(description="AI预测刑期区间下限（月），参考相似案例的判决结果")
    sentence_range_max: int = Field(description="AI预测刑期区间上限（月），参考相似案例的判决结果")


# ==================== 案情预测核心类 ====================

class CasePredictionChain:
    """
    案情预测链
    
    整合案例检索和法律检索，提供刑期预测、罪名预测等功能
    """
    
    def __init__(self, config: Any):
        """
        初始化案情预测链

        Args:
            config: 配置对象
        """
        self.config = config

        # 加载案例向量库
        self.case_vs = get_vectorstore(config.CASE_VS_COLLECTION_NAME)
        self.case_retriever = self.case_vs.as_retriever(
            search_kwargs={"k": config.CASE_VS_SEARCH_K}
        )

        # 加载法律向量库（复用现有的法律知识向量库）
        self.law_vs = get_vectorstore(config.LAW_VS_COLLECTION_NAME)
        self.law_retriever = self.law_vs.as_retriever(
            search_kwargs={"k": 5}
        )

        # 加载刑法条文用于罪名-法条映射
        self.crime_to_articles = {}
        criminal_law = load_criminal_law(config.CRIMINAL_LAW_PATH)
        if criminal_law:
            self.crime_to_articles = parse_criminal_law_articles(criminal_law)
            print(f"✓ 已加载 {len(self.crime_to_articles)} 个罪名的相关法条映射")

        # 获取LLM模型
        self.model = get_model(streaming=False)

        # 构建 Multi-Query 案例检索器
        output_parser = LineListOutputParser()

        def format_input(x):
            if isinstance(x, dict) and 'question' in x:
                return x
            return {'question': x}

        llm_chain = (
            RunnableLambda(format_input)
            | MULTI_QUERY_PROMPT_TEMPLATE
            | self.model
            | output_parser
        )

        self.multi_query_case_retriever = MultiQueryRetriever(
            retriever=self.case_retriever, llm_chain=llm_chain
        )

        # 检索数量
        self.search_k = config.CASE_VS_SEARCH_K

    def _retrieve_similar_cases(self, query_fact: str) -> List[Tuple[Document, float]]:
        """
        使用 Multi-Query 生成多角度查询，再用 similarity_search_with_score 检索并去重。
        返回 (Document, score) 列表，score 越小越相似（L2距离）。
        """
        # 1. 用 Multi-Query 生成多个查询变体
        try:
            queries = self.multi_query_case_retriever.llm_chain.invoke(query_fact)
        except Exception:
            queries = []

        # 加上原始查询
        all_queries = [query_fact] + (queries if queries else [])

        # 2. 对每个查询执行 similarity_search_with_score
        seen_ids = set()
        results: List[Tuple[Document, float]] = []

        for q in all_queries:
            docs_with_scores = self.case_vs.similarity_search_with_score(q, k=self.search_k)
            for doc, score in docs_with_scores:
                doc_id = doc.page_content[:100]
                if doc_id not in seen_ids:
                    seen_ids.add(doc_id)
                    results.append((doc, score))

        # 按相似度排序（L2距离越小越相似）
        results.sort(key=lambda x: x[1])
        return results[:self.search_k]
    
    def _retrieve_law_context(self, query: str) -> str:
        """检索相关法律条文"""
        law_docs = self.law_retriever.invoke(query)
        if not law_docs:
            return "未检索到相关法律条文"
        return "\n\n".join([doc.page_content for doc in law_docs])
    
    def _format_similar_cases(self, cases: List[Tuple[Document, float]]) -> str:
        """格式化相似案例为文本"""
        if not cases:
            return "未找到相似案例"

        formatted = []
        for i, (case, score) in enumerate(cases[:10], 1):
            meta = case.metadata
            imprisonment = meta.get('imprisonment', 0)
            accusation = meta.get('accusation', '') or '未知'

            fact_short = case.page_content[:200]

            keywords = extract_keywords(case.page_content)
            keywords_str = '、'.join(keywords[:3]) if keywords else '无特殊情节'

            similarity_pct = max(0, (1 - score / 2)) * 100

            formatted.append(
                f"案例{i} | {accusation} | 相似度：{similarity_pct:.0f}%\n"
                f"案情：{fact_short}...\n"
                f"量刑情节：{keywords_str}\n"
                f"判决：{imprisonment}个月"
            )

        return "\n\n".join(formatted)

    def _get_similar_cases_data(self, cases: List[Tuple[Document, float]]) -> List[Dict[str, Any]]:
        """获取结构化的相似案例数据（含完整内容）"""
        if not cases:
            return []

        data = []
        for i, (case, score) in enumerate(cases[:10], 1):
            meta = case.metadata
            imprisonment = meta.get('imprisonment', 0)
            accusation = meta.get('accusation', '') or '未知'
            keywords = extract_keywords(case.page_content)
            similarity_pct = max(0, (1 - score / 2)) * 100

            data.append({
                "no": i,
                "title": accusation,
                "body": case.page_content,
                "imprisonment": imprisonment,
                "similarity": round(similarity_pct, 1),
                "badges": [f"相似度：{similarity_pct:.0f}%", f"判决：{imprisonment}个月"] + ([f"量刑情节：{'、'.join(keywords[:3])}"] if keywords else [])
            })
        return data

    def _get_case_statistics(self, cases: List[Tuple[Document, float]]) -> Dict[str, Any]:
        """计算案例统计信息"""
        if not cases:
            return {
                'avg': 0, 'min': 0, 'max': 0, 'count': 0
            }

        imprisonments = [case.metadata.get('imprisonment', 0) for case, _score in cases]

        return {
            'avg': sum(imprisonments) / len(imprisonments),
            'min': min(imprisonments),
            'max': max(imprisonments),
            'count': len(imprisonments)
        }
    
    def _extract_predicted_imprisonment(self, ai_response: str) -> Optional[int]:
        """从AI响应中提取预测的刑期（月）"""
        patterns = [
            r'预测刑期[：:]\s*(\d+)\s*个?月\s*[（(]',
            r'[•·●]\s*预测刑期[：:]\s*(\d+)\s*个?月',
            r'预测刑期[：:]\s*(\d+)\s*个?月',
            r'预测刑期[：:]\s*(\d+)\s*月',
            r'建议刑期[：:]\s*(\d+)\s*个?月',
            r'量刑建议[：:]\s*(\d+)\s*个?月',
            r'判处[有期徒刑]*\s*(\d+)\s*个?月',
            r'应判处?\s*(\d+)\s*个?月',
            r'刑期[：:]\s*(\d+)\s*个?月',
            r'有期徒刑\s*(\d+)\s*个?月',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, ai_response)
            if match:
                months = int(match.group(1))
                if 0 <= months <= 600:
                    return months
        
        # 兜底方案
        fallback_pattern = r'(?:预测|建议|判处|刑期).*?(\d+)\s*个?月'
        match = re.search(fallback_pattern, ai_response, re.DOTALL)
        if match:
            months = int(match.group(1))
            if 0 <= months <= 600:
                return months
        
        return None
    
    def predict_imprisonment(
        self,
        query_fact: str,
        accusations: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        预测刑期

        Args:
            query_fact: 案情描述
            accusations: 已知罪名列表（可选）

        Returns:
            包含预测结果的字典
        """
        print("\n正在进行刑期预测...")

        # 1. Multi-Query 检索相似案例（带相似度分数）
        similar_cases = self._retrieve_similar_cases(query_fact)
        if not similar_cases:
            return {"error": "未找到相似案例", "prediction": None}

        print(f"✓ 已检索到 {len(similar_cases)} 个相似案例（Multi-Query + 相似度评分）")

        # 2. 获取加权案例统计
        stats = self._get_case_statistics(similar_cases)

        # 3. 获取相关法律条文
        law_context = ""
        if accusations and self.crime_to_articles:
            articles = find_relevant_law_articles(accusations[0], self.crime_to_articles)
            law_context = format_law_articles(articles)

        if not law_context or law_context == "未找到直接相关的刑法条文":
            law_context = self._retrieve_law_context(query_fact)

        # 4. 格式化相似案例
        similar_cases_text = self._format_similar_cases(similar_cases)
        similar_cases_data = self._get_similar_cases_data(similar_cases)

        # 5. 使用 with_structured_output 强制结构化输出
        prompt_input = {
            "query_fact": query_fact,
            "law_context": law_context,
            "num_cases": stats['count'],
            "min_imprisonment": stats['min'],
            "max_imprisonment": stats['max'],
            "avg_imprisonment": stats['avg'],
            "similar_cases_text": similar_cases_text
        }

        structured_model = self.model.with_structured_output(ImprisonmentPrediction)
        chain = IMPRISONMENT_PREDICTION_PROMPT | structured_model
        prediction: ImprisonmentPrediction = chain.invoke(prompt_input)

        # 6. 构建 AI 响应文本（兼容前端展示）
        ai_response = (
            f"罪名：{prediction.crime}\n"
            f"法定刑：{prediction.statutory_range}\n"
            f"从轻情节：{'、'.join(prediction.mitigating_factors) if prediction.mitigating_factors else '无'}\n"
            f"从重情节：{'、'.join(prediction.aggravating_factors) if prediction.aggravating_factors else '无'}\n"
            f"参考刑期范围：{prediction.reference_range_min}-{prediction.reference_range_max}个月\n"
            f"参考案例分析：{prediction.reference_analysis}\n"
            f"预测刑期：{prediction.predicted_months}个月\n"
            f"理由：{prediction.reasoning}"
        )

        predicted = prediction.predicted_months

        return {
            "query_fact": query_fact,
            "similar_cases_count": len(similar_cases),
            "case_statistics": stats,
            "law_context": law_context,
            "similar_cases_text": similar_cases_text,
            "similar_cases_data": similar_cases_data,
            "ai_response": ai_response,
            "predicted_imprisonment": predicted,
            "predicted_years": predicted // 12 if predicted else None,
            "predicted_months": predicted % 12 if predicted else None,
            "structured_prediction": prediction.model_dump(),
        }
    
    def predict_accusation(self, query_fact: str) -> Dict[str, Any]:
        """
        预测罪名

        Args:
            query_fact: 案情描述

        Returns:
            包含预测结果的字典
        """
        print("\n正在进行罪名预测...")

        # 1. 检索相似案例
        similar_cases = self._retrieve_similar_cases(query_fact)
        similar_cases_text = self._format_similar_cases(similar_cases)
        similar_cases_data = self._get_similar_cases_data(similar_cases)

        # 2. 统计相似案例的罪名分布
        accusation_counter = Counter()
        for case, _score in similar_cases:
            accusation_str = case.metadata.get('accusation', '')
            if accusation_str:
                accusations = re.split(r'、(?![^[]*\])', accusation_str)
                for acc in accusations:
                    if acc.strip():
                        accusation_counter[acc.strip()] += 1

        # 格式化罪名统计
        accusation_stats = "\n".join([
            f"- {acc}: {count}个案例"
            for acc, count in accusation_counter.most_common(5)
        ])

        # 3. 获取相关法律条文
        law_context = self._retrieve_law_context(query_fact)

        # 4. 调用LLM预测
        prompt_input = {
            "query_fact": query_fact,
            "law_context": law_context,
            "accusation_stats": accusation_stats if accusation_stats else "无参考案例"
        }

        chain = ACCUSATION_PREDICTION_PROMPT | self.model | StrOutputParser()
        ai_response = chain.invoke(prompt_input)

        return {
            "query_fact": query_fact,
            "similar_cases_count": len(similar_cases),
            "accusation_distribution": dict(accusation_counter),
            "law_context": law_context,
            "similar_cases_text": similar_cases_text,
            "similar_cases_data": similar_cases_data,
            "ai_response": ai_response
        }

    def analyze_case(self, query_fact: str) -> Dict[str, Any]:
        """
        综合分析案件

        Args:
            query_fact: 案情描述

        Returns:
            包含分析结果的字典
        """
        print("\n正在进行案件综合分析...")

        # 1. 检索相似案例
        similar_cases = self._retrieve_similar_cases(query_fact)
        similar_cases_text = self._format_similar_cases(similar_cases)
        similar_cases_data = self._get_similar_cases_data(similar_cases)

        # 2. 获取相关法律条文
        law_context = self._retrieve_law_context(query_fact)

        # 3. 调用LLM分析
        prompt_input = {
            "query_fact": query_fact,
            "law_context": law_context,
            "similar_cases_text": similar_cases_text
        }

        chain = CASE_ANALYSIS_PROMPT | self.model | StrOutputParser()
        ai_response = chain.invoke(prompt_input)

        # 4. 用结构化输出让AI预测罪名和刑期区间（参考案例）
        summary_prompt = PromptTemplate(
            template="""你是资深刑事法官。基于以下案情、分析结果和相似判例，给出精确的罪名推测和刑期区间预测。

【重要要求】
- 刑期区间不要简单取相似案例的最小值和最大值
- 应根据本案的具体情节（从轻/从重因素），在相似案例的量刑范围内给出更精确、更窄的区间
- 区间上下限之差通常不超过相似案例范围的50%

【案情描述】
{query_fact}

【AI分析结果】
{ai_response}

【相似判例参考】
{similar_cases_text}

请输出结构化结果。""",
            input_variables=["query_fact", "ai_response", "similar_cases_text"]
        )

        structured_model = self.model.with_structured_output(CaseAnalysisSummary)
        summary_chain = summary_prompt | structured_model
        summary: CaseAnalysisSummary = summary_chain.invoke({
            "query_fact": query_fact,
            "ai_response": ai_response,
            "similar_cases_text": similar_cases_text
        })

        return {
            "query_fact": query_fact,
            "similar_cases_count": len(similar_cases),
            "case_statistics": {
                "min": summary.sentence_range_min,
                "max": summary.sentence_range_max
            },
            "predicted_accusation": summary.predicted_accusation,
            "law_context": law_context,
            "similar_cases_text": similar_cases_text,
            "similar_cases_data": similar_cases_data,
            "ai_response": ai_response,
            "predicted_imprisonment": None
        }


def get_case_prediction_chain(config: Any) -> CasePredictionChain:
    """
    获取案情预测链实例
    
    Args:
        config: 配置对象
        
    Returns:
        CasePredictionChain实例
    """
    return CasePredictionChain(config)

