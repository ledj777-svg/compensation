const state = {
  loaded: false,
  lastIds: [],
  awaitingFormulas: false,
};

const BUILT_IN_FORMULAS = `<p>I'll go with these formulas and calculate now.</p>
<p class="muted">Increment % by rating: 5 = 15%, 4 = 10%, 3 = 7%, 2 = 3%, 1 = 0%<br>
Salary band for A1 at 2 years: Min 11, Median 14, Max 20 LPA<br>
Correction by compa: below 0.80 = 8%, 0.80–0.90 = 5%, 0.90–1.00 = 2%, 1.00+ = 0%<br>
Recommended salary = current × (1 + increment % + correction %)</p>
<p>Example: 10 LPA and rating 4 → 10% + 8% = 18% → 11.8 LPA.</p>`;

const $ = (id) => document.getElementById(id);

function money(value) {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return Number(value).toLocaleString("en-IN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function pct(value) {
  if (value === null || value === undefined) return "—";
  return `${(Number(value) * 100).toFixed(2)}%`;
}

function ratio(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "0.00";
  return Number(value).toFixed(2);
}

function chip(position) {
  return `<span class="chip">${position || "Unknown"}</span>`;
}

function parseIds(text) {
  return String(text)
    .split(/[\s,;]+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function extractIds(text) {
  return (String(text).match(/\b[A-Za-z0-9_-]*\d[A-Za-z0-9_-]*\b/g) || []).filter(
    (token) => !/^(phase1)$/i.test(token)
  );
}

function scrollThread() {
  const thread = $("thread");
  thread.scrollTop = thread.scrollHeight;
}

function addMessage(role, html, extraClass) {
  const wrap = document.createElement("div");
  wrap.className = `msg ${role}${extraClass ? ` ${extraClass}` : ""}`;
  wrap.innerHTML = `<div class="bubble">${html}</div>`;
  $("thread").appendChild(wrap);
  scrollThread();
  return wrap;
}

function setChips(items) {
  const mount = $("chips");
  mount.innerHTML = items
    .map((item) => `<button type="button" class="chip-btn" data-cmd="${item.cmd}">${item.label}</button>`)
    .join("");
  mount.querySelectorAll("button").forEach((button) => {
    button.addEventListener("click", () => handleText(button.dataset.cmd, true));
  });
}

async function api(path, options = {}) {
  const response = await fetch(path, options);
  if (response.status === 409) {
    throw new Error("Upload an Excel workbook first.");
  }
  if (!response.ok) {
    let detail = `Request failed (${response.status})`;
    try {
      const body = await response.json();
      detail = body.detail || detail;
    } catch {
      /* ignore */
    }
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  const type = response.headers.get("content-type") || "";
  if (type.includes("application/json")) return response.json();
  return response;
}

async function downloadBlob(path, filename, body) {
  const options = body
    ? {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      }
    : {};
  const response = await api(path, options);
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function reportTable(rows) {
  if (!rows.length) return `<p class="muted">No matching employees.</p>`;
  const body = rows
    .map(
      (row) => `
      <tr title="${(row.flags || []).join(" | ")}">
        <td>${row.employee_id}</td>
        <td><span class="emp-name">${row.employee_name || "—"}</span><span class="emp-sub">${row.designation || ""}</span></td>
        <td>${row.department}<div class="emp-sub">${row.grade}</div></td>
        <td class="num">${row.performance_rating ?? "—"}</td>
        <td class="num">${money(row.current_salary)}</td>
        <td class="num">${ratio(row.compa_ratio)}</td>
        <td>${chip(row.salary_position)}</td>
        <td class="num">${pct(row.increment_pct)}</td>
        <td class="num">${pct(row.correction_pct)}</td>
        <td class="num">${money(row.recommended_salary)}</td>
      </tr>`
    )
    .join("");
  return `
    <div class="table-wrap">
      <table class="data-table">
        <thead>
          <tr>
            <th>ID</th><th>Employee</th><th>Dept / Grade</th><th>Rating</th>
            <th class="num">Current</th><th class="num">Compa Ratio</th><th>Salary Position</th>
            <th class="num">Increment</th><th class="num">Correction</th><th class="num">Recommended</th>
          </tr>
        </thead>
        <tbody>${body}</tbody>
      </table>
    </div>`;
}

function kpis(items) {
  return `<div class="kpis">${items
    .map(([label, value]) => `<article class="kpi"><span>${label}</span><strong>${value}</strong></article>`)
    .join("")}</div>`;
}

function statList(rows, valueFn, metaFn) {
  if (!rows.length) return `<p class="muted">No data.</p>`;
  return `<table class="stat-table">${rows
    .map(
      (row) =>
        `<tr><td><div class="stat-name">${row.label}</div><div class="stat-meta">${metaFn(row)}</div></td><td class="stat-value">${valueFn(row)}</td></tr>`
    )
    .join("")}</table>`;
}

function afterLoadChips() {
  setChips([
    { label: "Compensation report", cmd: "report" },
    { label: "Budget", cmd: "budget" },
    { label: "Download Excel", cmd: "download report" },
  ]);
}

function greet(alreadyLoaded) {
  if (alreadyLoaded) {
    addMessage(
      "bot",
      `<p>A workbook is already loaded.</p><p class="muted">Ask for a report, budget, or enter employee IDs.</p>`
    );
    afterLoadChips();
    return;
  }
  addMessage(
    "bot",
    `<p>Drop an Excel file here, or attach one with +.</p>
     <div class="drop-hint">Sheets needed: Employee_Master, Increment_Grid, Salary_Band, Salary_Correction_Rules</div>`
  );
  setChips([{ label: "Choose Excel file", cmd: "__attach__" }]);
}

async function uploadFile(file) {
  addMessage("user", `Uploaded ${file.name}`);
  const data = new FormData();
  data.append("file", file);
  try {
    const result = await api("/api/upload", { method: "POST", body: data });
    state.loaded = true;
    const dataset = result.dataset || {};
    const validation = result.validation || dataset.validation || {};
    const issues = validation.issues || [];
    const counts = dataset.sheet_counts || {};
    const missing = dataset.missing_sheets || [];
    const fields = dataset.found_fields || [];
    state.awaitingFormulas = Boolean(
      dataset.awaiting_formulas || missing.length || (counts.Increment_Grid === 0 && counts.Salary_Band === 0)
    );
    const issueHtml = issues.length ? reportishIssues(issues) : "";
    const fieldLine = fields.length
      ? `<p>I found these employee columns:<br><em>${fields.join(", ")}</em></p>`
      : "";
    if (state.awaitingFormulas) {
      addMessage(
        "bot",
        `<p>I read your Excel. ${dataset.employee_count || 0} employees loaded.</p>
         ${fieldLine}
         <p>I did not find Increment_Grid, Salary_Band, or Salary_Correction_Rules in this file.</p>
         <p>Do you have those formulas with you? If yes, upload them in Excel. If no, I will use the built-in formulas and calculate.</p>
         ${issueHtml}
         <div class="actions">
           <button class="btn btn-primary" data-cmd="yes">Yes, I'll upload</button>
           <button class="btn" data-cmd="no">No, use built-in formulas</button>
         </div>`
      );
      bindBubbleActions();
      setChips([
        { label: "Yes, I'll upload", cmd: "yes" },
        { label: "No, use built-in formulas", cmd: "no" },
      ]);
      return;
    }
    addMessage(
      "bot",
      `<p>I read your Excel. ${dataset.employee_count || counts.Employee_Master || 0} employees loaded.</p>
       ${fieldLine}
       <p>I used the Increment_Grid, Salary_Band, and Salary_Correction_Rules from your Excel.</p>
       ${issueHtml}
       <div class="actions">
         <button class="btn btn-primary" data-cmd="report">Compensation report</button>
         <button class="btn" data-cmd="budget">Budget</button>
       </div>`
    );
    bindBubbleActions();
    afterLoadChips();
  } catch (error) {
    addMessage("bot", `<p class="error">${error.message}</p>`);
  }
}

function reportishIssues(issues) {
  const rows = issues
    .map(
      (item) =>
        `<tr><td>${item.sheet || ""}</td><td class="num">${item.row ?? "—"}</td><td>${item.employee_id || "—"}</td><td>${item.code || ""}</td><td>${item.message || ""}</td></tr>`
    )
    .join("");
  return `<div class="table-wrap"><table class="data-table" style="min-width:0"><thead><tr><th>Sheet</th><th>Row</th><th>Employee</th><th>Code</th><th>Message</th></tr></thead><tbody>${rows}</tbody></table></div>`;
}

function bindBubbleActions() {
  $("thread")
    .querySelectorAll(".bubble .btn[data-cmd], .bubble .chip-btn[data-cmd]")
    .forEach((button) => {
      if (button.dataset.bound) return;
      button.dataset.bound = "1";
      button.addEventListener("click", () => handleText(button.dataset.cmd, true));
    });
}

function requireLoaded() {
  if (state.loaded) return true;
  addMessage("bot", `<p>Upload an Excel workbook first.</p>`);
  setChips([{ label: "Choose Excel file", cmd: "__attach__" }]);
  return false;
}

async function showReport() {
  const data = await api("/api/reports");
  const rows = data.reports || [];
  const current = rows.reduce((sum, row) => sum + (row.current_salary || 0), 0);
  const recommended = rows.reduce((sum, row) => sum + (row.recommended_salary || 0), 0);
  addMessage(
    "bot",
    `<h2>Compensation report</h2>
     ${kpis([
       ["Employees", rows.length],
       ["Current payroll", `${money(current)} LPA`],
       ["Recommended", `${money(recommended)} LPA`],
     ])}
     ${reportTable(rows)}
     <div class="actions">
       <button class="btn btn-primary" data-cmd="download report">Download Excel</button>
       <button class="btn" data-cmd="budget">Budget</button>
     </div>`,
    "wide"
  );
  bindBubbleActions();
}

async function showSelected(ids) {
  const data = await api("/api/reports/selected", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ employee_ids: ids }),
  });
  state.lastIds = ids;
  const missing = data.missing_ids?.length ? `<p class="muted">Not found: ${data.missing_ids.join(", ")}</p>` : "";
  addMessage(
    "bot",
    `<h2>Selected employees</h2>${missing}${reportTable(data.reports || [])}
     <div class="actions"><button class="btn" data-cmd="download selected">Download Excel</button></div>`,
    "wide"
  );
  bindBubbleActions();
}

function comparisonHtml(data) {
  const employees = data.employees || [];
  const header = ["<th>Metric</th>", ...employees.map((row) => `<th>${row.employee_id}<div class="emp-sub">${row.employee_name}</div></th>`)].join("");
  const formatters = {
    money,
    percent: pct,
    ratio,
    number: (value) => (value === null || value === undefined ? "—" : value),
    text: (value) => value || "—",
  };
  const body = (data.metrics || [])
    .map((metric) => {
      const format = formatters[metric.kind] || formatters.text;
      const cells = metric.values
        .map((value) => {
          const highlight =
            metric.kind !== "text" && metric.max !== null && metric.max !== metric.min && value === metric.max
              ? "hi"
              : "";
          const rendered = metric.key === "salary_position" ? chip(value) : format(value);
          return `<td class="${metric.kind === "text" ? "" : "num"} ${highlight}">${rendered}</td>`;
        })
        .join("");
      return `<tr><td>${metric.label}</td>${cells}</tr>`;
    })
    .join("");
  return `<div class="table-wrap"><table class="data-table compare-table"><thead><tr>${header}</tr></thead><tbody>${body}</tbody></table></div>`;
}

async function showCompare(ids) {
  if (ids.length < 2) {
    addMessage("bot", `<p>Enter at least two employee IDs to compare. Example: 1001, 1002</p>`);
    return;
  }
  const data = await api("/api/compare", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ employee_ids: ids }),
  });
  state.lastIds = ids;
  const missing = data.missing_ids?.length ? `<p class="muted">Not found: ${data.missing_ids.join(", ")}</p>` : "";
  addMessage(
    "bot",
    `<h2>Comparison</h2>${missing}${comparisonHtml(data)}
     <div class="actions"><button class="btn" data-cmd="download comparison">Download Excel</button></div>`,
    "wide"
  );
  bindBubbleActions();
}

async function showBudget() {
  const data = await api("/api/budget");
  addMessage(
    "bot",
    `<h2>Budget impact</h2>${kpis([
      ["Current payroll", `${money(data.current_payroll)} LPA`],
      ["Proposed payroll", `${money(data.recommended_payroll)} LPA`],
      ["Increment cost", `${money(data.increment_cost)} LPA`],
      ["Correction cost", `${money(data.correction_cost)} LPA`],
      ["Total cost", `${money(data.total_compensation_cost)} LPA`],
      ["Average increase", pct(data.increase_pct)],
    ])}<div class="split-lists"><div><h3>By department</h3>${statList(
      data.by_department || [],
      (row) => `${money(row.total_compensation_cost)} LPA`,
      (row) => `${row.headcount} emp · ${pct(row.increase_pct)}`
    )}</div><div><h3>By grade</h3>${statList(
      data.by_grade || [],
      (row) => pct(row.increase_pct),
      (row) => `${row.headcount} emp · ${money(row.total_compensation_cost)} LPA`
    )}</div></div><div class="actions"><button class="btn" data-cmd="download budget">Download Excel</button></div>`,
    "wide"
  );
  bindBubbleActions();
}

async function handleDownload(kind) {
  if (kind === "validation") {
    await downloadBlob("/api/export/validation", "validation_report.xlsx");
  } else if (kind === "budget") {
    await downloadBlob("/api/export/budget", "budget_analysis.xlsx");
  } else if (kind === "comparison") {
    await downloadBlob("/api/export/comparison", "employee_comparison.xlsx", { employee_ids: state.lastIds });
  } else if (kind === "selected") {
    await downloadBlob("/api/export/selected", "selected_employees_report.xlsx", { employee_ids: state.lastIds });
  } else {
    await downloadBlob("/api/export/compensation", "compensation_report.xlsx");
  }
  addMessage("bot", `<p>Download started.</p>`);
}

const SUPPORT_LIST = `<p class="muted">I can help you with:<br>uploading an Excel workbook<br>generating a compensation report<br>looking up selected employee IDs<br>comparing employees<br>budget impact<br>downloading Excel reports</p>`;

function hasCompensationIntent(text) {
  const lower = String(text).toLowerCase();
  return /report|budget|compar|download|validat|compensat|upload|excel/.test(lower)
    || extractIds(text).length > 0;
}

const WORD_STEMS = {
  calculated: "calculate",
  calculation: "calculate",
  calculations: "calculate",
  calc: "calculate",
  calcuate: "calculate",
  calulate: "calculate",
  salaries: "salary",
  salry: "salary",
  sallary: "salary",
  slary: "salary",
  recommended: "recommend",
  recommendation: "recommend",
  recommendations: "recommend",
  increments: "increment",
  hiked: "hike",
  hikes: "hike",
  compared: "compare",
  comparison: "compare",
  comparing: "compare",
  uploaded: "upload",
  uploading: "upload",
  explained: "explain",
  meaning: "mean",
  means: "mean",
};

function stemWord(word) {
  return WORD_STEMS[word] || word;
}

function normalizeTalk(text) {
  return String(text)
    .toLowerCase()
    .replace(/['’]/g, "")
    .replace(/[^a-z0-9\s]/g, " ")
    .replace(/(.)\1{2,}/g, "$1$1")
    .replace(/\s+/g, " ")
    .trim()
    .split(" ")
    .map(stemWord)
    .join(" ");
}

function phraseBank(kind) {
  const data = window.CHAT_PHRASES || { fillers: [], greetings: [], thanks: [] };
  return new Set((data[kind] || []).map((item) => normalizeTalk(item)));
}

function messageHitsPhrases(text, phrases) {
  const normalized = normalizeTalk(text);
  if (!normalized) return false;
  if (phrases.has(normalized)) return true;
  for (const phrase of phrases) {
    if (phrase.includes(" ") && (normalized === phrase || normalized.includes(` ${phrase} `) || normalized.startsWith(`${phrase} `) || normalized.endsWith(` ${phrase}`))) {
      return true;
    }
  }
  return false;
}

function tokensAreKnown(text, wordSet, fillers) {
  const tokens = normalizeTalk(text).split(" ").filter(Boolean);
  if (!tokens.length) return false;
  let hit = false;
  for (const token of tokens) {
    if (wordSet.has(token)) {
      hit = true;
      continue;
    }
    if (fillers.has(token)) continue;
    return false;
  }
  return hit;
}

function isGreeting(text) {
  if (hasCompensationIntent(text)) return false;
  const greetings = phraseBank("greetings");
  const fillers = phraseBank("fillers");
  const greetingWords = new Set([...greetings].filter((item) => !item.includes(" ")));
  return messageHitsPhrases(text, greetings) || tokensAreKnown(text, greetingWords, fillers);
}

function isThanks(text) {
  if (hasCompensationIntent(text)) return false;
  const thanks = phraseBank("thanks");
  const fillers = phraseBank("fillers");
  const thankWords = new Set([...thanks].filter((item) => !item.includes(" ")));
  return messageHitsPhrases(text, thanks) || tokensAreKnown(text, thankWords, fillers);
}

function looksLikeQuestion(text) {
  const lower = String(text).toLowerCase();
  return /\?/.test(text)
    || /\b(what|whats|whatis|which|where|why|how|who|when|can i|can you|can we|do i|do you|should i|need to|tell me|explain|meaning|sample|template|format)\b/.test(
      lower
    );
}

function isShortAction(text) {
  const t = normalizeTalk(text);
  return /^(report|budget|compare|download|validation|help|clear|cls|clr)(\s.*)?$/.test(t);
}

function isClear(text) {
  const t = normalizeTalk(text);
  return /^(clear|cls|clr|\/clear|\/cls)$/.test(t);
}

function clearChat() {
  $("thread").innerHTML = "";
  $("chips").innerHTML = "";
  const input = $("composerInput");
  if (input) input.value = "";
  greet(state.loaded);
  if (state.awaitingFormulas) {
    addMessage(
      "bot",
      `<p>Do you have the formulas with you? If yes, upload them in Excel. If no, I will use the built-in formulas and calculate.</p>`
    );
    setChips([
      { label: "Yes, I'll upload", cmd: "yes" },
      { label: "No, use built-in formulas", cmd: "no" },
    ]);
  }
}

const FAQ_STOP = new Set(["the", "a", "an", "is", "do", "does", "did", "i", "you", "u", "we", "me", "to", "of", "for", "in", "on", "my", "please", "pls", "plz", "and", "or", "this", "that", "it", "be", "was", "are"]);

function contentWords(text) {
  return normalizeTalk(text)
    .split(" ")
    .filter((word) => word.length > 1 && !FAQ_STOP.has(word));
}

function matchFaq(text) {
  const items = window.CHAT_FAQ || [];
  const normalized = normalizeTalk(text);
  if (!normalized || !items.length) return null;
  const userSet = new Set(contentWords(text));
  const genericIds = new Set(["what-is-this", "how-to-use"]);
  let best = null;
  let bestScore = 0;
  for (const item of items) {
    let score = 0;
    for (const question of item.questions || []) {
      const q = normalizeTalk(question);
      if (normalized === q) {
        score = Math.max(score, 100);
        continue;
      }
      if (q.length > 12 && (normalized.includes(q) || q.includes(normalized))) {
        score = Math.max(score, 80);
      }
      const qWords = contentWords(question);
      if (qWords.length >= 2) {
        const overlap = qWords.filter((word) => userSet.has(word)).length;
        if (overlap >= 2) {
          score = Math.max(score, Math.round((overlap / qWords.length) * 90));
        }
      }
    }
    const weakKeys = new Set(["what", "how", "this", "that", "tool", "app", "do", "use", "who", "why"]);
    const specificHits = (item.keywords || []).filter((keyword) => {
      const key = stemWord(normalizeTalk(keyword));
      return key.length > 3 && !weakKeys.has(key) && userSet.has(key);
    });
    score += specificHits.length * 28;
    if (genericIds.has(item.id)) score -= 20;
    if (score > bestScore) {
      bestScore = score;
      best = item;
    }
  }
  if (!best) return null;
  if (bestScore >= 40) return best;
  if (looksLikeQuestion(text) && bestScore >= 28) return best;
  return null;
}

function isYes(text) {
  const t = normalizeTalk(text);
  return (
    t === "y" ||
    /\b(yes|yeah|yep|yup|ya|ha|hai|i have|i do|i will upload|ill upload)\b/.test(t)
  );
}

function isNo(text) {
  const t = normalizeTalk(text);
  return /^(no|nope|nah|n|nahi|no thanks|dont have|do not have|no formula|no formulas|use default|use defaults|go ahead|proceed|calculate|no need)(\b.*)?$/.test(
    t
  );
}

function interpret(text) {
  const raw = text.trim();
  const lower = raw.toLowerCase();
  if (!raw) return { type: "empty" };
  if (raw === "__attach__") return { type: "attach" };
  if (isClear(raw)) return { type: "clear" };
  if (state.awaitingFormulas && isYes(raw)) return { type: "formula_yes" };
  if (state.awaitingFormulas && isNo(raw)) return { type: "formula_no" };
  if (isGreeting(raw)) return { type: "greet" };
  if (isThanks(raw)) return { type: "thanks" };
  const idsEarly = extractIds(raw);
  if (idsEarly.length >= 2) return { type: "compare", ids: idsEarly };
  if (idsEarly.length === 1 && !looksLikeQuestion(raw)) return { type: "selected", ids: idsEarly };
  const faq = !isShortAction(raw) ? matchFaq(raw) : null;
  if (faq) return { type: "faq", item: faq };
  if (/\bhelp\b/.test(lower) || /what can you|how do i use|how to use/.test(lower)) return { type: "help" };
  if (/download/.test(lower)) {
    if (/budget/.test(lower)) return { type: "download", what: "budget" };
    if (/valid/.test(lower)) return { type: "download", what: "validation" };
    if (/compar/.test(lower)) return { type: "download", what: "comparison" };
    if (/select/.test(lower)) return { type: "download", what: "selected" };
    return { type: "download", what: "report" };
  }
  if (/budget/.test(lower)) return { type: "budget" };
  if (/validat/.test(lower)) return { type: "validation" };
  const ids = extractIds(raw);
  if (/compar/.test(lower)) return { type: "compare", ids };
  if (/report|compensat/.test(lower)) {
    return ids.length ? { type: "selected", ids } : { type: "report" };
  }
  if (ids.length && raw.replace(/[\s,;]+/g, "") === ids.join("")) {
    return ids.length >= 2 ? { type: "compare", ids } : { type: "selected", ids };
  }
  if (ids.length >= 2) return { type: "compare", ids };
  if (ids.length === 1) return { type: "selected", ids };
  return { type: "unknown" };
}

async function handleText(text, fromChip) {
  if (text === "__attach__") {
    $("fileInput").click();
    return;
  }
  if (isClear(text)) {
    clearChat();
    return;
  }
  if (!fromChip) addMessage("user", text);
  else addMessage("user", text.replace(/^__attach__$/, "Choose Excel file"));

  const intent = interpret(text);
  try {
    if (intent.type === "empty") return;
    if (intent.type === "attach") {
      $("fileInput").click();
      return;
    }
    if (intent.type === "formula_yes") {
      addMessage(
        "bot",
        `<p>Please upload the Excel that has your formulas.</p><p class="muted">Sheets: Increment_Grid, Salary_Band, Salary_Correction_Rules. I will keep the employees already loaded and use your formulas instead of the built-in ones.</p>`
      );
      setChips([{ label: "Choose Excel file", cmd: "__attach__" }]);
      return;
    }
    if (intent.type === "formula_no") {
      await api("/api/use-defaults", { method: "POST" });
      state.awaitingFormulas = false;
      addMessage("bot", BUILT_IN_FORMULAS);
      afterLoadChips();
      await showReport();
      return;
    }
    if (state.awaitingFormulas && !["faq", "greet", "thanks", "help"].includes(intent.type)) {
      addMessage(
        "bot",
        `<p>Do you have the formulas with you? If yes, upload them in Excel. If no, I will use the built-in formulas and calculate.</p>`
      );
      setChips([
        { label: "Yes, I'll upload", cmd: "yes" },
        { label: "No, use built-in formulas", cmd: "no" },
      ]);
      return;
    }
    if (intent.type === "greet") {
      addMessage(
        "bot",
        `<p>Hi. I am here to support you with compensation planning.</p>${SUPPORT_LIST}<p>Upload an Excel file, type <em>report</em>, type <em>budget</em>, or enter employee IDs such as <em>1001, 1002</em>.</p>`
      );
      if (state.loaded) afterLoadChips();
      return;
    }
    if (intent.type === "thanks") {
      addMessage(
        "bot",
        `<p>Thank you. Happy to help.</p><p class="muted">If you need anything else, I can still run a report, compare employees, or show budget impact.</p>`
      );
      return;
    }
    if (intent.type === "faq") {
      addMessage("bot", intent.item.answer);
      if (state.loaded) afterLoadChips();
      return;
    }
    if (intent.type === "help") {
      addMessage(
        "bot",
        `<p>I am here to support you with compensation planning.</p>${SUPPORT_LIST}`
      );
      if (state.loaded) afterLoadChips();
      return;
    }
    if (intent.type === "unknown") {
      addMessage(
        "bot",
        `<p>I can't process this request.</p><p>I only have access to compensation planning in this chat.</p>${SUPPORT_LIST}`
      );
      return;
    }
    if (!requireLoaded()) return;
    if (intent.type === "report") await showReport();
    else if (intent.type === "selected") await showSelected(intent.ids);
    else if (intent.type === "compare") await showCompare(intent.ids);
    else if (intent.type === "budget") await showBudget();
    else if (intent.type === "validation") await handleDownload("validation");
    else if (intent.type === "download") await handleDownload(intent.what);
  } catch (error) {
    addMessage("bot", `<p class="error">${error.message}</p>`);
  }
}

function bindComposer() {
  const form = $("composerForm");
  const input = $("composerInput");
  const fileInput = $("fileInput");
  const thread = $("thread");

  $("attachBtn").addEventListener("click", () => fileInput.click());
  fileInput.addEventListener("change", () => {
    const file = fileInput.files[0];
    if (file) uploadFile(file);
    fileInput.value = "";
  });

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const text = input.value.trim();
    if (!text) return;
    input.value = "";
    handleText(text, false);
  });

  ["dragenter", "dragover"].forEach((name) => {
    thread.addEventListener(name, (event) => {
      event.preventDefault();
      thread.classList.add("is-over");
    });
  });
  ["dragleave", "drop"].forEach((name) => {
    thread.addEventListener(name, (event) => {
      event.preventDefault();
      thread.classList.remove("is-over");
    });
  });
  thread.addEventListener("drop", (event) => {
    const file = event.dataTransfer.files[0];
    if (file) uploadFile(file);
  });
}

async function boot() {
  bindComposer();
  try {
    const status = await api("/api/status");
    state.loaded = Boolean(status.loaded);
    state.awaitingFormulas = Boolean(status.dataset && status.dataset.awaiting_formulas);
    greet(state.loaded);
  } catch {
    greet(false);
  }
}

boot();
