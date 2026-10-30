"""Turn raw emission results into an understandable footprint summary."""

from collections import defaultdict
from datetime import date, timedelta

from pydantic import BaseModel

from .calculator import EmissionResult

# Approximate annual per-capita benchmarks in tonnes CO2e.
BENCHMARKS_T_PER_YEAR = {
    "india_average": 2.0,
    "world_average": 4.7,
    "paris_1_5c_target_2030": 2.3,
}


class CategoryShare(BaseModel):
    category: str
    kg_co2e: float
    share: float  # 0..1


class Hotspot(BaseModel):
    key: str
    label: str
    kg_co2e: float
    share: float


class BenchmarkComparison(BaseModel):
    name: str
    benchmark_t_per_year: float
    ratio: float  # your annualised footprint / benchmark


class FootprintSummary(BaseModel):
    total_kg_co2e: float
    period_days: int
    annualized_t_co2e: float
    by_category: list[CategoryShare]
    by_scope: dict[int, float]
    hotspots: list[Hotspot]
    benchmarks: list[BenchmarkComparison]


def annualize_kg(kg: float, period_days: int) -> float:
    return kg * 365 / period_days


MIN_SPAN_DAYS = 7


def logged_span_days(results: list[EmissionResult], window_days: int, today: date | None = None) -> int:
    """Days to annualise over: from the first logged day in the window to today.

    Someone who started logging 10 days ago shouldn't have their year estimated as if the other 20 days of a
    30-day window were zero-emission. Floored at a week so a single logged day doesn't extrapolate wildly.
    """
    days = [r.activity.occurred_on for r in results if r.activity.occurred_on]
    if not days:
        return window_days
    span = ((today or date.today()) - min(days)).days + 1
    return max(min(span, window_days), min(MIN_SPAN_DAYS, window_days))


def summarize(
    results: list[EmissionResult],
    period_days: int = 30,
    top_n: int = 3,
    per_capita: bool = True,
    annualize_over_days: int | None = None,
) -> FootprintSummary:
    """Summarise emissions over `period_days`.

    Set `per_capita=False` for organisations, where personal benchmarks don't apply. The annual estimate is
    scaled from `annualize_over_days` (default: the whole period); see `logged_span_days`.
    """
    if period_days <= 0:
        raise ValueError("period_days must be positive")

    total = sum(r.kg_co2e for r in results)
    by_cat: dict[str, float] = defaultdict(float)
    by_scope: dict[int, float] = defaultdict(float)
    by_key: dict[str, float] = defaultdict(float)
    labels: dict[str, str] = {}
    for r in results:
        by_cat[r.factor.category] += r.kg_co2e
        by_scope[r.factor.scope] += r.kg_co2e
        by_key[r.factor.key] += r.kg_co2e
        labels[r.factor.key] = r.factor.label

    def share(kg: float) -> float:
        return kg / total if total else 0.0

    annual_t = annualize_kg(total, annualize_over_days or period_days) / 1000
    return FootprintSummary(
        total_kg_co2e=total,
        period_days=period_days,
        annualized_t_co2e=annual_t,
        by_category=sorted(
            (CategoryShare(category=c, kg_co2e=kg, share=share(kg)) for c, kg in by_cat.items()),
            key=lambda c: c.kg_co2e,
            reverse=True,
        ),
        by_scope=dict(sorted(by_scope.items())),
        hotspots=[
            Hotspot(key=k, label=labels[k], kg_co2e=kg, share=share(kg))
            for k, kg in sorted(by_key.items(), key=lambda kv: kv[1], reverse=True)[:top_n]
        ],
        benchmarks=[
            BenchmarkComparison(name=name, benchmark_t_per_year=t, ratio=annual_t / t)
            for name, t in BENCHMARKS_T_PER_YEAR.items()
        ]
        if per_capita
        else [],
    )


class DailyPoint(BaseModel):
    date: date
    total_kg_co2e: float
    by_category: dict[str, float]


def daily_series(results: list[EmissionResult], days: int, end: date | None = None) -> list[DailyPoint]:
    """One zero-filled point per day for the `days` days ending on `end` (default today)."""
    end = end or date.today()
    start = end - timedelta(days=days - 1)
    buckets: dict[date, dict[str, float]] = {start + timedelta(d): defaultdict(float) for d in range(days)}
    for r in results:
        day = r.activity.occurred_on
        if day in buckets:
            buckets[day][r.factor.category] += r.kg_co2e
    return [
        DailyPoint(date=day, total_kg_co2e=sum(cats.values()), by_category=dict(cats))
        for day, cats in buckets.items()
    ]
