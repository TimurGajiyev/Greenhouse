"""Sensitivity-дашборд GreenHouse (шаг 9).

Запуск из корня проекта (с активированным .venv):
    python scripts/show_sweeps.py

Гоняет полный sensitivity-пакет для scenarios/yemen_sizing.json
(~2 минуты: два десятка LP-задач по 8760 часов) и сохраняет:
  results/tornado.png — какой параметр сильнее всего качает издержки;
  results/pareto.png  — фронт "стоимость vs надёжность" с коленом;
+ печатает стресс-таблицу и вывод про колено.
"""

import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.schema import Scenario
from src.sweep import run_sensitivity

SCENARIO_PATH = "scenarios/yemen_sizing.json"
WEATHER_CSV = "tests/data/tmy_sanaa_pvgis_sarah3.csv"

# Палитра (те же роли, что в show_results.py).
BLUE = "#2a78d6"
BLUE_LIGHT = "#9ec5f4"
RED = "#e34948"
INK = "#0b0b0b"
MUTED = "#898781"
GRID = "#e1e0d9"
SURFACE = "#fcfcfb"


def style_axis(ax):
    ax.set_facecolor(SURFACE)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    for spine in ("left", "bottom"):
        ax.spines[spine].set_color(GRID)
    ax.tick_params(colors=MUTED)


def plot_tornado(report) -> None:
    """Tornado: для каждого параметра — размах годовых издержек
    между его минимальным и максимальным значением из свипа.
    Читается сверху вниз: чем длиннее полоса, тем чувствительнее
    результат к параметру."""
    base = float(
        report.fuel_price.loc[report.fuel_price.value == 1.0, "annual_cost_usd"].iloc[0]
    )
    factors = [
        ("Цена дизеля ±50%", report.fuel_price),
        ("CAPEX BESS ±30%", report.bess_capex),
        ("CAPEX PV ±30%", report.pv_capex),
    ]
    # Сортировка по размаху — форма "торнадо".
    rows = []
    for name, df in factors:
        lo, hi = df.annual_cost_usd.min(), df.annual_cost_usd.max()
        rows.append((name, lo, hi))
    rows.sort(key=lambda r: r[2] - r[1], reverse=True)

    fig, ax = plt.subplots(figsize=(9, 3.8), facecolor=SURFACE)
    y = range(len(rows))
    for i, (name, lo, hi) in enumerate(rows):
        # Светлая часть — от низкой цены до базы, тёмная — от базы вверх.
        ax.barh(i, base - lo, left=lo, height=0.5, color=BLUE_LIGHT)
        ax.barh(i, hi - base, left=base, height=0.5, color=BLUE)
        ax.annotate(f"${lo:,.0f}", (lo, i), textcoords="offset points",
                    xytext=(-6, 0), ha="right", va="center",
                    fontsize=9, color=INK)
        ax.annotate(f"${hi:,.0f}", (hi, i), textcoords="offset points",
                    xytext=(6, 0), ha="left", va="center",
                    fontsize=9, color=INK)
    ax.axvline(base, color=INK, linewidth=1.2, linestyle="--")
    ax.annotate(f"база ${base:,.0f}", (base, len(rows) - 0.4),
                textcoords="offset points", xytext=(6, 6),
                fontsize=9, color=INK)
    ax.set_yticks(list(y))
    ax.set_yticklabels([r[0] for r in rows], fontsize=10, color=INK)
    ax.invert_yaxis()
    ax.set_xlabel("годовые издержки оптимума, $/год", color=MUTED)
    ax.set_title("Tornado: чувствительность оптимума к ценам",
                 color=INK, fontsize=11)
    # Запас по краям, чтобы подписи не резались.
    lo_all = min(r[1] for r in rows)
    hi_all = max(r[2] for r in rows)
    span = hi_all - lo_all
    ax.set_xlim(lo_all - 0.18 * span, hi_all + 0.18 * span)
    style_axis(ax)
    fig.tight_layout()
    fig.savefig("results/tornado.png", dpi=150, facecolor=SURFACE)
    print("сохранено: results/tornado.png")


def plot_pareto(report) -> None:
    """Фронт "стоимость vs надёжность" + колено."""
    df = report.pareto.sort_values("lpsp_target")
    x = df.lpsp_target * 100  # в проценты для читаемости
    y = df.annual_cost_usd

    fig, ax = plt.subplots(figsize=(9, 4.2), facecolor=SURFACE)
    ax.plot(x, y, color=BLUE, linewidth=2, marker="o", markersize=6)

    knee = report.knee
    ax.plot(knee["lpsp"] * 100, knee["annual_cost_usd"], "o",
            markersize=12, markerfacecolor="none",
            markeredgecolor=RED, markeredgewidth=2)
    ax.annotate(
        f"колено: LPSP {knee['lpsp']:.1%}\n${knee['annual_cost_usd']:,.0f}/год",
        (knee["lpsp"] * 100, knee["annual_cost_usd"]),
        textcoords="offset points", xytext=(14, 10),
        fontsize=9, color=INK,
    )
    ax.set_xlabel("допустимая недопоставка (LPSP), % годовой нагрузки",
                  color=MUTED)
    ax.set_ylabel("годовые издержки, $/год", color=MUTED)
    ax.set_title("Pareto: сколько стоит надёжность", color=INK, fontsize=11)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    style_axis(ax)
    fig.tight_layout()
    fig.savefig("results/pareto.png", dpi=150, facecolor=SURFACE)
    print("сохранено: results/pareto.png")


def main() -> None:
    with open(SCENARIO_PATH, encoding="utf-8") as f:
        scenario = Scenario.model_validate(json.load(f))

    print("Гоняю sensitivity-пакет (~2 минуты)...")
    report = run_sensitivity(scenario, weather_csv=WEATHER_CSV)

    Path("results").mkdir(exist_ok=True)
    plot_tornado(report)
    plot_pareto(report)

    print()
    print("=== Pareto-фронт ===")
    cols = ["lpsp_target", "annual_cost_usd", "pv_kwp", "batt_kwh", "dg_kw"]
    df_show = report.pareto[cols].copy(); df_show["lpsp_target"] = (df_show["lpsp_target"] * 100).map("{:.1f}%".format); print(df_show.round(1).to_string(index=False))
    print(f"колено: LPSP {report.knee['lpsp']:.2%} за "
          f"${report.knee['annual_cost_usd']:,.0f}/год")
    print()
    print("=== Стрессы оптимального дизайна (rule-симулятор) ===")
    print(report.stress.round(4).to_string(index=False))
    print()
    print(f"сводные таблицы: {report.summary_path.parent}")


if __name__ == "__main__":
    main()
