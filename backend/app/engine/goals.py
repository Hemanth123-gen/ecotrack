"""Reduction goals: baseline, a linear glide path to the target, and progress against it."""

from collections import defaultdict
from datetime import date, timedelta
from typing import Literal

from pydantic import BaseModel

from .calculator import EmissionResult

PACE_WINDOW_DAYS = 30
MIN_DAYS_WITH_DATA = 7

GoalStatus = Literal["achieved", "on_track", "behind", "not_enough_data"]


class Goal(BaseModel):
    baseline_t_per_year: float
    target_t_per_year: float
    start_date: date
    target_date: date


class Pace(BaseModel):
    t_per_year: float | None  # None when there is too little data to trust
    days_with_data: int


class GoalProgressPoint(BaseModel):
    date: date
    actual_t_per_year: float | None
    planned_t_per_year: float


class GoalProgress(BaseModel):
    goal: Goal
    status: GoalStatus
    current_t_per_year: float | None
    planned_t_per_year_today: float
    reduction_achieved_pct: float | None  # share of the targeted reduction achieved so far
    elapsed_pct: float
    days_left: int
    days_with_data: int
    series: list[GoalProgressPoint]


def _daily(results: list[EmissionResult]) -> dict[date, float]:
    totals: dict[date, float] = defaultdict(float)
    for r in results:
        if r.activity.occurred_on:
            totals[r.activity.occurred_on] += r.kg_co2e
    return totals


def trailing_pace(daily: dict[date, float], end: date, window: int = PACE_WINDOW_DAYS) -> Pace:
    """Annualised emissions over the trailing window.

    Divides by the span since the first logged day in the window rather than the whole window, so a
    user who started logging 10 days ago isn't credited with 20 empty days.
    """
    start = end - timedelta(days=window - 1)
    days = sorted(d for d in daily if start <= d <= end)
    if len(days) < MIN_DAYS_WITH_DATA:
        return Pace(t_per_year=None, days_with_data=len(days))
    span = (end - days[0]).days + 1
    kg = sum(daily[d] for d in days)
    return Pace(t_per_year=kg / span * 365 / 1000, days_with_data=len(days))


def baseline_pace(results: list[EmissionResult], today: date | None = None) -> Pace:
    return trailing_pace(_daily(results), today or date.today())


def planned_t(goal: Goal, on: date) -> float:
    if on <= goal.start_date:
        return goal.baseline_t_per_year
    if on >= goal.target_date:
        return goal.target_t_per_year
    frac = (on - goal.start_date).days / (goal.target_date - goal.start_date).days
    return goal.baseline_t_per_year + (goal.target_t_per_year - goal.baseline_t_per_year) * frac


def goal_progress(goal: Goal, results: list[EmissionResult], today: date | None = None) -> GoalProgress:
    today = today or date.today()
    daily = _daily(results)
    pace = trailing_pace(daily, today)
    planned_now = planned_t(goal, today)

    if pace.t_per_year is None:
        status: GoalStatus = "not_enough_data"
    elif pace.t_per_year <= goal.target_t_per_year:
        status = "achieved"
    elif pace.t_per_year <= planned_now:
        status = "on_track"
    else:
        status = "behind"

    wanted = goal.baseline_t_per_year - goal.target_t_per_year
    achieved_pct = (
        (goal.baseline_t_per_year - pace.t_per_year) / wanted * 100
        if pace.t_per_year is not None and wanted > 0
        else None
    )
    total_days = max((goal.target_date - goal.start_date).days, 1)
    elapsed = min(max((today - goal.start_date).days / total_days, 0), 1)

    # Weekly points from four weeks before the goal started up to today
    # Weekly points from four weeks before the goal started, through today (actual pace), then on along the plan
    # to the target date so the chart shows the road ahead
    series = []
    point = today
    first = goal.start_date - timedelta(weeks=4)
    while point >= first:
        series.append(GoalProgressPoint(
            date=point,
            actual_t_per_year=trailing_pace(daily, point).t_per_year,
            planned_t_per_year=planned_t(goal, point),
        ))
        point -= timedelta(weeks=1)
    series.reverse()
    point = today + timedelta(weeks=1)
    while point < goal.target_date:
        series.append(GoalProgressPoint(date=point, actual_t_per_year=None, planned_t_per_year=planned_t(goal, point)))
        point += timedelta(weeks=1)
    if goal.target_date > today:
        series.append(GoalProgressPoint(
            date=goal.target_date, actual_t_per_year=None, planned_t_per_year=goal.target_t_per_year,
        ))

    return GoalProgress(
        goal=goal,
        status=status,
        current_t_per_year=pace.t_per_year,
        planned_t_per_year_today=planned_now,
        reduction_achieved_pct=achieved_pct,
        elapsed_pct=elapsed * 100,
        days_left=max((goal.target_date - today).days, 0),
        days_with_data=pace.days_with_data,
        series=series,
    )
