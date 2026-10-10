"""Calls the AI, validates what comes back, retries automatically if it is invalid."""
import json
import re
import time
from datetime import date

import planner
import prompts
import risk
from errors import AIOutputError
from groq_client import GroqError, call_groq, extract_json

MAX_ATTEMPTS = 3
MAX_RATE_WAIT = 30      # seconds we are willing to wait for a per-minute rate limit (longer = daily limit)
UNKNOWN_RATE_WAIT = 20  # used when the error text does not say how long to wait


class AIError(RuntimeError):
    """The AI could not give a valid answer (reported to the client as HTTP 502)."""


def _retry_after(message):
    """Seconds suggested by a Groq 429 message ("... try again in 6.5s", "1m12.5s", "800ms"), else None."""
    m = re.search(r"try again in\s+(?:(\d+)m)?\s*([\d.]+)(ms|s)", str(message))
    if not m:
        return None
    secs = float(m.group(2)) / (1000 if m.group(3) == "ms" else 1)
    return int(m.group(1) or 0) * 60 + secs


def _ask_json(system, user, validate_fn):
    last_error = "unknown error"
    rate_waits = 0
    for attempt in range(MAX_ATTEMPTS):
        feedback = ""
        if last_error != "unknown error":
            feedback = f"\n\nYour previous answer was rejected: {last_error}. Return corrected JSON only."
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user + feedback},
        ]
        try:
            return validate_fn(extract_json(call_groq(messages, json_mode=True)))
        except GroqError as e:
            if e.status == 429:  # per-minute token limit: wait it out once or twice; a daily limit gives up
                wait = _retry_after(e)
                wait = UNKNOWN_RATE_WAIT if wait is None else wait
                if wait > MAX_RATE_WAIT or rate_waits >= 2 or attempt == MAX_ATTEMPTS - 1:
                    raise AIError(str(e)) from e
                rate_waits += 1
                time.sleep(wait + 1)
                continue
            if e.status in (401, 403, 404, 413):  # key/model problems: retrying will not help
                raise AIError(str(e)) from e
            last_error = str(e)
            time.sleep(2 * (attempt + 1))  # network/5xx: wait a little before trying again
        except json.JSONDecodeError as e:
            last_error = f"it was not valid JSON ({e})"
        except AIOutputError as e:
            last_error = "; ".join(e.errors)
        except (KeyError, TypeError, ValueError, AttributeError) as e:
            last_error = f"unexpected structure ({e})"
    raise AIError(f"AI did not return a valid result after {MAX_ATTEMPTS} attempts: {last_error}")


def generate_plan(project):
    def validate(data):
        if not isinstance(data, dict):
            raise AIOutputError("response must be a JSON object with 'wbs' and 'workflow'")
        wbs = planner.validate_wbs(data.get("wbs"), project["resources"])
        available = (date.fromisoformat(project["deadline"]) - date.fromisoformat(project["startDate"])).days + 1
        too_long = [t["id"] for ph in wbs for t in ph["tasks"] if t["durationDays"] > min(10, available)]
        if too_long:
            raise AIOutputError(f"tasks {too_long} are longer than {min(10, available)} days; split them into smaller tasks")
        workflow = planner.validate_workflow(data.get("workflow"))
        return planner.build_plan(project, wbs, workflow)  # also catches circular dependencies

    return _ask_json(prompts.PLAN_SYSTEM, prompts.plan_user_message(project), validate)


def generate_risks(project, plan, previous_risks=None, progress_signals=None, extra_signals=None):
    """previous_risks: risks of the last saved run (keeps keys stable between runs).
    progress_signals: progress numbers from a project update (health, spi, cpi, delay, forecast...).
    extra_signals: the name monitoring.py uses; {"progress": {...}} is unpacked into progress_signals."""
    if extra_signals and not progress_signals:
        progress_signals = extra_signals.get("progress", extra_signals)
    signals = risk.compute_signals(project, plan)
    drivers = risk.compute_drivers(project, plan, signals)
    roles = [r["role"] for r in project["resources"]]
    previous = [{k: p.get(k) for k in ("key", "category", "description", "score")}
                for p in previous_risks or [] if isinstance(p, dict)]
    return _ask_json(
        prompts.RISK_SYSTEM,
        prompts.risk_user_message(project, plan, signals, drivers, roles, previous or None, progress_signals),
        lambda data: risk.finalize_risks(data, roles=roles, signals=signals, strict=True,
                                         previous_risks=previous),
    )
