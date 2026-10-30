"""Checks that a /api/analyze result meets the acceptance list (shared by the mocked test and the live run)."""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import risk  # noqa: E402

FIELDS = ["id", "key", "category", "description", "probability", "impact", "score", "level", "priority", "mitigation", "owner"]


def check_analysis(result, project):
    """Returns a list of problems (empty list = everything passes)."""
    problems = []
    risks = result.get("risks") or []
    roles = [r["role"] for r in project["resources"]] + ["Project Manager"]
    if not 6 <= len(risks) <= 8:
        problems.append(f"expected 6 to 8 risks, got {len(risks)}")
    if len({r.get("category") for r in risks}) < 4:
        problems.append("fewer than 4 different categories")
    for r in risks:
        rid = f"risk {r.get('id')}"
        missing = [f for f in FIELDS if f not in r or r[f] in (None, "", [])]
        if missing:
            problems.append(f"{rid}: missing {missing}")
            continue
        if r["category"] not in risk.CATEGORIES:
            problems.append(f"{rid}: bad category {r['category']}")
        if r["score"] != r["probability"] * r["impact"]:
            problems.append(f"{rid}: score {r['score']} != {r['probability']} x {r['impact']}")
        if r["level"] != risk.level_for(r["score"]):
            problems.append(f"{rid}: level {r['level']} does not match score {r['score']}")
        if r["priority"] != risk.PRIORITY[r["level"]]:
            problems.append(f"{rid}: priority does not match level")
        if not 2 <= len(r["mitigation"]) <= 3:
            problems.append(f"{rid}: mitigation has {len(r['mitigation'])} actions")
        if r["owner"] not in roles:
            problems.append(f"{rid}: owner '{r['owner']}' is not a project role")
        d = r["description"]
        if not (re.search(r"\d", d) or any(x.lower() in d.lower() for x in roles)):
            problems.append(f"{rid}: description names no task id, role or number")
    scores = [r.get("score", 0) for r in risks]
    if scores != sorted(scores, reverse=True):
        problems.append("risks are not sorted by score, highest first")
    if len({r.get("key") for r in risks}) != len(risks):
        problems.append("duplicate keys")
    return problems
