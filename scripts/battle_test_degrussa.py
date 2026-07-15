"""Battle-тест №2: рудник DeGrussa (Западная Австралия) — сверка с ФАКТОМ.

Запуск из корня проекта (с активированным .venv):
    python scripts/battle_test_degrussa.py

Чем отличается от battle-теста №1 (Тонга): там мы сравнивали оптимум
с оптимумом, здесь — проверяем, воспроизводит ли наш симулятор
ОПУБЛИКОВАННЫЕ ФАКТИЧЕСКИЕ итоги реально построенной системы.

Кейс (источники: ARENA — государственное агентство Австралии;
pv-magazine об итогах эксплуатации 2016-2023):
  - 10.6 MWp PV на ОДНООСНЫХ ТРЕКЕРАХ + 6 MWh Li-ion BESS,
    дизельная станция ~19 MW; медный рудник, нагрузка ~12-13 MW 24/7;
  - опубликованные итоги: солнце покрывает ~20% годовой энергии,
    экономия ~5 млн литров дизеля/год, минус ~12 000 т CO2/год.

Известное различие моделей, которое ОБЯЗАНО дать расхождение:
  у нас PV на фиксированном наклоне (PVWatts fixed), у них трекеры
  (+15-25% выработки). Это тест на честность: расхождение должно быть
  в предсказуемую сторону и объяснимого масштаба.
"""

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.schema import Scenario
from src.simulate import run_simulation
from src.kpi import compute_kpi

# DeGrussa Copper Mine, ~900 км СВ от Перта.
LAT, LON, TZ = -25.55, 119.19, "Australia/Perth"

# ASSUMPTION: средняя нагрузка рудника 12.5 MW круглосуточно (объём
# годового потребления ~110 GWh согласуется с "PV ~20%" при ~21-22 GWh
# солнечной выработки на трекерах).
LOAD_KW = 12_500

# As-built размеры (ARENA).
PV_KWP, BESS_KWH, BESS_KW, DG_KW = 10_600, 6_000, 6_000, 19_000

# Опубликованные итоги для сверки.
PUB_RENEWABLE_SHARE = 0.20      # ~20% годовой энергии от солнца
PUB_DIESEL_SAVED_L = 5.0e6      # ~5 млн литров в год
PUB_CO2_SAVED_T = 12_000        # ~12 тыс. т CO2 в год

# ASSUMPTION: удельный расход большой дизельной станции 0.25 л/кВт*ч
# (эффективнее малых генсетов); цена топлива на руднике ~0.30 $/kWh —
# на энергетические итоги не влияет, нужна контракту.
L_PER_KWH = 0.25
CO2_KG_PER_L = 2.68  # IPCC, кг CO2 на литр дизеля

WEATHER_CSV = Path("tests/data/tmy_degrussa.csv")


def fetch_weather() -> None:
    if WEATHER_CSV.exists():
        print(f"Погода уже есть: {WEATHER_CSV}")
        return
    import pvlib

    try:
        print("Качаю PVGIS TMY для DeGrussa...")
        data, _ = pvlib.iotools.get_pvgis_tmy(
            LAT, LON, map_variables=True, coerce_year=2026)
        source = "PVGIS TMY"
    except Exception as e:
        print(f"PVGIS недоступен ({e}) — NASA POWER 2023.")
        data, _ = pvlib.iotools.get_nasa_power(
            LAT, LON,
            start=pd.Timestamp(2023, 1, 1, tz="UTC"),
            end=pd.Timestamp(2023, 12, 31, 23, tz="UTC"),
            map_variables=True)
        data.index = data.index.map(lambda ts: ts.replace(year=2026))
        source = "NASA POWER"
    keep = data[["ghi", "dni", "dhi", "temp_air", "wind_speed"]].copy()
    keep.index.name = "time_utc"
    keep.to_csv(WEATHER_CSV)
    print(f"Сохранено ({source}): {WEATHER_CSV}")


def build_scenario() -> Scenario:
    return Scenario.model_validate({
        "name": "DeGrussa mine as-built (ARENA facts check)",
        "site": {"name": "DeGrussa Copper Mine, WA",
                 "latitude": LAT, "longitude": LON, "timezone": TZ},
        "pv": {
            # Экономика вторична для сверки энергий; цифры типовые.
            "capex_usd_per_kw": 2500, "om_usd_per_kw_year": 30,  # ASSUMPTION
            "min_kw": PV_KWP, "max_kw": PV_KWP, "lifetime_years": 25,
        },
        "battery": {
            "capex_usd_per_kwh": 700, "capex_usd_per_kw": 0,  # ASSUMPTION
            "om_usd_per_kwh_year": 10,
            "rte_fraction": 0.90, "soc_min_fraction": 0.2,
            "min_kwh": BESS_KWH, "max_kwh": BESS_KWH,
            "min_kw": BESS_KW, "max_kw": BESS_KW,
            "lifetime_years": 10,
        },
        "diesel": {
            "capex_usd_per_kw": 400, "om_usd_per_kw_year": 20,  # ASSUMPTION
            "fuel_cost_usd_per_kwh": 0.30,                       # ASSUMPTION
            "fuel_liters_per_kwh": L_PER_KWH,
            "min_kw": DG_KW, "max_kw": DG_KW, "lifetime_years": 20,
        },
        # Рудник молотит круглые сутки: день == ночь.
        "load": {"day_kw": LOAD_KW, "night_kw": LOAD_KW,
                 "work_start_hour": 8, "work_end_hour": 18},
        "financial": {"discount_rate_fraction": 0.08,
                      "project_years": 10, "currency": "USD"},
        "reliability": {"mode": "hard"},
    })


def verdict(name, ours, published, note=""):
    dev = (ours - published) / published
    flag = "  <-- >10%" if abs(dev) > 0.10 else ""
    print(f"{name:34s} {ours:>12,.0f} {published:>12,.0f} {dev:>+7.1%}{flag}")
    if note:
        print(f"{'':34s} {note}")
    return dev


def main() -> None:
    print("=" * 74)
    print("BATTLE-ТЕСТ №2: DeGrussa — наш симулятор против опубликованных фактов")
    print("=" * 74)
    fetch_weather()

    scenario = build_scenario()
    sim = run_simulation(scenario, weather_csv=str(WEATHER_CSV),
                         write_outputs=False)
    kpi = compute_kpi(scenario, sim)

    renewable_kwh = kpi.served_kwh - kpi.dg_kwh
    saved_liters = renewable_kwh * L_PER_KWH
    saved_co2_t = saved_liters * CO2_KG_PER_L / 1000

    print()
    print(f"нагрузка года: {kpi.load_kwh/1e6:,.1f} GWh | LPSP {kpi.lpsp:.2%} | "
          f"PV выработал {kpi.pv_gen_kwh/1e6:,.1f} GWh "
          f"({kpi.pv_gen_kwh/PV_KWP:,.0f} kWh/kWp, фиксированный наклон) | "
          f"curtail {kpi.curtail_fraction_of_pv:.1%}")
    print()
    print(f"{'метрика':34s} {'GreenHouse':>12s} {'факт ARENA':>12s} {'откл.':>8s}")
    verdict("доля солнца в энергии, %",
            100 * (1 - kpi.dg_kwh / kpi.served_kwh),
            100 * PUB_RENEWABLE_SHARE)
    verdict("экономия дизеля, л/год", saved_liters, PUB_DIESEL_SAVED_L,
            note=f"(наши {renewable_kwh/1e6:,.1f} GWh чистой энергии x "
                 f"{L_PER_KWH} л/кВт*ч)")
    verdict("экономия CO2, т/год", saved_co2_t, PUB_CO2_SAVED_T)

    print()
    print("Ожидаемый источник расхождений: у DeGrussa PV на ОДНООСНЫХ")
    print("ТРЕКЕРАХ (+15-25% к выработке), наша модель v1 — фиксированный")
    print("наклон. Если наша доля солнца НИЖЕ факта на сопоставимую")
    print("величину — модель честна; если выше — разбираться.")


if __name__ == "__main__":
    main()
