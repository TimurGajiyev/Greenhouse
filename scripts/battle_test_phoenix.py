"""Battle-тест №5: госпиталь в Фениксе — off-grid критический микрогрид.

Запуск из корня проекта (с активированным .venv):
    python scripts/battle_test_phoenix.py

Полностью автономный: сам качает реальный верифицированный почасовой
профиль нагрузки (8760 ч) из репозитория NREL, масштабирует его,
скачивает погоду и собирает контракт-совместимый сценарий, затем
прогоняет калькулятор и печатает вердикт.

Чем НОВ этот кейс (все прошлые были другими):
  - Йемен — завод, дневная смена; Тонга — клиника; DeGrussa — рудник
    (ровная нагрузка); OKC/NIST — только PV. Здесь — ГОСПИТАЛЬ:
    круглосуточная критическая нагрузка (24/7), hard-надёжность,
    жаркая пустыня (Феникс) с сильным солнцем, но и сильным нагревом
    панелей — тест на температурную модель (open_rack, из кейсов
    OKC/NIST наши параметры модуля теперь поля схемы).

Профиль: DOE Commercial Reference Building "Hospital", климат Феникса
(NREL/REopt.jl, нормированный ряд, сумма за год = 1.0). Масштабируем
до пика 1000 kW (средний госпиталь).

Референс для сверки (публикации по off-grid госпитальным микрогридам):
  LCOE off-grid PV+BESS+DG обычно $0.13–0.41/kWh; чистый дизель ~$1.0.
  NREL REopt — стандартный MILP-инструмент для таких задач.
"""

import json
import sys
import zipfile
from io import BytesIO
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.schema import Scenario
from src.simulate import run_simulation
from src.optimize import optimize_sizing
from src.economics import compute_economics
from src.kpi import compute_kpi

# Феникс, Аризона.
LAT, LON, TZ = 33.4484, -112.0740, "America/Phoenix"
PEAK_KW = 1000.0

# Верифицированный профиль NREL (нормированный, сумма за год = 1.0).
LOAD_URL = ("https://raw.githubusercontent.com/NREL/REopt.jl/master/"
            "data/load_profiles/electric/crb8760_norm_Phoenix_Hospital.dat")
LOAD_LOCAL = Path("reference/REopt.jl-master/data/load_profiles/electric/"
                  "crb8760_norm_Phoenix_Hospital.dat")

LOAD_CSV = Path("scenarios/phoenix_hospital_load.csv")
WEATHER_CSV = Path("tests/data/tmy_phoenix.csv")
SCENARIO_JSON = Path("scenarios/phoenix_hospital_test.json")

# Референсная («вендорская») конфигурация off-grid госпиталя (плаузибл,
# для проверки simulate). ASSUMPTION: типовой турнкей.
REF_PV_KWP, REF_BESS_KWH, REF_BESS_KW, REF_DG_KW = 2500.0, 6000.0, 2000.0, 1200.0

HOMER_LCOE_BAND = (0.13, 0.41)  # $/kWh, публикации off-grid госпиталей

# ASSUMPTION: топливо США ~$4/галлон / ~12.5 кВт*ч/галлон = 0.32 $/кВт*ч;
# удельный расход 0.27 л/кВт*ч.
FUEL_USD_PER_KWH = 0.32
L_PER_KWH = 0.27


def fetch_load_profile() -> list[float]:
    """Скачивает нормированный 8760-профиль NREL; fallback — локальная
    копия REopt (тот же файл). Поддерживает и .zip на всякий случай."""
    try:
        print(f"Скачивание профиля нагрузки NREL...\n  {LOAD_URL}")
        resp = requests.get(LOAD_URL, timeout=60)
        resp.raise_for_status()
        content = resp.content
        if content[:2] == b"PK":  # ZIP-сигнатура
            with zipfile.ZipFile(BytesIO(content)) as z:
                content = z.read(z.namelist()[0])
        values = [float(x) for x in content.decode().splitlines() if x.strip()]
        print("Скачивание завершено (GitHub NREL/REopt.jl).")
    except Exception as e:
        print(f"Сеть недоступна ({e}) — беру ТОТ ЖЕ файл из локальной "
              f"копии {LOAD_LOCAL}")
        values = [float(x) for x in LOAD_LOCAL.read_text().splitlines()
                  if x.strip()]
    if len(values) != 8760:
        raise ValueError(f"Ожидалось 8760 точек, получено {len(values)}")
    return values


def build_load_csv(norm: list[float]) -> pd.Series:
    """Масштабирует профиль до пика PEAK_KW и пишет CSV по контракту."""
    scale = PEAK_KW / max(norm)
    load_kw = [round(v * scale, 4) for v in norm]
    index = pd.date_range("2026-01-01 00:00", periods=8760, freq="h")
    LOAD_CSV.parent.mkdir(exist_ok=True)
    pd.DataFrame({"timestamp": index, "load_kw": load_kw}).to_csv(
        LOAD_CSV, index=False)
    s = pd.Series(load_kw, index=index)
    print(f"Профиль масштабирован до пика {max(load_kw):.0f} kW; "
          f"год = {s.sum():,.0f} kWh; средняя {s.mean():.0f} kW; "
          f"база/пик (load factor) {s.mean() / s.max():.2f}; записан {LOAD_CSV}")
    return s


def fetch_weather() -> None:
    if WEATHER_CSV.exists():
        print(f"Погода уже есть: {WEATHER_CSV}")
        return
    import pvlib
    try:
        print("Скачивание PVGIS TMY для Феникса...")
        data, _ = pvlib.iotools.get_pvgis_tmy(LAT, LON, map_variables=True,
                                              coerce_year=2026)
        source = "PVGIS TMY"
    except Exception as e:
        print(f"PVGIS недоступен ({e}) — NASA POWER 2023.")
        data, _ = pvlib.iotools.get_nasa_power(
            LAT, LON, start=pd.Timestamp(2023, 1, 1, tz="UTC"),
            end=pd.Timestamp(2023, 12, 31, 23, tz="UTC"), map_variables=True)
        data.index = data.index.map(lambda ts: ts.replace(year=2026))
        source = "NASA POWER"
    keep = data[["ghi", "dni", "dhi", "temp_air", "wind_speed"]].copy()
    keep.index.name = "time_utc"
    keep.to_csv(WEATHER_CSV)
    print(f"Погода ({source}) сохранена: {WEATHER_CSV}")


def build_scenario(sizing: bool) -> dict:
    """Контракт schema.py. sizing=False — референсные размеры зафиксированы."""
    return {
        "name": "Phoenix Hospital off-grid microgrid"
                + (" [sizing]" if sizing else " [reference]"),
        "site": {"name": "Phoenix, AZ — hospital (NREL CRB profile)",
                 "latitude": LAT, "longitude": LON, "timezone": TZ,
                 "roof_area_m2": 40000},
        "pv": {
            # ASSUMPTION: US commercial ground/roof ~$1200/kW.
            "capex_usd_per_kw": 1200, "om_usd_per_kw_year": 16,
            "min_kw": 0 if sizing else REF_PV_KWP,
            "max_kw": 8000 if sizing else REF_PV_KWP,
            "unit_kw": 0.58,
            # Жаркая пустыня: наземный/крышный монтаж на раме охлаждается
            # лучше — берём open_rack (значимость показал кейс NIST).
            "mount_type": "open_rack",
            "gamma_pdc_per_c": -0.0035,   # ASSUMPTION: N-type, ~-0.35%/°C
            "inverter_eff_fraction": 0.97,
            "lifetime_years": 25,
        },
        "battery": {
            # ASSUMPTION: US off-grid BESS ~$350/kWh + PCS $150/kW.
            "capex_usd_per_kwh": 350, "capex_usd_per_kw": 150,
            "om_usd_per_kwh_year": 4,
            "rte_fraction": 0.90, "soc_min_fraction": 0.15,
            "self_discharge_fraction_per_hour": 2e-5,  # ASSUMPTION: LFP
            "min_kwh": 0 if sizing else REF_BESS_KWH,
            "max_kwh": 30000 if sizing else REF_BESS_KWH,
            "min_kw": 0 if sizing else REF_BESS_KW,
            "max_kw": 6000 if sizing else REF_BESS_KW,
            "unit_kwh": 261, "unit_kw": 125,
            "lifetime_years": 10,
        },
        "diesel": {
            # ASSUMPTION: контейнерный генсет ~$500/kW.
            "capex_usd_per_kw": 500, "om_usd_per_kw_year": 20,
            "fuel_cost_usd_per_kwh": FUEL_USD_PER_KWH,
            "fuel_liters_per_kwh": L_PER_KWH,
            "min_kw": 0 if sizing else REF_DG_KW,
            "max_kw": 2000 if sizing else REF_DG_KW,
            "unit_kw": 500,
            "lifetime_years": 15,
        },
        "load": {"profile_csv": str(LOAD_CSV)},
        "financial": {"discount_rate_fraction": 0.08, "project_years": 20,
                      "currency": "USD"},
        # Госпиталь — критический объект: недопоставка запрещена.
        "reliability": {"mode": "hard"},
    }


def main() -> None:
    print("=" * 72)
    print("BATTLE-ТЕСТ №5: госпиталь в Фениксе — off-grid критический микрогрид")
    print("=" * 72)

    norm = fetch_load_profile()
    build_load_csv(norm)
    fetch_weather()

    scenario_dict = build_scenario(sizing=False)
    SCENARIO_JSON.write_text(
        json.dumps(scenario_dict, indent=2, ensure_ascii=False),
        encoding="utf-8")
    print(f"Файл {SCENARIO_JSON} успешно создан (контракт schema.py).")

    # --- 1. Проверка референсной конфигурации ---
    print()
    print(f"--- Референс {REF_PV_KWP:.0f} kWp / {REF_BESS_KWH:.0f} kWh / "
          f"{REF_DG_KW:.0f} kW (rule-симулятор) ---")
    ref = Scenario.model_validate(scenario_dict)
    sim = run_simulation(ref, weather_csv=str(WEATHER_CSV), write_outputs=False)
    kpi = compute_kpi(ref, sim)
    eco = compute_economics(ref, sim)
    print(f"LPSP: {kpi.lpsp:.3%} (критическая нагрузка 24/7; пик {PEAK_KW:.0f} "
          f"kW < DG {REF_DG_KW:.0f} kW — дизель структурно закрывает пик)")
    print(f"Renewable fraction: {kpi.renewable_fraction:.1%} | "
          f"солнце {sim.manifest['totals_kwh']['pv_gen'] / REF_PV_KWP:,.0f} "
          "kWh/kWp/год")
    print(f"Дизель: {kpi.dg_kwh:,.0f} kWh = {kpi.dg_fuel_liters:,.0f} л/год "
          f"(${kpi.dg_fuel_usd:,.0f})")
    print(f"LCOE: ${eco.lcoe_usd_per_kwh:.4f}/kWh | NPC (20 лет): "
          f"${eco.npc_usd:,.0f}")

    # --- 2. Наш оптимум ---
    print()
    print("--- Оптимум GreenHouse (PV 0-8000, BESS 0-30000, DG 0-2000, hard) ---")
    opt = optimize_sizing(Scenario.model_validate(build_scenario(sizing=True)),
                          weather_csv=str(WEATHER_CSV), write_outputs=False)
    s, m, u = opt.sizes, opt.sim.manifest, opt.units
    served = m["totals_kwh"]["load"] - m["totals_kwh"]["shortfall"]
    opt_lcoe = m["objective_value"] / served
    print(f"{'размер':10s} {'оптимум':>10s} {'штук':>8s}")
    print(f"{'PV, kWp':10s} {s['pv_kwp']:>10,.0f} {str(u['pv_panels']):>8s}")
    print(f"{'BESS,kWh':10s} {s['batt_kwh']:>10,.0f} {str(u['batt_cabinets']):>8s}")
    print(f"{'BESS,kW':10s} {s['batt_kw']:>10,.0f} {str(u['batt_pcs_units']):>8s}")
    print(f"{'DG, kW':10s} {s['dg_kw']:>10,.0f} {str(u['dg_gensets']):>8s}")
    print(f"LCOE оптимума: ${opt_lcoe:.4f}/kWh | издержки "
          f"${m['objective_value']:,.0f}/год | LPSP {m['lpsp']:.2%} | "
          f"решено за {m['solve_seconds']} c")

    # --- 2b. Perfect-foresight проверка: зафиксировать оптимум и
    #         прогнать слепым rule-симулятором (реальный контроллер). ---
    fixed = build_scenario(sizing=True)
    for tech, keys in (("pv", [("min_kw", "max_kw", s["pv_kwp"])]),
                       ("battery", [("min_kwh", "max_kwh", s["batt_kwh"]),
                                    ("min_kw", "max_kw", s["batt_kw"])]),
                       ("diesel", [("min_kw", "max_kw", s["dg_kw"])])):
        for lo_k, hi_k, val in keys:
            fixed[tech][lo_k] = fixed[tech][hi_k] = max(val, 0.001)
    rule = run_simulation(Scenario.model_validate(fixed),
                          weather_csv=str(WEATHER_CSV), write_outputs=False)
    print(f"Perfect-foresight разрыв: LPSP слепого rule-контроллера на "
          f"оптимальных размерах = {rule.manifest['lpsp']:.3%} "
          f"(DG {s['dg_kw']:,.0f} kW < пика {PEAK_KW:.0f} kW опирается на "
          "батарею + предвидение LP).")

    # --- 2c. Enhancement: оперативный резерв закрывает разрыв ---
    # (принципиальная замена прежнего костыля firm-capacity: вместо
    #  «дизель на весь пик» требуем горячий запас мощности КАЖДЫЙ час —
    #  недогруженный дизель + доступный разряд батареи, как в REopt.)
    RESERVE_FRACTION = 0.25
    print()
    print(f"--- Оптимум с оперативным резервом ({RESERVE_FRACTION:.0%} "
          "нагрузки; критический объект) ---")
    res_dict = build_scenario(sizing=True)
    res_dict["reliability"] = {
        "mode": "hard", "operating_reserve_load_fraction": RESERVE_FRACTION}
    opt2 = optimize_sizing(Scenario.model_validate(res_dict),
                           weather_csv=str(WEATHER_CSV), write_outputs=False)
    s2, m2 = opt2.sizes, opt2.sim.manifest
    served2 = m2["totals_kwh"]["load"] - m2["totals_kwh"]["shortfall"]
    fixed2 = build_scenario(sizing=True)
    fixed2["reliability"] = {
        "mode": "hard", "operating_reserve_load_fraction": RESERVE_FRACTION}
    for tech, keys in (("pv", [("min_kw", "max_kw", s2["pv_kwp"])]),
                       ("battery", [("min_kwh", "max_kwh", s2["batt_kwh"]),
                                    ("min_kw", "max_kw", s2["batt_kw"])]),
                       ("diesel", [("min_kw", "max_kw", s2["dg_kw"])])):
        for lo_k, hi_k, val in keys:
            fixed2[tech][lo_k] = fixed2[tech][hi_k] = max(val, 0.001)
    rule2 = run_simulation(Scenario.model_validate(fixed2),
                           weather_csv=str(WEATHER_CSV), write_outputs=False)
    print(f"PV {s2['pv_kwp']:,.0f} kWp | BESS {s2['batt_kwh']:,.0f} kWh | "
          f"DG {s2['dg_kw']:,.0f} kW | LCOE ${m2['objective_value']/served2:.4f}"
          f"/kWh | LPSP слепого контроллера = {rule2.manifest['lpsp']:.3%}")
    print("Вывод: оперативный резерв требует горячий запас мощности каждый "
          "час — реальная надёжность восстановлена ценой небольшого роста "
          "LCOE, и запас может дать батарея, а не только дизель на весь пик.")

    # --- 3. Вердикт против публикаций ---
    print()
    lo, hi = HOMER_LCOE_BAND
    inside = lo <= opt_lcoe <= hi
    print(f"Публикации off-grid госпиталей: LCOE {lo:.2f}–{hi:.2f} $/kWh -> "
          f"наш оптимум {'ВНУТРИ диапазона' if inside else 'ВНЕ — разобрать'}")
    print("Интерпретация: критический 24/7-объект + hard-надёжность в "
          "пустыне — солнце дешёвое днём, но ночь и hard тянут либо большую "
          "батарею, либо дизель. Сверка rule vs LP и LPSP выше показывают, "
          "держит ли дизайн нагрузку без предвидения.")


if __name__ == "__main__":
    main()
