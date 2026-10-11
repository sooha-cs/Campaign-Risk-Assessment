const root = $("#root");
const plan = store.get("plan");
const analysis = store.get("analysis");

if (!plan) emptyState(root, "No plan yet"); else render();

function gantt(tasks) {
  const t = tasks.map(x => ({
    name: (x.name || x.taskId || "") + (x.isCritical ? " (critical)" : ""),
    s: new Date(x.startDate),
    e: new Date(x.endDate)
  })).filter(x => !isNaN(x.s) && !isNaN(x.e));
  if (!t.length) return '<p class="text-secondary mb-0">The plan has no dated tasks to chart.</p>';
  const min = Math.min(...t.map(x => x.s)), max = Math.max(...t.map(x => x.e)), span = Math.max(max - min, 1);
  return `<div class="gantt">${t.map(x => `<div class="small">${esc(x.name)}</div>
    <div class="gantt-track" title="${esc(fmtDate(x.s) + " to " + fmtDate(x.e))}">
    <div class="gantt-bar" style="left:${(x.s - min) / span * 100}%;width:${Math.max((x.e - x.s) / span * 100, 1)}%"></div></div>`).join("")}</div>
    <div class="d-flex justify-content-between small text-secondary mt-2"><span>${fmtDate(min)}</span><span>${fmtDate(max)}</span></div>`;
}

function render() {
  const warnings = arr(plan.warnings).map(w => (typeof w === "string" ? w : w.message || JSON.stringify(w)));
  const s = plan.scheduleSummary || {}, c = plan.costEstimate || {};
  // backend wbs = list of phases, each with a tasks list; flatten it for the table
  const tasks = arr(plan.wbs).flatMap(ph => arr(ph.tasks).map(t => ({ ...t, phase: ph.name })));
  const cost = arr(c.byPhase);
  const maxCost = Math.max(...cost.map(x => +x.cost || 0), 1);
  const resources = arr(plan.resourcePlan);
  const workflow = arr(plan.workflow);
  const yes = (ok) => ok ? '<span class="lvl lvl-low">Yes</span>' : '<span class="lvl lvl-crit">No</span>';

  root.innerHTML = `
  ${warnings.map(w => `<div class="alert alert-warning" role="alert"><strong>Warning:</strong> ${esc(w)}</div>`).join("")}

  <div class="row g-4 mb-4">
    <div class="col-lg-6"><div class="panel h-100"><h2 class="h5 mb-3">Schedule summary</h2>
      <table class="table table-sm mb-0"><tbody>
        <tr><th>Start</th><td>${esc(fmtDate(s.startDate))}</td></tr>
        <tr><th>Planned finish</th><td>${esc(fmtDate(s.finishDate))}</td></tr>
        <tr><th>Deadline</th><td>${esc(fmtDate(s.deadline))}</td></tr>
        <tr><th>Duration</th><td>${esc(s.durationDays)} of ${esc(s.daysAvailable)} days available</td></tr>
        <tr><th>Within deadline</th><td>${yes(s.withinDeadline)}</td></tr>
        <tr><th>Critical path</th><td>${esc(arr(s.criticalPath).join(" → "))}</td></tr>
      </tbody></table></div></div>
    <div class="col-lg-6"><div class="panel h-100"><h2 class="h5 mb-3">Cost summary</h2>
      <table class="table table-sm mb-0"><tbody>
        <tr><th>Base cost</th><td>${money(c.baseCost)}</td></tr>
        <tr><th>Contingency (${Math.round((c.contingencyRate || 0) * 100)}%)</th><td>${money(c.contingency)}</td></tr>
        <tr><th>Total estimate</th><td><strong>${money(c.total)}</strong></td></tr>
        <tr><th>Budget</th><td>${money(c.budget)}</td></tr>
        <tr><th>Remaining</th><td>${money(c.variance)}</td></tr>
        <tr><th>Within budget</th><td>${yes(c.withinBudget)}</td></tr>
      </tbody></table></div></div>
  </div>

  <div class="panel mb-4"><h2 class="h5 mb-3">Work breakdown structure</h2>
    ${tasks.length ? `<div class="table-responsive"><table class="table table-sm align-middle mb-0">
      <thead><tr><th>ID</th><th>Phase</th><th>Task</th><th>Resource</th><th>Days</th><th>Depends on</th><th>Cost</th></tr></thead><tbody>
      ${tasks.map(t => `<tr><td>${esc(t.id)}</td><td>${esc(t.phase)}</td><td>${esc(t.name)}</td><td>${esc(t.resource)}</td>
        <td>${esc(t.durationDays)}</td><td>${esc(arr(t.dependsOn).join(", ") || "-")}</td><td>${money(t.estimatedCost)}</td></tr>`).join("")}
      </tbody></table></div>` : '<p class="text-secondary mb-0">The plan has no work breakdown.</p>'}</div>

  <div class="panel mb-4"><h2 class="h5 mb-3">Schedule</h2>${gantt(arr(plan.schedule))}</div>

  <div class="row g-4 mb-4">
    <div class="col-lg-6"><div class="panel h-100"><h2 class="h5 mb-3">Cost by phase</h2>
      ${cost.length ? cost.map(x => `<div class="bar-row"><span>${esc(x.phase)}</span>
        <div class="bar-track"><div class="bar-fill" style="width:${(+x.cost || 0) / maxCost * 100}%;background:var(--teal)"></div></div>
        <span class="small text-nowrap">${money(x.cost)}</span></div>`).join("") : '<p class="text-secondary mb-0">No cost data.</p>'}</div></div>
    <div class="col-lg-6"><div class="panel h-100"><h2 class="h5 mb-3">Resource plan</h2>
      ${resources.length ? `<div class="table-responsive"><table class="table table-sm align-middle mb-0">
        <thead><tr><th>Role</th><th>Count</th><th>Per day</th><th>Days</th><th>Utilisation</th><th>Total</th></tr></thead><tbody>
        ${resources.map(r => `<tr><td>${esc(r.role)}${r.overallocated ? ' <span class="lvl lvl-high">Overallocated</span>' : ""}</td>
          <td>${esc(r.count)}</td><td>${money(r.costPerDay)}</td><td>${esc(r.totalDays)}</td>
          <td>${esc(r.utilizationPercent)}%</td><td>${money((r.totalDays || 0) * (r.costPerDay || 0))}</td></tr>`).join("")}
        </tbody></table></div>` : '<p class="text-secondary mb-0">No resource plan.</p>'}</div></div>
  </div>

  <div class="panel mb-4"><h2 class="h5 mb-3">Workflow</h2>
    ${workflow.length ? `<ol class="mb-0">${workflow.map(w => `<li><strong>${esc(w.name)}</strong>
      ${w.description ? "– " + esc(w.description) : ""} <span class="text-secondary small">(${esc(w.owner)})</span></li>`).join("")}</ol>`
      : '<p class="text-secondary mb-0">No workflow steps.</p>'}</div>

  <a class="btn btn-main" href="risks.html">View risks</a>`;
}
