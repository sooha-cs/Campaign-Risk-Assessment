import logging
import os

from flask import Flask, jsonify, request
from flask_cors import CORS

import ai_service
import monitoring
from errors import ValidationError
from groq_client import call_groq_json
from http_utils import run as _run
from validators import validate_project

app = Flask(__name__)
CORS(app)


@app.get("/")
def index():
    return jsonify(
        name="CampaignRisk AI backend",
        endpoints=["GET /api/health", "GET /api/test-groq", "POST /api/plan", "POST /api/analyze",
                   "POST /api/update", "GET /api/history"],
    )


@app.get("/api/health")
def health():
    return jsonify(status="ok")


# Temporary route to confirm the AI connection. Remove before final submission.
@app.get("/api/test-groq")
def test_groq():
    return _run(lambda: call_groq_json(
        [{"role": "user", "content": 'Reply with JSON only: {"status":"connected"}'}]
    ))


@app.post("/api/plan")
def plan():
    """Body: the project object. Returns WBS, schedule, cost, resources, workflow."""
    def work():
        project = validate_project(request.get_json(silent=True))
        return ai_service.generate_plan(project)
    return _run(work)


@app.post("/api/analyze")
def analyze():
    """Body: {"project": {...}, "plan": {...optional, output of /api/plan}}. Returns scored risks and projectId."""
    def work():
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            raise ValidationError('Body must be JSON: {"project": {...}, "plan": {...}}')
        project = validate_project(body.get("project"))
        plan_data = body.get("plan")
        generated = False
        if plan_data is None:
            plan_data, generated = ai_service.generate_plan(project), True
        elif not isinstance(plan_data, dict) or "schedule" not in plan_data:
            raise ValidationError("plan must be the JSON returned by /api/plan")
        result = ai_service.generate_risks(project, plan_data)
        if generated:
            result["plan"] = plan_data
        # The id monitoring.py uses by default, so the frontend can call /api/update and /api/history with it.
        result["projectId"] = monitoring._slug(project["name"])
        return result
    return _run(work)


@app.post("/api/update")
def update():
    """Body: {projectId?, project?, plan?, risks?, progress: {asOfDate, actualCostToDate, tasks}, reanalyze?}.
    Saves a progress snapshot, calculates project health and (optionally) re-scores the risks."""
    return _run(lambda: monitoring.apply_update(request.get_json(silent=True)))


@app.get("/api/history")
def history():
    """Query: projectId (optional), limit (optional), full=true (optional). Saved snapshots + trend lists."""
    def work():
        limit = request.args.get("limit")
        if limit is not None and (not limit.isdigit() or int(limit) < 1):
            raise ValidationError("limit must be a whole number >= 1")
        full = request.args.get("full", "").lower() in ("1", "true", "yes")
        return monitoring.get_history(request.args.get("projectId"), int(limit) if limit else None, full)
    return _run(work)


if __name__ == "__main__":
    app.run(port=int(os.getenv("PORT", 5000)), debug=os.getenv("FLASK_DEBUG") == "1")
