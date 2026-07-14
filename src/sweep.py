"""Sensitivity-анализ GreenHouse. Версия v0.8 (шаг 9).

Идея: ядро — чистая функция scenario -> результат (инвариант 7),
поэтому анализ чувствительности — это просто цикл "мутируем один
параметр -> перерешиваем сайзер -> собираем строку таблицы".
Тот же паттерн simulate -> optimize -> sensitivity, что у HOMER.

Четыре исследования (из дорожной карты):
  1. Цена дизельного kWh +-50%      — как плывут размеры и издержки;
  2. CAPEX батареи +-30%            — то же;
     (бонусом PV CAPEX +-30% — тот же механизм, третья строка tornado)
  3. Pareto "стоимость vs надёжность": свип целевого LPSP; поиск
     "колена" (knee) — точки, после которой каждая девятка надёжности
     дорожает непропорционально;
  4. Стрессы ВЫБРАННОГО дизайна (размеры фиксированы, rule-симулятор):
     песчаная буря (облучённость = 0 на N суток — правим погодный файл)
     и топливный разрыв (дизель = 0 на M суток — окно отказа).

Каждый прогон сайзера пишет свой manifest (это делает optimize_sizing);
сводные таблицы уходят в Parquet + summary.json со ссылками на прогоны.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from src.optimize import optimize_sizing
from src.schema import Scenario
from src.simulate import run_simulation

# Сетки свипов (множители к базовому значению параметра).
FUEL_PRICE_FACTORS = (0.5, 0.75, 1.0, 1.25, 1.5)
BESS_CAPEX_FACTORS = (0.7, 0.85, 1.0, 1.15, 1.3)
PV_CAPEX_FACTORS = (0.7, 0.85, 1.0, 1.15, 1.3)

# Целевые LPSP Pareto-фронта; 0.0 означает режим hard.
PARETO_LPSP_TARGETS = (0.0, 0.002, 0.005, 0.01, 0.02, 0.05, 0.10)

# Стрессы: песчаная буря 3 суток, топливный разрыв 7 суток.
# ASSUMPTION: длительности из рисков CLAUDE.md ("несколько суток" бури,
# резерв топлива ~ неделя); даты — облачный сезон (июль), худший случай.
SANDSTORM_DAYS = ("2026-07-10", "2026-07-12")
FUEL_GAP_DAYS = ("2026-07-10", "2026-07-16")


@dataclass(frozen=True)
class SweepReport:
    """Итог шага 9: четыре таблицы + найденное колено Pareto."""

    fuel_price: pd.DataFrame = field(repr=False)
    bess_capex: pd.DataFrame = field(repr=False)
    pv_capex: pd.DataFrame = field(repr=False)
    pareto: pd.DataFrame = field(repr=False)
    knee: dict                      # {"lpsp": ..., "annual_cost_usd": ...}
    stress: pd.DataFrame = field(repr=False)
    summary_path: Path | None


def run_sensitivity(
    scenario: Scenario,
    weather_csv: str | None = None,
    results_dir: str = "results/sweeps",
    write_outputs: bool = True,
) -> SweepReport:
    """Полный sensitivity-пакет для сценария сайзинга (шаг 9)."""
    out = Path(results_dir)
    # Каждый прогон свипа пишет свой manifest + Parquet в подпапку
    # runs/ (требование шага 9: прогон без паспорта не существует).
    runs_dir = str(out / "runs") if write_outputs else None
    if write_outputs:
        out.mkdir(parents=True, exist_ok=True)

    # --- 1-2. Однофакторные свипы цен ---
    fuel_df = _price_sweep(
        scenario, weather_csv, ["diesel", "fuel_cost_usd_per_kwh"],
        FUEL_PRICE_FACTORS, runs_dir,
    )
    bess_df = _price_sweep(
        scenario, weather_csv, ["battery", "capex_usd_per_kwh"],
        BESS_CAPEX_FACTORS, runs_dir,
    )
    pv_df = _price_sweep(
        scenario, weather_csv, ["pv", "capex_usd_per_kw"],
        PV_CAPEX_FACTORS, runs_dir,
    )

    # --- 3. Pareto: стоимость vs надёжность ---
    pareto_df = _pareto_sweep(scenario, weather_csv, runs_dir)
    knee = _find_knee(
        pareto_df["lpsp_target"].to_numpy(),
        pareto_df["annual_cost_usd"].to_numpy(),
    )

    # --- 4. Стрессы оптимального дизайна ---
    stress_df = _stress_tests(scenario, weather_csv, out if write_outputs else None)

    summary_path = None
    if write_outputs:
        for name, df in (
            ("fuel_price", fuel_df), ("bess_capex", bess_df),
            ("pv_capex", pv_df), ("pareto", pareto_df), ("stress", stress_df),
        ):
            df.to_parquet(out / f"sweep_{name}.parquet")
        summary_path = out / "summary.json"
        summary_path.write_text(
            json.dumps(
                {
                    "scenario": scenario.name,
                    "knee": knee,
                    "tables": [f"sweep_{n}.parquet" for n in
                               ("fuel_price", "bess_capex", "pv_capex",
                                "pareto", "stress")],
                },
                indent=2, ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    return SweepReport(
        fuel_price=fuel_df, bess_capex=bess_df, pv_capex=pv_df,
        pareto=pareto_df, knee=knee, stress=stress_df,
        summary_path=summary_path,
    )


# ---------- приватные помощники ----------


def _mutate(scenario: Scenario, path: list[str], factor: float) -> Scenario:
    """Копия сценария с параметром path, умноженным на factor.

    Мутируем копию словаря и заново валидируем: любое изменение
    проходит через те же pydantic-ворота, что и входной JSON.
    """
    data = scenario.model_dump(mode="json")
    node = data
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = node[path[-1]] * factor
    return Scenario.model_validate(data)


def _collect_row(label, value, result) -> dict:
    """Одна строка сводной таблицы из результата сайзера."""
    m = result.sim.manifest
    return {
        "label": label,
        "value": value,
        "pv_kwp": result.sizes["pv_kwp"],
        "batt_kwh": result.sizes["batt_kwh"],
        "batt_kw": result.sizes["batt_kw"],
        "dg_kw": result.sizes["dg_kw"],
        "annual_cost_usd": m["objective_value"],
        "dg_kwh": m["totals_kwh"]["dg"],
        "lpsp": m["lpsp"],
        "run_id": m["run_id"],
    }


def _price_sweep(
    scenario, weather_csv, path, factors, runs_dir: str | None = None
) -> pd.DataFrame:
    """Однофакторный свип: параметр по пути path умножается на factor.

    Если технологии нет в сценарии — пустая таблица (свип не о чем).
    runs_dir — куда писать manifest/Parquet каждого прогона (None = не писать).
    """
    if getattr(scenario, path[0]) is None:
        return pd.DataFrame(
            columns=["label", "value", "pv_kwp", "batt_kwh", "batt_kw",
                     "dg_kw", "annual_cost_usd", "dg_kwh", "lpsp", "run_id"]
        )
    rows = []
    for f in factors:
        mutated = _mutate(scenario, path, f)
        res = optimize_sizing(
            mutated, weather_csv=weather_csv,
            results_dir=runs_dir or "results",
            write_outputs=runs_dir is not None,
        )
        rows.append(_collect_row(".".join(path), f, res))
    return pd.DataFrame(rows)


def _pareto_sweep(scenario, weather_csv, runs_dir: str | None = None) -> pd.DataFrame:
    """Фронт "стоимость vs надёжность": свип целевого LPSP."""
    rows = []
    for target in PARETO_LPSP_TARGETS:
        data = scenario.model_dump(mode="json")
        if target == 0.0:
            data["reliability"] = {"mode": "hard"}
        else:
            data["reliability"] = {"mode": "lpsp", "lpsp_max_fraction": target}
        mutated = Scenario.model_validate(data)
        res = optimize_sizing(
            mutated, weather_csv=weather_csv,
            results_dir=runs_dir or "results",
            write_outputs=runs_dir is not None,
        )
        row = _collect_row("lpsp_target", target, res)
        row["lpsp_target"] = target
        rows.append(row)
    return pd.DataFrame(rows)


def _find_knee(x: np.ndarray, y: np.ndarray) -> dict:
    """Колено кривой: точка максимального удаления от хорды.

    Метод: нормируем обе оси в [0, 1], проводим отрезок (хорду) от
    первой точки фронта до последней и ищем точку с максимальным
    перпендикулярным расстоянием до неё — там кривая "ломается".
    (Тот же принцип, что в алгоритме kneedle.)
    """
    if len(x) < 3:
        raise ValueError("Колено ищется минимум по трём точкам")
    # Нормировка: иначе ось долларов задавит ось долей LPSP.
    xn = (x - x.min()) / (x.max() - x.min())
    yn = (y - y.min()) / (y.max() - y.min())
    # Расстояние точки до прямой через первую и последнюю точки:
    # |cross product| / длину хорды (константу можно не делить).
    dx, dy = xn[-1] - xn[0], yn[-1] - yn[0]
    dist = np.abs(dx * (yn[0] - yn) - (xn[0] - xn) * dy)
    idx = int(dist.argmax())
    return {"lpsp": float(x[idx]), "annual_cost_usd": float(y[idx]), "index": idx}


def _stress_tests(scenario, weather_csv, out_dir) -> pd.DataFrame:
    """Стрессы ЗАФИКСИРОВАННОГО оптимального дизайна.

    Смысл: сайзер выбирает размеры под типичный год; стресс отвечает
    "а что если год не типичный". Размеры фиксируются (min = max),
    прогоняется rule-симулятор (реалистичный, без предвидения).
    """
    # Прогоны стрессов тоже получают манифесты (если пишем на диск).
    write = out_dir is not None
    runs_dir = str(out_dir / "runs") if write else "results"

    # 1) Базовый оптимум и его фиксация.
    base = optimize_sizing(
        scenario, weather_csv=weather_csv,
        results_dir=runs_dir, write_outputs=write,
    )
    fixed = _freeze_sizes(scenario, base.sizes)

    rows = []

    # Базовая линия стресс-таблицы: тот же дизайн в типичном году.
    normal = run_simulation(
        fixed, weather_csv=weather_csv,
        results_dir=runs_dir, write_outputs=write,
    )
    rows.append(_stress_row("typical_year", normal))

    # 2) Песчаная буря: правим КОПИЮ погодного файла (облучённость -> 0),
    #    сами данные не имитируем — честно моделируем "солнца нет".
    if scenario.pv is not None and weather_csv is not None:
        storm_csv = _make_sandstorm_weather(
            weather_csv, out_dir, SANDSTORM_DAYS
        )
        storm = run_simulation(
            fixed, weather_csv=storm_csv,
            results_dir=runs_dir, write_outputs=write,
        )
        rows.append(_stress_row(f"sandstorm_{SANDSTORM_DAYS[0]}_{SANDSTORM_DAYS[1]}", storm))

    # 3) Топливный разрыв: дизель недоступен неделю.
    fuel_gap = run_simulation(
        fixed, weather_csv=weather_csv,
        results_dir=runs_dir, write_outputs=write,
        dg_outage=FUEL_GAP_DAYS,
    )
    rows.append(_stress_row(f"fuel_gap_{FUEL_GAP_DAYS[0]}_{FUEL_GAP_DAYS[1]}", fuel_gap))

    return pd.DataFrame(rows)


def _freeze_sizes(scenario: Scenario, sizes: dict) -> Scenario:
    """Сценарий с коридорами, сжатыми в точку оптимума (min = max)."""
    data = scenario.model_dump(mode="json")
    if data.get("pv"):
        data["pv"]["min_kw"] = data["pv"]["max_kw"] = max(sizes["pv_kwp"], 0.001)
    if data.get("battery"):
        data["battery"]["min_kwh"] = data["battery"]["max_kwh"] = max(
            sizes["batt_kwh"], 0.001
        )
        data["battery"]["min_kw"] = data["battery"]["max_kw"] = max(
            sizes["batt_kw"], 0.001
        )
    if data.get("diesel"):
        data["diesel"]["min_kw"] = data["diesel"]["max_kw"] = max(
            sizes["dg_kw"], 0.001
        )
    return Scenario.model_validate(data)


def _stress_row(label: str, sim_result) -> dict:
    m = sim_result.manifest
    return {
        "stress": label,
        "lpsp": m["lpsp"],
        "shortfall_kwh": m["totals_kwh"]["shortfall"],
        "dg_kwh": m["totals_kwh"]["dg"],
        "run_id": m["run_id"],
    }


def _make_sandstorm_weather(
    weather_csv: str, out_dir: Path | None, days: tuple[str, str]
) -> str:
    """Копия погодного файла с нулевой облучённостью в окне бури.

    Температуру и ветер не трогаем: буря гасит солнце, а не жару.
    """
    df = pd.read_csv(weather_csv, index_col="time_utc", parse_dates=True)
    df.loc[days[0]:days[1], ["ghi", "dni", "dhi"]] = 0.0

    target_dir = out_dir if out_dir is not None else Path("results/sweeps")
    target_dir.mkdir(parents=True, exist_ok=True)
    out_path = target_dir / f"weather_sandstorm_{days[0]}_{days[1]}.csv"
    df.to_csv(out_path)
    return str(out_path)
