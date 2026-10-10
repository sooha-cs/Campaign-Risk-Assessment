"""Project monitoring: progress updates, health checks and history.

What this file does
-------------------
* apply_update()   -> POST /api/update   saves a progress snapshot and checks project health
* get_history()    -> GET  /api/history  returns the saved snapshots (and trend lists for charts)

The health numbers are calculated HERE in code (earned value method), never by the AI,
so they are always consistent. The AI is only used, if asked, to re-score the risks with the
new progress numbers. Pass "reanalyze": false to skip the AI and use no tokens.

Storage: a small SQLite file (data/campaignrisk.db). Override with the CAMPAIGNRISK_DB variable.
Assumptions: calendar days, task cost is spread evenly over the task's duration.
"""
import copy
import json
import math
import os
import pathlib
import re
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone

import ai_service
import risk
from errors import NotFoundError, ValidationError
from validators import validate_project

ROOT = pathlib.Path(__file__).resolve().parent
RISE_ALERT = 3          # alert when a risk category score rises by this much or more
BEHIND_POINTS = 10      # a task is "behind" when it is this many percentage points under plan


# ---------------------------------------------------------------- storage
def _db():
    path = pathlib.Path(os.getenv("CAMPAIGNRISK_DB") or ROOT / "data" / "campaignrisk.db")
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.execute("""CREATE TABLE IF NOT EXISTS projects (
        project_id TEXT PRIMARY KEY, name TEXT, project TEXT, plan TEXT, updated_at TEXT)""")
    con.execute("""CREATE TABLE IF NOT EXISTS snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT, created_at TEXT,
        as_of TEXT, data TEXT)""")
    con.execute("CREATE INDEX IF NOT EXISTS idx_snap_project ON snapshots(project_id, id)")
    return con


@contextmanager
def _session():
    """Opens the database, commits on success, and ALWAYS closes it (Windows cannot delete an open file)."""
    con = _db()
    try:
        with con:
            yield con
    finally:
        con.close()


def _slug(text):
    slug = re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")
    return slug or "project"


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------- small helpers
def _isnum(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _clamp(x, lo, hi):
    return max(lo, min(hi, x))


def _round(x, nd=2):
    return None if x is None else round(x, nd)


def _date(text, field):
    try:
        return date.fromisoformat(str(text))
    except ValueError:
        raise ValidationError(f"{field} must be a date in YYYY-MM-DD format")


# ---------------------------------------------------------------- validation
def validate_progress(progress, plan, previous_tasks, start, last_as_of):
    """Checks the progress object and returns (asOfDate, actualCost, {taskId: percent}).
    Tasks that are not listed keep their percent from the previous update (0 at first)."""
    if not isinstance(progress, dict):
        raise ValidationError("progress must be an object: {asOfDate, actualCostToDate, tasks}")
    errs = []
    as_of = None
    try:
        as_of = date.fromisoformat(str(progress.get("asOfDate")))
    except ValueError:
        errs.append("progress.asOfDate must be a date in YYYY-MM-DD format")
    if as_of and as_of < start:
        errs.append("progress.asOfDate cannot be before the project start date")
    if as_of and last_as_of and as_of < last_as_of:
        errs.append(f"progress.asOfDate cannot be earlier than the last update ({last_as_of.isoformat()})")

    cost = progress.get("actualCostToDate")
    if not _isnum(cost) or cost < 0:
        errs.append("progress.actualCostToDate must be a number >= 0 (money spent so far)")

    known = {t["taskId"] for t in plan["schedule"]}
    tasks = dict(previous_tasks)
    raw = progress.get("tasks", [])
    if not isinstance(raw, list):
        errs.append("progress.tasks must be a list of {taskId, percentComplete}")
        raw = []
    for n, t in enumerate(raw, 1):
        tid = str(t.get("taskId", "")).strip() if isinstance(t, dict) else ""
        pct = t.get("percentComplete") if isinstance(t, dict) else None
        if tid not in known:
            errs.append(f"progress.tasks[{n}]: unknown taskId '{tid}'")
        elif not _isnum(pct) or not 0 <= pct <= 100:
            errs.append(f"progress.tasks[{n}]: percentComplete must be a number from 0 to 100")
        else:
            tasks[tid] = pct
    if errs:
        raise ValidationError(errs)
    return as_of, cost, {tid: tasks.get(tid, 0) for tid in sorted(known)}


def _check_plan(plan):
    needed = ("schedule", "scheduleSummary", "costEstimate", "wbs")
    if not isinstance(plan, dict) or any(not plan.get(k) for k in needed):
        raise ValidationError("plan must be the JSON returned by /api/plan")
    return plan


# ---------------------------------------------------------------- the health numbers
def compute_metrics(project, plan, task_pct, as_of, actual_cost):
    """Earned value numbers, delay forecast, cost forecast and health status."""
    cost_of = {t["id"]: t.get("estimatedCost", 0) for ph in plan["wbs"] for t in ph["tasks"]}
    bac = sum(cost_of.values())
    if bac <= 0:
        raise ValidationError("the plan has no task costs, so progress cannot be measured")

    pv = ev = 0.0
    delay = 0.0
    behind = []
    for t in plan["schedule"]:
        tid, dur = t["taskId"], t["durationDays"]
        start = date.fromisoformat(t["startDate"])
        planned = _clamp(((as_of - start).days + 1) / dur, 0, 1)
        actual = _clamp(task_pct.get(tid, 0) / 100, 0, 1)
        pv += cost_of.get(tid, 0) * planned
        ev += cost_of.get(tid, 0) * actual
        late_days = max(0.0, planned - actual) * dur           # how many days behind plan
        delay = max(delay, late_days - t["slackDays"])         # slack absorbs part of the delay
        if (planned - actual) * 100 >= BEHIND_POINTS:
            behind.append(tid)
    delay_days = max(0, math.ceil(delay - 1e-9))

    spi = ev / pv if pv > 0 else None
    cpi = ev / actual_cost if actual_cost > 0 else None
    forecast_cost = actual_cost + (bac - ev) / cpi if cpi else actual_cost + (bac - ev)

    summary = plan["scheduleSummary"]
    planned_finish = date.fromisoformat(summary["finishDate"])
    forecast_finish = planned_finish + timedelta(days=delay_days)
    deadline = date.fromisoformat(project["deadline"])
    late = (forecast_finish - deadline).days
    over_budget = forecast_cost > project["budget"]

    alerts = []
    if late > 0:
        alerts.append(f"Forecast finish {forecast_finish.isoformat()} is {late} day(s) after the deadline.")
    if over_budget:
        alerts.append(f"Forecast cost {round(forecast_cost)} is above the budget {project['budget']}.")
    if cpi is not None and cpi < 0.95:
        alerts.append(f"CPI is {cpi:.2f}: money is being spent faster than work is completed.")
    if spi is not None and spi < 0.95:
        alerts.append(f"SPI is {spi:.2f}: the project is behind schedule.")
    if behind:
        alerts.append(f"Tasks behind plan: {', '.join(behind)}.")

    if late > 0 or over_budget or (spi is not None and spi < 0.8) or (cpi is not None and cpi < 0.8):
        health = "Off Track"
    elif (spi is not None and spi < 0.95) or (cpi is not None and cpi < 0.95):
        health = "At Risk"
    else:
        health = "On Track"

    return {
        "health": health,
        "percentComplete": _round(100 * ev / bac, 1),
        "plannedPercent": _round(100 * pv / bac, 1),
        "plannedValue": round(pv), "earnedValue": round(ev), "actualCost": actual_cost,
        "spi": _round(spi), "cpi": _round(cpi),
        "scheduleDelayDays": delay_days,
        "plannedFinish": planned_finish.isoformat(),
        "forecastFinish": forecast_finish.isoformat(),
        "deadline": project["deadline"],
        "forecastCost": round(forecast_cost),
        "budget": project["budget"],
        "forecastOverBudget": over_budget,
        "behindTasks": behind,
        "alerts": alerts,
    }


def _forecast_plan(plan, metrics, contingency_rate):
    """A copy of the plan with the forecast finish and cost, so the risk analysis sees today's reality."""
    adjusted = copy.deepcopy(plan)
    start = date.fromisoformat(plan["scheduleSummary"]["startDate"])
    finish = date.fromisoformat(metrics["forecastFinish"])
    deadline = date.fromisoformat(metrics["deadline"])
    adjusted["scheduleSummary"].update({
        "finishDate": finish.isoformat(),
        "durationDays": (finish - start).days + 1,
        "withinDeadline": finish <= deadline,
    })
    total = round(metrics["forecastCost"] * (1 + contingency_rate))
    adjusted["costEstimate"].update({
        "total": total, "variance": metrics["budget"] - total, "withinBudget": total <= metrics["budget"],
    })
    return adjusted


# ---------------------------------------------------------------- risk comparison
def _by_category(risks):
    out = {}
    for r in risks or []:
        if r["category"] not in out or r["score"] > out[r["category"]]["score"]:
            out[r["category"]] = r
    return out


def compare_risks(previous, current):
    """Per category (highest score): which risks are new, which rose by +3 or more, which fell."""
    before, after = _by_category(previous), _by_category(current)
    changes = {"newRisks": [], "increased": [], "decreased": []}
    for cat, r in after.items():
        old = before.get(cat)
        if old is None:
            if previous:
                changes["newRisks"].append({"category": cat, "score": r["score"], "level": r["level"]})
        elif r["score"] - old["score"] >= RISE_ALERT:
            changes["increased"].append({"category": cat, "from": old["score"], "to": r["score"], "level": r["level"]})
        elif old["score"] - r["score"] >= RISE_ALERT:
            changes["decreased"].append({"category": cat, "from": old["score"], "to": r["score"], "level": r["level"]})
    return changes


def _risk_alerts(changes):
    alerts = [f"New {c['level']} {c['category']} risk (score {c['score']})." for c in changes["newRisks"]]
    alerts += [f"{c['category']} risk score rose from {c['from']} to {c['to']} ({c['level']})."
               for c in changes["increased"]]
    return alerts


# ---------------------------------------------------------------- POST /api/update
def apply_update(body):
    """Body: {projectId?, project?, plan?, risks?, progress, reanalyze?}.
    First update needs project and plan. Later updates only need projectId and progress."""
    if not isinstance(body, dict):
        raise ValidationError("Body must be JSON: {projectId, project, plan, progress}")
    with _session() as con:
        project, plan, project_id = _load_project(con, body)
        last = con.execute("SELECT data FROM snapshots WHERE project_id=? ORDER BY id DESC LIMIT 1",
                           (project_id,)).fetchone()
        last = json.loads(last["data"]) if last else None

        start = date.fromisoformat(project["startDate"])
        last_as_of = date.fromisoformat(last["asOfDate"]) if last else None
        as_of, cost, task_pct = validate_progress(
            body.get("progress"), plan, last["tasks"] if last else {}, start, last_as_of)

        reanalyze = body.get("reanalyze", True)
        if not isinstance(reanalyze, bool):
            raise ValidationError("reanalyze must be true or false")

        metrics = compute_metrics(project, plan, task_pct, as_of, cost)

        previous_risks = (last or {}).get("risks") or (body.get("risks") or {}).get("risks")
        risks_block, changes = (last or {}).get("riskResult"), {"newRisks": [], "increased": [], "decreased": []}
        if risks_block is None and isinstance(body.get("risks"), dict):
            risks_block = body["risks"]
        if reanalyze:
            adjusted = _forecast_plan(plan, metrics, plan["costEstimate"].get("contingencyRate", 0.1))
            extra = {"progress": {k: metrics[k] for k in (
                "health", "percentComplete", "plannedPercent", "spi", "cpi", "scheduleDelayDays",
                "forecastFinish", "forecastCost", "behindTasks")} | {"asOfDate": as_of.isoformat()}}
            risks_block = ai_service.generate_risks(project, adjusted, extra_signals=extra)
            changes = compare_risks(previous_risks, risks_block["risks"])
            metrics["alerts"] += _risk_alerts(changes)

        snapshot = {
            "asOfDate": as_of.isoformat(), "tasks": task_pct, "metrics": metrics,
            "reanalyzed": reanalyze, "riskResult": risks_block,
            "risks": (risks_block or {}).get("risks"), "changes": changes,
        }
        created = _now()
        cur = con.execute("INSERT INTO snapshots (project_id, created_at, as_of, data) VALUES (?,?,?,?)",
                          (project_id, created, as_of.isoformat(), json.dumps(snapshot)))
        con.execute("""INSERT INTO projects (project_id, name, project, plan, updated_at) VALUES (?,?,?,?,?)
                       ON CONFLICT(project_id) DO UPDATE SET name=excluded.name, project=excluded.project,
                       plan=excluded.plan, updated_at=excluded.updated_at""",
                    (project_id, project["name"], json.dumps(project), json.dumps(plan), created))

    return {
        "projectId": project_id, "snapshotId": cur.lastrowid, "createdAt": created,
        "asOfDate": snapshot["asOfDate"], "reanalyzed": reanalyze,
        "health": metrics["health"], "metrics": metrics, "changes": changes,
        "risks": (risks_block or {}).get("risks"), "summary": (risks_block or {}).get("summary"),
    }


def _load_project(con, body):
    """Uses project and plan from the body (and saves them), or the saved copy from the first update."""
    raw_project, raw_plan = body.get("project"), body.get("plan")
    pid = body.get("projectId")
    if pid is not None and (not isinstance(pid, str) or not pid.strip()):
        raise ValidationError("projectId must be a non-empty text")
    if raw_project is not None:
        project = validate_project(raw_project)
        pid = pid.strip() if pid else _slug(project["name"])
        plan = _check_plan(raw_plan) if raw_plan is not None else None
        if plan is None:
            saved = con.execute("SELECT plan FROM projects WHERE project_id=?", (pid,)).fetchone()
            if not saved:
                raise ValidationError("plan is required for the first update (use the JSON from /api/plan)")
            plan = json.loads(saved["plan"])
        return project, plan, pid
    if not pid:
        raise ValidationError("send projectId (saved project) or project and plan (first update)")
    saved = con.execute("SELECT project, plan FROM projects WHERE project_id=?", (pid,)).fetchone()
    if not saved:
        raise NotFoundError(f"project '{pid}' has no saved plan yet; send project and plan with the first update")
    return json.loads(saved["project"]), json.loads(saved["plan"]), pid


# ---------------------------------------------------------------- GET /api/history
def get_history(project_id=None, limit=None, full=False):
    """No projectId: list of saved projects. With projectId: snapshots (oldest first) plus trend lists."""
    with _session() as con:
        if not project_id:
            rows = con.execute("""SELECT p.project_id, p.name, p.updated_at,
                (SELECT COUNT(*) FROM snapshots s WHERE s.project_id = p.project_id) AS updates
                FROM projects p ORDER BY p.updated_at DESC""").fetchall()
            out = []
            for r in rows:
                last = con.execute("SELECT data FROM snapshots WHERE project_id=? ORDER BY id DESC LIMIT 1",
                                   (r["project_id"],)).fetchone()
                last = json.loads(last["data"]) if last else {}
                out.append({"projectId": r["project_id"], "name": r["name"], "updates": r["updates"],
                            "lastUpdated": r["updated_at"], "lastAsOfDate": last.get("asOfDate"),
                            "health": (last.get("metrics") or {}).get("health")})
            return {"projects": out}

        if not con.execute("SELECT 1 FROM projects WHERE project_id=?", (project_id,)).fetchone():
            raise NotFoundError(f"project '{project_id}' not found")
        query = "SELECT id, created_at, data FROM snapshots WHERE project_id=? ORDER BY id"
        rows = con.execute(query, (project_id,)).fetchall()
    if limit is not None:
        rows = rows[-limit:]

    snaps, trend = [], {"dates": [], "percentComplete": [], "plannedPercent": [], "spi": [], "cpi": [],
                        "forecastCost": [], "scheduleDelayDays": [], "highestRiskScore": []}
    for r in rows:
        d = json.loads(r["data"])
        m, risks = d["metrics"], d.get("risks") or []
        top = max((x["score"] for x in risks), default=None)
        item = {
            "snapshotId": r["id"], "createdAt": r["created_at"], "asOfDate": d["asOfDate"],
            "health": m["health"], "percentComplete": m["percentComplete"], "plannedPercent": m["plannedPercent"],
            "spi": m["spi"], "cpi": m["cpi"], "scheduleDelayDays": m["scheduleDelayDays"],
            "forecastFinish": m["forecastFinish"], "forecastCost": m["forecastCost"],
            "reanalyzed": d["reanalyzed"], "highestRiskScore": top,
            "riskSummary": (d.get("riskResult") or {}).get("summary"),
        }
        if full:
            item.update({"metrics": m, "tasks": d["tasks"], "risks": risks, "changes": d.get("changes")})
        snaps.append(item)
        trend["dates"].append(d["asOfDate"])
        for key in ("percentComplete", "plannedPercent", "spi", "cpi", "forecastCost", "scheduleDelayDays"):
            trend[key].append(m[key])
        trend["highestRiskScore"].append(top)
    return {"projectId": project_id, "count": len(snaps), "snapshots": snaps, "trend": trend}