"""Тесты симулятора (src/simulate.py). Версия v0.4 (шаг 5).

Запуск: из корня проекта, с активированным окружением, команда  pytest

Прогоны — на кэшированной погоде (сеть не нужна), без записи файлов
(write_outputs=False), кроме отдельного теста manifest/Parquet.
"""

import json

import pandas as pd
import pytest

from src.schema import Scenario
from src.profiles import timestep_hours
from src.simulate import run_simulation, _align_solar_to_load
from src.solar import build_solar_profile

SCENARIO_PATH = "scenarios/yemen_vendor.json"
WEATHER_CSV = "tests/data/tmy_sanaa_pvgis_sarah3.csv"


def yemen_dict() -> dict:
    with open(SCENARIO_PATH, encoding="utf-8") as f:
        return json.load(f)


def run_yemen():
    scenario = Scenario.model_validate(yemen_dict())
    return run_simulation(scenario, weather_csv=WEATHER_CSV, write_outputs=False)


# ---------- энергобаланс и физика ----------

def test_balance_holds_every_step():
    """Приход == расход на каждом из 8760 шагов (независимая проверка
    поверх assert-ов внутри цикла — уже по готовой таблице)."""
    t = run_yemen().table
    inflow = t.pv_gen_kw + t.discharge_kw + t.dg_kw + t.shortfall_kw
    outflow = t.load_kw + t.charge_kw + t.curtail_kw
    assert (inflow - outflow).abs().max() < 1e-6


def test_soc_always_in_bounds():
    """SOC не покидает [soc_min * E, E] ни на одном шаге."""
    scenario = Scenario.model_validate(yemen_dict())
    t = run_yemen().table
    e = scenario.battery.max_kwh
    floor = scenario.battery.soc_min_fraction * e
    # Микрозапас 1e-9 — на округления плавающей точки.
    assert t.soc_kwh.min() >= floor - 1e-9
    assert t.soc_kwh.max() <= e + 1e-9


def test_vendor_yemen_shortfall_is_zero():
    """Вендорская конфигурация покрывает нагрузку полностью: дизель
    1000 kW >= пика 700 kW, поэтому недопоставка структурно невозможна.
    Если тест упал — изменилась физика, разбираться обязательно."""
    result = run_yemen()
    assert result.table.shortfall_kw.sum() == 0.0
    assert result.manifest["lpsp"] == 0.0


# ---------- вариативность состава (без спец-веток) ----------

def test_diesel_only_runs_offline():
    """Дизель-онли: без PV погода не нужна вовсе (weather_csv=None,
    интернет не трогается), дизель тащит всю нагрузку сам."""
    data = yemen_dict()
    del data["pv"]
    del data["battery"]
    scenario = Scenario.model_validate(data)
    t = run_simulation(scenario, write_outputs=False).table
    assert (t.dg_kw == t.load_kw).all()
    assert t.pv_gen_kw.eq(0).all()
    assert t.charge_kw.eq(0).all() and t.discharge_kw.eq(0).all()


def test_pv_battery_without_diesel_has_honest_shortfall():
    """PV+BESS без дизеля: солнце в среднем даёт ~80% суточной энергии,
    значит недопоставка ОБЯЗАНА появиться — честный физический результат,
    а не баг."""
    data = yemen_dict()
    del data["diesel"]
    scenario = Scenario.model_validate(data)
    result = run_simulation(scenario, weather_csv=WEATHER_CSV, write_outputs=False)
    assert result.table.shortfall_kw.sum() > 0
    assert 0 < result.manifest["lpsp"] < 1


# ---------- игрушечный кейс с ручной арифметикой ----------

def test_toy_battery_hand_arithmetic(tmp_path):
    """Батарея-онли, 4 часа постоянной нагрузки 10 kW, RTE=1:
    из полной батареи 100 kWh каждый час уходит ровно 10 kWh:
    SOC: 100 -> 90 -> 80 -> 70 (посчитано руками)."""
    csv = tmp_path / "load4.csv"
    csv.write_text(
        "timestamp,load_kw\n"
        "2026-01-01 00:00,10\n2026-01-01 01:00,10\n"
        "2026-01-01 02:00,10\n2026-01-01 03:00,10\n",
        encoding="utf-8",
    )
    data = yemen_dict()
    del data["pv"]
    del data["diesel"]
    data["battery"] = {
        "capex_usd_per_kwh": 100, "capex_usd_per_kw": 0,
        "om_usd_per_kwh_year": 0,
        "rte_fraction": 1.0, "soc_min_fraction": 0.0,
        "min_kwh": 100, "max_kwh": 100, "min_kw": 50, "max_kw": 50,
        "lifetime_years": 10,
    }
    data["load"] = {"profile_csv": str(csv)}
    scenario = Scenario.model_validate(data)
    t = run_simulation(scenario, write_outputs=False).table
    assert list(t.discharge_kw) == [10.0, 10.0, 10.0, 10.0]
    assert list(t.soc_kwh) == [90.0, 80.0, 70.0, 60.0]
    assert t.shortfall_kw.sum() == 0.0


def test_toy_battery_hits_power_and_floor_limits(tmp_path):
    """Пределы уважаются: PCS 5 kW режет разряд (нагрузка 10 ->
    недопоставка 5), а пол soc_min останавливает разряд полностью."""
    csv = tmp_path / "load3.csv"
    csv.write_text(
        "timestamp,load_kw\n"
        "2026-01-01 00:00,10\n2026-01-01 01:00,10\n2026-01-01 02:00,10\n",
        encoding="utf-8",
    )
    data = yemen_dict()
    del data["pv"]
    del data["diesel"]
    data["battery"] = {
        "capex_usd_per_kwh": 100, "capex_usd_per_kw": 0,
        "om_usd_per_kwh_year": 0,
        "rte_fraction": 1.0, "soc_min_fraction": 0.9,  # пол 9 kWh из 10
        "min_kwh": 10, "max_kwh": 10, "min_kw": 5, "max_kw": 5,
        "lifetime_years": 10,
    }
    data["load"] = {"profile_csv": str(csv)}
    scenario = Scenario.model_validate(data)
    t = run_simulation(scenario, write_outputs=False).table
    # Час 1: доступно (10-9)=1 kWh -> разряд 1 kW (меньше PCS 5);
    # дальше батарея на полу, весь спрос — недопоставка.
    assert list(t.discharge_kw) == [1.0, 0.0, 0.0]
    assert list(t.shortfall_kw) == [9.0, 10.0, 10.0]
    assert list(t.soc_kwh) == [9.0, 9.0, 9.0]


# ---------- 15-минутные и суточные данные (Чехия-ready) ----------

def make_quarter_hour_scenario(tmp_path) -> Scenario:
    """Сценарий с 15-минутной нагрузкой на двое суток (192 шага)."""
    index = pd.date_range("2026-06-01 00:00", periods=192, freq="15min")
    csv = tmp_path / "load15min.csv"
    pd.DataFrame({"timestamp": index, "load_kw": 100.0}).to_csv(csv, index=False)
    data = yemen_dict()
    data["load"] = {"profile_csv": str(csv)}
    return Scenario.model_validate(data)


def test_quarter_hour_resolution_runs(tmp_path):
    """Полный состав на 15-минутной сетке: Δt=0.25 из данных, баланс
    сходится, солнце повторено внутри часа (приём REopt)."""
    scenario = make_quarter_hour_scenario(tmp_path)
    result = run_simulation(scenario, weather_csv=WEATHER_CSV, write_outputs=False)
    t = result.table
    assert result.manifest["timestep_hours"] == 0.25
    assert len(t) == 192
    # Внутри одного часа 4 значения PV одинаковы (kW константен).
    assert t.pv_gen_kw.iloc[48:52].nunique() == 1


def test_alignment_conserves_energy(tmp_path):
    """Выравнивание час -> 15 минут сохраняет энергию: сумма kWh
    исходного часового окна == сумма kWh четырёх четвертей."""
    scenario = make_quarter_hour_scenario(tmp_path)
    solar_hourly = build_solar_profile(scenario, weather_csv=WEATHER_CSV)
    load = pd.Series(
        100.0,
        index=pd.date_range(
            "2026-06-01 00:00", periods=192, freq="15min", tz="Asia/Aden"
        ),
        name="load_kw",
    )
    aligned = _align_solar_to_load(solar_hourly, load)
    span = solar_hourly.loc["2026-06-01":"2026-06-02"]
    assert aligned.sum() * 0.25 == pytest.approx(span.sum() * 1.0, rel=1e-9)


def test_daily_load_with_pv_aggregates_solar():
    """Суточная нагрузка + PV: солнце усредняется в сутки (энергия
    сохраняется), баланс сходится и на Δt=24."""
    data = yemen_dict()
    data["load"] = {"profile_csv": "tests/data/sample_load_daily.csv"}
    scenario = Scenario.model_validate(data)
    result = run_simulation(scenario, weather_csv=WEATHER_CSV, write_outputs=False)
    assert result.manifest["timestep_hours"] == 24.0
    assert len(result.table) == 7


# ---------- manifest и Parquet ----------

def test_outputs_written_and_manifest_complete(tmp_path):
    """Файлы результатов пишутся, manifest содержит паспортные поля,
    Parquet читается обратно в ту же таблицу."""
    scenario = Scenario.model_validate(yemen_dict())
    result = run_simulation(
        scenario, weather_csv=WEATHER_CSV, results_dir=str(tmp_path)
    )
    assert result.parquet_path.exists()
    assert result.manifest_path.exists()

    m = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    for key in ("run_id", "git_commit", "inputs_hash", "timestep_hours",
                "source_model", "totals_kwh", "lpsp"):
        assert key in m
    assert m["n_steps"] == 8760

    roundtrip = pd.read_parquet(result.parquet_path)
    assert len(roundtrip) == len(result.table)
    assert roundtrip.load_kw.equals(result.table.load_kw)
