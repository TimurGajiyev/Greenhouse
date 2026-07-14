"""Тесты сайзера (src/optimize.py, режим sizing). Версия v0.7 (шаг 8).

Игрушечные оптимумы посчитаны руками; сравнение с вендором — материал
ОТЧЁТА, а не теста (числа оптимума зависят от погоды и допущений).
"""

import json

import pytest

from src.schema import Scenario
from src.optimize import optimize_dispatch, optimize_sizing

SCENARIO_VENDOR = "scenarios/yemen_vendor.json"
SCENARIO_SIZING = "scenarios/yemen_sizing.json"
WEATHER_CSV = "tests/data/tmy_sanaa_pvgis_sarah3.csv"


def load_dict(path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def toy_diesel_sizing_scenario(tmp_path) -> Scenario:
    """Игрушка: дизель-онли сайзинг, ставка 0, простые числа.

    Нагрузка: 3 часа [100, 150, 120] kW. Режим hard -> дизель обязан
    покрыть пик: dg_kw == 150. Ручной оптимум:
      капитал CRF(0,10)*100$/kW*150 = 0.1*100*150 = 1500/год
      O&M 10*150 = 1500/год; топливо 0.26*370 = 96.2
      objective = 3096.2 (+микроштраф ~0.00015 — в допуске approx).
    """
    csv = tmp_path / "toy3.csv"
    csv.write_text(
        "timestamp,load_kw\n"
        "2026-01-01 00:00,100\n2026-01-01 01:00,150\n2026-01-01 02:00,120\n",
        encoding="utf-8",
    )
    data = load_dict(SCENARIO_VENDOR)
    del data["pv"]
    del data["battery"]
    data["diesel"] = {
        "capex_usd_per_kw": 100, "om_usd_per_kw_year": 10,
        "fuel_cost_usd_per_kwh": 0.26,
        "min_kw": 0, "max_kw": 1000, "lifetime_years": 10,
    }
    data["load"] = {"profile_csv": str(csv)}
    data["financial"] = {"discount_rate_fraction": 0.0,
                         "project_years": 10, "currency": "USD"}
    return Scenario.model_validate(data)


# ---------- игрушечный ручной оптимум ----------

def test_toy_diesel_sizing_hand_optimum(tmp_path):
    scenario = toy_diesel_sizing_scenario(tmp_path)
    res = optimize_sizing(scenario, write_outputs=False)

    # Размер == пик нагрузки: меньше нельзя (hard), больше — дороже.
    assert res.sizes["dg_kw"] == pytest.approx(150, abs=1e-4)
    assert res.sim.manifest["objective_value"] == pytest.approx(3096.2, rel=1e-4)
    assert res.sim.manifest["totals_kwh"]["shortfall"] == pytest.approx(0)


def test_toy_battery_zero_without_pv(tmp_path):
    """Батарее без солнца нечем заряжаться — оптимальный размер 0
    (недвусмысленно благодаря анти-вырожденному микроштрафу)."""
    scenario_data = json.loads(toy_diesel_sizing_scenario(tmp_path).model_dump_json(exclude_none=True))
    scenario_data["battery"] = {
        "capex_usd_per_kwh": 196, "capex_usd_per_kw": 0,
        "om_usd_per_kwh_year": 2,
        "rte_fraction": 0.85, "soc_min_fraction": 0.2,
        "min_kwh": 0, "max_kwh": 5000, "min_kw": 0, "max_kw": 5000,
        "lifetime_years": 10,
    }
    scenario = Scenario.model_validate(scenario_data)
    res = optimize_sizing(scenario, write_outputs=False)
    assert res.sizes["batt_kwh"] == pytest.approx(0, abs=1e-6)
    assert res.sizes["batt_kw"] == pytest.approx(0, abs=1e-6)


# ---------- фиксация min == max воспроизводит шаг 7 ----------

def test_fixed_corridors_reproduce_dispatch():
    """Приём REopt: сжать коридоры в точку (min == max) — сайзер
    обязан выдать вендорские размеры и ТО ЖЕ топливо, что LP-диспетчер
    шага 7 на том же сценарии. cyclic_soc выравниваем (False), иначе
    это были бы РАЗНЫЕ задачи: дефолт сайзера — годовое кольцо."""
    scenario = Scenario.model_validate(load_dict(SCENARIO_VENDOR))
    dispatch = optimize_dispatch(scenario, weather_csv=WEATHER_CSV, write_outputs=False)
    sizing = optimize_sizing(
        scenario, weather_csv=WEATHER_CSV, write_outputs=False, cyclic_soc=False
    )

    assert sizing.sizes["pv_kwp"] == pytest.approx(1500)
    assert sizing.sizes["batt_kwh"] == pytest.approx(3132)
    assert sizing.sizes["dg_kw"] == pytest.approx(1000)
    assert sizing.sim.manifest["totals_kwh"]["dg"] == pytest.approx(
        dispatch.manifest["totals_kwh"]["dg"], rel=1e-6
    )


# ---------- политики надёжности ----------

def test_lpsp_policy_respected(tmp_path):
    """Режим lpsp: недопоставка не выше заданной доли. Дизель-онли с
    дорогим капиталом: выгодно недодать 5%, солвер упирается в потолок."""
    data = json.loads(
        toy_diesel_sizing_scenario(tmp_path).model_dump_json(exclude_none=True)
    )
    data["reliability"] = {"mode": "lpsp", "lpsp_max_fraction": 0.05}
    scenario = Scenario.model_validate(data)
    res = optimize_sizing(scenario, write_outputs=False)
    m = res.sim.manifest
    assert m["lpsp"] <= 0.05 + 1e-9
    # Капитал дорогой, недопоставка бесплатна -> ограничение активно.
    assert m["lpsp"] == pytest.approx(0.05, rel=1e-3)


def test_voll_policy_prices_reliability(tmp_path):
    """Режим voll: при VOLL ниже цены дизеля солвер строит НОЛЬ
    генерации — терять нагрузку дешевле, чем покрывать."""
    data = json.loads(
        toy_diesel_sizing_scenario(tmp_path).model_dump_json(exclude_none=True)
    )
    data["reliability"] = {"mode": "voll", "voll_usd_per_kwh": 0.05}
    scenario = Scenario.model_validate(data)
    res = optimize_sizing(scenario, write_outputs=False)
    assert res.sizes["dg_kw"] == pytest.approx(0, abs=1e-6)
    assert res.sim.manifest["lpsp"] == pytest.approx(1.0)


def test_hard_infeasible_raises(tmp_path):
    """Режим hard при коридорах, которым нагрузка не по зубам, — это
    честная ошибка 'неразрешимо', а не тихий мусор."""
    data = json.loads(
        toy_diesel_sizing_scenario(tmp_path).model_dump_json(exclude_none=True)
    )
    data["diesel"]["max_kw"] = 100  # пик 150 не покрыть
    scenario = Scenario.model_validate(data)
    with pytest.raises(RuntimeError, match="неразрешима|статус"):
        optimize_sizing(scenario, write_outputs=False)


# ---------- площадь и штуки ----------

def test_roof_area_caps_pv():
    """Йемен с открытыми коридорами: PV упирается в крышу —
    8500 м² / 5 м² на kWp = 1700 kWp (ограничение активно, потому
    что солнечный kWh дешевле дизельного)."""
    scenario = Scenario.model_validate(load_dict(SCENARIO_SIZING))
    res = optimize_sizing(scenario, weather_csv=WEATHER_CSV, write_outputs=False)
    assert res.sizes["pv_kwp"] == pytest.approx(8500 / 5.0, rel=1e-6)
    # hard-режим: недопоставки нет.
    assert res.sim.manifest["totals_kwh"]["shortfall"] == pytest.approx(0)


def test_units_postprocessing_ceil():
    """Штуки = ceil(size / unit): 1500 kWp / 0.58 -> 2587 панелей
    (как в вендорском предложении); 3132/261 -> ровно 12 шкафов."""
    scenario = Scenario.model_validate(load_dict(SCENARIO_VENDOR))
    res = optimize_sizing(scenario, weather_csv=WEATHER_CSV, write_outputs=False)
    assert res.units["pv_panels"] == 2587
    assert res.units["batt_cabinets"] == 12
    assert res.units["batt_pcs_units"] == 12
    assert res.units["dg_gensets"] == 1
    # Manifest несёт и размеры, и штуки (Definition of Done миссии).
    assert res.sim.manifest["sizes"]["pv_kwp"] == pytest.approx(1500)
    assert res.sim.manifest["units"]["pv_panels"] == 2587
