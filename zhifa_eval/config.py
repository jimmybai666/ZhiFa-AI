"""
ZhiFa-Eval 全局配置
"""
import os
import re
from pathlib import Path
from dotenv import load_dotenv

# ─── 路径 ───────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent
DATASET_PATH = PROJECT_ROOT.parent / "datasets"
RESULTS_PATH = PROJECT_ROOT.parent / "results"
ZHIFA_PROJECT_PATH = Path(r"C:\Users\16004\Desktop\zhifa_jimmybai\ZhiFa")

# ─── 加载 .env ──────────────────────────────────────────
ENV_PATH = PROJECT_ROOT.parent / ".env"
load_dotenv(ENV_PATH)

# ─── 推理模型 服务端配置 ────────────────────────────────
INFERENCE_BASE_URL = os.getenv("INFERENCE_BASE_URL", "")
INFERENCE_API_KEY = os.getenv("INFERENCE_API_KEY", "")
INFERENCE_MODEL = os.getenv("INFERENCE_MODEL", "")

# ─── 裁判模型（LLM-as-Judge）服务端配置 ─────────────────
JUDGE_BASE_URL = os.getenv("JUDGE_BASE_URL", "")
JUDGE_API_KEY = os.getenv("JUDGE_API_KEY", "")
JUDGE_MODEL = os.getenv("JUDGE_MODEL", "")

# ─── 推理目标（被测模型 / 应用）──────────────────────────
INFERENCE_MODES = {
    "智法AI（RAG 增强）": "zhifa",
    "裸模型 API": "openai_api",
}


# ─── .env 写入 ──────────────────────────────────────────

def update_env_file(updates: dict):
    """将 updates 中的 key=value 写入 .env 并热更新模块变量。

    只修改 updates 中出现的 key，其余行保持原样。
    """
    global INFERENCE_BASE_URL, INFERENCE_API_KEY, INFERENCE_MODEL
    global JUDGE_BASE_URL, JUDGE_API_KEY, JUDGE_MODEL

    # 读取现有内容
    if ENV_PATH.exists():
        lines = ENV_PATH.read_text(encoding="utf-8").splitlines()
    else:
        lines = []

    remaining = dict(updates)  # 还没写入的 key

    # 逐行替换已有 key
    new_lines = []
    for line in lines:
        m = re.match(r"^([A-Z_]+)=", line)
        if m and m.group(1) in remaining:
            key = m.group(1)
            new_lines.append(f"{key}={remaining.pop(key)}")
        else:
            new_lines.append(line)

    # 追加 .env 中不存在的 key
    for key, val in remaining.items():
        new_lines.append(f"{key}={val}")

    ENV_PATH.write_text("\n".join(new_lines) + "\n", encoding="utf-8")

    # 热更新模块级变量
    INFERENCE_BASE_URL = updates.get("INFERENCE_BASE_URL", INFERENCE_BASE_URL)
    INFERENCE_API_KEY = updates.get("INFERENCE_API_KEY", INFERENCE_API_KEY)
    INFERENCE_MODEL = updates.get("INFERENCE_MODEL", INFERENCE_MODEL)
    JUDGE_BASE_URL = updates.get("JUDGE_BASE_URL", JUDGE_BASE_URL)
    JUDGE_API_KEY = updates.get("JUDGE_API_KEY", JUDGE_API_KEY)
    JUDGE_MODEL = updates.get("JUDGE_MODEL", JUDGE_MODEL)
