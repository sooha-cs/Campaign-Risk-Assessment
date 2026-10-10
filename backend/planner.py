"""Turns the AI's work breakdown structure (WBS) into a full plan.

The AI only proposes tasks, durations, dependencies and workflow steps.
Dates, critical path, costs and resource load are calculated HERE in code,
so the numbers are always consistent and never "hallucinated".
Assumptions: calendar days, one person per task, 10% contingency.
"""
from datetime import date, timedelta

from errors import AIOutputError

CONTINGENCY_RATE = 0.10
MAX_TASKS = 60


def _num(x):
    x = round(float(x), 2)
    return int(x) if x.is_integer() else x


def validate_wbs(wbs, resources):
    if not isinstance(wbs, list) or not wbs:
        raise AIOutputError("wbs must be a non-empty list of phases")
    roles = {r["role"].lower(): r["role"] for r in resources}
    errs, seen, clean = [], set(), []

    for p_idx, phase in enumerate(wbs, 1):
        if not isinstance(phase, dict) or not isinstance(phase.get("tasks"), list) or not phase["tasks"]:
            errs.append(f"phase #{p_idx} must be an object with a non-empty 'tasks' list")
            continue
        tasks = []
        for t in phase["tasks"]:
            if not isinstance(t, dict):
                errs.append(f"a task in phase #{p_idx} is not an object")
                continue
            tid = str(t.get("id", "")).strip()
            if not tid or tid in seen:
                errs.append(f"task id '{tid}' is missing or duplicated")
                continue
            seen.add(tid)
            try:
                dur = max(1, int(round(float(t.get("durationDays")))))
            except (TypeError, ValueError):
                errs.append(f"task {tid}: durationDays must be a number")
                continue
            role = roles.get(str(t.get("resource", "")).strip().lower())
            if role is None:
                errs.append(f"task {tid}: resource '{t.get('resource')}' must be exactly one of {sorted(roles.values())}")
                continue
            deps = t.get("dependsOn") or []
            if not isinstance(deps, list):
                deps = [deps]
            deps = list(dict.fromkeys(str(d).strip() for d in deps))
            tasks.append({
                "id": tid,
                "name": str(t.get("name") or f"Task {tid}").strip(),
                "durationDays": dur,
                "dependsOn": deps,
                "resource": role,
            })
        clean.append({
            "id": str(phase.get("id", p_idx)),
            "name": str(phase.get("name") or f"Phase {p_idx}").strip(),
            "tasks": tasks,
        })

    for phase in clean:
        for t in phase["tasks"]:
            for d in t["dependsOn"]:
                if d == t["id"]:
                    errs.append(f"task {t['id']} depends on itself")
                elif d not in seen:
                    errs.append(f"task {t['id']} depends on unknown task '{d}'")
    if len(seen) < 3:
        errs.append("the WBS needs at least 3 tasks")
    if len(seen) > MAX_TASKS:
        errs.append(f"too many tasks (max {MAX_TASKS})")
    if errs:
        raise AIOutputError(errs[:10])
    return clean


def validate_workflow(wf):
    if not isinstance(wf, list) or not wf:
        raise AIOutputError("workflow must be a non-empty list of steps")
    out = []
    for n, s in enumerate(wf, 1):
        if not isinstance(s, dict) or not str(s.get("name", "")).strip():
            raise AIOutputError(f"workflow step {n} needs a name")
        out.append({
            "step": n,
            "name": str(s["name"]).strip(),
            "description": str(s.get("description", "")).strip(),
            "owner": str(s.get("owner") or "Project Manager").strip(),
        })
    return out


def _cpm(tasks):
    """Critical Path Method. Returns earliest start, earliest finish, latest start, total days."""
    succ = {i: [] for i in tasks}
    indeg = {i: len(t["dependsOn"]) for i, t in tasks.items()}
    for i, t in tasks.items():
        for d in t["dependsOn"]:
            succ[d].append(i)

    queue = [i for i, n in indeg.items() if n == 0]
    order = []
    while queue:
        i = queue.pop(0)
        order.append(i)
        for s in succ[i]:
            indeg[s] -= 1
            if indeg[s] == 0:
                queue.append(s)
    if len(order) != len(tasks):
        raise AIOutputError("dependsOn contains a circular loop; dependencies must be one-directional")

    es, ef = {}, {}
    for i in order:
        es[i] = max((ef[d] for d in tasks[i]["dependsOn"]), default=0)
        ef[i] = es[i] + tasks[i]["durationDays"]
    total = max(ef.values())

    ls = {}
    for i in reversed(order):
        lf = min((ls[s] for s in succ[i]), default=total)
        ls[i] = lf - tasks[i]["durationDays"]
    return es, ef, ls, total


def build_plan(project, wbs, workflow):
    start = date.fromisoformat(project["startDate"])
    deadline = date.fromisoformat(project["deadline"])
    rates = {r["role"]: r["costPerDay"] for r in project["resources"]}

    tasks, listing = {}, []
    for phase in wbs:
        for t in phase["tasks"]:
            tasks[t["id"]] = {**t, "phase": phase["name"], "cost": t["durationDays"] * rates[t["resource"]]}
            listing.append(t["id"])

    es, ef, ls, total_days = _cpm(tasks)
    critical = [i for i in sorted(tasks, key=lambda i: (es[i], listing.index(i))) if ls[i] == es[i]]
    finish = start + timedelta(days=total_days - 1)

    # ---- WBS (with cost) ----
    wbs_out = [{
        "id": ph["id"], "name": ph["name"],
        "tasks": [{
            "id": t["id"], "name": t["name"], "durationDays": t["durationDays"],
            "dependsOn": t["dependsOn"], "resource": t["resource"],
            "estimatedCost": _num(tasks[t["id"]]["cost"]),
        } for t in ph["tasks"]],
    } for ph in wbs]

    # ---- Schedule ----
    schedule = [{
        "taskId": i, "name": tasks[i]["name"], "phase": tasks[i]["phase"],
        "resource": tasks[i]["resource"],
        "startDate": (start + timedelta(days=es[i])).isoformat(),
        "endDate": (start + timedelta(days=ef[i] - 1)).isoformat(),
        "durationDays": tasks[i]["durationDays"],
        "dependsOn": tasks[i]["dependsOn"],
        "slackDays": ls[i] - es[i],
        "isCritical": ls[i] == es[i],
    } for i in sorted(tasks, key=lambda i: (es[i], listing.index(i)))]

    schedule_summary = {
        "startDate": project["startDate"],
        "finishDate": finish.isoformat(),
        "deadline": project["deadline"],
        "durationDays": total_days,
        "daysAvailable": (deadline - start).days + 1,
        "withinDeadline": finish <= deadline,
        "criticalPath": critical,
    }

    # ---- Cost ----
    base = sum(t["cost"] for t in tasks.values())
    contingency = base * CONTINGENCY_RATE
    total = base + contingency
    by_phase = {}
    for t in tasks.values():
        by_phase[t["phase"]] = by_phase.get(t["phase"], 0) + t["cost"]
    cost_estimate = {
        "baseCost": _num(base),
        "contingencyRate": CONTINGENCY_RATE,
        "contingency": _num(contingency),
        "total": _num(total),
        "budget": project["budget"],
        "currency": project["currency"],
        "variance": _num(project["budget"] - total),
        "withinBudget": total <= project["budget"],
        "byPhase": [{"phase": k, "cost": _num(v)} for k, v in by_phase.items()],
    }

    # ---- Resource plan (peak concurrent tasks per role) ----
    resource_plan = []
    for r in project["resources"]:
        mine = [i for i in listing if tasks[i]["resource"] == r["role"]]
        load = [0] * total_days
        for i in mine:
            for d in range(es[i], ef[i]):
                load[d] += 1
        peak = max(load, default=0)
        days = sum(tasks[i]["durationDays"] for i in mine)
        resource_plan.append({
            "role": r["role"], "count": r["count"], "costPerDay": r["costPerDay"],
            "assignedTasks": mine, "totalDays": days,
            "peakConcurrentTasks": peak, "overallocated": peak > r["count"],
            "utilizationPercent": round(100 * days / (r["count"] * total_days)),
        })

    warnings = []
    if not schedule_summary["withinDeadline"]:
        late = (finish - deadline).days
        warnings.append(f"Plan finishes {late} day(s) after the deadline.")
    if not cost_estimate["withinBudget"]:
        warnings.append("Estimated cost (with contingency) is above the budget.")
    for r in resource_plan:
        if r["overallocated"]:
            warnings.append(f"{r['role']}: up to {r['peakConcurrentTasks']} tasks run at once but only {r['count']} available.")

    return {
        "wbs": wbs_out,
        "schedule": schedule,
        "scheduleSummary": schedule_summary,
        "costEstimate": cost_estimate,
        "resourcePlan": resource_plan,
        "workflow": workflow,
        "warnings": warnings,
    }
