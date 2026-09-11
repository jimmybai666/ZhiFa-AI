"""
ZhiFa-Eval FastAPI Server
"""
import io
import json
import time
import random
import zipfile
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel

from .data_loader import TASK_REGISTRY, TASK_MAP, load_task_data, get_tasks_by_module
from .scorers.scorer_registry import score_single
from .scorers.subjective.llm_judge import LLMJudge
from .inference.openai_inference import OpenAIInference
from .config import RESULTS_PATH, update_env_file
from . import config as _config

app = FastAPI(title="ZhiFa-Eval", version="1.0")

STATIC_DIR = Path(__file__).parent / "static"
TEMPLATES_DIR = Path(__file__).parent / "templates"

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

SEED = 42


# ─── Helpers ─────────────────────────────────────────────

def _sample_data(data: list, ratio: int, seed: int = 42) -> list:
    """Fixed-seed sampling. ratio: 1, 25, 50, 100."""
    if ratio >= 100:
        return data
    if ratio == 1:
        return [random.Random(seed).choice(data)]
    k = max(1, len(data) * ratio // 100)
    return random.Random(seed).sample(data, k)


def _score_items(task, data, predictions, judge=None):
    """Score predictions against data. Returns (results, summary)."""
    results = []
    for i, (item, pred) in enumerate(zip(data, predictions)):
        scores = {}
        question = item.get("question", item.get("conversation", ""))
        reference = item.get("answer", "")
        if task.eval_method == "objective":
            scores = score_single(task.task_id, task.metrics, pred, reference)
        elif task.eval_method == "rubric" and judge:
            try:
                scores = judge.score(task.task_id, question, pred, item)
            except Exception as e:
                scores = {"judge_error": str(e)}
        results.append({
            "index": i, "status": "success",
            "question": question[:200],
            "reference": reference[:300],
            "prediction": pred[:500],
            "scores": scores,
        })

    # Summary
    if task.eval_method == "objective" and results:
        valid = [r for r in results if r["scores"]]
        if valid:
            key = next(iter(valid[0]["scores"]))
            vals = [r["scores"].get(key, 0) for r in valid]
            avg = sum(vals) / len(vals)
        else:
            key, avg = "score", 0
    else:
        valid = [r for r in results if isinstance(r.get("scores"), dict)]
        vals = [r["scores"].get("score_ratio", 0) for r in valid]
        avg = sum(vals) / len(vals) if vals else 0
        key = "score_ratio"
    return results, {"metric": key, "average_score": round(avg, 4)}


def _save_result(task_id, difficulty, model_name, judge_model, sample_count,
                 elapsed, summary, results):
    RESULTS_PATH.mkdir(parents=True, exist_ok=True)
    task = TASK_MAP.get(task_id)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    fname = f"{task_id}_{difficulty}_{ts}.json"
    output = {
        "task_id": task_id,
        "display_name": task.display_name if task else task_id,
        "difficulty": difficulty,
        "model": model_name, "judge_model": judge_model or "N/A",
        "sample_count": sample_count, "elapsed_seconds": elapsed,
        "summary": summary, "results": results,
    }
    with open(RESULTS_PATH / fname, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    return output


# ─── Pages ───────────────────────────────────────────────

_html_cache = None

def _get_html():
    global _html_cache
    if _html_cache is None:
        _html_cache = (TEMPLATES_DIR / "index.html").read_text(encoding="utf-8")
    return _html_cache

@app.get("/", response_class=HTMLResponse)
async def page_index():
    return _get_html()

@app.get("/eval/{path:path}", response_class=HTMLResponse)
async def page_eval_catchall(path: str = ""):
    return _get_html()


# ─── API: Task Registry ─────────────────────────────────

@app.get("/api/tasks")
async def get_tasks():
    modules = {}
    for t in TASK_REGISTRY:
        if t.module not in modules:
            modules[t.module] = []
        info = {
            "task_id": t.task_id, "display_name": t.display_name,
            "module": t.module, "layer": t.layer,
            "eval_method": t.eval_method, "metrics": t.metrics,
            "task_type": t.task_type, "difficulties": t.difficulties,
            "sample_counts": t.sample_counts,
        }
        if t.subtypes:
            info["subtypes"] = t.subtypes
        modules[t.module].append(info)
    return {"modules": modules, "total_tasks": len(TASK_REGISTRY)}


# ─── API: Judge 配置状态 ───────────────────────────────

def _mask_key(key: str) -> str:
    if not key:
        return ""
    if len(key) > 8:
        return key[:3] + "*" * (len(key) - 7) + key[-4:]
    return "*" * len(key)


def _clean_val(v):
    """过滤空值和前端回传的 masked 占位符"""
    if not v or "*" in v:
        return ""
    return v


def _resolve_inference(req_url, req_key, req_model):
    """合并前端传值和服务端 .env 推理配置"""
    key = _clean_val(req_key) or _config.INFERENCE_API_KEY
    url = _clean_val(req_url) or _config.INFERENCE_BASE_URL
    model = _clean_val(req_model) or _config.INFERENCE_MODEL
    return url, key, model


def _resolve_judge(req_url, req_key, req_model, fallback_url="", fallback_model=""):
    """合并前端传值和服务端 .env 裁判配置"""
    key = _clean_val(req_key) or _config.JUDGE_API_KEY
    url = _clean_val(req_url) or _config.JUDGE_BASE_URL or fallback_url
    model = _clean_val(req_model) or _config.JUDGE_MODEL or fallback_model
    return url, key, model


@app.get("/api/inference-config")
async def get_inference_config():
    return {
        "configured": bool(_config.INFERENCE_API_KEY),
        "base_url": _config.INFERENCE_BASE_URL,
        "api_key_masked": _mask_key(_config.INFERENCE_API_KEY),
        "model": _config.INFERENCE_MODEL,
    }


@app.get("/api/judge-config")
async def get_judge_config():
    return {
        "configured": bool(_config.JUDGE_API_KEY),
        "base_url": _config.JUDGE_BASE_URL,
        "api_key_masked": _mask_key(_config.JUDGE_API_KEY),
        "model": _config.JUDGE_MODEL,
    }


@app.post("/api/save-config")
async def save_config(body: dict):
    """将前端提交的推理/裁判模型配置写入 .env 并热更新。"""
    mapping = {}
    for env_key, body_key in [
        ("INFERENCE_BASE_URL", "inference_base_url"),
        ("INFERENCE_API_KEY", "inference_api_key"),
        ("INFERENCE_MODEL", "inference_model"),
        ("JUDGE_BASE_URL", "judge_base_url"),
        ("JUDGE_API_KEY", "judge_api_key"),
        ("JUDGE_MODEL", "judge_model"),
    ]:
        val = body.get(body_key, "")
        if val and "*" not in val:  # 空值和 masked 值不覆盖已有配置
            mapping[env_key] = val
    if not mapping:
        return {"ok": True}
    try:
        update_env_file(mapping)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"ok": True}


# ─── API: 1 样本抽取 ────────────────────────────────────

def _normalize_sample(task_id: str, item: dict) -> dict:
    """
    将不同格式的数据统一为 {prompt, question, answer, has_rubric} 结构。

    - prompt: 任务指令（告诉模型要做什么）
    - question: 真实问题/案情/合同内容
    - answer: 参考答案（客观题有，Rubric 题为空）
    - has_rubric: 是否有 Rubric 评分标准
    """
    prompt = item.get("instruction", "")
    question = ""
    answer = item.get("answer", "")
    has_rubric = "rubrics" in item or "risks" in item

    if task_id == "legal_qa.application.consultation_fact_inquiry":
        # conversation 是当事人陈述，question 是任务指令
        prompt = item.get("question", "")
        question = item.get("conversation", "")
    elif task_id in ("contract_review.risk_detection", "contract_review.risk_revision"):
        # 合同审查：question 是指令，_contract_text 是合同原文
        prompt = item.get("question", "请审阅以下合同，识别其中存在的法律风险。")
        question = item.get("_contract_text", "[合同原文需从文件加载]")
    elif task_id == "legal_qa.application.legal_document_generation":
        # 文书生成：question 本身就是当事人陈述
        prompt = f"请根据以下当事人陈述，起草一份{item.get('doc_type', '法律文书')}。"
        question = item.get("question", "")
    else:
        # 通用格式：instruction 是指令，question 是问题
        question = item.get("question", "")

    return {
        "prompt": prompt,
        "question": question,
        "answer": answer,
        "has_rubric": has_rubric,
        "raw_keys": list(item.keys()),
    }


@app.get("/api/tasks/{task_id}/sample")
async def get_one_sample(task_id: str, difficulty: str = "standard", seed: int = 42, subtype: Optional[str] = None):
    task = TASK_MAP.get(task_id)
    if not task:
        raise HTTPException(404, "Unknown task")
    data = load_task_data(task_id, difficulty, subtype=subtype)
    item = random.Random(seed).choice(data)
    normalized = _normalize_sample(task_id, item)
    return {
        "task_id": task_id,
        "difficulty": difficulty,
        "display_name": task.display_name,
        "eval_method": task.eval_method,
        "metrics": task.metrics,
        **normalized,
    }


# ─── API: 在线推理评测 ──────────────────────────────────

class EvalRequest(BaseModel):
    task_id: str
    difficulty: str = "standard"
    sample_ratio: int = 100
    seed: int = 42
    subtype: Optional[str] = None
    api_base_url: str
    api_key: str
    model_name: str
    judge_base_url: Optional[str] = None
    judge_api_key: Optional[str] = None
    judge_model: Optional[str] = None


@app.post("/api/eval/run")
async def run_eval(req: EvalRequest):
    task = TASK_MAP.get(req.task_id)
    if not task:
        raise HTTPException(404, f"Unknown task: {req.task_id}")
    data = _sample_data(load_task_data(req.task_id, req.difficulty, subtype=req.subtype), req.sample_ratio, req.seed)
    i_url, i_key, i_model = _resolve_inference(req.api_base_url, req.api_key, req.model_name)
    client = OpenAIInference(i_url, i_key, i_model)
    judge = None
    if task.eval_method == "rubric":
        j_url, j_key, j_model = _resolve_judge(
            req.judge_base_url, req.judge_api_key, req.judge_model,
            i_url, i_model)
        if j_key:
            jclient = OpenAIInference(j_url, j_key, j_model, temperature=0.0)
            judge = LLMJudge(jclient)

    predictions = []
    start = time.time()
    for item in data:
        instruction = item.get("instruction", "")
        question = item.get("question", item.get("conversation", ""))
        try:
            pred = client.infer(instruction, question)
        except Exception as e:
            pred = f"[ERROR] {e}"
        predictions.append(pred)

    results, summary = _score_items(task, data, predictions, judge)
    elapsed = round(time.time() - start, 1)
    return _save_result(req.task_id, req.difficulty, req.model_name,
                        req.judge_model, len(data), elapsed, summary, results)


# ─── API: 导出题目 JSON ────────────────────────────────

CONTRACT_TASKS = ("contract_review.risk_detection", "contract_review.risk_revision")


@app.get("/api/eval/export")
async def export_questions(
    task_id: str,
    difficulty: str = "standard",
    sample_ratio: int = 100,
    seed: int = 42,
    subtype: Optional[str] = None,
):
    task = TASK_MAP.get(task_id)
    if not task:
        raise HTTPException(404, "Unknown task")
    data = _sample_data(
        load_task_data(task_id, difficulty, subtype=subtype or None),
        sample_ratio, seed
    )

    meta = {
        "task_id": task_id,
        "display_name": task.display_name,
        "difficulty": difficulty,
        "sample_ratio": sample_ratio,
        "seed": seed,
        "subtype": subtype,
        "count": len(data),
        "eval_method": task.eval_method,
        "metrics": task.metrics,
    }

    is_contract = task_id in CONTRACT_TASKS

    samples = []
    contract_files = {}
    for i, item in enumerate(data):
        norm = _normalize_sample(task_id, item)
        sample = {
            "id": i,
            "instruction": norm["prompt"],
        }
        if is_contract:
            fname = item.get("_rubric_file", f"{i}.md")
            contract_name = Path(fname).stem + ".md"
            sample["contract_file"] = f"contracts/{contract_name}"
            contract_files[contract_name] = norm["question"]
        else:
            sample["question"] = norm["question"]
        samples.append(sample)

    if is_contract:
        meta["format"] = "zip"
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            export_data = {"meta": meta, "samples": samples}
            zf.writestr("questions.json",
                        json.dumps(export_data, ensure_ascii=False, indent=2))
            for fname, content in contract_files.items():
                zf.writestr(f"contracts/{fname}", content)
        buf.seek(0)
        zip_name = f"{task_id}_{difficulty}_seed{seed}_{len(data)}q.zip"
        return StreamingResponse(
            buf,
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{zip_name}"'},
        )
    else:
        return {"meta": meta, "samples": samples}


# ─── API: 离线评分（JSON 导入 / 单条手动）───────────────

class ScoreRequest(BaseModel):
    task_id: str
    difficulty: str = "standard"
    sample_ratio: int = 100
    seed: int = 42
    subtype: Optional[str] = None
    predictions: List[str]
    model_name: str = "manual"
    judge_base_url: Optional[str] = None
    judge_api_key: Optional[str] = None
    judge_model: Optional[str] = None


@app.post("/api/eval/score")
async def score_only(req: ScoreRequest):
    task = TASK_MAP.get(req.task_id)
    if not task:
        raise HTTPException(404, f"Unknown task: {req.task_id}")
    data = _sample_data(load_task_data(req.task_id, req.difficulty, subtype=req.subtype), req.sample_ratio, req.seed)
    if len(req.predictions) != len(data):
        raise HTTPException(400,
            f"predictions 数量({len(req.predictions)})与采样数据量({len(data)})不匹配")
    judge = None
    if task.eval_method == "rubric":
        j_url, j_key, j_model = _resolve_judge(
            req.judge_base_url, req.judge_api_key, req.judge_model)
        if j_key:
            jclient = OpenAIInference(j_url, j_key, j_model, temperature=0.0)
            judge = LLMJudge(jclient)

    start = time.time()
    results, summary = _score_items(task, data, req.predictions, judge)
    elapsed = round(time.time() - start, 1)
    return _save_result(req.task_id, req.difficulty, req.model_name,
                        req.judge_model, len(data), elapsed, summary, results)


# ─── Helper: 按问题匹配 ─────────────────────────────────

def _match_by_question(task_id: str, data: list, pred_list: list) -> list:
    MATCH_LEN = 200

    def _get_q(item):
        return _normalize_sample(task_id, item)["question"][:MATCH_LEN]

    data_qs = [_get_q(item) for item in data]
    predictions = [""] * len(data)
    matched = set()
    unmatched = []

    for p in pred_list:
        q_prefix = (p.get("question", "") or "")[:MATCH_LEN]
        pred_text = p.get("answer", "") or p.get("prediction", "")
        found = False
        for idx, dq in enumerate(data_qs):
            if idx not in matched and dq == q_prefix:
                predictions[idx] = pred_text
                matched.add(idx)
                found = True
                break
        if not found:
            q_clean = q_prefix.replace(" ", "").replace("\n", "")
            for idx, dq in enumerate(data_qs):
                if idx not in matched:
                    if dq.replace(" ", "").replace("\n", "") == q_clean:
                        predictions[idx] = pred_text
                        matched.add(idx)
                        found = True
                        break
        if not found:
            unmatched.append(q_prefix[:50])

    if len(matched) < len(data):
        missing = len(data) - len(matched)
        msg = f"有 {missing} 道题未找到匹配的回答"
        if unmatched:
            msg += f"。未匹配示例: {unmatched[:3]}"
        raise HTTPException(400, msg)
    return predictions


# ─── API: JSON 文件上传评分 ──────────────────────────────

@app.post("/api/eval/upload")
async def upload_and_score(
    file: UploadFile = File(...),
    task_id: str = Form(""),
    difficulty: str = Form("standard"),
    sample_ratio: int = Form(100),
    seed: int = Form(42),
    subtype: str = Form(""),
    model_name: str = Form("uploaded"),
    judge_base_url: str = Form(""),
    judge_api_key: str = Form(""),
    judge_model: str = Form(""),
):
    content = await file.read()
    try:
        preds_data = json.loads(content)
    except json.JSONDecodeError:
        raise HTTPException(400, "JSON 解析失败")

    # ---- 新格式: {meta, answers/predictions} ----
    _answers_key = "answers" if "answers" in preds_data else "predictions" if "predictions" in preds_data else None
    if isinstance(preds_data, dict) and _answers_key:
        meta = preds_data.get("meta", {})

        if meta:
            _required = ["task_id", "difficulty", "sample_ratio", "seed"]
            _missing = [k for k in _required if k not in meta]
            if _missing:
                raise HTTPException(400,
                    f"meta 中缺少必填字段: {', '.join(_missing)}。"
                    "请使用导出题目时生成的完整 meta，或删除 meta 字段后通过表单参数指定。")
            _tid = meta["task_id"]
            _diff = meta["difficulty"]
            _ratio = meta["sample_ratio"]
            _seed = meta["seed"]
            _sub = meta.get("subtype", "") or ""
        else:
            if not task_id:
                raise HTTPException(400, "JSON 中无 meta，且表单未指定 task_id")
            _tid = task_id
            _diff = difficulty
            _ratio = sample_ratio
            _seed = seed
            _sub = subtype or ""

        task = TASK_MAP.get(_tid)
        if not task:
            raise HTTPException(404, f"Unknown task: {_tid}")
        data = _sample_data(
            load_task_data(_tid, _diff, subtype=_sub or None), _ratio, _seed)

        pred_list = preds_data[_answers_key]
        if not pred_list or not isinstance(pred_list[0], dict):
            raise HTTPException(400,
                "answers 应为对象数组 [{id, answer}] 或 [{question, answer}]")

        if len(pred_list) != len(data):
            raise HTTPException(400,
                f"答案数量({len(pred_list)})与采样题目数量({len(data)})不匹配。"
                f"请确认 meta 中的 task_id、difficulty、sample_ratio、seed、subtype "
                f"与导出时一致。")

        def _get_answer(p):
            return p.get("answer", "") or p.get("prediction", "")

        if "id" in pred_list[0]:
            pred_map = {p["id"]: _get_answer(p) for p in pred_list}
            extra_ids = [k for k in pred_map if k < 0 or k >= len(data)]
            if extra_ids:
                raise HTTPException(400,
                    f"答案中有 {len(extra_ids)} 条 id 超出范围 (应为 0~{len(data)-1}，"
                    f"多余 id: {extra_ids[:5]})")
            predictions = [pred_map.get(i, "") for i in range(len(data))]
            missing_ids = [i for i in range(len(data)) if i not in pred_map]
            if missing_ids:
                raise HTTPException(400,
                    f"缺少 {len(missing_ids)} 条回答 (id: {missing_ids[:5]})")
        elif "question" in pred_list[0]:
            predictions = _match_by_question(_tid, data, pred_list)
        else:
            raise HTTPException(400,
                "每项需包含 'id' 或 'question' 字段")

        task_id = _tid
        difficulty = _diff

    # ---- 旧格式: 纯数组（向后兼容）----
    elif isinstance(preds_data, list):
        task = TASK_MAP.get(task_id)
        if not task:
            raise HTTPException(404, f"Unknown task: {task_id}")
        data = _sample_data(
            load_task_data(task_id, difficulty, subtype=subtype or None),
            sample_ratio, seed)
        if preds_data and isinstance(preds_data[0], str):
            predictions = preds_data
        else:
            predictions = [
                p.get("prediction", "") if isinstance(p, dict) else str(p)
                for p in preds_data]
        if len(predictions) != len(data):
            raise HTTPException(400,
                f"JSON 中 {len(predictions)} 条回答，但采样数据有 {len(data)} 条")
    else:
        raise HTTPException(400, "不支持的 JSON 格式")

    judge = None
    if task.eval_method == "rubric":
        j_url, j_key, j_model = _resolve_judge(judge_base_url, judge_api_key, judge_model)
        if j_key:
            jclient = OpenAIInference(j_url, j_key, j_model, temperature=0.0)
            judge = LLMJudge(jclient)

    start = time.time()
    results, summary = _score_items(task, data, predictions, judge)
    elapsed = round(time.time() - start, 1)
    return _save_result(task_id, difficulty, model_name,
                        judge_model, len(data), elapsed, summary, results)


# ─── API: History ─────────────────────────────────────────

@app.get("/api/results")
async def get_results():
    RESULTS_PATH.mkdir(parents=True, exist_ok=True)
    records = []
    for rf in sorted(RESULTS_PATH.glob("*.json"), reverse=True):
        with open(rf, "r", encoding="utf-8") as f:
            d = json.load(f)
        tid = d.get("task_id", "")
        t = TASK_MAP.get(tid)
        records.append({
            "file": rf.name,
            "task_id": tid,
            "display_name": d.get("display_name") or (t.display_name if t else tid),
            "difficulty": d.get("difficulty", ""),
            "model": d.get("model", ""),
            "judge_model": d.get("judge_model", ""),
            "sample_count": d.get("sample_count", 0),
            "average_score": d.get("summary", {}).get("average_score", 0),
            "elapsed": d.get("elapsed_seconds", 0),
        })
    return records


@app.get("/api/results/{filename}")
async def get_result_detail(filename: str):
    fp = RESULTS_PATH / filename
    if not fp.exists():
        raise HTTPException(404, "File not found")
    with open(fp, "r", encoding="utf-8") as f:
        return json.load(f)
