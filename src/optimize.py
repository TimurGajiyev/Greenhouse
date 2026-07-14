"""LP-оптимизатор GreenHouse. Версия v0.7 (шаги 7-8).

Два режима на ОДНОМ LP-ядре (_build_lp_core):

  optimize_dispatch (шаг 7) — размеры оборудования зафиксированы,
      солвер выбирает потоки; цель: топливо + VOLL * недопоставка.

  optimize_sizing (шаг 8, главный ответ калькулятора) — размеры
      pv_kwp / batt_kwh / batt_kw / dg_kw становятся НЕПРЕРЫВНЫМИ
      переменными решения (как dvSize / dvStorageEnergy /
      dvStoragePower в REopt); солвер одновременно выбирает и
      размеры, и режим работы на весь год. Цель:
        min Σ_tech CRF_tech * CAPEX(размер) + O&M(размер)
            + Σ_t Δt * цена_топлива * dg[t]   [+ VOLL * недопоставка]
      CRF-коэффициенты — те же, что в economics.py (шаг 6): по сроку
      жизни технологии. Совместная оптимизация инвестиций и
      диспетчеризации — тот же паттерн, что у REopt, Calliope,
      OSeMOSYS, urbs и PyPSA.

LP (linear program) — минимизация линейной функции при линейных
ограничениях; солвер (HiGHS) даёт доказанный глобальный оптимум.

Почему непрерывные размеры, а не целые панели: непрерывная задача
решается за секунды и гарантирует оптимум; перевод в штуки —
постобработка ceil(размер / юнит) по unit-полям схемы (инвариант 3).

Надёжность — переключаемая политика из scenario.reliability (шаг 8):
  hard — Σ shortfall == 0 (аналог min_load_met_annual_fraction = 1.0
         в off-grid REopt);
  lpsp — Σ shortfall*Δt <= x% * Σ load*Δt;
  voll — штраф в целевой функции (аналог dvUnservedLoad * VOLL).

Ограничение площадки: pv_kwp * m2_per_kwp <= site.roof_area_m2
(аналог land/roof constraint в tech_constraints.jl REopt).

Формулировки ограничений — из REopt.jl:
  баланс 8b (load_balance.jl), русла PV 4e, SOC-динамика 4g
  (storage_constraints.jl), связь потоков с размерами (dispatch <=
  size — tech_constraints.jl / storage_constraints.jl 4i-4n).
"""

import math
import time
import uuid
import warnings
from dataclasses import asdict, dataclass, field

import pandas as pd
import pulp

from src.economics import capital_recovery_factor
from src.schema import Scenario
from src.simulate import (
    SimulationResult,
    TimestepRecord,
    _build_manifest,
    prepare_series,
    write_results,
)

SOURCE_MODEL_DISPATCH = "lp_v1"
SOURCE_MODEL_SIZING = "lp_sizing_v1"

# ASSUMPTION: VOLL по дефолту = $1.00/kWh — дефолт REopt
# (core/financial.jl, value_of_lost_load_per_kwh); уточнить у заказчика
# цену часа простоя завода.
VOLL_DEFAULT_USD_PER_KWH = 1.0

# ASSUMPTION: 1 kWp панелей занимает ~5 м² крыши: панель 0.58 kWp
# имеет площадь ~2.6 м² (4.5 м²/kWp) плюс проходы и отступы. Точное
# значение — из плана раскладки; переопределяется полем pv.m2_per_kwp.
DEFAULT_M2_PER_KWP = 5.0

# Допуск проверки баланса LP-решения (точность солвера ~1e-7
# относительной; на сотнях kW это ~1e-4 kW).
LP_BALANCE_TOL_KW = 1e-4

# Анти-вырожденный микроштраф на каждый kW/kWh размера. Зачем: если
# у технологии нулевой ценник (у вендора PCS = $0/kW — цена внутри
# шкафов), солвер БЕЗРАЗЛИЧЕН к её размеру и может вернуть любое
# допустимое число (хоть верхнюю границу коридора). Штраф в
# миллионную долю доллара экономику не меняет (< $0.01 на всю
# систему), но заставляет выбрать МИНИМАЛЬНО НЕОБХОДИМОЕ железо —
# стандартный приём снятия вырожденности (degeneracy) в LP.
SIZE_TIEBREAK_USD = 1e-6


@dataclass(frozen=True)
class SizingResult:
    """Ответ сайзера: размеры в kW/kWh И в штуках + полный прогон."""

    sizes: dict            # pv_kwp, batt_kwh, batt_kw, dg_kw (float)
    units: dict            # pv_panels, batt_cabinets, batt_pcs_units,
                           # dg_gensets (int | None — юнит не задан)
    sim: SimulationResult = field(repr=False)


def optimize_dispatch(
    scenario: Scenario,
    weather_csv: str | None = None,
    voll_usd_per_kwh: float = VOLL_DEFAULT_USD_PER_KWH,
    results_dir: str = "results",
    write_outputs: bool = True,
    cyclic_soc: bool = False,
    solver: str | None = None,
    lp_snapshot_path: str | None = None,
) -> SimulationResult:
    """Шаг 7: оптимальные потоки при ФИКСИРОВАННЫХ размерах.

    cyclic_soc=False (дефолт): батарея стартует полной, как в rule-
    симуляторе, — иначе сравнение "LP не хуже правила" было бы
    сравнением РАЗНЫХ задач. True — годовое кольцо, как в сайзере.
    solver — "highs"/"cbc"/None (None = HiGHS с откатом на CBC);
    lp_snapshot_path — выгрузить модель в текстовый .lp-файл
    (паттерн эталонных LP-тестов Calliope).
    """
    load, dt_hours, solar_unit = prepare_series(scenario, weather_csv)
    load_arr = load.to_numpy(dtype=float)
    solar_arr = solar_unit.to_numpy(dtype=float)
    n = len(load_arr)

    prob = pulp.LpProblem("greenhouse_dispatch", pulp.LpMinimize)

    # Размеры — константы из сценария (режим проверки: min == max).
    sizes = {
        "pv_kwp": scenario.pv.max_kw if scenario.pv else 0.0,
        "batt_kwh": scenario.battery.max_kwh if scenario.battery else 0.0,
        "batt_kw": scenario.battery.max_kw if scenario.battery else 0.0,
        "dg_kw": scenario.diesel.max_kw if scenario.diesel else 0.0,
    }
    v = _build_lp_core(
        prob, scenario, n, dt_hours, load_arr, solar_arr, sizes,
        cyclic_soc=cyclic_soc,
    )

    fuel_price = scenario.diesel.fuel_cost_usd_per_kwh if scenario.diesel else 0.0
    prob += pulp.lpSum(
        dt_hours * (fuel_price * v["dg"][t] + voll_usd_per_kwh * v["shortfall"][t])
        for t in range(n)
    )

    if lp_snapshot_path is not None:
        prob.writeLP(lp_snapshot_path)

    solver_info = _solve(prob, solver)
    return _extract_result(
        scenario, load, dt_hours, solar_unit, sizes, v,
        source_model=SOURCE_MODEL_DISPATCH,
        solver_info=solver_info,
        results_dir=results_dir,
        write_outputs=write_outputs,
        extra={"cyclic_soc": cyclic_soc},
    )


def optimize_sizing(
    scenario: Scenario,
    weather_csv: str | None = None,
    results_dir: str = "results",
    write_outputs: bool = True,
    cyclic_soc: bool = True,
    solver: str | None = None,
    lp_snapshot_path: str | None = None,
) -> SizingResult:
    """Шаг 8: солвер сам выбирает размеры оборудования.

    Коридор поиска — [min, max] каждой технологии из сценария;
    min == max воспроизводит режим шага 7 (приём REopt: фиксация
    размера сжатием коридора в точку).

    cyclic_soc=True (дефолт, как в Calliope): запас батареи замкнут
    в годовое кольцо — конец года "перетекает" в его начало, и
    система не получает бесплатной стартовой заправки. Честнее для
    сайзинга: размер батареи оплачивает только реально прокачанную
    энергию.
    """
    load, dt_hours, solar_unit = prepare_series(scenario, weather_csv)
    load_arr = load.to_numpy(dtype=float)
    solar_arr = solar_unit.to_numpy(dtype=float)
    n = len(load_arr)
    rate = scenario.financial.discount_rate_fraction

    prob = pulp.LpProblem("greenhouse_sizing", pulp.LpMinimize)

    # --- размеры: переменные решения в коридорах схемы ---
    sizes = {"pv_kwp": 0.0, "batt_kwh": 0.0, "batt_kw": 0.0, "dg_kw": 0.0}
    if scenario.pv is not None:
        sizes["pv_kwp"] = prob.add_variable(
            "size_pv_kwp", lowBound=scenario.pv.min_kw, upBound=scenario.pv.max_kw
        )
    if scenario.battery is not None:
        sizes["batt_kwh"] = prob.add_variable(
            "size_batt_kwh",
            lowBound=scenario.battery.min_kwh,
            upBound=scenario.battery.max_kwh,
        )
        sizes["batt_kw"] = prob.add_variable(
            "size_batt_kw",
            lowBound=scenario.battery.min_kw,
            upBound=scenario.battery.max_kw,
        )
    if scenario.diesel is not None:
        sizes["dg_kw"] = prob.add_variable(
            "size_dg_kw",
            lowBound=scenario.diesel.min_kw,
            upBound=scenario.diesel.max_kw,
        )

    v = _build_lp_core(
        prob, scenario, n, dt_hours, load_arr, solar_arr, sizes,
        cyclic_soc=cyclic_soc,
    )

    # --- целевая функция: годовой эквивалент капитала + O&M + топливо ---
    # CRF по сроку жизни технологии — ровно те же коэффициенты, что
    # считает economics.py для готовой системы (согласованность слоёв).
    objective = []
    if scenario.pv is not None:
        crf_pv = capital_recovery_factor(rate, scenario.pv.lifetime_years)
        objective.append(
            (crf_pv * scenario.pv.capex_usd_per_kw
             + scenario.pv.om_usd_per_kw_year) * sizes["pv_kwp"]
        )
    if scenario.battery is not None:
        b = scenario.battery
        crf_b = capital_recovery_factor(rate, b.lifetime_years)
        objective.append(
            (crf_b * b.capex_usd_per_kwh + b.om_usd_per_kwh_year)
            * sizes["batt_kwh"]
        )
        objective.append(crf_b * b.capex_usd_per_kw * sizes["batt_kw"])
    if scenario.diesel is not None:
        d = scenario.diesel
        crf_d = capital_recovery_factor(rate, d.lifetime_years)
        objective.append(
            (crf_d * d.capex_usd_per_kw + d.om_usd_per_kw_year) * sizes["dg_kw"]
        )
        objective.append(
            pulp.lpSum(
                dt_hours * d.fuel_cost_usd_per_kwh * v["dg"][t] for t in range(n)
            )
        )

    # --- политика надёжности ---
    mode = scenario.reliability.mode
    total_shortfall_kwh = pulp.lpSum(
        dt_hours * v["shortfall"][t] for t in range(n)
    )
    if mode == "hard":
        # Сумма неотрицательных слагаемых == 0 значит каждый == 0.
        prob += total_shortfall_kwh == 0, "reliability_hard"
    elif mode == "lpsp":
        total_load_kwh = float(load_arr.sum() * dt_hours)
        prob += (
            total_shortfall_kwh
            <= scenario.reliability.lpsp_max_fraction * total_load_kwh
        ), "reliability_lpsp"
    else:  # voll
        objective.append(
            scenario.reliability.voll_usd_per_kwh * total_shortfall_kwh
        )

    # Микроштраф от вырожденности — на все размеры разом (см. константу).
    objective.append(
        pulp.lpSum(
            SIZE_TIEBREAK_USD * s
            for s in sizes.values()
            if isinstance(s, pulp.LpVariable)
        )
    )
    prob += pulp.lpSum(objective)

    # --- площадь под панели ---
    if scenario.pv is not None and scenario.site.roof_area_m2 is not None:
        m2_per_kwp = scenario.pv.m2_per_kwp or DEFAULT_M2_PER_KWP
        prob += (
            sizes["pv_kwp"] * m2_per_kwp <= scenario.site.roof_area_m2
        ), "roof_area"

    if lp_snapshot_path is not None:
        prob.writeLP(lp_snapshot_path)

    solver_info = _solve(prob, solver)

    # Переменные размеров -> числа; дальше всё как в dispatch-режиме.
    solved_sizes = {
        k: (s.value() if isinstance(s, pulp.LpVariable) else s)
        for k, s in sizes.items()
    }
    units = _sizes_to_units(scenario, solved_sizes)

    sim = _extract_result(
        scenario, load, dt_hours, solar_unit, solved_sizes, v,
        source_model=SOURCE_MODEL_SIZING,
        solver_info=solver_info,
        results_dir=results_dir,
        write_outputs=write_outputs,
        extra={
            "sizes": {k: round(x, 3) for k, x in solved_sizes.items()},
            "units": units,
            "reliability_mode": mode,
            "cyclic_soc": cyclic_soc,
        },
    )
    return SizingResult(sizes=solved_sizes, units=units, sim=sim)


# ---------- приватные помощники ----------


def _build_lp_core(
    prob: pulp.LpProblem,
    scenario: Scenario,
    n: int,
    dt_hours: float,
    load_arr,
    solar_arr,
    sizes: dict,
    cyclic_soc: bool,
) -> dict:
    """Общие переменные и ограничения обоих режимов.

    sizes — словарь ЛИБО чисел (dispatch), ЛИБО LpVariable (sizing):
    LP-ограничения записываются одинаково, потому что линейное
    выражение не различает константу и переменную. Все лимиты
    "поток <= размер" — ограничениями, а не upBound переменных,
    иначе размер-переменная в границу не встанет.

    cyclic_soc — годовое кольцо запаса (Calliope, cyclic_storage):
    "предыдущий" шаг для t=0 — это ПОСЛЕДНИЙ шаг горизонта, стартовый
    уровень выбирает солвер, и подарить системе бесплатную заправку
    невозможно. False — REopt-стиль off-grid: старт с полной батареей.
    """
    if scenario.battery is not None:
        eta = math.sqrt(scenario.battery.rte_fraction)
        soc_min_frac = scenario.battery.soc_min_fraction
        loss = scenario.battery.self_discharge_fraction_per_hour or 0.0
        # Саморазряд (Calliope, storage_loss): доля запаса, доживающая
        # до конца шага, — (1-loss)^Δt; при loss=0 множитель равен 1.
        decay = (1.0 - loss) ** dt_hours
    else:
        eta = 1.0
        soc_min_frac = 0.0
        decay = 1.0

    charge = prob.add_variable_dicts("charge_kw", range(n), lowBound=0)
    discharge = prob.add_variable_dicts("discharge_kw", range(n), lowBound=0)
    dg = prob.add_variable_dicts("dg_kw", range(n), lowBound=0)
    curtail = prob.add_variable_dicts("curtail_kw", range(n), lowBound=0)
    shortfall = prob.add_variable_dicts("shortfall_kw", range(n), lowBound=0)
    soc = prob.add_variable_dicts("soc_kwh", range(n), lowBound=0)

    # Нецикличный старт — полная батарея (REopt off-grid:
    # soc_init_fraction=1.0); в sizing это 1.0 * batt_kwh_var — линейно.
    soc_init = sizes["batt_kwh"]

    for t in range(n):
        pv_gen_t = sizes["pv_kwp"] * solar_arr[t]

        # Баланс шага (REopt 8b).
        prob += (
            pv_gen_t + discharge[t] + dg[t] + shortfall[t]
            == load_arr[t] + charge[t] + curtail[t]
        ), f"balance_{t}"
        # Русла PV (REopt 4e): заряд и сброс питаются только солнцем.
        prob += charge[t] + curtail[t] <= pv_gen_t, f"pv_split_{t}"
        # Потоки не выше размеров (REopt 4i-4n / tech_constraints).
        prob += charge[t] <= sizes["batt_kw"], f"charge_cap_{t}"
        prob += discharge[t] <= sizes["batt_kw"], f"discharge_cap_{t}"
        prob += dg[t] <= sizes["dg_kw"], f"dg_cap_{t}"
        # Запас в границах ёмкости (пол и потолок зависят от размера).
        prob += soc[t] <= sizes["batt_kwh"], f"soc_max_{t}"
        prob += soc[t] >= soc_min_frac * sizes["batt_kwh"], f"soc_min_{t}"

        # "Предыдущий" запас: кольцо или фиксированный старт.
        if t == 0:
            prev = soc[n - 1] if cyclic_soc else soc_init
        else:
            prev = soc[t - 1]

        # SOC-динамика (REopt 4g + саморазряд Calliope).
        prob += (
            soc[t] == decay * prev + dt_hours * (eta * charge[t] - discharge[t] / eta)
        ), f"soc_dyn_{t}"

        # REopt 4h: один только заряд не должен переполнять ёмкость.
        # Отсекает вырожденное "заряжаю и разряжаю одновременно, чтобы
        # уместиться" без целочисленных переменных.
        prob += (
            sizes["batt_kwh"] >= decay * prev + dt_hours * eta * charge[t]
        ), f"charge_no_overfill_{t}"

    return {
        "charge": charge, "discharge": discharge, "dg": dg,
        "curtail": curtail, "shortfall": shortfall, "soc": soc,
        "eta": eta,
    }


def _solve(prob: pulp.LpProblem, preference: str | None = None) -> dict:
    """Решает LP и возвращает паспорт солвера; не-Optimal — ошибка."""
    solver_name, solver = _pick_solver(preference)
    started = time.perf_counter()
    prob.solve(solver)
    solve_seconds = time.perf_counter() - started

    status = pulp.LpStatus[prob.status]
    if status != "Optimal":
        raise RuntimeError(
            f"LP: солвер {solver_name} вернул статус {status!r} — "
            "результат недействителен (возможно, задача неразрешима: "
            "например, режим hard при слишком тесных коридорах размеров)"
        )
    return {
        "solver": solver_name,
        "solver_status": status,
        "objective_value": float(pulp.value(prob.objective)),
        "solve_seconds": round(solve_seconds, 3),
    }


def _extract_result(
    scenario: Scenario,
    load: pd.Series,
    dt_hours: float,
    solar_unit: pd.Series,
    sizes: dict,
    v: dict,
    source_model: str,
    solver_info: dict,
    results_dir: str,
    write_outputs: bool,
    extra: dict | None = None,
) -> SimulationResult:
    """Решение солвера -> записи той же формы, что у симулятора."""
    load_arr = load.to_numpy(dtype=float)
    run_id = uuid.uuid4().hex[:12]
    records = []
    for t, ts in enumerate(load.index):
        pv_gen_t = sizes["pv_kwp"] * float(solar_unit.iloc[t])
        charge_t = v["charge"][t].value()
        curtail_t = v["curtail"][t].value()
        rec = TimestepRecord(
            run_id=run_id,
            timestamp=ts,
            load_kw=float(load_arr[t]),
            pv_gen_kw=float(pv_gen_t),
            pv_to_load_kw=float(pv_gen_t - charge_t - curtail_t),
            charge_kw=float(charge_t),
            discharge_kw=float(v["discharge"][t].value()),
            dg_kw=float(v["dg"][t].value()),
            curtail_kw=float(curtail_t),
            shortfall_kw=float(v["shortfall"][t].value()),
            soc_kwh=float(v["soc"][t].value()),
            source_model=source_model,
        )
        inflow = rec.pv_gen_kw + rec.discharge_kw + rec.dg_kw + rec.shortfall_kw
        outflow = rec.load_kw + rec.charge_kw + rec.curtail_kw
        assert abs(inflow - outflow) < LP_BALANCE_TOL_KW, (
            f"{ts}: LP-баланс нарушен: {inflow} != {outflow}"
        )
        records.append(rec)

    table = pd.DataFrame([asdict(r) for r in records]).set_index("timestamp")
    manifest = _build_manifest(
        run_id, scenario, load, solar_unit, dt_hours, table,
        source_model=source_model,
        solver_info=solver_info,
        extra=extra,
    )

    parquet_path = manifest_path = None
    if write_outputs:
        parquet_path, manifest_path = write_results(table, manifest, results_dir)

    return SimulationResult(
        table=table,
        manifest=manifest,
        parquet_path=parquet_path,
        manifest_path=manifest_path,
    )


def _sizes_to_units(scenario: Scenario, sizes: dict) -> dict:
    """Непрерывные размеры -> целые штуки: ceil(размер / юнит).

    None = unit-поле в сценарии не задано (перевод не запрошен).
    Микродопуск 1e-6 спасает от 12.0000001 -> 13 шкафов из-за
    плавающей точки солвера.
    """

    def units_for(size: float, unit: float | None) -> int | None:
        if unit is None:
            return None
        if size <= 0:
            return 0
        return math.ceil(size / unit - 1e-6)

    return {
        "pv_panels": units_for(
            sizes["pv_kwp"], scenario.pv.unit_kw if scenario.pv else None
        ),
        "batt_cabinets": units_for(
            sizes["batt_kwh"], scenario.battery.unit_kwh if scenario.battery else None
        ),
        "batt_pcs_units": units_for(
            sizes["batt_kw"], scenario.battery.unit_kw if scenario.battery else None
        ),
        "dg_gensets": units_for(
            sizes["dg_kw"], scenario.diesel.unit_kw if scenario.diesel else None
        ),
    }


def _pick_solver(preference: str | None = None):
    """Выбор солвера.

    preference: "highs" / "cbc" — взять именно этот (для кросс-
    солверной сверки: два НЕЗАВИСИМЫХ солвера обязаны дать один
    оптимум); None — HiGHS, а если недоступен, честный откат на CBC.
    """
    if preference is not None:
        name = preference.lower()
        if name == "highs":
            return "HiGHS", pulp.HiGHS(msg=False)
        if name == "cbc":
            return "CBC", pulp.PULP_CBC_CMD(msg=False)
        raise ValueError(f"Неизвестный солвер {preference!r}: жду 'highs' или 'cbc'")

    try:
        solver = pulp.HiGHS(msg=False)
        if solver.available():
            return "HiGHS", solver
    except Exception:
        pass
    warnings.warn("HiGHS недоступен — решаю запасным CBC (медленнее)")
    return "CBC", pulp.PULP_CBC_CMD(msg=False)
