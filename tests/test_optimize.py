"""Тесты LP-диспетчера (src/optimize.py). Версия v0.6 (шаг 7).

Игрушечные сценарии посчитаны руками; Йемен сверяется с rule-симулятором
(солвер не может быть хуже правила — правило лишь одна из допустимых
точек его поиска).
"""

import json

import pytest

from src.schema import Scenario
from src.simulate import run_simulation
from src.optimize import optimize_dispatch

SCENARIO_PATH = "scenarios/yemen_vendor.json"
WEATHER_CSV = "tests/data/tmy_sanaa_pvgis_sarah3.csv"


def yemen_dict() -> dict:
    with open(SCENARIO_PATH, encoding="utf-8") as f:
        return json.load(f)


def toy_battery_diesel_scenario(tmp_path, with_diesel=True) -> Scenario:
    """Игрушка: 4 часа по 150 kW; полная батарея 100 kWh (RTE=1,
    PCS 200 kW, пола нет) + опционально дизель 100 kW по $0.26."""
    csv = tmp_path / "toy_load.csv"
    csv.write_text(
        "timestamp,load_kw\n"
        "2026-01-01 00:00,150\n2026-01-01 01:00,150\n"
        "2026-01-01 02:00,150\n2026-01-01 03:00,150\n",
        encoding="utf-8",
    )
    data = yemen_dict()
    del data["pv"]
    data["battery"] = {
        "capex_usd_per_kwh": 100, "capex_usd_per_kw": 0,
        "om_usd_per_kwh_year": 0,
        "rte_fraction": 1.0, "soc_min_fraction": 0.0,
        "min_kwh": 100, "max_kwh": 100, "min_kw": 200, "max_kw": 200,
        "lifetime_years": 10,
    }
    if with_diesel:
        data["diesel"] = {
            "capex_usd_per_kw": 100, "om_usd_per_kw_year": 0,
            "fuel_cost_usd_per_kwh": 0.26,
            "min_kw": 100, "max_kw": 100, "lifetime_years": 10,
        }
    else:
        del data["diesel"]
    data["load"] = {"profile_csv": str(csv)}
    return Scenario.model_validate(data)


# ---------- игрушечные кейсы с ручным оптимумом ----------

def test_toy_optimum_matches_hand_calculation(tmp_path):
    """Спрос 600 kWh; батарея бесплатно отдаёт 100, дизель может
    максимум 100 kW * 4 ч = 400 -> дефицита не избежать? Нет:
    150*4=600; батарея 100 + дизель 400 = 500... остаток 100 -> VOLL.
    Ручной оптимум: топливо 400*0.26=104, штраф 100*1.0=100,
    objective = 204. Потоки: dg=400, discharge=100, shortfall=100."""
    scenario = toy_battery_diesel_scenario(tmp_path)
    res = optimize_dispatch(scenario, write_outputs=False)
    m = res.manifest

    assert m["solver_status"] == "Optimal"
    assert m["objective_value"] == pytest.approx(400 * 0.26 + 100 * 1.0)
    assert m["totals_kwh"]["dg"] == pytest.approx(400)
    assert m["totals_kwh"]["discharge"] == pytest.approx(100)
    assert m["totals_kwh"]["shortfall"] == pytest.approx(100)


def test_toy_no_diesel_serves_all_it_can(tmp_path):
    """Без дизеля: VOLL заставляет солвер выжать из батареи всё —
    отдано 100 kWh, недопоставка 500, objective = 500 * $1."""
    scenario = toy_battery_diesel_scenario(tmp_path, with_diesel=False)
    res = optimize_dispatch(scenario, write_outputs=False)
    m = res.manifest
    assert m["objective_value"] == pytest.approx(500.0)
    assert m["totals_kwh"]["discharge"] == pytest.approx(100)
    assert m["totals_kwh"]["shortfall"] == pytest.approx(500)


def test_voll_below_fuel_price_prefers_darkness(tmp_path):
    """Экономический смысл VOLL: если недопоставка ($0.10/kWh)
    дешевле дизеля ($0.26/kWh) — солвер честно выключает свет.
    Дизель не работает вовсе; батарея всё равно отдаёт свои 100 kWh
    (её энергия бесплатна)."""
    scenario = toy_battery_diesel_scenario(tmp_path)
    res = optimize_dispatch(scenario, voll_usd_per_kwh=0.10, write_outputs=False)
    m = res.manifest
    assert m["totals_kwh"]["dg"] == pytest.approx(0)
    assert m["totals_kwh"]["shortfall"] == pytest.approx(500)
    assert m["objective_value"] == pytest.approx(500 * 0.10)


# ---------- Йемен: солвер не хуже правила ----------

@pytest.fixture(scope="module")
def yemen_both():
    scenario = Scenario.model_validate(yemen_dict())
    rule = run_simulation(scenario, weather_csv=WEATHER_CSV, write_outputs=False)
    lp = optimize_dispatch(scenario, weather_csv=WEATHER_CSV, write_outputs=False)
    return scenario, rule, lp


def test_lp_not_worse_than_rule(yemen_both):
    """Издержки солвера <= издержек правила (у обоих shortfall=0,
    так что сравниваем топливо)."""
    _, rule, lp = yemen_both
    assert lp.manifest["totals_kwh"]["shortfall"] == pytest.approx(0)
    assert (
        lp.manifest["totals_kwh"]["dg"]
        <= rule.manifest["totals_kwh"]["dg"] + 1e-6
    )


def test_lp_balance_and_soc_bounds(yemen_both):
    """Решение солвера проходит те же физические ворота, что и
    rule-симулятор: баланс на каждом шаге, SOC в границах."""
    scenario, _, lp = yemen_both
    t = lp.table
    inflow = t.pv_gen_kw + t.discharge_kw + t.dg_kw + t.shortfall_kw
    outflow = t.load_kw + t.charge_kw + t.curtail_kw
    assert (inflow - outflow).abs().max() < 1e-4

    e = scenario.battery.max_kwh
    floor = scenario.battery.soc_min_fraction * e
    assert t.soc_kwh.min() >= floor - 1e-6
    assert t.soc_kwh.max() <= e + 1e-6


def test_lp_manifest_has_solver_fields(yemen_both):
    """Manifest шага 7 дополнен паспортом солвера."""
    _, _, lp = yemen_both
    m = lp.manifest
    assert m["source_model"] == "lp_v1"
    assert m["solver"] in ("HiGHS", "CBC")
    assert m["solver_status"] == "Optimal"
    assert m["objective_value"] > 0
    assert m["solve_seconds"] > 0


def test_lp_diesel_only_matches_load():
    """Опциональность в LP: дизель-онли (без погоды и интернета) —
    dg[t] == load[t] на каждом шаге, батарейные потоки нулевые."""
    data = yemen_dict()
    del data["pv"]
    del data["battery"]
    scenario = Scenario.model_validate(data)
    t = optimize_dispatch(scenario, write_outputs=False).table
    assert (t.dg_kw - t.load_kw).abs().max() < 1e-6
    assert t.charge_kw.abs().max() == 0
    assert t.discharge_kw.abs().max() == 0
