"""
文件转换模块 - 将 PDF/DOCX 文件转换为 Markdown 文本

支持两种 PDF 识别方式：
1. API 模式（默认）：调用 PaddleOCR 云端 API，无需本地 GPU
2. 本地模式：使用本地部署的 PaddleOCR-VL 模型，需要 GPU + 正确的 CUDA 环境
"""
import os
import json
import time
import requests
import builtins
import threading
from pathlib import Path
from .docx2markdown.docx_to_markdown_converter import docx_to_markdown

# ============================================================
# PDF 识别方式配置：  "api" | "local"
# ============================================================
PDF_OCR_MODE = os.environ.get("PDF_OCR_MODE", "api")

# ============================================================
# API 模式相关配置
# ============================================================
PADDLE_OCR_API_URL = "https://paddleocr.aistudio-app.com/api/v2/ocr/jobs"
PADDLE_OCR_API_TOKEN = os.environ.get("PADDLE_OCR_API_TOKEN", "")
PADDLE_OCR_MODEL = os.environ.get("PADDLE_OCR_MODEL", "PaddleOCR-VL-1.6")


def convert_to_markdown_via_api(input_file, output_path=None):
    """
    通过 PaddleOCR 云端 API 将 PDF 转换为 Markdown

    Args:
        input_file: PDF 文件路径
        output_path: 可选的输出目录路径
    Returns:
        markdown_texts: 转换后的 Markdown 文本
    """
    if not PADDLE_OCR_API_TOKEN:
        raise ValueError("未配置 PADDLE_OCR_API_TOKEN，请在 .env 文件中设置")

    headers = {
        "Authorization": f"bearer {PADDLE_OCR_API_TOKEN}",
    }

    optional_payload = {
        "useDocOrientationClassify": False,
        "useDocUnwarping": False,
        "useChartRecognition": False,
    }

    print(f"  [API] 正在上传文件: {Path(input_file).name}")

    # 上传文件创建任务
    if not os.path.exists(input_file):
        raise FileNotFoundError(f"文件不存在: {input_file}")

    data = {
        "model": PADDLE_OCR_MODEL,
        "optionalPayload": json.dumps(optional_payload),
    }

    with open(input_file, "rb") as f:
        files = {"file": f}
        job_response = requests.post(
            PADDLE_OCR_API_URL, headers=headers, data=data, files=files
        )

    if job_response.status_code != 200:
        raise RuntimeError(
            f"PaddleOCR API 提交失败 (HTTP {job_response.status_code}): {job_response.text}"
        )

    job_id = job_response.json()["data"]["jobId"]
    print(f"  [API] 任务已提交，jobId: {job_id}")

    # 轮询等待结果
    jsonl_url = ""
    poll_interval = 3  # 秒
    max_wait = 300  # 最多等待 5 分钟

    start_time = time.time()
    while time.time() - start_time < max_wait:
        result_response = requests.get(
            f"{PADDLE_OCR_API_URL}/{job_id}", headers=headers
        )
        if result_response.status_code != 200:
            raise RuntimeError(
                f"PaddleOCR API 查询失败 (HTTP {result_response.status_code})"
            )

        state = result_response.json()["data"]["state"]

        if state == "pending":
            print("  [API] 状态: 排队中...")
        elif state == "running":
            progress = result_response.json()["data"].get("extractProgress", {})
            total = progress.get("totalPages", "?")
            extracted = progress.get("extractedPages", "?")
            print(f"  [API] 状态: 识别中 ({extracted}/{total} 页)")
        elif state == "done":
            progress = result_response.json()["data"]["extractProgress"]
            print(f"  [API] ✓ 识别完成，共 {progress['extractedPages']} 页")
            jsonl_url = result_response.json()["data"]["resultUrl"]["jsonUrl"]
            break
        elif state == "failed":
            error_msg = result_response.json()["data"].get("errorMsg", "未知错误")
            raise RuntimeError(f"PaddleOCR API 任务失败: {error_msg}")

        time.sleep(poll_interval)
    else:
        raise TimeoutError(f"PaddleOCR API 任务超时（等待超过 {max_wait} 秒）")

    # 下载并解析结果
    if not jsonl_url:
        raise RuntimeError("未获取到结果 URL")

    jsonl_response = requests.get(jsonl_url)
    jsonl_response.raise_for_status()

    lines = jsonl_response.text.strip().split("\n")
    markdown_pages = []

    for line in lines:
        line = line.strip()
        if not line:
            continue
        result = json.loads(line)["result"]
        for res in result["layoutParsingResults"]:
            md_text = res["markdown"]["text"]
            markdown_pages.append(md_text)

    # 合并所有页面
    markdown_texts = "\n\n".join(markdown_pages)

    # 如果指定了输出路径，保存文件
    if output_path:
        mkd_file_path = os.path.join(output_path, f"{Path(input_file).stem}.md")
        Path(mkd_file_path).parent.mkdir(parents=True, exist_ok=True)
        with open(mkd_file_path, "w", encoding="utf-8") as f:
            f.write(markdown_texts)
        print(f"  [API] Markdown 已保存: {mkd_file_path}")

    return markdown_texts


# ============================================================
# 本地模式相关配置
# ============================================================

# 允许多份 OpenMP 运行时共存（paddle 和 numpy 各自链接了 libiomp5md.dll）
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

# 使用 builtins 存储 pipeline 实例，避免在 Flask 重载（Reload）时丢失引用但 C++ 层仍保持初始化状态
# 从而导致 "PDX has already been initialized" 错误
if not hasattr(builtins, "_law_ai_paddle_pipeline"):
    builtins._law_ai_paddle_pipeline = None
# 初始化时加锁，避免并发请求同时初始化导致 PDX 重复初始化
if not hasattr(builtins, "_law_ai_paddle_lock"):
    builtins._law_ai_paddle_lock = threading.Lock()


def _init_local_paddle():
    """延迟初始化本地 PaddlePaddle 环境（仅在本地模式下调用）"""
    import paddle.nn.functional.flash_attention as _fa
    _fa.g_enable_flash = False
    _fa.g_enable_math = True
    _fa.g_enable_mem_efficient = False

    _fa._select_sdp_cuda = lambda head_dim: "math"
    _fa._select_sdp = lambda head_dim: "math"

    os.environ["FLAGS_use_flash_attn"] = "0"
    try:
        import paddle
        paddle.set_flags({"FLAGS_flash_attn_version": 0})
    except Exception:
        pass


def _force_eager_attention(pipeline):
    """遍历 pipeline 中的模型，将 _attn_implementation 强制设为 eager"""
    try:
        for attr_name in dir(pipeline):
            obj = getattr(pipeline, attr_name, None)
            if obj is None:
                continue
            config = getattr(obj, 'config', None)
            if config is not None and hasattr(config, '_attn_implementation'):
                config._attn_implementation = "eager"
                print(f"  [local] patch: {attr_name}.config._attn_implementation -> eager")
            inner_model = getattr(obj, 'model', None)
            if inner_model is not None:
                inner_config = getattr(inner_model, 'config', None)
                if inner_config is not None and hasattr(inner_config, '_attn_implementation'):
                    inner_config._attn_implementation = "eager"
                    print(f"  [local] patch: {attr_name}.model.config._attn_implementation -> eager")
    except Exception as e:
        print(f"  [local] _force_eager_attention warning: {e}")


def get_paddle_pipeline():
    """获取本地 PaddleOCR pipeline 单例"""
    if builtins._law_ai_paddle_pipeline is None:
        with builtins._law_ai_paddle_lock:
            if builtins._law_ai_paddle_pipeline is None:
                _init_local_paddle()
                try:
                    from paddleocr import PaddleOCRVL
                    pipeline = PaddleOCRVL()
                    _force_eager_attention(pipeline)
                    builtins._law_ai_paddle_pipeline = pipeline
                except Exception as e:
                    print(f"Failed to initialize PaddleOCRVL: {e}")
                    if builtins._law_ai_paddle_pipeline is None:
                        raise
    return builtins._law_ai_paddle_pipeline


def convert_to_markdown_local(input_file, output_path=None):
    """
    通过本地 PaddleOCR-VL 模型将 PDF 转换为 Markdown

    Args:
        input_file: PDF 文件路径
        output_path: 可选的输出目录路径
    Returns:
        markdown_texts: 转换后的 Markdown 文本
    """
    pipeline = get_paddle_pipeline()
    output = pipeline.predict(input=input_file)

    markdown_list = []
    markdown_images = []

    for res in output:
        md_info = res.markdown
        markdown_list.append(md_info)
        markdown_images.append(md_info.get("markdown_images", {}))

    # 合并所有的 Markdown 内容
    markdown_texts = pipeline.concatenate_markdown_pages(markdown_list)

    if output_path:
        mkd_file_path = os.path.join(output_path, f"{Path(input_file).stem}.md")
        Path(mkd_file_path).parent.mkdir(parents=True, exist_ok=True)

        with open(mkd_file_path, "w", encoding="utf-8") as f:
            f.write(markdown_texts)
        print(f"Successfully converted PDF to Markdown: {mkd_file_path}")

        for item in markdown_images:
            if item:
                for path, image in item.items():
                    file_path = Path(output_path) / path
                    file_path.parent.mkdir(parents=True, exist_ok=True)
                    image.save(file_path)

    return markdown_texts


# ============================================================
# 统一入口
# ============================================================

def convert_to_markdown(input_file, output_path=None):
    """
    将文件转换为 Markdown 文本（统一入口）

    支持格式：
    - .docx: 直接解析
    - .pdf: 根据 PDF_OCR_MODE 选择 API 或本地模式

    Args:
        input_file: 输入文件路径
        output_path: 可选的输出目录路径
    Returns:
        markdown_texts: 转换后的 Markdown 文本
    """
    input_extension = Path(input_file).suffix.lower()

    if input_extension == ".docx":
        if output_path:
            output_file = os.path.join(output_path, f"{Path(input_file).stem}.md")
            markdown_texts = docx_to_markdown(input_file, output_file)
            print(f"Successfully converted DOCX to Markdown: {output_file}")
        else:
            markdown_texts = docx_to_markdown(input_file)
        return markdown_texts

    elif input_extension == ".pdf":
        if PDF_OCR_MODE == "api":
            return convert_to_markdown_via_api(input_file, output_path)
        else:
            return convert_to_markdown_local(input_file, output_path)

    else:
        raise ValueError(f"不支持的文件格式: {input_extension}（仅支持 .docx 和 .pdf）")
