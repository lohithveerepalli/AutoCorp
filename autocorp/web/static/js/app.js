/* AutoCorp Web UI — CEO control plane */
const PAGE_META = {
  dashboard: ["Dashboard", "Command center for your autonomous company fleet"],
  launch: ["Launch Company", "One brief. Four agents. End-to-end execution."],
  companies: ["Companies", "All companies launched in this workspace"],
  company: ["Company", "Live status, agents, messages, and P&L"],
  approvals: ["Approvals", "Money and irreversible actions requiring a human"],
  settings: ["Settings / Models", "Models, cost calculator, budget alerts"],
  usage: ["Usage & Costs", "Projected LLM spend and workspace costs"],
  docs: ["Docs / Help", "How to run AutoCorp as a real CEO dashboard"],
};

const state = {
  page: "dashboard",
  modelsCatalog: null,
  config: null,
  companies: [],
  selectedSlug: null,
  companyData: null,
  selectedModels: {
    brain: "claude-sonnet-4-5",
    operator: "gpt-4o",
    marketer: "gpt-4o",
    accountant: "gpt-4o",
  },
  usageProfile: "medium",
  launchJobId: null,
  confirmAction: null,
};

const $ = (sel, el = document) => el.querySelector(sel);
const $$ = (sel, el = document) => [...el.querySelectorAll(sel)];

function money(n) {
  return `$${Number(n || 0).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

function escapeHtml(s) {
  return String(s ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function toast(msg, type = "ok") {
  const host = $("#toast-host");
  const el = document.createElement("div");
  el.className = `toast ${type}`;
  el.textContent = msg;
  host.appendChild(el);
  setTimeout(() => {
    el.style.opacity = "0";
    el.style.transition = "opacity 200ms";
    setTimeout(() => el.remove(), 220);
  }, 3200);
}

function setLoading(show, text = "Loading…") {
  const overlay = $("#loading-overlay");
  $("#loading-text").textContent = text;
  overlay.classList.toggle("show", !!show);
}

async function api(path, opts = {}) {
  const res = await fetch(`/api${path}`, {
    headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
    ...opts,
  });
  let data = {};
  try {
    data = await res.json();
  } catch (_) {}
  if (!res.ok) {
    const detail = data.detail;
    const msg =
      typeof detail === "string"
        ? detail
        : Array.isArray(detail)
          ? detail.map((d) => d.msg || JSON.stringify(d)).join(", ")
          : data.error || res.statusText;
    throw new Error(msg || "Request failed");
  }
  return data;
}

/* Theme + sidebar */
function applyTheme(theme) {
  document.documentElement.setAttribute("data-theme", theme);
  localStorage.setItem("autocorp-theme", theme);
}

function toggleTheme() {
  const cur = document.documentElement.getAttribute("data-theme") || "dark";
  applyTheme(cur === "dark" ? "light" : "dark");
}

function toggleSidebar() {
  const shell = $("#shell");
  shell.classList.toggle("sidebar-collapsed");
  localStorage.setItem(
    "autocorp-sidebar-collapsed",
    shell.classList.contains("sidebar-collapsed") ? "1" : "0"
  );
}

/* Navigation */
function showPage(page) {
  state.page = page;
  $$(".page").forEach((p) => p.classList.remove("active"));
  $(`#page-${page}`)?.classList.add("active");
  $$(".nav-item").forEach((b) =>
    b.classList.toggle("active", b.dataset.page === page)
  );
  const meta = PAGE_META[page] || ["AutoCorp", ""];
  $("#topbar-title").textContent = meta[0];
  $("#topbar-subtitle").textContent = meta[1];

  const loaders = {
    dashboard: loadDashboard,
    launch: loadLaunch,
    companies: loadCompanies,
    company: () =>
      state.selectedSlug
        ? loadCompany(state.selectedSlug)
        : Promise.resolve(),
    approvals: loadApprovals,
    settings: loadSetup,
    usage: loadUsage,
    docs: async () => {},
  };
  (loaders[page] || (async () => {}))().catch((e) => toast(e.message, "err"));
}

/* Models / costs */
function currentModels() {
  return { ...state.selectedModels };
}

async function refreshCosts() {
  const data = await api("/costs/estimate", {
    method: "POST",
    body: JSON.stringify({ models: currentModels() }),
  });
  const profiles = data.profiles || {};
  const tbody = $("#cost-body");
  if (tbody) {
    tbody.innerHTML = "";
    for (const key of ["light", "medium", "heavy"]) {
      const p = profiles[key];
      if (!p) continue;
      const b = p.breakdown || {};
      const tr = document.createElement("tr");
      if (key === state.usageProfile) tr.classList.add("active");
      tr.innerHTML = `
        <td>${escapeHtml(p.profile_label || key)}</td>
        <td class="num">${p.companies_per_month}</td>
        <td class="num">${money(b.brain)}</td>
        <td class="num">${money(b.operator)}</td>
        <td class="num">${money(b.marketer)}</td>
        <td class="num">${money(b.accountant)}</td>
        <td class="num">${money(p.total_usd)}</td>`;
      tbody.appendChild(tr);
    }
  }
  return profiles;
}

function renderAgentModels() {
  const roles = [
    ["brain", "Brain", "Product ownership, code, deploy"],
    ["operator", "Operator", "Domains, email, infrastructure"],
    ["marketer", "Marketer", "Social, branding, growth"],
    ["accountant", "Accountant", "Budget, Stripe, P&L"],
  ];
  const wrap = $("#agent-models");
  if (!wrap) return;
  wrap.innerHTML = "";
  for (const [role, label, desc] of roles) {
    const options = state.modelsCatalog?.by_role?.[role] || [];
    const selected = state.selectedModels[role];
    const selectedMeta = options.find((o) => o.id === selected) || options[0];
    const ready = !!selectedMeta?.ready;
    const card = document.createElement("div");
    card.className = "model-card";
    card.innerHTML = `
      <header>
        <span class="agent-badge ${role}"><span class="orb"></span>${label}</span>
        <span class="key-pill ${ready ? "ok" : "bad"}">${
          ready ? "API ready" : selectedMeta?.key_name || "missing key"
        }</span>
      </header>
      <div class="muted" style="font-size:0.78rem;margin-bottom:0.5rem">${desc}</div>
      <div class="field">
        <select data-role="${role}">
          ${options
            .map(
              (o) =>
                `<option value="${escapeHtml(o.id)}" ${
                  o.id === selected ? "selected" : ""
                }>${escapeHtml(o.label)} · ${escapeHtml(
                  o.provider
                )} · $${o.input_per_m}/$${o.output_per_m} per 1M</option>`
            )
            .join("")}
        </select>
      </div>`;
    wrap.appendChild(card);
  }
  wrap.querySelectorAll("select").forEach((sel) => {
    sel.addEventListener("change", async () => {
      state.selectedModels[sel.dataset.role] = sel.value;
      renderAgentModels();
      try {
        await refreshCosts();
        updateLaunchCostBox(await refreshCosts());
      } catch (e) {
        toast(e.message, "err");
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
  state.usageProfile = body.usage_profile;
  toast("Configuration saved");
  const meta = await api("/meta");
  $("#meta-setup").textContent = meta.setup_completed
    ? "Setup complete"
    : "Setup needed";
}

/* Dashboard */
function renderCompanyList(target, companies, emptyTitle) {
  const list = $(target);
  if (!companies.length) {
    list.innerHTML = `<div class="empty"><h4>${emptyTitle}</h4><p>Launch FocusFlow to see the full multi-agent loop.</p><button class="btn btn-primary" data-goto="launch">Launch company</button></div>`;
    return;
  }
  list.innerHTML = companies
    .map(
      (c) => `
    <button class="list-item" data-slug="${escapeHtml(c.slug)}">
      <div>
        <h4>${escapeHtml(c.name)} <span class="status-pill ${escapeHtml(
        c.status
      )}">${escapeHtml(c.status)}</span></h4>
        <p>${escapeHtml(c.description || "")}</p>
        <p class="mono" style="margin-top:0.35rem">${money(c.spent_usd)} / ${money(
        c.budget_usd
      )} · ${escapeHtml(c.domain || "no domain")}</p>
      </div>
      <div class="muted">Open →</div>
    </button>`
    )
    .join("");
  list.querySelectorAll("[data-slug]").forEach((btn) => {
    btn.addEventListener("click", () => openCompany(btn.dataset.slug));
  });
}

function renderMessages(target, messages, emptyText = "No messages yet.") {
  const feed = $(target);
  if (!messages?.length) {
    feed.innerHTML = `<div class="empty"><h4>${emptyText}</h4></div>`;
    return;
  }
  feed.innerHTML = messages
    .slice()
    .reverse()
    .map((m) => {
      const from = String(m.from_agent || "system").toLowerCase();
      return `
      <div class="msg">
        <div class="meta">
          <span class="agent-badge ${from}"><span class="orb"></span>${from}</span>
          <span>→ ${escapeHtml(String(m.to_agent))}</span>
        </div>
        <div class="subject">${escapeHtml(m.subject || "")}</div>
        <div class="body">${escapeHtml((m.body || "").slice(0, 260))}</div>
      </div>`;
    })
    .join("");
}

function renderAgentCards(target, agents) {
  const el = $(target);
  const order = ["brain", "operator", "marketer", "accountant"];
  const byRole = {};
  (agents || []).forEach((a) => {
    byRole[String(a.agent || "").toLowerCase()] = a;
  });
  el.innerHTML = order
    .map((role) => {
      const a = byRole[role] || {
        status: "idle",
        current_task: "No recent activity",
        loop_count: 0,
      };
      const status = String(a.status || "idle").toLowerCase();
      const task = a.current_task || status;
      const hb = a.last_heartbeat
        ? new Date(a.last_heartbeat).toLocaleString()
        : "—";
      return `
      <div class="agent-card ${role}">
        <div style="display:flex;justify-content:space-between;gap:0.5rem;align-items:center">
          <span class="agent-badge ${role}"><span class="orb"></span>${role}</span>
          <span class="status-pill ${status}">${status}</span>
        </div>
        <div class="status-line">${escapeHtml(task)}</div>
        <div class="meta-line"><span>loops ${a.loop_count || 0}</span><span>${escapeHtml(
          hb
        )}</span></div>
      </div>`;
    })
    .join("");
}

async function loadDashboard() {
  const [companiesData, approvals, config] = await Promise.all([
    api("/companies"),
    api("/approvals"),
    api("/config"),
  ]);
  const companies = companiesData.companies || [];
  state.companies = companies;
  state.config = config;

  $("#kpi-companies").textContent = companies.length;
  $("#kpi-approvals").textContent = (approvals.approvals || []).length;
  const spent = companies.reduce((s, c) => s + (c.spent_usd || 0), 0);
  $("#kpi-spend").textContent = money(spent);
  updateApprovalBadge((approvals.approvals || []).length);

  try {
    const est = await api("/costs/estimate", {
      method: "POST",
      body: JSON.stringify({ models: config.models || state.selectedModels }),
    });
    const p = est.profiles?.[config.usage_profile || "medium"];
    if (p) {
      $("#kpi-llm").textContent = money(p.total_usd);
      $("#kpi-llm-meta").textContent = p.profile_label || "Usage profile";
    }
  } catch (_) {
    $("#kpi-llm").textContent = "—";
  }

  renderCompanyList("#dash-companies", companies.slice(0, 5), "No companies yet");

  // Latest activity + agent overview from most recent company
  if (companies[0]) {
    try {
      const detail = await api(
        `/companies/${encodeURIComponent(companies[0].slug)}`
      );
      renderAgentCards("#dash-agents", detail.agents);
      renderMessages("#dash-activity", detail.messages?.slice(-12), "No activity yet");
    } catch (_) {
      /* keep placeholders */
    }
  } else {
    $("#dash-agents").innerHTML = ["brain", "operator", "marketer", "accountant"]
      .map(
        (r) =>
          `<div class="agent-card ${r}"><span class="agent-badge ${r}"><span class="orb"></span>${r}</span><div class="status-line muted">Waiting for first launch</div></div>`
      )
      .join("");
    $("#dash-activity").innerHTML =
      `<div class="empty"><h4>No activity yet</h4><p>Launch a company to see agents coordinate.</p></div>`;
  }
}

function updateApprovalBadge(n) {
  const badge = $("#nav-approval-badge");
  if (n > 0) {
    badge.textContent = String(n);
    badge.classList.remove("hidden");
  } else {
    badge.classList.add("hidden");
  }
}

/* Companies */
async function loadCompanies() {
  const data = await api("/companies");
  state.companies = data.companies || [];
  renderCompanyList("#companies-list", state.companies, "No companies yet");
}

function openCompany(slug) {
  state.selectedSlug = slug;
  showPage("company");
}

/* Company detail */
async function loadCompany(slug) {
  $("#company-empty").classList.add("hidden");
  $("#company-body").classList.remove("hidden");
  const data = await api(`/companies/${encodeURIComponent(slug)}`);
  state.companyData = data;
  const p = data.project;
  const b = data.budget;
  state.selectedSlug = p.slug;

  $("#topbar-title").textContent = p.name;
  $("#topbar-subtitle").textContent = p.description || "Company detail";

  $("#co-name").textContent = p.name;
  $("#co-desc").textContent = p.description || "";
  $("#co-slug").textContent = p.slug;
  const pill = $("#co-status-pill");
  pill.textContent = p.status;
  pill.className = `status-pill ${p.status}`;
  $("#co-remaining").textContent = money(b.remaining_usd);
  $("#co-spent").textContent = money(b.spent_usd);
  $("#co-domain").textContent = p.domain || "—";
  $("#co-vercel").innerHTML = p.vercel_url
    ? `<a href="${escapeHtml(p.vercel_url)}" target="_blank" rel="noopener">${escapeHtml(
        p.vercel_url.replace("https://", "")
      )}</a>`
    : "—";
  $("#co-budget-text").textContent = `${money(b.spent_usd)} spent of ${money(
    b.budget_usd
  )} · pending ${money(b.pending_usd)}`;
  const pct = b.budget_usd ? Math.min(100, (b.spent_usd / b.budget_usd) * 100) : 0;
  $("#co-budget-bar").style.width = `${pct}%`;

  renderAgentCards("#co-agents", data.agents);
  renderAgentCards("#co-overview-agents", data.agents);
  renderMessages("#co-messages", data.messages);
  renderMessages("#co-overview-messages", (data.messages || []).slice(-8));

  // P&L
  $("#pnl-budget").textContent = money(b.budget_usd);
  $("#pnl-spent").textContent = money(b.spent_usd);
  $("#pnl-pending").textContent = money(b.pending_usd);
  const cats = b.by_category || {};
  const maxCat = Math.max(1, ...Object.values(cats), b.spent_usd || 1);
  $("#pnl-bars").innerHTML = Object.keys(cats).length
    ? Object.entries(cats)
        .map(
          ([k, v]) => `
      <div class="cost-bar-row">
        <div>${escapeHtml(k)}</div>
        <div class="cost-bar-track"><div class="cost-bar-fill" style="width:${
          (v / maxCat) * 100
        }%"></div></div>
        <div class="mono" style="text-align:right">${money(v)}</div>
      </div>`
        )
        .join("")
    : `<div class="muted">No categorized spend yet.</div>`;

  const costs = data.costs || [];
  $("#co-costs").innerHTML = costs.length
    ? `<table class="table"><thead><tr><th>Item</th><th>Category</th><th class="num">Amount</th><th>Status</th></tr></thead><tbody>
      ${costs
        .map(
          (c) =>
            `<tr><td>${escapeHtml(c.description || "")}</td><td>${escapeHtml(
              c.category
            )}</td><td class="num">${money(c.amount_usd)}</td><td>${
              c.approved ? "✓ approved" : "… pending"
            }</td></tr>`
        )
        .join("")}
      </tbody></table>`
    : `<div class="empty"><h4>No line items</h4><p>Costs appear when agents propose spend.</p></div>`;

  // Domains / assets
  const domains = data.domains || [];
  $("#co-domains").innerHTML = domains.length
    ? `<table class="table"><thead><tr><th>Domain</th><th>Registrar</th><th class="num">Price</th><th>Status</th></tr></thead><tbody>
      ${domains
        .slice(0, 12)
        .map(
          (d) =>
            `<tr><td class="mono">${escapeHtml(d.domain)}</td><td>${escapeHtml(
              d.registrar
            )}</td><td class="num">${
              d.available ? money(d.price_usd) : "—"
            }</td><td>${d.available ? "available" : "taken"}</td></tr>`
        )
        .join("")}
      </tbody></table>`
    : `<div class="muted">No domain research stored yet.</div>`;

  const emails = (data.emails || []).map((e) => e.address);
  const socials = (data.socials || []).map((s) => `${s.platform}: ${s.handle} [${s.status}]`);
  $("#co-assets").innerHTML = `
    <div class="mb-1"><strong>Emails</strong><div class="muted" style="margin-top:0.35rem">${
      emails.length ? emails.map(escapeHtml).join("<br>") : "—"
    }</div></div>
    <div><strong>Socials</strong><div class="muted" style="margin-top:0.35rem">${
      socials.length ? socials.map(escapeHtml).join("<br>") : "—"
    }</div></div>
    <div class="mt-1 mono muted">GitHub: ${escapeHtml(p.github_repo || "—")}</div>`;

  // company approvals
  renderApprovalCards("#co-approvals-list", data.pending_approvals || [], true);

  $("#co-github").textContent = p.github_repo || "—";
  $("#co-stack").textContent = p.stack || "—";
  $("#co-tone").textContent = p.tone || "—";
  $("#co-id").textContent = p.id || "—";
}

function switchCompanyTab(tab) {
  $$("#co-tabs .tab").forEach((t) =>
    t.classList.toggle("active", t.dataset.tab === tab)
  );
  $$("#page-company .tab-panel").forEach((p) =>
    p.classList.toggle("active", p.id === `tab-${tab}`)
  );
}

async function runMoreCycles() {
  if (!state.selectedSlug) return;
  const btn = $("#co-run");
  btn.disabled = true;
  btn.innerHTML = `<span class="spinner sm"></span> Running…`;
  try {
    await api(`/companies/${encodeURIComponent(state.selectedSlug)}/run`, {
      method: "POST",
      body: JSON.stringify({ cycles: 2, auto_approve: true }),
    });
    toast("Autonomous cycles complete");
    await loadCompany(state.selectedSlug);
  } catch (e) {
    toast(e.message, "err");
  } finally {
    btn.disabled = false;
    btn.textContent = "Run +2 cycles";
  }
}

/* Launch */
function updateBudgetLabel() {
  const v = Number($("#launch-budget").value || 0);
  $("#launch-budget-label").textContent = money(v);
}

async function updateLaunchCostBox(profiles) {
  const box = $("#launch-cost-box");
  if (!box) return;
  if (!profiles) {
    try {
      profiles = await refreshCosts();
    } catch (_) {
      box.textContent = "Configure models in Settings to see estimates.";
      return;
    }
  }
  const p = profiles[state.usageProfile] || profiles.medium;
  if (!p) return;
  const b = p.breakdown || {};
  box.innerHTML = `
    <div class="kpi-meta" style="margin-bottom:0.75rem">${escapeHtml(
      p.profile_label || state.usageProfile
    )} · based on saved/default models</div>
    <div class="cost-bar-row"><div>Brain</div><div class="cost-bar-track"><div class="cost-bar-fill" style="width:${Math.min(
      100,
      (b.brain / Math.max(p.total_usd, 1)) * 100
    )}%"></div></div><div class="mono" style="text-align:right">${money(
    b.brain
  )}</div></div>
    <div class="cost-bar-row"><div>Operator</div><div class="cost-bar-track"><div class="cost-bar-fill" style="width:${Math.min(
      100,
      (b.operator / Math.max(p.total_usd, 1)) * 100
    )}%"></div></div><div class="mono" style="text-align:right">${money(
    b.operator
  )}</div></div>
    <div class="cost-bar-row"><div>Marketer</div><div class="cost-bar-track"><div class="cost-bar-fill" style="width:${Math.min(
      100,
      (b.marketer / Math.max(p.total_usd, 1)) * 100
    )}%"></div></div><div class="mono" style="text-align:right">${money(
    b.marketer
  )}</div></div>
    <div class="cost-bar-row"><div>Accountant</div><div class="cost-bar-track"><div class="cost-bar-fill" style="width:${Math.min(
      100,
      (b.accountant / Math.max(p.total_usd, 1)) * 100
    )}%"></div></div><div class="mono" style="text-align:right">${money(
    b.accountant
  )}</div></div>
    <div class="mt-1" style="display:flex;justify-content:space-between;align-items:baseline">
      <span class="muted">Projected monthly LLM</span>
      <strong style="font-size:1.2rem;color:var(--success)">${money(p.total_usd)}</strong>
    </div>
    <div class="field-hint mt-1">Company budget (slider) is separate infra/domain spend, not LLM API cost.</div>`;
}

async function loadLaunch() {
  updateBudgetLabel();
  try {
    const config = await api("/config");
    state.config = config;
    state.selectedModels = { ...config.models };
    state.usageProfile = config.usage_profile || "medium";
    const profiles = await api("/costs/estimate", {
      method: "POST",
      body: JSON.stringify({ models: config.models }),
    });
    await updateLaunchCostBox(profiles.profiles);
  } catch (e) {
    $("#launch-cost-box").textContent = e.message;
  }
}

function openConfirm(title, body, onOk) {
  $("#confirm-title").textContent = title;
  $("#confirm-body").textContent = body;
  state.confirmAction = onOk;
  $("#confirm-modal").classList.add("show");
}

function closeConfirm() {
  state.confirmAction = null;
  $("#confirm-modal").classList.remove("show");
}

function requestLaunch(e) {
  e.preventDefault();
  const name = $("#launch-name").value.trim();
  if (!name) return toast("Company name required", "err");
  openConfirm(
    "Launch company?",
    `Start autonomous agents for “${name}” with budget ${money(
      $("#launch-budget").value
    )}?`,
    () => doLaunch()
  );
}

async function doLaunch() {
  closeConfirm();
  const btn = $("#launch-btn");
  const status = $("#launch-status");
  btn.disabled = true;
  btn.innerHTML = `<span class="spinner sm"></span> Launching…`;
  status.classList.remove("hidden");
  status.textContent = "Spinning up agents — usually 10–30s in mock mode…";
  setLoading(true, "Launching company…");

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
    setLoading(false);
    toast(err.message, "err");
    btn.disabled = false;
    btn.textContent = "Launch Company";
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
      setTimeout(() => pollJob(jobId, name), 1400);
      return;
    }
    setLoading(false);
    if (job.status === "error") {
      toast(job.error || "Launch failed", "err");
      status.textContent = job.error;
      btn.disabled = false;
      btn.textContent = "Launch Company";
      return;
    }
    toast(`${name} launched successfully`);
    status.textContent = `Done · ${job.result?.domain || "domain pending"} · ${
      job.result?.vercel_url || ""
    }`;
    btn.disabled = false;
    btn.textContent = "Launch Company";
    if (job.result?.slug) {
      state.selectedSlug = job.result.slug;
      openCompany(job.result.slug);
    }
  } catch (err) {
    setLoading(false);
    toast(err.message, "err");
    btn.disabled = false;
    btn.textContent = "Launch Company";
  }
}

/* Approvals */
function renderApprovalCards(target, items, compact = false) {
  const list = $(target);
  if (!items.length) {
    list.innerHTML = `<div class="empty"><h4>No pending approvals</h4><p>Agents only pause for money and irreversible actions.</p></div>`;
    return;
  }
  list.innerHTML = items
    .map((a) => {
      const options = a.options || [];
      const amount = Number(a.amount_usd || 0);
      const risks = [];
      if (amount > 0) risks.push(`<span class="risk money">${money(amount)}</span>`);
      if (a.irreversible) risks.push(`<span class="risk irreversible">Irreversible</span>`);
      if (a.action === "choose_option")
        risks.push(`<span class="risk choice">Choice required</span>`);
      const optsHtml = options.length
        ? `<div class="option-list">${options
            .map(
              (o, idx) => `
            <label>
              <input type="radio" name="opt-${escapeHtml(a.id)}" value="${idx}" ${
                idx === 0 ? "checked" : ""
              } />
              <span>${escapeHtml(o.label || o.domain || JSON.stringify(o))}</span>
            </label>`
            )
            .join("")}</div>`
        : "";
      return `
      <div class="approval-card ${compact ? "mb-1" : ""}" data-id="${escapeHtml(a.id)}" style="${
        compact ? "" : "margin-bottom:0.85rem"
      }">
        <h4>${escapeHtml(a.action)} ${amount ? "· " + money(amount) : ""}</h4>
        <p>${escapeHtml(a.description || "")}</p>
        <div class="risk-row">${risks.join("") || '<span class="risk">Review</span>'}</div>
        <p class="mono muted" style="font-size:0.72rem">${escapeHtml(a.id)} · by ${escapeHtml(
        String(a.requested_by)
      )}</p>
        ${optsHtml}
        <div class="btn-row">
          <button class="btn btn-success btn-sm" data-approve="${escapeHtml(a.id)}">Approve</button>
          <button class="btn btn-danger btn-sm" data-reject="${escapeHtml(a.id)}">Reject</button>
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
        if (state.page === "approvals") loadApprovals();
        if (state.page === "company" && state.selectedSlug)
          loadCompany(state.selectedSlug);
        loadDashboard().catch(() => {});
      } catch (e) {
        toast(e.message, "err");
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
        toast("Rejected", "info");
        if (state.page === "approvals") loadApprovals();
        if (state.page === "company" && state.selectedSlug)
          loadCompany(state.selectedSlug);
      } catch (e) {
        toast(e.message, "err");
      }
    });
  });
}

async function loadApprovals() {
  const data = await api("/approvals");
  updateApprovalBadge((data.approvals || []).length);
  renderApprovalCards("#approvals-list", data.approvals || []);
}

/* Usage */
async function loadUsage() {
  const [config, companiesData] = await Promise.all([
    api("/config"),
    api("/companies"),
  ]);
  state.config = config;
  state.usageProfile = config.usage_profile || "medium";
  const est = await api("/costs/estimate", {
    method: "POST",
    body: JSON.stringify({ models: config.models }),
  });
  const profiles = est.profiles || {};
  const active = profiles[state.usageProfile] || {};
  const spent = (companiesData.companies || []).reduce(
    (s, c) => s + (c.spent_usd || 0),
    0
  );
  $("#usage-profile").textContent = active.profile_label || state.usageProfile;
  $("#usage-total").textContent = money(active.total_usd);
  $("#usage-spend").textContent = money(spent);

  const b = active.breakdown || {};
  const max = Math.max(1, ...Object.values(b));
  $("#usage-bars").innerHTML = ["brain", "operator", "marketer", "accountant"]
    .map(
      (role) => `
    <div class="cost-bar-row">
      <div class="agent-badge ${role}"><span class="orb"></span>${role}</div>
      <div class="cost-bar-track"><div class="cost-bar-fill" style="width:${
        ((b[role] || 0) / max) * 100
      }%;background:var(--${role === "brain" ? "brain" : role === "operator" ? "operator" : role === "marketer" ? "marketer" : "accountant"})"></div></div>
      <div class="mono" style="text-align:right">${money(b[role])}</div>
    </div>`
    )
    .join("");

  $("#usage-profiles").innerHTML = ["light", "medium", "heavy"]
    .map((k) => {
      const p = profiles[k];
      if (!p) return "";
      return `<tr class="${k === state.usageProfile ? "active" : ""}"><td>${escapeHtml(
        p.profile_label
      )}</td><td class="num">${p.companies_per_month}</td><td class="num">${money(
        p.total_usd
      )}</td></tr>`;
    })
    .join("");
}

/* Refresh current page */
function refreshCurrent() {
  showPage(state.page);
  toast("Refreshed", "info");
}

/* Boot */
async function init() {
  // theme / sidebar prefs
  applyTheme(localStorage.getItem("autocorp-theme") || "dark");
  if (localStorage.getItem("autocorp-sidebar-collapsed") === "1") {
    $("#shell").classList.add("sidebar-collapsed");
  }

  $$(".nav-item[data-page]").forEach((btn) =>
    btn.addEventListener("click", () => showPage(btn.dataset.page))
  );
  document.body.addEventListener("click", (e) => {
    const t = e.target.closest("[data-goto]");
    if (t) {
      e.preventDefault();
      showPage(t.dataset.goto);
    }
  });

  $("#theme-toggle").addEventListener("click", toggleTheme);
  $("#collapse-btn").addEventListener("click", toggleSidebar);
  $("#refresh-btn").addEventListener("click", refreshCurrent);
  $("#launch-form").addEventListener("submit", requestLaunch);
  $("#launch-budget").addEventListener("input", updateBudgetLabel);
  $("#save-config-btn").addEventListener("click", () =>
    saveConfig().catch((e) => toast(e.message, "err"))
  );
  $("#cfg-profile").addEventListener("change", async () => {
    state.usageProfile = $("#cfg-profile").value;
    await refreshCosts();
  });
  $("#co-refresh").addEventListener("click", () => {
    if (state.selectedSlug) loadCompany(state.selectedSlug);
  });
  $("#co-run").addEventListener("click", runMoreCycles);
  $$("#co-tabs .tab").forEach((tab) =>
    tab.addEventListener("click", () => switchCompanyTab(tab.dataset.tab))
  );
  $("#confirm-cancel").addEventListener("click", closeConfirm);
  $("#confirm-ok").addEventListener("click", () => {
    const fn = state.confirmAction;
    closeConfirm();
    if (fn) fn();
  });
  $("#confirm-modal").addEventListener("click", (e) => {
    if (e.target.id === "confirm-modal") closeConfirm();
  });

  // Keyboard shortcuts
  document.addEventListener("keydown", (e) => {
    if (e.target.matches("input, textarea, select")) return;
    const map = {
      1: "dashboard",
      2: "launch",
      3: "companies",
      4: "approvals",
      5: "settings",
      6: "usage",
      7: "docs",
    };
    if (map[e.key]) showPage(map[e.key]);
    if (e.key.toLowerCase() === "t") toggleTheme();
    if (e.key.toLowerCase() === "r") refreshCurrent();
    if (e.key.toLowerCase() === "l") showPage("launch");
  });

  try {
    setLoading(true, "Loading AutoCorp…");
    const meta = await api("/meta");
    $("#meta-version").textContent = `v${meta.version}`;
    $("#meta-setup").textContent = meta.setup_completed
      ? "Setup complete"
      : "Setup needed";
    await loadDashboard();
  } catch (e) {
    toast(`API error: ${e.message}`, "err");
  } finally {
    setLoading(false);
  }
}

init();
