/* ZhiFa-Eval Frontend */
const MODULE_NAMES = {
  legal_qa: "⚖️ 法律问答",
  contract_review: "📄 合同审查",
  case_prediction: "🔮 案情预测",
};

let taskData = null;
let currentPanel = "dashboard";
let pendingTask = null;

// ─── Panel Switching + Path Routing ─────────────────────
const WIZARD_STEP_PATHS = {1:"task", 2:"method", 3:"judge", 4:"execute"};

function switchPanel(name) {
  document.querySelectorAll(".panel").forEach((p) => (p.classList.remove("active")));
  document.querySelectorAll(".nav-item").forEach((n) => n.classList.remove("active"));
  const panel = document.getElementById("panel-" + name);
  if (panel) panel.classList.add("active");
  const nav = document.querySelector(`.nav-item[data-panel="${name}"]`);
  if (nav) nav.classList.add("active");
  const titles = { dashboard: "总览", runner: "评测执行", results: "结果分析", settings: "API 配置" };
  document.getElementById("page-title-text").textContent = titles[name] || name;
  currentPanel = name;
  const target = name === "dashboard" ? "/" : "/eval/" + name;
  if (location.pathname !== target) history.pushState(null, "", target);
  if (name === "dashboard") loadDashboard();
  if (name === "runner") loadRunner();
  if (name === "results") loadResults();
  if (name === "settings") loadSettings();
}

function _parseRoute() {
  const p = location.pathname;
  if (p.startsWith("/eval/runner/")) {
    const step = p.split("/")[3];
    const stepNum = Object.entries(WIZARD_STEP_PATHS).find(([k,v]) => v === step);
    return { panel: "runner", wizardStep: stepNum ? parseInt(stepNum[0]) : 1 };
  }
  if (p.startsWith("/eval/")) return { panel: p.split("/")[2] || "dashboard", wizardStep: null };
  return { panel: "dashboard", wizardStep: null };
}

window.addEventListener("popstate", () => {
  const route = _parseRoute();
  if (route.panel !== currentPanel) {
    // 切换到不同面板
    switchPanel(route.panel);
    if (route.panel === "runner" && route.wizardStep) {
      setTimeout(() => wizardGoTo(route.wizardStep, true), 100);
    }
  } else if (route.panel === "runner" && route.wizardStep) {
    // 同一面板内切换向导步骤，不重建页面
    document.getElementById("single-sample-area").style.display = "none";
    wizardGoTo(route.wizardStep, true);
  }
});

// ─── Theme ──────────────────────────────────────────────
function setTheme(t) {
  document.documentElement.setAttribute("data-theme", t);
  document.querySelectorAll(".theme-btn").forEach((b) => b.classList.toggle("active", b.textContent.trim() === (t === "dark" ? "深色" : "浅色")));
  localStorage.setItem("theme", t);
}

// ─── Dashboard ──────────────────────────────────────────
async function loadDashboard() {
  if (!taskData) taskData = await fetch("/api/tasks").then(r => r.json());
  const el = document.getElementById("panel-dashboard");
  const mods = taskData.modules;
  let totalSamples = 0;
  let totalTasks = taskData.total_tasks;
  for (const mod of Object.values(mods)) {
    for (const t of mod) {
      totalSamples += Object.values(t.sample_counts).reduce((a, b) => a + b, 0);
    }
  }

  let html = `<div class="stats-grid">
    <div class="stat-card"><div class="stat-value">${totalTasks}</div><div class="stat-label">子任务</div></div>
    <div class="stat-card"><div class="stat-value">${totalSamples.toLocaleString()}</div><div class="stat-label">评测样本</div></div>
    <div class="stat-card"><div class="stat-value">7</div><div class="stat-label">评估维度</div></div>
    <div class="stat-card"><div class="stat-value">3</div><div class="stat-label">评测模块</div></div>
  </div><h3 style="margin-bottom:16px">任务一览</h3>`;

  // 构建三列各自的 HTML
  const modEntries = Object.entries(mods);
  const colHtmls = modEntries.map(([modKey, tasks]) => {
    let h = `<div class="module-header">${MODULE_NAMES[modKey] || modKey}<span class="module-badge">${tasks.length} 个</span></div><div class="task-list">`;
    for (const t of tasks) {
      const sc = t.sample_counts;
      let parts = [];
      if (sc.standard) parts.push(sc.standard);
      if (sc.challenge) parts.push(sc.challenge);
      if (sc.adversarial) parts.push(sc.adversarial);
      const countStr = parts.join('+');
      const badge = t.eval_method === "rubric"
        ? `<span class="badge badge-rubric">Rubric</span>`
        : `<span class="badge badge-obj">${t.task_type === "SLC/MLC" ? "Acc/F1" : t.metrics.map(m => m.replace(/-ABCD[E]?|-Category/g,'')).join("+")}</span>`;
      h += `<div class="task-item" onclick="goToTask('${modKey}','${t.task_id}')">
        <span class="task-item-name">${t.display_name}</span>
        <span class="task-item-counts">${countStr}</span>${badge}</div>`;
    }
    h += `</div>`;
    return h;
  });

  // 信息卡片：评估维度 / 指标含义 / 数据看板
  const infoBox = `<div class="info-box">
    <div class="info-box-tabs">
      <button class="info-tab active" onclick="switchInfoTab('dims',this)">评估维度</button>
      <button class="info-tab" onclick="switchInfoTab('metrics',this)">指标含义</button>
      <button class="info-tab" onclick="switchPanel('results')">数据看板</button>
    </div>
    <div class="info-tab-content" id="info-tab-dims">
      <div class="info-grid">
        <div class="info-chip"><span class="info-chip-dot"></span><b>事实准确性</b><span>回答中的事实陈述与法律条文/案例原文是否一致</span></div>
        <div class="info-chip"><span class="info-chip-dot"></span><b>法条引用正确性</b><span>引用的法条编号、名称是否存在且内容匹配</span></div>
        <div class="info-chip"><span class="info-chip-dot"></span><b>证据可追溯性</b><span>输出结论是否附有可验证的来源依据</span></div>
        <div class="info-chip"><span class="info-chip-dot"></span><b>法律推理逻辑性</b><span>从事实到结论的推理链是否合乎法律逻辑</span></div>
        <div class="info-chip"><span class="info-chip-dot"></span><b>完整性</b><span>是否覆盖了问题涉及的全部要点</span></div>
        <div class="info-chip"><span class="info-chip-dot"></span><b>安全合规性</b><span>是否存在煽动违法、泄露隐私或超出科普边界的内容</span></div>
        <div class="info-chip"><span class="info-chip-dot"></span><b>用户可理解性</b><span>专业内容是否以目标用户能理解的方式表达</span></div>
      </div>
    </div>
    <div class="info-tab-content" id="info-tab-metrics" style="display:none">
      <div class="info-grid">
        <div class="info-chip"><span class="info-chip-dot"></span><b>Accuracy</b><span>选择题精确匹配正确率</span></div>
        <div class="info-chip"><span class="info-chip-dot"></span><b>F1</b><span>多标签分类的 Precision/Recall 调和均值</span></div>
        <div class="info-chip"><span class="info-chip-dot"></span><b>EM</b><span>Exact Match，标准化后完全一致</span></div>
        <div class="info-chip"><span class="info-chip-dot"></span><b>Rouge-L</b><span>最长公共子序列 F1（中文字级别）</span></div>
        <div class="info-chip"><span class="info-chip-dot"></span><b>rc-F1</b><span>阅读理解 token 级 F1</span></div>
        <div class="info-chip"><span class="info-chip-dot"></span><b>F0.5</b><span>Precision 加权的 F 值（条款纠错）</span></div>
        <div class="info-chip"><span class="info-chip-dot"></span><b>nLog-distance</b><span>刑期预测对数距离，越高越准</span></div>
        <div class="info-chip"><span class="info-chip-dot" style="background:var(--accent-warning)"></span><b>Rubric Score</b><span>LLM-as-Judge 按评分标准逐项打分</span></div>
      </div>
    </div>
  </div>`;

  html += `<div class="task-layout">
    <div class="task-col task-col-legal">${colHtmls[0] || ""}</div>
    <div class="task-col task-col-contract">${colHtmls[1] || ""}</div>
    <div class="task-col task-col-case">${colHtmls[2] || ""}</div>
    <div class="task-info-box">${infoBox}</div>
  </div>`;

  el.innerHTML = html;
}

function switchInfoTab(tab, btn) {
  document.getElementById("info-tab-dims").style.display = tab === "dims" ? "" : "none";
  document.getElementById("info-tab-metrics").style.display = tab === "metrics" ? "" : "none";
  btn.parentElement.querySelectorAll(".info-tab").forEach(b => b.classList.remove("active"));
  btn.classList.add("active");
}

function goToTask(moduleKey, taskId) {
  pendingTask = { module: moduleKey, task_id: taskId };
  switchPanel('runner');
}

// ─── Runner (Wizard) ────────────────────────────────────
let wizardStep = 1;

function getSelectedTask() {
  const tid = document.getElementById("sel-task")?.value;
  return Object.values(taskData.modules).flat().find(x => x.task_id === tid);
}

function isRubricTask() {
  const t = getSelectedTask();
  return t && t.eval_method === "rubric";
}

function getSeed() {
  const el = document.getElementById("inp-seed");
  return el ? parseInt(el.value, 10) || 42 : 42;
}

function getSelectedSubtype() {
  const el = document.getElementById("sel-subtype");
  return el ? el.value : "";
}

function wizardGoTo(step, fromPopstate) {
  // 切换步骤时清除评测结果
  const evalResults = document.getElementById("eval-results");
  if (evalResults) evalResults.innerHTML = "";
  // When ratio=1 and user clicks forward from step 1, skip to single-sample mode
  if (step > 1 && window._sampleRatio === 1 && !fromPopstate) {
    loadOneSample();
    history.pushState(null, "", "/eval/runner/sample");
    return;
  }
  // Skip step 3 (judge config) for non-rubric tasks
  if (step === 3 && !isRubricTask()) {
    step = wizardStep < 3 ? 4 : 2;
  }
  if (step < 1) step = 1;
  if (step > 4) step = 4;
  wizardStep = step;
  document.querySelectorAll(".wizard-step").forEach(s => s.classList.remove("active"));
  const cur = document.getElementById("wizard-step-" + step);
  if (cur) cur.classList.add("active");
  // Update URL
  const stepPath = WIZARD_STEP_PATHS[step] || "task";
  if (!fromPopstate) history.pushState(null, "", "/eval/runner/" + stepPath);
  // Update config summary when entering step 4
  if (step === 4) updateConfigSummary();
}

function updateConfigSummary() {
  const el = document.getElementById("config-summary");
  if (!el) return;
  const mode = window._evalMode === "json" ? "导入 JSON" : "API 在线推理";
  const RATIO_LABELS = {1:"单样本", 25:"四分之一", 50:"半量", 100:"全量"};
  const DIFF_NAMES = {standard:"标准", challenge:"难例", adversarial:"反例"};

  const meta = (window._evalMode === "json" && window._jsonMeta) ? window._jsonMeta : null;

  if (meta) {
    const allTasks = Object.values(taskData.modules).flat();
    const mt = allTasks.find(x => x.task_id === meta.task_id);
    const modKey = mt ? mt.module : "";
    const ratio = meta.sample_ratio;
    let html = `<b>模块：</b>${MODULE_NAMES[modKey] || modKey}<br>`;
    html += `<b>子任务：</b>${meta.display_name || (mt ? mt.display_name : meta.task_id)}<br>`;
    if (meta.subtype && mt && mt.subtypes) {
      html += `<b>类型：</b>${mt.subtypes[meta.subtype] || meta.subtype}<br>`;
    }
    html += `<b>难度：</b>${DIFF_NAMES[meta.difficulty] || meta.difficulty}<br>`;
    html += `<b>采样：</b>${RATIO_LABELS[ratio] || ratio + "%"} (seed=${meta.seed})<br>`;
    html += `<b>评测方式：</b>${mode}<br>`;
    html += `<span class="form-hint">以上参数来自文件 meta</span>`;
    el.innerHTML = html;
  } else {
    const t = getSelectedTask();
    const mod = document.getElementById("sel-module").value;
    const diff = document.getElementById("sel-diff").value;
    const ratio = window._sampleRatio;
    const seed = getSeed();
    let html = `<b>模块：</b>${MODULE_NAMES[mod] || mod}<br>`;
    html += `<b>子任务：</b>${t ? t.display_name : ""}<br>`;
    const subtype = getSelectedSubtype();
    if (subtype && t && t.subtypes) {
      html += `<b>类型：</b>${t.subtypes[subtype] || subtype}<br>`;
    }
    html += `<b>难度：</b>${DIFF_NAMES[diff] || diff}<br>`;
    html += `<b>采样：</b>${RATIO_LABELS[ratio] || ratio + "%"} (seed=${seed})<br>`;
    html += `<b>评测方式：</b>${mode}<br>`;
    if (isRubricTask()) {
      html += `<b>裁判模型：</b>${document.getElementById("inp-jmodel")?.value || "未配置"}<br>`;
    }
    el.innerHTML = html;
  }
}

async function loadRunner() {
  if (!taskData) taskData = await fetch("/api/tasks").then(r => r.json());
  const el = document.getElementById("panel-runner");
  const cfg = JSON.parse(localStorage.getItem("evalConfig") || "{}");

  el.innerHTML = `
  <!-- Step 1: Task + Sampling (merged) -->
  <div class="wizard-step active" id="wizard-step-1">
    <div class="wizard-card">
      <div class="runner-section"><h3><span class="step-badge">1</span> 选择任务与采样</h3></div>
      <div class="wizard-card-desc">选择评测模块、子任务、难度，并设置采样数量</div>
      <div class="form-row">
        <div class="form-group"><label class="form-label">模块</label>
          <select class="form-select" id="sel-module" onchange="onModuleChange()">
            ${Object.keys(taskData.modules).map(k => `<option value="${k}">${MODULE_NAMES[k]}</option>`).join("")}
          </select></div>
        <div class="form-group"><label class="form-label">子任务</label>
          <select class="form-select" id="sel-task"></select></div>
        <div class="form-group"><label class="form-label">难度</label>
          <select class="form-select" id="sel-diff"></select></div>
      </div>
      <div class="form-row" id="subtype-row" style="display:none">
        <div class="form-group"><label class="form-label">数据类型</label>
          <div class="subtype-chips" id="subtype-chips"></div>
          <input type="hidden" id="sel-subtype" value="" />
        </div>
      </div>
      <div id="task-info" class="task-meta"></div>
      <label class="form-label">采样数量</label>
      <div class="ratio-cards">
        <div class="ratio-card active" onclick="selectRatio(1,this)">
          <span class="ratio-card-num">1</span>
          <div class="ratio-card-text"><span class="ratio-card-label">单样本</span><span class="ratio-card-sub">快速验证</span></div></div>
        <div class="ratio-card" onclick="selectRatio(25,this)">
          <span class="ratio-card-num">¼</span>
          <div class="ratio-card-text"><span class="ratio-card-label">四分之一</span><span class="ratio-card-sub">25% 采样</span></div></div>
        <div class="ratio-card" onclick="selectRatio(50,this)">
          <span class="ratio-card-num">½</span>
          <div class="ratio-card-text"><span class="ratio-card-label">半量</span><span class="ratio-card-sub">50% 采样</span></div></div>
        <div class="ratio-card" onclick="selectRatio(100,this)">
          <span class="ratio-card-num">All</span>
          <div class="ratio-card-text"><span class="ratio-card-label">全量</span><span class="ratio-card-sub">完整评测</span></div></div>
      </div>
      <div class="seed-row">
        <label class="form-label">随机种子</label>
        <input class="form-input" id="inp-seed" type="number" value="42" />
        <span class="form-hint">固定种子，同配置每次抽到相同样本</span>
      </div>
      <div class="wizard-nav"><span></span><button class="btn btn-primary" onclick="wizardGoTo(2)">下一步</button></div>
    </div>
  </div>

  <!-- Step 2: Evaluation method -->
  <div class="wizard-step" id="wizard-step-2">
    <div class="wizard-card">
      <div class="runner-section"><h3><span class="step-badge">2</span> 评测方式</h3></div>
      <div class="wizard-card-desc">选择在线推理或离线导入 JSON 进行评测</div>
      <div class="mode-tabs">
        <button class="mode-tab active" onclick="switchMode('api',this)">🔗 API 在线推理</button>
        <button class="mode-tab" onclick="switchMode('json',this)">📄 导入 JSON</button>
      </div>
      <div id="mode-api" class="mode-panel">
        <div class="form-row" style="margin-top:16px">
          <div class="form-group"><label class="form-label">API Base URL</label>
            <input class="form-input" id="inp-url" value="${cfg.api_base_url||""}"/></div>
          <div class="form-group"><label class="form-label">API Key</label>
            <input class="form-input" id="inp-key" type="password" value="${cfg.api_key||""}" /></div>
          <div class="form-group"><label class="form-label">Model Name</label>
            <input class="form-input" id="inp-model" value="${cfg.model_name||""}" /></div>
        </div>
      </div>
      <div id="mode-json" class="mode-panel" style="display:none">
        <div class="json-flow">
          <div class="json-flow-step">
            <div class="json-flow-header"><span class="step-badge" style="width:22px;height:22px;font-size:11px">1</span><b>导出题目</b></div>
            <p class="form-hint" style="margin-top:6px" id="exportDesc">按当前任务和采样配置导出题目，交给模型生成回答</p>
            <button class="btn btn-primary" style="margin-top:10px" id="btnExport" onclick="exportQuestions()">导出题目 JSON</button>
            <span class="form-hint" id="exportInfo" style="margin-left:12px;display:none"></span>
          </div>
          <div class="json-flow-step" style="margin-top:16px">
            <div class="json-flow-header"><span class="step-badge" style="width:22px;height:22px;font-size:11px">2</span><b>导入回答</b></div>
            <p class="form-hint" style="margin-top:6px">上传模型回答 JSON</p>
            <div class="json-format-hints" id="jsonFormatHints"></div>
            <div class="file-drop-zone" id="jsonDropZone" onclick="document.getElementById('json-file').click()" ondragover="event.preventDefault();this.classList.add('dragover')" ondragleave="this.classList.remove('dragover')" ondrop="handleJsonDrop(event)">
              <input type="file" id="json-file" accept=".json" style="display:none" onchange="onJsonFileSelected(this)" />
              <span class="file-drop-icon">📄</span>
              <span class="file-drop-text">点击选择或拖拽 JSON 文件</span>
            </div>
            <p id="jsonFileInfo" class="form-hint" style="display:none"></p>
          </div>
        </div>
      </div>
      <div class="wizard-nav">
        <button class="btn btn-secondary" onclick="wizardGoTo(1)">上一步</button>
        <button class="btn btn-primary" onclick="wizardGoTo(3)">下一步</button>
      </div>
    </div>
  </div>

  <!-- Step 3: Judge model (Rubric only) -->
  <div class="wizard-step" id="wizard-step-3">
    <div class="wizard-card">
      <div class="runner-section"><h3><span class="step-badge">3</span> 裁判模型</h3></div>
      <div class="wizard-card-desc">Rubric 评分任务需要 LLM-as-Judge 裁判模型，优先使用服务端 .env 配置</div>
      <div id="judge-server-status" style="margin-bottom:16px"></div>
      <details id="judge-override-details">
        <summary style="cursor:pointer;font-size:13px;color:var(--text-muted);margin-bottom:12px">手动覆盖（可选）</summary>
        <div class="form-row">
          <div class="form-group"><label class="form-label">Judge API Base URL</label>
            <input class="form-input" id="inp-jurl" value="" placeholder="留空则使用服务端配置" /></div>
          <div class="form-group"><label class="form-label">Judge API Key</label>
            <input class="form-input" id="inp-jkey" type="password" value="" placeholder="留空则使用服务端配置" /></div>
          <div class="form-group"><label class="form-label">Judge Model</label>
            <input class="form-input" id="inp-jmodel" value="" placeholder="留空则使用服务端配置" /></div>
        </div>
      </details>
      <div class="wizard-nav">
        <button class="btn btn-secondary" onclick="wizardGoTo(2)">上一步</button>
        <button class="btn btn-primary" onclick="wizardGoTo(4)">下一步</button>
      </div>
    </div>
  </div>

  <!-- Step 4: Confirmation + run -->
  <div class="wizard-step" id="wizard-step-4">
    <div class="wizard-card">
      <div class="runner-section"><h3><span class="step-badge">4</span> 确认并运行</h3></div>
      <div class="wizard-card-desc">检查以下配置，确认无误后开始评测</div>
      <div class="card" style="margin-bottom:16px"><div class="card-title" style="margin-bottom:8px">配置总览</div>
        <div class="config-summary" id="config-summary"></div>
      </div>
      <button class="btn btn-primary" id="btn-run" onclick="runEval()" style="width:100%">🚀 开始评测</button>
      <div class="progress-bar" id="eval-progress-bar" style="display:none"><div class="progress-fill" id="eval-progress-fill"></div></div>
      <div class="progress-text" id="eval-status"></div>
      <div class="wizard-nav" style="margin-top:12px">
        <button class="btn btn-secondary" onclick="wizardGoTo(3)">上一步</button><span></span>
      </div>
    </div>
  </div>

  <div id="single-sample-area" style="display:none"></div>
  <div id="eval-results"></div>`;

  window._evalMode = "api";
  window._sampleRatio = 1;
  wizardStep = 1;
  onModuleChange();
  loadJudgeConfig();
  if (pendingTask) {
    document.getElementById("sel-module").value = pendingTask.module;
    onModuleChange();
    document.getElementById("sel-task").value = pendingTask.task_id;
    onTaskChange();
    pendingTask = null;
  }
}

function selectRatio(ratio, el) {
  window._sampleRatio = ratio;
  document.querySelectorAll(".ratio-card").forEach(b => b.classList.remove("active"));
  el.classList.add("active");
}

async function loadJudgeConfig() {
  const el = document.getElementById("judge-server-status");
  if (!el) return;
  try {
    const res = await fetch("/api/judge-config");
    const cfg = await res.json();
    if (cfg.configured) {
      el.innerHTML = `<div style="display:flex;align-items:center;gap:10px;padding:12px 16px;background:var(--bg-tertiary);border-radius:10px;border:1px solid var(--accent-success);font-size:13px">
        <span style="color:var(--accent-success);font-weight:700">✓ 服务端已配置</span>
        <span style="color:var(--text-muted)">模型: <b style="color:var(--text-primary)">${cfg.model}</b></span>
        <span style="color:var(--text-muted)">Key: <code style="font-size:12px">${cfg.api_key_masked}</code></span>
      </div>`;
    } else {
      el.innerHTML = `<div style="display:flex;align-items:center;gap:10px;padding:12px 16px;background:var(--bg-tertiary);border-radius:10px;border:1px solid var(--accent-warning);font-size:13px">
        <span style="color:var(--accent-warning);font-weight:700">⚠ 未配置</span>
        <span style="color:var(--text-muted)">请在项目根目录 .env 中填写 JUDGE_API_KEY，或展开下方手动输入</span>
      </div>`;
    }
  } catch(e) {
    el.innerHTML = `<div style="font-size:13px;color:var(--text-muted)">无法获取服务端配置</div>`;
  }
}

function selectSubtype(value, el) {
  document.getElementById("sel-subtype").value = value;
  document.querySelectorAll(".subtype-chip").forEach(c => c.classList.remove("active"));
  el.classList.add("active");
}

function switchMode(mode, btn) {
  window._evalMode = mode;
  window._jsonMeta = null;
  document.querySelectorAll(".mode-tab").forEach(b => b.classList.remove("active"));
  btn.classList.add("active");
  document.getElementById("mode-api").style.display = mode === "api" ? "" : "none";
  document.getElementById("mode-json").style.display = mode === "json" ? "" : "none";
  const info = document.getElementById("exportInfo");
  if (info) { info.style.display = "none"; info.textContent = ""; }
  const finfo = document.getElementById("jsonFileInfo");
  if (finfo) { finfo.style.display = "none"; finfo.textContent = ""; }
  const drop = document.getElementById("jsonDropZone");
  if (drop) drop.classList.remove("has-file");
}

const CONTRACT_TASKS = ["contract_review.risk_detection", "contract_review.risk_revision"];

function updateJsonFlowHints() {
  const tid = document.getElementById("sel-task")?.value || "";
  const isContract = CONTRACT_TASKS.includes(tid);
  const desc = document.getElementById("exportDesc");
  const btn = document.getElementById("btnExport");
  const hints = document.getElementById("jsonFormatHints");
  if (!desc || !btn || !hints) return;

  if (isContract) {
    desc.textContent = "导出 ZIP 压缩包（含合同原文 + 题目 JSON），交给模型生成回答";
    btn.textContent = "导出题目 ZIP";
    hints.innerHTML = `<details><summary>格式：按 id 匹配</summary>
      <pre class="json-hint-pre">{"meta":{...}, "answers":[{"id":0,"answer":"回答"},...]}</pre></details>
      <p class="form-hint" style="margin-top:4px">合同审查任务仅支持按 id 匹配</p>
      <button class="btn btn-secondary" style="margin-top:8px;padding:6px 14px;font-size:12px" onclick="downloadAnswerTemplate()">下载示例 JSON</button>`;
  } else {
    desc.textContent = "按当前任务和采样配置导出题目 JSON，交给模型生成回答";
    btn.textContent = "导出题目 JSON";
    hints.innerHTML = `<details><summary>格式 A：按 id 匹配（推荐）</summary>
      <pre class="json-hint-pre">{"meta":{...}, "answers":[{"id":0,"answer":"回答"},...]}</pre></details>
      <details><summary>格式 B：按问题匹配</summary>
      <pre class="json-hint-pre">{"meta":{...}, "answers":[{"question":"题目前200字","answer":"回答"},...]}</pre></details>
      <button class="btn btn-secondary" style="margin-top:8px;padding:6px 14px;font-size:12px" onclick="downloadAnswerTemplate()">下载示例 JSON</button>`;
  }
}

function onModuleChange() {
  const mod = document.getElementById("sel-module").value;
  const tasks = taskData.modules[mod] || [];
  const sel = document.getElementById("sel-task");
  sel.innerHTML = tasks.map(t => `<option value="${t.task_id}">${t.display_name}</option>`).join("");
  sel.onchange = onTaskChange;
  onTaskChange();
}

function onTaskChange() {
  const tid = document.getElementById("sel-task").value;
  const allTasks = Object.values(taskData.modules).flat();
  const t = allTasks.find(x => x.task_id === tid);
  if (!t) return;
  const diffSel = document.getElementById("sel-diff");
  diffSel.innerHTML = t.difficulties.map(d => `<option value="${d}">${d}</option>`).join("");
  // subtype chips
  const subtypeRow = document.getElementById("subtype-row");
  const chipsEl = document.getElementById("subtype-chips");
  const hiddenInput = document.getElementById("sel-subtype");
  if (t.subtypes && Object.keys(t.subtypes).length) {
    subtypeRow.style.display = "";
    let chips = `<span class="subtype-chip active" onclick="selectSubtype('',this)">全部</span>`;
    for (const [k, v] of Object.entries(t.subtypes)) {
      chips += `<span class="subtype-chip" onclick="selectSubtype('${k}',this)">${v}</span>`;
    }
    chipsEl.innerHTML = chips;
    hiddenInput.value = "";
  } else {
    subtypeRow.style.display = "none";
    chipsEl.innerHTML = "";
    hiddenInput.value = "";
  }
  const METHOD_LABELS = {objective:"客观评分", rubric:"Rubric 评分"};
  const sc = t.sample_counts;
  const total = Object.values(sc).reduce((a,b)=>a+b,0);
  const parts = [];
  if (sc.standard) parts.push(`标准 ${sc.standard}`);
  if (sc.challenge) parts.push(`难例 ${sc.challenge}`);
  if (sc.adversarial) parts.push(`反例 ${sc.adversarial}`);
  const metricStr = t.task_type === "SLC/MLC" ? "Accuracy/F1" : t.metrics.map(m=>m.replace(/-ABCD[E]?|-Category/g,'')).join('+');
  document.getElementById("task-info").innerHTML =
    `<span class="task-tag"><b>${METHOD_LABELS[t.eval_method]||t.eval_method}</b></span>` +
    `<span class="task-tag"><b>${metricStr}</b></span>` +
    `<span class="task-tag"><b>${t.task_type}</b></span>` +
    `<span class="task-tag"><b>${total}</b> 样本（${parts.join(' + ')}）</span>`;
  updateJsonFlowHints();
}

// ─── 1 样本模式 ─────────────────────────────────────────
async function loadOneSample() {
  const tid = document.getElementById("sel-task").value;
  const diff = document.getElementById("sel-diff").value;
  const seed = getSeed();
  const subtype = getSelectedSubtype();
  const area = document.getElementById("single-sample-area");
  document.querySelectorAll(".wizard-step").forEach(s => s.classList.remove("active"));
  area.style.display = "block";
  area.innerHTML = `<div class="card"><div class="card-title">抽取中...</div></div>`;
  try {
    let url = `/api/tasks/${tid}/sample?difficulty=${diff}&seed=${seed}`;
    if (subtype) url += `&subtype=${subtype}`;
    const res = await fetch(url);
    if (!res.ok) { const err = await res.json(); throw new Error(err.detail || res.statusText); }
    const data = await res.json();
    const prompt = data.prompt || "";
    const question = data.question || "";
    const answer = data.answer || "";
    const hasRubric = data.has_rubric;
    const evalMethod = data.eval_method;
    const selDiff = document.getElementById("sel-diff")?.value || "";
    const selTask = getSelectedTask();
    let metricLabel = hasRubric ? 'Rubric' : (data.metrics||[]).map(m => m.replace(/-ABCD[E]?|-Category/g,'')).join('+') || '客观';
    if (selTask?.task_type === "SLC/MLC" && selDiff === "challenge") metricLabel = "F1";

    area.innerHTML = `<div class="card">
      <div class="card-header">
        <span class="card-title">📋 ${data.display_name || '单样本测试'}</span>
        <span class="badge ${hasRubric ? 'badge-rubric' : 'badge-obj'}">${metricLabel}</span>
      </div>
      ${prompt ? `<div style="background:var(--bg-tertiary);padding:10px 14px;border-radius:8px;margin:12px 0;font-size:13px;color:var(--text-secondary)"><b>📌 任务指令</b><br/>${prompt}</div>` : ""}
      <div style="margin:12px 0"><b style="font-size:13px;color:var(--text-muted)">📝 题目内容</b></div>
      <div style="font-size:14px;line-height:1.7;margin-bottom:16px;max-height:400px;overflow-y:auto;white-space:pre-wrap;background:var(--bg-tertiary);padding:14px;border-radius:8px;border:1px solid var(--border-primary)">${question || '<i>无题目内容</i>'}</div>
      ${!hasRubric && answer ? `<details style="margin-bottom:16px"><summary style="cursor:pointer;font-size:13px;color:var(--text-muted)">🔑 参考答案（点击展开）</summary><div style="margin-top:8px;padding:10px 14px;background:var(--bg-tertiary);border-radius:8px;font-size:13px;white-space:pre-wrap">${answer}</div></details>` : ""}
      <label class="form-label">粘贴模型回答</label>
      <textarea class="form-input" id="single-answer" rows="6" placeholder="将模型的回答粘贴到这里..."></textarea>
      <button class="btn btn-primary" style="margin-top:12px;width:100%" onclick="scoreSingle()">📊 评分</button>
      <div id="single-result"></div>
      <div class="wizard-nav" style="margin-top:12px">
        <button class="btn btn-secondary" onclick="backFromSingleSample()">返回向导</button><span></span>
      </div>
    </div>`;
    window._singleTaskId = tid;
    window._singleDiff = diff;
    window._singleSubtype = subtype;
  } catch(e) {
    area.innerHTML = `<div class="card"><div class="card-title">抽取失败: ${e.message}</div>
      <div class="wizard-nav" style="margin-top:12px">
        <button class="btn btn-secondary" onclick="backFromSingleSample()">返回向导</button><span></span>
      </div></div>`;
  }
}

function backFromSingleSample() {
  document.getElementById("single-sample-area").style.display = "none";
  wizardGoTo(1);
}

async function scoreSingle() {
  const pred = document.getElementById("single-answer").value.trim();
  if (!pred) return;
  const seed = getSeed();
  const el = document.getElementById("single-result");
  el.innerHTML = `<div style="margin-top:12px;color:var(--text-muted)">评分中...</div>`;
  try {
    const res = await fetch("/api/eval/score", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        task_id: window._singleTaskId,
        difficulty: window._singleDiff,
        sample_ratio: 1,
        seed: seed,
        subtype: window._singleSubtype || undefined,
        predictions: [pred],
        model_name: "manual",
        judge_api_key: document.getElementById("inp-jkey")?.value || "",
        judge_base_url: document.getElementById("inp-jurl")?.value || "",
        judge_model: document.getElementById("inp-jmodel")?.value || "",
      })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || res.statusText);
    const r = data.results[0];
    el.innerHTML = `<div class="card" style="margin-top:12px">
      <div class="card-title">评分结果</div>
      <pre>${JSON.stringify(r.scores, null, 2)}</pre>
    </div>`;
  } catch(e) {
    el.innerHTML = `<div style="margin-top:12px;color:var(--accent-danger)">评分失败: ${e.message}</div>`;
  }
}

// ─── JSON 导出/导入 ────────────────────────────────────
async function exportQuestions() {
  const tid = document.getElementById("sel-task").value;
  const diff = document.getElementById("sel-diff").value;
  const ratio = window._sampleRatio || 100;
  const seed = getSeed();
  const subtype = getSelectedSubtype();

  const params = new URLSearchParams({
    task_id: tid, difficulty: diff, sample_ratio: ratio, seed: seed,
  });
  if (subtype) params.set("subtype", subtype);

  try {
    const resp = await fetch(`/api/eval/export?${params}`);
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({detail: resp.statusText}));
      throw new Error(err.detail || resp.statusText);
    }
    const contentType = resp.headers.get("content-type") || "";
    const isZip = contentType.includes("zip");

    const blob = isZip
      ? await resp.blob()
      : new Blob([JSON.stringify(await resp.json(), null, 2)], {type: "application/json"});
    const ext = isZip ? "zip" : "json";
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${tid}_${diff}_seed${seed}.${ext}`;
    a.click();
    URL.revokeObjectURL(url);
    const info = document.getElementById("exportInfo");
    info.textContent = isZip
      ? `已导出 ZIP（含合同原文 + 题目 JSON）`
      : `已导出题目 JSON`;
    info.style.display = "";
  } catch(e) {
    alert("导出失败: " + e.message);
  }
}

async function downloadAnswerTemplate() {
  const tid = document.getElementById("sel-task").value;
  const diff = document.getElementById("sel-diff").value;
  const ratio = window._sampleRatio || 100;
  const seed = getSeed();
  const subtype = getSelectedSubtype();

  const t = getSelectedTask();
  if (!t) return;
  const total = diff === "all"
    ? Object.values(t.sample_counts).reduce((a, b) => a + b, 0)
    : (t.sample_counts[diff] || 0);
  const count = ratio >= 100 ? total : ratio === 1 ? 1 : Math.max(1, Math.floor(total * ratio / 100));

  const template = {
    meta: {
      task_id: tid,
      display_name: t.display_name,
      difficulty: diff,
      sample_ratio: ratio,
      seed: seed,
      subtype: subtype || null,
      count: count,
    },
    answers: Array.from({length: count}, (_, i) => ({id: i, answer: ""})),
  };
  const blob = new Blob([JSON.stringify(template, null, 2)], {type: "application/json"});
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${tid}_${diff}_answer_template.json`;
  a.click();
  URL.revokeObjectURL(url);
}

function onJsonFileSelected(input) {
  const file = input.files[0];
  if (!file) return;
  const info = document.getElementById("jsonFileInfo");
  info.textContent = `已选择: ${file.name} (${(file.size / 1024).toFixed(1)} KB)`;
  info.style.display = "";
  document.getElementById("jsonDropZone").classList.add("has-file");
  window._jsonMeta = null;

  const reader = new FileReader();
  reader.onload = function(e) {
    try {
      const data = JSON.parse(e.target.result);
      const meta = data.meta;
      if (!meta) return;
      window._jsonMeta = meta;

      const curTid = document.getElementById("sel-task")?.value || "";
      const curDiff = document.getElementById("sel-diff")?.value || "";
      const curRatio = window._sampleRatio || 100;
      const curSeed = getSeed();
      const curSubtype = getSelectedSubtype();

      const mismatches = [];
      if (meta.task_id && meta.task_id !== curTid) {
        const t = Object.values(taskData.modules).flat().find(x => x.task_id === meta.task_id);
        mismatches.push(`任务: 文件=${t ? t.display_name : meta.task_id}，当前=${document.getElementById("sel-task")?.selectedOptions[0]?.text || curTid}`);
      }
      if (meta.difficulty && meta.difficulty !== curDiff)
        mismatches.push(`难度: 文件=${meta.difficulty}，当前=${curDiff}`);
      if (meta.sample_ratio != null && meta.sample_ratio !== curRatio)
        mismatches.push(`采样: 文件=${meta.sample_ratio}%，当前=${curRatio}%`);
      if (meta.seed != null && meta.seed !== curSeed)
        mismatches.push(`种子: 文件=${meta.seed}，当前=${curSeed}`);
      if ((meta.subtype || "") !== (curSubtype || ""))
        mismatches.push(`子类型: 文件=${meta.subtype || "全部"}，当前=${curSubtype || "全部"}`);

      if (mismatches.length) {
        info.innerHTML = `<span style="color:var(--accent-warning)">⚠️ 文件 meta 与当前配置不一致：</span><br>`
          + mismatches.map(m => `<span style="color:var(--accent-danger);font-size:11px">${m}</span>`).join("<br>")
          + `<br><span style="font-size:11px">提交时将以文件 meta 为准，请确认是否正确</span>`;
      }
    } catch(e) {}
  };
  reader.readAsText(file);
}

function handleJsonDrop(e) {
  e.preventDefault();
  e.currentTarget.classList.remove("dragover");
  const file = e.dataTransfer.files[0];
  if (!file) return;
  const input = document.getElementById("json-file");
  const dt = new DataTransfer();
  dt.items.add(file);
  input.files = dt.files;
  onJsonFileSelected(input);
}

async function runEval() {
  const btn = document.getElementById("btn-run");
  btn.disabled = true; btn.textContent = "⏳ 评测中...";
  const bar = document.getElementById("eval-progress-bar");
  const fill = document.getElementById("eval-progress-fill");
  const status = document.getElementById("eval-status");
  bar.style.display = "block"; fill.style.width = "10%";
  status.textContent = "正在提交评测请求...";

  const tid = document.getElementById("sel-task").value;
  const diff = document.getElementById("sel-diff").value;
  const ratio = window._sampleRatio || 100;
  const seed = getSeed();
  const subtype = getSelectedSubtype();

  const cfg = {
    api_base_url: document.getElementById("inp-url")?.value || "",
    api_key: document.getElementById("inp-key")?.value || "",
    model_name: document.getElementById("inp-model")?.value || "",
    judge_base_url: document.getElementById("inp-jurl")?.value || "",
    judge_api_key: document.getElementById("inp-jkey")?.value || "",
    judge_model: document.getElementById("inp-jmodel")?.value || "",
  };
  localStorage.setItem("evalConfig", JSON.stringify(cfg));

  try {
    let data;
    if (window._evalMode === "json") {
      const fileInput = document.getElementById("json-file");
      if (!fileInput.files.length) throw new Error("请先选择 JSON 文件");
      const formData = new FormData();
      formData.append("file", fileInput.files[0]);
      formData.append("task_id", tid);
      formData.append("difficulty", diff);
      formData.append("sample_ratio", ratio);
      formData.append("seed", seed);
      if (subtype) formData.append("subtype", subtype);
      formData.append("model_name", cfg.model_name || "uploaded");
      formData.append("judge_base_url", cfg.judge_base_url);
      formData.append("judge_api_key", cfg.judge_api_key);
      formData.append("judge_model", cfg.judge_model);
      fill.style.width = "30%";
      status.textContent = "上传 JSON + 评分中...";
      const res = await fetch("/api/eval/upload", { method: "POST", body: formData });
      if (!res.ok) { const err = await res.json(); throw new Error(err.detail || res.statusText); }
      data = await res.json();
    } else {
      fill.style.width = "30%";
      status.textContent = "服务端推理 + 评分中，请耐心等待...";
      const body = { task_id: tid, difficulty: diff, sample_ratio: ratio, seed: seed, subtype: subtype || undefined, ...cfg };
      const res = await fetch("/api/eval/run", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) { const err = await res.json(); throw new Error(err.detail || res.statusText); }
      data = await res.json();
    }
    fill.style.width = "100%";
    status.textContent = `评测完成！耗时 ${data.elapsed_seconds}s`;
    renderEvalResults(data);
  } catch (e) {
    status.textContent = "评测失败: " + e.message; fill.style.width = "0%";
  } finally { btn.disabled = false; btn.textContent = "🚀 开始评测"; }
}

function renderEvalResults(data) {
  const el = document.getElementById("eval-results");
  const s = data.summary;
  const scoreClass = s.average_score >= 0.8 ? "score-good" : s.average_score >= 0.5 ? "score-mid" : "score-bad";
  let html = `<div class="card" style="margin-top:20px">
    <div class="card-header"><span class="card-title">评测结果</span></div>
    <div class="stats-grid">
      <div class="stat-card"><div class="stat-value ${scoreClass}">${(s.average_score * (s.metric === "score_ratio" ? 100 : 1)).toFixed(2)}${s.metric === "score_ratio" ? "%" : ""}</div><div class="stat-label">均分 (${s.metric})</div></div>
      <div class="stat-card"><div class="stat-value">${data.sample_count}</div><div class="stat-label">样本数</div></div>
      <div class="stat-card"><div class="stat-value">${data.elapsed_seconds}s</div><div class="stat-label">耗时</div></div>
    </div><h4 style="margin:12px 0 8px">样本详情</h4>`;
  for (const r of data.results.slice(0, 20)) {
    const scoreVals = r.scores ? Object.values(r.scores).filter(v => typeof v === "number") : [];
    const mainScore = scoreVals.length ? scoreVals[0] : 0;
    const icon = mainScore >= 0.8 ? "✅" : mainScore > 0 ? "⚠️" : "❌";
    const scoreStr = _formatScoreStr(r.scores);
    const qSnippet = (r.question || "").slice(0, 40).replace(/\n/g, " ");
    html += `<div class="detail-item">
      <div class="detail-header" onclick="this.nextElementSibling.classList.toggle('open')">
        <span>${icon} #${r.index + 1}</span>
        <span style="font-size:12px;color:var(--text-secondary);flex:1;margin:0 12px;overflow:hidden;white-space:nowrap;text-overflow:ellipsis">${qSnippet}</span>
        <span style="font-size:12px;color:var(--text-muted);flex-shrink:0">${scoreStr}</span>
      </div>
      <div class="detail-body">
        <div style="margin-bottom:8px"><b style="color:var(--text-muted)">题目：</b><span style="color:var(--text-secondary)">${(r.question||"").slice(0,150).replace(/\n/g," ")}</span></div>
        <div style="margin-bottom:8px"><b style="color:var(--accent-success)">正确答案：</b><span>${(r.reference||"").slice(0,150).replace(/\n/g," ")}</span></div>
        <div style="margin-bottom:8px"><b style="color:var(--accent-primary)">模型回答：</b><span>${(r.prediction||"").slice(0,150).replace(/\n/g," ")}</span></div>
        <pre>${JSON.stringify(r.scores, null, 2)}</pre>
      </div>
    </div>`;
  }
  html += `</div>`;
  el.innerHTML = html;
}

// ─── Results ────────────────────────────────────────────
async function loadResults() {
  const el = document.getElementById("panel-results");
  el.innerHTML = `<div class="card"><div class="card-title">加载中...</div></div>`;
  try {
    const records = await fetch("/api/results").then(r => r.json());
    if (!records.length) {
      el.innerHTML = `<div class="card"><div class="card-title">暂无评测记录</div><div class="card-subtitle">前往「评测执行」开始第一次评测</div></div>`;
      return;
    }
    let html = `<div class="card"><div class="card-header"><span class="card-title">评测历史 (${records.length})</span></div>
      <table class="results-table"><thead><tr>
        <th>任务</th><th>难度</th><th>模型</th><th>裁判模型</th><th>样本</th><th>均分</th><th>耗时</th><th>操作</th>
      </tr></thead><tbody>`;
    for (const r of records) {
      const sc = r.average_score;
      const cls = sc >= 0.8 ? "score-good" : sc >= 0.5 ? "score-mid" : "score-bad";
      const name = r.display_name || r.task_id;
      html += `<tr><td>${name}</td><td>${r.difficulty}</td><td>${r.model}</td><td>${r.judge_model}</td>
        <td>${r.sample_count}</td><td class="${cls}">${sc.toFixed(4)}</td><td>${r.elapsed}s</td>
        <td style="white-space:nowrap">
          <button class="btn btn-secondary" style="padding:4px 10px;font-size:12px" onclick="viewDetail('${r.file}')">查看</button>
          <button class="btn btn-secondary" style="padding:4px 10px;font-size:12px;margin-left:4px" onclick="exportResult('${r.file}')">导出</button>
        </td></tr>`;
    }
    html += `</tbody></table></div><div id="result-detail"></div>`;
    el.innerHTML = html;
  } catch (e) {
    el.innerHTML = `<div class="card"><div class="card-title">加载失败: ${e.message}</div></div>`;
  }
}

async function exportResult(filename) {
  const resp = await fetch("/api/results/" + filename);
  const data = await resp.json();
  const blob = new Blob([JSON.stringify(data, null, 2)], {type: "application/json"});
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function _formatScoreStr(scores) {
  if (!scores) return "";
  const entries = Object.entries(scores).filter(([k,v]) => typeof v === "number");
  if (!entries.length) return "";
  if (entries.length === 1) return `${entries[0][0]}: ${entries[0][1].toFixed(4)}`;
  const hasScore = entries.find(([k]) => k === "score");
  if (hasScore) return `score: ${hasScore[1].toFixed(4)}`;
  return `${entries[0][0]}: ${entries[0][1].toFixed(4)}`;
}

async function viewDetail(filename) {
  const el = document.getElementById("result-detail");
  el.innerHTML = `<div class="card"><div class="card-title">加载中...</div></div>`;
  const data = await fetch("/api/results/" + filename).then(r => r.json());
  const title = data.display_name || data.task_id;
  const DIFF_NAMES = {standard:"标准", challenge:"难例", adversarial:"反例"};
  let html = `<div class="card" style="margin-top:16px">
    <div class="card-header"><span class="card-title">${title} — ${DIFF_NAMES[data.difficulty] || data.difficulty}</span></div>
    <div class="stats-grid">
      <div class="stat-card"><div class="stat-value">${data.summary.average_score.toFixed(4)}</div><div class="stat-label">${data.summary.metric}</div></div>
      <div class="stat-card"><div class="stat-value">${data.sample_count}</div><div class="stat-label">样本</div></div>
      <div class="stat-card"><div class="stat-value">${data.elapsed_seconds}s</div><div class="stat-label">耗时</div></div>
    </div>`;
  for (const r of (data.results || []).slice(0, 50)) {
    const scoreVals = r.scores ? Object.values(r.scores).filter(v => typeof v === "number") : [];
    const mainScore = scoreVals.length ? scoreVals[0] : 0;
    const icon = mainScore >= 0.8 ? "✅" : mainScore > 0 ? "⚠️" : "❌";
    const scoreStr = _formatScoreStr(r.scores);
    const qSnippet = (r.question || "").slice(0, 40).replace(/\n/g, " ");
    html += `<div class="detail-item">
      <div class="detail-header" onclick="this.nextElementSibling.classList.toggle('open')">
        <span>${icon} #${r.index+1}</span>
        <span style="font-size:12px;color:var(--text-secondary);flex:1;margin:0 12px;overflow:hidden;white-space:nowrap;text-overflow:ellipsis">${qSnippet}</span>
        <span style="font-size:12px;color:var(--text-muted);flex-shrink:0">${scoreStr}</span>
      </div>
      <div class="detail-body">
        <div style="margin-bottom:8px"><b style="color:var(--text-muted)">题目：</b><span style="color:var(--text-secondary)">${(r.question||"").slice(0,150).replace(/\n/g," ")}</span></div>
        <div style="margin-bottom:8px"><b style="color:var(--accent-success)">正确答案：</b><span>${(r.reference||"").slice(0,150).replace(/\n/g," ")}</span></div>
        <div style="margin-bottom:8px"><b style="color:var(--accent-primary)">模型回答：</b><span>${(r.prediction||"").slice(0,150).replace(/\n/g," ")}</span></div>
        <pre>${JSON.stringify(r.scores,null,2)}</pre>
      </div>
    </div>`;
  }
  html += `</div>`;
  el.innerHTML = html;
}

// ─── Settings ───────────────────────────────────────────
function loadSettings() {
  const el = document.getElementById("panel-settings");
  el.innerHTML = `<div class="settings-grid">
    <div class="card settings-card">
      <div class="card-header"><span class="card-title">推理模型 API</span></div>
      <div id="settings-infer-status" style="margin:12px 0"></div>
      <div class="form-group"><label class="form-label">Base URL</label>
        <input class="form-input" id="cfg-url" value="" /></div>
      <div class="form-group"><label class="form-label">API Key</label>
        <input class="form-input" id="cfg-key" type="password" value="" /></div>
      <div class="form-group" style="margin-bottom:0"><label class="form-label">Model</label>
        <input class="form-input" id="cfg-model" value="" /></div>
    </div>
    <div class="card settings-card">
      <div class="card-header"><span class="card-title">裁判模型 (Judge)</span></div>
      <div id="settings-judge-status" style="margin:12px 0"></div>
      <div class="form-group"><label class="form-label">Base URL</label>
        <input class="form-input" id="cfg-jurl" value="" /></div>
      <div class="form-group"><label class="form-label">API Key</label>
        <input class="form-input" id="cfg-jkey" type="password" value="" /></div>
      <div class="form-group" style="margin-bottom:0"><label class="form-label">Model</label>
        <input class="form-input" id="cfg-jmodel" value="" /></div>
    </div>
  </div>
  <div class="form-hint" style="margin-bottom:12px">配置保存到服务端 .env，重启后依然生效</div>
  <button class="btn btn-primary" onclick="saveConfig()">保存配置</button>
  <span id="cfg-msg" style="margin-left:12px;font-size:13px;color:var(--accent-success)"></span>`;

  // 从后端读取 .env 配置回填输入框
  fetch("/api/inference-config").then(r=>r.json()).then(c=>{
    if(c.base_url) document.getElementById("cfg-url").value = c.base_url;
    if(c.api_key_masked) document.getElementById("cfg-key").value = c.api_key_masked;
    if(c.model) document.getElementById("cfg-model").value = c.model;
  }).catch(()=>{});
  fetch("/api/judge-config").then(r=>r.json()).then(c=>{
    if(c.base_url) document.getElementById("cfg-jurl").value = c.base_url;
    if(c.api_key_masked) document.getElementById("cfg-jkey").value = c.api_key_masked;
    if(c.model) document.getElementById("cfg-jmodel").value = c.model;
  }).catch(()=>{});
}

function _loadConfigStatus(url, elId) {
  fetch(url).then(r=>r.json()).then(c=>{
    const el=document.getElementById(elId);
    if(!el)return;
    if(c.configured){
      el.innerHTML='';
    } else {
      el.innerHTML='';
    }
  }).catch(()=>{});
}

function saveConfig() {
  const cfg = {
    api_base_url: document.getElementById("cfg-url").value,
    api_key: document.getElementById("cfg-key").value,
    model_name: document.getElementById("cfg-model").value,
    judge_base_url: document.getElementById("cfg-jurl").value,
    judge_api_key: document.getElementById("cfg-jkey").value,
    judge_model: document.getElementById("cfg-jmodel").value,
  };
  localStorage.setItem("evalConfig", JSON.stringify(cfg));

  // 同步写入后端 .env
  fetch("/api/save-config", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      inference_base_url: cfg.api_base_url,
      inference_api_key: cfg.api_key,
      inference_model: cfg.model_name,
      judge_base_url: cfg.judge_base_url,
      judge_api_key: cfg.judge_api_key,
      judge_model: cfg.judge_model,
    }),
  })
    .then(r => {
      if (!r.ok) throw new Error("保存失败");
      document.getElementById("cfg-msg").textContent = "已保存到服务器 ✓";
      _loadConfigStatus("/api/inference-config", "settings-infer-status");
      _loadConfigStatus("/api/judge-config", "settings-judge-status");
    })
    .catch(() => {
      document.getElementById("cfg-msg").textContent = "保存失败 ✗";
    })
    .finally(() => {
      setTimeout(() => { document.getElementById("cfg-msg").textContent = ""; }, 2000);
    });
}

// ─── Init ───────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  const saved = localStorage.getItem("theme");
  if (saved) setTheme(saved); else setTheme("light");
  const route = _parseRoute();
  switchPanel(route.panel);
  if (route.panel === "runner" && route.wizardStep) {
    setTimeout(() => wizardGoTo(route.wizardStep, true), 100);
  }
});
