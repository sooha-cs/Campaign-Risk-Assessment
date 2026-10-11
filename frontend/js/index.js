const form = $("#projectForm"), msg = $("#msg"), btn = $("#submitBtn");
const tpl = { res: $("#resTpl"), past: $("#pastTpl") };
const addRow = (list, t) => $(list).appendChild(t.content.cloneNode(true));
addRow("#resList", tpl.res);

document.addEventListener("click", e => {
  if (e.target.dataset.add === "res") addRow("#resList", tpl.res);
  if (e.target.dataset.add === "past") addRow("#pastList", tpl.past);
  if (e.target.hasAttribute("data-remove")) e.target.closest(".row-item").remove();
});

const field = n => form.elements[n].value.trim();
const lines = n => field(n).split("\n").map(s => s.trim()).filter(Boolean);
const cell = (row, n) => row.querySelector(`[name="${n}"]`).value.trim();
const rowsOf = sel => [...form.querySelectorAll(sel)];

function buildPayload() {
  const p = {
    name: field("name"),
    budget: +field("budget"),
    startDate: field("startDate"),
    deadline: field("deadline"),
    teamSize: +field("teamSize"),
    resources: rowsOf("#resList .row-item")
      .map(r => ({ role: cell(r, "role"), count: +cell(r, "count"), costPerDay: +cell(r, "costPerDay") }))
      .filter(r => r.role)
  };
  const deliverables = lines("deliverables"), constraints = lines("constraints");
  const pastProjects = rowsOf("#pastList .row-item")
    .map(r => ({ name: cell(r, "pname"), plannedCost: +cell(r, "pplancost"), actualCost: +cell(r, "pactcost"), plannedDays: +cell(r, "pplandays"), actualDays: +cell(r, "pactdays"), outcome: cell(r, "poutcome") }))
    .filter(x => x.name);
  // optional fields are only sent when filled in
  if (deliverables.length) p.deliverables = deliverables;
  if (constraints.length) p.constraints = constraints;
  if (pastProjects.length) p.pastProjects = pastProjects;
  return p;
}

function validate(p) {
  const e = [];
  if (!p.name) e.push("Project name is required.");
  if (!(p.budget > 0)) e.push("Budget must be greater than 0.");
  if (!p.startDate || !p.deadline) e.push("Start date and deadline are required.");
  else if (p.deadline <= p.startDate) e.push("Deadline must be after the start date.");
  if (!(p.teamSize > 0)) e.push("Team size must be at least 1.");
  if (!p.resources.length) e.push("Add at least one resource with a role.");
  (p.pastProjects || []).forEach(x => { if (!(x.plannedCost > 0 && x.plannedDays > 0)) e.push(`Past project "${x.name}": planned cost and planned days must be greater than 0.`); });
  return e;
}

let timer;
function setLoading(on) {
  $("#fields").disabled = on;
  $("#progress").hidden = !on;
  setBusy(btn, on, "Working...");
  clearInterval(timer);
  if (on) {
    const t0 = Date.now();
    timer = setInterval(() => { $("#elapsed").textContent = Math.round((Date.now() - t0) / 1000) + "s"; }, 500);
  }
}
function step(text, pct) { $("#stepText").textContent = text; $("#bar").style.width = pct + "%"; }

form.addEventListener("submit", async e => {
  e.preventDefault();
  msg.innerHTML = "";
  const input = buildPayload();
  const problems = validate(input);
  if (problems.length) { showError(msg, new ApiError(400, "Please fix the form before continuing.", problems)); return; }

  let planDone = false;
  setLoading(true);
  try {
    step("Step 1 of 2: building the project plan...", 15);
    const plan = await api("/api/plan", { method: "POST", body: input });
    planDone = true;
    store.set("input", input); store.set("plan", plan);

    step("Step 2 of 2: identifying and scoring risks...", 55);
    const analysis = await api("/api/analyze", { method: "POST", body: { project: input, plan } });
    store.set("analysis", analysis);
    store.set("alerts", null);

    step("Done. Opening your plan...", 100);
    location.href = "plan.html";
  } catch (err) {
    showError(msg, err);
    if (planDone) msg.insertAdjacentHTML("beforeend",
      '<p class="small">The plan was created. <a href="plan.html">View it</a>, or submit again to retry the risk analysis.</p>');
    window.scrollTo({ top: 0, behavior: "smooth" });
  } finally {
    if (!document.hidden) setLoading(false);
  }
});