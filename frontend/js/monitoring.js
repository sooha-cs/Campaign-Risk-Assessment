const page = $("#page"), msg = $("#msg");
const input = store.get("input"), plan = store.get("plan");
let analysis = store.get("analysis");

if (!input || !plan) {
  emptyState(page, "No project yet");
} else {
  init();
}

function init() {
  const form = $("#progressForm"), btn = $("#submitBtn");
  const alertsEl = $("#alerts"), healthEl = $("#health"), trendEl = $("#trend"), histEl = $("#history");
  const pid = analysis && analysis.projectId;
  const schedule = arr(plan.schedule);

  // default date: today, but never before the project start
  const today = new Date().toISOString().slice(0, 10);
  const dateEl = $("#asOfDate");
  dateEl.min = input.startDate;
  dateEl.value = today < input.startDate ? input.startDate : today;

  /* ---------- task inputs ---------- */
  function renderTasks(prefill = {}) {
    $("#taskList").innerHTML = `<table class="table table-sm align-middle mb-0"><tbody>
      ${schedule.map(t => `<tr><td class="small">${esc(t.taskId)} ${esc(t.name)}</td>
        <td style="width:6.5rem"><input type="number" min="0" max="100" class="form-control form-control-sm" data-task="${esc(t.taskId)}"
          value="${prefill[t.taskId] ?? ""}" placeholder="%" aria-label="Percent complete for ${esc(t.name)}"></td></tr>`).join("")}
      </tbody></table>`;
  }
  renderTasks();

  /* ---------- health + alerts ---------- */
  const HEALTH = { "On Track": "low", "At Risk": "med", "Off Track": "crit" };
  function renderHealth(m) {
    if (!m) { healthEl.innerHTML = '<p class="text-secondary mb-0">No update submitted yet.</p>'; return; }
    const row = (k, v) => `<tr><th>${k}</th><td>${v}</td></tr>`;
    healthEl.innerHTML = `<p>${badge(HEALTH[m.health] || "med").replace(/>[^<]+</, `>${esc(m.health)}<`)}
      <span class="ms-2 text-secondary small">as of ${esc(m.asOfDate || "")}</span></p>
      <table class="table table-sm mb-0"><tbody>
      ${row("Complete / planned", `${m.percentComplete}% / ${m.plannedPercent}%`)}
      ${row("SPI (schedule)", m.spi ?? "-")}
      ${row("CPI (cost)", m.cpi ?? "-")}
      ${row("Forecast finish", `${esc(fmtDate(m.forecastFinish))} (deadline ${esc(fmtDate(m.deadline))}, delay ${m.scheduleDelayDays} d)`)}
      ${row("Forecast cost", `${money(m.forecastCost)} (budget ${money(m.budget)})`)}
      </tbody></table>`;
  }
  function renderAlerts(alerts) {
    if (alerts == null) { alertsEl.innerHTML = '<p class="text-secondary mb-0">No update submitted yet.</p>'; return; }
    if (!alerts.length) { alertsEl.innerHTML = '<p class="text-secondary mb-0">No alerts. Everything is on plan.</p>'; return; }
    alertsEl.innerHTML = alerts.map(a => `<div class="panel alert-risk mb-2">${esc(a)}</div>`).join("");
  }

  /* ---------- history ---------- */
  async function loadHistory() {
    if (!pid) {
      trendEl.innerHTML = histEl.innerHTML = '<p class="text-secondary mb-0">Run the analysis from the Project Input page first.</p>';
      return;
    }
    try {
      const res = await api(`/api/history?projectId=${encodeURIComponent(pid)}&full=true`);
      const snaps = arr(res.snapshots);
      if (!snaps.length) throw new ApiError(404, "none");
      renderTrend(snaps);
      renderRiskHistory(snaps);
      // prefill the task boxes with the last saved percentages
      if (!form.querySelector("[data-task]").value) renderTasks(snaps[snaps.length - 1].tasks || {});
    } catch (err) {
      if (err.status === 404) {
        const none = '<p class="text-secondary mb-0">No history yet. Save a progress update to start the timeline.</p>';
        trendEl.innerHTML = histEl.innerHTML = none;
      } else { showError(trendEl, err); histEl.innerHTML = ""; }
    }
  }

  function renderTrend(snaps) {
    trendEl.innerHTML = `<div class="table-responsive"><table class="table table-sm mb-0"><thead><tr>
      <th>As of</th><th>Health</th><th>Done</th><th>SPI</th><th>CPI</th><th>Forecast cost</th><th>Delay</th><th>Top risk</th></tr></thead><tbody>
      ${snaps.map(s => `<tr><td>${esc(fmtDate(s.asOfDate))}</td><td>${esc(s.health)}</td><td>${esc(s.percentComplete)}%</td>
        <td>${esc(s.spi ?? "-")}</td><td>${esc(s.cpi ?? "-")}</td><td>${money(s.forecastCost)}</td>
        <td>${esc(s.scheduleDelayDays)} d</td><td>${esc(s.highestRiskScore ?? "-")}</td></tr>`).join("")}
      </tbody></table></div>`;
  }

  function renderRiskHistory(snaps) {
    // rows are matched by the stable risk `key`, not by description (descriptions change on every AI run)
    const label = {}, keys = [];
    snaps.forEach(s => arr(s.risks).forEach(r => { label[r.key] = r.description; if (!keys.includes(r.key)) keys.push(r.key); }));
    if (!keys.length) { histEl.innerHTML = '<p class="text-secondary mb-0">No risk scores saved yet.</p>'; return; }
    const score = (s, k) => { const r = arr(s.risks).find(x => x.key === k); return r ? r.score : "-"; };
    histEl.innerHTML = `<div class="table-responsive"><table class="table table-sm mb-0"><thead><tr><th>Risk</th>
      ${snaps.map(s => `<th>${esc(fmtDate(s.asOfDate))}${s.reanalyzed ? "" : " *"}</th>`).join("")}</tr></thead><tbody>
      ${keys.map(k => `<tr><td>${esc(label[k])}</td>${snaps.map(s => `<td>${esc(score(s, k))}</td>`).join("")}</tr>`).join("")}
      </tbody></table></div><p class="small text-secondary mb-0 mt-2">* AI analysis was not re-run for this update, so scores are carried over.</p>`;
  }

  /* ---------- submit ---------- */
  function buildBody() {
    const tasks = [...form.querySelectorAll("[data-task]")]
      .filter(i => i.value !== "")
      .map(i => ({ taskId: i.dataset.task, percentComplete: +i.value }));
    const body = {
      project: input,                       // sent every time, so the backend can save it on the first update
      plan,
      risks: analysis,                      // used as the baseline for new/rising comparison on the first update
      reanalyze: $("#reanalyze").checked,
      progress: { asOfDate: dateEl.value, actualCostToDate: +$("#actualCost").value, tasks }
    };
    if (pid) body.projectId = pid;
    return body;
  }

  form.addEventListener("submit", async e => {
    e.preventDefault();
    msg.innerHTML = "";
    if (!form.reportValidity()) return;
    const ai = $("#reanalyze").checked;
    setBusy(btn, true, ai ? "Re-assessing (up to 60 s)..." : "Saving...");
    try {
      const res = await api("/api/update", { method: "POST", body: buildBody() });
      const m = { ...res.metrics, asOfDate: res.asOfDate };
      if (res.reanalyzed && Array.isArray(res.risks)) {   // keep the other pages in sync with the new scores
        analysis = { ...(analysis || {}), risks: res.risks, summary: res.summary };
        store.set("analysis", analysis);
      }
      store.set("metrics", m); store.set("alerts", m.alerts || []);
      renderHealth(m); renderAlerts(m.alerts || []);
      await loadHistory();
      msg.innerHTML = `<div class="alert alert-success" role="status">Update saved${res.reanalyzed ? " and risks re-assessed" : ""}.</div>`;
    } catch (err) {
      showError(msg, err);
    } finally {
      setBusy(btn, false);
    }
  });

  renderHealth(store.get("metrics"));
  renderAlerts(store.get("alerts"));
  loadHistory();
}
