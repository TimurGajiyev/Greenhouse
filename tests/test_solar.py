"""Тесты солнечного профиля (src/solar.py). Версия v0.3 (шаг 4).

Запуск: из корня проекта, с активированным окружением, команда  pytest

Все тесты работают на КЭШИРОВАННОМ погодном файле (tests/data/) —
сеть не нужна, результаты воспроизводимы.
"""

import json

from src.schema import Scenario
from src.profiles import build_load_profile, timestep_hours
from src.solar import build_solar_profile

SCENARIO_PATH = "scenarios/yemen_vendor.json"
WEATHER_CSV = "tests/data/tmy_sanaa_pvgis_sarah3.csv"

# Годовая удельная выработка, зафиксированная при первом прогоне шага 4
# (pvlib 0.15.2, PVGIS SARAH3 TMY, наши консервативные потери).
# Если тест упал — значит, изменилась физика модели или данные,
# и это надо ОСОЗНАННО подтвердить, обновив число.
EXPECTED_ANNUAL_KWH_PER_KWP = 1501.9


def load_yemen_scenario() -> Scenario:
    with open(SCENARIO_PATH, encoding="utf-8") as f:
        return Scenario.model_validate(json.load(f))


def build_profile():
    """Профиль на кэшированной погоде — общий помощник тестов."""
    return build_solar_profile(load_yemen_scenario(), weather_csv=WEATHER_CSV)


def test_length_and_dt_match_load_profile():
    """Длина и шаг времени согласованы с рядом нагрузки; Δt — только
    из timestep_hours, никакого "подразумеваемого часа"."""
    scenario = load_yemen_scenario()
    solar = build_solar_profile(scenario, weather_csv=WEATHER_CSV)
    load = build_load_profile(scenario)
    assert len(solar) == len(load)
    assert timestep_hours(solar) == timestep_hours(load)
    # Индексы совпадают отметка в отметку — симулятор шага 5 сможет
    # складывать ряды без выравнивания.
    assert solar.index.equals(load.index)


def test_night_generation_is_zero():
    """Ночью солнца нет: глухие ночные часы (00-03 местного) — строгий 0."""
    solar = build_profile()
    night = solar[solar.index.hour < 4]
    assert (night == 0.0).all()


def test_values_in_physical_corridor():
    """Удельная выработка в [0, ~1.2] kW/kWp: отрицательной не бывает,
    выше ~1.2 на 1 kWp панелей физически не выжать."""
    solar = build_profile()
    assert solar.min() >= 0.0
    assert solar.max() <= 1.2


def test_annual_yield_plausible_for_yemen():
    """Годовая выработка в правдоподобном коридоре для Йемена."""
    annual = build_profile().sum()  # Δt=1 ч, поэтому сумма kW == kWh
    assert 1500 <= annual <= 2300


def test_annual_yield_regression():
    """Регрессия: точное значение первого прогона (допуск ±1 kWh)."""
    annual = build_profile().sum()
    assert abs(annual - EXPECTED_ANNUAL_KWH_PER_KWP) < 1.0


def test_index_timezone_matches_site():
    """Ряд живёт в поясе площадки (Asia/Aden), как и нагрузка."""
    solar = build_profile()
    assert str(solar.index.tz) == "Asia/Aden"


def test_geometry_fields_accepted_by_schema():
    """Новые поля tilt_deg / azimuth_deg читаются из сценария и
    реально влияют на результат (панель плашмя != панель под 20°)."""
    with open(SCENARIO_PATH, encoding="utf-8") as f:
        data = json.load(f)
    data["pv"]["tilt_deg"] = 0
    data["pv"]["azimuth_deg"] = 180
    flat = Scenario.model_validate(data)
    assert flat.pv.tilt_deg == 0

    annual_flat = build_solar_profile(flat, weather_csv=WEATHER_CSV).sum()
    annual_tilted = build_profile().sum()
    assert annual_flat != annual_tilted


def test_module_params_from_scenario():
    """Параметры модуля из сценария (v1.1, кейсы OKC/NIST) реально
    меняют результат: хуже КПД инвертора / больший саморазогрев
    close_mount дают меньше энергии, open_rack — больше."""
    with open(SCENARIO_PATH, encoding="utf-8") as f:
        base = json.load(f)

    base_annual = build_profile().sum()

    # Худший инвертор (0.90 против дефолта 0.96) -> меньше выработки.
    d = json.loads(json.dumps(base))
    d["pv"]["inverter_eff_fraction"] = 0.90
    worse_inv = build_solar_profile(
        Scenario.model_validate(d), weather_csv=WEATHER_CSV).sum()
    assert worse_inv < base_annual

    # open_rack охлаждается лучше close_mount -> выработка выше.
    d_close = json.loads(json.dumps(base))
    d_close["pv"]["mount_type"] = "close_mount"
    d_open = json.loads(json.dumps(base))
    d_open["pv"]["mount_type"] = "open_rack"
    close = build_solar_profile(
        Scenario.model_validate(d_close), weather_csv=WEATHER_CSV).sum()
    openr = build_solar_profile(
        Scenario.model_validate(d_open), weather_csv=WEATHER_CSV).sum()
    assert openr > close
