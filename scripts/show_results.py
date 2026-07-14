"""Дашборд результатов GreenHouse (после шагов 5-6).

Запуск из корня проекта (с активированным .venv):
    python scripts/show_results.py

Строит для scenarios/yemen_vendor.json:
  results/dispatch_week.png    — стековая диаграмма "кто кормит завод"
                                 за характерную неделю (час за часом);
  results/dispatch_monthly.png — вклад источников по месяцам за год;
  results/capex_pie.png        — CAPEX по технологиям;
  + печатает сравнение "гибрид vs 100% дизель" (LCOE, renewable, CO2).

Сейчас это ВЕНДОРСКАЯ конфигурация (simulate-режим). После шага 8
тот же скрипт покажет оптимальное решение — вход не изменится.
"""

import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # рисуем в файл, окно не открываем
import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.schema import Scenario
from src.simulate import run_simulation
from src.economics import compute_economics
from src.kpi import compute_kpi

SCENARIO_PATH = "scenarios/yemen_vendor.json"
WEATHER_CSV = "tests/data/tmy_sanaa_pvgis_sarah3.csv"

# Неделя для почасового графика: середина февраля — солнечный сезон
# с полным суточным циклом батареи (см. отчёт шага 5).
WEEK_SLICE = ("2026-02-16", "2026-02-22")

# Цвета — категориальные слоты валидированной палитры; закреплены за
# сущностями НАВСЕГДА (одна технология = один цвет во всех графиках).
C_PV = "#eda100"      # солнце
C_BESS = "#1baf7a"    # батарея
C_DG = "#e34948"      # дизель
INK = "#0b0b0b"
MUTED = "#898781"
GRID = "#e1e0d9"
SURFACE = "#fcfcfb"

# ASSUMPTION: операционные выбросы дизель-генерации ~0.72 кг CO2 на
# kWh электричества (=2.68 кг CO2/л топлива * ~0.27 л/кВт*ч генсета;
# факторы IPCC/DEFRA). Встроенные выбросы производства PV/BESS не
# учитываются (только эксплуатация). Точнее станет, когда в сценарии
# появится fuel_liters_per_kwh из datasheet.
CO2_KG_PER_DIESEL_KWH = 0.72


def style_axis(ax):
    """Единый тихий стиль: сетка-волосок, без лишних рамок."""
    ax.set_facecolor(SURFACE)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    for spine in ("left", "bottom"):
        ax.spines[spine].set_color(GRID)
    ax.tick_params(colors=MUTED)


def plot_dispatch_week(table) -> None:
    """(a) Стековая area-диаграмма: из чего складывается питание завода."""
    week = table.loc[WEEK_SLICE[0]:WEEK_SLICE[1]]
    x = range(len(week))

    fig, ax = plt.subplots(figsize=(12, 4.5), facecolor=SURFACE)
    ax.stackplot(
        x,
        week.pv_to_load_kw,
        week.discharge_kw,
        week.dg_kw,
        labels=["PV напрямую", "батарея (разряд)", "дизель"],
        colors=[C_PV, C_BESS, C_DG],
        linewidth=0,
    )
    # Линия нагрузки поверх стека: стек обязан дотягиваться до неё
    # (разрыв означал бы недопоставку).
    ax.plot(x, week.load_kw, color=INK, linewidth=1.2, linestyle="--",
            label="нагрузка")

    ax.set_title(
        f"Кто кормит завод: неделя {WEEK_SLICE[0]} — {WEEK_SLICE[1]}",
        color=INK, fontsize=11, pad=28,
    )
    ax.set_xlabel("часы недели (местное время)", color=MUTED)
    ax.set_ylabel("kW", color=MUTED)
    # Отметки дней вместо безликих номеров часов.
    ax.set_xticks(range(0, len(week) + 1, 24))
    ax.set_xticklabels(
        [d.strftime("%d.%m") for d in week.index[::24]] + [""], fontsize=9
    )
    # Легенда НАД графиком в одну строку — не заслоняет данные.
    ax.legend(loc="lower center", bbox_to_anchor=(0.5, 1.0), ncol=4,
              frameon=False, fontsize=9)
    style_axis(ax)
    fig.tight_layout()
    fig.savefig("results/dispatch_week.png", dpi=150, facecolor=SURFACE)
    print("сохранено: results/dispatch_week.png")


def plot_dispatch_monthly(table) -> None:
    """(a-год) Вклад источников по месяцам: сезонность одним взглядом."""
    monthly = (
        table[["pv_to_load_kw", "discharge_kw", "dg_kw"]]
        .resample("MS")
        .sum()  # Δt=1 ч, поэтому сумма kW == kWh; для другого Δt — умножить
        / 1000.0  # -> MWh, чтобы ось не пестрела нулями
    )
    months = range(1, 13)

    fig, ax = plt.subplots(figsize=(12, 4.5), facecolor=SURFACE)
    bottom = None
    for col, color, label in (
        ("pv_to_load_kw", C_PV, "PV напрямую"),
        ("discharge_kw", C_BESS, "батарея (разряд)"),
        ("dg_kw", C_DG, "дизель"),
    ):
        vals = monthly[col].to_numpy()
        ax.bar(months, vals, width=0.62, bottom=bottom, color=color,
               label=label)
        bottom = vals if bottom is None else bottom + vals

    ax.set_title("Поставленная энергия по месяцам", color=INK, fontsize=11,
                 pad=28)
    ax.set_xlabel("месяц", color=MUTED)
    ax.set_ylabel("MWh", color=MUTED)
    ax.set_xticks(list(months))
    ax.legend(loc="lower center", bbox_to_anchor=(0.5, 1.0), ncol=3,
              frameon=False, fontsize=9)
    style_axis(ax)
    fig.tight_layout()
    fig.savefig("results/dispatch_monthly.png", dpi=150, facecolor=SURFACE)
    print("сохранено: results/dispatch_monthly.png")


def plot_capex_pie(eco) -> None:
    """(b) CAPEX по технологиям."""
    labels = {"pv": "PV", "battery": "BESS", "diesel": "DG"}
    colors = {"pv": C_PV, "battery": C_BESS, "diesel": C_DG}
    names = [labels[k] for k in eco.by_tech]
    values = [t.capex_usd for t in eco.by_tech.values()]

    fig, ax = plt.subplots(figsize=(6, 5), facecolor=SURFACE)
    wedges, texts, autotexts = ax.pie(
        values,
        labels=[f"{n}\n${v:,.0f}" for n, v in zip(names, values)],
        colors=[colors[k] for k in eco.by_tech],
        autopct="%1.0f%%",
        startangle=90,
        wedgeprops=dict(width=0.55, edgecolor=SURFACE, linewidth=2),
        textprops=dict(color=INK, fontsize=10),
    )
    for at in autotexts:
        at.set_color(INK)
        at.set_fontsize(10)
    ax.set_title(
        f"CAPEX ${eco.capex_total_usd:,.0f} — из чего складывается",
        color=INK, fontsize=11,
    )
    fig.tight_layout()
    fig.savefig("results/capex_pie.png", dpi=150, facecolor=SURFACE)
    print("сохранено: results/capex_pie.png")


def comparison_table(scenario_dict) -> None:
    """(c) Гибрид vs '100% дизель' — таблица в терминал."""
    hybrid = Scenario.model_validate(scenario_dict)
    sim_h = run_simulation(hybrid, weather_csv=WEATHER_CSV, write_outputs=False)
    eco_h = compute_economics(hybrid, sim_h)
    kpi_h = compute_kpi(hybrid, sim_h)

    diesel_dict = json.loads(json.dumps(scenario_dict))
    del diesel_dict["pv"]
    del diesel_dict["battery"]
    diesel = Scenario.model_validate(diesel_dict)
    sim_d = run_simulation(diesel, write_outputs=False)
    eco_d = compute_economics(diesel, sim_d)
    kpi_d = compute_kpi(diesel, sim_d)

    co2_h = kpi_h.dg_kwh * CO2_KG_PER_DIESEL_KWH / 1000  # тонн/год
    co2_d = kpi_d.dg_kwh * CO2_KG_PER_DIESEL_KWH / 1000

    print()
    print(f"{'метрика':28s} {'гибрид (вендор)':>18s} {'100% дизель':>14s}")
    rows = [
        ("LCOE, $/kWh", f"{eco_h.lcoe_usd_per_kwh:.3f}", f"{eco_d.lcoe_usd_per_kwh:.3f}"),
        ("renewable fraction", f"{kpi_h.renewable_fraction:.1%}", f"{kpi_d.renewable_fraction:.1%}"),
        ("топливо, $/год", f"{eco_h.fuel_usd_per_year:,.0f}", f"{eco_d.fuel_usd_per_year:,.0f}"),
        ("CO2 (оценка*), т/год", f"{co2_h:,.0f}", f"{co2_d:,.0f}"),
        ("NPC (10 лет), $", f"{eco_h.npc_usd:,.0f}", f"{eco_d.npc_usd:,.0f}"),
        ("годовые издержки, $", f"{eco_h.annual_cost_usd:,.0f}", f"{eco_d.annual_cost_usd:,.0f}"),
        ("LPSP", f"{kpi_h.lpsp:.1%}", f"{kpi_d.lpsp:.1%}"),
    ]
    for name, h, d in rows:
        print(f"{name:28s} {h:>18s} {d:>14s}")
    print(f"* ASSUMPTION: {CO2_KG_PER_DIESEL_KWH} кг CO2/kWh дизеля "
          "(2.68 кг/л * ~0.27 л/кВт*ч); только эксплуатация")


def main() -> None:
    with open(SCENARIO_PATH, encoding="utf-8") as f:
        scenario_dict = json.load(f)
    scenario = Scenario.model_validate(scenario_dict)

    sim = run_simulation(scenario, weather_csv=WEATHER_CSV, write_outputs=False)
    eco = compute_economics(scenario, sim)

    Path("results").mkdir(exist_ok=True)
    plot_dispatch_week(sim.table)
    plot_dispatch_monthly(sim.table)
    plot_capex_pie(eco)
    comparison_table(scenario_dict)


if __name__ == "__main__":
    main()
