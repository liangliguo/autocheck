function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

async function readJson(response) {
  const text = await response.text();
  if (!text) {
    return {};
  }
  try {
    return JSON.parse(text);
  } catch (_error) {
    return { detail: text };
  }
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  const payload = await readJson(response);
  if (!response.ok) {
    const message = payload.detail || payload.message || "请求失败";
    throw new Error(message);
  }
  return payload;
}

function formatBool(value) {
  return value ? "开启" : "关闭";
}

function renderRecentReports(container, recentReports) {
  if (!recentReports.length) {
    container.innerHTML = '<div class="empty-state compact">还没有生成过报告。</div>';
    return;
  }
  container.innerHTML = `
    <ul class="recent-list">
      ${recentReports.map((path) => `<li class="recent-item">${escapeHtml(path)}</li>`).join("")}
    </ul>
  `;
}

function renderConfigSummary(container, configPayload) {
  const summaryKeys = [
    ["AUTOCHECK_CHAT_MODEL", "聊天模型"],
    ["AUTOCHECK_VERIFY_MODEL", "核验模型"],
    ["AUTOCHECK_ENABLE_LLM_VERIFICATION", "LLM 核验"],
    ["AUTOCHECK_CHUNK_SIZE", "切块大小"],
  ];
  container.innerHTML = summaryKeys.map(([key, label]) => {
    const rawValue = configPayload.values[key];
    const value = typeof rawValue === "boolean" ? formatBool(rawValue) : rawValue || "未设置";
    return `
      <article class="summary-card">
        <span>${escapeHtml(label)}</span>
        <strong>${escapeHtml(value)}</strong>
      </article>
    `;
  }).join("");
}

function renderRunResult(container, payload) {
  const report = payload.report;
  const summary = report.summary;
  const progress = report.progress || {};
  const references = report.parsed_document.references || [];
  const assessments = report.assessments || [];

  const referenceHtml = references.length
    ? references.map((reference) => `
        <article class="reference-card">
          <strong>${escapeHtml(reference.ref_id)} · ${escapeHtml(reference.title || "Unknown reference")}</strong>
          <p>作者：${escapeHtml((reference.authors || []).join(", ") || "未知")}</p>
          <p>年份：${escapeHtml(reference.year ?? "未知")}</p>
          <p>原始条目：${escapeHtml((reference.raw_text || "").slice(0, 280))}</p>
        </article>
      `).join("")
    : '<div class="empty-state compact">没有解析出参考文献。</div>';

  const assessmentHtml = assessments.length
    ? assessments.map((item) => {
        const evidence = (item.evidence || []).slice(0, 3).map((chunk) => `
          <div class="evidence"><strong>${escapeHtml(chunk.chunk_id)}</strong><br>${escapeHtml((chunk.text || "").slice(0, 320))}</div>
        `).join("");
        const supported = (item.supported_points || []).join("; ") || "无";
        const concerns = (item.concerns || []).join("; ") || "无";
        const referenceTitle = item.reference?.title || "Unknown reference";
        return `
          <article class="assessment-card">
            <div class="assessment-head">
              <strong>${escapeHtml(item.claim_id)} × ${escapeHtml(item.citation_marker)}</strong>
              <span class="badge ${escapeHtml(item.verdict)}">${escapeHtml(item.verdict)}</span>
            </div>
            <p><strong>引用文献：</strong>${escapeHtml(referenceTitle)}</p>
            <p><strong>置信度：</strong>${escapeHtml(Number(item.confidence ?? 0).toFixed(2))}</p>
            <p><strong>Claim：</strong>${escapeHtml(item.claim_text)}</p>
            <p><strong>Reasoning：</strong>${escapeHtml(item.reasoning)}</p>
            <p><strong>Supported points：</strong>${escapeHtml(supported)}</p>
            <p><strong>Concerns：</strong>${escapeHtml(concerns)}</p>
            ${evidence}
          </article>
        `;
      }).join("")
    : '<div class="empty-state compact">没有生成 assessment。</div>';

  const pathItems = Object.entries(payload.report_paths || {}).map(([key, value]) => (
    `<li class="path-item"><strong>${escapeHtml(key)}</strong>：${escapeHtml(value)}</li>`
  )).join("");

  // Extract workspace name from source path for export links
  const sourcePath = payload.source_path || report.source_path || "";
  const workspaceMatch = sourcePath.match(/workspaces\/([^\/]+)\//);
  const workspaceName = workspaceMatch ? workspaceMatch[1] : null;

  const exportButtons = workspaceName ? `
    <div class="export-buttons">
      <a class="button" href="/api/export/references/${escapeHtml(workspaceName)}" download>导出参考文献 PDF</a>
      <a class="button" href="/api/export/reports/${escapeHtml(workspaceName)}" download>导出报告文件</a>
      <a class="button" href="/api/export/workspace/${escapeHtml(workspaceName)}" download>导出全部文件</a>
    </div>
  ` : '';

  container.innerHTML = `
    <div class="metrics">
      <div class="metric"><span>Claims</span><strong>${escapeHtml(summary.total_claims)}</strong></div>
      <div class="metric"><span>Assessments</span><strong>${escapeHtml(summary.total_assessments)}</strong></div>
      <div class="metric"><span>Strong</span><strong>${escapeHtml(summary.strong_support)}</strong></div>
      <div class="metric"><span>Partial</span><strong>${escapeHtml(summary.partial_support)}</strong></div>
      <div class="metric"><span>Unsupported</span><strong>${escapeHtml(summary.unsupported_or_misleading)}</strong></div>
      <div class="metric"><span>Not Found</span><strong>${escapeHtml(summary.not_found)}</strong></div>
    </div>
    ${exportButtons}
    <ul class="meta-list">
      <li class="meta-item"><strong>状态：</strong>${escapeHtml(report.status)}</li>
      <li class="meta-item"><strong>输入源：</strong>${escapeHtml(payload.source_path || report.source_path)}</li>
      <li class="meta-item"><strong>参考文献进度：</strong>${escapeHtml(`${progress.completed_references ?? "-"} / ${progress.total_references ?? "-"}`)}</li>
      <li class="meta-item"><strong>核验进度：</strong>${escapeHtml(`${progress.completed_assessments ?? "-"} / ${progress.total_assessments ?? "-"}`)}</li>
    </ul>
    <div style="height:16px"></div>
    <h3>报告路径</h3>
    <ul class="path-list">${pathItems}</ul>
    <div style="height:16px"></div>
    <h3>解析出的参考文献</h3>
    <div class="reference-grid">${referenceHtml}</div>
    <div style="height:16px"></div>
    <h3>逐条核验结果</h3>
    <div class="assessment-grid">${assessmentHtml}</div>
    <details>
      <summary>查看 Markdown 报告预览</summary>
      <pre>${escapeHtml(payload.markdown_preview || "")}</pre>
    </details>
  `;
}

function groupFields(fields) {
  const groups = new Map();
  fields.forEach((field) => {
    if (!groups.has(field.group)) {
      groups.set(field.group, []);
    }
    groups.get(field.group).push(field);
  });
  return groups;
}

function inputValueForField(field, value) {
  if (field.control === "boolean") {
    return `
      <label class="checkbox">
        <input type="checkbox" name="${escapeHtml(field.key)}" ${value ? "checked" : ""}>
        <span>${escapeHtml(field.label)}</span>
      </label>
    `;
  }

  const type = field.control === "password" ? "password" : field.control === "number" ? "number" : "text";
  const minAttr = field.min_value !== null && field.min_value !== undefined ? `min="${escapeHtml(field.min_value)}"` : "";
  const stepAttr = field.step ? `step="${escapeHtml(field.step)}"` : "";
  const placeholderAttr = field.placeholder ? `placeholder="${escapeHtml(field.placeholder)}"` : "";
  return `
    <label>
      ${escapeHtml(field.label)}
      <input
        type="${type}"
        name="${escapeHtml(field.key)}"
        value="${escapeHtml(value ?? "")}"
        ${minAttr}
        ${stepAttr}
        ${placeholderAttr}
      >
    </label>
  `;
}

function renderConfigForm(container, payload) {
  const groups = groupFields(payload.fields || []);
  container.classList.add("config-groups");
  container.innerHTML = Array.from(groups.entries()).map(([groupName, fields]) => `
    <section class="config-group">
      <div>
        <h3>${escapeHtml(groupName)}</h3>
      </div>
      ${fields.map((field) => `
        <div class="config-field">
          ${inputValueForField(field, payload.values[field.key])}
          <p class="config-field-copy">${escapeHtml(field.description)}</p>
        </div>
      `).join("")}
    </section>
  `).join("");
}

function applyConfigValues(form, payload, useDefaults = false) {
  (payload.fields || []).forEach((field) => {
    const element = form.elements.namedItem(field.key);
    if (!element) {
      return;
    }
    const nextValue = useDefaults ? field.default_value : payload.values[field.key];
    if (field.control === "boolean") {
      element.checked = Boolean(nextValue);
      return;
    }
    element.value = nextValue ?? "";
  });
}

function collectConfigValues(form, payload) {
  const values = {};
  (payload.fields || []).forEach((field) => {
    const element = form.elements.namedItem(field.key);
    if (!element) {
      return;
    }
    if (field.control === "boolean") {
      values[field.key] = Boolean(element.checked);
      return;
    }
    if (field.value_type === "int") {
      values[field.key] = element.value === "" ? "" : Number.parseInt(element.value, 10);
      return;
    }
    if (field.value_type === "float") {
      values[field.key] = element.value === "" ? "" : Number.parseFloat(element.value);
      return;
    }
    values[field.key] = element.value;
  });
  return values;
}

async function initRunPage() {
  const form = document.getElementById("run-form");
  const submitButton = document.getElementById("run-submit");
  const errorBox = document.getElementById("run-error");
  const resultBox = document.getElementById("run-result");
  const recentReportsBox = document.getElementById("recent-reports");
  const configSummaryBox = document.getElementById("config-summary");
  const statusPill = document.getElementById("run-status");

  const [recentPayload, configPayload] = await Promise.all([
    fetchJson("/api/reports/recent"),
    fetchJson("/api/config"),
  ]);
  renderRecentReports(recentReportsBox, recentPayload.recent_reports || []);
  renderConfigSummary(configSummaryBox, configPayload);

  form?.addEventListener("submit", async (event) => {
    event.preventDefault();
    errorBox.classList.add("is-hidden");
    errorBox.textContent = "";
    submitButton.disabled = true;
    submitButton.textContent = "正在运行…";
    statusPill.textContent = "任务执行中";

    try {
      const payload = await fetchJson("/api/run", {
        method: "POST",
        body: new FormData(form),
      });
      renderRunResult(resultBox, payload);
      renderRecentReports(recentReportsBox, payload.recent_reports || []);
      statusPill.textContent = "运行完成";
    } catch (error) {
      errorBox.textContent = error.message;
      errorBox.classList.remove("is-hidden");
      statusPill.textContent = "运行失败";
    } finally {
      submitButton.disabled = false;
      submitButton.textContent = "提交核验任务";
    }
  });
}

async function initConfigPage() {
  const form = document.getElementById("config-form");
  const groupsContainer = document.getElementById("config-groups");
  const metaBar = document.getElementById("config-meta");
  const submitButton = document.getElementById("config-submit");
  const resetButton = document.getElementById("config-reset");
  const errorBox = document.getElementById("config-error");
  const successBox = document.getElementById("config-success");
  const statusPill = document.getElementById("config-status");

  let configPayload = await fetchJson("/api/config");
  renderConfigForm(groupsContainer, configPayload);
  metaBar.textContent = `配置文件：${configPayload.env_path}`;
  statusPill.textContent = configPayload.has_env_file ? "已加载 .env" : "将创建 .env";

  form?.addEventListener("submit", async (event) => {
    event.preventDefault();
    errorBox.classList.add("is-hidden");
    successBox.classList.add("is-hidden");
    submitButton.disabled = true;
    submitButton.textContent = "正在保存…";
    statusPill.textContent = "保存中";

    try {
      const values = collectConfigValues(form, configPayload);
      configPayload = await fetchJson("/api/config", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ values }),
      });
      applyConfigValues(form, configPayload, false);
      successBox.textContent = configPayload.message || "配置已保存。";
      successBox.classList.remove("is-hidden");
      metaBar.textContent = `配置文件：${configPayload.env_path}`;
      statusPill.textContent = "已保存";
    } catch (error) {
      errorBox.textContent = error.message;
      errorBox.classList.remove("is-hidden");
      statusPill.textContent = "保存失败";
    } finally {
      submitButton.disabled = false;
      submitButton.textContent = "保存配置";
    }
  });

  resetButton?.addEventListener("click", () => {
    errorBox.classList.add("is-hidden");
    successBox.classList.add("is-hidden");
    applyConfigValues(form, configPayload, true);
    statusPill.textContent = "已恢复默认值";
  });
}

document.addEventListener("DOMContentLoaded", () => {
  const page = document.body.dataset.page;
  if (page === "run") {
    initRunPage().catch((error) => {
      const box = document.getElementById("run-error");
      const statusPill = document.getElementById("run-status");
      if (box) {
        box.textContent = error.message || "初始化失败";
        box.classList.remove("is-hidden");
      }
      if (statusPill) {
        statusPill.textContent = "初始化失败";
      }
    });
    return;
  }

  if (page === "config") {
    initConfigPage().catch((error) => {
      const box = document.getElementById("config-error");
      const statusPill = document.getElementById("config-status");
      if (box) {
        box.textContent = error.message || "初始化失败";
        box.classList.remove("is-hidden");
      }
      if (statusPill) {
        statusPill.textContent = "初始化失败";
      }
    });
  }
});
