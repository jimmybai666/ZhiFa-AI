import json
import os
from pathlib import Path

class Config:
    # ==================== 法律文档配置 ====================
    LAW_BOOK_PATH = "data/Law-Book"
    LAW_BOOK_CHUNK_SIZE = 100
    LAW_BOOK_CHUNK_OVERLAP = 20

    # ==================== 向量数据库配置 ====================
    LAW_VS_COLLECTION_NAME = "law"
    LAW_VS_SEARCH_K = 3

    WEB_VS_COLLECTION_NAME = "web"
    WEB_VS_SEARCH_K = 20

    # ==================== DuckDuckGo 网页搜索配置 ====================
    # region 会影响结果的语言/地区倾向（例如更偏中文页面、中文标题/摘要）
    WEB_SEARCH_REGION = "cn-zh"
    # safesearch 会提高过滤成人/不适内容的强度，并且通常也会降低一部分低质量站点命中概率
    WEB_SEARCH_SAFESEARCH = "strict"  # strict / moderate / off
    # time 用于限制搜索结果的时间范围：d/w/m/y（天/周/月/年）
    WEB_SEARCH_TIME = "y"

    # ==================== 网页结果优先级（非白名单限制） ====================
    # 只做“优先排序”，也可开启强制白名单（只允许指定站点）
    WEB_SEARCH_REQUIRE_HTTPS = True

    # 强制白名单：True 时，只允许 WEB_SEARCH_ALLOWED_TLDS / WEB_SEARCH_ALLOWED_DOMAINS 命中的链接
    WEB_SEARCH_ENFORCE_WHITELIST = True
    # 允许的域名后缀（含子域名）
    WEB_SEARCH_ALLOWED_TLDS = (
        ".gov.cn",
        ".edu.cn"
    )
    # 允许的域名（含子域名）——用于放行非 .gov.cn 但你信任的站点
    WEB_SEARCH_ALLOWED_DOMAINS = (
        "pkulaw.com",      # 北大法宝
        "chinacourt.org",  # 中国法院网

        # 常见知识平台（非 .gov.cn）：注意这类内容权威性不一
        "baike.baidu.com",   # 百度百科
        "zhihu.com",         # 知乎
        "bilibili.com",      # 哔哩哔哩
        "wikipedia.org",     # 维基百科（含 zh.wikipedia.org 等）
        "tieba.baidu.com",       # 百度贴吧
        "zhidao.baidu.com",      # 百度知道
        "toutiao.com",           # 今日头条
        "ifeng.com",             # 凤凰网
        "sina.com.cn",          # 新浪网
    )
    # 优先域名（含子域名）
    WEB_SEARCH_PREFER_DOMAINS = (
        # 法律数据库/检索平台
        "pkulaw.com",  # 北大法宝

        # 权威机关站点（这些多数也会被 .gov.cn 命中，但单独列出可获得更高优先级）
        "npc.gov.cn",        # 全国人大
        "court.gov.cn",      # 中国裁判文书网/法院系统入口（域名可能用于跳转到具体子站）
        "supremecourt.gov.cn",  # 最高人民法院（常见）
        "moj.gov.cn",        # 司法部
        "chinacourt.org",    # 中国法院网（非 .gov.cn，但相对权威）
    )
    # 优先域名后缀（含子域名）
    WEB_SEARCH_PREFER_TLDS = (
        ".gov.cn",  # 政府/法院/部委等
         ".edu.cn",  # 如需放宽到高校/研究机构，可取消注释（注意：白名单开启时需同时加入 ALLOWED_TLDS）
    )
    # DuckDuckGo 先抓取的候选条数（用于排序/去噪后再截断到 WEB_VS_SEARCH_K）
    WEB_SEARCH_FETCH_K = 50

    # ==================== 网页结果 AI 过滤/提炼 ====================
    # 将 DuckDuckGo 返回的网页摘要（snippet）先交给模型过滤低质量/不相关内容，并提炼要点后再用于回答
    WEB_AI_REFINE_ENABLED = True
    # 参与“AI提炼”的网页文档条数上限（越大越慢/越贵）
    WEB_AI_REFINE_MAX_DOCS = WEB_VS_SEARCH_K
    # 每条网页摘要参与提炼的最大字符数（防止提示词过长）
    WEB_AI_REFINE_MAX_CHARS_PER_DOC = 800


    # ==================== 案情预测配置 ====================
    # 案例数据集路径
    CASE_DATASET_PATH = "data/case_dataset/train.json"
    CASE_TESTSET_PATH = "data/case_dataset/test.json"
    
    # 案例向量数据库配置
    CASE_VS_COLLECTION_NAME = "criminal_cases"
    CASE_VS_SEARCH_K = 10  # 检索相似案例数量
    
    # 案例文本长度限制（字符数，超过则截断）
    CASE_MAX_CHARS = 2250
    
    # 刑法条文路径（用于刑期预测）
    CRIMINAL_LAW_PATH = "data/Law-Book/7-刑法/刑法.md"
    
    # ==================== 输出配置 ====================
    OUTPUT_DIR = "outputs"
    
    # ==================== 模型配置（从设置文件动态加载） ====================
    # 设置文件在项目根目录，需要向上两级（src/config -> src -> 项目根）
    SETTINGS_FILE = Path(__file__).parent.parent.parent / 'settings.json'
    
    # 默认模型配置（腾讯混元 via 万码云 OpenAI 兼容端点）
    DEFAULT_LLM_MODEL = "tencent/hy3"
    DEFAULT_EMBEDDING_MODEL = "hunyuan-embedding"
    DEFAULT_TEMPERATURE = 0.6
    DEFAULT_MAX_TOKENS = 7800
    DEFAULT_BASE_URL = "https://wcode.net/api/gpt/v1"

    # 模型名称映射（前端显示名 -> 实际模型名）
    LLM_MODEL_MAP = {
        "tencent/hy3": "tencent/hy3",
        "tencent/hy3-preview": "tencent/hy3-preview",
    }
    
    @classmethod
    def get_settings(cls):
        """获取当前设置"""
        # 调试信息：打印配置文件路径
        settings_path = cls.SETTINGS_FILE.resolve()
        # print(f"[配置调试] 读取配置文件: {settings_path}")
        
        if cls.SETTINGS_FILE.exists():
            try:
                with open(cls.SETTINGS_FILE, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
                    # print(f"[配置调试] 成功读取配置: LLM={settings.get('llm_model')}, T={settings.get('temperature')}, Embed={settings.get('embedding_model')}")
                    return settings
            except Exception as e:
                print(f"[配置调试] 读取配置文件失败: {e}")
                pass
        else:
            print(f"[配置调试] 配置文件不存在: {settings_path}")
        return {}
    
    @classmethod
    def get_api_key(cls):
        """获取API密钥（优先环境变量 HUNYUAN_API_KEY，其次设置文件）"""
        env_key = os.getenv("HUNYUAN_API_KEY", "")
        if env_key:
            return env_key
        settings = cls.get_settings()
        api_key = settings.get('api_key', '')
        if api_key and not api_key.endswith('****'):
            return api_key
        return ""
    
    @classmethod
    def get_llm_model(cls):
        """获取LLM模型名称"""
        settings = cls.get_settings()
        model = settings.get('llm_model', cls.DEFAULT_LLM_MODEL)
        return cls.LLM_MODEL_MAP.get(model, model)
    
    @classmethod
    def get_embedding_model(cls):
        """获取Embedding模型名称"""
        settings = cls.get_settings()
        return settings.get('embedding_model', cls.DEFAULT_EMBEDDING_MODEL)
    
    @classmethod
    def get_temperature(cls):
        """获取温度参数"""
        settings = cls.get_settings()
        try:
            return float(settings.get('temperature', cls.DEFAULT_TEMPERATURE))
        except:
            return cls.DEFAULT_TEMPERATURE

    @classmethod
    def get_max_tokens(cls):
        """获取最大输出token数"""
        settings = cls.get_settings()
        try:
            value = settings.get('max_tokens', cls.DEFAULT_MAX_TOKENS)
            return int(float(value))
        except:
            return cls.DEFAULT_MAX_TOKENS

config = Config()