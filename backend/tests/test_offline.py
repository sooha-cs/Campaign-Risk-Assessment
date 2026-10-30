"""Offline tests: the AI is mocked, so no API key or internet is needed.
Run from the backend folder:  python -m unittest discover tests -v
"""
import copy
import json
import pathlib
import sys
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import ai_service  # noqa: E402
from app import app  # noqa: E402

PROJECT = json.loads((ROOT / "samples" / "sample_project.json").read_text())


def T(tid, name, dur, deps, res):
    return {"id": tid, "name": name, "durationDays": dur, "dependsOn": deps, "resource": res}


GOOD_PLAN = {
    "wbs": [
        {"id": "1", "name": "Planning", "tasks": [
            T("1.1", "Gather requirements", 3, [], "Project Manager"),
            T("1.2", "Define scope and plan", 2, ["1.1"], "Project Manager")]},
        {"id": "2", "name": "Design", "tasks": [
            T("2.1", "UI/UX design", 4, ["1.2"], "Developer"),
            T("2.2", "Database design", 3, ["1.2"], "Developer"),
            T("2.3", "Design review", 1, ["2.1", "2.2"], "Project Manager")]},
        {"id": "3", "name": "Development", "tasks": [
            T("3.1", "Backend development", 8, ["2.3"], "Developer"),
            T("3.2", "Frontend development", 7, ["2.3"], "Developer"),
            T("3.3", "Integration", 3, ["3.1", "3.2"], "Developer")]},
        {"id": "4", "name": "Testing", "tasks": [
            T("4.1", "Write test cases", 3, ["2.3"], "Tester"),
            T("4.2", "System testing", 4, ["3.3", "4.1"], "Tester"),
            T("4.3", "Bug fixing", 3, ["4.2"], "Developer")]},
        {"id": "5", "name": "Deployment", "tasks": [
            T("5.1", "Write user manual", 2, ["3.3"], "Project Manager"),
            T("5.2", "Deploy and handover", 2, ["4.3", "5.1"], "Developer")]},
    ],
    "workflow": [
        {"step": 1, "name": "Initiation", "description": "Agree goals and scope", "owner": "Project Manager"},
        {"step": 2, "name": "Planning", "description": "Build WBS, schedule, budget", "owner": "Project Manager"},
        {"step": 3, "name": "Design", "description": "Design UI and database", "owner": "Developer"},
        {"step": 4, "name": "Development", "description": "Build backend and frontend", "owner": "Developer"},
        {"step": 5, "name": "Testing", "description": "Test and fix defects", "owner": "Tester"},
        {"step": 6, "name": "Closure", "description": "Deploy, hand over, review lessons", "owner": "Project Manager"},
    ],
}

GOOD_RISKS = {"risks": [
    {"category": "Time", "description": "Only 2 days of buffer before the deadline; critical path 1.1 to 5.2 has no slack.",
     "probability": 4, "impact": 4, "score": 3, "level": "Low",  # wrong on purpose: server must recalculate
     "mitigation": ["Add a 3-day buffer", "Start test-case writing early"], "owner": "Project Manager"},
    {"category": "cost", "description": "Past project overspent by 30%; contingency is only 10%.",
     "probability": 3, "impact": 4, "mitigation": ["Review spend weekly", "Raise contingency to 15%"], "owner": "Project Manager"},
    {"category": "Resource", "description": "Two developers carry 30 of 45 person-days; one absence delays integration.",
     "probability": 3, "impact": 3, "mitigation": ["Cross-train a second developer", "Plan leave around integration week"], "owner": "Developer"},
    {"category": "Quality", "description": "Only 4 days for system testing may miss defects.",
     "probability": 2, "impact": 4, "mitigation": ["Automate smoke tests", "Test during development"], "owner": "Tester"},
    {"category": "Scope", "description": "Library staff may add features after design review task 2.3.",
     "probability": 3, "impact": 2, "mitigation": ["Freeze scope after design review", "Use a change request log"], "owner": "Project Manager"},
    {"category": "Time", "description": "Late approval of design review task 2.3 would shift all 3 development tasks.",
     "probability": 2, "impact": 3, "mitigation": ["Book reviewer in advance", "Name a backup approver"], "owner": "Project Manager"},
]}


def fake_ai(*replies):
    """Mock call_groq to return the given replies in order (dicts are turned into JSON)."""
    items = [r if isinstance(r, str) else json.dumps(r) for r in replies]
    return mock.patch.object(ai_service, "call_groq", side_effect=items)


class PlanTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        ai_service.cache_clear()

    def test_plan_calculations(self):
        with fake_ai(GOOD_PLAN):
            r = self.client.post("/api/plan", json=PROJECT)
        self.assertEqual(r.status_code, 200)
        plan = r.get_json()
        s = plan["scheduleSummary"]
        self.assertEqual(s["durationDays"], 30)
        self.assertEqual(s["finishDate"], "2026-11-10")
        self.assertTrue(s["withinDeadline"])
        self.assertEqual(s["criticalPath"], ["1.1", "1.2", "2.1", "2.3", "3.1", "3.3", "4.2", "4.3", "5.2"])
        c = plan["costEstimate"]
        self.assertEqual(c["baseCost"], 68000)   # PM 8d*2000 + Dev 30d*1500 + Tester 7d*1000
        self.assertEqual(c["total"], 74800)      # +10% contingency
        self.assertTrue(c["withinBudget"])
        dev = next(x for x in plan["resourcePlan"] if x["role"] == "Developer")
        self.assertEqual(dev["totalDays"], 30)
        self.assertFalse(dev["overallocated"])
        (ROOT / "samples" / "example_plan_response.json").write_text(json.dumps(plan, indent=2))

    def test_retry_after_bad_json_and_bad_role(self):
        bad_role = copy.deepcopy(GOOD_PLAN)
        bad_role["wbs"][0]["tasks"][0]["resource"] = "Wizard"
        with fake_ai("this is not json {", bad_role, GOOD_PLAN) as m:
            r = self.client.post("/api/plan", json=PROJECT)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(m.call_count, 3)

    def test_circular_dependency_is_rejected(self):
        loop = copy.deepcopy(GOOD_PLAN)
        loop["wbs"][0]["tasks"][0]["dependsOn"] = ["5.2"]
        with fake_ai(loop, loop, loop):
            r = self.client.post("/api/plan", json=PROJECT)
        self.assertEqual(r.status_code, 502)

    def test_invalid_input_returns_400(self):
        bad = copy.deepcopy(PROJECT)
        bad["budget"] = -5
        bad["deadline"] = "2026-10-01"
        r = self.client.post("/api/plan", json=bad)
        self.assertEqual(r.status_code, 400)
        self.assertGreaterEqual(len(r.get_json()["details"]), 2)
        self.assertEqual(self.client.post("/api/plan", data="nope").status_code, 400)


class AnalyzeTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        ai_service.cache_clear()

    def test_analyze_scores_are_recalculated(self):
        with fake_ai(GOOD_PLAN):
            plan = self.client.post("/api/plan", json=PROJECT).get_json()
        with fake_ai(GOOD_RISKS):
            r = self.client.post("/api/analyze", json={"project": PROJECT, "plan": plan})
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        top = data["risks"][0]
        self.assertEqual((top["score"], top["level"]), (16, "Critical"))  # AI said 3/Low, code fixed it
        self.assertEqual([x["id"] for x in data["risks"]], [1, 2, 3, 4, 5, 6])
        scores = [x["score"] for x in data["risks"]]
        self.assertEqual(scores, sorted(scores, reverse=True))
        self.assertEqual(data["risks"][1]["category"], "Cost")  # "cost" normalised
        self.assertEqual(data["summary"]["total"], 6)
        (ROOT / "samples" / "example_analyze_response.json").write_text(json.dumps(data, indent=2))

    def test_analyze_without_plan_generates_one(self):
        with fake_ai(GOOD_PLAN, GOOD_RISKS):
            r = self.client.post("/api/analyze", json={"project": PROJECT})
        self.assertEqual(r.status_code, 200)
        self.assertIn("plan", r.get_json())

    def test_bad_risk_output_is_retried(self):
        bad = {"risks": [{"category": "Weather", "description": "x", "probability": "high",
                          "impact": 3, "mitigation": []}]}
        with fake_ai(bad, GOOD_RISKS) as m:
            with fake_ai(GOOD_PLAN):
                plan = self.client.post("/api/plan", json=PROJECT).get_json()
            r = self.client.post("/api/analyze", json={"project": PROJECT, "plan": plan})
        self.assertEqual(r.status_code, 200)

    def test_missing_project_returns_400(self):
        self.assertEqual(self.client.post("/api/analyze", json={}).status_code, 400)


if __name__ == "__main__":
    unittest.main()
