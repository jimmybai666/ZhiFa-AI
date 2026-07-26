"""
健康检查API模块
"""
from flask import jsonify


def register_health_routes(app):
    """注册健康检查相关路由"""
    
    @app.route('/health')
    def health_check():
        """健康检查接口"""
        from ..app import _cached_law_chain, _cached_contract_chain, _cached_case_chain
        
        return jsonify({
            "status": "ok",
            "services": {
                "law_qa": _cached_law_chain is not None,
                "contract_review": _cached_contract_chain is not None,
                "case_prediction": _cached_case_chain is not None
            }
        })

