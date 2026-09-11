"""
Objective scorers for ZhiFa-Eval.

Each scorer: score(prediction, reference, **kw) -> Dict[str, float]
"""

import re
import math
from typing import Dict, List, Set
from collections import Counter


# ---- Text normalization ----

CN_NUM = {"零":0,"一":1,"二":2,"三":3,"四":4,"五":5,
          "六":6,"七":7,"八":8,"九":9,"十":10,
          "十一":11,"十二":12,"十五":15,"二十":20,"三十":30}

def _cn_to_num(s):
    s = s.strip()
    if s in CN_NUM:
        return CN_NUM[s]
    if re.match(r"\d+", s):
        return float(s)
    total = 0
    if "十" in s:
        parts = s.split("十")
        tens = CN_NUM.get(parts[0], 1) if parts[0] else 1
        ones = CN_NUM.get(parts[1], 0) if len(parts) > 1 and parts[1] else 0
        total = tens * 10 + ones
    return float(total) if total else 0.0


def _chinese_tokenize(text):
    return list(text.strip())


def _normalize(text):
    text = text.strip().lower()
    text = re.sub(r"\s+", "", text)
    # Remove CJK punctuation (U+3000-U+303F), fullwidth forms (U+FF00-U+FFEF), ASCII punct
    text = re.sub(r"[　-〿＀-￯.,;:!?\"'()\[\]{}\-]", "", text)
    return text


def _strip_answer_prefix(text):
    text = text.strip()
    m = re.search(r"\[(?:答案|回答|法条|罪名|刑期|类别|争议焦点)\]\s*(.+?)(?:<eoa>|$)", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    text = re.sub(r"^(答案|回答|法条|罪名|刑期|类别)\s*[:：]\s*", "", text)
    text = re.sub(r"^答案是\s*", "", text)
    return text.strip()


# ---- Option extraction (ABCD) ----

def _extract_options(text):
    """Extract option letters. Accepts A-Z in patterns, keeps only A-E."""
    text = text.strip()
    raw = None
    m = re.search(r"\[正确答案\]\s*([A-Za-z]+)", text)
    if m:
        raw = m.group(1).upper()
    if not raw:
        m = re.search(r"正确答案\s*[：:是为]\s*([A-Za-z]+)", text)
        if m:
            raw = m.group(1).upper()
    if not raw:
        m = re.search(r"(?:答案|选择?)\s*[：:是为]?\s*([A-Za-z]+)", text)
        if m:
            raw = m.group(1).upper()
    if not raw:
        if re.search(r"\[类别\]", text):
            return set()
        m = re.match(r"^([A-Za-z]+)\s*[。.\s]*$", text.strip())
        if m:
            raw = m.group(1).upper()
    if not raw and len(text) < 50:
        found = re.findall(r"(?<![a-zA-Z])([A-Za-z])(?![a-zA-Z])", text)
        if found:
            raw = "".join(f.upper() for f in found)
    if not raw:
        return set()
    valid = {c for c in raw if c in "ABCDE"}
    # If any letter outside A-E appeared, treat as invalid answer
    if len(valid) < len(raw):
        return set()
    return valid


# ---- Category extraction ----

def _extract_category(text):
    text = text.strip()
    # [类别]婚姻家庭<eoa>
    m = re.search(r"\[类别\]\s*(.+?)(?:<eoa>|$)", text)
    if m:
        return _normalize(m.group(1))
    # [争议焦点]责任承担<eoa>
    m = re.search(r"\[争议焦点\]\s*(.+?)(?:<eoa>|$)", text)
    if m:
        return _normalize(m.group(1))
    # 争议焦点类别：合同效力。
    m = re.search(r"争议焦点类别\s*[：:]\s*(.+?)(?:[。.\s]|$)", text)
    if m:
        return _normalize(m.group(1))
    # 类别：婚姻家庭
    m = re.search(r"类别\s*[：:]\s*(.+?)(?:[。.\s]|$)", text)
    if m:
        return _normalize(m.group(1))
    # Bare text fallback
    return _normalize(_strip_answer_prefix(text).split("\n")[0])


# ---- Item extraction ----

def _extract_articles(text):
    text = _strip_answer_prefix(text)
    numbers = re.findall(r"(\d+)", text)
    return set(numbers) if numbers else set()


def _extract_crimes(text):
    text = _strip_answer_prefix(text)
    items = re.split(r"[;；、\n,，]+", text)
    result = set()
    for item in items:
        item = _normalize(item)
        if not item:
            continue
        item = re.sub(r"罪$", "", item)
        if item:
            result.add(item)
    return result


def _extract_months(text):
    text = _strip_answer_prefix(text)
    if re.search(r"死刑", text):
        return 360
    if re.search(r"无期徒刑", text):
        return 300
    years, months = 0.0, 0.0
    ym = re.search(r"(\d+)\s*年", text)
    mm = re.search(r"(\d+)\s*(?:个月|月)", text)
    if ym:
        years = float(ym.group(1))
    if mm:
        months = float(mm.group(1))
    if years == 0 and months == 0:
        ym = re.search(r"([一二三四五六七八九十]+)\s*年", text)
        mm = re.search(r"([一二三四五六七八九十]+)\s*(?:个月|月)", text)
        if ym:
            years = _cn_to_num(ym.group(1))
        if mm:
            months = _cn_to_num(mm.group(1))
    total = years * 12 + months
    if total == 0:
        nm = re.search(r"(\d+(?:\.\d+)?)", text)
        if nm:
            total = float(nm.group(1))
    return total


# ==== Scoring functions ====

def _option_accuracy(prediction, reference, valid_range):
    """Core option scoring. valid_range: 'ABCD' or 'ABCDE'."""
    ref_opts = _extract_options(reference)
    pred_opts = _extract_options(prediction)
    # Prediction contains letters outside valid range -> 0
    if pred_opts and any(c not in valid_range for c in pred_opts):
        return 0.0
    if not ref_opts:
        return 0.0
    if len(ref_opts) == 1:
        return 1.0 if pred_opts == ref_opts else 0.0
    else:
        if not pred_opts:
            return 0.0
        tp = len(pred_opts & ref_opts)
        p = tp / len(pred_opts)
        r = tp / len(ref_opts)
        return round(2 * p * r / (p + r), 4) if (p + r) > 0 else 0.0


def accuracy_abcd(prediction, reference, **kw):
    """legal_knowledge_mcqa: A-D only, E+ invalid."""
    return {"accuracy": _option_accuracy(prediction, reference, "ABCD")}


def accuracy_abcde(prediction, reference, **kw):
    """argument_understanding: A-E."""
    return {"accuracy": _option_accuracy(prediction, reference, "ABCDE")}


def accuracy_category(prediction, reference, **kw):
    """issue_understanding: category name matching."""
    ref_cat = _extract_category(reference)
    pred_cat = _extract_category(prediction)
    if not ref_cat:
        return {"accuracy": 0.0}
    return {"accuracy": 1.0 if pred_cat == ref_cat else 0.0}


def accuracy_score(prediction, reference, **kw):
    """Generic fallback: auto-detect option vs category."""
    ref_opts = _extract_options(reference)
    if ref_opts and all(c in "ABCDE" for c in ref_opts):
        return {"accuracy": _option_accuracy(prediction, reference, "ABCDE")}
    return accuracy_category(prediction, reference, **kw)


def f1_score(prediction, reference, **kw):
    if re.search(r"(?:刑法|第|条|法条)", reference):
        pred_items = _extract_articles(prediction)
        ref_items = _extract_articles(reference)
    else:
        pred_items = _extract_crimes(prediction)
        ref_items = _extract_crimes(reference)
    if not ref_items:
        return {"f1": 0.0, "precision": 0.0, "recall": 0.0}
    tp = len(pred_items & ref_items)
    p = tp / len(pred_items) if pred_items else 0.0
    r = tp / len(ref_items)
    f1 = 2 * p * r / (p + r) if (p + r) > 0 else 0.0
    return {"f1": f1, "precision": p, "recall": r}


def exact_match_score(prediction, reference, **kw):
    p = _normalize(_strip_answer_prefix(prediction))
    r = _normalize(_strip_answer_prefix(reference))
    return {"exact_match": 1.0 if p == r else 0.0}


def _lcs_length(x, y):
    m, n = len(x), len(y)
    if m == 0 or n == 0:
        return 0
    prev = [0] * (n + 1)
    for i in range(1, m + 1):
        curr = [0] * (n + 1)
        for j in range(1, n + 1):
            if x[i - 1] == y[j - 1]:
                curr[j] = prev[j - 1] + 1
            else:
                curr[j] = max(prev[j], curr[j - 1])
        prev = curr
    return prev[n]


def rouge_l_score(prediction, reference, **kw):
    pt = _chinese_tokenize(_normalize(_strip_answer_prefix(prediction)))
    rt = _chinese_tokenize(_normalize(_strip_answer_prefix(reference)))
    if not rt or not pt:
        return {"rouge_l": 0.0}
    lcs = _lcs_length(pt, rt)
    p = lcs / len(pt)
    r = lcs / len(rt)
    f1 = 2 * p * r / (p + r) if (p + r) > 0 else 0.0
    return {"rouge_l": f1}


def rc_f1_score(prediction, reference, **kw):
    pt = _chinese_tokenize(_normalize(_strip_answer_prefix(prediction)))
    rt = _chinese_tokenize(_normalize(_strip_answer_prefix(reference)))
    if not rt:
        return {"rc_f1": 0.0}
    common = Counter(pt) & Counter(rt)
    nc = sum(common.values())
    if nc == 0:
        return {"rc_f1": 0.0}
    p = nc / len(pt) if pt else 0.0
    r = nc / len(rt)
    f1 = 2 * p * r / (p + r) if (p + r) > 0 else 0.0
    return {"rc_f1": f1}


def f05_score(prediction, reference, **kw):
    pt = _chinese_tokenize(_normalize(prediction))
    rt = _chinese_tokenize(_normalize(reference))
    if not rt:
        return {"f05": 0.0}
    common = Counter(pt) & Counter(rt)
    nc = sum(common.values())
    if nc == 0:
        return {"f05": 0.0}
    p = nc / len(pt) if pt else 0.0
    r = nc / len(rt)
    beta_sq = 0.25
    f05 = (1 + beta_sq) * p * r / (beta_sq * p + r) if (beta_sq * p + r) > 0 else 0.0
    return {"f05": f05}


def nlog_distance_score(prediction, reference, **kw):
    pm = _extract_months(prediction)
    rm = _extract_months(reference)
    if rm == 0 and pm == 0:
        return {"nlog_distance": 1.0}
    diff = abs(pm - rm)
    mx = max(pm, rm, 1)
    s = 1.0 - math.log(1 + diff) / math.log(1 + mx)
    return {"nlog_distance": max(0.0, s)}


def em_rouge_combined_score(prediction, reference, **kw):
    """EM-priority combined score for factual_query.
    Exact match -> 1.0, otherwise Rouge-L * 0.8 as partial credit."""
    em = exact_match_score(prediction, reference)["exact_match"]
    if em == 1.0:
        return {"score": 1.0, "exact_match": 1.0, "rouge_l": 1.0}
    rl = rouge_l_score(prediction, reference)["rouge_l"]
    return {"score": round(rl * 0.8, 4), "exact_match": 0.0, "rouge_l": rl}


METRIC_FUNCTIONS = {
    "Accuracy": accuracy_score,
    "Accuracy-ABCD": accuracy_abcd,
    "Accuracy-ABCDE": accuracy_abcde,
    "Accuracy-Category": accuracy_category,
    "F1": f1_score,
    "EM": exact_match_score,
    "EM+Rouge-L": em_rouge_combined_score,
    "Rouge-L": rouge_l_score,
    "rc-F1": rc_f1_score,
    "F0.5": f05_score,
    "nLog-distance": nlog_distance_score,
}
