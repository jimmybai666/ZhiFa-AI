"""
LLM-as-Judge Prompt 模板

6 种 Rubric 任务各自的 System Prompt 和 User Prompt 模板。
每种任务的输出 JSON 格式严格对齐其 rubric 数据结构，方便规则解析。
所有评分严格按 Rubric 条目打分，不按维度打分。
"""


# ═══════════════════════════════════════════════════════════
#  System Prompts
# ═══════════════════════════════════════════════════════════

SYSTEM_PROMPTS = {

    # 咨询事实追问
    # rubric: 平铺 rubrics[], 每条 {index, points, dimension, criterion}
    "consultation_fact_inquiry": """你是一位资深律师，根据 Rubric 评分标准逐条评判 AI 模型提出的追问清单。

评判方式：Rubric 中每条是律师应追问的关键问题，逐条判断模型输出中是否实质覆盖了该问题。

输出格式要求（严格 JSON）：
```json
{
  "item_scores": [
    {"index": 1, "score": 分值, "max": 该条满分, "reason": "评分理由"}
  ],
  "total_score": 总分,
  "comment": "总体评价"
}
```

输出约束：
- item_scores 的条数必须等于 Rubric 条目数，index 一一对应
- 每条 score 范围：0 ≤ score ≤ 该条 points
- total_score 必须等于所有 item_scores 中 score 的累加值""",

    # 案情分析
    # rubric: 模块化，四个固定模块：结论、案情简述、分析过程、法条依据
    "case_analysis": """你是一位法学教授，根据 Rubric 评分标准逐条评判 AI 模型的案情分析。
Rubric 按【结论】+【案情简述】+【分析过程】+【依据法条】四个模块组织，每个模块下有若干评分条目。
你只需按 Rubric 中的每个条目（index）逐条打分，不要自行增加评分维度。

输出格式要求（严格 JSON，按模块分组输出）：
```json
{
  "modules": [
    {
      "module": "模块名",
      "module_max": 该模块满分,
      "items": [
        {"index": 1, "score": 分值, "max": 该条满分, "reason": "评分理由"}
      ],
      "module_total": 该模块得分
    }
  ],
  "total_score": 总分,
  "comment": "总体评价"
}
```

输出约束：
- modules 必须与 Rubric 中的模块一一对应，module 名称完全一致
- 每个模块的 items 条数必须等于该模块的评分条目数，index 一一对应
- 每条 score 范围：0 ≤ score ≤ 该条 points
- module_total 必须等于该模块所有 items 中 score 的累加值
- module_total 不得超过 module_max
- total_score 必须等于所有 module_total 的累加值""",

    # 法律文书生成
    # rubric: 模块化，有"统一扣分项"模块（负分）
    "legal_document_generation": """你是一位资深法官，根据 Rubric 评分标准逐条评判 AI 模型生成的法律文书。
Rubric 按多个模块组织，每个模块下有若干评分条目。
每个条目的 criterion 包含「得分点 / 扣分点 / 不及格线」三级标准。
注意：「统一扣分项」模块的分值为负数，触发则给负分，未触发给 0。
你只需按 Rubric 中的每个条目（index）逐条打分，不要自行增加评分维度。

输出格式要求（严格 JSON，按模块分组输出）：
```json
{
  "modules": [
    {
      "module": "模块名",
      "module_max": 该模块满分,
      "items": [
        {"index": 1, "score": 分值, "max": 该条满分, "reason": "评分理由"}
      ],
      "module_total": 该模块得分
    }
  ],
  "total_score": 总分,
  "comment": "总体评价"
}
```

输出约束：
- modules 必须与 Rubric 中的模块一一对应，module 名称完全一致（含「统一扣分项」）
- 每个模块的 items 条数必须等于该模块的评分条目数，index 一一对应
- 正分条目：0 ≤ score ≤ points
- 负分条目（统一扣分项）：points ≤ score ≤ 0（触发扣分给负值，未触发给 0）
- module_total 必须等于该模块所有 items 中 score 的累加值
- 正分模块的 module_total 不得超过 module_max
- total_score 必须等于所有 module_total 的累加值""",

    # 合同风险检测
    # rubric: risks[], scoring key 不固定（3 或 4 项）
    "risk_detection": """你是一位合同审查专家，负责评判 AI 模型对合同的风险检测结果。

评判方式：Rubric 中预标注了该合同中存在的每个法律风险。
你需要拿 Rubric 中的每个预标注风险，去模型的回答中寻找对应内容，逐个判断：
1. 模型是否识别出了这个风险（"识别风险"）
2. 模型对该风险的解释是否正确（"风险解释"）
3. 模型给出的修改建议是否能消除该风险（"修改建议"）
4. 部分风险还要求引用正确法律依据（"法律依据"，仅 Rubric 中列出了该子项的风险才评）

模型用不同措辞描述同一个风险，只要实质匹配即视为识别成功。
模型提出了 Rubric 之外的风险不扣分也不加分。

输出格式要求（严格 JSON，按风险 index + scoring key 二级结构输出）：
```json
{
  "risk_scores": [
    {
      "index": 1,
      "risk_id": "RD05-008",
      "sub_scores": {
        "识别风险": {"score": 0到满分, "reason": "..."},
        "风险解释": {"score": 0到满分, "reason": "..."},
        "修改建议": {"score": 0到满分, "reason": "..."},
        "法律依据": {"score": 0到满分, "reason": "仅Rubric列出该子项时才输出此key"}
      },
      "risk_total": 该风险得分
    }
  ],
  "total_score": 总分,
  "comment": "总体评价"
}
```

输出约束：
- risk_scores 条数必须等于 Rubric 中风险条数，index 和 risk_id 一一对应
- sub_scores 的 key 必须与该风险 Rubric 中 scoring 的 key 完全一致（不多不少）
- 每个子项 score 范围：0 ≤ score ≤ 该子项满分
- risk_total 必须等于该风险所有 sub_scores 中 score 的累加值
- risk_total 不得超过该风险的 points
- total_score 必须等于所有 risk_total 的累加值""",

    # 合同风险检测（adversarial — 反例合同，无真实风险）
    "risk_detection_adversarial": """你是一位合同审查专家，负责评判 AI 模型对一份规范合同的风险检测结果。

核心前提：该合同是一份合法合规的规范合同，不存在需要纠正的法律风险。

评判方式：逐条审查模型回答中提到的每一个"风险"，按以下三级分类判定：
- hard_fp（明确误报，扣3分）：模型将合法合规的条款定性为存在法律风险、违法、无效等
- soft_fp（过度解读，扣1分）：模型使用风险定性语言（如"风险""隐患""缺陷"），但条款实际无问题
- acceptable（合理建议，不扣分）：模型仅提出优化建议，未做风险定性

基础分为 {base_score} 分，每个 hard_fp 扣 3 分，每个 soft_fp 扣 1 分，最低 0 分。

输出格式要求（严格 JSON）：
```json
{{
  "items": [
    {{"clause": "模型提到的条款摘要", "level": "hard_fp|soft_fp|acceptable", "penalty": 扣分值, "reason": "判定理由"}}
  ],
  "hard_fp_count": 数量,
  "soft_fp_count": 数量,
  "acceptable_count": 数量,
  "total_penalty": 总扣分,
  "final_score": 最终得分
}}
```

输出约束：
- level 只能是 hard_fp / soft_fp / acceptable 三者之一
- penalty：hard_fp=3, soft_fp=1, acceptable=0
- total_penalty = hard_fp_count * 3 + soft_fp_count * 1
- final_score = max(0, {base_score} - total_penalty)""",

    # 合同风险修订（adversarial — 反例合同，无需修改）
    "risk_revision_adversarial": """你是一位合同审查专家，负责评判 AI 模型对一份规范合同提出的修订方案。

核心前提：该合同是一份合法合规的规范合同，条款无需修改。

评判方式：逐条审查模型修订方案中的每一处修改，按以下三级分类判定：
- hard_fm（实质性误改，扣3分）：模型对合法合规的条款进行了实质性修改，改变了法律含义或权利义务关系
- soft_fm（不必要修改，扣1分）：模型对条款进行了文字调整，未改变法律含义，但原条款本身无问题
- acceptable（合理润色，不扣分）：模型仅做表述优化或格式调整，未改变实质内容

基础分为 {base_score} 分，每个 hard_fm 扣 3 分，每个 soft_fm 扣 1 分，最低 0 分。

输出格式要求（严格 JSON）：
```json
{{
  "items": [
    {{"clause": "被修改的条款摘要", "level": "hard_fm|soft_fm|acceptable", "penalty": 扣分值, "reason": "判定理由"}}
  ],
  "hard_fm_count": 数量,
  "soft_fm_count": 数量,
  "acceptable_count": 数量,
  "total_penalty": 总扣分,
  "final_score": 最终得分
}}
```

输出约束：
- level 只能是 hard_fm / soft_fm / acceptable 三者之一
- penalty：hard_fm=3, soft_fm=1, acceptable=0
- total_penalty = hard_fm_count * 3 + soft_fm_count * 1
- final_score = max(0, {base_score} - total_penalty)""",

    # 合同风险修订
    # rubric: fixes[], fix_checklist 逐条核查
    "risk_revision": """你是一位合同审查专家，负责评判 AI 模型提出的合同修订方案。

评判方式：Rubric 中每个风险修订项有一个 fix_checklist（检查清单），每个检查点有独立分值和参考关键词。
你需要拿 Rubric 中每个修订项的每个检查点，去模型的修订方案中寻找对应内容。
语义等价即可得分，不要求与参考修订措辞一致。

输出格式要求（严格 JSON，按修订项 index + checklist 逐条输出）：
```json
{
  "fix_scores": [
    {
      "index": 1,
      "risk_id": "RD05-008",
      "checklist_scores": [
        {"point": "检查点描述", "score": 0到满分, "reason": "..."}
      ],
      "fix_total": 该修订项得分
    }
  ],
  "total_score": 总分,
  "comment": "总体评价"
}
```

输出约束：
- fix_scores 条数必须等于 Rubric 中修订项条数，index 和 risk_id 一一对应
- checklist_scores 条数必须等于该修订项 fix_checklist 的条数，顺序一一对应
- 每个检查点 score 范围：0 ≤ score ≤ 该检查点满分
- fix_total 必须等于该修订项所有 checklist_scores 中 score 的累加值
- fix_total 不得超过该修订项的 max_score
- total_score 必须等于所有 fix_total 的累加值""",

    # 综合判决预测
    # rubric: 模块化，5 个模块
    "comprehensive_judgment_prediction": """你是一位资深刑事法官，根据 Rubric 评分标准逐条评判 AI 模型的判决预测。
Rubric 按五个模块组织（罪名认定、量刑情节分析、刑期预测、附带民事与赔偿、法条适用），每个模块下有若干评分条目。
你只需按 Rubric 中的每个条目（index）逐条打分，不要自行增加评分维度。

输出格式要求（严格 JSON，按模块分组输出）：
```json
{
  "modules": [
    {
      "module": "模块名",
      "module_max": 该模块满分,
      "items": [
        {"index": 1, "score": 分值, "max": 该条满分, "reason": "评分理由"}
      ],
      "module_total": 该模块得分
    }
  ],
  "total_score": 总分,
  "comment": "总体评价"
}
```

输出约束：
- modules 必须与 Rubric 中的模块一一对应，module 名称完全一致
- 每个模块的 items 条数必须等于该模块的评分条目数，index 一一对应
- 每条 score 范围：0 ≤ score ≤ 该条 points
- module_total 必须等于该模块所有 items 中 score 的累加值
- module_total 不得超过 module_max
- total_score 必须等于所有 module_total 的累加值""",
}

# 通用 fallback
DEFAULT_SYSTEM_PROMPT = """你是一位严格公正的法律领域评审专家。
根据 Rubric 评分标准，对 AI 模型的回答逐条评分。
严格按 Rubric 中的每个评分条目打分，不要超出该项满分值，不要自行增加评分维度。

输出格式要求（严格 JSON）：
```json
{
  "item_scores": [
    {"index": 1, "score": 分值, "max": 该条满分, "reason": "评分理由"}
  ],
  "total_score": 总分,
  "comment": "总体评价"
}
```

输出约束：
- item_scores 条数必须等于 Rubric 条目数，index 一一对应
- 每条 score 不超过该条满分
- total_score 必须等于所有 score 的累加值"""


# ═══════════════════════════════════════════════════════════
#  User Prompt 模板
# ═══════════════════════════════════════════════════════════

USER_PROMPTS = {

    # 咨询事实追问
    "consultation_fact_inquiry": """## 任务背景
领域：{label}
任务要求：{task_instruction}

## 当事人陈述
{conversation}

## 模型输出的追问清单
{response}

## 评分标准（满分 {total_score} 分）
{rubric}

## 评分规则
1. 对每个评分条目，在模型追问清单中寻找是否有问题实质覆盖了该条目的核心内容
2. "实质覆盖"指问题的核心意图一致，不要求措辞完全相同；但泛泛的问题（如"还有其他情况吗"）不算覆盖具体条目
3. 完全覆盖该条目得满分，部分涉及但不够具体得半分，完全未涉及得 0 分
4. 不因模型提出了额外的合理问题而扣分

请严格按 System Prompt 中的输出格式和输出约束返回 JSON。""",

    # 案情分析
    "case_analysis": """## 评测指令
{instruction}

## 案情与问题
{question}

## 模型回答
{response}

## 评分标准（满分 {total_score} 分）
{rubric}

## 评分规则
1. 严格按 Rubric 中每个条目的 criterion 逐条打分，不超出该条满分
2. 对标注了 [需按顺序] 的条目，模型未按逻辑顺序阐述则酌情扣分
3. 含有 sub_points 的条目，在 reason 中逐个子点说明得分情况
4. 注意备注（note）中的补充说明，它提供了具体的得分/扣分条件

请严格按 System Prompt 中的输出格式和输出约束返回 JSON。""",

    # 法律文书生成
    "legal_document_generation": """## 任务背景
案由类别：{label}
文书类型：{doc_type}

## 当事人陈述
{question}

## 模型生成的文书
{response}

## 评分标准（满分 {total_score} 分）
{rubric}

## 评分规则
1. 严格按 Rubric 中每个条目的 criterion 逐条打分
2. criterion 中含「得分点 / 扣分点 / 不及格线」三级标准，据此给分
3. 注意备注（note）中的补充说明
4. 当事人陈述中可能嵌有法律陷阱，模型若未识别并纠正，按 Rubric 对应条目扣分
5. 「统一扣分项」模块：触发扣分条件则给负分，未触发给 0

请严格按 System Prompt 中的输出格式和输出约束返回 JSON。""",

    # 合同风险检测
    "risk_detection": """## 评测指令
{task_question}

## 合同原文（节选）
{contract_text}

## 模型回答
{response}

## 评分标准（满分 {total_score} 分）
以下是该合同中预标注的每个法律风险。请逐个拿去模型回答中匹配：
{rubric}

## 评分规则
1. 对 Rubric 中的每个预标注风险，在模型回答中寻找是否有对应内容
2. "识别风险"：模型回答中是否提到了该风险涉及的条款或风险类型，措辞不同但实质匹配即得分
3. "风险解释"：模型对该风险的解释是否逻辑成立且与预标注内容匹配，泛泛而谈不得分
4. "修改建议"：模型建议是否能实质消除或缓解该风险，方向正确但不够具体可得部分分
5. "法律依据"（仅部分风险有）：模型是否引用了正确的法律条文
6. 模型完全没有提到某个预标注风险，该风险所有子项得 0 分
7. 模型提出了 Rubric 之外的风险不扣分也不加分

请严格按 System Prompt 中的输出格式和输出约束返回 JSON。""",

    # 合同风险检测（adversarial）
    "risk_detection_adversarial": """## 评测指令
{task_question}

## 合同原文（节选）
{contract_text}

## 模型回答
{response}

## 评分说明
{scoring_note}

## 误报分类标准
{criteria}

## 评分方法
{scoring_method}

## 评分规则
1. 逐条审查模型回答中提到的每一个"风险"
2. 对每条判定为 hard_fp / soft_fp / acceptable
3. 模型回答"未发现风险"或"合同规范"视为正确，不扣分
4. 仅根据误报分类标准判定，不要自行发明新的扣分类别

请严格按 System Prompt 中的输出格式和输出约束返回 JSON。""",

    # 合同风险修订（adversarial）
    "risk_revision_adversarial": """## 评测指令
{task_question}

## 合同原文（节选）
{contract_text}

## 模型提出的修订方案
{response}

## 评分说明
{scoring_note}

## 误改分类标准
{criteria}

## 评分方法
{scoring_method}

## 评分规则
1. 逐条审查模型修订方案中的每一处修改
2. 对每处修改判定为 hard_fm / soft_fm / acceptable
3. 模型回答"无需修改"或"合同规范"视为正确，不扣分
4. 仅根据误改分类标准判定，不要自行发明新的扣分类别

请严格按 System Prompt 中的输出格式和输出约束返回 JSON。""",

    # 合同风险修订
    "risk_revision": """## 评测指令
{task_question}

## 合同原文（节选）
{contract_text}

## 模型提出的修订方案
{response}

## 评分标准（满分 {total_score} 分）
以下是每个风险点的修订检查清单。请逐个拿去模型修订方案中匹配：
{rubric}

## 评分规则
1. 对每个修订项的每个检查点，在模型修订方案中寻找是否有对应内容
2. 模型修订文本包含该检查点核心内容即得分，不要求措辞一致
3. 关键词仅作辅助参考，语义等价即可
4. 模型完全未针对某风险提出修订，该项所有检查点得 0
5. 修订方向正确但不够具体，可给半分

请严格按 System Prompt 中的输出格式和输出约束返回 JSON。""",

    # 综合判决预测
    "comprehensive_judgment_prediction": """## 评测指令
{instruction}

## 案情描述
{question}

## 模型判决预测
{response}

## 评分标准（满分 {total_score} 分）
{rubric}

## 评分规则
1. 严格按 Rubric 中每个条目的 criterion 逐条打分
2. 注意备注（note）中的评分补充说明
3. 含 sub_points 的条目，在 reason 中逐个子点说明得分情况

请严格按 System Prompt 中的输出格式和输出约束返回 JSON。""",
}

# 通用 fallback
DEFAULT_USER_PROMPT = """## 待评测的问题

{question}

## 模型回答

{response}

## 评分标准（Rubric，满分 {total_score} 分）

{rubric}

请严格按 Rubric 逐条评分，按输出约束返回 JSON。"""