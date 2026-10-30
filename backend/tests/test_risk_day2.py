"""Day 2 offline tests (no API key). Run: python -m unittest discover tests -v"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import risk
import prompts
from errors import AIOutputError

ROLES = ["Project Manager", "Developer"]


def sig(**kw):
    base = {"daysAvailable": 30, "bufferDays": 8, "withinDeadline": True, "budgetUtilizationPercent": 80,
            "overallocatedRoles": [], "pastAvgCostOverrunPercent": None, "pastAvgDelayPercent": None,
            "criticalTasks": ["1.1"], "totalTasks": 10}
    base.update(kw)
    return base


def mk(cat, desc, p=3, i=3, owner="Developer", mit=("Do A", "Do B")):
    return {"category": cat, "description": desc, "probability": p, "impact": i,
            "mitigation": list(mit), "owner": owner}


def six():
    return {"risks": [
        mk("Time", "Task 2.1 slips because the Developer is sick, delaying the release"),
        mk("Cost", "Cloud hosting fees rise above the planned INR 5000 in the build phase"),
        mk("Resource", "Only one Developer is available during testing in week four"),
        mk("Scope", "Client adds a reporting module after task 3.2 starts"),
        mk("Quality", "Insufficient test coverage on payment task 4.2 allows defects through"),
        mk("Cost", "Licence renewal for design tools arrives mid project at a 20% higher price"),
    ]}


class RiskDay2(unittest.TestCase):
    def test_backward_compatible_call(self):
        out = risk.finalize_risks({"risks": [mk("Time", "x slips", 4, 4)]})
        self.assertEqual(out["risks"][0]["score"], 16)
        self.assertEqual(out["risks"][0]["level"], "Critical")

    def test_probability_raised_when_plan_is_late(self):
        s = sig(withinDeadline=False, bufferDays=-3)
        data = {"risks": [mk("Time", "Critical task 1.1 overruns", 2, 4)]}
        r = risk.finalize_risks(data, ROLES, s)["risks"][0]
        self.assertEqual(r["probability"], 4)
        self.assertIn("ratingNote", r)

    def test_probability_capped_when_buffer_is_large(self):
        s = sig(bufferDays=15)
        r = risk.finalize_risks({"risks": [mk("Time", "Task 1.1 overruns", 5, 3)]}, ROLES, s)["risks"][0]
        self.assertEqual(r["probability"], 3)

    def test_floor_beats_cap(self):
        b = risk.calibration_bounds(sig(budgetUtilizationPercent=120, pastAvgCostOverrunPercent=0))
        self.assertGreaterEqual(b["Cost"]["min"], 4)

    def test_unknown_owner_becomes_pm(self):
        r = risk.finalize_risks({"risks": [mk("Time", "Task slips", owner="Wizard")]}, ROLES)["risks"][0]
        self.assertEqual(r["owner"], "Project Manager")
        r = risk.finalize_risks({"risks": [mk("Time", "Task slips", owner="developer")]}, ROLES)["risks"][0]
        self.assertEqual(r["owner"], "Developer")

    def test_duplicates_removed(self):
        d = {"risks": [mk("Time", "Task 2.1 slips because the Developer is sick"),
                       mk("Time", "Task 2.1 slips because the Developer is sick!"),
                       mk("Cost", "Hosting fees rise")]}
        self.assertEqual(risk.finalize_risks(d)["summary"]["total"], 2)

    def test_strict_accepts_good_answer(self):
        out = risk.finalize_risks(six(), ROLES, sig(), strict=True)
        self.assertEqual(out["summary"]["total"], 6)
        self.assertEqual([r["id"] for r in out["risks"]], list(range(1, 7)))

    def test_strict_rejects_too_few(self):
        with self.assertRaises(AIOutputError):
            risk.finalize_risks({"risks": six()["risks"][:2]}, ROLES, sig(), strict=True)

    def test_strict_requires_cost_risk_when_over_budget(self):
        d = six()
        d["risks"] = [r for r in d["risks"] if r["category"] != "Cost"] + [mk("Scope", "Extra feature 4.1 requested")]
        with self.assertRaises(AIOutputError) as cm:
            risk.finalize_risks(d, ROLES, sig(budgetUtilizationPercent=110), strict=True)
        self.assertIn("Cost", "; ".join(cm.exception.errors))

    def test_strict_rejects_single_mitigation(self):
        d = six()
        d["risks"][0]["mitigation"] = ["Only one"]
        with self.assertRaises(AIOutputError):
            risk.finalize_risks(d, ROLES, sig(), strict=True)

    def test_drivers_and_prompt(self):
        plan = {"resourcePlan": [{"role": "Developer", "count": 1, "utilizationPercent": 90}],
                "costEstimate": {"byPhase": [{"phase": "Build", "cost": 700}, {"phase": "Plan", "cost": 300}]},
                "warnings": ["Plan finishes 3 day(s) after the deadline."]}
        project = {"pastProjects": [{}], "resources": [{"role": "Developer"}]}
        s = sig(bufferDays=-3, overallocatedRoles=["Developer"], pastAvgCostOverrunPercent=12, pastAvgDelayPercent=9)
        facts = risk.compute_drivers(project, plan, s)
        text = " ".join(facts)
        self.assertIn("LONGER", text)
        self.assertIn("Build", text)
        self.assertIn("over-allocated", text)
        msg = prompts.risk_user_message(project, {"schedule": []}, s, facts, ["Developer"])
        self.assertIn("allowedOwners", msg)
        self.assertIn("keyFacts", msg)


if __name__ == "__main__":
    unittest.main()
