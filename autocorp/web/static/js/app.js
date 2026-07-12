/* AutoCorp Web UI */
const state = {
  page: "dashboard",
  modelsCatalog: null,
  config: null,
  companies: [],
  selectedSlug: null,
  selectedModels: {
    brain: "claude-sonnet-4-5",
    operator: "gpt-4o",
    marketer: "gpt-4o",
    accountant: "gpt-4o",
  },
  usageProfile: "medium",
  launchJobId: null,
};

const $ = (sel, el = document) => el.querySelector(sel);
const $$ = (sel, el = document) => [...el.querySelectorAll(sel)];

function money(n) {
  return `$${Number(n || 0).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

function toast(msg, ok = true) {
  const el = $("#toast");
  el.textContent = msg;
  el.className = `toast show ${ok ? "ok" : "err"}`;
  setTimeout(() => el.classList.remove("show"), 3200);
}

async function api(path, opts = {}) {
  const res = await fetch(`/api${path}`, {
    headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
    ...opts,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || data.error || res.statusText);
  return data;
}

/* Navigation */
function showPage(page) {
  state.page = page;
  $$(".page").forEach((p) => p.classList.remove("active"));
  $(`#page-${page}`)?.classList.add("active");
  $$(".nav-btn").forEach((b) => b.classList.toggle("active", b.dataset.page === page));
  if (page === "dashboard") loadDashboard();
  if (page === "setup") loadSetup();
  if (page === "approvals") loadApprovals();
  if (page === "company" && state.selectedSlug) loadCompany(state.selectedSlug);
}

/* Setup & costs */
function currentModels() {
  return { ...state.selectedModels };
}

async function refreshCosts() {
  const models = currentModels();
  const data = await api("/costs/estimate", {
    method: "POST",
    body: JSON.stringify({ models }),
  });
  const profiles = data.profiles || {};
  const tbody = $("#cost-body");
  tbody.innerHTML = "";
  for (const key of ["light", "medium", "heavy"]) {
    const p = profiles[key];
    if (!p) continue;
    const b = p.breakdown || {};
    const tr = document.createElement("tr");
    if (key === state.usageProfile) tr.classList.add("active");
    tr.innerHTML = `
      <td>${p.profile_label || key}</td>
      <td class="num">${p.companies_per_month}</td>
      <td class="num">${money(b.brain)}</td>
      <td class="num">${money(b.operator)}</td>
      <td class="num">${money(b.marketer)}</td>
      <td class="num">${money(b.accountant)}</td>
      <td class="num">${money(p.total_usd)}</td>
    `;
    tbody.appendChild(tr);
  }
  const active = profiles[state.usageProfile];
  if (active) $("#stat-llm").textContent = money(active.total_usd);
}

function renderAgentModels() {
  const roles = [
    ["brain", "Brain", "Product ownership, code, deploy"],
    ["operator", "Operator", "Domains, email, infrastructure"],
    ["marketer", "Marketer", "Social, branding, growth"],
    ["accountant", "Accountant", "Budget, Stripe, P&L"],
  ];
  const wrap = $("#agent-models");
  wrap.innerHTML = "";
  for (const [role, label, desc] of roles) {
    const options = state.modelsCatalog?.by_role?.[role] || [];
    const selected = state.selectedModels[role];
    const selectedMeta = options.find((o) => o.id === selected) || options[0];
    const ready = selectedMeta?.ready;
    const card = document.createElement("div");
    card.className = "agent-card";
    card.innerHTML = `
      <header>
        <span class="agent-badge ${role}"><span class="orb"></span>${label}</span>
        <span class="key-pill ${ready ? "ok" : "bad"}">${ready ? "key ready" : selectedMeta?.key_name || "missing key"}</span>
      </header>
      <div class="muted" style="font-size:0.78rem;margin-bottom:0.5rem">${desc}</div>
      <div class="field">
        <select data-role="${role}">
          ${options
            .map(
              (o) =>
                `<option value="${o.id}" ${o.id === selected ? "selected" : ""}>
                  ${o.label} · ${o.provider} · $${o.input_per_m}/$${o.output_per_m} per 1M
                </option>`
            )
            .join("")}
        </select>
      </div>
    `;
    wrap.appendChild(card);
  }
  wrap.querySelectorAll("select").forEach((sel) => {
    sel.addEventListener("change", async () => {
      state.selectedModels[sel.dataset.role] = sel.value;
      renderAgentModels();
      try {
        await refreshCosts();
      } catch (e) {
        toast(e.message, false);
      }
    });
  });
}

async function loadSetup() {
  const [models, config] = await Promise.all([api("/models"), api("/config")]);
  state.modelsCatalog = models;
  state.config = config;
  state.selectedModels = { ...config.models };
  state.usageProfile = config.usage_profile || "medium";
  $("#cfg-profile").value = state.usageProfile;
  $("#cfg-alert").value = config.budget_alert_usd ?? 50;
  $("#cfg-budget").value = config.default_company_budget_usd ?? 500;
  $("#cfg-approval").checked = !!config.require_human_approval;
  renderAgentModels();
  await refreshCosts();
}

async function saveConfig() {
  const body = {
    models: currentModels(),
    budget_alert_usd: Number($("#cfg-alert").value || 50),
    default_company_budget_usd: Number($("#cfg-budget").value || 500),
    require_human_approval: $("#cfg-approval").checked,
    usage_profile: $("#cfg-profile").value,
  };
  await api("/config", { method: "POST", body: JSON.stringify(body) });
  toast("Configuration saved");
  const meta = await api("/meta");
  $("#meta-setup").textContent = meta.setup_completed ? "Setup complete" : "Setup incomplete";
}

/* Dashboard */
async function loadDashboard() {
  const [companiesData, approvals, config] = await Promise.all([
    api("/companies"),
    api("/approvals"),
    api("/config"),
  ]);

  const companies = companiesData.companies || [];
  state.companies = companies;
  $("#stat-companies").textContent = companies.length;
  $("#stat-approvals").textContent = (approvals.approvals || []).length;
  const spent = companies.reduce((s, c) => s + (c.spent_usd || 0), 0);
  $("#stat-spent").textContent = money(spent);

  try {
    const est = await api("/costs/estimate", {
      method: "POST",
      body: JSON.stringify({ models: config.models || state.selectedModels }),
    });
    const p = est.profiles?.[config.usage_profile || "medium"];
    if (p) $("#stat-llm").textContent = money(p.total_usd);
  } catch (_) {
    $("#stat-llm").textContent = "—";
  }

  const list = $("#company-list");
  if (!companies.length) {
    list.innerHTML = `<div class="empty">No companies yet. <a href="#" data-goto="launch">Launch FocusFlow</a> to test.</div>`;
    list.querySelector("[data-goto]")?.addEventListener("click", (e) => {
      e.preventDefault();
      showPage("launch");
    });
    return;
  }
  list.innerHTML = companies
    .map(
      (c) => `
    <button class="company-item" data-slug="${c.slug}">
      <div>
        <h4>${escapeHtml(c.name)} <span class="badge ${c.status}">${c.status}</span></h4>
        <p>${escapeHtml(c.description || "")}</p>
        <p class="mono" style="margin-top:0.35rem">${money(c.spent_usd)} / ${money(c.budget_usd)} · ${c.domain || "no domain"}</p>
      </div>
      <div class="muted">Open →</div>
    </button>`
    )
    .join("");
  list.querySelectorAll(".company-item").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.selectedSlug = btn.dataset.slug;
      showPage("company");
      loadCompany(btn.dataset.slug);
    });
  });
}

/* Launch */
async function launchCompany(e) {
  e.preventDefault();
  const btn = $("#launch-btn");
  const status = $("#launch-status");
  btn.disabled = true;
  btn.innerHTML = `<span class="spinner"></span> Launching…`;
  status.classList.remove("hidden");
  status.textContent = "Agents spinning up — this takes ~10–30s in mock mode…";

  try {
    const payload = {
      name: $("#launch-name").value.trim(),
      description: $("#launch-desc").value.trim(),
      budget_usd: Number($("#launch-budget").value || 450),
      stack: $("#launch-stack").value.trim(),
      tone: $("#launch-tone").value.trim(),
      cycles: Number($("#launch-cycles").value || 3),
      auto_approve: $("#launch-auto").checked,
    };
    const job = await api("/companies/launch", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    state.launchJobId = job.job_id;
    pollJob(job.job_id, payload.name);
  } catch (err) {
    toast(err.message, false);
    btn.disabled = false;
    btn.textContent = "Launch company";
    status.textContent = "";
  }
}

async function pollJob(jobId, name) {
  const status = $("#launch-status");
  const btn = $("#launch-btn");
  try {
    const job = await api(`/jobs/${jobId}`);
    if (job.status === "running") {
      status.textContent = `Running autonomous cycles for ${name}…`;
      setTimeout(() => pollJob(jobId, name), 1500);
      return;
    }
    if (job.status === "error") {
      toast(job.error || "Launch failed", false);
      status.textContent = job.error;
      btn.disabled = false;
      btn.textContent = "Launch company";
      return;
    }
    toast(`${name} launched`);
    status.textContent = `Done · domain ${job.result?.domain || "—"} · ${job.result?.vercel_url || ""}`;
    btn.disabled = false;
    btn.textContent = "Launch company";
    state.selectedSlug = job.result?.slug;
    await loadDashboard();
    if (job.result?.slug) {
      showPage("company");
      loadCompany(job.result.slug);
    }
  } catch (err) {
    toast(err.message, false);
    btn.disabled = false;
    btn.textContent = "Launch company";
  }
}

/* Company detail */
async function loadCompany(slug) {
  $("#company-empty").classList.add("hidden");
  $("#company-body").classList.remove("hidden");
  const data = await api(`/companies/${encodeURIComponent(slug)}`);
  const p = data.project;
  const b = data.budget;
  state.selectedSlug = p.slug;

  $("#co-name").textContent = p.name;
  $("#co-desc").textContent = p.description;
  $("#co-status").textContent = p.status;
  $("#co-remaining").textContent = money(b.remaining_usd);
  $("#co-domain").textContent = p.domain || "—";
  $("#co-vercel").innerHTML = p.vercel_url
    ? `<a href="${p.vercel_url}" target="_blank" rel="noopener">${p.vercel_url.replace("https://", "")}</a>`
    : "—";
  $("#co-budget-text").textContent = `${money(b.spent_usd)} spent of ${money(b.budget_usd)} · pending ${money(b.pending_usd)}`;
  const pct = b.budget_usd ? Math.min(100, (b.spent_usd / b.budget_usd) * 100) : 0;
  $("#co-budget-bar").style.width = `${pct}%`;

  const agents = $("#co-agents");
  agents.innerHTML = (data.agents || [])
    .map((a) => {
      const role = (a.agent || "").toLowerCase();
      return `
      <div class="agent-status-card">
        <span class="agent-badge ${role}"><span class="orb"></span>${role}</span>
        <div class="task">${escapeHtml(a.current_task || a.status || "")}</div>
        <div class="loops">loops: ${a.loop_count || 0} · ${a.status}</div>
      </div>`;
    })
    .join("");

  const feed = $("#co-messages");
  const msgs = data.messages || [];
  feed.innerHTML = msgs.length
    ? msgs
        .slice()
        .reverse()
        .map((m) => {
          const from = String(m.from_agent || "system").toLowerCase();
          return `
        <div class="msg">
          <div class="meta">
            <span class="from ${from}">${from}</span>
            <span>→ ${m.to_agent}</span>
          </div>
          <div class="subject">${escapeHtml(m.subject || "")}</div>
          <div class="body">${escapeHtml((m.body || "").slice(0, 220))}</div>
        </div>`;
        })
        .join("")
    : `<div class="empty">No messages yet.</div>`;

  const costs = $("#co-costs");
  costs.innerHTML = (data.costs || []).length
    ? `<table class="cost-table"><thead><tr><th>Item</th><th class="num">Amount</th><th>Status</th></tr></thead><tbody>
      ${data.costs
        .map(
          (c) =>
            `<tr><td>${escapeHtml(c.description || c.category)}</td><td class="num">${money(c.amount_usd)}</td><td>${c.approved ? "✓" : "…"}</td></tr>`
        )
        .join("")}
      </tbody></table>`
    : `<div class="muted">No costs yet.</div>`;

  const emails = (data.emails || []).map((e) => e.address).join(", ");
  const socials = (data.socials || []).map((s) => `${s.platform}:${s.handle}`).join(" · ");
  $("#co-assets").innerHTML = `
    <div><strong>Emails:</strong> ${emails || "—"}</div>
    <div class="mt-1"><strong>Socials:</strong> ${socials || "—"}</div>
    <div class="link-row">
      ${p.github_repo ? `<span class="mono">GitHub: ${escapeHtml(p.github_repo)}</span>` : ""}
    </div>`;
}

async function runMoreCycles() {
  if (!state.selectedSlug) return;
  const btn = $("#co-run");
  btn.disabled = true;
  btn.innerHTML = `<span class="spinner"></span> Running…`;
  try {
    await api(`/companies/${encodeURIComponent(state.selectedSlug)}/run`, {
      method: "POST",
      body: JSON.stringify({ cycles: 2, auto_approve: true }),
    });
    toast("Cycles complete");
    await loadCompany(state.selectedSlug);
  } catch (e) {
    toast(e.message, false);
  } finally {
    btn.disabled = false;
    btn.textContent = "Run +2 cycles";
  }
}

/* Approvals */
async function loadApprovals() {
  const data = await api("/approvals");
  const list = $("#approvals-list");
  const items = data.approvals || [];
  if (!items.length) {
    list.innerHTML = `<div class="empty">No pending approvals. Agents only pause for money & irreversible actions.</div>`;
    return;
  }
  list.innerHTML = items
    .map((a, i) => {
      const options = a.options || [];
      const optsHtml = options.length
        ? `<div class="option-list">${options
            .map(
              (o, idx) => `
            <label>
              <input type="radio" name="opt-${a.id}" value="${idx}" ${idx === 0 ? "checked" : ""} />
              <span>${escapeHtml(o.label || o.domain || JSON.stringify(o))}</span>
            </label>`
            )
            .join("")}</div>`
        : "";
      return `
      <div class="approval-card" data-id="${a.id}">
        <h4>${escapeHtml(a.action)} · ${money(a.amount_usd)}</h4>
        <p>${escapeHtml(a.description || "")}</p>
        <p class="mono muted mt-1">${a.id} · by ${a.requested_by}</p>
        ${optsHtml}
        <div class="btn-row">
          <button class="btn btn-success btn-sm" data-approve="${a.id}">Approve</button>
          <button class="btn btn-danger btn-sm" data-reject="${a.id}">Reject</button>
        </div>
      </div>`;
    })
    .join("");

  list.querySelectorAll("[data-approve]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const id = btn.dataset.approve;
      const card = btn.closest(".approval-card");
      const selected = card.querySelector(`input[name="opt-${id}"]:checked`);
      try {
        await api("/approvals/decide", {
          method: "POST",
          body: JSON.stringify({
            approval_id: id,
            approve: true,
            option_index: selected ? Number(selected.value) : 0,
          }),
        });
        toast("Approved");
        loadApprovals();
      } catch (e) {
        toast(e.message, false);
      }
    });
  });
  list.querySelectorAll("[data-reject]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      try {
        await api("/approvals/decide", {
          method: "POST",
          body: JSON.stringify({ approval_id: btn.dataset.reject, approve: false }),
        });
        toast("Rejected");
        loadApprovals();
      } catch (e) {
        toast(e.message, false);
      }
    });
  });
}

function escapeHtml(s) {
  return String(s)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

/* Boot */
async function init() {
  $$(".nav-btn").forEach((btn) =>
    btn.addEventListener("click", () => showPage(btn.dataset.page))
  );
  document.body.addEventListener("click", (e) => {
    const t = e.target.closest("[data-goto]");
    if (t) {
      e.preventDefault();
      showPage(t.dataset.goto);
    }
  });

  $("#launch-form").addEventListener("submit", launchCompany);
  $("#save-config-btn").addEventListener("click", () =>
    saveConfig().catch((e) => toast(e.message, false))
  );
  $("#cfg-profile").addEventListener("change", async () => {
    state.usageProfile = $("#cfg-profile").value;
    await refreshCosts();
  });
  $("#refresh-approvals").addEventListener("click", () => loadApprovals());
  $("#co-refresh").addEventListener("click", () => {
    if (state.selectedSlug) loadCompany(state.selectedSlug);
  });
  $("#co-run").addEventListener("click", runMoreCycles);

  try {
    const meta = await api("/meta");
    $("#meta-version").textContent = `AutoCorp v${meta.version}`;
    $("#meta-setup").textContent = meta.setup_completed ? "Setup complete" : "Run Setup & models";
    await loadDashboard();
  } catch (e) {
    toast(`API error: ${e.message}`, false);
  }
}

init();
