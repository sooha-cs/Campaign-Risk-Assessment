const root = $("#root");

const actionsOf = r => arr(r.mitigation).map(a => (typeof a === "string" ? a : a.action || a.description || JSON.stringify(a)));

function render() {
  const risks = getRisks();
  if (!risks) { emptyState(root); return; }
  // Mitigation actions, owner and priority all come back from /api/analyze (there is no /api/mitigate).
  root.innerHTML = `<div class="panel"><div class="table-responsive"><table class="table align-middle mb-0">
    <thead><tr><th>Risk</th><th>Actions</th><th>Owner</th><th>Priority</th></tr></thead><tbody>
    ${[...risks].sort((a, b) => b.score - a.score).map(r => `<tr>
      <td>${esc(r.description)}<div class="small text-secondary">${esc(r.category || "")} &middot; score ${r.score}</div></td>
      <td>${actionsOf(r).length ? `<ul class="mb-0 ps-3">${actionsOf(r).map(a => `<li>${esc(a)}</li>`).join("")}</ul>` : "-"}</td>
      <td>${esc(r.owner || "-")}</td>
      <td>${badge(r.lvl)}<div class="small text-secondary mt-1">${esc(r.priority || "")}</div></td></tr>`).join("")}
    </tbody></table></div></div>`;
}

render();
