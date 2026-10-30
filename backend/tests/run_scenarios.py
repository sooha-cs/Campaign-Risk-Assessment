"""LIVE check (needs the server running and a real Groq key):  python tests/run_scenarios.py [base_url]
Runs the 3 scenarios through /api/plan and /api/analyze, checks the acceptance list, saves the real responses."""
import json
import os
import sys
import time

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from checks import check_analysis  # noqa: E402

BASE = (sys.argv[1] if len(sys.argv) > 1 else os.getenv("API_URL", "http://127.0.0.1:5000")).rstrip("/")
SCENARIOS = ["scenario_ontrack", "scenario_overbudget", "scenario_delayed"]


def post(path, body):
    t = time.time()
    r = requests.post(BASE + path, json=body, timeout=180)
    if r.status_code == 502 and "rate limit" in r.text.lower():
        print("   Groq per-minute limit hit; waiting 65 s and retrying once...")
        time.sleep(65)
        t = time.time()
        r = requests.post(BASE + path, json=body, timeout=180)
    return r, round(time.time() - t, 1)


failed = False
for name in SCENARIOS:
    print(f"\n=== {name} ===")
    with open(os.path.join(ROOT, "samples", name + ".json"), encoding="utf-8") as f:
        project = json.load(f)
    r1, t1 = post("/api/plan", project)
    print(f"/api/plan     status {r1.status_code} in {t1}s")
    if r1.status_code != 200:
        print("  ", r1.text[:400]); failed = True; continue
    plan = r1.json()
    for w in plan.get("warnings", []):
        print("   plan warning:", w)
    r2, t2 = post("/api/analyze", {"project": project, "plan": plan})
    print(f"/api/analyze  status {r2.status_code} in {t2}s")
    if r2.status_code != 200:
        print("  ", r2.text[:400]); failed = True; continue
    result = r2.json()
    for r in result["risks"]:
        print(f"  #{r['id']} {r['category']:<8} P{r['probability']} x I{r['impact']} = {r['score']:>2} {r['level']:<8} {r['description'][:70]}")
    problems = check_analysis(result, project)
    print("  CHECKS:", "all passed" if not problems else "")
    for p in problems:
        print("   -", p); failed = True
    with open(os.path.join(ROOT, "samples", f"output_{name}_plan.json"), "w", encoding="utf-8") as f:
        json.dump(plan, f, indent=2)
    with open(os.path.join(ROOT, "samples", f"output_{name}_analyze.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

print("\nRESULT:", "PROBLEMS FOUND" if failed else "all scenarios passed")
sys.exit(1 if failed else 0)
