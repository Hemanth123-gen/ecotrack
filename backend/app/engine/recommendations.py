"""Rank reduction actions by how much they would actually save for this footprint."""

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel

from .analysis import annualize_kg
from .calculator import EmissionResult
from .factors import FactorDB, default_db
from .scenarios import simulate_reduction, simulate_switch

Effort = Literal["low", "medium", "high"]


@dataclass(frozen=True)
class Action:
    id: str
    title: str
    applies_to: str  # factor key this action targets
    switch_to: str | None  # None means "reduce" rather than "switch"
    fraction: float
    effort: Effort
    tip: str


CATALOG: list[Action] = [
    Action("car_petrol_to_metro", "Take public transport for half your car trips", "car_petrol", "metro", 0.5, "medium",
           "Metro or bus for the daily commute; keep the car for trips with no transit option."),
    Action("car_diesel_to_metro", "Take public transport for half your car trips", "car_diesel", "metro", 0.5, "medium",
           "Metro or bus for the daily commute; keep the car for trips with no transit option."),
    Action("car_petrol_to_ev", "Switch to an electric car", "car_petrol", "car_ev", 1.0, "high",
           "Best at your next vehicle purchase; pairs well with rooftop solar."),
    Action("taxi_to_metro", "Replace half your cab rides with metro/bus", "taxi", "metro", 0.5, "low",
           "Use metro for predictable routes and cabs for the last mile only."),
    Action("two_wheeler_to_ev", "Switch to an electric two-wheeler", "two_wheeler_petrol", "two_wheeler_ev", 1.0, "medium",
           "E-scooters are also cheaper to run per km in India."),
    Action("flight_to_train", "Take the train instead of half your domestic flights", "flight_domestic", "train", 0.5, "medium",
           "Overnight trains work well for routes under ~800 km."),
    Action("beef_to_chicken", "Replace half your beef with chicken", "beef", "chicken", 0.5, "low",
           "Ruminant meat has the highest footprint of any food."),
    Action("mutton_to_chicken", "Replace half your mutton with chicken", "mutton", "chicken", 0.5, "low",
           "Ruminant meat has the highest footprint of any food."),
    Action("chicken_to_pulses", "Replace half your chicken with dal/pulses", "chicken", "pulses", 0.5, "low",
           "Pulses deliver protein at a fraction of the emissions."),
    Action("paneer_to_pulses", "Replace a third of your paneer/cheese with pulses", "paneer_cheese", "pulses", 0.33, "low",
           "Dairy-heavy dishes add up quickly."),
    Action("electricity_efficiency", "Cut electricity use by 15%", "electricity_grid", None, 0.15, "low",
           "LED lights, AC at 24-26 C, 5-star rated appliances, switch off standby loads."),
    Action("electricity_solar", "Cover half your electricity with rooftop solar", "electricity_grid",
           "electricity_rooftop_solar", 0.5, "high",
           "PM Surya Ghar subsidy can cut the upfront cost for households."),
    Action("lpg_efficiency", "Cut cooking gas use by 10%", "lpg", None, 0.10, "low",
           "Pressure cookers, lids on pans, and soaking grains first."),
    Action("waste_recycle", "Recycle or compost half your landfill waste", "waste_landfill", "waste_recycled", 0.5, "low",
           "Segregate wet and dry waste at source."),
]


class Recommendation(BaseModel):
    id: str
    title: str
    effort: Effort
    tip: str
    saved_kg_period: float
    saved_kg_per_year: float
    saved_pct: float


def recommend(
    results: list[EmissionResult],
    period_days: int = 30,
    top_n: int = 5,
    db: FactorDB | None = None,
) -> list[Recommendation]:
    db = db or default_db()
    present = {r.factor.key for r in results}
    recs = []
    for action in CATALOG:
        if action.applies_to not in present:
            continue
        if action.switch_to:
            sim = simulate_switch(results, action.applies_to, action.switch_to, action.fraction, db)
        else:
            sim = simulate_reduction(results, action.applies_to, action.fraction)
        if sim.saved_kg <= 0:
            continue
        recs.append(Recommendation(
            id=action.id,
            title=action.title,
            effort=action.effort,
            tip=action.tip,
            saved_kg_period=sim.saved_kg,
            saved_kg_per_year=annualize_kg(sim.saved_kg, period_days),
            saved_pct=sim.saved_pct,
        ))
    return sorted(recs, key=lambda r: r.saved_kg_period, reverse=True)[:top_n]
