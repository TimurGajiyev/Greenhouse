"""Acceptance-тесты вариативности фундамента (спецификация Тимура).

Четыре независимых измерения:
  1) разрешение временного ряда (час / полчаса / сутки) — Δt из данных;
  2) присутствие технологий (любая может отсутствовать);
  3) их комбинации (разрешение x состав техники — независимы);
  4) источник нагрузки (ровно один: синтетика ИЛИ CSV).

"Работать" = конфигурация валидируется, ряд читается, число шагов и
Δt правильные, энергия = сумма мощностей * Δt. Отсутствующая
технология — это None в сценарии, а не ошибка и не молчаливый ноль.
"""

import copy
import json

import pytest
from pydantic import ValidationError

from src.schema import Scenario
from src.profiles import build_load_profile, timestep_hours
from src.solar import build_solar_profile

SCENARIO_PATH = "scenarios/yemen_vendor.json"
WEATHER_CSV = "tests/data/tmy_sanaa_pvgis_sarah3.csv"

# Годовая энергия синтетической нагрузки Йемена:
# (700 kW * 10 ч + 50 kW * 14 ч) * 365 дней = 7700 * 365.
YEMEN_ANNUAL_KWH = 7700.0 * 365


def yemen_dict() -> dict:
    """Свежая глубокая копия базового сценария для мутаций."""
    with open(SCENARIO_PATH, encoding="utf-8") as f:
        return json.load(f)


def energy_kwh(profile) -> float:
    """Энергия ряда: сумма мощностей, умноженная на Δt ИЗ ДАННЫХ."""
    return float(profile.sum() * timestep_hours(profile))


# ---------- измерение 2: присутствие технологий ----------

def test_full_system_hourly_synthetic():
    """Сценарий 1: полный состав + синтетика. Опорная арифметика."""
    scenario = Scenario.model_validate(yemen_dict())
    profile = build_load_profile(scenario)
    assert len(profile) == 8760
    assert timestep_hours(profile) == 1.0
    assert energy_kwh(profile) == YEMEN_ANNUAL_KWH


def test_diesel_only():
    """Сценарий 2: только дизель. Отсутствующие технологии — None,
    расчёт нагрузки их вообще не касается."""
    data = yemen_dict()
    del data["pv"]
    del data["battery"]
    scenario = Scenario.model_validate(data)
    assert scenario.pv is None
    assert scenario.battery is None
    assert scenario.diesel is not None
    profile = build_load_profile(scenario)
    assert energy_kwh(profile) == YEMEN_ANNUAL_KWH


def test_pv_battery_without_diesel():
    """Сценарий 3: солнце + батарея, без резервного генератора.
    Солнечный профиль строится и совпадает по оси с нагрузкой."""
    data = yemen_dict()
    del data["diesel"]
    scenario = Scenario.model_validate(data)
    assert scenario.diesel is None
    load = build_load_profile(scenario)
    solar = build_solar_profile(scenario, weather_csv=WEATHER_CSV)
    assert solar.index.equals(load.index)


def test_solar_profile_tolerates_missing_pv_block():
    """Удельный ряд солнца не зависит от блока pv в сценарии
    (без pv берутся дефолты геометрии): отсутствие технологии
    не источник ошибок нигде в слоях."""
    data = yemen_dict()
    del data["pv"]
    scenario = Scenario.model_validate(data)
    solar = build_solar_profile(scenario, weather_csv=WEATHER_CSV)
    assert len(solar) == 8760


# ---------- измерения 1 и 3: разрешение и комбинации ----------

def test_diesel_only_with_daily_csv():
    """Сценарий 4: суточное разрешение x только дизель — комбинация
    двух измерений вариативности сразу."""
    data = yemen_dict()
    del data["pv"]
    del data["battery"]
    data["load"] = {"profile_csv": "tests/data/sample_load_daily.csv"}
    scenario = Scenario.model_validate(data)
    profile = build_load_profile(scenario)
    assert len(profile) == 7
    assert timestep_hours(profile) == 24.0
    # 400+415+430+405+420+380+395 = 2845 kW-суток * 24 ч
    assert energy_kwh(profile) == 2845.0 * 24


def test_pv_battery_with_halfhourly_csv(tmp_path):
    """Получасовое разрешение x PV+BESS. CSV создаётся на лету во
    временной папке pytest (fixture tmp_path — про неё в отчёте)."""
    # Двое суток по 48 получасовых шагов, постоянные 100 kW:
    # энергия = 100 kW * 0.5 ч * 96 шагов = 4800 kWh.
    import pandas as pd

    index = pd.date_range("2026-01-01 00:00", periods=96, freq="30min")
    csv_path = tmp_path / "halfhourly.csv"
    pd.DataFrame({"timestamp": index, "load_kw": 100.0}).to_csv(
        csv_path, index=False
    )

    data = yemen_dict()
    del data["diesel"]
    data["load"] = {"profile_csv": str(csv_path)}
    scenario = Scenario.model_validate(data)
    profile = build_load_profile(scenario)
    assert len(profile) == 96
    assert timestep_hours(profile) == 0.5
    assert energy_kwh(profile) == 4800.0


# ---------- измерение 4: источник нагрузки ----------

def test_no_load_source_is_loud_error():
    """Сценарий 5: нагрузки нет вовсе — громкая ошибка валидации,
    а не молчаливый расчёт с нулевой нагрузкой."""
    data = yemen_dict()
    data["load"] = {}
    with pytest.raises(ValidationError, match="profile_csv"):
        Scenario.model_validate(data)


def test_both_load_sources_is_loud_error():
    """Оба источника сразу — тоже ошибка (двусмысленность запрещена)."""
    data = yemen_dict()
    data["load"]["profile_csv"] = "tests/data/sample_load_daily.csv"
    with pytest.raises(ValidationError, match="не оба"):
        Scenario.model_validate(data)
