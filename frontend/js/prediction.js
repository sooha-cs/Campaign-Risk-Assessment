const root = $("#root");
const risks = getRisks();

if (!risks) {
  emptyState(root);
} else {
  // heat map: rows = probability 5..1, columns = impact 1..5, built from each risk's probability and impact
  let heat = '<div class="heat" role="img" aria-label="Heat map of probability against impact">';
  for (let p = 5; p >= 1; p--) {
    heat += `<div class="ax">${p}</div>`;
    for (let i = 1; i <= 5; i++) {
      const here = risks.filter(r => r.probability === p && r.impact === i);
      const tip = here.map(r => `#${r.id} ${r.description}`).join("; ") || "No risks";
      heat += `<div class="${levelOf(p * i)}${here.length ? " has" : ""}" title="${esc(tip)}">${here.map(r => "#" + r.id).join(" ")}</div>`;
    }
  }
  heat += '<div class="ax"></div>' + [1, 2, 3, 4, 5].map(i => `<div class="ax">${i}</div>`).join("") + "</div>";

  // bars: width = score out of 25
  const sorted = [...risks].sort((a, b) => b.score - a.score);
  const bars = sorted.map(r => `<div class="bar-row"><span title="${esc(r.description)}">#${r.id} ${esc(r.category || "")}</span>
    <div class="bar-track"><div class="bar-fill" style="width:${r.score / 25 * 100}%;background:var(--${r.lvl})"></div></div><b>${r.score}</b></div>`).join("");

  root.innerHTML = `<div class="row g-4">
    <div class="col-lg-6"><div class="panel h-100"><h2 class="h5 mb-3">Heat map</h2>${heat}
      <p class="small text-secondary mt-2">Rows: probability (1-5). Columns: impact (1-5). Numbers are risk IDs.</p></div></div>
    <div class="col-lg-6"><div class="panel h-100"><h2 class="h5 mb-3">Risk scores</h2>${bars}
      <div class="table-responsive mt-4"><table class="table table-sm align-middle mb-0">
        <thead><tr><th>Score</th><th>Level</th><th>Action</th></tr></thead><tbody>
        <tr><td>1-4</td><td>${badge("low")}</td><td>Monitor</td></tr>
        <tr><td>5-9</td><td>${badge("med")}</td><td>Plan a response</td></tr>
        <tr><td>10-15</td><td>${badge("high")}</td><td>Act this week</td></tr>
        <tr><td>16-25</td><td>${badge("crit")}</td><td>Escalate immediately</td></tr></tbody></table></div></div></div>
  </div>
  <div class="panel mt-4"><h2 class="h5 mb-3">Risk key</h2><ul class="mb-0">
    ${sorted.map(r => `<li>#${r.id} ${esc(r.description)} (P${r.probability} &times; I${r.impact})</li>`).join("")}</ul></div>
  <a class="btn btn-main mt-4" href="mitigation.html">View mitigation plan</a>`;
}