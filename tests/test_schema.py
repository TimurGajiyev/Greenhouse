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


# ---------- топливо: цена литра × расход (v1.1) ----------

def test_fuel_cost_derived_from_price_per_liter():
    """$/кВт*ч можно НЕ задавать: он выводится из цены литра и расхода
    (как fuel_cost_per_gallon × slope в REopt). 0.96 × 0.27 = 0.2592."""
    data = load_yemen_dict()
    del data["diesel"]["fuel_cost_usd_per_kwh"]
    data["diesel"]["fuel_price_usd_per_liter"] = 0.96
    data["diesel"]["fuel_liters_per_kwh"] = 0.27
    scenario = Scenario.model_validate(data)
    assert scenario.diesel.fuel_cost_usd_per_kwh == pytest.approx(0.2592)


def test_fuel_price_per_liter_needs_consumption():
    """Цена литра без удельного расхода — недостаточно для $/кВт*ч."""
    data = load_yemen_dict()
    del data["diesel"]["fuel_cost_usd_per_kwh"]
    data["diesel"]["fuel_price_usd_per_liter"] = 0.96
    with pytest.raises(ValidationError):
        Scenario.model_validate(data)


def test_fuel_neither_source_rejected():
    """Совсем без топливной цены — ошибка (нечем считать деньги)."""
    data = load_yemen_dict()
    del data["diesel"]["fuel_cost_usd_per_kwh"]
    with pytest.raises(ValidationError):
        Scenario.model_validate(data)


def test_fuel_direct_kwh_still_works():
    """Прямой $/кВт*ч (как у вендора) по-прежнему принимается."""
    scenario = Scenario.model_validate(load_yemen_dict())
    assert scenario.diesel.fuel_cost_usd_per_kwh == 0.26


# ---------- поля MILP-режима (группа A) ----------

def test_min_turn_down_fraction_read():
    """Минимальная загрузка генсета читается из сценария (для MILP)."""
    data = load_yemen_dict()
    data["diesel"]["min_turn_down_fraction"] = 0.3
    scenario = Scenario.model_validate(data)
    assert scenario.diesel.min_turn_down_fraction == 0.3


def test_idle_fuel_needs_price_per_liter():
    """Холостой ход задан в литрах — без цены литра его не перевести
    в деньги, поэтому это ошибка контракта."""
    data = load_yemen_dict()
    data["diesel"]["fuel_idle_liters_per_hour"] = 8.0
    with pytest.raises(ValidationError):
        Scenario.model_validate(data)


def test_idle_fuel_with_price_ok():
    """Холостой ход + цена литра — валидная пара (intercept REopt)."""
    data = load_yemen_dict()
    data["diesel"]["fuel_price_usd_per_liter"] = 0.96
    data["diesel"]["fuel_idle_liters_per_hour"] = 8.0
    scenario = Scenario.model_validate(data)
    assert scenario.diesel.fuel_idle_liters_per_hour == 8.0


# ---------- оперативный резерв (B1) заменил firm-capacity ----------

def test_operating_reserve_fields_read():
    """Доли оперативного резерва читаются из блока reliability."""
    data = load_yemen_dict()
    data["reliability"] = {"mode": "hard",
                           "operating_reserve_load_fraction": 0.2,
                           "operating_reserve_pv_fraction": 0.1}
    scenario = Scenario.model_validate(data)
    assert scenario.reliability.operating_reserve_load_fraction == 0.2
    assert scenario.reliability.operating_reserve_pv_fraction == 0.1


def test_old_firm_fraction_field_removed():
    """Прежний костыль diesel_firm_fraction удалён из схемы — попытка
    его задать теперь ловится (extra='forbid'), а не игнорируется молча."""
    data = load_yemen_dict()
    data["reliability"] = {"mode": "hard", "diesel_firm_fraction": 1.0}
    with pytest.raises(ValidationError):
        Scenario.model_validate(data)
