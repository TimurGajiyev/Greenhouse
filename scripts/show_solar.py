"""Просмотрщик солнечного профиля (шаг 4).

Запуск из корня проекта (с активированным .venv):
    python scripts/show_solar.py

Что делает: строит профиль для scenarios/yemen_vendor.json на
кэшированной погоде, печатает сводку в терминал и сохраняет картинку
results/solar_profile.png с двумя графиками:
  слева  — ход выработки в три характерных дня (лучший/типичный/худший);
  справа — энергия по месяцам.

Это утилита "посмотреть глазами", НЕ часть ядра: ядро (src/) не знает
о её существовании, удаление scripts/ ничего не сломает.
"""

import json
import sys
from pathlib import Path

import matplotlib

# Backend "Agg" — рисование в файл без открытия окна: скрипт работает
# и по SSH, и в терминале без графической подсистемы.
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# Скрипт лежит в scripts/, а импортирует из src/ — добавляем корень
# проекта в пути поиска модулей (как это делает conftest.py для pytest).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.schema import Scenario
from src.solar import build_solar_profile

SCENARIO_PATH = "scenarios/yemen_vendor.json"
WEATHER_CSV = "tests/data/tmy_sanaa_pvgis_sarah3.csv"
OUT_PNG = "results/solar_profile.png"

# Цвета — из валидированной палитры (категориальные слоты 1-3 и чернила).
BLUE = "#2a78d6"     # слот 1 — лучший день
YELLOW = "#eda100"   # слот 3 — типичный день (аква оставлена месяцам)
AQUA = "#1baf7a"     # слот 2 — не используется в линиях, месячные бары
INK = "#0b0b0b"      # основной текст
MUTED = "#898781"    # подписи осей
GRID = "#e1e0d9"     # сетка-волосок
SURFACE = "#fcfcfb"  # фон


def main() -> None:
    # 1) Сценарий и профиль — ровно тот же путь, что в тестах.
    with open(SCENARIO_PATH, encoding="utf-8") as f:
        scenario = Scenario.model_validate(json.load(f))
    solar = build_solar_profile(scenario, weather_csv=WEATHER_CSV)

    # 2) Сводка в терминал.
    daily = solar.resample("D").sum()  # kWh на 1 kWp за каждые сутки
    monthly = solar.resample("MS").sum()  # и за каждый месяц
    pv_kwp = scenario.pv.max_kw if scenario.pv else 0.0

    print(f"Сценарий: {scenario.name}")
    print(f"Годовая удельная выработка: {solar.sum():,.1f} kWh/kWp")
    print(f"Средние сутки: {daily.mean():.2f} kWh/kWp "
          f"(= {daily.mean() * pv_kwp:,.0f} kWh при {pv_kwp:,.0f} kWp)")
    print(f"Лучший день:  {daily.max():.2f} kWh/kWp ({daily.idxmax().date()})")
    print(f"Худший день:  {daily.min():.2f} kWh/kWp ({daily.idxmin().date()})"
          " — артефакт данных PVGIS, оставлен намеренно")
    print(f"Пик мощности: {solar.max():.3f} kW/kWp")

    # 3) Картинка: два графика на одном полотне.
    fig, (ax_days, ax_months) = plt.subplots(
        1, 2, figsize=(12, 4.5), facecolor=SURFACE
    )

    # --- слева: три характерных дня ---
    best = daily.idxmax().date()
    # "Типичный" = день, чья выработка ближе всех к среднегодовой.
    typical = (daily - daily.mean()).abs().idxmin().date()
    days = [
        (str(best), f"лучший ({best:%d.%m})", BLUE),
        (str(typical), f"типичный ({typical:%d.%m})", YELLOW),
    ]
    for date_str, label, color in days:
        day = solar[date_str]
        ax_days.plot(day.index.hour, day.values, color=color, linewidth=2,
                     label=label)
        # Прямая подпись у пика линии — вместо чтения легенды глазами.
        peak_hour = int(day.values.argmax())
        ax_days.annotate(label, (peak_hour, day.max()),
                         textcoords="offset points", xytext=(6, 6),
                         fontsize=9, color=INK)
    ax_days.set_title("Выработка в характерные сутки", color=INK, fontsize=11)
    ax_days.set_xlabel("час местного времени (Asia/Aden)", color=MUTED)
    ax_days.set_ylabel("kW на 1 kWp", color=MUTED)
    ax_days.set_xticks(range(0, 25, 4))

    # --- справа: энергия по месяцам ---
    ax_months.bar(range(1, 13), monthly.values, width=0.62, color=AQUA)
    ax_months.set_title("Энергия по месяцам", color=INK, fontsize=11)
    ax_months.set_xlabel("месяц", color=MUTED)
    ax_months.set_ylabel("kWh на 1 kWp", color=MUTED)
    ax_months.set_xticks(range(1, 13))

    # Общий стиль: тонкая сетка, без лишних рамок (recessive chrome).
    for ax in (ax_days, ax_months):
        ax.set_facecolor(SURFACE)
        ax.grid(axis="y", color=GRID, linewidth=0.8)
        ax.set_axisbelow(True)  # сетка ПОД данными, а не поверх
        for spine in ("top", "right"):
            ax.spines[spine].set_visible(False)
        for spine in ("left", "bottom"):
            ax.spines[spine].set_color(GRID)
        ax.tick_params(colors=MUTED)

    fig.tight_layout()
    Path("results").mkdir(exist_ok=True)
    fig.savefig(OUT_PNG, dpi=150, facecolor=SURFACE)
    print(f"\nКартинка сохранена: {OUT_PNG}")


if __name__ == "__main__":  # запуск как скрипта, не при импорте
    main()
