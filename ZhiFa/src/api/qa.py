"""
法律问答API模块
"""
from flask import request, jsonify, Response, stream_with_context
import traceback
import json

from ..core.cache_manager import increment_stat


def register_qa_routes(app, get_or_refresh_law_chain, get_or_refresh_contract_chain):
    """注册法律问答相关路由"""

    @app.route('/api/qa', methods=['POST'])
    def legal_qa():
        """
        法律问答API（非流式，向后兼容）

        请求体:
        {
            "question": "法律问题",
            "history": [{"role": "user/assistant", "content": "消息内容"}]  // 可选
        }

        返回:
        {
            "answer": "AI回答",
            "sources": [{"title": "来源", "content": "内容"}]
        }
        """
        try:
            data = request.get_json()
            question = data.get('question', '')
            history = data.get('history', [])  # 获取对话历史

            if not question:
                return jsonify({"error": "请提供问题"}), 400

            # 获取最新的 chain（支持热更新）
            chain_bundle = get_or_refresh_law_chain()

            if chain_bundle is None:
                return jsonify({"error": "法律问答服务未初始化"}), 500

            law_chain = chain_bundle["full_chain"]

            # 调用法律问答链（传递对话历史）
            result = law_chain.invoke({
                "question": question,
                "history": history
            })

            # 提取答案和来源
            answer = result.get("answer", "")

            # 格式化来源信息
            sources = []
            if result.get("law_docs_formatted"):
                for doc in result["law_docs_formatted"][:5]:
                    sources.append({
                        "title": doc.get("source", "法律条文"),
                        "chapter": doc.get("chapter", ""),
                        "content": doc.get("content", "")[:200]
                    })
            if result.get("web_docs_formatted"):
                for doc in result["web_docs_formatted"][:3]:
                    sources.append({
                        "title": doc.get("title", "网页来源"),
                        "url": doc.get("url", ""),
                        "content": doc.get("content", "")[:200]
                    })

            # 更新使用统计
            increment_stat('qa_count')

            return jsonify({
                "answer": answer,
                "sources": sources
            })

        except Exception as e:
            traceback.print_exc()
            return jsonify({"error": str(e)}), 500

    @app.route('/api/qa/stream', methods=['POST'])
    def legal_qa_stream():
        """
        法律问答API（流式输出，SSE）

        Stage 1-2（检索+上下文构建）同步执行后，
        Stage 3（答案生成）通过 SSE 逐 chunk 推送给前端。

        请求体:
        {
            "question": "法律问题",
            "history": [{"role": "user/assistant", "content": "消息内容"}]  // 可选
        }

        SSE 事件格式:
        - data: {"type": "sources", "sources": [...]}    // 检索来源
        - data: {"type": "chunk", "content": "..."}      // 答案片段
        - data: {"type": "done"}                         // 结束标记
        - data: {"type": "error", "message": "..."}      // 错误
        """
        try:
            data = request.get_json()
            question = data.get('question', '')
            history = data.get('history', [])

            if not question:
                return jsonify({"error": "请提供问题"}), 400

            # 获取最新的 chain 组件
            chain_bundle = get_or_refresh_law_chain()

            if chain_bundle is None:
                return jsonify({"error": "法律问答服务未初始化"}), 500

            retrieval_chain = chain_bundle["retrieval_chain"]
            stream_answer_fn = chain_bundle["stream_answer"]

            def generate():
                try:
                    # Stage 1+2：同步执行检索和上下文构建
                    context = retrieval_chain.invoke({
                        "question": question,
                        "history": history
                    })

                    # 格式化来源信息并推送
                    sources = []
                    if context.get("law_docs_formatted"):
                        for doc in context["law_docs_formatted"][:5]:
                            sources.append({
                                "title": doc.get("source", "法律条文"),
                                "chapter": doc.get("chapter", ""),
                                "content": doc.get("content", "")[:200]
                            })
                    if context.get("web_docs_formatted"):
                        for doc in context["web_docs_formatted"][:3]:
                            sources.append({
                                "title": doc.get("title", "网页来源"),
                                "url": doc.get("url", ""),
                                "content": doc.get("content", "")[:200]
                            })

                    yield f"data: {json.dumps({'type': 'sources', 'sources': sources}, ensure_ascii=False)}\n\n"

                    # Stage 3：流式生成答案
                    for chunk in stream_answer_fn(context):
                        yield f"data: {json.dumps({'type': 'chunk', 'content': chunk}, ensure_ascii=False)}\n\n"

                    # 发送结束标记
                    yield f"data: {json.dumps({'type': 'done'})}\n\n"

                    # 更新使用统计
                    increment_stat('qa_count')

                except Exception as e:
                    traceback.print_exc()
                    yield f"data: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"

            return Response(
                stream_with_context(generate()),
                mimetype='text/event-stream',
                headers={
                    'Cache-Control': 'no-cache',
                    'X-Accel-Buffering': 'no',
                    'Connection': 'keep-alive'
                }
            )

        except Exception as e:
            traceback.print_exc()
            return jsonify({"error": str(e)}), 500
    
    
    @app.route('/api/rewrite', methods=['POST'])
    def rewrite_contract():
        """
        合同自动重写API（基于法律审查）
        
        请求体:
        {
            "original": "原始合同文本"
        }
        
        返回:
        {
            "rewritten": "修改后的合同",
            "references": [{"title": "法条", "content": "内容"}]
        }
        """
        try:
            data = request.get_json()
            original = data.get('original', '')
            
            if not original:
                return jsonify({"error": "请提供原始文本"}), 400
            
            # 获取最新的 chain（支持热更新）
            contract_chain = get_or_refresh_contract_chain()
            
            if contract_chain is None:
                return jsonify({"error": "合同审查服务未初始化"}), 500
            
            # 调用合同审查链
            result = contract_chain.invoke({"contract_text": original})
            
            # 拼接修改后的文本
            clauses = result.get("clauses_analysis", [])
            rewritten_parts = []
            references = []
            
            for clause in clauses:
                if clause.get('revised_text'):
                    rewritten_parts.append(clause['revised_text'])
                else:
                    rewritten_parts.append(clause.get('clause_text', ''))
                
                # 收集法律依据
                if clause.get('evidence'):
                    for ev in clause['evidence'][:2]:
                        references.append({
                            "title": ev.get('source', '法律条文'),
                            "content": ev.get('content', '')[:150],
                            "url": "#"
                        })
            
            return jsonify({
                "rewritten": "\n\n".join(rewritten_parts),
                "references": references[:5]  # 最多返回5条参考
            })
            
        except Exception as e:
            traceback.print_exc()
            return jsonify({"error": str(e)}), 500
    
    
    @app.route('/api/compare', methods=['POST'])
    def compare_contracts():
        """
        合同对比API（生成红线对比）
        
        请求体:
        {
            "original": "原始文本",
            "revised": "修改后文本"
        }
        
        返回:
        {
            "diffs": [{"op": "equal/insert/delete", "text": "...", "reason": "..."}]
        }
        """
        try:
            data = request.get_json()
            original = data.get('original', '')
            revised = data.get('revised', '')
            
            if not original or not revised:
                return jsonify({"error": "请提供原始和修改后的文本"}), 400
            
            # 使用difflib进行简单对比
            import difflib
            
            differ = difflib.SequenceMatcher(None, original, revised)
            diffs = []
            
            for tag, i1, i2, j1, j2 in differ.get_opcodes():
                if tag == 'equal':
                    diffs.append({
                        "op": "equal",
                        "text": original[i1:i2]
                    })
                elif tag == 'delete':
                    diffs.append({
                        "op": "delete",
                        "text": original[i1:i2],
                        "reason": "此内容已被删除"
                    })
                elif tag == 'insert':
                    diffs.append({
                        "op": "insert",
                        "text": revised[j1:j2],
                        "reason": "此为新增内容"
                    })
                elif tag == 'replace':
                    diffs.append({
                        "op": "delete",
                        "text": original[i1:i2],
                        "reason": "此内容已被替换"
                    })
                    diffs.append({
                        "op": "insert",
                        "text": revised[j1:j2],
                        "reason": "替换为此内容"
                    })
            
            return jsonify({"diffs": diffs})
            
        except Exception as e:
            traceback.print_exc()
            return jsonify({"error": str(e)}), 500

