"""Battle-тест GreenHouse: тихоокеанский остров (Тонга), офф-грид клиника.

Запуск из корня проекта (с активированным .venv):
    python scripts/battle_test_pacific.py

Что делает (полностью автономно):
  1. Скачивает РЕАЛЬНЫЙ верифицированный почасовой профиль нагрузки NREL
     (DOE Commercial Reference Building "Outpatient", климат Майами —
     единственный жарко-влажный климат-прокси США для тропического
     острова) прямо с GitHub NREL/REopt.jl; при сбое сети честно берёт
     тот же файл из локальной копии reference/REopt.jl-master.
  2. Масштабирует профиль до пика ровно 120 kW, пишет CSV на 8760 точек.
  3. Скачивает погодный год для Тонги (PVGIS TMY, при недоступности —
     NASA POWER) и сохраняет в формате кэша проекта.
  4. Собирает scenarios/pacific_island_test.json СТРОГО по контракту
     src/schema.py (структура site/pv/battery/diesel/load/financial/
     reliability; поля вроде "meta"/"fixed_equipment" контракт отвергает).
  5. Прогоняет калькулятор: проверка референсной конфигурации
     (150 kWp / 400 kWh / 100 kW) + поиск оптимума в коридорах
     (PV 0-500, BESS 0-1000, DG 0-200) — и печатает вердикт против
     ожиданий HOMER Pro (LCOE 0.25-0.32 $/kWh).

Экономические допущения island-кейса (все — ASSUMPTION, источники в
комментариях):
  топливо: 1.35 $/л x 0.27 л/кВт*ч (типовой удельный расход генсета
      на номинале) = 0.3645 $/кВт*ч;
  CAPEX: PV 1300 $/kW, BESS 600 $/kWh, DG 500 $/kW — типичные уровни
      малых удалённых островных систем (IRENA/NREL island reports);
  жизни: PV 25 / BESS 10 / DG 15 лет; ставка 8%, горизонт 20 лет.
"""

import json
import sys
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.schema import Scenario
from src.simulate import run_simulation
from src.optimize import optimize_sizing
from src.economics import compute_economics
from src.kpi import compute_kpi

# ---------- параметры кейса ----------

CASE_NAME = "Pacific Island Battle Test (Tonga, off-grid clinic)"
LAT, LON, TZ = -21.1789, -175.1982, "Pacific/Tongatapu"
PEAK_KW = 120.0

REF_PV_KWP, REF_BESS_KWH, REF_DG_KW = 150.0, 400.0, 100.0
HOMER_LCOE_RANGE = (0.25, 0.32)  # $/kWh, ожидание HOMER Pro

# ASSUMPTION: удельный расход генсета 0.27 л/кВт*ч (типовой номинал).
DIESEL_USD_PER_L = 1.35
L_PER_KWH = 0.27
FUEL_USD_PER_KWH = round(DIESEL_USD_PER_L * L_PER_KWH, 4)  # 0.3645

# Верифицированный профиль NREL (нормированный, сумма за год = 1.0).
LOAD_URL = ("https://raw.githubusercontent.com/NREL/REopt.jl/master/"
            "data/load_profiles/electric/crb8760_norm_Miami_Outpatient.dat")
LOAD_LOCAL = Path("reference/REopt.jl-master/data/load_profiles/electric/"
                  "crb8760_norm_Miami_Outpatient.dat")

LOAD_CSV = Path("scenarios/pacific_island_load.csv")
WEATHER_CSV = Path("tests/data/tmy_tonga.csv")
SCENARIO_JSON = Path("scenarios/pacific_island_test.json")

# ASSUMPTION: годовое потребление клиники-прототипа. CRB-профиль
# нормирован (сумма = 1), масштаб задаём через ПИК 120 kW по заданию.
ANNUAL_IS_DERIVED = True


# ---------- шаг 1-2: нагрузка ----------


def fetch_load_profile() -> list[float]:
    """Скачивает нормированный 8760-профиль NREL; fallback — локальная
    копия REopt (тот же файл, честно логируем источник)."""
    try:
        print(f"Скачиваю профиль нагрузки NREL:\n  {LOAD_URL}")
        resp = requests.get(LOAD_URL, timeout=60)
        resp.raise_for_status()
        values = [float(line) for line in resp.text.splitlines() if line.strip()]
        print("Скачивание завершено (GitHub NREL/REopt.jl).")
    except Exception as e:
        print(f"Сеть недоступна ({e}) — беру ТОТ ЖЕ файл из локальной "
              f"копии {LOAD_LOCAL}")
        values = [float(line) for line in LOAD_LOCAL.read_text().splitlines()
                  if line.strip()]
    if len(values) != 8760:
        raise ValueError(f"Ожидалось 8760 точек, получено {len(values)}")
    return values


def build_load_csv(norm_values: list[float]) -> pd.Series:
    """Масштабирует профиль до пика PEAK_KW и пишет CSV по контракту
    profiles.py (timestamp местного времени + load_kw)."""
    scale = PEAK_KW / max(norm_values)
    load_kw = [round(v * scale, 4) for v in norm_values]

    index = pd.date_range("2026-01-01 00:00", periods=8760, freq="h")
    LOAD_CSV.parent.mkdir(exist_ok=True)
    pd.DataFrame({"timestamp": index, "load_kw": load_kw}).to_csv(
        LOAD_CSV, index=False)
    series = pd.Series(load_kw, index=index)
    print(f"Профиль масштабирован до пика {max(load_kw):.1f} kW; "
          f"год = {series.sum():,.0f} kWh; средняя {series.mean():.1f} kW; "
          f"записан {LOAD_CSV}")
    return series


# ---------- шаг 3: погода Тонги ----------


def fetch_weather() -> None:
    """PVGIS TMY для Тонги; если сервис не покрывает Пацифику —
    NASA POWER (фактический 2023 год, честно предупреждаем)."""
    if WEATHER_CSV.exists():
        print(f"Погода уже скачана: {WEATHER_CSV} (пропускаю)")
        return
    import pvlib

    try:
        print("Пробую PVGIS TMY для Тонги...")
        data, _ = pvlib.iotools.get_pvgis_tmy(
            LAT, LON, map_variables=True, coerce_year=2026)
        source = "PVGIS TMY"
    except Exception as e:
        print(f"PVGIS не покрывает точку ({e}) — беру NASA POWER 2023 "
              "(фактический год, не TMY — честное отличие).")
        data, _ = pvlib.iotools.get_nasa_power(
            LAT, LON,
            start=pd.Timestamp(2023, 1, 1, tz="UTC"),
            end=pd.Timestamp(2023, 12, 31, 23, tz="UTC"),
            map_variables=True)
        data.index = data.index.map(lambda ts: ts.replace(year=2026))
        source = "NASA POWER 2023"

    keep = data[["ghi", "dni", "dhi", "temp_air", "wind_speed"]].copy()
    keep.index.name = "time_utc"
    keep.to_csv(WEATHER_CSV)
    print(f"Погода ({source}) сохранена: {WEATHER_CSV} ({len(keep)} часов)")


# ---------- шаг 4: сценарий по контракту ----------


def build_scenario(sizing: bool) -> dict:
    """JSON строго по src/schema.py. sizing=False — референсные размеры
    зафиксированы (min=max); True — коридоры поиска из задания."""
    return {
        "name": CASE_NAME + (" [sizing]" if sizing else " [reference]"),
        "site": {
            "name": "Tongatapu clinic (prototype: NREL CRB Outpatient/Miami)",
            "latitude": LAT, "longitude": LON, "timezone": TZ,
        },
        "pv": {
            # ASSUMPTION: остров, малый масштаб — 1300 $/kW установленных.
            "capex_usd_per_kw": 1300, "om_usd_per_kw_year": 20,
            "min_kw": 0 if sizing else REF_PV_KWP,
            "max_kw": 500 if sizing else REF_PV_KWP,
            "lifetime_years": 25,
        },
        "battery": {
            # ASSUMPTION: островной BESS ~600 $/kWh (контейнер + доставка).
            "capex_usd_per_kwh": 600, "capex_usd_per_kw": 0,
            "om_usd_per_kwh_year": 10,
            "rte_fraction": 0.90, "soc_min_fraction": 0.2,
            "min_kwh": 0 if sizing else REF_BESS_KWH,
            "max_kwh": 1000 if sizing else REF_BESS_KWH,
            "min_kw": 0 if sizing else REF_BESS_KWH / 2,
            "max_kw": 500 if sizing else REF_BESS_KWH / 2,  # C/2 ASSUMPTION
            "lifetime_years": 10,
        },
        "diesel": {
            # ASSUMPTION: контейнерный генсет с доставкой ~500 $/kW.
            "capex_usd_per_kw": 500, "om_usd_per_kw_year": 25,
            "fuel_cost_usd_per_kwh": FUEL_USD_PER_KWH,
            "fuel_liters_per_kwh": L_PER_KWH,
            "min_kw": 0 if sizing else REF_DG_KW,
            "max_kw": 200 if sizing else REF_DG_KW,
            "lifetime_years": 15,
        },
        "load": {"profile_csv": str(LOAD_CSV)},
        "financial": {
            "discount_rate_fraction": 0.08,
            "project_years": 20,
            "currency": "USD",
        },
        "reliability": {"mode": "hard"},
    }


# ---------- шаг 5: сам battle-тест ----------


def main() -> None:
    print("=" * 66)
    print("BATTLE-ТЕСТ:", CASE_NAME)
    print("=" * 66)

    norm = fetch_load_profile()
    load = build_load_csv(norm)
    fetch_weather()

    scenario_dict = build_scenario(sizing=False)
    SCENARIO_JSON.write_text(
        json.dumps(scenario_dict, indent=2, ensure_ascii=False),
        encoding="utf-8")
    print(f"Файл {SCENARIO_JSON} успешно создан (контракт schema.py).")

    # --- 5а. Проверка референсной конфигурации (rule-симулятор) ---
    print()
    print("--- Референсная конфигурация 150 kWp / 400 kWh / 100 kW ---")
    ref = Scenario.model_validate(scenario_dict)
    sim = run_simulation(ref, weather_csv=str(WEATHER_CSV),
                         write_outputs=False)
    kpi = compute_kpi(ref, sim)
    eco = compute_economics(ref, sim)

    print(f"LPSP: {kpi.lpsp:.2%} (недопоставка {kpi.shortfall_kwh:,.0f} kWh; "
          f"пик 120 kW > DG 100 kW — батарея обязана прикрывать пик)")
    print(f"Renewable fraction: {kpi.renewable_fraction:.1%}")
    print(f"Дизель: {kpi.dg_kwh:,.0f} kWh = {kpi.dg_fuel_liters:,.0f} л "
          f"(${kpi.dg_fuel_usd:,.0f}/год)")
    print(f"LCOE: ${eco.lcoe_usd_per_kwh:.4f}/kWh | "
          f"NPC (20 лет): ${eco.npc_usd:,.0f}")

    lo, hi = HOMER_LCOE_RANGE
    in_range = lo <= eco.lcoe_usd_per_kwh <= hi
    print(f"Ожидание HOMER Pro: {lo:.2f}-{hi:.2f} $/kWh -> "
          f"{'ВНУТРИ диапазона' if in_range else 'ВНЕ диапазона — разобрать'}")

    # --- 5б. Наш оптимум в коридорах задания ---
    print()
    print("--- Оптимум GreenHouse (PV 0-500, BESS 0-1000, DG 0-200, hard) ---")
    sizing_scenario = Scenario.model_validate(build_scenario(sizing=True))
    opt = optimize_sizing(sizing_scenario, weather_csv=str(WEATHER_CSV),
                          write_outputs=False)
    s, m = opt.sizes, opt.sim.manifest
    served = m["totals_kwh"]["load"] - m["totals_kwh"]["shortfall"]
    opt_lcoe = m["objective_value"] / served

    rows = [("PV, kWp", s["pv_kwp"], REF_PV_KWP),
            ("BESS, kWh", s["batt_kwh"], REF_BESS_KWH),
            ("BESS, kW", s["batt_kw"], REF_BESS_KWH / 2),
            ("DG, kW", s["dg_kw"], REF_DG_KW)]
    print(f"{'размер':10s} {'GreenHouse':>11s} {'референс':>9s} {'откл.':>8s}")
    for name, ours, refv in rows:
        dev = (ours - refv) / refv if refv else float("nan")
        flag = " <-- >10%" if abs(dev) > 0.10 else ""
        print(f"{name:10s} {ours:>11,.1f} {refv:>9,.0f} {dev:>+7.0%}{flag}")
    print(f"LCOE оптимума: ${opt_lcoe:.4f}/kWh | издержки "
          f"${m['objective_value']:,.0f}/год | решено за {m['solve_seconds']} c")

    print()
    print("Готово: сценарий, CSV нагрузки и погода сохранены; числа выше —")
    print("материал для сравнения с HOMER/REopt (вкладка Валидация в app.py).")


if __name__ == "__main__":
    main()
