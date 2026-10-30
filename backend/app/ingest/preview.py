"""Validate imported rows into a reviewable preview. Nothing is saved until the user confirms."""

from datetime import date
from typing import Any

from pydantic import BaseModel, ValidationError

from ..engine import Activity, FactorDB, FactorNotFound, UnitError, calculate


class ImportItem(BaseModel):
    key: str
    quantity: float | None
    unit: str
    occurred_on: date | None = None
    description: str | None = None
    label: str | None = None
    category: str | None = None
    kg_co2e: float | None = None
    confidence: float | None = None  # set by document extraction
    error: str | None = None


def resolve_key(value: str, factors: FactorDB) -> str:
    """Accept a factor key or its human label ("Petrol car"), case-insensitively."""
    v = value.strip()
    keys = factors.keys()
    if v in keys:
        return v
    norm = v.lower().replace(" ", "_").replace("-", "_")
    if norm in keys:
        return norm
    for f in factors.list():
        if f.label.lower() == v.lower():
            return f.key
    return v


def preview_item(raw: dict[str, Any], region: str, factors: FactorDB) -> ImportItem:
    key = resolve_key(str(raw.get("key") or ""), factors)
    base = {
        "key": key,
        "unit": str(raw.get("unit") or ""),
        "description": raw.get("description") or None,
        "confidence": raw.get("confidence"),
    }
    try:
        quantity = float(raw.get("quantity"))
    except (TypeError, ValueError):
        return ImportItem(**base, quantity=None, error=f"Invalid quantity '{raw.get('quantity')}'")
    occurred_on = raw.get("occurred_on") or None
    try:
        activity = Activity(key=key, quantity=quantity, unit=base["unit"], region=region, occurred_on=occurred_on)
        if activity.occurred_on and activity.occurred_on > date.today():
            raise ValueError("Date is in the future")
        result = calculate(activity, factors)
    except ValidationError as e:
        msg = "; ".join(f"{'.'.join(map(str, err['loc']))}: {err['msg']}" for err in e.errors())
        return ImportItem(**base, quantity=quantity, error=msg)
    except (FactorNotFound, UnitError, ValueError) as e:
        return ImportItem(**base, quantity=quantity, error=str(e).strip('"'))
    return ImportItem(
        **base,
        quantity=quantity,
        occurred_on=activity.occurred_on,
        label=result.factor.label,
        category=result.factor.category,
        kg_co2e=result.kg_co2e,
    )
