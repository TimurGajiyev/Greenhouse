"""Тесты sensitivity-слоя (src/sweep.py). Версия v0.8 (шаг 9).

Свипы гоняются на ИГРУШЕЧНОМ сценарии (3 шага, дизель-онли) — быстрые
LP; полный Йемен — материал отчёта, не тестов.
"""

import json

import numpy as np
import pandas as pd
import pytest

from src.schema import Scenario
from src.simulate import run_simulation
from src.sweep import (
    _find_knee,
    _make_sandstorm_weather,
    _pareto_sweep,
    _price_sweep,
    run_sensitivity,
)

SCENARIO_VENDOR = "scenarios/yemen_vendor.json"
WEATHER_CSV = "tests/data/tmy_sanaa_pvgis_sarah3.csv"


@pytest.fixture()
def toy_scenario(tmp_path) -> Scenario:
    """Дизель-онли сайзинг: 3 часа [100, 150, 120] kW, ставка 0."""
    csv = tmp_path / "toy3.csv"
    csv.write_text(
        "timestamp,load_kw\n"
        "2026-01-01 00:00,100\n2026-01-01 01:00,150\n2026-01-01 02:00,120\n",
        encoding="utf-8",
    )
    with open(SCENARIO_VENDOR, encoding="utf-8") as f:
        data = json.load(f)
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


# ---------- колено Pareto ----------

def test_knee_on_synthetic_curve():
    """Рукотворная L-кривая: резкий излом во второй точке —
    метод хорды обязан найти именно её."""
    x = np.array([0.0, 1.0, 2.0, 3.0, 4.0])
    y = np.array([100.0, 40.0, 35.0, 32.0, 30.0])
    knee = _find_knee(x, y)
    assert knee["index"] == 1
    assert knee["lpsp"] == 1.0


def test_knee_needs_three_points():
    with pytest.raises(ValueError):
        _find_knee(np.array([0, 1]), np.array([5, 3]))


# ---------- однофакторные свипы ----------

def test_fuel_price_sweep_monotonic(toy_scenario):
    """Дороже солярка — выше годовые издержки (дизель-онли: строго)."""
    df = _price_sweep(
        toy_scenario, None, ["diesel", "fuel_cost_usd_per_kwh"],
        (0.5, 1.0, 1.5),
    )
    costs = df["annual_cost_usd"].to_numpy()
    assert (np.diff(costs) > 0).all()
    # Размер дизеля от цены топлива не зависит (hard: всегда пик 150).
    assert df["dg_kw"].nunique() == 1


def test_sweep_of_absent_tech_is_empty(toy_scenario):
    """Свип по отсутствующей технологии — пустая таблица, не крэш."""
    df = _price_sweep(
        toy_scenario, None, ["battery", "capex_usd_per_kwh"], (0.7, 1.3)
    )
    assert df.empty


# ---------- Pareto ----------

def test_pareto_cost_non_increasing(toy_scenario):
    """Слабее требование надёжности — не дороже решение (фронт
    невозрастающий по стоимости)."""
    df = _pareto_sweep(toy_scenario, None)
    costs = df.sort_values("lpsp_target")["annual_cost_usd"].to_numpy()
    assert (np.diff(costs) <= 1e-6).all()
    # Достигнутый LPSP не превышает целевой.
    assert (df["lpsp"] <= df["lpsp_target"] + 1e-9).all()


# ---------- стрессы ----------

def test_dg_outage_causes_shortfall(toy_scenario):
    """Окно отказа дизеля: покрытие нуля -> вся нагрузка окна в
    недопоставку (в игрушке нет ни PV, ни батареи)."""
    data = json.loads(toy_scenario.model_dump_json(exclude_none=True))
    data["diesel"]["min_kw"] = data["diesel"]["max_kw"] = 150
    scenario = Scenario.model_validate(data)
    sim = run_simulation(
        scenario, write_outputs=False,
        dg_outage=("2026-01-01 01:00", "2026-01-01 02:00"),
    )
    t = sim.table
    assert list(t.shortfall_kw) == [0.0, 150.0, 120.0]
    assert list(t.dg_kw) == [100.0, 0.0, 0.0]


def test_sandstorm_weather_builder(tmp_path):
    """Копия погоды: в окне бури вся облучённость 0, температура
    нетронута, вне окна файл идентичен исходному."""
    out = _make_sandstorm_weather(
        WEATHER_CSV, tmp_path, ("2026-07-10", "2026-07-12")
    )
    orig = pd.read_csv(WEATHER_CSV, index_col="time_utc", parse_dates=True)
    storm = pd.read_csv(out, index_col="time_utc", parse_dates=True)

    window = storm.loc["2026-07-10":"2026-07-12"]
    assert (window[["ghi", "dni", "dhi"]] == 0).all().all()
    assert window["temp_air"].equals(
        orig.loc["2026-07-10":"2026-07-12", "temp_air"]
    )
    outside = storm.loc["2026-07-14":]
    assert outside["ghi"].equals(orig.loc["2026-07-14":, "ghi"])


# ---------- полный пакет на игрушке ----------

def test_run_sensitivity_end_to_end(toy_scenario, tmp_path):
    """Весь пакет шага 9 на игрушке: таблицы собраны, parquet и
    summary.json написаны, колено найдено."""
    report = run_sensitivity(
        toy_scenario, results_dir=str(tmp_path / "sweeps")
    )
    assert not report.fuel_price.empty
    assert report.bess_capex.empty  # батареи в игрушке нет
    assert not report.pareto.empty
    assert "lpsp" in report.knee
    assert report.summary_path.exists()
    summary = json.loads(report.summary_path.read_text(encoding="utf-8"))
    assert "knee" in summary
    # Каждый прогон свипа получил свой manifest на диске (шаг 9).
    runs = list((tmp_path / "sweeps" / "runs").glob("*_manifest.json"))
    assert len(runs) >= len(report.fuel_price) + len(report.pareto)
    # Стресс-таблица: типичный год + топливный разрыв (буря пропущена:
    # PV нет). В типичном году дизель-онли покрывает всё.
    assert len(report.stress) == 2
    assert report.stress.iloc[0]["lpsp"] == 0.0
