"""
智法AI - Flask后端服务主入口

提供以下API接口：
- /api/qa: 法律问答
- /api/contract-review: 合同审查
- /api/case/imprisonment: 刑期预测
- /api/case/accusation: 罪名预测
- /api/case/analysis: 案情综合分析
"""

from flask import Flask, render_template
from flask_cors import CORS
from dotenv import load_dotenv
import traceback
import threading

# 加载环境变量
load_dotenv()

from .config.config import config
from .chain.legal_question_answering import get_law_chain
from .chain.contract_review import get_contract_review_chain
from .chain.case_prediction import get_case_prediction_chain
from .core.cache_manager import start_cleanup_task
from .core.preload_cache import preload_all_caches
from .utils.file_converter import get_paddle_pipeline, PDF_OCR_MODE

# 导入API路由注册函数
from .api.qa import register_qa_routes
from .api.contract import register_contract_routes
from .api.case import register_case_routes
from .api.law import register_law_routes
from .api.settings import register_settings_routes
from .api.health import register_health_routes

# ==================== 创建Flask应用 ====================
app = Flask(__name__, template_folder='../templates', static_folder='../static')
CORS(app)


# ==================== 初始化各功能链 ====================
print("\n" + "="*60)
print("正在初始化智法AI服务（支持热更新）...")
print("="*60)

# 打印当前使用的配置
print(f"\n[系统配置]")
print(f"  • LLM模型: {config.get_llm_model()}")
print(f"  • 温度参数: {config.get_temperature()}")
print(f"  • 最大输出Token: {config.get_max_tokens()}")
print(f"  • Embedding模型: {config.get_embedding_model()}")
print(f"  • API密钥: {'已配置' if config.get_api_key() else '未配置'}")
print()


# ==================== 热更新机制：缓存配置和 Chain ====================

# 缓存配置和 chain 实例
_cached_config = None
_cached_law_chain = None
_cached_contract_chain = None
_cached_case_chain = None


def get_current_config():
    """获取当前配置的快照（用于比较是否发生变化）"""
    return {
        'llm_model': config.get_llm_model(),
        'temperature': config.get_temperature(),
        'max_tokens': config.get_max_tokens(),
        'embedding_model': config.get_embedding_model(),
        'api_key': config.get_api_key()  # API Key 变化也需要重新创建
    }


def get_or_refresh_law_chain():
    """获取或刷新法律问答链（支持热更新）

    返回包含以下键的字典：
    - full_chain: 完整的非流式 chain（向后兼容）
    - retrieval_chain: Stage 1+2 检索链
    - stream_answer: 流式答案生成器函数
    """
    global _cached_config, _cached_law_chain

    current_config = get_current_config()

    # 如果配置发生变化或 chain 未初始化，重新创建
    if _cached_config != current_config or _cached_law_chain is None:
        print(f"\n{'='*60}")
        print(f"[热更新] 检测到配置变化，重新创建法律问答链...")
        if _cached_config:
            print(f"  旧配置: LLM={_cached_config['llm_model']}, T={_cached_config['temperature']}, Embed={_cached_config['embedding_model']}")
        print(f"  新配置: LLM={current_config['llm_model']}, T={current_config['temperature']}, Embed={current_config['embedding_model']}")

        try:
            _cached_law_chain = get_law_chain(config)
            _cached_config = current_config
            print(f"✓ 法律问答链已更新")
        except Exception as e:
            print(f"⚠ 法律问答链更新失败: {e}")
            traceback.print_exc()
            _cached_law_chain = None

        print(f"{'='*60}\n")

    return _cached_law_chain


def get_or_refresh_contract_chain():
    """获取或刷新合同审查链（支持热更新）"""
    global _cached_config, _cached_contract_chain
    
    current_config = get_current_config()
    
    # 如果配置发生变化或 chain 未初始化，重新创建
    if _cached_config != current_config or _cached_contract_chain is None:
        print(f"\n{'='*60}")
        print(f"[热更新] 检测到配置变化，重新创建合同审查链...")
        if _cached_config:
            print(f"  旧配置: LLM={_cached_config['llm_model']}, T={_cached_config['temperature']}, Embed={_cached_config['embedding_model']}")
        print(f"  新配置: LLM={current_config['llm_model']}, T={current_config['temperature']}, Embed={current_config['embedding_model']}")
        
        try:
            _cached_contract_chain = get_contract_review_chain(config)
            _cached_config = current_config
            print(f"✓ 合同审查链已更新")
        except Exception as e:
            print(f"⚠ 合同审查链更新失败: {e}")
            traceback.print_exc()
            _cached_contract_chain = None
        
        print(f"{'='*60}\n")
    
    return _cached_contract_chain


def get_or_refresh_case_chain():
    """获取或刷新案情预测链（支持热更新）"""
    global _cached_config, _cached_case_chain
    
    current_config = get_current_config()
    
    # 如果配置发生变化或 chain 未初始化，重新创建
    if _cached_config != current_config or _cached_case_chain is None:
        print(f"\n{'='*60}")
        print(f"[热更新] 检测到配置变化，重新创建案情预测链...")
        if _cached_config:
            print(f"  旧配置: LLM={_cached_config['llm_model']}, T={_cached_config['temperature']}, Embed={_cached_config['embedding_model']}")
        print(f"  新配置: LLM={current_config['llm_model']}, T={current_config['temperature']}, Embed={current_config['embedding_model']}")
        
        try:
            _cached_case_chain = get_case_prediction_chain(config)
            _cached_config = current_config
            print(f"✓ 案情预测链已更新")
        except Exception as e:
            print(f"⚠ 案情预测链更新失败: {e}")
            traceback.print_exc()
            _cached_case_chain = None
        
        print(f"{'='*60}\n")
    
    return _cached_case_chain


# ==================== 初始化所有 chain ====================
print("正在初始化所有功能链...")
try:
    get_or_refresh_law_chain()
    print("✓ 法律问答链初始化成功")
except Exception as e:
    print(f"⚠ 法律问答链初始化失败: {e}")

try:
    get_or_refresh_contract_chain()
    print("✓ 合同审查链初始化成功")
except Exception as e:
    print(f"⚠ 合同审查链初始化失败: {e}")

try:
    get_or_refresh_case_chain()
    print("✓ 案情预测链初始化成功")
except Exception as e:
    print(f"⚠ 案情预测链初始化失败: {e}")


# ==================== 初始化 PaddleOCR Pipeline ====================
if PDF_OCR_MODE == "local":
    print("正在初始化 PaddleOCR Pipeline (GPU, 本地模式)...")
    try:
        # 在主线程初始化，避免在 Flask 线程中初始化导致 CUDA 上下文错误或崩溃
        get_paddle_pipeline()
        print("✓ PaddleOCR Pipeline 初始化成功")
    except Exception as e:
        print(f"⚠ PaddleOCR Pipeline 初始化失败: {e}")
        traceback.print_exc()
else:
    print(f"✓ PaddleOCR 使用 API 模式 (模型: {PDF_OCR_MODE})")


# ==================== 启动缓存管理器 ====================
# 启动缓存管理器的后台清理任务
start_cleanup_task(interval=300)  # 每5分钟清理一次过期缓存

# 预加载热门数据到缓存（异步执行，不阻塞服务启动）
def async_preload():
    try:
        preload_all_caches()
    except Exception as e:
        print(f"⚠ 缓存预加载失败: {e}")

preload_thread = threading.Thread(target=async_preload, daemon=True)
preload_thread.start()


print("\n" + "="*60)
print("✓ 智法AI服务初始化完成！")
print("ℹ️  系统支持热更新：修改配置后无需重启，下次调用自动应用")
print("ℹ️  缓存系统已启用：大幅提升数据加载速度")
print("ℹ️  后台正在预热缓存：首次访问将更加快速")
print("="*60 + "\n")


# ==================== 注册路由 ====================

@app.route('/')
def index():
    """主页"""
    return render_template('index.html')


# 注册所有API路由
register_qa_routes(app, get_or_refresh_law_chain, get_or_refresh_contract_chain)
register_contract_routes(app, get_or_refresh_contract_chain)
register_case_routes(app, get_or_refresh_case_chain)
register_law_routes(app)
register_settings_routes(app, config)
register_health_routes(app)


# ==================== 启动服务 ====================

def run_app():
    """启动应用"""
    print("\n" + "="*50)
    print("智法AI 法律智能助手")
    print("访问地址: http://localhost:5000")
    print("="*50 + "\n")
    
    app.run(
        host='0.0.0.0',
        port=5000,
        debug=True,
        use_reloader=False
    )


if __name__ == '__main__':
    run_app()

