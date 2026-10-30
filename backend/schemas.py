"""Pydantic schema for the AI's risk answer. risk.finalize_risks applies the business rules afterwards."""
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic import ValidationError as PydanticError

from errors import AIOutputError

CATEGORIES = ("Time", "Cost", "Resource", "Scope", "Quality")


class RiskItem(BaseModel):
    model_config = ConfigDict(extra="ignore")  # AI-supplied score/level are ignored; code recalculates
    key: Optional[str] = None
    category: str
    description: str = Field(min_length=1)
    probability: int = Field(ge=1, le=5)
    impact: int = Field(ge=1, le=5)
    mitigation: List[str] = Field(min_length=1)
    owner: Optional[str] = None

    @field_validator("category", mode="before")
    @classmethod
    def _category(cls, v):
        match = {c.lower(): c for c in CATEGORIES}.get(str(v).strip().lower())
        if match is None:
            raise ValueError(f"must be one of {list(CATEGORIES)}")
        return match

    @field_validator("description", mode="before")
    @classmethod
    def _desc(cls, v):
        return v.strip() if isinstance(v, str) else v

    @field_validator("probability", "impact", mode="before")
    @classmethod
    def _rating(cls, v):
        if isinstance(v, bool):
            raise ValueError("must be a whole number from 1 to 5")
        return round(v) if isinstance(v, float) else v  # 3.0 -> 3; range is still enforced

    @field_validator("mitigation", mode="before")
    @classmethod
    def _mit(cls, v):
        if isinstance(v, str):
            v = [v]
        if isinstance(v, list):
            return [str(m).strip() for m in v if str(m).strip()][:3]
        return v

    @field_validator("key", "owner", mode="before")
    @classmethod
    def _text(cls, v):
        return None if v in (None, "") else str(v).strip()


class RiskResponse(BaseModel):
    risks: List[RiskItem] = Field(min_length=1)


def _messages(e):
    out = []
    for err in e.errors():
        loc = err["loc"]
        if len(loc) >= 2 and loc[0] == "risks" and isinstance(loc[1], int):
            where = f"risk #{loc[1] + 1}" + (f" {loc[2]}" if len(loc) > 2 else "")
        else:
            where = ".".join(map(str, loc)) or "response"
        msg = err["msg"].removeprefix("Value error, ")
        got = err.get("input")
        if len(loc) > 2 and isinstance(got, (int, float, str)) and len(str(got)) < 40:
            msg += f" (got {got!r})"
        out.append(f"{where}: {msg}")
    return out[:10]


def parse_risks(data):
    """Returns a list of clean dicts, or raises AIOutputError (which makes ai_service retry)."""
    try:
        return [r.model_dump() for r in RiskResponse.model_validate(data).risks]
    except PydanticError as e:
        raise AIOutputError(_messages(e)) from e