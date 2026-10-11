const listEl = $("#riskList"), sel = $("#cat");
const risks = getRisks();

if (!risks) {
  emptyState(listEl);
} else {
  sel.innerHTML = '<option value="">All categories</option>' + CATEGORIES.map(c => `<option>${c}</option>`).join("");
  const draw = () => {
    const shown = risks.filter(r => !sel.value || r.category === sel.value).sort((a, b) => b.score - a.score);
    listEl.innerHTML = shown.length ? shown.map(r => `<div class="col-lg-6">
      <div class="panel risk-card ${r.lvl}">
        <div class="d-flex justify-content-between gap-2"><h2 class="h5">${esc(r.description)}</h2>${badge(r.lvl)}</div>
        <p class="mb-1 text-secondary">${esc(r.category)}</p>
        <p class="mb-0 small">Probability ${r.probability} &times; Impact ${r.impact} = <strong>${r.score}</strong></p>
      </div></div>`).join("") : '<p class="text-secondary">No risks in this category.</p>';
  };
  sel.addEventListener("change", draw);
  draw();
}