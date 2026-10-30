"""End-to-end check of the integrated backend: plan -> analyze -> update (no AI) -> update (AI re-score) -> history.
Needs the server running.   python tests/live_flow.py [scenario_name] [base_url]
Example:  python tests/live_flow.py scenario_overbudget"""
import json
import os
import sys
import time
from datetime import date, timedelta

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from checks import check_analysis  # noqa: E402

NAME = sys.argv[1] if len(sys.argv) > 1 else "scenario_ontrack"
BASE = (sys.argv[2] if len(sys.argv) > 2 else os.getenv("API_URL", "http://127.0.0.1:5000")).rstrip("/")
failed = []


def step(title):
    print(f"\n--- {title}")


def call(method, path, **kw):
    r = requests.request(method, BASE + path, timeout=180, **kw)
    if r.status_code == 502 and "rate limit" in r.text.lower():
        print("   Groq per-minute limit hit; waiting 65 s and retrying once...")
        time.sleep(65)
        r = requests.request(method, BASE + path, timeout=180, **kw)
    ok = r.status_code == 200
    print(f"{method} {path.split('?')[0]:<14} -> {r.status_code}")
    if not ok:
        print("   ", r.text[:500])
        failed.append(f"{method} {path} returned {r.status_code}")
        return None
    return r.json()


def progress_at(plan, as_of, pace, cost_factor):
    """Builds a progress update: tasks done at `pace` x planned progress, spend = planned cost x cost_factor."""
    start = date.fromisoformat(plan["scheduleSummary"]["startDate"])
    cost = {t["id"]: t["estimatedCost"] for ph in plan["wbs"] for t in ph["tasks"]}
    tasks, planned_cost = [], 0
    for t in plan["schedule"]:
        planned = min(1, max(0, ((as_of - date.fromisoformat(t["startDate"])).days + 1) / t["durationDays"]))
        planned_cost += cost[t["taskId"]] * planned * pace
        if planned > 0:
            tasks.append({"taskId": t["taskId"], "percentComplete": round(100 * planned * pace)})
    return {"asOfDate": as_of.isoformat(), "actualCostToDate": round(planned_cost * cost_factor), "tasks": tasks}


step("health")
call("GET", "/api/health")

with open(os.path.join(ROOT, "samples", NAME + ".json"), encoding="utf-8") as f:
    project = json.load(f)
print("scenario:", NAME)

step("1. plan")
plan = call("POST", "/api/plan", json=project)
if not plan:
    sys.exit("stopped: no plan")
s, c = plan["scheduleSummary"], plan["costEstimate"]
print(f"   finish {s['finishDate']} vs deadline {s['deadline']} | cost {c['total']} vs budget {c['budget']}")
for w in plan["warnings"]:
    print("   warning:", w)

step("2. analyze")
base = call("POST", "/api/analyze", json={"project": project, "plan": plan})
if not base:
    sys.exit("stopped: no analysis")
for r in base["risks"]:
    print(f"   #{r['id']} {r['category']:<8} {r['score']:>2} {r['level']:<8} {r['description'][:70]}")
problems = check_analysis(base, project)
print("   checks:", "all passed" if not problems else problems)
failed += problems
pid = base["projectId"]
print("   projectId:", pid)

start = date.fromisoformat(project["startDate"])
step("3. update #1 (on pace, no AI)")
u1 = call("POST", "/api/update", json={"projectId": pid, "project": project, "plan": plan, "risks": base,
          "reanalyze": False, "progress": progress_at(plan, start + timedelta(days=10), 1.0, 1.0)})
if u1:
    m = u1["metrics"]
    print(f"   health {m['health']} | SPI {m['spi']} CPI {m['cpi']} | forecast finish {m['forecastFinish']}")

step("4. update #2 (behind and overspending, AI re-scores risks)")
u2 = call("POST", "/api/update", json={"projectId": pid, "reanalyze": True,
          "progress": progress_at(plan, start + timedelta(days=20), 0.5, 1.4)})
if u2:
    m = u2["metrics"]
    print(f"   health {m['health']} | SPI {m['spi']} CPI {m['cpi']} | forecast finish {m['forecastFinish']} | delay {m['scheduleDelayDays']}d")
    for a in m["alerts"]:
        print("   alert:", a)
    print("   risk changes:", json.dumps(u2["changes"]))
    print("   keys kept from first analysis:", len({r["key"] for r in base["risks"]} & {r["key"] for r in u2["risks"]}), "of", len(u2["risks"]))
    p2 = check_analysis({"risks": u2["risks"]}, project)
    print("   re-scored risks:", "all checks passed" if not p2 else p2)
    failed += p2

step("5. history")
h = call("GET", f"/api/history?projectId={pid}")
if h:
    print(f"   {h['count']} snapshots; trend dates {h['trend']['dates']}")
    print(f"   SPI trend {h['trend']['spi']} | highest risk score {h['trend']['highestRiskScore']}")
    if h["count"] != 2:
        failed.append(f"expected 2 snapshots, got {h['count']}")

print("\nRESULT:", "PROBLEMS: " + "; ".join(failed) if failed else "integration OK")
sys.exit(1 if failed else 0)
