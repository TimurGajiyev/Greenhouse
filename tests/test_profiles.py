"""Тесты профилей (src/profiles.py). Версия v0.2.

Запуск: из корня проекта, с активированным окружением, команда  pytest
"""

import json

from src.schema import Scenario
from src.profiles import build_load_profile, timestep_hours

SCENARIO_PATH = "scenarios/yemen_vendor.json"


def load_yemen_scenario() -> Scenario:
    with open(SCENARIO_PATH, encoding="utf-8") as f:
        return Scenario.model_validate(json.load(f))


def make_csv_scenario() -> Scenario:
    """Сценарий с нагрузкой из CSV (суточное разрешение) вместо синтетики."""
    with open(SCENARIO_PATH, encoding="utf-8") as f:
        data = json.load(f)
    data["load"] = {"profile_csv": "tests/data/sample_load_daily.csv"}
    return Scenario.model_validate(data)


# ---------- синтетический режим (из v0.1) ----------

def test_profile_length():
    profile = build_load_profile(load_yemen_scenario())
    assert len(profile) == 8760


def test_peak_and_base_load():
    profile = build_load_profile(load_yemen_scenario())
    assert profile.max() == 700.0
    assert profile.min() == 50.0


def test_first_day_energy():
    """E = P * t: 700*10 + 50*14 = 7700 кВт*ч за первые сутки."""
    profile = build_load_profile(load_yemen_scenario())
    assert profile.iloc[:24].sum() == 7700.0


def test_work_hours_count():
    profile = build_load_profile(load_yemen_scenario())
    assert (profile.iloc[:24] == 700.0).sum() == 10


def test_index_is_timezone_aware():
    profile = build_load_profile(load_yemen_scenario())
    assert profile.index.tz is not None


def test_timestep_hours_is_one():
    profile = build_load_profile(load_yemen_scenario())
    assert timestep_hours(profile) == 1.0


# ---------- режим CSV, другое разрешение (новое в v0.2) ----------

def test_csv_profile_daily_resolution():
    """Ряд с СУТОЧНЫМ шагом читается, и Δt вычисляется как 24 часа.

    Это проверка масштабируемости ядра на другое временное
    разрешение: никакой код не предполагал "1 шаг = 1 час".
    """
    profile = build_load_profile(make_csv_scenario())
    assert len(profile) == 7
    assert timestep_hours(profile) == 24.0
    assert profile.index.tz is not None        # локализован в пояс площадки
    assert profile.max() == 430.0
    assert profile.name == "load_kw"
