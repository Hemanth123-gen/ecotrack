import pytest

from app.engine import (
    Activity,
    FactorDB,
    FactorNotFound,
    UnitError,
    calculate,
    calculate_many,
    convert,
    default_db,
    recommend,
    simulate_reduction,
    simulate_switch,
    summarize,
)


@pytest.fixture
def month():
    """A typical urban Indian month."""
    return calculate_many([
        Activity(key="car_petrol", quantity=600, unit="km"),
        Activity(key="electricity_grid", quantity=250, unit="units"),
        Activity(key="lpg", quantity=1, unit="cylinder"),
        Activity(key="chicken", quantity=3, unit="kg"),
        Activity(key="waste_landfill", quantity=20, unit="kg"),
    ])


def test_factor_file_loads_and_is_sane():
    db = default_db()
    assert "electricity_grid" in db.keys()
    for f in db.list("IN"):
        assert f.value >= 0
        convert(1, f.unit, f.unit)  # every factor unit must be known


def test_region_specific_then_global_fallback():
    db = default_db()
    assert db.get("electricity_grid", "IN").value == pytest.approx(0.716)
    assert db.get("electricity_grid", "US").region == "GLOBAL"
    assert db.get("beef", "IN").region == "GLOBAL"


def test_unknown_factor_suggests_close_match():
    with pytest.raises(FactorNotFound, match="car_petrol"):
        default_db().get("car_petroll")


def test_unit_conversion():
    assert convert(10, "miles", "km") == pytest.approx(16.09344)
    assert convert(2, "cylinders", "kg") == pytest.approx(28.4)
    assert convert(500, "g", "kg") == pytest.approx(0.5)
    with pytest.raises(UnitError):
        convert(1, "km", "kg")
    with pytest.raises(UnitError):
        convert(1, "furlong", "km")


def test_calculate_basic():
    r = calculate(Activity(key="electricity_grid", quantity=100, unit="kWh"))
    assert r.kg_co2e == pytest.approx(71.6)
    assert r.factor.scope == 2


def test_calculate_converts_to_factor_unit():
    r = calculate(Activity(key="chicken", quantity=500, unit="g"))
    assert r.quantity_in_factor_unit == pytest.approx(0.5)
    assert r.kg_co2e == pytest.approx(3.45)


def test_negative_quantity_rejected():
    with pytest.raises(ValueError):
        Activity(key="car_petrol", quantity=-5, unit="km")


def test_summary(month):
    s = summarize(month, period_days=30)
    expected_total = 600 * 0.14 + 250 * 0.716 + 14.2 * 2.94 + 3 * 6.9 + 20 * 0.5
    assert s.total_kg_co2e == pytest.approx(expected_total)
    assert sum(c.share for c in s.by_category) == pytest.approx(1.0)
    assert s.by_category[0].category == "energy"
    assert s.hotspots[0].key == "electricity_grid"
    assert s.annualized_t_co2e == pytest.approx(expected_total * 365 / 30 / 1000)
    assert {b.name for b in s.benchmarks} >= {"india_average", "world_average"}
    assert set(s.by_scope) == {1, 2, 3}


def test_summary_for_organisation_has_no_per_capita_benchmarks(month):
    assert summarize(month, per_capita=False).benchmarks == []


def test_summary_empty():
    s = summarize([])
    assert s.total_kg_co2e == 0
    assert s.hotspots == []


def test_switch_scenario(month):
    sim = simulate_switch(month, "car_petrol", "metro", fraction=0.5)
    assert sim.saved_kg == pytest.approx(300 * (0.14 - 0.015))
    assert 0 < sim.saved_pct < 100


def test_switch_scenario_rejects_incompatible_units(month):
    with pytest.raises(UnitError):
        simulate_switch(month, "car_petrol", "chicken")


def test_reduction_scenario(month):
    sim = simulate_reduction(month, "electricity_grid", 0.2)
    assert sim.saved_kg == pytest.approx(250 * 0.716 * 0.2)
    with pytest.raises(ValueError):
        simulate_reduction(month, "electricity_grid", 1.5)


def test_recommendations_ranked_and_relevant(month):
    recs = recommend(month, period_days=30, top_n=10)
    assert recs, "expected at least one recommendation"
    savings = [r.saved_kg_period for r in recs]
    assert savings == sorted(savings, reverse=True)
    ids = {r.id for r in recs}
    assert "beef_to_chicken" not in ids  # no beef in this footprint
    assert "electricity_solar" in ids
    assert all(r.saved_kg_per_year == pytest.approx(r.saved_kg_period * 365 / 30) for r in recs)


def test_custom_factor_db():
    from app.engine.factors import EmissionFactor
    db = FactorDB([EmissionFactor(key="x", label="X", category="goods", scope=3, unit="item", value=2, source="t")])
    assert calculate(Activity(key="x", quantity=3, unit="items"), db).kg_co2e == 6
