"use strict";

const state = { notes: [], tasks: [], progress: [], selected: null, counts: {}, retrieval: null };
const STATUS_LABEL = { unread: "未开始", reading: "在读", mastered: "已掌握" };
const el = (id) => document.getElementById(id);

function toast(message, kind = "info") {
  const node = el("toast");
  node.textContent = message;
  node.className = `toast ${kind}`;
  node.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => { node.hidden = true; }, 4200);
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  let payload = null;
  try { payload = await response.json(); } catch (_) { /* non-JSON error page */ }
  if (!response.ok || !payload || payload.ok === false) {
    const detail = payload && payload.error ? payload.error : {};
    const pc = payload && payload.powercontext ? `（PowerContext：${detail.code || ""}）` : "";
    throw new Error(`${detail.message || `请求失败 ${response.status}`}${pc}`);
  }
  return payload.data;
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (ch) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));
}

function tagChips(items, cls = "") {
  if (!items || !items.length) return "";
  return `<span class="chips ${cls}">${items.map((item) => `<i>${escapeHtml(item)}</i>`).join("")}</span>`;
}

function shortId(value) {
  const text = String(value || "");
  return text.length > 18 ? `${text.slice(0, 10)}…${text.slice(-5)}` : text;
}

function fmtTime(value) {
  return value ? String(value).replace("T", " ").slice(0, 16) : "—";
}

// --------------------------------------------------------------------- reading

async function refresh({ keepSelection = true } = {}) {
  const data = await api("/api/state");
  state.notes = data.notes || [];
  state.tasks = data.tasks || [];
  state.progress = data.progress || [];
  state.counts = data.record_counts || {};
  state.retrieval = null;
  if (!keepSelection || !state.notes.some((note) => note.id === state.selected)) {
    state.selected = state.notes.length ? state.notes[0].id : null;
  }
  renderList();
  renderDetail();
  return data;
}

async function runSearch() {
  const params = new URLSearchParams();
  const query = el("q").value.trim();
  const tags = el("tagf").value.trim();
  const status = el("statusf").value;
  if (query) params.set("q", query);
  if (tags) params.set("tags", tags);
  if (params.has("tags")) params.set("match", el("match").value);
  if (status) params.set("status", status);
  if (!params.toString()) return refresh();

  const data = await api(`/api/search?${params.toString()}`);
  const all = await api("/api/state");
  state.notes = data.notes || [];
  state.tasks = all.tasks;
  state.progress = all.progress;
  state.counts = all.record_counts;
  state.retrieval = data.powercontext || null;
  state.selected = state.notes.length ? state.notes[0].id : null;
  renderList();
  renderDetail();
  renderRetrieval(data);
}

function renderRetrieval(data) {
  const pc = data.powercontext || {};
  const parts = [];
  if (data.query) parts.push(`关键词「${escapeHtml(data.query)}」：PowerContext 文本检索命中 ${pc.search_hits} 条记录`);
  if (pc.tag_filter && pc.tag_filter.length) {
    parts.push(`标签 ${escapeHtml(pc.tag_filter.join(" / "))}（${pc.tag_match === "all" ? "全部满足" : "任一满足"}）：服务端返回 ${pc.tag_filter_records} 条记录`);
  }
  if (pc.search_error) parts.push(`文本检索失败：${escapeHtml(pc.search_error)}`);
  if (pc.tag_error) parts.push(`标签过滤失败：${escapeHtml(pc.tag_error)}`);
  parts.push(`界面结果 ${data.notes.length} 条（已按当前状态折叠）`);
  el("retrieval-note").innerHTML = parts.join("　·　");
}

function renderList() {
  const list = el("note-list");
  if (!state.notes.length) {
    list.innerHTML = `<li class="empty">没有匹配的笔记。用左侧表单记录第一条。</li>`;
    return;
  }
  list.innerHTML = state.notes.map((note) => `
    <li class="note-card ${note.id === state.selected ? "active" : ""}" data-id="${escapeHtml(note.id)}">
      <div class="note-head">
        <h3>${escapeHtml(note.title)}</h3>
        <span class="status ${escapeHtml(note.status)}">${escapeHtml(note.status_label || STATUS_LABEL[note.status])}</span>
      </div>
      <p class="note-meta">
        ${note.course ? `<b>${escapeHtml(note.course)}</b> · ` : ""}
        更新 ${fmtTime(note.updated_at)} ·
        ${note.open_tasks ? `${note.open_tasks} 项待办未完成` : "待办已清空"}
      </p>
      <p class="note-body">${escapeHtml((note.body || "").slice(0, 90))}</p>
      <footer>
        ${tagChips(note.tags)}${tagChips(note.keywords, "kw")}
        <span class="prov" title="修订数 / Atomic Memory 记录数">r${note.revisions}${note.chunks > 1 ? ` · ${note.chunks} 块` : ""}</span>
        ${(note.matched_via || []).length ? tagChips(note.matched_via, "via") : ""}
      </footer>
    </li>`).join("");
  list.querySelectorAll(".note-card").forEach((card) => {
    card.addEventListener("click", () => {
      state.selected = card.dataset.id;
      renderList();
      renderDetail();
    });
  });
}

function renderDetail() {
  const detail = el("detail");
  const note = state.notes.find((item) => item.id === state.selected);
  if (!note) {
    detail.innerHTML = `<p class="placeholder">没有选中条目。</p>`;
    return;
  }
  const tasks = note.tasks || [];
  const events = state.progress.filter((item) => item.note_id === note.id);
  detail.innerHTML = `
    <div class="detail-head">
      <div>
        <h2>${escapeHtml(note.title)}</h2>
        <p class="note-meta">${note.course ? `${escapeHtml(note.course)} · ` : ""}创建于 ${fmtTime(note.created_at)}　更新 ${fmtTime(note.updated_at)}</p>
      </div>
      <button class="ghost danger" id="retire">删除</button>
    </div>

    <div class="status-picker">
      ${Object.keys(STATUS_LABEL).map((key) => `
        <button class="status-choice ${key} ${note.status === key ? "on" : ""}" data-status="${key}">${STATUS_LABEL[key]}</button>`).join("")}
      <input id="memo" placeholder="进度备注（可选）">
    </div>

    <article class="body">${escapeHtml(note.body || "（无正文）").replace(/\n/g, "<br>")}</article>

    <div class="block">
      <h4>关联待办</h4>
      <ul class="task-list">
        ${tasks.length ? tasks.map((task) => `
          <li class="${task.done ? "done" : ""}">
            <input type="checkbox" data-task="${escapeHtml(task.id)}" ${task.done ? "checked" : ""}>
            <span>${escapeHtml(task.title)}</span>
            <button class="link" data-retire-task="${escapeHtml(task.id)}">删除</button>
          </li>`).join("") : `<li class="empty">还没有待办。</li>`}
      </ul>
      <form id="task-form"><input name="title" placeholder="新增一项待办，回车保存" required><button class="ghost" type="submit">添加</button></form>
    </div>

    <div class="block">
      <h4>进度时间线</h4>
      <ul class="timeline">
        ${events.length ? events.map((event) => `
          <li><b>${fmtTime(event.at)}</b> → ${escapeHtml(event.status_label || STATUS_LABEL[event.status] || event.status)}
          ${event.memo ? `　<i>${escapeHtml(event.memo)}</i>` : ""}</li>`).join("") : `<li class="empty">切换上方状态后会在此追加一条 PowerContext 进度记录。</li>`}
      </ul>
    </div>

    <div class="block provenance-inline">
      <h4>这条数据的来源</h4>
      <ul class="kv">
        <li><span>Scope</span><code>${escapeHtml(shortId(state.scopeId || ""))}</code></li>
        <li><span>Atomic Memory</span><code>${escapeHtml((note.atomic_memory_ids || []).map(shortId).join(", ") || "—")}</code></li>
        <li><span>kind</span><code>yanxi.note.v1</code></li>
        <li><span>修订 / 分块</span><code>r${note.revisions} / ${note.chunks}</code></li>
        <li><span>检索命中方式</span><code>${escapeHtml((note.matched_via || ["scope-list"]).join(", "))}</code></li>
      </ul>
    </div>`;

  detail.querySelectorAll(".status-choice").forEach((button) => {
    button.addEventListener("click", () => setStatus(note.id, button.dataset.status, el("memo").value));
  });
  el("retire").addEventListener("click", () => retireNote(note.id));
  detail.querySelectorAll("input[type=checkbox]").forEach((box) => {
    box.addEventListener("change", () => toggleTask(box.dataset.task, box.checked));
  });
  detail.querySelectorAll("[data-retire-task]").forEach((button) => {
    button.addEventListener("click", () => retireTask(button.dataset.retireTask));
  });
  el("task-form").addEventListener("submit", (event) => {
    event.preventDefault();
    const title = event.target.elements.title.value.trim();
    if (title) addTask(note.id, title).then(() => event.target.reset());
  });
}

// -------------------------------------------------------------------- writing

async function createNote(fields) {
  const data = await api("/api/notes", { method: "POST", body: JSON.stringify(fields) });
  toast(`已写入 ${data.chunks} 条 Atomic Memory 记录`, "ok");
  await refresh();
  if (state.notes.length) {
    state.selected = data.id;
    renderList();
    renderDetail();
  }
}

async function setStatus(noteId, status, memo) {
  await api(`/api/notes/${encodeURIComponent(noteId)}/status`, {
    method: "POST", body: JSON.stringify({ status, memo }),
  });
  toast(`进度已更新为「${STATUS_LABEL[status]}」`, "ok");
  await refresh();
}

async function retireNote(noteId) {
  await api(`/api/notes/${encodeURIComponent(noteId)}`, { method: "DELETE" });
  toast("已删除（PowerContext 中保留可追溯记录）");
  await refresh();
}

async function addTask(noteId, title) {
  await api("/api/tasks", { method: "POST", body: JSON.stringify({ note_id: noteId, title }) });
  await refresh();
}

async function toggleTask(taskId, done) {
  await api(`/api/tasks/${encodeURIComponent(taskId)}/done`, { method: "POST", body: JSON.stringify({ done }) });
  await refresh();
}

async function retireTask(taskId) {
  await api(`/api/tasks/${encodeURIComponent(taskId)}`, { method: "DELETE" });
  await refresh();
}

// ----------------------------------------------------------------- provenance

async function showProvenance() {
  el("provenance").hidden = false;
  el("provenance-body").innerHTML = "<p>正在向 PowerContext 查询…</p>";
  try {
    const data = await api("/api/state");
    const pc = await api("/api/pc");
    state.scopeId = pc.scope_id;
    const calls = (pc.recent_calls || []).map((call) => `
      <tr><td>${escapeHtml(call.method)}</td><td>${escapeHtml(call.path)}</td>
      <td>${escapeHtml(call.status ?? "—")}</td><td>${call.request_bytes}B → ${call.response_bytes}B</td>
      <td>${call.duration_ms}ms</td></tr>`).join("");
    el("provenance-body").innerHTML = `
      <ul class="kv">
        <li><span>接入方式</span><code>HTTP JSON · POST /v1/scopes · /v1/memory/remember · /v1/atomic-memory/list · /v1/atomic-memory/search</code></li>
        <li><span>服务地址</span><code>${escapeHtml(pc.base_url)}</code></li>
        <li><span>产品 / 版本</span><code>${escapeHtml(pc.product)} ${escapeHtml(pc.package_version)}</code></li>
        <li><span>Server ID</span><code>${escapeHtml(pc.server_id || "—")}</code></li>
        <li><span>API 契约</span><code>${escapeHtml(JSON.stringify(pc.api_contract_version))}</code></li>
        <li><span>已启用契约</span><code>${escapeHtml((pc.feature_contracts || []).join(", "))}</code></li>
        <li><span>工作区 Scope</span><code>${escapeHtml(pc.scope_id || "—")}</code></li>
        <li><span>Scope 幂等键</span><code>${escapeHtml(pc.scope_idempotency_key)}</code></li>
        <li><span>记忆 kind</span><code>${escapeHtml((pc.kinds || []).join(", "))}</code></li>
        <li><span>PowerContext 记录数</span><code>笔记 ${data.record_counts.note_records} / 待办 ${data.record_counts.task_records} / 进度 ${data.record_counts.progress_records}</code></li>
        <li><span>当前条目数</span><code>${data.record_counts.notes} 条笔记 · ${data.record_counts.tasks} 项待办</code></li>
        <li><span>解析异常</span><code>${data.parse_errors.length ? escapeHtml(JSON.stringify(data.parse_errors)) : "无"}</code></li>
      </ul>
      <h4>最近的服务端调用</h4>
      <table class="calls"><thead><tr><th>方法</th><th>路径</th><th>状态码</th><th>字节</th><th>耗时</th></tr></thead>
      <tbody>${calls || "<tr><td colspan=5>暂无</td></tr>"}</tbody></table>
      <h4>机制说明</h4>
      <ol class="explainer">
        <li>应用进程内不保存任何业务数据，也没有本地数据库文件；每次界面刷新都会重新调用 <code>/v1/atomic-memory/list</code>。</li>
        <li>新增与修改都是 <b>追加</b> 一条新的 Atomic Memory（<code>seq</code> 递增），读取时按 <code>entity_id</code> 折叠出当前状态，因此历史修订天然可审计。</li>
        <li>正文超过 PowerContext 单条 8192 UTF-8 字节上限时自动分块为多条记录，读取时按 <code>chunk_index</code> 无损拼回。</li>
        <li>标签由 PowerContext 保存并支持服务端过滤（<code>tag_match=all|any</code>）；关键词检索走服务端 <code>mode=text</code>，界面会标注每条结果的命中方式。</li>
        <li>官方契约禁止就地改写记忆条目，删除实现为追加一条 <code>op=retire</code> 记录，旧记录仍可在 PowerContext 中查到。</li>
        <li>服务未配置任何生成模型：显式读写与文本检索均为确定性能力，不消耗任何模型额度。</li>
      </ol>`;
    renderDetail();
  } catch (error) {
    el("provenance-body").innerHTML = `<p class="error">无法读取 PowerContext：${escapeHtml(error.message)}<br>
    请确认服务已启动：运行 <code>bash scripts/start_pc.sh</code>，再用 <code>bash scripts/start_pc.sh status</code> 检查。</p>`;
  }
}

// ---------------------------------------------------------------------- wiring

el("note-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.target;
  const fields = {
    title: form.elements.title.value.trim(),
    course: form.elements.course.value.trim(),
    tags: form.elements.tags.value,
    keywords: form.elements.keywords.value,
    body: form.elements.body.value,
  };
  if (!fields.title) return toast("请填写标题", "error");
  try {
    await createNote(fields);
    form.reset();
    el("form-hint").textContent = "";
  } catch (error) {
    toast(error.message, "error");
  }
});

el("reload").addEventListener("click", async () => {
  try {
    const data = await refresh();
    toast(`已重新读取：${data.record_counts.note_records} 条笔记记录在 PowerContext 中`, "ok");
  } catch (error) {
    toast(error.message, "error");
  }
});

el("search").addEventListener("click", () => runSearch().catch((error) => toast(error.message, "error")));
["q", "tagf", "statusf"].forEach((id) => el(id).addEventListener("keydown", (event) => {
  if (event.key === "Enter") runSearch().catch((error) => toast(error.message, "error"));
}));
el("clear-filters").addEventListener("click", () => {
  el("q").value = "";
  el("tagf").value = "";
  el("statusf").value = "";
  el("retrieval-note").textContent = "";
  refresh().catch((error) => toast(error.message, "error"));
});
el("toggle-provenance").addEventListener("click", showProvenance);
el("close-provenance").addEventListener("click", () => { el("provenance").hidden = true; });

refresh()
  .then(() => api("/api/pc"))
  .then((pc) => { state.scopeId = pc.scope_id; renderDetail(); })
  .catch((error) => toast(error.message, "error"));
