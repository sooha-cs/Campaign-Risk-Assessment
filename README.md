# CampaignRisk AI

**AI-driven project planning, risk assessment and continuous monitoring.**

CampaignRisk AI takes a project description (budget, dates, team, deliverables, past projects), uses an LLM to propose a work breakdown structure, calculates the schedule, cost and critical path in code, identifies and scores risks, suggests mitigations, and re-assesses everything whenever progress is reported.

![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![Flask](https://img.shields.io/badge/Flask-3.x-lightgrey)
![LLM](https://img.shields.io/badge/LLM-Groq%20(gpt--oss--120b)-orange)
![Storage](https://img.shields.io/badge/Storage-SQLite-green)

---

## Table of Contents

1. [Introduction](#1-introduction)
2. [Problem Statement](#2-problem-statement)
3. [Objectives](#3-objectives)
4. [Key Features](#4-key-features)
5. [System Architecture and Workflow](#5-system-architecture-and-workflow)
6. [Tech Stack](#6-tech-stack)
7. [Project Structure](#7-project-structure)
8. [Installation](#8-installation)
9. [Demo Walkthrough](#9-demo-walkthrough)
10. [API Reference](#10-api-reference)
11. [How the Numbers Are Calculated](#11-how-the-numbers-are-calculated)
12. [Configuration](#12-configuration)
13. [Testing](#13-testing)
14. [Design Decisions and Assumptions](#14-design-decisions-and-assumptions)
15. [Troubleshooting](#15-troubleshooting)
16. [Limitations and Future Work](#16-limitations-and-future-work)
17. [Team](#17-team)


---

## 1. Introduction

Planning a project and keeping track of what could go wrong usually means juggling spreadsheets, gut feeling and last-minute surprises. **CampaignRisk AI** combines a large language model with deterministic project-management maths to make that process fast and consistent.

The project began as a risk tool for marketing campaigns and grew into a general project-management assistant covering **time, cost, resources, work breakdown structure (WBS), schedule, workflow and risk assessment**.

The core idea is a clear division of labour:

| The AI does | The code does |
|-------------|---------------|
| Proposes tasks, durations, dependencies and workflow steps | Calculates dates, critical path, slack, costs and resource load |
| Identifies project-specific risks and rates probability and impact | Calculates score, level and priority; validates and calibrates the AI's ratings |
| Writes concrete mitigation actions and suggests owners | Computes project health (earned value), forecasts, alerts and trends |

Because every number is computed in Python, results are always internally consistent and never "hallucinated".

---

## 2. Problem Statement

Project and campaign managers face recurring problems:

- **Risks are found too late.** Budget overruns and schedule slips are often noticed only after they have happened.
- **Risk assessment is subjective.** Different people rate the same risk differently, and past project data is rarely used.
- **Plans go stale.** A risk register written at kickoff is rarely updated as spend and progress change.
- **Raw LLM output is unreliable.** Asking an AI to "plan a project" directly produces inconsistent dates, costs and malformed JSON.

**CampaignRisk AI addresses this by:**

1. Generating a structured, validated plan from a short project description.
2. Producing a scored, calibrated risk register that uses past-project evidence.
3. Re-assessing risks automatically whenever progress data is submitted, and alerting on new or rising risks.
4. Guarding every AI response with validation, calibration rules and automatic retries.

---

## 3. Objectives

- **Risk identification:** detect time, cost, resource, scope and quality risks specific to the project.
- **Predictive scoring:** score each risk as probability x impact (1-5 each), informed by plan signals and past-project data.
- **Mitigation strategies:** give 2-3 actionable steps and an owner for every risk.
- **Continuous monitoring:** compute project health from progress updates, re-score risks, and flag new or rising risks.

---

## 4. Key Features

- **AI-generated WBS and workflow** (`POST /api/plan`) with 4-6 phases and 12-25 tasks.
- **Code-calculated plan:** schedule via Critical Path Method (CPM), slack, cost by phase, 10% contingency, resource utilisation and over-allocation checks.
- **Scored risk register** (`POST /api/analyze`) with category, probability, impact, score, level, priority, mitigation and owner.
- **Rule-based calibration:** simple rules raise or lower the AI's probability when the data says it is too optimistic or pessimistic (for example, a plan that already misses the deadline forces Time probability to at least 4).
- **Progress monitoring** (`POST /api/update`) using earned value management: SPI, CPI, delay forecast, cost forecast and an On Track / At Risk / Off Track health status.
- **Risk comparison between runs:** alerts for new risks and for any category whose score rises by 3 or more.
- **History and trends** (`GET /api/history`) ready for charts.
- **Robust AI handling:** JSON-only prompts, fence-tolerant parsing, strict validation, up to 3 automatic retries with error feedback, and rate-limit waiting for the Groq free tier.
- **Offline test suite:** the AI is mocked, so tests run without an API key.

---

## 5. System Architecture and Workflow

```
┌──────────┐   project JSON   ┌────────────────────────────────────────────┐
│ Frontend │ ───────────────▶ │                Flask backend               │
│ (Web UI) │                  │                                            │
│          │ ◀─────────────── │  validators ─▶ ai_service ─▶ groq_client ──┼──▶ Groq LLM
└──────────┘   JSON results   │                   │                        │
                              │         planner / risk (code maths)        │
                              │                   │                        │
                              │             monitoring ─▶ SQLite           │
                              └────────────────────────────────────────────┘
```

The application follows a five-stage loop. Stage 5 feeds back into Stage 2, which is what makes monitoring continuous.

| Stage | What happens | Endpoint | Output |
|-------|--------------|----------|--------|
| 1. Input | User submits the project form (name, budget, dates, team, resources, deliverables, past projects) | all | Validated project data |
| 2. Planning | AI proposes WBS and workflow; code builds schedule, cost and resource plan | `POST /api/plan` | Plan with critical path and warnings |
| 3. Risk identification and prediction | AI lists risks and rates them; code calibrates and calculates score and level | `POST /api/analyze` | Scored risks with mitigation and owner |
| 4. Mitigation | Included in the risk response (2-3 actions and an owner per risk) | `POST /api/analyze` | Mitigation plan |
| 5. Monitoring | User reports spend and task progress; health is computed; risks are re-scored and compared | `POST /api/update`, `GET /api/history` | Health metrics, alerts, trend data |

**Data flow:** `Project input → /api/plan → /api/analyze → /api/update (repeat) → /api/history → dashboard`

---

## 6. Tech Stack

| Layer | Technology |
|-------|------------|
| Backend | Python 3, Flask, Flask-CORS |
| AI | Groq API, model `openai/gpt-oss-120b` (configurable) |
| Storage | SQLite (`data/campaignrisk.db`) |
| HTTP client | `requests` |
| Config | `python-dotenv` (`.env`) |
| Frontend | HTML/CSS/JS or React (calls the REST API) |
| Charts | Chart.js (Gantt-style schedule, cost by phase, heat map, bar chart, trend line) |
| Testing | `unittest`, mocked AI, Postman collection |

---

## 7. Project Structure

```
campaignrisk-ai/
├── README.md
├── .gitignore
├── frontend/                  # Web UI - adjust to match your repo
│   └── ...
└── backend/
    ├── app.py                 # Flask routes: /, /api/health, /api/plan, /api/analyze, /api/update, /api/history
    ├── ai_service.py          # Calls the AI, validates output, retries, handles rate limits
    ├── prompts.py             # All prompt templates (plan and risk system prompts, user messages)
    ├── groq_client.py         # Groq API wrapper, token budgeting, JSON extraction
    ├── validators.py          # Validates and cleans the project input
    ├── planner.py             # WBS validation, CPM schedule, cost, resource plan
    ├── risk.py                # Risk signals, calibration rules, validation, scoring
    ├── monitoring.py          # Progress updates, earned value metrics, comparison, history (SQLite)
    ├── http_utils.py          # Shared route wrapper: errors -> clean JSON responses
    ├── errors.py              # ValidationError, AIOutputError, NotFoundError
    ├── test_groq.py           # Quick check that the Groq connection works
    ├── requirements.txt
    ├── .env.example           # Template for environment variables (never commit .env)
    ├── data/
    │   └── campaignrisk.db    # SQLite database (created automatically)
    ├── samples/
    │   ├── sample_project.json
    │   ├── scenario_ontrack.json
    │   ├── scenario_overbudget.json
    │   ├── scenario_delayed.json
    │   ├── example_plan_response.json
    │   └── example_analyze_response.json
    └── tests/
        ├── test_offline.py                 # Plan and analyze with mocked AI
        ├── test_api_mocked.py              # 3 scenarios end to end, mocked AI
        ├── test_risk_rules.py              # Scoring and validation rules
        ├── test_risk_day2.py               # Calibration, strict mode, drivers
        ├── test_rate_limit.py              # Rate-limit waiting logic
        ├── test_monitoring_integration.py  # plan -> analyze -> update -> history
        ├── checks.py                       # Shared acceptance checks for /api/analyze
        ├── check_samples.py                # Validates all sample JSON files
        ├── live_check.py                   # Live run against Groq (needs key)
        ├── run_scenarios.py                # Live run of the 3 scenarios
        └── live_flow.py                    # Live end-to-end incl. monitoring
```

---

## 8. Installation

### Prerequisites

- Python 3.10 or newer
- `pip`
- A free Groq API key from <https://console.groq.com>

### Steps

```bash
# 1. Clone the repository
git clone https://github.com/<your-username>/campaignrisk-ai.git
cd campaignrisk-ai/backend

# 2. Create and activate a virtual environment
python -m venv venv
venv\Scripts\activate            # Windows
# source venv/bin/activate       # macOS / Linux

# 3. Install dependencies
pip install -r requirements.txt

# 4. Create your environment file
copy .env.example .env           # Windows
# cp .env.example .env           # macOS / Linux
```

Open `.env` and paste your key:

```env
GROQ_API_KEY=your_groq_key_here
GROQ_MODEL=openai/gpt-oss-120b
PORT=5000
```

### Verify the setup

```bash
python test_groq.py              # expects: Groq connected: {'status': 'connected'}
python -m unittest discover tests -v   # offline tests, no API key needed
python app.py                    # starts the server at http://127.0.0.1:5000
```

Then open <http://127.0.0.1:5000/api/health>. You should see `{"status":"ok"}`.

> **Security:** never commit `.env`. Share `.env.example` only.

---

## 9. Demo Walkthrough

With the server running (`python app.py`), the following steps reproduce the full flow using the bundled sample project. Commands use `curl`; on Windows PowerShell, use `curl.exe` or Postman.

### Step 1: Generate a plan (10-40 seconds)

```bash
curl -X POST http://127.0.0.1:5000/api/plan \
  -H "Content-Type: application/json" \
  -d @samples/sample_project.json > plan.json
```

Result: WBS, schedule with critical path, cost estimate, resource plan, workflow and warnings.

### Step 2: Analyze risks

Create a body containing `{"project": ..., "plan": ...}` (or send only `{"project": ...}` and the backend will generate the plan for you):

```bash
curl -X POST http://127.0.0.1:5000/api/analyze \
  -H "Content-Type: application/json" \
  -d '{"project": <contents of sample_project.json>}'
```

Example (shortened) response:

```json
{
  "projectId": "diwali-festive-email-campaign",
  "risks": [
    {
      "id": 1, "key": "time-critical-path-3-2", "category": "Time",
      "description": "Task 3.2 is on the critical path with 0 slack, so any delay moves the deadline.",
      "probability": 4, "impact": 4, "score": 16, "level": "Critical",
      "priority": "Escalate immediately",
      "mitigation": ["Start 3.2 as early as possible", "Add a second person for 3.2"],
      "owner": "Project Manager"
    }
  ],
  "summary": { "total": 7, "byLevel": { "Low": 0, "Medium": 3, "High": 3, "Critical": 1 }, "highestScore": 16 }
}
```

Keep the returned `projectId`; it is needed for monitoring.

### Step 3: Report progress (first update, no AI tokens used)

```bash
curl -X POST http://127.0.0.1:5000/api/update \
  -H "Content-Type: application/json" \
  -d '{
    "projectId": "diwali-festive-email-campaign",
    "project": { ... },
    "plan": { ... },
    "reanalyze": false,
    "progress": {
      "asOfDate": "2026-10-25",
      "actualCostToDate": 90000,
      "tasks": [ { "taskId": "1.1", "percentComplete": 100 } ]
    }
  }'
```

The first update must include `project` and `plan`. They are saved, so later updates only need `projectId` and `progress`.

### Step 4: Report worse progress and let the AI re-score risks

```bash
curl -X POST http://127.0.0.1:5000/api/update \
  -H "Content-Type: application/json" \
  -d '{
    "projectId": "diwali-festive-email-campaign",
    "reanalyze": true,
    "progress": {
      "asOfDate": "2026-11-10",
      "actualCostToDate": 200000,
      "tasks": [ { "taskId": "1.2", "percentComplete": 40 } ]
    }
  }'
```

The response includes `health` (for example `Off Track`), `metrics` (SPI, CPI, forecast finish and cost), `changes` (new, increased and decreased risks) and the re-scored `risks`.

### Step 5: View history and trends

```bash
curl "http://127.0.0.1:5000/api/history?projectId=diwali-festive-email-campaign&full=true"
```

The `trend` object holds ready-to-plot lists: `dates`, `percentComplete`, `plannedPercent`, `spi`, `cpi`, `forecastCost`, `scheduleDelayDays`, `highestRiskScore`.

### One-command live demo

```bash
python tests/live_flow.py scenario_overbudget
```

This runs plan, analyze, a no-AI update, an AI re-scoring update and history in sequence, printing risks, health, alerts and trends.

---

## 10. API Reference

Base URL: `http://127.0.0.1:5000`. All requests and responses are JSON. CORS is enabled.

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/` | Lists the available endpoints |
| GET | `/api/health` | Health check, returns `{"status":"ok"}` |
| GET | `/api/test-groq` | *Temporary.* Confirms the AI connection. Remove before final submission |
| POST | `/api/plan` | Project in; WBS, schedule, cost, resource plan and workflow out |
| POST | `/api/analyze` | Project (and optional plan) in; scored risks and `projectId` out |
| POST | `/api/update` | Progress in; health metrics, alerts and (optionally) re-scored risks out |
| GET | `/api/history` | Saved snapshots and trend lists for charts |

### Project input

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `name` | text | yes | |
| `budget` | number > 0 | yes | |
| `startDate` | `YYYY-MM-DD` | yes | |
| `deadline` | `YYYY-MM-DD` | yes | Must be after `startDate` |
| `teamSize` | whole number >= 1 | yes | |
| `resources` | list of `{role, count, costPerDay}` | yes | Roles must be unique; the AI may only assign tasks to these roles |
| `description`, `projectType` | text | no | Defaults `""` and `"General"` |
| `currency` | text | no | Default `"INR"` |
| `deliverables`, `constraints` | list of text | no | |
| `pastProjects` | list of `{name, plannedCost, actualCost, plannedDays, actualDays, outcome}` | no | Used to calibrate risk likelihood |

### `POST /api/plan`

Body: the project object. Response keys: `wbs`, `schedule`, `scheduleSummary`, `costEstimate`, `resourcePlan`, `workflow`, `warnings`.

### `POST /api/analyze`

Body: `{ "project": {...}, "plan": {...} }`. `plan` is optional; if omitted, one is generated and returned in a `plan` field.

Response keys: `risks`, `summary`, `projectId` (and `plan` if it was generated).

- `category` is one of **Time, Cost, Resource, Scope, Quality**.
- Risks are sorted by score, highest first, and capped at 8.
- A risk may include `ratingNote` when the rules adjusted the AI's probability.

### `POST /api/update`

Body: `{ projectId?, project?, plan?, risks?, progress, reanalyze? }`

```json
{
  "progress": {
    "asOfDate": "YYYY-MM-DD",
    "actualCostToDate": 123000,
    "tasks": [ { "taskId": "2.1", "percentComplete": 60 } ]
  },
  "reanalyze": true
}
```

- Tasks not listed keep their previous percentage.
- `asOfDate` cannot be before the project start or the previous update.
- Set `"reanalyze": false` to skip the AI and use no tokens.

### `GET /api/history`

Query parameters: `projectId` (optional; omit to list all projects), `limit` (optional), `full=true` (optional; include metrics, tasks, risks and changes per snapshot).

### Errors

| Status | Meaning | Body |
|--------|---------|------|
| 400 | Invalid input | `{"error": "Invalid input", "details": ["..."]}` |
| 404 | Project or record not found | `{"error": "..."}` |
| 502 | AI failed after 3 attempts, or key/model/rate-limit problem | `{"error": "..."}` |
| 500 | Unexpected server error | `{"error": "Internal server error"}` |

---

## 11. How the Numbers Are Calculated

### Risk scoring

`score = probability x impact` (both whole numbers 1-5). The AI is never allowed to supply the score or level; code recalculates them.

| Score | Level | Priority / Action |
|-------|-------|-------------------|
| 1-4 | Low | Monitor |
| 5-9 | Medium | Plan a response |
| 10-15 | High | Act this week |
| 16-25 | Critical | Escalate immediately |

### Signals and calibration rules

Before calling the AI, `risk.py` computes **signals** (buffer days, budget utilisation, critical tasks, over-allocated roles, average past delay and cost overrun). After the AI answers, simple rules adjust probabilities. Examples:

| Condition | Rule |
|-----------|------|
| Plan finishes after the deadline | Time probability at least 4 |
| Schedule buffer under 10% of available days | Time probability at least 3 |
| Estimated cost exceeds the budget | Cost probability at least 4 |
| Budget utilisation above 90% | Cost probability at least 3 |
| Past projects ran more than 10% late or over budget | Matching probability at least 3 |
| One or more roles over-allocated | Resource probability at least 3 (4 if two or more) |
| Buffer 25% or more and small past delays | Time probability at most 3 |
| Cost under 75% of budget and small past overruns | Cost probability at most 3 |

Floors always win over caps. Any adjustment is explained in the risk's `ratingNote`.

### Plan calculations (`planner.py`)

- **Schedule:** forward and backward CPM pass; zero slack means critical.
- **Cost:** `duration x costPerDay` per task, plus 10% contingency.
- **Resources:** peak concurrent tasks per role, flagged as over-allocated when above the role's `count`.

### Project health (`monitoring.py`, earned value method)

| Metric | Meaning |
|--------|---------|
| PV (planned value) | Cost of the work that *should* be done by the report date |
| EV (earned value) | Cost of the work actually done |
| SPI = EV / PV | Below 0.95 means behind schedule |
| CPI = EV / actual cost | Below 0.95 means overspending |
| Forecast cost | `actual cost + (budget at completion - EV) / CPI` |
| Forecast finish | Planned finish plus the delay not absorbed by task slack |

| Health | Condition |
|--------|-----------|
| **Off Track** | Forecast finish after deadline, forecast cost over budget, or SPI/CPI below 0.8 |
| **At Risk** | SPI or CPI below 0.95 |
| **On Track** | Otherwise |

### Risk alerts

Risks are compared per category (highest score) with the previous run. An alert is raised for each **new** category risk and for each category whose score **rose by 3 or more**. Risk `key` values are reused between runs so comparisons stay stable.

---

## 12. Configuration

Set these in `backend/.env`.

| Variable | Default | Purpose |
|----------|---------|---------|
| `GROQ_API_KEY` | *(required)* | Groq API key |
| `GROQ_MODEL` | `openai/gpt-oss-120b` | Model name; change without code edits |
| `GROQ_REASONING_EFFORT` | `low` | Reasoning effort for gpt-oss models |
| `GROQ_TPM_BUDGET` | `7500` | Tokens-per-minute budget used to size output length |
| `GROQ_MAX_TOKENS` | `4096` | Upper cap for output tokens |
| `PORT` | `5000` | Server port |
| `FLASK_DEBUG` | *(off)* | Set to `1` for debug mode |
| `CAMPAIGNRISK_DB` | `data/campaignrisk.db` | Path to the SQLite file |
| `API_URL` / `BASE_URL` | `http://127.0.0.1:5000` | Server URL used by the live test scripts |

---

## 13. Testing

All offline tests mock the AI, so **no API key or internet is needed**.

```bash
cd backend
python -m unittest discover tests -v
```

| Test file | Covers |
|-----------|--------|
| `test_offline.py` | Plan calculations, retry after bad JSON or role, circular dependency rejection, score recalculation |
| `test_api_mocked.py` | The 3 scenarios (on-track, over-budget, delayed) through both endpoints |
| `test_risk_rules.py` | Levels, sorting, AI cannot set the score, owner fallback, key reuse |
| `test_risk_day2.py` | Calibration floors and caps, strict-mode rejections, duplicate removal |
| `test_rate_limit.py` | Per-minute limit is waited out, daily limit fails fast |
| `test_monitoring_integration.py` | plan, analyze, update, history through the real routes |

**Live tests** (server running, valid Groq key):

```bash
python tests/live_check.py --repeat 3      # quality report and stability of ratings
python tests/run_scenarios.py              # all 3 scenarios, saves real outputs to samples/
python tests/live_flow.py scenario_delayed # full flow including monitoring
python tests/check_samples.py              # validates every sample JSON file
```

The acceptance checks in `tests/checks.py` require 6-8 risks, at least 4 categories, valid owners, 2-3 mitigations each, specific descriptions, correct score/level/priority, sorted order and unique keys.

---

## 14. Design Decisions and Assumptions

| Decision | Reason |
|----------|--------|
| Python (Flask) backend | Easy JSON handling; the workflow document allowed Node or Python |
| Groq with `openai/gpt-oss-120b` | Free tier; `llama-3.3-70b-versatile` was retired on free accounts |
| Two AI calls (`/plan`, `/analyze`) | Smaller calls give more reliable JSON than one huge call |
| Numbers computed in code | Dates, costs, scores and health stay consistent and auditable |
| Mitigation inside `/api/analyze` | A separate `/api/mitigate` was unnecessary |
| SQLite storage | No database server to set up |

**Assumptions** (state these in the report):

- Durations are in **calendar days**; weekends are not skipped.
- **One person per task**; cost equals duration x the role's `costPerDay`.
- **10% contingency** is added (`CONTINGENCY_RATE` in `planner.py`).
- Task cost is spread evenly over the task's duration when computing planned value.
- A risk's `overallocated` flag is true when more tasks of a role run on the same day than that role's `count`.

---

## 15. Troubleshooting

| Problem | Fix |
|---------|-----|
| `404 model_not_found` | Change `GROQ_MODEL` in `.env` to a current model from the Groq docs, then restart |
| `401` or "GROQ_API_KEY missing" | Make sure `.env` is in the same folder as `app.py`, with the key pasted without quotes or spaces |
| `429` rate limit | The backend waits out short limits automatically. For daily limits wait, or switch to `openai/gpt-oss-20b` |
| `502 AI did not return a valid result` | Run again, since AI output varies. If it repeats, check the message and the prompts in `prompts.py` |
| Port 5000 already in use | Set `PORT=5001` in `.env` and update the frontend's base URL |
| Browser shows "Not Found" at an unknown path | Normal; use the `/api/...` URLs |
| `.env` appears in `git status` | `.gitignore` must be in the repo root; never commit the key |
| Cannot delete the database on Windows | Close the server first; connections are closed after every request |

---

## 16. Limitations and Future Work

**Current limitations**

- Free-tier Groq limits (about 8K tokens per minute and 200K per day) constrain how often plans and re-assessments can run.
- Plans use calendar days and one person per task; there are no working calendars or resource levelling.
- Risk probabilities come from an LLM plus simple rules, not a trained statistical model.
- No user accounts or authentication; the SQLite database is single-instance.
- `/api/test-groq` is a development route and must be removed before deployment.

**Possible improvements**

- Result caching to reduce API cost and latency.
- CSV upload for past-project data and bulk import.
- Working-day calendars, holidays and resource levelling.
- Monte Carlo simulation for schedule and cost confidence ranges.
- Authentication, multi-user projects and a PostgreSQL option.
- Notifications (email or Slack) when alerts are raised.
- Docker setup and CI pipeline running the offline tests.

---

## 17. Team

| Role | Responsibility |
|----------|----------------|
| Frontend / UI | Pages, forms, navigation, responsive design |
| AI Integration  | Prompts, Groq connection, planning and risk endpoints, validation, retries |
| Monitoring and Storage  | `/api/update`, `/api/history`, earned value metrics, alerts, SQLite |
| Data, Visualization, Testing, Docs | Sample data, charts, test scenarios, Postman collection, report and slides |

---
