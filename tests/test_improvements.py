"""Тесты улучшений, перенесённых из reference-калькуляторов (Calliope,
REopt). Версия v0.9.

Что проверяем:
  1. cyclic_soc (Calliope cyclic_storage): годовое кольцо запаса —
     бесплатной стартовой заправки больше нет;
  2. self-discharge (Calliope storage_loss): саморазряд батареи
     в rule-симуляторе и в LP;
  3. LP-snapshot (паттерн эталонных .lp-файлов Calliope): формулировка
     модели зафиксирована текстом — случайное изменение математики
     роняет тест;
  4. кросс-солверная сверка: два независимых солвера (HiGHS и CBC)
     обязаны найти один и тот же оптимум.
"""

import json
from pathlib import Path

import pytest

from src.schema import Scenario
from src.simulate import run_simulation
from src.optimize import optimize_dispatch, optimize_sizing

SCENARIO_VENDOR = "scenarios/yemen_vendor.json"
BASELINE_DIR = Path("tests/data/lp_baselines")


def yemen_dict() -> dict:
    with open(SCENARIO_VENDOR, encoding="utf-8") as f:
        return json.load(f)


def toy_battery_diesel(
    tmp_path, loss: float | None = None, open_dg: bool = False
) -> Scenario:
    """Батарея 100 kWh (RTE=1, пола нет) + дизель 100 kW @ $0.26;
    нагрузка 150 kW x 4 часа.

    open_dg=True — коридор дизеля [0, 1000] вместо фиксированных 100:
    нужно sizing-режиму с кольцом, где hard-надёжность при дизеле
    меньше пика неразрешима (кольцо не даёт батарее бесплатной
    заправки — и это ровно тот случай, который оно должно ловить).
    """
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
    if loss is not None:
        data["battery"]["self_discharge_fraction_per_hour"] = loss
    data["diesel"] = {
        "capex_usd_per_kw": 100, "om_usd_per_kw_year": 0,
        "fuel_cost_usd_per_kwh": 0.26,
        "min_kw": 0 if open_dg else 100,
        "max_kw": 1000 if open_dg else 100,
        "lifetime_years": 10,
    }
    data["load"] = {"profile_csv": str(csv)}
    return Scenario.model_validate(data)


def zero_load_battery_scenario(tmp_path, loss: float) -> Scenario:
    """Нулевая нагрузка + батарея с саморазрядом: виден чистый распад."""
    csv = tmp_path / "zero_load.csv"
    csv.write_text(
        "timestamp,load_kw\n"
        "2026-01-01 00:00,0\n2026-01-01 01:00,0\n2026-01-01 02:00,0\n",
        encoding="utf-8",
    )
    data = yemen_dict()
    del data["pv"]
    del data["diesel"]
    data["battery"] = {
        "capex_usd_per_kwh": 100, "capex_usd_per_kw": 0,
        "om_usd_per_kwh_year": 0,
        "rte_fraction": 1.0, "soc_min_fraction": 0.0,
        "self_discharge_fraction_per_hour": loss,
        "min_kwh": 100, "max_kwh": 100, "min_kw": 50, "max_kw": 50,
        "lifetime_years": 10,
    }
    data["load"] = {"profile_csv": str(csv)}
    return Scenario.model_validate(data)


# ---------- 1. циклическое хранилище ----------

def test_cyclic_removes_free_initial_charge(tmp_path):
    """Кольцо: заряжаться нечем (PV нет), значит и разряжаться нельзя —
    Σразряда = 0, дизель 400 kWh, недопоставка 200 kWh.
    Ручной optimum: 0.26*400 + 1.0*200 = 304 (было 204 с бесплатной
    полной батареей)."""
    scenario = toy_battery_diesel(tmp_path)
    res = optimize_dispatch(scenario, write_outputs=False, cyclic_soc=True)
    m = res.manifest
    assert m["totals_kwh"]["discharge"] == pytest.approx(0, abs=1e-6)
    assert m["objective_value"] == pytest.approx(304.0)
    assert m["cyclic_soc"] is True


def test_cyclic_ring_equation_holds(tmp_path):
    """Соединение кольца: soc[0] == soc[последний] + Δt*(η*charge[0] -
    discharge[0]/η) — 'предыдущим' для первого шага стал последний."""
    scenario = toy_battery_diesel(tmp_path)
    t = optimize_dispatch(scenario, write_outputs=False, cyclic_soc=True).table
    eta = 1.0  # rte 1
    expected_first = t.soc_kwh.iloc[-1] + 1.0 * (
        eta * t.charge_kw.iloc[0] - t.discharge_kw.iloc[0] / eta
    )
    assert t.soc_kwh.iloc[0] == pytest.approx(expected_first, abs=1e-6)


# ---------- 2. саморазряд ----------

def test_self_discharge_rule_simulator(tmp_path):
    """Rule-симулятор: нагрузки нет, потоков нет — запас тает
    геометрически: 100 -> 90 -> 81 -> 72.9 при loss = 10%/ч."""
    scenario = zero_load_battery_scenario(tmp_path, loss=0.1)
    t = run_simulation(scenario, write_outputs=False).table
    assert list(t.soc_kwh.round(6)) == [90.0, 81.0, 72.9]
    assert t.discharge_kw.abs().max() == 0.0


def test_self_discharge_lp_matches_rule(tmp_path):
    """LP с теми же входами обязан показать тот же распад (нецикличный
    режим, старт с полной батареи — как у правила)."""
    scenario = zero_load_battery_scenario(tmp_path, loss=0.1)
    t = optimize_dispatch(scenario, write_outputs=False, cyclic_soc=False).table
    assert list(t.soc_kwh.round(6)) == [90.0, 81.0, 72.9]


def test_no_self_discharge_by_default(tmp_path):
    """Поле не задано -> распада нет (старое поведение не тронуто)."""
    scenario = zero_load_battery_scenario(tmp_path, loss=0.1)
    data = json.loads(scenario.model_dump_json(exclude_none=True))
    del data["battery"]["self_discharge_fraction_per_hour"]
    scenario0 = Scenario.model_validate(data)
    t = run_simulation(scenario0, write_outputs=False).table
    assert list(t.soc_kwh) == [100.0, 100.0, 100.0]


# ---------- 3. LP-snapshot (паттерн Calliope) ----------

def _lp_lines(path: Path) -> set[str]:
    """Множество непустых строк .lp-файла — сравнение, нечувствительное
    к порядку (приём _diff_files из tests/math Calliope)."""
    return {ln.strip() for ln in path.read_text().splitlines() if ln.strip()}


@pytest.mark.parametrize("mode", ["dispatch", "sizing"])
def test_lp_snapshot_matches_baseline(tmp_path, mode):
    """Формулировка модели зафиксирована эталонным .lp-файлом.

    Упал тест — значит, изменилась МАТЕМАТИКА (переменная, ограничение,
    коэффициент). Если изменение осознанное: перегенерируй эталон
    скриптом  python scripts/regen_lp_baselines.py  и объясни диф
    в сообщении коммита.
    """
    generated = tmp_path / f"{mode}.lp"
    if mode == "dispatch":
        scenario = toy_battery_diesel(tmp_path)
        optimize_dispatch(
            scenario, write_outputs=False, lp_snapshot_path=str(generated)
        )
    else:
        # Кольцо + hard требуют дизель >= пика: коридор открыт.
        scenario = toy_battery_diesel(tmp_path, open_dg=True)
        optimize_sizing(
            scenario, write_outputs=False, lp_snapshot_path=str(generated)
        )

    baseline = BASELINE_DIR / f"toy_{mode}.lp"
    assert baseline.exists(), (
        f"Нет эталона {baseline} — создай его: python scripts/regen_lp_baselines.py"
    )
    assert _lp_lines(generated) == _lp_lines(baseline)


# ---------- 4. кросс-солверная сверка ----------

def test_highs_and_cbc_agree(tmp_path):
    """Два независимых солвера — один оптимум (допуск 1e-6 отн.).
    Это замена 'сверки с коммерческим солвером' из аудита: HiGHS и
    CBC написаны разными командами и не могут ошибаться одинаково."""
    scenario = toy_battery_diesel(tmp_path, open_dg=True)
    highs = optimize_sizing(scenario, write_outputs=False, solver="highs")
    cbc = optimize_sizing(scenario, write_outputs=False, solver="cbc")

    assert highs.sim.manifest["solver"] == "HiGHS"
    assert cbc.sim.manifest["solver"] == "CBC"
    assert highs.sim.manifest["objective_value"] == pytest.approx(
        cbc.sim.manifest["objective_value"], rel=1e-6
    )
