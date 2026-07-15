"""Тесты оперативного резерва (operating reserve, B1).

Перенос формулы REopt (operating_reserve_constraints.jl): в каждый час
система обязана держать свободную мощность СВЕРХ выработки — недогруженный
дизель плюс доступный разряд батареи. Принципиальная замена прежнему
костылю diesel_firm_fraction: резерв требуется час за часом и может быть
обеспечен и батареей, а не только «дизелем на весь пик».
"""

import json

import pytest

from src.schema import Scenario
from src.optimize import optimize_sizing

WEATHER_CSV = "tests/data/tmy_sanaa_pvgis_sarah3.csv"
WEATHER_PHOENIX = "tests/data/tmy_phoenix.csv"
SCENARIO_PHOENIX = "scenarios/phoenix_hospital_test.json"


def load_dict(path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _diesel_only(tmp_path, reserve_frac: float | None) -> dict:
    """Игрушка: дизель-онли, 3 часа [100, 150, 120] kW, ставка 0."""
    csv = tmp_path / "toy3.csv"
    csv.write_text(
        "timestamp,load_kw\n"
        "2026-01-01 00:00,100\n2026-01-01 01:00,150\n2026-01-01 02:00,120\n",
        encoding="utf-8",
    )
    rel = {"mode": "hard"}
    if reserve_frac is not None:
        rel["operating_reserve_load_fraction"] = reserve_frac
    return {
        "name": "reserve-toy",
        "site": {"name": "x", "latitude": 15.28, "longitude": 44.08,
                 "timezone": "Asia/Aden"},
        "diesel": {"capex_usd_per_kw": 100, "om_usd_per_kw_year": 10,
                   "fuel_cost_usd_per_kwh": 0.26,
                   "min_kw": 0, "max_kw": 1000, "lifetime_years": 10},
        "load": {"profile_csv": str(csv)},
        "financial": {"discount_rate_fraction": 0.0, "project_years": 10,
                      "currency": "USD"},
        "reliability": rel,
    }


# ---------- ручной оптимум дизель-онли ----------

def test_diesel_only_reserve_hand_optimum(tmp_path):
    """Дизель-онли: покрывать нагрузку больше нечем, значит dg[t]==load[t].
    Резерв 50% нагрузки требует свободной мощности dg_kw - load[t] >=
    0.5*load[t] на каждом часе, т.е. dg_kw >= 1.5*пик = 1.5*150 = 225.
    Минимизация капитала упирается ровно в 225 kW."""
    scenario = Scenario.model_validate(_diesel_only(tmp_path, 0.5))
    res = optimize_sizing(scenario, write_outputs=False)
    assert res.sizes["dg_kw"] == pytest.approx(225, abs=1e-3)
    assert res.sim.manifest["totals_kwh"]["shortfall"] == pytest.approx(0)


def test_reserve_zero_is_noop(tmp_path):
    """Без резерва (поле не задано) дизель ровно на пик (hard) = 150 kW —
    подтверждает, что резерв это НАДСТРОЙКА, а не изменение базы."""
    scenario = Scenario.model_validate(_diesel_only(tmp_path, None))
    res = optimize_sizing(scenario, write_outputs=False)
    assert res.sizes["dg_kw"] == pytest.approx(150, abs=1e-3)


def test_reserve_scales_with_fraction(tmp_path):
    """Больше требуемая доля резерва — больше установленный дизель:
    0.2 -> 180, 0.5 -> 225 (оба = (1+доля)*пик)."""
    r20 = optimize_sizing(Scenario.model_validate(_diesel_only(tmp_path, 0.2)),
                          write_outputs=False)
    r50 = optimize_sizing(Scenario.model_validate(_diesel_only(tmp_path, 0.5)),
                          write_outputs=False)
    assert r20.sizes["dg_kw"] == pytest.approx(180, abs=1e-3)
    assert r50.sizes["dg_kw"] == pytest.approx(225, abs=1e-3)


def test_reserve_from_battery(tmp_path):
    """Резерв может дать батарея, а не только дизель: добавим PV+BESS и
    убедимся, что задача решается и держит нагрузку (батарейный резерв —
    ветвь opres_batt_* в _add_operating_reserve)."""
    data = _diesel_only(tmp_path, 0.3)
    data["battery"] = {
        "capex_usd_per_kwh": 196, "capex_usd_per_kw": 50,
        "om_usd_per_kwh_year": 2, "rte_fraction": 0.9, "soc_min_fraction": 0.2,
        "min_kwh": 0, "max_kwh": 5000, "min_kw": 0, "max_kw": 5000,
        "lifetime_years": 10,
    }
    res = optimize_sizing(Scenario.model_validate(data), write_outputs=False)
    assert res.sim.manifest["totals_kwh"]["shortfall"] == pytest.approx(0)


# ---------- существующий сценарий: госпиталь в Фениксе ----------

def test_reserve_on_phoenix_hospital():
    """Резерв на реальном сценарии (госпиталь Феникса, NREL CRB-профиль):
    открываем коридоры, требуем 40% горячего резерва от нагрузки —
    задача решается, недопоставки нет, а система дороже безрезервной
    (запас мощности реально резервируется, а не берётся бесплатно)."""
    data = load_dict(SCENARIO_PHOENIX)
    for tech, lo, hi in [("pv", "min_kw", "max_kw"),
                         ("diesel", "min_kw", "max_kw")]:
        data[tech][lo] = 0.0
    data["pv"]["max_kw"] = 6000.0
    data["diesel"]["max_kw"] = 4000.0
    data["battery"]["min_kwh"] = 0.0
    data["battery"]["max_kwh"] = 16000.0
    data["battery"]["min_kw"] = 0.0
    data["battery"]["max_kw"] = 5000.0

    base = optimize_sizing(
        Scenario.model_validate(json.loads(json.dumps(data))),
        weather_csv=WEATHER_PHOENIX, write_outputs=False)

    data["reliability"] = {"mode": "hard",
                           "operating_reserve_load_fraction": 0.4}
    res = optimize_sizing(Scenario.model_validate(data),
                          weather_csv=WEATHER_PHOENIX, write_outputs=False)

    assert res.sim.manifest["totals_kwh"]["shortfall"] == pytest.approx(0)
    assert (res.sim.manifest["objective_value"]
            > base.sim.manifest["objective_value"])
