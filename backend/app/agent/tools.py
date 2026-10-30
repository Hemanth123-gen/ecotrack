"""Tools the LLM can call. Every number the agent reports comes from here."""

from collections.abc import Callable
from datetime import date, timedelta
from typing import Any

from google.genai import types
from pydantic import ValidationError

from ..engine import (
    Activity,
    FactorNotFound,
    Goal,
    UnitError,
    baseline_pace,
    calculate,
    goal_progress,
    logged_span_days,
    recommend,
    simulate_reduction,
    simulate_switch,
    summarize,
    weekly_insights,
)
from ..engine.goals import MIN_DAYS_WITH_DATA, PACE_WINDOW_DAYS
from ..store import NotFound, Store

_ACTIVITY = {
    "type": "object",
    "properties": {
        "key": {"type": "string", "description": "Emission factor key from the catalog, e.g. car_petrol."},
        "quantity": {"type": "number", "description": "Amount of the activity, >= 0."},
        "unit": {"type": "string", "description": "Unit, e.g. km, kWh, units, kg, g, litre, cylinder, scm, item."},
        "occurred_on": {"type": "string", "description": "ISO date YYYY-MM-DD. Omit for today."},
        "description": {"type": "string", "description": "Short note in the user's own words."},
    },
    "required": ["key", "quantity", "unit"],
}
_ACTIVITIES = {"type": "array", "items": _ACTIVITY, "minItems": 1}
_DAYS = {"type": "integer", "minimum": 1, "maximum": 366, "description": "Look-back window in days (default 30)."}


def _round(value: Any) -> Any:
    """Keep tool output compact so the model isn't tempted to echo long decimals."""
    if isinstance(value, float):
        return round(value, 3)
    if isinstance(value, dict):
        return {k: _round(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_round(v) for v in value]
    return value


class Toolbox:
    def __init__(self, store: Store, user_id: str):
        self.store = store
        self.user = store.get_user(user_id)
        self._tools: dict[str, tuple[str, dict, Callable[..., dict]]] = {
            "log_activities": (
                "Save one or more activities the user did to their footprint log and return the emissions of each.",
                {"type": "object", "properties": {"activities": _ACTIVITIES}, "required": ["activities"]},
                self.log_activities,
            ),
            "estimate_emissions": (
                "Calculate emissions for hypothetical activities WITHOUT saving them "
                "(e.g. 'how much CO2 is a flight to Delhi?').",
                {"type": "object", "properties": {"activities": _ACTIVITIES}, "required": ["activities"]},
                self.estimate_emissions,
            ),
            "get_footprint_summary": (
                "Summarise the user's logged footprint: total, annualised estimate, breakdown by category and "
                "GHG scope, top hotspots, and comparison with benchmarks.",
                {"type": "object", "properties": {"days": _DAYS}},
                self.get_footprint_summary,
            ),
            "list_recent_activities": (
                "List the user's logged activities, newest first, with their ids and emissions.",
                {"type": "object", "properties": {
                    "days": _DAYS,
                    "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                }},
                self.list_recent_activities,
            ),
            "delete_activity": (
                "Delete a logged activity by id, e.g. when the user says an entry was wrong.",
                {"type": "object", "properties": {"activity_id": {"type": "integer"}}, "required": ["activity_id"]},
                self.delete_activity,
            ),
            "simulate_scenario": (
                "What-if analysis on the user's logged footprint. kind='switch' moves a fraction of from_key "
                "activity onto to_key (same unit type, e.g. car_petrol -> metro). kind='reduce' cuts a fraction "
                "of from_key.",
                {"type": "object", "properties": {
                    "kind": {"type": "string", "enum": ["switch", "reduce"]},
                    "from_key": {"type": "string"},
                    "to_key": {"type": "string", "description": "Required when kind='switch'."},
                    "fraction": {"type": "number", "minimum": 0, "maximum": 1},
                    "days": _DAYS,
                }, "required": ["kind", "from_key", "fraction"]},
                self.simulate_scenario,
            ),
            "set_goal": (
                "Set (or replace) the user's reduction goal. Give reduction_pct OR target_t_per_year. The baseline "
                "is measured from the last 30 days of logged activity unless baseline_t_per_year is given. Only "
                "call this when the user asks for a goal and has agreed to its numbers.",
                {"type": "object", "properties": {
                    "target_date": {"type": "string", "description": "YYYY-MM-DD, in the future."},
                    "reduction_pct": {"type": "number", "exclusiveMinimum": 0, "exclusiveMaximum": 100},
                    "target_t_per_year": {"type": "number", "exclusiveMinimum": 0},
                    "baseline_t_per_year": {"type": "number", "exclusiveMinimum": 0},
                }, "required": ["target_date"]},
                self.set_goal,
            ),
            "get_goal_progress": (
                "The user's goal and progress: current annual pace vs the planned glide path, status "
                "(achieved / on_track / behind / not_enough_data) and days left.",
                {"type": "object", "properties": {}},
                self.get_goal_progress,
            ),
            "get_weekly_insights": (
                "Compare the last 7 days with the 7 days before: totals, change by category, top source this "
                "week and how many days were logged.",
                {"type": "object", "properties": {}},
                self.get_weekly_insights,
            ),
            "get_recommendations": (
                "Reduction actions ranked by how much CO2e they would save for this user's logged footprint.",
                {"type": "object", "properties": {
                    "days": _DAYS,
                    "top_n": {"type": "integer", "minimum": 1, "maximum": 10},
                }},
                self.get_recommendations,
            ),
        }

    def declarations(self) -> list[types.FunctionDeclaration]:
        return [
            types.FunctionDeclaration(name=name, description=desc, parameters_json_schema=schema)
            for name, (desc, schema, _) in self._tools.items()
        ]

    def execute(self, name: str, args: dict | None) -> dict:
        """Run a tool. Errors are returned to the model so it can correct itself."""
        if name not in self._tools:
            return {"error": f"Unknown tool '{name}'"}
        try:
            return _round(self._tools[name][2](**(args or {})))
        except (FactorNotFound, UnitError, NotFound, ValidationError, ValueError, TypeError) as e:
            return {"error": str(e)}

    def _activity(self, raw: dict) -> Activity:
        return Activity(**{**raw, "region": self.user.region})

    # tool implementations

    def log_activities(self, activities: list[dict]) -> dict:
        saved, errors = [], []
        for raw in activities:
            try:
                saved.append(self.store.add_activity(self.user.id, self._activity(raw)).model_dump(mode="json"))
            except (FactorNotFound, UnitError, ValidationError, ValueError) as e:
                errors.append({"input": raw, "error": str(e)})
        return {"saved": saved, "errors": errors, "total_kg_co2e": sum(a["kg_co2e"] for a in saved)}

    def estimate_emissions(self, activities: list[dict]) -> dict:
        results = [calculate(self._activity(raw), self.store.factors) for raw in activities]
        return {
            "items": [
                {"key": r.factor.key, "label": r.factor.label, "quantity": r.activity.quantity,
                 "unit": r.activity.unit, "kg_co2e": r.kg_co2e, "factor_source": r.factor.source}
                for r in results
            ],
            "total_kg_co2e": sum(r.kg_co2e for r in results),
        }

    def get_footprint_summary(self, days: int = 30) -> dict:
        results = self.store.emission_results(self.user.id, days)
        span = logged_span_days(results, days)
        summary = summarize(results, days, per_capita=self.user.kind == "individual", annualize_over_days=span)
        days_with_data = len({r.activity.occurred_on for r in results})
        return {
            **summary.model_dump(mode="json"),
            "activities_count": len(results),
            "days_with_data": days_with_data,
            "annualized_over_days": span,
            "user_kind": self.user.kind,
        }

    def list_recent_activities(self, days: int = 30, limit: int = 20) -> dict:
        items = self.store.list_activities(self.user.id, days, limit)
        return {"activities": [a.model_dump(mode="json") for a in items]}

    def delete_activity(self, activity_id: int) -> dict:
        self.store.delete_activity(self.user.id, activity_id)
        return {"deleted": activity_id}

    def simulate_scenario(
        self, kind: str, from_key: str, fraction: float, to_key: str | None = None, days: int = 30
    ) -> dict:
        results = self.store.emission_results(self.user.id, days)
        if not any(r.factor.key == from_key for r in results):
            return {"error": f"No '{from_key}' activities logged in the last {days} days to simulate on. "
                             "Use estimate_emissions for hypothetical activities instead."}
        if kind == "switch":
            if not to_key:
                raise ValueError("to_key is required when kind='switch'")
            sim = simulate_switch(results, from_key, to_key, fraction, self.store.factors)
        elif kind == "reduce":
            sim = simulate_reduction(results, from_key, fraction)
        else:
            raise ValueError("kind must be 'switch' or 'reduce'")
        span = logged_span_days(results, days)
        return {**sim.model_dump(), "saved_kg_per_year": sim.saved_kg * 365 / span, "days": days}

    def set_goal(
        self,
        target_date: str,
        reduction_pct: float | None = None,
        target_t_per_year: float | None = None,
        baseline_t_per_year: float | None = None,
    ) -> dict:
        today = date.today()
        target_on = date.fromisoformat(target_date)
        if not today < target_on <= today + timedelta(days=366 * 10):
            raise ValueError("target_date must be in the future and within 10 years")
        if (reduction_pct is None) == (target_t_per_year is None):
            raise ValueError("Give exactly one of reduction_pct or target_t_per_year")

        if baseline_t_per_year is None:
            pace = baseline_pace(self.store.emission_results(self.user.id, PACE_WINDOW_DAYS), today)
            if pace.t_per_year is None:
                raise ValueError(
                    f"Need at least {MIN_DAYS_WITH_DATA} days of logged activity in the last {PACE_WINDOW_DAYS} days "
                    f"to measure a baseline (have {pace.days_with_data}). Log more, or pass baseline_t_per_year."
                )
            baseline_t_per_year = pace.t_per_year
        if reduction_pct is not None:
            if not 0 < reduction_pct < 100:
                raise ValueError("reduction_pct must be between 0 and 100")
            target_t_per_year = baseline_t_per_year * (1 - reduction_pct / 100)
        if not 0 < target_t_per_year < baseline_t_per_year:
            raise ValueError(
                f"Target ({target_t_per_year:.2f} t/yr) must be below the baseline ({baseline_t_per_year:.2f} t/yr)"
            )

        self.store.set_goal(self.user.id, Goal(
            baseline_t_per_year=baseline_t_per_year,
            target_t_per_year=target_t_per_year,
            start_date=today,
            target_date=target_on,
        ))
        return self.get_goal_progress()

    def get_goal_progress(self) -> dict:
        goal = self.store.get_goal(self.user.id)
        if goal is None:
            return {"goal": None, "message": "No goal set yet."}
        # Enough history for the pre-goal weeks of the chart plus a trailing pace window at each point
        days = min((date.today() - goal.start_date).days + 28 + PACE_WINDOW_DAYS, 366)
        return goal_progress(goal, self.store.emission_results(self.user.id, days)).model_dump(mode="json")

    def get_weekly_insights(self) -> dict:
        return weekly_insights(self.store.emission_results(self.user.id, 14)).model_dump(mode="json")

    def get_recommendations(self, days: int = 30, top_n: int = 5) -> dict:
        results = self.store.emission_results(self.user.id, days)
        recs = recommend(results, logged_span_days(results, days), top_n, self.store.factors)
        return {"recommendations": [r.model_dump() for r in recs], "days": days}
