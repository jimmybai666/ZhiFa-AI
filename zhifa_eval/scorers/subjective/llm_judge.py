"""
LLM-as-Judge 评分器

支持 6 种 Rubric 格式，通过 OpenAI 兼容 API 调用裁判模型评分。
Prompt 模板见 prompts.py。
"""

import json
import re
from typing import Any, Dict, List, Tuple

from zhifa_eval.inference.openai_inference import OpenAIInference
from .prompts import (
    SYSTEM_PROMPTS, DEFAULT_SYSTEM_PROMPT,
    USER_PROMPTS, DEFAULT_USER_PROMPT,
)

MAX_RETRY = 2  # 校验失败后最多重试次数


class LLMJudge:
    """LLM-as-Judge 通用评分器"""

    def __init__(self, inference: OpenAIInference):
        self.llm = inference

    def score(
        self,
        task_id: str,
        question: str,
        model_response: str,
        rubric_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """对模型回答进行 Rubric 评分，校验不通过自动重试。"""
        task_key = task_id.rsplit(".", 1)[-1] if task_id else ""

        # adversarial 合同（反例）：走单独的 prompt 和 validator
        is_adversarial = rubric_data.get("difficulty") == "adversarial" or (
            rubric_data.get("risk_count", -1) == 0 and "scoring_note" in rubric_data)
        if is_adversarial:
            task_key = task_key + "_adversarial"

        system_prompt = SYSTEM_PROMPTS.get(task_key, DEFAULT_SYSTEM_PROMPT)
        user_prompt = self._build_prompt(task_key, question, model_response, rubric_data)

        for attempt in range(1 + MAX_RETRY):
            raw = self.llm.infer(instruction=system_prompt, question=user_prompt)
            result = self._parse_and_validate(raw, rubric_data, task_key)

            if result["validation"] == "ok":
                result["attempts"] = attempt + 1
                return result

            # 判断是否值得重试（结构性错误才重试，clamp 修正不算）
            if not self._should_retry(result["validation"]):
                result["attempts"] = attempt + 1
                return result

        # 用尽重试，返回最后一次结果
        result["attempts"] = 1 + MAX_RETRY
        return result

    @staticmethod
    def _should_retry(warnings: list) -> bool:
        """判断校验失败是否值得重试。
        结构性错误（格式不对、缺项）值得重试；
        数值修正（clamp、module_total_mismatch）不值得重试。
        """
        retry_keywords = [
            "no_item_scores", "no_modules_in_response", "no_risk_scores",
            "no_fix_scores", "empty_items", "no_scores",
            "judge_json_parse_error", "fallback_",
            "missing_indices", "missing_modules", "missing_risks", "missing_fixes",
            "missing_sub_keys", "count:", "checklist_count",
        ]
        if not isinstance(warnings, list):
            return False
        for w in warnings:
            for kw in retry_keywords:
                if kw in w:
                    return True
        return False

    # ─── Prompt 构建 ─────────────────────────────────────

    def _build_prompt(
        self, task_key: str, question: str, response: str, rubric: Dict
    ) -> str:
        template = USER_PROMPTS.get(task_key)
        if template:
            return self._fill_template(template, task_key, question, response, rubric)
        return self._build_default(question, response, rubric)

    def _fill_template(
        self, template: str, task_key: str, question: str, response: str, rubric: Dict
    ) -> str:
        total = self._compute_total(rubric)
        rubric_text = self._format_rubric(rubric)
        variables = {
            "question": question,
            "response": response,
            "rubric": rubric_text,
            "total_score": total,
            "instruction": rubric.get("instruction", ""),
            "label": rubric.get("label", ""),
            "doc_type": rubric.get("doc_type", "法律文书"),
            "conversation": rubric.get("conversation", question),
            "task_instruction": rubric.get("question", ""),
            "task_question": rubric.get("question", question),
            "contract_text": rubric.get("_contract_text", "")[:3000],
            "base_score": rubric.get("total_score", 15),
            "scoring_note": rubric.get("scoring_note", ""),
            "scoring_method": rubric.get("scoring_method", ""),
            "criteria": json.dumps(
                rubric.get("false_positive_criteria",
                           rubric.get("false_modification_criteria", [])),
                ensure_ascii=False, indent=2),
        }
        return template.format(**variables)

    def _build_default(self, question: str, response: str, rubric: Dict) -> str:
        total = self._compute_total(rubric)
        rubric_text = self._format_rubric(rubric)
        return DEFAULT_USER_PROMPT.format(
            question=question, response=response,
            rubric=rubric_text, total_score=total,
        )

    # ─── Rubric 格式化 ───────────────────────────────────

    def _format_rubric(self, rubric: Dict) -> str:
        if "rubrics" in rubric and isinstance(rubric["rubrics"], list):
            items = rubric["rubrics"]
            if items and "module" in items[0]:
                return self._fmt_modules(items)
            return self._fmt_flat(items)
        if "fixes" in rubric:
            return self._fmt_fixes(rubric["fixes"])
        if "risks" in rubric:
            return self._fmt_risks(rubric["risks"])
        return json.dumps(rubric, ensure_ascii=False, indent=2)

    def _fmt_modules(self, modules: List[Dict]) -> str:
        lines = []
        for mod in modules:
            lines.append(f"\n### 模块：{mod['module']}（{mod['module_score']} 分）")
            for item in mod.get("items", []):
                idx, pts = item.get("index", ""), item.get("points", "")
                crit = item.get("criterion", "")
                order = " [需按顺序]" if item.get("order_required") else ""
                lines.append(f"  [{idx}] ({pts}分{order}) {crit}")
                if item.get("note"):
                    lines.append(f"       备注：{item['note']}")
        return "\n".join(lines)

    def _fmt_flat(self, items: List[Dict]) -> str:
        lines = []
        for item in items:
            idx, pts = item.get("index", ""), item.get("points", "")
            crit = item.get("criterion", "")
            lines.append(f"  [{idx}] ({pts}分) {crit}")
        return "\n".join(lines)

    def _fmt_risks(self, risks: List[Dict]) -> str:
        lines = []
        for r in risks:
            rid, name = r.get("risk_id", ""), r.get("risk_name", "")
            severity, pts = r.get("severity", ""), r.get("points", "")
            clause = r.get("risky_clause", "")[:120]
            location = r.get("clause_location", "")
            lines.append(f"\n### 风险 {rid}：{name}（{pts}分）")
            lines.append(f"  严重性：{severity}")
            if location:
                lines.append(f"  条款位置：{location}")
            lines.append(f"  风险条款原文：{clause}...")
            for k, v in r.get("scoring", {}).items():
                lines.append(f"  - {k}：{v.get('score', '')}分 — {v.get('desc', '')}")
        return "\n".join(lines)

    def _fmt_fixes(self, fixes: List[Dict]) -> str:
        lines = []
        for f in fixes:
            idx, rid = f.get("index", ""), f.get("risk_id", "")
            name, severity = f.get("risk_name", ""), f.get("severity", "")
            location = f.get("clause_location", "")
            risky = f.get("risky_clause", "")[:120]
            gold = f.get("gold_fix", "")[:250]
            max_s = f.get("max_score", "")
            lines.append(f"\n### 修订项 {idx}（风险 {rid}）：{name}")
            lines.append(f"  严重性：{severity} | 满分：{max_s}")
            if location:
                lines.append(f"  条款位置：{location}")
            lines.append(f"  原风险条款：{risky}...")
            lines.append(f"  参考修订文本：{gold}...")
            checklist = f.get("fix_checklist", [])
            if checklist:
                lines.append("  修订检查清单（逐条核查）：")
                for c in checklist:
                    pt, sc = c.get("point", ""), c.get("score", "")
                    kw = c.get("keywords", [])
                    kw_str = "、".join(kw) if isinstance(kw, list) else str(kw)
                    lines.append(f"    - {pt}（{sc}分）[关键词：{kw_str}]")
        return "\n".join(lines)

    # ─── 辅助 ────────────────────────────────────────────

    @staticmethod
    def _compute_total(rubric: Dict):
        total = rubric.get("total_score")
        if total is not None:
            return total
        if "rubrics" in rubric and isinstance(rubric["rubrics"], list):
            s = sum(m.get("module_score", 0) for m in rubric["rubrics"] if isinstance(m, dict))
            if s > 0:
                return s
        if "fixes" in rubric and isinstance(rubric["fixes"], list):
            s = sum(f.get("max_score", 0) for f in rubric["fixes"] if isinstance(f, dict))
            if s > 0:
                return s
        return "未知"

    @staticmethod
    def _detect_rubric_type(rubric: Dict) -> str:
        if "fixes" in rubric:
            return "risk_revision"
        if "risks" in rubric:
            return "risk_detection"
        if "rubrics" in rubric and isinstance(rubric["rubrics"], list):
            items = rubric["rubrics"]
            if items and "module" in items[0]:
                return "module"
            return "flat"
        return "unknown"

    # ─── 解析 + 按任务分发校验 ─────────────────────────────

    def _parse_and_validate(self, raw: str, rubric: Dict, task_key: str) -> Dict[str, Any]:
        max_score = self._compute_total(rubric)
        if not isinstance(max_score, (int, float)) or max_score <= 0:
            max_score = 100

        # 提取 JSON
        json_str = None
        code_block = re.search(r"```(?:json)?\s*\n?([\s\S]*?)```", raw)
        if code_block:
            json_str = code_block.group(1).strip()
        else:
            m = re.search(r"\{[\s\S]*\}", raw)
            if m:
                json_str = m.group()

        item_scores, total, warnings = [], 0.0, []

        if json_str:
            try:
                parsed = self._normalize_cn_keys(json.loads(json_str))
            except json.JSONDecodeError:
                parsed = None
                warnings.append("judge_json_parse_error")
        else:
            parsed = None

        # 按 task_key 分发到 6 个独立校验方法
        if parsed:
            validator = TASK_VALIDATORS.get(task_key)
            if validator:
                item_scores, total, w = validator(self, parsed, rubric)
            else:
                # 没有专属校验，按 rubric 结构分发
                rtype = self._detect_rubric_type(rubric)
                if rtype == "flat":
                    item_scores, total, w = self._validate_consultation_fact_inquiry(parsed, rubric)
                elif rtype == "module":
                    item_scores, total, w = self._validate_module(parsed, rubric)
                elif rtype == "risk_detection":
                    item_scores, total, w = self._validate_risk_detection(parsed, rubric)
                elif rtype == "risk_revision":
                    item_scores, total, w = self._validate_risk_revision(parsed, rubric)
                else:
                    item_scores, total, w = self._validate_generic(parsed)
            warnings.extend(w)

        # fallback：文本提取
        if not item_scores and total == 0:
            nums = re.findall(r"(\d+(?:\.\d+)?)\s*[/／]\s*\d+", raw)
            if nums:
                total = sum(float(n) for n in nums)
                warnings.append("fallback_slash_extraction")
            else:
                m = re.search(r"[总]分[：:]\s*(\d+(?:\.\d+)?)", raw)
                if m:
                    total = float(m.group(1))
                    warnings.append("fallback_total_extraction")

        return {
            "total_score": total,
            "max_score": max_score,
            "score_ratio": round(total / max_score, 4) if max_score > 0 else 0,
            "item_scores": item_scores,
            "judge_raw": raw,
            "validation": warnings if warnings else "ok",
        }

    # ═══════════════════════════════════════════════════════
    #  6 个任务各自的校验方法
    # ═══════════════════════════════════════════════════════

    # --- consultation_fact_inquiry ---
    # rubric: 平铺 rubrics[{index, points}]
    # 输出: item_scores[{index, score}]
    # 校验: index 一一对应, 0 <= score <= points

    def _validate_consultation_fact_inquiry(self, parsed: Dict, rubric: Dict):
        warnings = []
        expected = {item["index"]: item["points"]
                    for item in rubric.get("rubrics", []) if "index" in item}

        item_scores = parsed.get("item_scores", [])
        if not item_scores:
            warnings.append("no_item_scores_in_response")
            return [], 0.0, warnings

        self._check_indices(expected, item_scores, warnings)
        self._clamp_scores(expected, item_scores, warnings)

        total = sum(s.get("score", 0) for s in item_scores)
        return item_scores, total, warnings

    # --- case_analysis ---
    # rubric: 模块化 rubrics[{module, module_score, items[{index, points}]}]
    # 输出: modules[{module, items[{index, score}], module_total}]
    # 校验: 模块一一对应, index 一一对应, 0 <= score <= points, module_total <= module_score

    def _validate_case_analysis(self, parsed: Dict, rubric: Dict):
        return self._validate_module(parsed, rubric)

    # --- legal_document_generation ---
    # rubric: 模块化，含「统一扣分项」负分模块
    # 输出: modules[{module, items[{index, score}], module_total}]
    # 校验: 同 module + 负分条目 points <= score <= 0

    def _validate_legal_document_generation(self, parsed: Dict, rubric: Dict):
        return self._validate_module(parsed, rubric)

    # --- risk_detection ---
    # rubric: risks[{index, risk_id, points, scoring: {key: {score}}}]
    # 输出: risk_scores[{index, risk_id, sub_scores: {key: {score}}, risk_total}]
    # 校验: risk 一一对应, sub_scores key 完全匹配, 子项不超分, risk_total <= points

    def _validate_risk_detection(self, parsed: Dict, rubric: Dict):
        warnings = []
        expected = {}
        for r in rubric.get("risks", []):
            idx = r.get("index")
            if idx is not None:
                expected[idx] = {
                    "risk_id": r.get("risk_id", ""),
                    "points": r.get("points", 0),
                    "scoring": {k: v.get("score", 0) for k, v in r.get("scoring", {}).items()},
                }

        risk_scores = parsed.get("risk_scores", [])
        if not risk_scores:
            warnings.append("no_risk_scores_in_response")
            return [], 0.0, warnings

        # 风险项匹配
        returned = {s.get("index") for s in risk_scores if s.get("index") is not None}
        missing = set(expected) - returned
        if missing:
            warnings.append(f"missing_risks:{sorted(missing)}")
        extra = returned - set(expected)
        if extra:
            warnings.append(f"extra_risks:{sorted(extra)}")

        item_scores = []
        for rs in risk_scores:
            idx = rs.get("index")
            sub_scores = rs.get("sub_scores", {})
            exp = expected.get(idx, {})
            exp_scoring = exp.get("scoring", {})

            # sub_scores key 匹配
            if exp_scoring:
                mk = set(exp_scoring) - set(sub_scores)
                if mk:
                    warnings.append(f"risk[{idx}] missing_sub_keys:{sorted(mk)}")
                ek = set(sub_scores) - set(exp_scoring)
                if ek:
                    warnings.append(f"risk[{idx}] extra_sub_keys:{sorted(ek)}")

            # 子项 clamp
            for key, sub in sub_scores.items():
                if isinstance(sub, dict):
                    sc = sub.get("score", 0)
                    cap = exp_scoring.get(key, 999)
                    if sc > cap:
                        warnings.append(f"risk[{idx}].{key}: {sc}->{cap}")
                        sub["score"] = cap
                    elif sc < 0:
                        warnings.append(f"risk[{idx}].{key}: {sc}->0")
                        sub["score"] = 0

            # risk_total
            rt = sum(v.get("score", 0) for v in sub_scores.values() if isinstance(v, dict))
            cap_total = exp.get("points", 999)
            if rt > cap_total:
                warnings.append(f"risk[{idx}] total: {rt}->{cap_total}")
                rt = cap_total

            item_scores.append({
                "index": idx,
                "risk_id": rs.get("risk_id", exp.get("risk_id", "")),
                "score": rt,
                "sub_scores": sub_scores,
            })

        total = sum(s["score"] for s in item_scores if s.get("index") in expected)
        return item_scores, total, warnings

    # --- risk_revision ---
    # rubric: fixes[{index, risk_id, max_score, fix_checklist[{point, score}]}]
    # 输出: fix_scores[{index, risk_id, checklist_scores[{point, score}], fix_total}]
    # 校验: fix 一一对应, checklist 条数匹配, 每条不超分, fix_total <= max_score

    def _validate_risk_revision(self, parsed: Dict, rubric: Dict):
        warnings = []
        expected = {}
        for f in rubric.get("fixes", []):
            idx = f.get("index")
            if idx is not None:
                expected[idx] = {
                    "risk_id": f.get("risk_id", ""),
                    "max_score": f.get("max_score", 0),
                    "checklist": f.get("fix_checklist", []),
                }

        fix_scores = parsed.get("fix_scores", [])
        if not fix_scores:
            warnings.append("no_fix_scores_in_response")
            return [], 0.0, warnings

        # 修订项匹配
        returned = {s.get("index") for s in fix_scores if s.get("index") is not None}
        missing = set(expected) - returned
        if missing:
            warnings.append(f"missing_fixes:{sorted(missing)}")
        extra = returned - set(expected)
        if extra:
            warnings.append(f"extra_fixes:{sorted(extra)}")

        item_scores = []
        for fs in fix_scores:
            idx = fs.get("index")
            cl_scores = fs.get("checklist_scores", [])
            exp = expected.get(idx, {})
            exp_cl = exp.get("checklist", [])

            # checklist 条数
            if exp_cl and len(cl_scores) != len(exp_cl):
                warnings.append(f"fix[{idx}] checklist_count:expected={len(exp_cl)},got={len(cl_scores)}")

            # 逐条 clamp
            for i, cs in enumerate(cl_scores):
                sc = cs.get("score", 0)
                cap = exp_cl[i].get("score", 999) if i < len(exp_cl) else 999
                if sc > cap:
                    warnings.append(f"fix[{idx}].cl[{i}]: {sc}->{cap}")
                    cs["score"] = cap
                elif sc < 0:
                    warnings.append(f"fix[{idx}].cl[{i}]: {sc}->0")
                    cs["score"] = 0

            ft = sum(cs.get("score", 0) for cs in cl_scores)
            cap_total = exp.get("max_score", 999)
            if ft > cap_total:
                warnings.append(f"fix[{idx}] total: {ft}->{cap_total}")
                ft = cap_total

            item_scores.append({
                "index": idx,
                "risk_id": fs.get("risk_id", exp.get("risk_id", "")),
                "score": ft,
                "checklist_scores": cl_scores,
            })

        total = sum(s["score"] for s in item_scores if s.get("index") in expected)
        return item_scores, total, warnings

    # --- comprehensive_judgment_prediction ---
    # rubric: 模块化，5 个模块
    # 输出: modules[{module, items[{index, score}], module_total}]
    # 校验: 同 case_analysis

    def _validate_comprehensive_judgment_prediction(self, parsed: Dict, rubric: Dict):
        return self._validate_module(parsed, rubric)

    # --- adversarial 合同（反例）---
    # 基础分制，按误报/误改扣分

    def _validate_adversarial(self, parsed: Dict, rubric: Dict):
        """adversarial detection/revision 通用校验：基础分 - 扣分"""
        warnings = []
        base_score = rubric.get("total_score", 15)

        items = parsed.get("items", [])
        hard_count = sum(1 for it in items if it.get("level", "").startswith("hard"))
        soft_count = sum(1 for it in items if it.get("level", "").startswith("soft"))

        total_penalty = hard_count * 3 + soft_count * 1
        final_score = max(0, base_score - total_penalty)

        claimed_final = parsed.get("final_score")
        if claimed_final is not None and abs(claimed_final - final_score) > 0.01:
            warnings.append(f"final_score_mismatch:claimed={claimed_final},computed={final_score}")

        item_scores = [{
            "hard_count": hard_count,
            "soft_count": soft_count,
            "acceptable_count": len(items) - hard_count - soft_count,
            "total_penalty": total_penalty,
            "score": final_score,
        }]
        return item_scores, final_score, warnings

    def _validate_risk_detection_adversarial(self, parsed: Dict, rubric: Dict):
        return self._validate_adversarial(parsed, rubric)

    def _validate_risk_revision_adversarial(self, parsed: Dict, rubric: Dict):
        return self._validate_adversarial(parsed, rubric)

    # ═══════════════════════════════════════════════════════
    #  共用校验逻辑
    # ═══════════════════════════════════════════════════════

    def _validate_module(self, parsed: Dict, rubric: Dict):
        """模块类 rubric 的通用校验（case_analysis / doc_gen / judgment 共用）"""
        warnings = []

        expected = {}
        module_map = {}
        module_caps = {}
        for mod in rubric.get("rubrics", []):
            mname = mod.get("module", "")
            module_caps[mname] = mod.get("module_score", 0)
            for item in mod.get("items", []):
                idx = item.get("index")
                if idx is not None:
                    expected[idx] = item.get("points", 0)
                    module_map[idx] = mname

        if "modules" not in parsed or not isinstance(parsed.get("modules"), list):
            warnings.append("no_modules_in_response")
            return [], 0.0, warnings

        # 模块名匹配
        returned_modules = {m.get("module") for m in parsed["modules"]}
        missing_mods = set(module_caps) - returned_modules
        if missing_mods:
            warnings.append(f"missing_modules:{sorted(missing_mods)}")

        item_scores = []
        for pm in parsed["modules"]:
            mname = pm.get("module", "")
            for s in pm.get("items", []):
                s["_module"] = mname
                item_scores.append(s)

            # module_total 一致性
            claimed = pm.get("module_total")
            actual = sum(s.get("score", 0) for s in pm.get("items", []))
            if claimed is not None and abs(claimed - actual) > 0.01:
                warnings.append(f"module_total_mismatch:{mname} claimed={claimed},actual={actual}")

        if not item_scores:
            warnings.append("empty_items_in_modules")
            return [], 0.0, warnings

        self._check_indices(expected, item_scores, warnings)
        self._clamp_scores(expected, item_scores, warnings)

        # 模块小计校验
        mod_totals = {}
        for s in item_scores:
            mname = s.get("_module") or module_map.get(s.get("index"), "")
            if mname:
                mod_totals[mname] = mod_totals.get(mname, 0) + s.get("score", 0)
        for mname, mt in mod_totals.items():
            mcap = module_caps.get(mname, 0)
            if mcap > 0 and mt > mcap:
                warnings.append(f"module_overflow:{mname} {mt}>{mcap}")

        total = sum(s.get("score", 0) for s in item_scores)
        return item_scores, total, warnings

    def _validate_generic(self, parsed: Dict):
        warnings = []
        if "item_scores" in parsed:
            item_scores = parsed["item_scores"]
            total = sum(s.get("score", 0) for s in item_scores)
        elif "total_score" in parsed:
            total = float(parsed["total_score"])
            item_scores = parsed.get("details", [])
        else:
            item_scores, total = [], 0.0
            for k, v in parsed.items():
                if isinstance(v, (int, float)):
                    item_scores.append({"index": k, "score": v})
                    total += v
        if not item_scores:
            warnings.append("no_scores_found")
        return item_scores, total, warnings

    # ─── 校验工具方法 ────────────────────────────────────

    @staticmethod
    def _check_indices(expected: Dict, item_scores: List[Dict], warnings: List):
        returned = {s.get("index") for s in item_scores if s.get("index") is not None}
        missing = set(expected) - returned
        if missing:
            warnings.append(f"missing_indices:{sorted(missing)}")
        extra = returned - set(expected)
        if extra:
            warnings.append(f"extra_indices:{sorted(extra)}")
        if len(item_scores) != len(expected):
            warnings.append(f"count:expected={len(expected)},got={len(item_scores)}")

    @staticmethod
    def _clamp_scores(expected: Dict, item_scores: List[Dict], warnings: List):
        for s in item_scores:
            idx, sc = s.get("index"), s.get("score", 0)
            if idx in expected:
                cap = expected[idx]
                if cap >= 0 and sc > cap:
                    warnings.append(f"clamped:[{idx}] {sc}->{cap}")
                    s["score"] = cap
                elif cap >= 0 and sc < 0:
                    warnings.append(f"clamped:[{idx}] {sc}->0")
                    s["score"] = 0
                elif cap < 0 and sc < cap:
                    warnings.append(f"clamped:[{idx}] {sc}->{cap}")
                    s["score"] = cap
                elif cap < 0 and sc > 0:
                    warnings.append(f"clamped:[{idx}] {sc}->0")
                    s["score"] = 0

    @staticmethod
    def _normalize_cn_keys(d: Dict) -> Dict:
        MAP = {
            "总分": "total_score", "评分项": "item_scores",
            "得分": "score", "理由": "reason", "分数": "score",
            "评价": "comment", "总体评价": "comment", "详情": "details",
        }
        out = {}
        for k, v in d.items():
            ek = MAP.get(k, k)
            if isinstance(v, list):
                out[ek] = [LLMJudge._normalize_cn_keys(i) if isinstance(i, dict) else i for i in v]
            elif isinstance(v, dict):
                out[ek] = LLMJudge._normalize_cn_keys(v)
            else:
                out[ek] = v
        return out


# ─── 6 个任务 → 校验方法映射 ─────────────────────────────

TASK_VALIDATORS = {
    "consultation_fact_inquiry": LLMJudge._validate_consultation_fact_inquiry,
    "case_analysis": LLMJudge._validate_case_analysis,
    "legal_document_generation": LLMJudge._validate_legal_document_generation,
    "risk_detection": LLMJudge._validate_risk_detection,
    "risk_revision": LLMJudge._validate_risk_revision,
    "risk_detection_adversarial": LLMJudge._validate_risk_detection_adversarial,
    "risk_revision_adversarial": LLMJudge._validate_risk_revision_adversarial,
    "comprehensive_judgment_prediction": LLMJudge._validate_comprehensive_judgment_prediction,
}
