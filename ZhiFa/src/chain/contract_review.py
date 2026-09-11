"""
contract_review_structured.py - 基于结构化拆解的合同审查功能

包含：
- get_contract_review_chain: 结构化合同检测链
- ContractReviewChain: 合同审查链实现
"""

from typing import Any, List, Dict
import re
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from langchain_classic.chains.base import Chain
from ..vectorstore.utils import get_vectorstore
from ..core.model_factory import get_model
from .contract_review_prompt import CONTRACT_STRUCTURE_PROMPT, CONTRACT_CLAUSE_ANALYSIS_PROMPT, CONTRACT_SUMMARY_PROMPT


def compute_redline_diff(original: str, revised: str) -> str:
    """评测场景不需要 HTML redline，返回空字符串"""
    return ""

# 合同检测链 - 分析合同条款的法律风险
def get_contract_review_chain(config: Any) -> Chain:
    """
    创建结构化合同检测链。

    工作流程：
    1. 使用大模型对合同进行结构化拆解（提取条款、主题、层级）
    2. 对每个条款：
       a. 从法律向量库检索相关法律条文
       b. 使用模型分析该条款是否存在法律风险（结合主题信息）
    3. 汇总所有条款的分析结果，生成整体审查报告
    """

    # 加载法律向量库
    law_vs = get_vectorstore(config.LAW_VS_COLLECTION_NAME)
    vs_retriever = law_vs.as_retriever(search_kwargs={"k": 5})  # 每个条款检索5条相关法律

    # 辅助函数：合并法律文档
    def combine_law_docs(docs: List[Any]) -> str:
        return "\n\n".join([d.page_content for d in docs])

    # 定义合同条款分析函数
    def analyze_contract_clause(item: Dict[str, Any]) -> Dict[str, Any]:
        """
        分析单个合同条款（基于结构化后的数据）
        Args:
            item: 包含 content, theme, id 等信息的字典
        Returns:
            包含分析结果的字典
        """
        clause_text = item.get("content", "")
        clause_id = item.get("id", "unknown")
        clause_theme = item.get("theme", "未分类")
        section_path = item.get("section", "")

        # 检索相关法律条文
        # 确保 clause_text 不为空
        if not clause_text:
            clause_text = "（无内容）"
            
        law_docs = vs_retriever.invoke(clause_text)
        law_context = combine_law_docs(law_docs)
        
        # 提取法律文档元数据 (Evidence Panel)
        evidence_list = []
        for doc in law_docs:
            evidence_list.append({
                "content": doc.page_content,
                "source": doc.metadata.get("source", "Unknown"),
                "page": doc.metadata.get("page", 0)
            })

        # 如果没有检索到相关法律，使用默认文本
        if not law_context.strip():
            law_context = "未检索到直接相关的法律条文"

        # 格式化 prompt - 将主题信息注入 Prompt，帮助模型更准确地分析
        structured_clause_text = f"【章节：{section_path}】【主题：{clause_theme}】\n内容：{clause_text}"

        prompt_value = CONTRACT_CLAUSE_ANALYSIS_PROMPT.format_prompt(
            clause=structured_clause_text,
            law_context=law_context
        )

        # 调用模型分析
        model = get_model(streaming=False)  # 不使用流式输出
        analysis_result = model.invoke(prompt_value.to_string())

        # 解析分析结果
        result_content = analysis_result.content if hasattr(analysis_result, 'content') else str(analysis_result)
        
        # 尝试解析 JSON
        try:
            # 清理 Markdown 标记
            clean_json = result_content.strip()
            if clean_json.startswith("```json"):
                clean_json = clean_json[7:]
            elif clean_json.startswith("```"):
                clean_json = clean_json[3:]
            if clean_json.endswith("```"):
                clean_json = clean_json[:-3]
            
            analysis_json = json.loads(clean_json.strip())
            
            # 提取字段
            risk_level = analysis_json.get("risk_level", "未知")
            issue_description = analysis_json.get("issue_description", "")
            legal_basis = analysis_json.get("legal_basis", "")
            suggestion = analysis_json.get("suggestion", "")
            revised_text = analysis_json.get("revised_text", clause_text)
            
            # 计算红线对比 (Redline Comparison)
            diff_html = compute_redline_diff(clause_text, revised_text)
            
            # 组合分析文本供汇总使用
            analysis_text = f"风险等级：{risk_level}\n问题：{issue_description}\n建议：{suggestion}"

        except json.JSONDecodeError:
            # Fallback if JSON parsing fails
            print(f"Warning: Failed to parse JSON for clause {clause_id}. Using raw text.")
            analysis_text = result_content
            risk_level = "解析失败"
            diff_html = clause_text # No diff
            evidence_list = []
            revised_text = clause_text

        return {
            "clause_number": clause_id,
            "clause_text": clause_text,
            "type": item.get("type", "条款"),  # 传递类型字段
            "theme": clause_theme,
            "section": section_path,
            "analysis": analysis_text, # Keep for summary prompt
            "risk_level": risk_level,
            "diff_html": diff_html, # For Redline View
            "revised_text": revised_text,
            "evidence": evidence_list, # For Evidence Panel
            "related_laws": law_context
        }

    # 使用 LLM 进行合同结构化拆解
    def structure_contract_with_llm(contract_text: str) -> List[Dict[str, Any]]:
        """
        使用大模型将合同文本拆解为结构化的 JSON 列表
        """
        # 延迟导入以支持热更新
        from .contract_review_prompt import CONTRACT_STRUCTURE_PROMPT
        
        print("正在使用大模型对合同进行结构化拆解与主题识别...")
        model = get_model(streaming=False)

        prompt = CONTRACT_STRUCTURE_PROMPT.format(contract_text=contract_text)

        try:
            response = model.invoke(prompt)
            content = response.content if hasattr(response, 'content') else str(response)
            
            print("-" * 40)
            print("LLM Structure Response Preview:")
            print(content[:500] + "..." if len(content) > 500 else content)
            print("-" * 40)

            # 清理可能存在的 Markdown 标记
            content = content.strip()
            if content.startswith("```json"):
                content = content[7:]
            elif content.startswith("```"):
                content = content[3:]

            if content.endswith("```"):
                content = content[:-3]

            content = content.strip()

            structured_data = json.loads(content)

            # 清理 content 字段中的 Markdown 标题标记
            for item in structured_data:
                if "content" in item and isinstance(item["content"], str):
                    # 移除行首的 Markdown 标题标记 (如 "## ", "### ")
                    item["content"] = re.sub(r'(?m)^#+\s*', '', item["content"])

            print(f"成功拆解出 {len(structured_data)} 个审查单元。")
            return structured_data

        except Exception as e:
            print(f"结构化拆解失败，回退到默认段落分割。错误: {e}")
            # 回退策略：使用正则分割
            clauses = re.split(r'\n\n+|\n', contract_text)
            return [
                {
                    "id": str(i),
                    "type": "paragraph",
                    "theme": "未分类",
                    "section": "自动分割",
                    "content": c.strip()
                }
                for i, c in enumerate(clauses, 1) if c.strip()
            ]

    # 定义主处理函数
    def process_contract(inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理整个合同
        """
        contract_text = inputs["contract_text"]

        # 1. 结构化拆解 (Summarize & Split)
        clauses_data = structure_contract_with_llm(contract_text)

        # 2. 并发分析每个条款（线程池，max_workers 控制并发数，避免触发 API 速率限制）
        max_workers = 4
        total = len(clauses_data)
        print(f"开始并发分析 {total} 个条款（并发数: {max_workers}）...")
        clauses_analysis = [None] * total

        def _analyze_with_index(index, item):
            import time as _time
            theme_info = item.get('theme', '未分类')
            print(f"  → 开始分析第 {index + 1}/{total} 个条款 [主题: {theme_info}]")
            # 重试机制：遇到 429 时指数退避
            max_retries = 4
            for attempt in range(max_retries):
                try:
                    result = analyze_contract_clause(item)
                    print(f"  ✓ 完成第 {index + 1}/{total} 个条款 [主题: {theme_info}]")
                    return index, result
                except Exception as e:
                    if "429" in str(e) and attempt < max_retries - 1:
                        wait = (attempt + 1) * 5
                        print(f"  ⚠ 第 {index + 1} 条触发速率限制，等待 {wait}s 后重试...")
                        _time.sleep(wait)
                    else:
                        raise

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [
                executor.submit(_analyze_with_index, i, item)
                for i, item in enumerate(clauses_data)
            ]
            for future in as_completed(futures):
                idx, result = future.result()
                clauses_analysis[idx] = result

        # 3. 生成汇总报告
        print("正在生成汇总报告...")
        # 优化汇总输入的格式，包含主题信息
        clauses_text = "\n\n".join([
            f"【条款 {item['clause_number']} - {item['theme']}】\n原文：{item['clause_text']}\n分析：{item['analysis']}"
            for item in clauses_analysis
        ])

        summary_prompt = CONTRACT_SUMMARY_PROMPT.format_prompt(
            clauses_analysis=clauses_text
        )

        model = get_model(streaming=False)
        summary_result = model.invoke(summary_prompt.to_string())
        summary_text = summary_result.content if hasattr(summary_result, 'content') else str(summary_result)

        return {
            "clauses_analysis": clauses_analysis,
            "summary_report": summary_text,
            "total_clauses": len(clauses_data)
        }

    # 创建合同审查链
    class ContractReviewChain(Chain):
        """合同审查链实现"""

        @property
        def input_keys(self) -> List[str]:
            return ["contract_text"]

        @property
        def output_keys(self) -> List[str]:
            return ["clauses_analysis", "summary_report", "total_clauses"]

        def _call(self, inputs: Dict[str, Any], run_manager=None) -> Dict[str, Any]:
            return process_contract(inputs)

    return ContractReviewChain()
