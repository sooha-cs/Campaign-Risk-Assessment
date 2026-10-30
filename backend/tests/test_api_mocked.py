"""Runs /api/plan and /api/analyze end to end for the 3 scenarios with the AI mocked (no API key needed)."""
import json
import os
import sys
import unittest
from unittest.mock import patch
import ai_service

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

import app as app_module  # noqa: E402
from checks import check_analysis  # noqa: E402

SCENARIOS = ["scenario_ontrack", "scenario_overbudget", "scenario_delayed"]


def load(name):
    with open(os.path.join(ROOT, "samples", name + ".json"), encoding="utf-8") as f:
        return json.load(f)


def fake_plan(project):
    roles = [r["role"] for r in project["resources"]]
    phases = [("Planning", 3), ("Creative", 3), ("Build", 3), ("Launch", 3), ("Closure", 2)]
    wbs, n, prev = [], 0, None
    for p_idx, (name, count) in enumerate(phases, 1):
        tasks = []
        for t in range(1, count + 1):
            tid = f"{p_idx}.{t}"
            deps = [prev] if prev and t == 1 else ([f"{p_idx}.{t - 1}"] if t > 1 and t % 2 == 0 else ([prev] if prev else []))
            tasks.append({"id": tid, "name": f"{name} task {t}", "durationDays": 2 + (n % 4),
                          "dependsOn": deps, "resource": roles[n % len(roles)]})
            n += 1
        prev = f"{p_idx}.{count}"
        wbs.append({"id": str(p_idx), "name": name, "tasks": tasks})
    workflow = [{"step": i, "name": s, "description": s, "owner": "Project Manager"}
                for i, s in enumerate(["Initiation", "Planning", "Execution", "Launch", "Closure"], 1)]
    return {"wbs": wbs, "workflow": workflow}


def fake_risks(project):
    r0 = project["resources"][0]["role"]
    return {"risks": [
        {"key": "time-critical-path", "category": "Time", "description": "Task 3.2 is on the critical path with 0 slack, so any delay moves the deadline.",
         "probability": 4, "impact": 4, "mitigation": ["Start 3.2 early", "Add a second person"], "owner": r0},
        {"key": "cost-contingency", "category": "Cost", "description": "Past projects overran cost by 15% on average, which exceeds the 10% contingency.",
         "probability": 3, "impact": 4, "mitigation": ["Review spend weekly", "Cap ad spend"], "owner": "Project Manager"},
        {"key": "resource-overload", "category": "Resource", "description": f"The {r0} is assigned tasks 1.1 and 4.1 close together.",
         "probability": 3, "impact": 3, "mitigation": ["Stagger the work", "Borrow a colleague"], "owner": r0},
        {"key": "scope-deliverables", "category": "Scope", "description": "Four deliverables may grow during approval in week 3.",
         "probability": 3, "impact": 3, "mitigation": ["Freeze scope", "Change-request process"], "owner": "Project Manager"},
        {"key": "quality-testing", "category": "Quality", "description": "Only 3 days are planned for review before launch task 4.2.",
         "probability": 2, "impact": 4, "mitigation": ["Add a checklist", "Review earlier"], "owner": "Project Manager"},
        {"key": "time-approval", "category": "Time", "description": "Creative approval in task 2.2 can slip by 2 days.",
         "probability": 2, "impact": 3, "mitigation": ["Set an approval deadline", "Brief a backup"], "owner": "Project Manager"},
        {"key": "cost-ads", "category": "Cost", "description": "Paid ads in task 4.1 could spend 20% above the plan.",
         "probability": 3, "impact": 2, "mitigation": ["Daily spend cap", "Shift to best channel"], "owner": "Project Manager"},
    ]}


def fake_groq(messages, json_mode=False, temperature=0.2):
    system, user = messages[0]["content"], messages[1]["content"]
    payload = json.loads(user[user.index("{"):].split("\n\nYour previous answer")[0])
    project = payload["project"]
    return json.dumps(fake_plan(project) if "Work Breakdown" in system else fake_risks(project))


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.client = app_module.app.test_client()
        ai_service.cache_clear()
        p = patch("ai_service.call_groq", side_effect=fake_groq)
        p.start()
        self.addCleanup(p.stop)

    def test_scenarios_meet_acceptance_list(self):
        for name in SCENARIOS:
            with self.subTest(name):
                project = load(name)
                r1 = self.client.post("/api/plan", json=project)
                self.assertEqual(r1.status_code, 200, r1.get_data(as_text=True))
                plan = r1.get_json()
                for k in ("wbs", "schedule", "scheduleSummary", "costEstimate", "resourcePlan", "workflow", "warnings"):
                    self.assertIn(k, plan)
                r2 = self.client.post("/api/analyze", json={"project": project, "plan": plan})
                self.assertEqual(r2.status_code, 200, r2.get_data(as_text=True))
                self.assertEqual(check_analysis(r2.get_json(), project), [])

    def test_analyze_without_plan_returns_plan(self):
        project = load("scenario_ontrack")
        r = self.client.post("/api/analyze", json={"project": project})
        self.assertEqual(r.status_code, 200)
        self.assertIn("plan", r.get_json())

    def test_bad_input_gives_400(self):
        bad = load("scenario_ontrack")
        bad["deadline"] = "2026-01-01"
        r = self.client.post("/api/plan", json=bad)
        self.assertEqual(r.status_code, 400)
        self.assertIn("details", r.get_json())
        self.assertEqual(self.client.post("/api/analyze", data="nope").status_code, 400)

    def test_ai_failure_gives_502(self):
        with patch("ai_service.call_groq", return_value="not json at all"):
            r = self.client.post("/api/plan", json=load("scenario_ontrack"))
        self.assertEqual(r.status_code, 502)


if __name__ == "__main__":
    unittest.main()
