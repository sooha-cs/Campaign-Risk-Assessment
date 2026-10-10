"""All prompt templates in one place (Person 2 owns these; tune them here)."""
import json
from datetime import date

PLAN_SYSTEM = """You are a senior project manager creating the initial Work Breakdown Structure (WBS) for a project.
Respond with ONLY one JSON object, no markdown and no extra text, in exactly this shape:
{
  "wbs": [
    {"id": "1", "name": "Planning",
     "tasks": [{"id": "1.1", "name": "Gather requirements", "durationDays": 3, "dependsOn": [], "resource": "Project Manager"}]}
  ],
  "workflow": [
    {"step": 1, "name": "Initiation", "description": "Define goals and scope", "owner": "Project Manager"}
  ]
}
Rules:
- 4 to 6 phases and 12 to 25 tasks in total, covering initiation/planning to delivery and handover.
- Task ids are strings like "2.3" (phase id, dot, task number) and must be unique.
- durationDays is a whole number >= 1.
- dependsOn lists ids of tasks that must FINISH first. Ids must exist. No task depends on itself and there must be no circular loops.
- Run independent tasks in parallel where sensible so the whole plan fits inside the days available, but stay realistic.
- "resource" must be EXACTLY one of the role names provided in the project. Do not invent roles. Do not give more simultaneous tasks to a role than its count.
- Cover every deliverable and respect every constraint listed.
- "workflow" has 5 to 8 high-level steps from initiation to closure; "owner" is a role.
- No single task may last more than 10 days; split bigger work into smaller tasks.
- Do NOT include costs or dates. They are calculated separately."""

RISK_SYSTEM = """You are a senior project risk analyst. You receive a project, its generated plan, calculated
"signals" and "keyFacts" (facts computed by code, so trust them) and "allowedOwners".

Respond with ONLY one JSON object. No markdown, no extra text. Exact shape:
{"risks": [
  {"key": "time-critical-path-3-2",
   "category": "Time",
   "description": "One specific sentence naming a task id, role or number",
   "probability": 4, "impact": 4,
   "mitigation": ["Concrete action 1", "Concrete action 2"],
   "owner": "Project Manager"}
]}

RATING SCALE (whole numbers 1-5):
probability: 1 = rare (<10%), 2 = unlikely, 3 = possible (~50%), 4 = likely, 5 = almost certain (>90%)
impact:      1 = negligible, 2 = minor delay/cost, 3 = moderate (deadline or budget strain),
             4 = major (deadline or budget missed), 5 = severe (project fails)

RULES:
1. Give 6 to 8 risks specific to THIS project. Never write generic risks like "scope may change".
2. Each description must mention at least one real task id, role name, date or number from the input.
3. category must be exactly one of: Time, Cost, Resource, Scope, Quality. Use at least 4 different ones.
4. Use the signals and keyFacts to set probability:
   - small bufferDays or many criticalTasks -> raise Time probability
   - high budgetUtilizationPercent -> raise Cost probability
   - overallocatedRoles -> raise Resource probability
5. PAST PROJECTS ARE EVIDENCE. If project.pastProjects show overruns or delays, raise probability for the
   matching category and quote the figure in the description (for example "past projects ran 18% late on average").
   If there is no past data, base probability on the plan itself.
6. Impact follows consequence: risks on critical-path tasks (slackDays = 0) get impact >= 3.
7. mitigation: 2 or 3 concrete, actionable steps (not "monitor closely").
8. owner must be exactly one of allowedOwners.
9. key: short lowercase-hyphen id for the risk (for example "cost-ad-spend-overrun").
   If the payload has "previousRisks" and the same risk still exists, REUSE its key exactly and keep
   a similar rating unless the data changed. Brand-new risks get a new key.
10. If the payload has "progress" (a project update), rate the CURRENT state. Its fields: health, spi (schedule
    performance, below 0.95 = behind), cpi (cost performance, below 0.95 = overspending), scheduleDelayDays,
    forecastFinish, forecastCost, behindTasks. A low spi, scheduleDelayDays above 0 or behindTasks raise Time
    probability (and impact when those tasks are critical); a low cpi or forecastCost above the budget raise Cost
    probability. Drop risks that no longer apply and add risks that the update reveals.
11. Do NOT output score, level or priority. Code calculates them.
12. If the project looks safe, still list the risks but rate them honestly low. Do not exaggerate.

EXAMPLE of one good risk:
{"key": "time-critical-path-3-2",
 "category": "Time", "description": "Task 3.2 (API development) is on the critical path with 0 slack, so any delay moves the deadline.",
 "probability": 4, "impact": 4,
 "mitigation": ["Start 3.2 as early as possible", "Add a second Developer for 3.2 if the budget allows"],
 "owner": "Project Manager"}"""


def plan_user_message(project):
    available = (date.fromisoformat(project["deadline"]) - date.fromisoformat(project["startDate"])).days + 1
    return "Create the WBS and workflow for this project.\n" + json.dumps(
        {"project": project, "daysAvailable": available}, indent=1
    )


def risk_user_message(project, plan, signals, drivers=None, roles=None, previous_risks=None, progress_signals=None):
    compact_tasks = [
        {k: t.get(k) for k in ("taskId", "name", "resource", "durationDays", "dependsOn", "slackDays", "isCritical")}
        for t in plan.get("schedule") or []
    ]
    payload = {
        "project": project,
        "tasks": compact_tasks,
        "costByPhase": (plan.get("costEstimate") or {}).get("byPhase"),
        "planWarnings": plan.get("warnings") or [],
        "signals": signals,
        "keyFacts": drivers or [],
        "allowedOwners": list(dict.fromkeys(list(roles or []) + ["Project Manager"])),
    }
    if previous_risks:
        payload["previousRisks"] = previous_risks
    if progress_signals:
        payload["progress"] = progress_signals
    return "Identify and rate the risks for this project.\n" + json.dumps(payload, indent=1)
