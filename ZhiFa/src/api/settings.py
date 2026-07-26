"""
系统设置API模块
"""
from flask import request, jsonify
import traceback
import json
from pathlib import Path

from ..config.config import Config
from ..vectorstore.utils import get_vectorstore
from ..core.cache_manager import load_settings_file, save_settings_file, load_stats_file


def register_settings_routes(app, config):
    """注册系统设置相关路由"""
    
    @app.route('/api/settings/status')
    def get_system_status():
        """获取系统状态"""
        try:
            # 获取当前使用的模型配置
            current_model = Config.get_llm_model()
            current_temp = Config.get_temperature()
            current_max_tokens = Config.get_max_tokens()
            api_key = Config.get_api_key()
            
            # 检查API密钥是否配置
            api_connected = bool(api_key and len(api_key) > 10)
            
            # 检查LLM是否可用（使用缓存的chain变量）
            from ..app import _cached_law_chain
            llm_loaded = _cached_law_chain is not None
            
            # 检查向量库连接（检查案例库和法律库）
            vectordb_connected = False
            vectordb_details = {}
            try:
                # 检查刑事案例向量库
                case_vs = get_vectorstore("criminal_cases")
                case_count = case_vs._collection.count() if case_vs else 0
                vectordb_details['case'] = {'connected': True, 'count': case_count}
                
                # 检查法律法规向量库
                law_vs = get_vectorstore("law")
                law_count = law_vs._collection.count() if law_vs else 0
                vectordb_details['law'] = {'connected': True, 'count': law_count}
                
                # 只要有一个库有数据就认为连接正常
                vectordb_connected = case_count > 0 or law_count > 0
            except Exception as e:
                print(f"向量库检测失败: {e}")
                vectordb_details['error'] = str(e)
            
            # 获取使用统计
            stats = load_stats_file()
            
            return jsonify({
                "success": True,
                "api_connected": api_connected,
                "llm_loaded": llm_loaded,
                "vectordb_connected": vectordb_connected,
                "stats": stats,
                "current_config": {
                    "model": current_model,
                    "temperature": current_temp,
                    "max_tokens": current_max_tokens
                }
            })
        except Exception as e:
            return jsonify({
                "success": False,
                "error": str(e),
                "api_connected": False,
                "llm_loaded": False,
                "vectordb_connected": False,
                "stats": {'qa_count': 0, 'contract_count': 0, 'case_count': 0}
            })
    
    
    @app.route('/api/settings/test-connection', methods=['POST'])
    def test_api_connection():
        """测试API连接 - 进行真实的API调用测试"""
        try:
            data = request.get_json()
            api_key = data.get('api_key', '')
            model = data.get('model', Config.DEFAULT_LLM_MODEL)

            if not api_key:
                return jsonify({"success": False, "message": "API密钥不能为空"})

            # 进行真实的API调用测试
            try:
                from langchain_openai import ChatOpenAI

                test_llm = ChatOpenAI(
                    model=model,
                    api_key=api_key,
                    base_url=Config.DEFAULT_BASE_URL,
                    temperature=0.1
                )

                response = test_llm.invoke("你好，请回复'连接成功'")

                if response and hasattr(response, 'content'):
                    return jsonify({
                        "success": True,
                        "message": f"连接成功！模型: {model}",
                        "response": response.content[:50]
                    })
                else:
                    return jsonify({"success": False, "message": "API响应异常"})

            except Exception as api_error:
                error_msg = str(api_error)
                if "InvalidApiKey" in error_msg or "Unauthorized" in error_msg or "401" in error_msg:
                    return jsonify({"success": False, "message": "API密钥无效"})
                elif "quota" in error_msg.lower():
                    return jsonify({"success": False, "message": "API配额不足"})
                else:
                    return jsonify({"success": False, "message": f"连接失败: {error_msg[:100]}"})

        except Exception as e:
            return jsonify({"success": False, "message": str(e)})
    
    
    @app.route('/api/settings/save', methods=['POST'])
    def save_settings():
        """
        保存系统设置 - 支持热更新，无需重启服务
        """
        try:
            data = request.get_json()
            
            # 检查 Embedding 模型是否发生变化
            old_settings = load_settings_file()
            old_embedding = old_settings.get('embedding_model', config.DEFAULT_EMBEDDING_MODEL)
            new_embedding = data.get('embedding_model', config.DEFAULT_EMBEDDING_MODEL)
            embedding_changed = (old_embedding != new_embedding)
            
            # 保存设置到文件
            save_settings_file(data)
            
            # 获取保存的配置信息
            llm_model = data.get('llm_model', Config.DEFAULT_LLM_MODEL)
            embedding_model = data.get('embedding_model', Config.DEFAULT_EMBEDDING_MODEL)
            temperature = data.get('temperature', 0.7)
            max_tokens = data.get('max_tokens', Config.DEFAULT_MAX_TOKENS)
            
            # 打印配置更新信息
            print(f"\n{'='*60}")
            print(f"[配置更新] 系统设置已保存并将在下次调用时生效")
            print(f"  - LLM模型: {llm_model}")
            print(f"  - Embedding模型: {embedding_model}")
            print(f"  - 温度参数: {temperature}")
            print(f"  - 最大输出Token: {max_tokens}")
            if embedding_changed:
                print(f"  ⚠️ Embedding模型已变更: {old_embedding} -> {new_embedding}")
                print(f"  ℹ️  新模型将在下次向量检索时自动应用（支持热更新）")
            print(f"{'='*60}\n")
            
            # 构建返回消息
            if embedding_changed:
                message = (
                    f"✓ 设置已保存成功！所有配置支持热更新。\n\n"
                    f"配置信息：\n"
                    f"  • LLM模型: {llm_model} ✓ (立即生效)\n"
                    f"  • 温度参数: {temperature} ✓ (立即生效)\n"
                    f"  • 最大输出Token: {max_tokens} ✓ (立即生效)\n"
                    f"  • Embedding模型: {embedding_model} ✓ (立即生效)\n\n"
                    f"ℹ️ 检测到 Embedding 模型变更，新模型将在下次向量检索时自动应用。\n"
                    f"   不同的 embedding 模型使用独立的缓存空间，不会相互影响。"
                )
            else:
                message = (
                    f"✓ 设置已保存成功！\n\n"
                    f"配置信息：\n"
                    f"  • LLM模型: {llm_model} ✓\n"
                    f"  • 温度参数: {temperature} ✓\n"
                    f"  • 最大输出Token: {max_tokens} ✓\n"
                    f"  • Embedding模型: {embedding_model} ✓\n\n"
                    f"所有新配置将在下次调用时自动生效，无需重启服务。"
                )
            
            return jsonify({
                "success": True, 
                "message": message,
                "embedding_changed": embedding_changed,
                "config": {
                    "llm_model": llm_model,
                    "embedding_model": embedding_model,
                    "temperature": temperature,
                    "max_tokens": max_tokens
                }
            })
        except Exception as e:
            print(f"⚠ 保存设置失败: {e}")
            traceback.print_exc()
            return jsonify({"success": False, "message": f"保存失败: {str(e)}"})
    
    
    @app.route('/api/settings/load')
    def load_settings():
        """加载系统设置"""
        try:
            settings = load_settings_file()
            
            # 返回时隐藏完整API密钥
            if 'api_key' in settings and settings['api_key']:
                key = settings['api_key']
                if len(key) > 8 and '****' not in key:
                    settings['api_key_display'] = key[:4] + '****' + key[-4:]
                    # 前端显示掩码版本，但保留原始值用于后续操作
            
            return jsonify({"success": True, "settings": settings})
        except Exception as e:
            return jsonify({"success": False, "message": str(e)})
    
    
    @app.route('/api/settings/current')
    def get_current_settings():
        """获取当前实际使用的配置（从Config类读取）"""
        try:
            return jsonify({
                "success": True,
                "current": {
                    "llm_model": Config.get_llm_model(),
                    "embedding_model": Config.get_embedding_model(),
                    "temperature": Config.get_temperature(),
                    "max_tokens": Config.get_max_tokens(),
                    "api_key_configured": bool(Config.get_api_key())
                }
            })
        except Exception as e:
            return jsonify({"success": False, "message": str(e)})

