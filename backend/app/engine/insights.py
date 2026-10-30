"""Week-over-week insights, computed deterministically so the agent can narrate them safely."""

from collections import defaultdict
from datetime import date, timedelta

from pydantic import BaseModel

from .calculator import EmissionResult


class CategoryChange(BaseModel):
    category: str
    this_week_kg: float
    last_week_kg: float
    change_kg: float


class TopActivity(BaseModel):
    key: str
    label: str
    kg_co2e: float
    share: float


class WeeklyInsights(BaseModel):
    week_start: date
    week_end: date
    this_week_kg: float
    last_week_kg: float
    change_kg: float
    change_pct: float | None  # None when there is no previous week to compare with
    days_logged_this_week: int
    by_category: list[CategoryChange]
    top_activity: TopActivity | None
    highlights: list[str]


def _fmt(kg: float) -> str:
    return f"{kg / 1000:.2f} t" if abs(kg) >= 1000 else f"{kg:.1f} kg"


def weekly_insights(results: list[EmissionResult], today: date | None = None) -> WeeklyInsights:
    """Compare the last 7 days (ending today) with the 7 days before."""
    today = today or date.today()
    week_start = today - timedelta(days=6)
    prev_start = week_start - timedelta(days=7)

    this_cat: dict[str, float] = defaultdict(float)
    last_cat: dict[str, float] = defaultdict(float)
    by_key: dict[str, float] = defaultdict(float)
    labels: dict[str, str] = {}
    logged: set[date] = set()
    for r in results:
        d = r.activity.occurred_on
        if d is None:
            continue
        if week_start <= d <= today:
            this_cat[r.factor.category] += r.kg_co2e
            by_key[r.factor.key] += r.kg_co2e
            labels[r.factor.key] = r.factor.label
            logged.add(d)
        elif prev_start <= d < week_start:
            last_cat[r.factor.category] += r.kg_co2e

    this_kg, last_kg = sum(this_cat.values()), sum(last_cat.values())
    change = this_kg - last_kg
    change_pct = change / last_kg * 100 if last_kg else None
    changes = sorted(
        (
            CategoryChange(category=c, this_week_kg=this_cat[c], last_week_kg=last_cat[c],
                           change_kg=this_cat[c] - last_cat[c])
            for c in set(this_cat) | set(last_cat)
        ),
        key=lambda c: abs(c.change_kg),
        reverse=True,
    )
    top = None
    if by_key:
        key, kg = max(by_key.items(), key=lambda kv: kv[1])
        top = TopActivity(key=key, label=labels[key], kg_co2e=kg, share=kg / this_kg if this_kg else 0)

    highlights: list[str] = []
    if not this_kg and not last_kg:
        highlights.append("Nothing logged in the last two weeks yet.")
    elif change_pct is None:
        highlights.append(f"{_fmt(this_kg)} CO2e this week. Next week you'll get a week-over-week comparison.")
    elif abs(change_pct) < 3:
        highlights.append(f"About the same as last week ({_fmt(this_kg)} CO2e).")
    else:
        direction = "Down" if change < 0 else "Up"
        highlights.append(f"{direction} {abs(change_pct):.0f}% from last week ({'-' if change < 0 else '+'}{_fmt(abs(change))}).")
    if last_kg:
        drop = min(changes, key=lambda c: c.change_kg)
        rise = max(changes, key=lambda c: c.change_kg)
        if drop.change_kg < -0.5:
            highlights.append(f"Biggest drop: {drop.category.capitalize()} (-{_fmt(-drop.change_kg)}).")
        if rise.change_kg > 0.5:
            highlights.append(f"Biggest rise: {rise.category.capitalize()} (+{_fmt(rise.change_kg)}).")
    if top:
        highlights.append(f"Top source this week: {top.label} ({_fmt(top.kg_co2e)}, {top.share:.0%}).")
    if this_kg or last_kg:
        highlights.append(
            f"You logged on {len(logged)} of 7 days."
            + (" Log more days for reliable trends." if len(logged) < 4 else "")
        )

    return WeeklyInsights(
        week_start=week_start,
        week_end=today,
        this_week_kg=this_kg,
        last_week_kg=last_kg,
        change_kg=change,
        change_pct=change_pct,
        days_logged_this_week=len(logged),
        by_category=changes,
        top_activity=top,
        highlights=highlights,
    )
