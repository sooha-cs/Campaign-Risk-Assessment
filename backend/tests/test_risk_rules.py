"""Offline tests for the scoring and validation rules in risk.py."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import risk  # noqa: E402
from errors import AIOutputError  # noqa: E402

ROLES = ["Developer", "Project Manager", "Designer"]
SIG = {"daysAvailable": 30, "bufferDays": 2, "withinDeadline": True, "budgetUtilizationPercent": 95,
       "overallocatedRoles": [], "pastAvgDelayPercent": 15, "pastAvgCostOverrunPercent": 12}


def R(cat, desc, p, i, key=None, owner="Developer", mit=("a", "b")):
    d = {"category": cat, "description": desc, "probability": p, "impact": i, "mitigation": list(mit), "owner": owner}
    if key:
        d["key"] = key
    return d


def six():
    return [R("Time", "Task 3.2 is critical with 0 slack", 4, 4, "time-critical"),
            R("Cost", "Estimate uses 95% of the budget", 3, 3), R("Resource", "Developer holds tasks 2.1 and 2.3", 3, 3),
            R("Scope", "Deliverable 2 may expand in week 3", 3, 3), R("Quality", "Testing has only 3 days", 3, 3),
            R("Time", "Designer approval may slip", 3, 4)]


class RiskRules(unittest.TestCase):
    def fin(self, risks, **kw):
        return risk.finalize_risks({"risks": risks}, roles=ROLES, signals=SIG, strict=True, **kw)

    def test_levels(self):
        self.assertEqual([risk.level_for(s) for s in (1, 4, 5, 9, 10, 15, 16, 25)],
                         ["Low", "Low", "Medium", "Medium", "High", "High", "Critical", "Critical"])

    def test_score_level_priority_and_sorting(self):
        out = self.fin(six())["risks"]
        for r in out:
            self.assertEqual(r["score"], r["probability"] * r["impact"])
            self.assertEqual(r["level"], risk.level_for(r["score"]))
            self.assertEqual(r["priority"], risk.PRIORITY[r["level"]])
        self.assertEqual([r["score"] for r in out], sorted([r["score"] for r in out], reverse=True))

    def test_ai_cannot_set_score(self):
        data = six()
        data[0]["score"], data[0]["level"] = 1, "Low"
        top = self.fin(data)["risks"][0]
        self.assertEqual((top["score"], top["level"]), (16, "Critical"))

    def test_unknown_owner_becomes_project_manager(self):
        data = six()
        data[1]["owner"] = "Wizard"
        owners = {r["owner"] for r in self.fin(data)["risks"]}
        self.assertNotIn("Wizard", owners)

    def test_generic_description_rejected(self):
        data = six()
        data[0]["description"] = "Scope may change"
        with self.assertRaises(AIOutputError):
            self.fin(data)

    def test_too_few_risks_and_single_mitigation_rejected(self):
        with self.assertRaises(AIOutputError):
            self.fin(six()[:3])
        data = six()
        data[0]["mitigation"] = ["only one"]
        with self.assertRaises(AIOutputError):
            self.fin(data)

    def test_more_than_eight_are_cut(self):
        extra = six() + [R("Cost", f"Extra cost issue number {n} in task {n}.1", 1, 1, f"extra-{n}") for n in range(5)]
        self.assertEqual(len(self.fin(extra)["risks"]), risk.MAX_RISKS)

    def test_calibration_raises_probability(self):
        data = six()
        data[1]["probability"] = 1  # budget 95% used and past overruns of 12%: floor is 3
        cost = [r for r in self.fin(data)["risks"] if r["category"] == "Cost"][0]
        self.assertGreaterEqual(cost["probability"], 3)
        self.assertIn("ratingNote", cost)

    def test_keys_unique_and_previous_keys_reused(self):
        prev = [{"key": "time-old-key", "category": "Time", "description": "Task 3.2 is critical", "score": 9}]
        data = six()
        data[0]["key"] = "time-new-key"
        keys = [r["key"] for r in self.fin(data, previous_risks=prev)["risks"]]
        self.assertIn("time-old-key", keys)
        self.assertEqual(len(keys), len(set(keys)))

    def test_missing_key_is_generated(self):
        for r in self.fin(six())["risks"]:
            self.assertTrue(r["key"])


if __name__ == "__main__":
    unittest.main()
