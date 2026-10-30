"""What-if simulations: how much would a change in behaviour save?"""

from pydantic import BaseModel

from .calculator import EmissionResult
from .factors import FactorDB, default_db
from .units import convert


class ScenarioResult(BaseModel):
    description: str
    baseline_kg: float
    scenario_kg: float
    saved_kg: float
    saved_pct: float


def _result(description: str, baseline: float, scenario: float) -> ScenarioResult:
    saved = baseline - scenario
    return ScenarioResult(
        description=description,
        baseline_kg=baseline,
        scenario_kg=scenario,
        saved_kg=saved,
        saved_pct=saved / baseline * 100 if baseline else 0.0,
    )


def _check_fraction(fraction: float) -> None:
    if not 0 <= fraction <= 1:
        raise ValueError("fraction must be between 0 and 1")


def simulate_switch(
    results: list[EmissionResult],
    from_key: str,
    to_key: str,
    fraction: float = 1.0,
    db: FactorDB | None = None,
) -> ScenarioResult:
    """Move `fraction` of every `from_key` activity onto `to_key` (e.g. car -> metro)."""
    _check_fraction(fraction)
    db = db or default_db()
    baseline = sum(r.kg_co2e for r in results)
    scenario = baseline
    for r in results:
        if r.factor.key != from_key:
            continue
        target = db.get(to_key, r.activity.region)
        moved = r.quantity_in_factor_unit * fraction
        scenario += convert(moved, r.factor.unit, target.unit) * target.value - moved * r.factor.value
    return _result(f"Switch {fraction:.0%} of {from_key} to {to_key}", baseline, scenario)


def simulate_reduction(results: list[EmissionResult], key: str, fraction: float) -> ScenarioResult:
    """Cut `fraction` of every `key` activity (e.g. 15% less electricity)."""
    _check_fraction(fraction)
    baseline = sum(r.kg_co2e for r in results)
    cut = sum(r.kg_co2e for r in results if r.factor.key == key) * fraction
    return _result(f"Reduce {key} by {fraction:.0%}", baseline, baseline - cut)
