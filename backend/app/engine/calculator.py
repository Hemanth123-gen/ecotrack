"""Deterministic emission calculation. The LLM never does this math itself."""

from datetime import date

from pydantic import BaseModel, Field

from .factors import EmissionFactor, FactorDB, default_db
from .units import convert


class Activity(BaseModel):
    key: str  # emission factor key, e.g. "car_petrol"
    quantity: float = Field(ge=0)
    unit: str
    region: str = "IN"
    occurred_on: date | None = None
    description: str | None = None


class EmissionResult(BaseModel):
    activity: Activity
    factor: EmissionFactor
    quantity_in_factor_unit: float
    kg_co2e: float


def calculate(activity: Activity, db: FactorDB | None = None) -> EmissionResult:
    db = db or default_db()
    factor = db.get(activity.key, activity.region)
    qty = convert(activity.quantity, activity.unit, factor.unit)
    return EmissionResult(
        activity=activity,
        factor=factor,
        quantity_in_factor_unit=qty,
        kg_co2e=qty * factor.value,
    )


def calculate_many(activities: list[Activity], db: FactorDB | None = None) -> list[EmissionResult]:
    return [calculate(a, db) for a in activities]
