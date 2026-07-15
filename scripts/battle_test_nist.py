"""Battle-тест №4: PV-полигон NIST (Гейтерсберг, США) — три контрольные точки.

Запуск из корня проекта (с активированным .venv):
    python scripts/battle_test_nist.py

Источники кейса (все публичные, государственные):
  - Конфигурации: Boyd/Chen/Dougherty, J. Res. NIST 122 (2017), Табл. 3;
  - Факт: страница NIST Photovoltaic Testbeds — «за первый год
    мониторинга (2015-2016) три массива выдали 872 MWh» (587.3 kW DC);
  - Критерий качества моделей: Boyd 2017 (J. Sol. Energy Eng.) —
    месячные PR обычно > 0.75, модели сходятся с измерениями в
    пределах 5% месячной энергии (кроме снежных месяцев).

Точка 1 (номинал): три массива на одном модуле Sharp NU-U235F2 (235 Вт):
  Canopy 243 kW = 1032 шт, наклон 5°, восток/запад (аз. 90 и 270);
  Ground 271 kW = 1152 шт, наклон 20°, юг; Roof 73 kW = 312 шт, 10°, юг.
Точка 2 (проектная симуляция): наш PVWatts-конвейер для каждого
  массива; сверка PR с опубликованным критерием (> 0.75).
Точка 3 (факт): сумма трёх массивов против 872 MWh.

Отличие от кейса OKC: фактический метеогод 2015-2016 нам не дан —
считаем на TMY; межгодовой разброс инсоляции ±3-5% входит в
интерпретацию дельты Точки 3 (в OKC датчики давали поправку −4.2%).
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import src.solar as solar_mod
from src.schema import Scenario

LAT, LON, TZ = 39.1319, -77.2141, "America/New_York"  # Гейтерсберг, кампус NIST

MODULE_KW = 0.235  # Sharp NU-U235F2

# Табл. 3 (J.Res.NIST 122): имя, модулей, наклон, азимут(ы), AC инвертора.
ARRAYS = (
    ("Canopy-E", 516, 5, 90, 130.0),    # половина навеса на восток
    ("Canopy-W", 516, 5, 270, 130.0),   # половина на запад (PVP260 общий)
    ("Ground", 1152, 20, 180, 260.0),
    ("Roof", 312, 10, 180, 75.0),       # Satcon PVS-75
)
RATED_DC = {"Canopy": 243.0, "Ground": 271.0, "Roof": 73.0}

FACT_TOTAL_MWH = 872.0        # NIST Testbeds page, 2015-2016, все массивы
PUBLISHED_PR_FLOOR = 0.75     # Boyd 2017: месячные PR обычно выше

# ASSUMPTION: температурный коэффициент Sharp NU-U235F2 по datasheet
# около −0.485%/°C (моно-Si той эпохи); инверторы PVP260/Satcon ~96%.
GAMMA_SHARP = -0.00485
INV_EFF = 0.96

WEATHER_CSV = Path("tests/data/tmy_gaithersburg.csv")


def fetch_weather() -> None:
    if WEATHER_CSV.exists():
        print(f"Погода уже есть: {WEATHER_CSV}")
        return
    import pvlib
    print("Качаю PVGIS TMY для Гейтерсберга...")
    data, _ = pvlib.iotools.get_pvgis_tmy(LAT, LON, map_variables=True,
                                          coerce_year=2026)
    keep = data[["ghi", "dni", "dhi", "temp_air", "wind_speed"]].copy()
    keep.index.name = "time_utc"
    keep.to_csv(WEATHER_CSV)
    print(f"Сохранено: {WEATHER_CSV}")


def scenario(n_modules: int, tilt: float, azimuth: float) -> Scenario:
    dc_kw = round(n_modules * MODULE_KW, 3)
    return Scenario.model_validate({
        "name": "NIST array",
        "site": {"name": "NIST Gaithersburg", "latitude": LAT,
                 "longitude": LON, "timezone": TZ},
        "pv": {"capex_usd_per_kw": 1000, "om_usd_per_kw_year": 0,
               "min_kw": dc_kw, "max_kw": dc_kw, "unit_kw": MODULE_KW,
               "tilt_deg": tilt, "azimuth_deg": azimuth,
               "lifetime_years": 25},
        "load": {"day_kw": 1, "night_kw": 1,
                 "work_start_hour": 8, "work_end_hour": 18},
        "financial": {"discount_rate_fraction": 0.08, "project_years": 10,
                      "currency": "USD"},
        "reliability": {"mode": "hard"},
    })


def poa_annual_kwh_m2(tilt: float, azimuth: float) -> float:
    """Годовая инсоляция плоскости массива (для PR) — той же
    транспозицией haydavies, что в ядре."""
    import pvlib
    w = pd.read_csv(WEATHER_CSV, index_col="time_utc", parse_dates=True)
    solpos = pvlib.solarposition.get_solarposition(w.index, LAT, LON)
    dni_extra = pvlib.irradiance.get_extra_radiation(w.index)
    poa = pvlib.irradiance.get_total_irradiance(
        tilt, azimuth, solpos["apparent_zenith"], solpos["azimuth"],
        dni=w["dni"], ghi=w["ghi"], dhi=w["dhi"],
        dni_extra=dni_extra, model="haydavies")
    return float(poa["poa_global"].fillna(0).sum() / 1000)


def main() -> None:
    print("=" * 76)
    print("BATTLE-ТЕСТ №4: NIST Gaithersburg — три массива, три контрольные точки")
    print("=" * 76)
    fetch_weather()

    # Параметры модуля под кейс (v1: константы solar.py — та же находка,
    # что в кейсе OKC: кандидат в поля схемы).
    solar_mod.GAMMA_PDC_PER_C = GAMMA_SHARP
    solar_mod.INVERTER_EFFICIENCY = INV_EFF
    solar_mod.LOSSES_PERCENT = dict(
        soiling=2.0, shading=3.0, snow=1.5, mismatch=2.0, wiring=2.0,
        connections=0.5, lid=1.5, nameplate_rating=1.0, age=0.0,
        availability=3.0,
    )  # PVWatts-дефолты + снег 1.5% (Мэриленд; ASSUMPTION)

    # ---------- Точка 1: номинал через контракт ----------
    print()
    print("Точка 1 — номинал (Табл. 3 J.Res.NIST 122) через контракт схемы:")
    dc_by_group: dict[str, float] = {}
    for name, n, tilt, az, _ in ARRAYS:
        sc = scenario(n, tilt, az)
        group = name.split("-")[0]
        dc_by_group[group] = dc_by_group.get(group, 0) + sc.pv.max_kw
    for group, dc in dc_by_group.items():
        rated = RATED_DC[group]
        print(f"  {group:7s}: {dc:7.2f} kW из модулей x0.235 "
              f"(паспорт {rated} kW, дельта {(dc-rated)/rated:+.2%})")

    # ---------- Точка 2: проектная симуляция + PR ----------
    print()
    print("Точка 2 — наш PVWatts-конвейер по массивам:")
    total_mwh = 0.0
    for name, n, tilt, az, inv_ac in ARRAYS:
        sc = scenario(n, tilt, az)
        solar_mod.DC_AC_RATIO = sc.pv.max_kw / inv_ac
        profile = solar_mod.build_solar_profile(sc, weather_csv=str(WEATHER_CSV))
        annual = float(profile.sum() * sc.pv.max_kw)          # kWh AC
        poa = poa_annual_kwh_m2(tilt, az)
        pr = annual / (sc.pv.max_kw * poa)                    # PR = Y_f / Y_r
        total_mwh += annual / 1000
        ok = "ok" if pr > PUBLISHED_PR_FLOOR else "НИЖЕ ПОРОГА"
        print(f"  {name:9s}: {annual/1000:7.1f} MWh | "
              f"{profile.sum():6.0f} kWh/kWp | PR {pr:.3f} "
              f"(критерий Boyd > {PUBLISHED_PR_FLOOR}) {ok}")

    # ---------- Точка 3: факт ----------
    dev = (total_mwh - FACT_TOTAL_MWH) / FACT_TOTAL_MWH
    status = "Ок" if abs(dev) <= 0.05 else "Требует калибровки"
    print()
    print("| Контрольная точка       | Проект/факт | Калькулятор | Дельта | Статус |")
    print(f"| 1. Номинал DC, kW       | {587.3:>11,.1f} | "
          f"{sum(dc_by_group.values()):>11,.1f} | "
          f"{(sum(dc_by_group.values())-587.3)/587.3:>+6.2%} | Ок |")
    print(f"| 3. Факт 2015-16, MWh    | {FACT_TOTAL_MWH:>11,.1f} | "
          f"{total_mwh:>11,.1f} | {dev:>+6.1%} | {status} |")

    print()
    print("Интерпретация дельты Точки 3: наш расчёт на TMY (типичный год),")
    print("факт — конкретный 2015-16 (межгодовой разброс ±3-5%); плюс")
    print("исследовательский полигон NIST моется и обслуживается лучше")
    print("PVWatts-дефолтов потерь (14%). Если |дельта| > ~5% сверх этого —")
    print("смотреть транспозицию восточно-западного навеса (аз. 90/270).")


if __name__ == "__main__":
    main()
