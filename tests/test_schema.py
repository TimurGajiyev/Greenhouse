"""Тесты контракта данных (src/schema.py). Версия v0.2.

Запуск: из корня проекта, с активированным окружением, команда  pytest

Новое в v0.2: тесты вариативности — отсутствие технологии допустимо,
пустая система отвергается, режимы нагрузки взаимоисключающи,
размеры единиц оборудования читаются.
"""

import json

import pytest
from pydantic import ValidationError

from src.schema import Scenario

SCENARIO_PATH = "scenarios/yemen_vendor.json"


def load_yemen_dict():
    """Свежая копия сценария-словаря для каждого теста."""
    with open(SCENARIO_PATH, encoding="utf-8") as f:
        return json.load(f)


# ---------- базовые проверки (из v0.1) ----------

def test_yemen_loads():
    """Хороший файл проходит валидацию; значения доступны через точку."""
    scenario = Scenario.model_validate(load_yemen_dict())
    assert scenario.pv.max_kw == 1500
    assert scenario.battery.rte_fraction == 0.85
    assert scenario.diesel.fuel_cost_usd_per_kwh == 0.26
    assert scenario.load.day_kw == 700


def test_negative_capex_rejected():
    data = load_yemen_dict()
    data["pv"]["capex_usd_per_kw"] = -398
    with pytest.raises(ValidationError):
        Scenario.model_validate(data)


def test_rte_above_one_rejected():
    data = load_yemen_dict()
    data["battery"]["rte_fraction"] = 1.5
    with pytest.raises(ValidationError):
        Scenario.model_validate(data)


def test_typo_key_rejected():
    """Неизвестный ключ (опечатка) роняет валидацию: extra="forbid"."""
    data = load_yemen_dict()
    data["pv"]["capex_usd_per_kwt"] = 398
    with pytest.raises(ValidationError):
        Scenario.model_validate(data)


def test_inverted_corridor_rejected():
    data = load_yemen_dict()
    data["pv"]["min_kw"] = 2000
    with pytest.raises(ValidationError):
        Scenario.model_validate(data)


def test_bad_work_hours_rejected():
    data = load_yemen_dict()
    data["load"]["work_start_hour"] = 18
    data["load"]["work_end_hour"] = 8
    with pytest.raises(ValidationError):
        Scenario.model_validate(data)


# ---------- вариативность (новое в v0.2) ----------

def test_scenario_without_pv_ok():
    """Отсутствие технологии — законный сценарий (дизель + батарея)."""
    data = load_yemen_dict()
    del data["pv"]  # удаляем ключ целиком, как в REopt: нет ключа - нет техники
    scenario = Scenario.model_validate(data)
    assert scenario.pv is None
    assert scenario.diesel is not None


def test_empty_system_rejected():
    """Система вовсе без технологий — бессмысленный вход."""
    data = load_yemen_dict()
    del data["pv"]
    del data["battery"]
    del data["diesel"]
    with pytest.raises(ValidationError):
        Scenario.model_validate(data)


def test_load_modes_conflict_rejected():
    """Нельзя задать и синтетический режим, и CSV одновременно."""
    data = load_yemen_dict()
    data["load"]["profile_csv"] = "tests/data/sample_load_daily.csv"
    with pytest.raises(ValidationError):
        Scenario.model_validate(data)


def test_unit_sizes_loaded():
    """Размеры единиц оборудования читаются — база для перевода в штуки."""
    scenario = Scenario.model_validate(load_yemen_dict())
    assert scenario.battery.unit_kwh == 261   # шкаф
    assert scenario.battery.unit_kw == 125    # PCS
    assert scenario.pv.unit_kw == 0.58        # панель 580 Вт
    assert scenario.diesel.unit_kw == 1000    # генсет
