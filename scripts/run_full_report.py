"""GreenHouse: ПОЛНЫЙ отчёт одной командой (Definition of Done миссии).

Запуск из корня проекта (с активированным .venv):
    python scripts/run_full_report.py

Делает всё и складывает в results/:
  1. Проверка вендорской конфигурации (yemen_vendor.json):
     симуляция года -> KPI-таблица + экономика (NPC, LCOE, payback);
  2. Оптимальный сайзинг (yemen_sizing.json): размеры в kW/kWh И в
     штуках + сверка с вендором;
  3. Sensitivity: tornado, Pareto с коленом, стрессы;
  4. Все графики (диспетчеризация, CAPEX, tornado, Pareto) и
     manifest каждого прогона.

Время работы ~3 минуты (два десятка LP-задач).
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.schema import Scenario
from src.simulate import run_simulation
from src.optimize import optimize_sizing
from src.economics import compute_economics
from src.kpi import compute_kpi
from src.sweep import run_sensitivity

# Готовые художники из соседних скриптов.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from show_results import plot_dispatch_week, plot_dispatch_monthly, plot_capex_pie
from show_sweeps import plot_tornado, plot_pareto

VENDOR = "scenarios/yemen_vendor.json"
SIZING = "scenarios/yemen_sizing.json"
WEATHER = "tests/data/tmy_sanaa_pvgis_sarah3.csv"


def load_scenario(path: str) -> Scenario:
    with open(path, encoding="utf-8") as f:
        return Scenario.model_validate(json.load(f))


def main() -> None:
    Path("results").mkdir(exist_ok=True)

    # ---------- 1. Вендорская конфигурация ----------
    print("=" * 62)
    print("1/3  ПРОВЕРКА ВЕНДОРА (simulate)")
    print("=" * 62)
    vendor = load_scenario(VENDOR)
    sim = run_simulation(vendor, weather_csv=WEATHER)
    kpi = compute_kpi(vendor, sim)
    eco = compute_economics(vendor, sim)

    print(f"нагрузка {kpi.load_kwh:,.0f} kWh/год | LPSP {kpi.lpsp:.1%} | "
          f"renewable {kpi.renewable_fraction:.1%}")
    print(f"дизель {kpi.dg_kwh:,.0f} kWh за {kpi.dg_hours:,.0f} ч "
          f"(${kpi.dg_fuel_usd:,.0f})")
    print(f"CAPEX ${eco.capex_total_usd:,.0f} | годовые ${eco.annual_cost_usd:,.0f}")
    print(f"NPC ${eco.npc_usd:,.0f} | LCOE ${eco.lcoe_usd_per_kwh:.4f}/kWh | "
          f"payback {eco.simple_payback_years:.1f} лет")
    print(f"manifest: {sim.manifest_path}")

    plot_dispatch_week(sim.table)
    plot_dispatch_monthly(sim.table)
    plot_capex_pie(eco)

    # ---------- 2. Оптимальный сайзинг ----------
    print()
    print("=" * 62)
    print("2/3  ОПТИМАЛЬНЫЙ САЙЗИНГ (optimize)")
    print("=" * 62)
    sizing_scenario = load_scenario(SIZING)
    opt = optimize_sizing(sizing_scenario, weather_csv=WEATHER)
    s, u, m = opt.sizes, opt.units, opt.sim.manifest

    print(f"{'размер':12s} {'оптимум':>10s} {'вендор':>10s}   штуки")
    print(f"{'PV, kWp':12s} {s['pv_kwp']:>10,.1f} {1500:>10,}   "
          f"панелей {u['pv_panels']}")
    print(f"{'BESS, kWh':12s} {s['batt_kwh']:>10,.1f} {3132:>10,}   "
          f"шкафов {u['batt_cabinets']}")
    print(f"{'BESS, kW':12s} {s['batt_kw']:>10,.1f} {1500:>10,}   "
          f"PCS {u['batt_pcs_units']}")
    print(f"{'DG, kW':12s} {s['dg_kw']:>10,.1f} {1000:>10,}   "
          f"генсетов {u['dg_gensets']}")
    print(f"годовые издержки оптимума ${m['objective_value']:,.0f} "
          f"(вендор ${eco.annual_cost_usd:,.0f}) | "
          f"экономия ${eco.annual_cost_usd - m['objective_value']:,.0f}/год")
    print(f"солвер {m['solver']} за {m['solve_seconds']} c | manifest: "
          f"{opt.sim.manifest_path}")

    # ---------- 3. Sensitivity ----------
    print()
    print("=" * 62)
    print("3/3  SENSITIVITY (sweep, ~2 минуты)")
    print("=" * 62)
    report = run_sensitivity(sizing_scenario, weather_csv=WEATHER)
    plot_tornado(report)
    plot_pareto(report)

    print()
    print("Pareto-фронт:")
    cols = ["lpsp_target", "annual_cost_usd", "pv_kwp", "batt_kwh", "dg_kw"]
    df_show = report.pareto[cols].copy(); df_show["lpsp_target"] = (df_show["lpsp_target"] * 100).map("{:.1f}%".format); print(df_show.round(1).to_string(index=False))
    print(f"колено: LPSP {report.knee['lpsp']:.2%} за "
          f"${report.knee['annual_cost_usd']:,.0f}/год")
    print()
    print("Стрессы оптимального дизайна:")
    print(report.stress.round(4).to_string(index=False))
    print()
    print("Готово. Всё лежит в results/ (графики .png, прогоны .parquet, "
          "манифесты .json, свипы в results/sweeps/).")


if __name__ == "__main__":
    main()
