"""Тесты KPI (src/kpi.py). Версия v0.5 (шаг 6)."""

import json

import pytest

from src.schema import Scenario
from src.simulate import run_simulation
from src.kpi import compute_kpi

SCENARIO_PATH = "scenarios/yemen_vendor.json"
WEATHER_CSV = "tests/data/tmy_sanaa_pvgis_sarah3.csv"


def yemen_dict() -> dict:
    with open(SCENARIO_PATH, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def yemen_run():
    scenario = Scenario.model_validate(yemen_dict())
    sim = run_simulation(scenario, weather_csv=WEATHER_CSV, write_outputs=False)
    return scenario, sim


def test_yemen_kpi_consistency(yemen_run):
    """KPI согласованы с manifest и физикой: LPSP=0, поставка = спрос,
    renewable fraction = 1 - дизель/поставка."""
    scenario, sim = yemen_run
    kpi = compute_kpi(scenario, sim)
    totals = sim.manifest["totals_kwh"]

    assert kpi.lpsp == 0.0
    assert kpi.served_kwh == kpi.load_kwh
    assert kpi.dg_kwh == totals["dg"]
    assert kpi.renewable_fraction == pytest.approx(1 - totals["dg"] / totals["load"])
    assert kpi.dg_fuel_usd == pytest.approx(totals["dg"] * 0.26)
    # Дизель работает тысячи часов в году, но не круглый год.
    assert 0 < kpi.dg_hours < 8760


def test_liters_only_with_specific_consumption(yemen_run):
    """Литры не выдумываются: без удельного расхода — None,
    с расходом 0.27 л/кВт*ч — ровно dg_kwh * 0.27."""
    scenario, sim = yemen_run
    assert compute_kpi(scenario, sim).dg_fuel_liters is None

    data = yemen_dict()
    data["diesel"]["fuel_liters_per_kwh"] = 0.27
    scenario2 = Scenario.model_validate(data)
    kpi2 = compute_kpi(scenario2, sim)
    assert kpi2.dg_fuel_liters == pytest.approx(kpi2.dg_kwh * 0.27)


def test_kpi_without_diesel():
    """PV+BESS без дизеля: renewable fraction = 100% поставленной
    энергии, топливо 0, недопоставка честно > 0."""
    data = yemen_dict()
    del data["diesel"]
    scenario = Scenario.model_validate(data)
    sim = run_simulation(scenario, weather_csv=WEATHER_CSV, write_outputs=False)
    kpi = compute_kpi(scenario, sim)

    assert kpi.dg_kwh == 0.0
    assert kpi.dg_fuel_usd == 0.0
    assert kpi.dg_fuel_liters is None
    assert kpi.renewable_fraction == 1.0
    assert kpi.lpsp > 0
    assert kpi.served_kwh == pytest.approx(kpi.load_kwh - kpi.shortfall_kwh)


def test_curtail_fraction_none_without_pv():
    """Дизель-онли: выработки PV нет — доля сброса не 0/0, а None."""
    data = yemen_dict()
    del data["pv"]
    del data["battery"]
    scenario = Scenario.model_validate(data)
    sim = run_simulation(scenario, write_outputs=False)
    kpi = compute_kpi(scenario, sim)
    assert kpi.pv_gen_kwh == 0.0
    assert kpi.curtail_fraction_of_pv is None
