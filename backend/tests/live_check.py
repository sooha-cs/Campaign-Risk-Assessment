"""Live check against the RUNNING server (python app.py in another terminal).

  python tests/live_check.py              one run, prints risks + quality report
  python tests/live_check.py --repeat 3   re-run /api/analyze 3x on the same plan to see how stable the ratings are
Saves samples/output_plan.json and samples/output_analyze.json.
"""
import argparse
import json
import os
import re
import statistics
import sys
import time

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLES = os.path.join(HERE, "..", "samples")
BASE = os.getenv("BASE_URL", "http://127.0.0.1:5000")


def post(path, body):
    t = time.time()
    r = requests.post(BASE + path, json=body, timeout=180)
    if r.status_code == 502 and "rate limit" in r.text.lower():
        print("Groq free-tier rate limit hit; waiting 65 s and trying once more...")
        time.sleep(65)
        t = time.time()
        r = requests.post(BASE + path, json=body, timeout=180)
    print(f"POST {path} -> {r.status_code} in {time.time() - t:.1f}s")
    if not r.ok:
        print(r.text)
        sys.exit(1)
    return r.json()


def quality_report(result, project):
    """Cheap automatic checks for the things we tuned the prompt for."""
    risks = result["risks"]
    roles = {r["role"] for r in project["resources"]} | {"Project Manager"}
    task_id = re.compile(r"\b\d+\.\d+\b")
    rows = {
        "6-8 risks": 6 <= len(risks) <= 8,
        ">=4 categories": len({r["category"] for r in risks}) >= 4,
        "all owners valid": all(r["owner"] in roles for r in risks),
        "2-3 mitigations each": all(2 <= len(r["mitigation"]) <= 3 for r in risks),
        "specific (task id or number in text)": sum(bool(task_id.search(r["description"]) or re.search(r"\d", r["description"])) for r in risks) >= len(risks) * 0.7,
        "ratings spread (>=3 distinct scores)": len({r["score"] for r in risks}) >= 3,
        "<=2 risks with probability 5": sum(r["probability"] == 5 for r in risks) <= 2,
    }
    print("\nQuality report")
    for k, ok in rows.items():
        print(f"  [{'PASS' if ok else 'FAIL'}] {k}")
    adjusted = [r for r in risks if r.get("ratingNote")]
    if adjusted:
        print(f"  {len(adjusted)} rating(s) adjusted by rules:")
        for r in adjusted:
            print(f"    risk {r['id']} ({r['category']}): {r['ratingNote']}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--project", default=os.path.join(SAMPLES, "sample_project.json"))
    args = ap.parse_args()

    project = json.load(open(args.project, encoding="utf-8"))
    plan = post("/api/plan", project)
    json.dump(plan, open(os.path.join(SAMPLES, "output_plan.json"), "w", encoding="utf-8"), indent=2)
    for w in plan.get("warnings", []):
        print("  plan warning:", w)

    runs = []
    for n in range(args.repeat):
        result = post("/api/analyze", {"project": project, "plan": plan})
        runs.append(result)
        if n == 0:
            json.dump(result, open(os.path.join(SAMPLES, "output_analyze.json"), "w", encoding="utf-8"), indent=2)
            print()
            for r in result["risks"]:
                print(f"#{r['id']} [{r['level']:<8}] {r['score']:>2} (P{r['probability']} x I{r['impact']}) {r['category']}: {r['description']}")
                for m in r["mitigation"]:
                    print(f"      - {m}")
                print(f"      owner: {r['owner']}")
            quality_report(result, project)

    if args.repeat > 1:
        print("\nStability across runs (highest score / total risks / per-category mean score)")
        highs = [r["summary"]["highestScore"] for r in runs]
        print("  highest:", highs, "stdev", round(statistics.pstdev(highs), 2))
        print("  totals :", [r["summary"]["total"] for r in runs])
        for cat in ["Time", "Cost", "Resource", "Scope", "Quality"]:
            means = []
            for r in runs:
                s = [x["score"] for x in r["risks"] if x["category"] == cat]
                means.append(round(sum(s) / len(s), 1) if s else None)
            print(f"  {cat:<8}", means)


if __name__ == "__main__":
    main()
