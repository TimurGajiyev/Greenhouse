"""Тесты MILP-сайзинга (группа A: unit commitment + целые машины).

optimize_sizing_milp реализует три улучшения одной формулировкой
(паттерн Calliope units/operating_units + REopt binGenIsOnInTS):
  A2 — целочисленный сайзинг (размеры кратны юниту);
  A1 — топливо с холостым ходом (intercept топливной кривой);
  A3 — стадирование парка по часам (dg_units_on) с минимальной загрузкой.

Игрушечные оптимумы посчитаны руками; тяжёлый годовой прогон заменён
коротким окном реального профиля госпиталя (скорость).
"""

import csv as _csv
import json

import pytest

from src.schema import Scenario
from src.optimize import optimize_sizing, optimize_sizing_milp

WEATHER_PHOENIX = "tests/data/tmy_phoenix.csv"
SCENARIO_PHOENIX = "scenarios/phoenix_hospital_test.json"


def load_dict(path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _diesel_toy(tmp_path, loads, *, unit_kw=100, max_kw=400,
                turndown=None, idle=None, price=1.0) -> dict:
    """Дизель-онли сценарий с почасовым профилем loads (ставка 0)."""
    lines = "timestamp,load_kw\n" + "".join(
        f"2026-01-01 {h:02d}:00,{v}\n" for h, v in enumerate(loads))
    path = tmp_path / "milp_toy.csv"
    path.write_text(lines, encoding="utf-8")
    d = {"capex_usd_per_kw": 100, "om_usd_per_kw_year": 10,
         "fuel_price_usd_per_liter": price, "fuel_liters_per_kwh": 0.27,
         "min_kw": 0, "max_kw": max_kw, "unit_kw": unit_kw,
         "lifetime_years": 10}
    if turndown is not None:
        d["min_turn_down_fraction"] = turndown
    if idle is not None:
        d["fuel_idle_liters_per_hour"] = idle
    return {
        "name": "milp-toy",
        "site": {"name": "x", "latitude": 15.28, "longitude": 44.08,
                 "timezone": "Asia/Aden"},
        "diesel": d,
        "load": {"profile_csv": str(path)},
        "financial": {"discount_rate_fraction": 0.0, "project_years": 10,
                      "currency": "USD"},
        "reliability": {"mode": "hard"},
    }


# ---------- A2 + A3: целые машины и стадирование ----------

def test_milp_integer_sizing_and_staging(tmp_path):
    """Нагрузка [80,150,60], генсеты по 100 kW, min-загрузка 0.5, холостой
    ход 5 л/ч. Ручной оптимум: 150 требует 2 юнита, 80 и 60 — по одному.
    Значит установлено 2 генсета (dg_kw = 200, кратно 100), работают
    [1, 2, 1] → максимум 2, в среднем 1.333, недопоставки нет."""
    scenario = Scenario.model_validate(
        _diesel_toy(tmp_path, [80, 150, 60], turndown=0.5, idle=5.0))
    res = optimize_sizing_milp(scenario, write_outputs=False)

    assert res.sizes["dg_kw"] == pytest.approx(200)          # A2: 2×100
    assert res.sizes["dg_kw"] % 100 == pytest.approx(0)      # кратно юниту
    st = res.sim.manifest["diesel_staging"]
    assert st["dg_units_installed"] == 2
    assert st["dg_units_on_max"] == 2
    assert st["dg_units_on_mean"] == pytest.approx(4 / 3, abs=1e-3)  # A3
    assert res.units["dg_gensets"] == 2
    assert res.sim.manifest["totals_kwh"]["shortfall"] == pytest.approx(0)


def test_milp_never_cheaper_than_lp(tmp_path):
    """Целочисленность — это ОГРАНИЧЕНИЕ поверх LP, поэтому MILP-оптимум
    не может быть дешевле непрерывного LP на той же задаче (фундамент:
    целые размеры — подмножество непрерывных)."""
    data = _diesel_toy(tmp_path, [80, 150, 60])
    lp = optimize_sizing(Scenario.model_validate(json.loads(json.dumps(data))),
                         write_outputs=False)
    milp = optimize_sizing_milp(Scenario.model_validate(data),
                                write_outputs=False)
    assert (milp.sim.manifest["objective_value"]
            >= lp.sim.manifest["objective_value"] - 1e-6)
    # LP мог выбрать 150 kW непрерывно; MILP обязан округлить до 200 (2×100).
    assert lp.sizes["dg_kw"] == pytest.approx(150, abs=1e-3)
    assert milp.sizes["dg_kw"] == pytest.approx(200)


# ---------- A3: минимальная загрузка ----------

def test_milp_min_turndown_can_make_infeasible(tmp_path):
    """Нагрузка 30 kW, генсет 100 kW. Без нижней полки — 1 юнит выдаёт
    ровно 30 (решаемо). С min-загрузкой 0.6 включённый юнит обязан дать
    ≥60, а девать лишнее некуда (нет батареи/PV) → честно неразрешимо."""
    ok = optimize_sizing_milp(
        Scenario.model_validate(_diesel_toy(tmp_path, [30, 30])),
        write_outputs=False)
    assert ok.sim.table["dg_kw"].iloc[0] == pytest.approx(30, abs=1e-3)

    with pytest.raises(RuntimeError):
        optimize_sizing_milp(
            Scenario.model_validate(
                _diesel_toy(tmp_path, [30, 30], turndown=0.6)),
            write_outputs=False)


# ---------- A1: холостой ход ----------

def test_milp_idle_fuel_adds_exact_cost(tmp_path):
    """Нагрузка [100,100,100] = ровно один генсет 100 kW, работающий все
    3 часа. Холостой ход 10 л/ч по $1/л добавляет ровно 3ч × 10 × $1 = $30
    к целевой функции (маргинальный расход одинаков в обоих прогонах)."""
    no_idle = optimize_sizing_milp(
        Scenario.model_validate(_diesel_toy(tmp_path, [100, 100, 100])),
        write_outputs=False)
    with_idle = optimize_sizing_milp(
        Scenario.model_validate(
            _diesel_toy(tmp_path, [100, 100, 100], idle=10.0, price=1.0)),
        write_outputs=False)
    delta = (with_idle.sim.manifest["objective_value"]
             - no_idle.sim.manifest["objective_value"])
    assert delta == pytest.approx(30.0, abs=1e-2)


# ---------- контракты режима ----------

def test_milp_requires_diesel_unit_kw(tmp_path):
    """Стадировать парк нельзя без размера одного генсета: дизель без
    unit_kw в MILP-режиме — честная ошибка, а не молчаливый мусор."""
    data = _diesel_toy(tmp_path, [100, 100])
    del data["diesel"]["unit_kw"]
    with pytest.raises(RuntimeError, match="unit_kw"):
        optimize_sizing_milp(Scenario.model_validate(data), write_outputs=False)


# ---------- существующий сценарий: госпиталь (короткое окно) ----------

def test_milp_on_phoenix_hospital_window(tmp_path):
    """MILP на реальном профиле госпиталя Феникса (первые 4 суток —
    полный год под MILP слишком долог для теста). Открытые коридоры,
    min-загрузка и холостой ход включены: решение целочисленно, парк
    стадируется, нагрузка держится."""
    # Короткое окно реального 8760-часового профиля.
    with open("scenarios/phoenix_hospital_load.csv", encoding="utf-8") as f:
        rows = list(_csv.reader(f))
    window = tmp_path / "phoenix_4d.csv"
    with open(window, "w", newline="", encoding="utf-8") as f:
        _csv.writer(f).writerows(rows[:1 + 96])   # заголовок + 96 часов

    data = load_dict(SCENARIO_PHOENIX)
    data["load"] = {"profile_csv": str(window)}
    data["pv"]["min_kw"] = 0.0
    data["pv"]["max_kw"] = 6000.0
    data["battery"]["min_kwh"] = 0.0
    data["battery"]["max_kwh"] = 16000.0
    data["battery"]["min_kw"] = 0.0
    data["battery"]["max_kw"] = 5000.0
    data["diesel"]["min_kw"] = 0.0
    data["diesel"]["max_kw"] = 4000.0
    data["diesel"]["fuel_price_usd_per_liter"] = 1.2   # нужен для холостого хода
    data["diesel"]["min_turn_down_fraction"] = 0.3
    data["diesel"]["fuel_idle_liters_per_hour"] = 10.0

    res = optimize_sizing_milp(Scenario.model_validate(data),
                               weather_csv=WEATHER_PHOENIX, write_outputs=False)

    # Целые машины: каждый размер кратен своему юниту.
    assert res.sizes["dg_kw"] % data["diesel"]["unit_kw"] == pytest.approx(0)
    assert res.sizes["batt_kwh"] % data["battery"]["unit_kwh"] == pytest.approx(0)
    st = res.sim.manifest["diesel_staging"]
    assert st is not None and st["dg_units_installed"] >= 0
    assert res.sim.manifest["totals_kwh"]["shortfall"] == pytest.approx(0, abs=1e-6)
    assert res.sim.manifest["solver_status"] == "Optimal"
