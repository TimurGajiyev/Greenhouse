"""Battle-тест №3: NREL-OKCity-PV-5.3kW — верификация по трём точкам.

Запуск из корня проекта (с активированным .venv):
    python scripts/battle_test_okc.py

Кейс проверяет ТОЛЬКО солнечный модуль (src/solar.py) по классической
схеме валидации инженерных моделей:
  Точка 1. Предложение вендора (номинал): 25 панелей SunPower SPR-210
           (0.21 kW) = 5.25 kWp DC; инвертор Fronius IG 5100 (КПД 95%);
           температурный коэффициент −0.38%/°C.
  Точка 2. Проектная симуляция (NREL SAM, TMY2 Оклахома-Сити, наклон 35°,
           азимут юг, потери 14%): 7 550 кВт*ч/год, пик 4.41 кВт AC.
  Точка 3. Факт (12 месяцев датчиков): 7 120 кВт*ч/год; инсоляция года
           на 4.2% ниже TMY; аномально жаркое лето (ячейка до 58°C
           против проектных 45°C); КПД инвертора 93.8%; пыль 3.1%.

Честная оговорка о конструкции калькулятора (находка Точки 1):
размеры и юниты наш контракт читает из сценария, а вот параметры
МОДУЛЯ (КПД инвертора, темп. коэффициент, DC/AC) в v1 — константы
src/solar.py. Для верификации скрипт переопределяет их на вендорские
значения на уровне модуля; вывод «сделать их полями схемы» — в резюме.
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import src.solar as solar_mod
from src.schema import Scenario

# ---------- контрольные данные кейса ----------

LAT, LON, TZ = 35.4676, -97.5164, "America/Chicago"  # Оклахома-Сити

# Точка 1: номинал вендора.
PANEL_KW, N_PANELS = 0.21, 25
DC_KW = PANEL_KW * N_PANELS                  # 5.25 kWp
INV_EFF_VENDOR = 0.95
GAMMA_VENDOR = -0.0038                       # −0.38%/°C
INV_AC_KW = 5.1                              # Fronius IG 5100
DC_AC = DC_KW / INV_AC_KW                    # 1.029

# Точка 2: проектная симуляция SAM.
SAM_ANNUAL_KWH = 7_550
SAM_PEAK_AC_KW = 4.41
TILT, AZIMUTH = 35, 180

# Точка 3: факт.
FACT_ANNUAL_KWH = 7_120
FACT_IRRADIANCE_DELTA = -0.042               # год темнее TMY на 4.2%
FACT_INV_EFF = 0.938
FACT_SOILING_PCT = 3.1

WEATHER_TMY = Path("tests/data/tmy_okc.csv")
WEATHER_FACT = Path("results/tmy_okc_actual_year.csv")


def fetch_weather() -> None:
    if WEATHER_TMY.exists():
        print(f"Погода уже есть: {WEATHER_TMY}")
        return
    import pvlib
    print("Качаю PVGIS TMY для Оклахома-Сити...")
    data, _ = pvlib.iotools.get_pvgis_tmy(LAT, LON, map_variables=True,
                                          coerce_year=2026)
    keep = data[["ghi", "dni", "dhi", "temp_air", "wind_speed"]].copy()
    keep.index.name = "time_utc"
    keep.to_csv(WEATHER_TMY)
    print(f"Сохранено: {WEATHER_TMY}")


def make_actual_weather() -> None:
    """Точка 3: фактический год = TMY с инсоляцией −4.2% (по датчикам)."""
    df = pd.read_csv(WEATHER_TMY, index_col="time_utc", parse_dates=True)
    df[["ghi", "dni", "dhi"]] *= (1 + FACT_IRRADIANCE_DELTA)
    WEATHER_FACT.parent.mkdir(exist_ok=True)
    df.to_csv(WEATHER_FACT)


def scenario() -> Scenario:
    """PV-only сценарий по контракту (нагрузка формальная — солнечному
    модулю она не нужна, но контракт требует блок load)."""
    return Scenario.model_validate({
        "name": "NREL-OKCity-PV-5.3kW verification",
        "site": {"name": "Oklahoma City residence",
                 "latitude": LAT, "longitude": LON, "timezone": TZ},
        "pv": {"capex_usd_per_kw": 1000, "om_usd_per_kw_year": 0,
               "min_kw": DC_KW, "max_kw": DC_KW,
               "unit_kw": PANEL_KW,
               "tilt_deg": TILT, "azimuth_deg": AZIMUTH,
               "lifetime_years": 25},
        "load": {"day_kw": 1, "night_kw": 1,
                 "work_start_hour": 8, "work_end_hour": 18},
        "financial": {"discount_rate_fraction": 0.08, "project_years": 10,
                      "currency": "USD"},
        "reliability": {"mode": "hard"},
    })


def set_module_params(inv_eff: float, soiling_pct: float) -> None:
    """Переопределяем константы солнечного модуля под кейс (v1: это
    константы, НЕ поля схемы — главная находка Точки 1)."""
    solar_mod.GAMMA_PDC_PER_C = GAMMA_VENDOR
    solar_mod.INVERTER_EFFICIENCY = inv_eff
    solar_mod.DC_AC_RATIO = DC_AC
    # Потери SAM "стандартные 14%": дефолты PVWatts (soiling 2%), у нас
    # по умолчанию песок 5% — возвращаем к 2% для этого кейса.
    solar_mod.LOSSES_PERCENT = dict(
        soiling=soiling_pct, shading=3.0, snow=0.0, mismatch=2.0,
        wiring=2.0, connections=0.5, lid=1.5, nameplate_rating=1.0,
        age=0.0, availability=3.0,
    )


def annual_and_peak(weather_csv: Path) -> tuple[float, float]:
    profile = solar_mod.build_solar_profile(scenario(),
                                            weather_csv=str(weather_csv))
    return float(profile.sum() * DC_KW), float(profile.max() * DC_KW)


def row(point, project_value, ours, unit=""):
    dev = (ours - project_value) / project_value
    status = "Ок" if abs(dev) <= 0.05 else "Требует калибровки"
    print(f"| {point:26s} | {project_value:>10,.2f}{unit} | "
          f"{ours:>10,.2f}{unit} | {dev:>+6.1%} | {status} |")
    return dev


def main() -> None:
    print("=" * 76)
    print("BATTLE-ТЕСТ №3: NREL-OKCity-PV-5.3kW — три контрольные точки")
    print("=" * 76)
    fetch_weather()
    make_actual_weather()

    # ---------- Точка 1: читается ли номинал ----------
    sc = scenario()
    import math
    panels = math.ceil(sc.pv.max_kw / sc.pv.unit_kw - 1e-6)
    print()
    print("Точка 1 — номинал вендора через контракт схемы:")
    print(f"  DC-мощность: {sc.pv.max_kw} kWp | панелей: {panels} x "
          f"{sc.pv.unit_kw} kW | наклон {sc.pv.tilt_deg} град, "
          f"азимут {sc.pv.azimuth_deg}")
    assert sc.pv.max_kw == 5.25 and panels == 25
    print("  КПД инвертора и темп. коэффициент в v1 — константы solar.py "
          "(переопределены для кейса) — кандидат в поля схемы.")

    # ---------- Точка 2: против проектной симуляции SAM ----------
    set_module_params(inv_eff=INV_EFF_VENDOR, soiling_pct=2.0)
    design_annual, design_peak = annual_and_peak(WEATHER_TMY)

    # ---------- Точка 3: калибровка фактом ----------
    set_module_params(inv_eff=FACT_INV_EFF, soiling_pct=FACT_SOILING_PCT)
    fact_annual, _ = annual_and_peak(WEATHER_FACT)

    print()
    print("| Контрольная точка          | Проект      | Калькулятор | Дельта | Статус |")
    print("|" + "-" * 74 + "|")
    row("1. Номинал DC, kWp", DC_KW, sc.pv.max_kw)
    dev2 = row("2. SAM: годовая, кВт*ч", SAM_ANNUAL_KWH, design_annual)
    dev2p = row("2. SAM: пик AC, кВт", SAM_PEAK_AC_KW, design_peak)
    dev3 = row("3. Факт: годовая, кВт*ч", FACT_ANNUAL_KWH, fact_annual)

    # Остаток Точки 3, объяснимый жарким летом (не заведён в модель):
    # гамма −0.38%/°C x (58−45)°C = −4.9% на летнюю выработку (~1/3 года).
    hot_summer_effect = GAMMA_VENDOR * (58 - 45) * (1 / 3)
    print()
    print("Резюме:")
    print(f"  Точка 2 (наша физика против SAM): дельта {dev2:+.1%} по году, "
          f"{dev2p:+.1%} по пику — расхождение погодных баз (PVGIS NSRDB "
          "против TMY2 1961-1990 у SAM) и транспозиции.")
    print(f"  Точка 3 (после калибровки датчиками): дельта {dev3:+.1%}. "
          f"Неучтённое жаркое лето объясняет ещё ~{hot_summer_effect:+.1%} "
          "(гамма x 13°C x летняя треть года).")
    print("  Если |дельта Точки 3| > 5% сверх этого — искать в цепочке "
          "PVWatts (транспозиция/температурная модель solar.py).")


if __name__ == "__main__":
    main()
