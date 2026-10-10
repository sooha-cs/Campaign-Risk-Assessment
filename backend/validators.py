from datetime import date

from errors import ValidationError


def _is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def validate_project(body):
    """Checks the project input (see README) and returns a cleaned copy with defaults."""
    if not isinstance(body, dict):
        raise ValidationError("project must be a JSON object")
    errs = []

    name = body.get("name")
    if not isinstance(name, str) or not name.strip():
        errs.append("name is required (text)")

    budget = body.get("budget")
    if not _is_num(budget) or budget <= 0:
        errs.append("budget must be a number greater than 0")

    dates = {}
    for key in ("startDate", "deadline"):
        try:
            dates[key] = date.fromisoformat(str(body.get(key)))
        except ValueError:
            errs.append(f"{key} must be a date in YYYY-MM-DD format")
    if len(dates) == 2 and dates["deadline"] <= dates["startDate"]:
        errs.append("deadline must be after startDate")

    team = body.get("teamSize")
    if not isinstance(team, int) or isinstance(team, bool) or team < 1:
        errs.append("teamSize must be a whole number >= 1")

    resources, seen = [], set()
    raw = body.get("resources")
    if not isinstance(raw, list) or not raw:
        errs.append("resources must be a non-empty list of {role, count, costPerDay}")
    else:
        for i, r in enumerate(raw, 1):
            role = r.get("role") if isinstance(r, dict) else None
            count = r.get("count") if isinstance(r, dict) else None
            rate = r.get("costPerDay") if isinstance(r, dict) else None
            if not isinstance(role, str) or not role.strip():
                errs.append(f"resources[{i}]: role is required")
            elif role.strip().lower() in seen:
                errs.append(f"resources[{i}]: role '{role}' is duplicated")
            elif not isinstance(count, int) or isinstance(count, bool) or count < 1:
                errs.append(f"resources[{i}]: count must be a whole number >= 1")
            elif not _is_num(rate) or rate < 0:
                errs.append(f"resources[{i}]: costPerDay must be a number >= 0")
            else:
                seen.add(role.strip().lower())
                resources.append({"role": role.strip(), "count": count, "costPerDay": rate})

    for key in ("deliverables", "constraints", "pastProjects"):
        if body.get(key) is not None and not isinstance(body.get(key), list):
            errs.append(f"{key} must be a list")

    if errs:
        raise ValidationError(errs)

    return {
        "name": name.strip(),
        "description": str(body.get("description") or "").strip(),
        "projectType": str(body.get("projectType") or "General").strip(),
        "budget": budget,
        "currency": str(body.get("currency") or "INR").strip(),
        "startDate": dates["startDate"].isoformat(),
        "deadline": dates["deadline"].isoformat(),
        "teamSize": team,
        "resources": resources,
        "deliverables": [str(d) for d in body.get("deliverables") or []],
        "constraints": [str(c) for c in body.get("constraints") or []],
        "pastProjects": [p for p in body.get("pastProjects") or [] if isinstance(p, dict)],
    }
