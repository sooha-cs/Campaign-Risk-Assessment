"""Plan -> analyze -> update -> history through the real routes and Person 3's monitoring.py, AI mocked."""
import os
import sys
import tempfile
import unittest
from unittest.mock import patch
import ai_service

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

import app as app_module  # noqa: E402
from checks import check_analysis  # noqa: E402
from test_api_mocked import fake_groq, load  # noqa: E402


class MonitoringIntegration(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        ai_service.cache_clear()
        patch.dict(os.environ, {"CAMPAIGNRISK_DB": os.path.join(self.tmp.name, "t.db")}).start()
        patch("ai_service.call_groq", side_effect=fake_groq).start()
        self.addCleanup(patch.stopall)
        self.addCleanup(self.tmp.cleanup)
        self.c = app_module.app.test_client()
        self.project = load("scenario_ontrack")
        self.plan = self.c.post("/api/plan", json=self.project).get_json()
        self.base = self.c.post("/api/analyze", json={"project": self.project, "plan": self.plan}).get_json()

    def test_analyze_returns_project_id_and_valid_risks(self):
        self.assertEqual(self.base["projectId"], "diwali-festive-email-campaign")
        self.assertEqual(check_analysis(self.base, self.project), [])

    def test_update_without_ai_then_history(self):
        pid = self.base["projectId"]
        body = {"projectId": pid, "project": self.project, "plan": self.plan, "risks": self.base, "reanalyze": False,
                "progress": {"asOfDate": "2026-10-25", "actualCostToDate": 90000,
                             "tasks": [{"taskId": "1.1", "percentComplete": 100}]}}
        r = self.c.post("/api/update", json=body)
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        m = r.get_json()["metrics"]
        for k in ("health", "spi", "cpi", "forecastFinish", "forecastCost", "scheduleDelayDays"):
            self.assertIn(k, m)
        h = self.c.get(f"/api/history?projectId={pid}&full=true").get_json()
        self.assertEqual(h["count"], 1)
        self.assertEqual(len(h["trend"]["dates"]), 1)

    def test_update_with_reanalyze_uses_ai_and_validates(self):
        pid = self.base["projectId"]
        first = {"projectId": pid, "project": self.project, "plan": self.plan, "risks": self.base, "reanalyze": False,
                 "progress": {"asOfDate": "2026-10-20", "actualCostToDate": 20000, "tasks": []}}
        self.assertEqual(self.c.post("/api/update", json=first).status_code, 200)
        second = {"projectId": pid, "progress": {"asOfDate": "2026-11-10", "actualCostToDate": 900000,
                  "tasks": [{"taskId": "1.1", "percentComplete": 20}]}}
        r = self.c.post("/api/update", json=second)
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        data = r.get_json()
        self.assertTrue(data["reanalyzed"])
        self.assertEqual(check_analysis({"risks": data["risks"]}, self.project), [])
        self.assertEqual(len(self.c.get(f"/api/history?projectId={pid}").get_json()["trend"]["dates"]), 2)

    def test_errors(self):
        self.assertEqual(self.c.get("/api/history?projectId=nope").status_code, 404)
        r = self.c.post("/api/update", json={"projectId": "nope", "progress": {}})
        self.assertEqual(r.status_code, 404)
        r = self.c.post("/api/update", json={"projectId": self.base["projectId"], "project": self.project,
                                             "plan": self.plan, "progress": {"asOfDate": "bad", "actualCostToDate": -5}})
        self.assertEqual(r.status_code, 400)
        self.assertIn("details", r.get_json())
        self.assertEqual(self.c.get("/api/history?limit=0").status_code, 400)


if __name__ == "__main__":
    unittest.main()
