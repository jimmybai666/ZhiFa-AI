# ZhiFa-Bench

## 1. 概述

ZhiFa-Bench 是一套面向中文法律场景的开源评测基准，服务于**智法AI**评测体系，覆盖**法律问答（10 个子任务，2,300 条）、合同审查（3 个子任务，320 条）、案情预测（4 个子任务，1,150 条）**共 17 个子任务。评测方式兼顾客观评分（规则精确匹配、NLI 蕴含检测）与主观评分（LLM-as-Judge），围绕事实准确性、法条引用正确性、证据可追溯性、法律推理逻辑性、完整性、安全合规性、用户可理解性 7 个维度展开。

当前中文法律领域的开源评测资源稀缺，尤其是合同审查、法律文书生成等方向几乎没有公开标注数据。ZhiFa-Bench 整理清洗了多个已有数据集，并自行构造了缺失部分的评测样本与评分标准，形成一套可直接复用的中文法律 AI benchmark。

样本数据整理改编自 CAIL 系列、JEC_QA、裁判文书网等多个公开数据集，并结合项目组自行构造的 Rubric 评分样本（合同审查、案情分析、文书生成、综合判决预测等）与对抗性样本，涵盖民事、刑事、行政等主要领域。评测框架的设计环节部分参考借鉴了 LawBench、PLawBench、Legal-Eval 等已有 benchmark 的工作。

为充分评估**智法AI**的真实能力边界，部分子任务在 standard（常规样本）之外额外构建了两档样本：

- **challenge（难例）**：在常规题基础上提升难度，要求更深层次的法律理解与推理。
- **adversarial（反例）**：提升辨识度，考察模型能否区分"正确"与"貌似正确"。

---

## 2. 目录结构

```
datasets/
├── Legal_QA/                          # 法律问答
│   ├── memorization/                  # 记忆层
│   │   ├── factual_query/             # 法条事实查询 (100 standard)
│   │   ├── legal_knowledge_mcqa/      # 法律知识选择题 (150 standard + 50 challenge)
│   │   └── statute_recitation/        # 法条背诵 (100 standard + 50 challenge)
│   ├── understanding/                 # 理解层
│   │   ├── reading_comprehension/     # 阅读理解 (200 standard)
│   │   ├── argument_understanding/    # 论点理解 (200 standard)
│   │   ├── issue_understanding/       # 争议焦点识别
│   │   │   ├── legal_consultation/    # 法律咨询类 (150 standard + 50 challenge + 50 adversarial)
│   │   │   └── disputed_issues/       # 争议焦点类 (150 standard + 50 challenge + 50 adversarial)
│   │   └── case_summarization/        # 案情摘要 (300 standard + 100 challenge + 100 adversarial)
│   └── application/                   # 应用层
│       ├── consultation_fact_inquiry/ # 咨询事实追问 (50 standard)
│       ├── case_analysis/             # 案情分析 (100 standard + 25 challenge + 25 adversarial)
│       └── legal_document_generation/ # 法律文书生成 (50 standard + 25 challenge)  ← 起诉状/答辩状等
│
├── Contract_Review/                   # 合同审查
│   ├── clause_correction/             # 条款纠错 (200 standard)
│   └── contract_risk_detection_and_revision/  # 风险检测与修订
│       ├── risk_checklist.json        # 风险清单（169 项）
│       ├── standard/                  # 80 份合同 + rubric
│       │   ├── contracts/             #   合同原文 (.md)
│       │   ├── rubric_detection/      #   风险检测评分标准 (.json)
│       │   └── rubric_revision/       #   修订建议评分标准 (.json)
│       ├── challenge/                 # 20 份合同 + rubric（含 .pdf 格式）
│       │   ├── contracts/             #   合同原文 (.md + .pdf)
│       │   ├── rubric_detection/      #   风险检测评分标准 (.json)
│       │   └── rubric_revision/       #   修订建议评分标准 (.json)
│       └── adversarial/               # 20 份合同 + rubric
│           ├── contracts/             #   合同原文 (.md)
│           ├── rubric_detection/      #   风险检测评分标准 (.json)
│           └── rubric_revision/       #   修订建议评分标准 (.json)
│
└── Case_Prediction/                   # 案情预测
    ├── article_prediction/            # 法条预测 (200 standard + 100 challenge)
    ├── clause_prediction/             # 罪名预测 (200 standard)
    ├── prison_term_prediction/        # 刑期预测 (200 standard + 100 challenge)
    └── comprehensive_judgment_prediction/  # 综合判决预测 (200 standard + 50 challenge + 50 adversarial) 
```

---

## 3. 评估方式与维度

本 benchmark 的评估方式分为两类，按任务输出特性匹配：

- **客观指标**：适用于有确定答案的任务（分类、抽取、数值预测），使用 Accuracy、F1、EM、Rouge-L、rc-F1、nLog-distance 等自动化指标，零成本、可复现
- **LLM-as-Judge + 结构化 Rubric**：适用于开放式生成任务（案情分析、咨询追问、文书生成、合同风险检测、综合判决预测），由 LLM 按预定义的 Rubric 逐项评分

Rubric 中的每个评分条目均标注所属的**评估维度**，本评测体系共设计 7 个核心维度：

| # | 维度 | 定义 |
|---|------|------|
| 1 | 事实准确性 | 回答中的事实陈述与法律条文/案例原文是否一致 |
| 2 | 法条引用正确性 | 引用的法条编号、名称是否存在且内容匹配 |
| 3 | 证据可追溯性 | 输出结论是否附有可验证的来源依据 |
| 4 | 法律推理逻辑性 | 从事实到结论的推理链是否合乎法律逻辑 |
| 5 | 完整性 | 是否覆盖了问题涉及的全部要点 |
| 6 | 安全合规性 | 是否存在煽动违法、泄露隐私或超出科普边界的内容 |
| 7 | 用户可理解性 | 专业内容是否以目标用户能理解的方式表达 |

不同子任务的 Rubric 根据任务特性选取其中若干维度进行标注（详见第 4 节各模块说明）。部分子任务在 standard（常规样本）之外额外构建了 challenge（难例）与 adversarial（反例），难例与反例的具体设计方法已在各模块的构建流程中说明。

---

## 4. 三大评测模块

### 4.1 法律问答（Legal_QA）

借鉴 LawBench 在法律评测中的实践，并参考 Bloom 认知分类学（Bloom's Taxonomy），我们将法律问答能力拆分为**记忆→理解→应用**三个递进层次，并在此框架下重新划分了子任务，逐级检验法律 AI 应用从知识召回到语义理解再到实务推理的完整能力链：

| 层次 | 子任务 | 样本量 (std / chg / adv) | 数据来源 | 评估指标 | 任务类型 |
|------|--------|--------------------------|----------|------|------|
| 记忆 | factual_query（法条事实查询） | 100 / - / - | LawRefBook | EM + Rouge-L | Generation |
| | legal_knowledge_mcqa（法律知识选择题） | 150 / 50 / - | JEC_QA | Accuracy (SLC) / F1 (MLC) | SLC / MLC |
| | statute_recitation（法条背诵） | 100 / 50 / - | LawRefBook + Foreign Law | Rouge-L | Generation |
| 理解 | reading_comprehension（阅读理解） | 200 / - / - | CAIL2019 | rc-F1 | Extraction |
| | issue_understanding（争议焦点识别） | 300 / 100 / 100 | LAIC2021 + CrimeKgAssitant + LLM Generated | Accuracy | SLC |
| | argument_understanding（论点理解） | 200 / - / - |CAIL2022  |Accuracy |SLC|
| | case_summarization（案情摘要） | 300 / 100 / 100 |CAIL2021 + LLM Generated |Rouge-L |Generation |
| 应用 | consultation_fact_inquiry（咨询事实追问） | 50 / - / - | LLM-generated | Rubric Score | Generation |
| | case_analysis（案情分析） | 100 / 25 / 25 | PLawBench + LLM-generated | Rubric Score | Generation |
| | legal_document_generation（法律文书生成） | 50 / 25 / - | LLM-generated | Rubric Score | Generation |

记忆层与理解层的数据主要来源于已有公开数据集的整理改编。其中 `statute_recitation` 的 challenge 样本加入了外国法条文（如日本刑法、德国民法典等），用于检验模型是否会将外国法与中国法混淆，考察其法条记忆的精确性与边界感知能力。而应用层的三个子任务（案情分析、咨询追问、文书生成）因缺乏现成的带 Rubric 评测数据，均由项目组自行构造，构建流程分别如下：

**咨询事实追问**——该任务模拟律师接待当事人的真实场景：输入为当事人的口语化案情陈述（含情绪化表达、细节遗漏、前后矛盾等），模型需扮演律师角色提出 10–25 个跟进问题，评测其追问的完整性、证据意识与法律推理能力。数据全部由 LLM 生成：

1. **生成标准题**：指定法律领域（婚姻家庭、合同纠纷、劳动纠纷、交通事故、刑事案件、医疗纠纷、物权侵权等），由 LLM 同时生成当事人口语化陈述（conversation）与律师应追问的关键问题作为 Rubric 评分标准
2. **LLM 校验**：逐条校验 Rubric 问题与 conversation 的对应关系、分值分配与维度标注的合理性
3. **评分维度**：每个 Rubric 条目标注所属维度（完整性 / 证据可追溯性 / 法律推理逻辑性）与分值（1–3 分），由 LLM-as-Judge 按 Rubric 逐项评分


**案情分析**——标准题的案情描述复用自 PLawBench 的 `practical_case_analysis_250.jsonl`，但原数据的 Rubric 是非结构化的大段文本，无法直接用于自动评分。我们借鉴法律实务中"结论→案情简述→分析过程→法条依据"的四段式论证结构，将 Rubric 按这四个模块（module）重新组织：每个模块下拆分为独立的评分条目，标注分值与评分维度（dimensions），由 LLM 辅助完成语义拆分与校验。其中"分析过程"模块支持 `order_required` 标记，要求模型按法律推理的逻辑顺序作答。难例通过三种变异方法改造原题的案情描述——信息干扰注入、关键事实间接化、反直觉框架——Rubric 保持不变；反例则同时改造案情与 Rubric（翻转关键事实、法律适用陷阱、构成要件缺失），确保新结论与新评分标准一致。


**法律文书生成**——该任务要求模型根据当事人的口语化案情陈述，从零散叙述中提取法律要素，起草规范的法律文书（起诉状 / 答辩状）。数据全部由 LLM 生成，采用两阶段流程：

1. **生成客户叙述**（Prompt A）：指定案由类别、文书类型与当事人立场，由 LLM 生成 800–1500 字的口语化陈述，并在叙述中嵌入 2–3 个陷阱（错误法律术语、不合理诉求、管辖错误、当事人混淆、金额计算错误等），要求案情涉及至少 2 个法律争议焦点与 2 部以上法律法规
2. **生成评分标准**（Prompt B）：基于客户叙述生成结构化 Rubric（满分 100 分），按模块设计评分项（案由定性与管辖、当事人列明、诉讼请求、事实与理由、形式规范等），每个评分项标注所属维度、分值与三级评分标准（得分点 / 扣分点 / 不及格线），并要求叙述中的每个陷阱在 Rubric 中有对应检测项
3. **难例改造**（challenge）：从标准题中抽取样本，通过三种变异方法提升难度——多重法律关系交织（叠加 2–3 层关联法律关系）、关键要素矛盾散布（同一要素给出互相矛盾的版本）、程序障碍隐藏（暗含诉讼时效临界、仲裁前置等程序性障碍），Rubric 相应扩展新增评分模块

上述自行构造的数据均经过三重校验：LLM 自动校验（使用与生成模型不同的模型进行交叉校验，检查 Rubric 条目与题目的对应关系、维度标注合理性，避免单一模型的系统性偏差）、规则校验（分值求和一致性、字段完整性、模块覆盖率）、人工审核（核查法律准确性与评分标准的可操作性），以确保每条数据的质量可靠、评分标准可执行。

### 4.2 合同审查（Contract_Review）

| 子任务 | 样本量 (std / chg / adv) | 数据来源 | 评估指标 | 任务类型 |
|--------|--------------------------|----------|----------|----------|
| clause_correction（条款纠错） | 200 / - / - | LLM Generated | F0.5 | Generation |
| contract_risk_detection（风险检测） | 80 / 20 / 20 份合同 | LLM Generated | Rubric Score | Generation |
| contract_risk_revision（修订建议） | 80 / 20 / 20 份合同 | LLM Generated | Rubric Score | Generation |

**合同风险数据构建流程**：

当前中文领域几乎没有带标注的合同风险评测数据，本项目全部自行构造。

**Step 1 — 风险维度定义**：参考《民法典》第 470 条对合同一般条款的规定（当事人、标的、数量、质量、价款、履行、违约责任、争议解决等）以及英文合同审查基准 CUAD 的分类体系，我们将合同风险划分为 6 个一级维度，覆盖合同从成立到争议解决的全生命周期：

| 编号 | 维度 | 覆盖范围 |
|------|------|----------|
| RD01 | 主体与成立风险 | 签约主体资格、代理权限、合同成立要件 |
| RD02 | 范围与义务风险 | 权利义务不对等、义务范围模糊、知识产权归属 |
| RD03 | 履行与交付风险 | 履约标准、验收条件、交付时间、变更流程 |
| RD04 | 支付与财务风险 | 付款时间/条件/方式、税费承担、预付款退还 |
| RD05 | 责任与救济风险 | 违约责任不对等、免责条款、赔偿上限、不可抗力 |
| RD06 | 争议解决风险 | 管辖约定、仲裁/诉讼选择、适用法律、终止退出 |

**Step 2 — 风险清单生成**（→ `risk_checklist.json`）：在 6 个维度下，通过三阶段流程生成细粒度风险项：

1. **通用风险**：从民法典合同编条文中自动检索相关法条，由 LLM 进行三来源推理——法条驱动（逐条反推"不约定会怎样"）、判例驱动（裁判文书高频争议焦点）、监管规范驱动（特别法强制性要求），生成 100-200 项通用风险
2. **合同类型特有风险**：针对买卖、租赁、劳动、采购、服务等合同类型，结合行业风险参考资料补充 25-40 项特有风险
3. **语义去重与校验**：LLM 审查全部风险项，合并语义重复条目，校验定义的可操作性，最终产出 `risk_checklist.json`，含通用风险 136 项 + 合同类型特有风险 33 项，共 169 项

**Step 3 — 合同样本收集与生成**：合同模板来源于[国家市场监督管理总局合同示范文本库](https://htsfwb.samr.gov.cn/)等官方权威平台，覆盖买卖、租赁、劳动、借款、服务、仓储、委托、承揽等合同类型。在真实模板基础上随机填充当事人信息，并按 `risk_checklist.json` 中的风险项自然嵌入指定数量的风险条款，生成完整合同文本

**Step 4 — 标准答案与 Rubric 生成**：对每份合同，由 LLM 生成结构化 Rubric 评分标准。每个风险点包含 `risk_name`（风险名称）、`severity`（严重程度）、`risky_clause`（合同原文定位）、`explanation`（风险解释）、`recommendation`（修改建议），评分细分为"识别风险 / 风险解释 / 修改建议"三项，经LLM 校验与人工抽检校验后形成最终标注

### 4.3 案情预测（Case_Prediction）

| 子任务 | 样本量 (std / chg / adv) | 数据来源 | 评估指标 | 任务类型 |
|--------|--------------------------|----------|----------|----------|
| article_prediction（法条预测） | 200 / 100 / - | CAIL2018 | F1 | MLC |
| clause_prediction（罪名预测） | 200 / - / - | CAIL2018 | F1 | MLC |
| prison_term_prediction（刑期预测） | 200 / 100 / - | CAIL2018 | nLog-distance | Regression |
| comprehensive_judgment_prediction（综合判决预测） | 200 / 50 / 50 | CAIL2018 + LLM-generated | Rubric Score | Generation |

前三个子任务（法条预测、罪名预测、刑期预测）的案情描述与标准答案均来自 CAIL2018 的结构化标签，采用精确匹配或数值距离进行客观评分。综合判决预测则要求模型对一个完整案情给出端到端的判决分析，与单点预测任务（只看"答案对不对"）不同，该任务评估的是模型的综合法律推理与论证能力。

**综合判决预测数据构建流程**：

案情描述同样来自 CAIL2018，但评分方式从精确匹配改为 LLM-as-Judge Rubric 评分。Rubric 按五个模块组织（满分 100 分）：罪名认定（20 分）、量刑情节分析（30 分）、刑期预测（25 分）、附带民事与赔偿（15 分）、法条适用（10 分）。其中量刑情节分析是核心区分度模块，进一步拆分为四个递进子层次：量刑基准确定→法定量刑情节识别与论证→酌定量刑情节识别→综合量刑调节，要求模型展示从事实到量刑建议的完整推理链。

Rubric 均由 LLM 生成，输入为案情描述与 CAIL2018 的结构化标签（罪名、法条、刑期、罚金），以此作为 ground truth 约束。标准题、难例、反例分别使用独立的 Prompt 模板：标准题要求生成五模块完整 Rubric；难例在此基础上增加难度类型专项规则，覆盖四种高区分度场景——综合叠加型（多种难度场景叠加）、情节竞合型（从轻与从重情节同时存在，需权衡分析）、重刑案件型（法定刑升格判断）、数罪并罚型（需分别定罪并适用并罚规则）；反例则针对"案情容易产生错误直觉"的案件，分为罪名误导型（案情看似构成 A 罪实际应定 B 罪）与量刑反直觉型（如有自首但重判、累犯短刑期不适用缓刑），在 Rubric 关键模块设置**反向扣分项**（如"若认定为直觉性错误罪名则本项不得分"），要求模型明确排除错误直觉并论证区分理由。所有生成的 Rubric 均经过 ground truth 一致性校验（Rubric 中的罪名、法条、刑期必须与 CAIL2018 原始标签一致）、分值规则校验（各模块分值求和 = 100、评分项分值求和 = 模块分值）以及 LLM 交叉校验，确保评分标准与案情事实对应、分值分配合理。

---

## 5. 数据格式说明

### 5.1 通用问答格式

适用于所有客观评分任务（记忆层、理解层、条款纠错、罪名预测、法条预测、刑期预测）：

```json
{
  "instruction": "评测指令（System Prompt）",
  "question": "输入问题或案情描述",
  "answer": "参考答案"
}
```

- `factual_query`、`statute_recitation` 额外包含 `source` 字段，标注答案对应的法条来源
- `prison_term_prediction` 的 `question` 中同时包含案情事实、罪名、相关法条编号及法条全文，供模型参考后预测刑期

### 5.2 咨询追问 Rubric 格式（consultation_fact_inquiry）

```json
{
  "label": "婚姻家庭",
  "conversation": "当事人口语化案情陈述（800-1500 字）",
  "question": "评测指令",
  "total_score": 20,
  "rubrics": [
    {
      "index": 1,
      "points": 3,
      "dimension": "证据可追溯性",
      "criterion": "具体应追问的问题"
    }
  ]
}
```

每个 rubric 条目为一个律师应追问的关键问题，标注所属维度与分值。

### 5.3 案情分析 Rubric 格式（case_analysis）

```json
{
  "instruction": "评测指令",
  "question": "案情描述 + 问题",
  "label": "案件类别（如婚姻家事）",
  "total_score": 60,
  "rubrics": [
    {
      "module": "结论",
      "module_score": 10,
      "dimensions": ["事实准确性", "法律推理逻辑性"],
      "items": [
        {
          "index": 1,
          "criterion": "具体评分标准",
          "points": 5,
          "order_required": false
        }
      ]
    }
  ]
}
```

### 5.4 法律文书生成 Rubric 格式（legal_document_generation）

```json
{
  "question": "当事人口语化案情陈述",
  "label": "合同纠纷-买卖合同纠纷",
  "doc_type": "起诉状",
  "rubrics": [
    {
      "module": "案由定性与管辖法院",
      "module_score": 22,
      "dimensions": ["法律推理逻辑性", "事实准确性", "安全合规性"],
      "items": [
        {
          "index": 1,
          "criterion": "具体评分标准（含得分点/扣分点/不及格线）",
          "points": 10,
          "note": "评分补充说明（可选）"
        }
      ]
    }
  ]
}
```

每个评分项包含三级评分标准（得分点 / 扣分点 / 不及格线），`note` 提供额外评分指引。

### 5.5 合同审查格式（风险检测与修订 rubric）

每份合同在 `rubric_detection/` 和 `rubric_revision/` 下各对应一个 rubric JSON。两者共享相同的基础结构（`id`、`contract_type`、`difficulty`、`contract_file`、`question`、`risk_count`、`total_score`）。区别在于：`rubric_detection` 使用 `risks` 数组，每个风险项包含 `scoring`（识别风险/风险解释/修改建议/法律依据子项评分）、`explanation`、`risk_basis` 等字段；`rubric_revision` 使用 `fixes` 数组，每个修订项包含 `fix_checklist`（逐条检查清单）和 `gold_fix`（参考修订文本）等字段。

**rubric_detection 格式**（风险检测评分）：

```json
{
  "id": "买卖合同-商品房-1",
  "contract_type": "买卖合同",
  "sub_type": "商品房",
  "difficulty": "standard",
  "contract_file": "contracts/买卖合同-商品房-1.md",
  "question": "请审阅以下合同，识别其中存在的法律风险……",
  "risk_count": 7,
  "total_score": 52,
  "risks": [
    {
      "index": 1,
      "risk_id": "RD06-003",
      "dimension": "争议解决风险",
      "risk_name": "或裁或审条款无效风险",
      "severity": "高",
      "detect_difficulty": "easy",
      "points": 7,
      "clause_location": "第二十四条 争议解决方式",
      "risky_clause": "（原文定位）",
      "explanation": "风险解释",
      "risk_basis": "法律依据",
      "recommendation": "修改建议",
      "scoring": {
        "识别风险": {"score": 1, "desc": "指出该位置存在风险"},
        "风险解释": {"score": 3, "desc": "对风险的解释逻辑成立"},
        "修改建议": {"score": 3, "desc": "建议能实质消除风险"}
      }
    }
  ]
}
```

**rubric_revision 格式**（修订建议评分）：

```json
{
  "id": "买卖合同-商品房-1",
  "contract_type": "买卖合同",
  "sub_type": "商品房",
  "difficulty": "standard",
  "contract_file": "contracts/买卖合同-商品房-1.md",
  "question": "请审阅以下合同，对存在法律风险的条款提出具体修改方案，给出修改前后的条款对比。",
  "risk_count": 7,
  "total_score": 52,
  "fixes": [
    {
      "index": 1,
      "risk_id": "RD06-003",
      "dimension": "争议解决风险",
      "risk_name": "或裁或审条款无效风险",
      "severity": "高",
      "clause_location": "第二十四条 争议解决方式",
      "risky_clause": "（原文定位）",
      "gold_fix": "参考修订文本",
      "max_score": 6,
      "fix_checklist": [
        {"point": "检查点描述", "score": 2, "keywords": ["关键词1", "关键词2"]}
      ]
    }
  ]
}
```

### 5.6 综合判决预测 Rubric 格式（comprehensive_judgment_prediction）

```json
{
  "instruction": "评测指令（System Prompt）",
  "question": "案情描述",
  "total_score": 100,
  "rubrics": [
    {
      "module": "罪名认定",
      "module_score": 20,
      "dimensions": ["事实准确性", "法律推理逻辑性"],
      "items": [
        {
          "index": 1,
          "criterion": "具体评分标准",
          "points": 8,
          "order_required": false,
          "note": "评分补充说明（可选）"
        }
      ]
    }
  ]
}
```

Rubric 按五个模块组织（满分 100 分）：罪名认定（20 分）、量刑情节分析（30 分）、刑期预测（25 分）、附带民事与赔偿（15 分）、法条适用（10 分）。challenge 样本额外包含 `tag` 字段（如 `"难例改造：数罪并罚型"`），标注难例类型。

## 6. 许可与引用

本 benchmark 仅供学术研究与教育用途。合同样本基于公开模板改编，案例数据来源于裁判文书网公开信息，均已脱敏处理。

感谢 CAIL、JEC_QA、LawBench、PLawBench 等开源项目与数据集的贡献者，本项目的工作建立在这些工作之上。欢迎社区补充新的评测样本或提出改进建议。如有任何侵权问题，请联系我们，将第一时间处理。
