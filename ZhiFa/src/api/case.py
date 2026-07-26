"""
案情分析API模块
"""
from flask import request, jsonify, send_file, after_this_request
import traceback
import os
import uuid
import shutil
from datetime import datetime

from ..core.cache_manager import increment_stat
from ..utils.export_utils import generate_pdf_report


def register_case_routes(app, get_or_refresh_case_chain):
    """注册案情分析相关路由"""
    
    @app.route('/api/case/imprisonment', methods=['POST'])
    def predict_imprisonment():
        """
        刑期预测API
        
        请求体:
        {
            "query_fact": "案情描述",
            "accusations": ["罪名"] (可选)
        }
        
        返回:
        {
            "predicted_imprisonment": 36,
            "similar_cases_count": 10,
            "case_statistics": {...},
            "ai_response": "分析结果",
            "law_context": "相关法条"
        }
        """
        try:
            data = request.get_json()
            query_fact = data.get('query_fact', '')
            accusations = data.get('accusations', None)
            
            if not query_fact:
                return jsonify({"error": "请提供案情描述"}), 400
            
            # 获取最新的 chain（支持热更新）
            case_chain = get_or_refresh_case_chain()
            
            if case_chain is None:
                return jsonify({"error": "案情预测服务未初始化"}), 500
            
            # 调用刑期预测
            result = case_chain.predict_imprisonment(query_fact, accusations)
            
            return jsonify(result)
            
        except Exception as e:
            traceback.print_exc()
            return jsonify({"error": str(e)}), 500
    
    
    @app.route('/api/case/accusation', methods=['POST'])
    def predict_accusation():
        """
        罪名预测API
        
        请求体:
        {
            "query_fact": "案情描述"
        }
        
        返回:
        {
            "accusation_distribution": {...},
            "ai_response": "分析结果",
            "law_context": "相关法条"
        }
        """
        try:
            data = request.get_json()
            query_fact = data.get('query_fact', '')
            
            if not query_fact:
                return jsonify({"error": "请提供案情描述"}), 400
            
            # 获取最新的 chain（支持热更新）
            case_chain = get_or_refresh_case_chain()
            
            if case_chain is None:
                return jsonify({"error": "案情预测服务未初始化"}), 500
            
            # 调用罪名预测
            result = case_chain.predict_accusation(query_fact)
            
            return jsonify(result)
            
        except Exception as e:
            traceback.print_exc()
            return jsonify({"error": str(e)}), 500
    
    
    @app.route('/api/case/analysis', methods=['POST'])
    def analyze_case():
        """
        案情综合分析API
        
        请求体:
        {
            "query_fact": "案情描述"
        }
        
        返回:
        {
            "ai_response": "综合分析结果",
            "similar_cases_count": 10,
            "law_context": "相关法条"
        }
        """
        try:
            data = request.get_json()
            query_fact = data.get('query_fact', '')
            
            if not query_fact:
                return jsonify({"error": "请提供案情描述"}), 400
            
            # 获取最新的 chain（支持热更新）
            case_chain = get_or_refresh_case_chain()
            
            if case_chain is None:
                return jsonify({"error": "案情预测服务未初始化"}), 500
            
            # 调用综合分析
            result = case_chain.analyze_case(query_fact)
            
            # 更新使用统计
            increment_stat('case_count')
            
            return jsonify(result)
            
        except Exception as e:
            traceback.print_exc()
            return jsonify({"error": str(e)}), 500

    @app.route('/api/case/export-pdf', methods=['POST'])
    def export_case_pdf():
        """
        导出案情分析报告 PDF（后端生成，避免浏览器打印页脚出现URL/乱码）

        请求体:
        {
            "case_fact": "...",
            "predicted_imprisonment": 36,
            "similar_cases_count": 10,
            "case_statistics": {"min": 1, "max": 36},
            "ai_response": "...",
            "law_context": "...",
            "similar_cases_text": "..."
        }
        """
        base_temp_dir = None
        try:
            data = request.get_json(silent=True) or {}
            case_fact = (data.get("case_fact") or "").strip()
            ai_response = (data.get("ai_response") or "").strip()
            law_context = (data.get("law_context") or "").strip()
            case_reference = (data.get("similar_cases_text") or "").strip()
            predicted_accusation = (data.get("predicted_accusation") or "").strip()
            case_statistics = data.get("case_statistics") or {}

            if not case_fact:
                return jsonify({"error": "缺少 case_fact"}), 400

            # 生成报告 Markdown
            today = datetime.now().strftime("%Y-%m-%d")
            min_v = case_statistics.get("min", None)
            max_v = case_statistics.get("max", None)

            def _fmt(v):
                try:
                    if v is None or v == "":
                        return "--"
                    return str(int(round(float(v))))
                except Exception:
                    return str(v)

            stats_range = "--"
            if min_v is not None and max_v is not None:
                stats_range = f"{_fmt(min_v)}-{_fmt(max_v)} 个月"

            md = f"""# 智能案情分析报告

生成日期：{today}

## 核心指标
- **罪名推测**：{predicted_accusation if predicted_accusation else '--'}
- **刑期区间**：{stats_range}

## 案情描述
{case_fact}

## 案情分析
{ai_response if ai_response else "（无）"}
"""

            if case_reference:
                md += f"""

## 相关案例分析
{case_reference}
"""

            if law_context:
                md += f"""

## 相关法律条文
{law_context}
"""

            md += """

---
本报告由智法AI智能分析系统生成，仅供参考。
如需法律建议，请咨询专业律师。
"""

            # 写入临时目录并生成 PDF
            session_id = str(uuid.uuid4())
            base_temp_dir = os.path.join(os.getcwd(), "storage", "temp_uploads", session_id)
            os.makedirs(base_temp_dir, exist_ok=True)
            pdf_path = os.path.join(base_temp_dir, f"案情分析报告_{today}.pdf")

            ok = generate_pdf_report(md, pdf_path)
            if not ok or not os.path.exists(pdf_path):
                return jsonify({"error": "PDF生成失败"}), 500

            @after_this_request
            def remove_temp_dir(response):
                try:
                    if base_temp_dir and os.path.isdir(base_temp_dir):
                        shutil.rmtree(base_temp_dir)
                except Exception as cleanup_err:
                    print(f"Error removing temp dir: {cleanup_err}")
                return response

            return send_file(
                pdf_path,
                as_attachment=True,
                download_name=os.path.basename(pdf_path),
                mimetype="application/pdf",
            )

        except Exception as e:
            traceback.print_exc()
            # 尽力清理
            try:
                if base_temp_dir and os.path.isdir(base_temp_dir):
                    shutil.rmtree(base_temp_dir)
            except Exception:
                pass
            return jsonify({"error": str(e)}), 500

