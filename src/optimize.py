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

from src.economics import capital_recovery_factor, fuel_levelization_factor
from src.profiles import HOURS_PER_YEAR
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
SOURCE_MODEL_MILP = "milp_sizing_v1"

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

# ASSUMPTION: операционные выбросы дизель-генерации ~0.72 кг CO2/kWh
# (2.68 кг/л * ~0.27 л/кВт*ч) — дефолт для цены углерода, когда сценарий
# не задал diesel.co2_kg_per_kwh. Та же цифра, что в KPI-слое приложения.
DIESEL_CO2_KG_PER_KWH_DEFAULT = 0.72

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

    # Оперативный резерв: свободная мощность дизеля = весь размер минус
    # текущая выработка (в dispatch размер — константа).
    dg_headroom = [sizes["dg_kw"] - v["dg"][t] for t in range(n)]
    _add_operating_reserve(
        prob, scenario, n, dt_hours, load_arr, solar_arr, sizes, v, dg_headroom
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
    cost_cap: float | None = None,
    spore_scores: dict | None = None,
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

    Режим SPORES (аудит №3; spores.yaml Calliope): spore_scores +
    cost_cap переключают целевую на поиск ОТЛИЧАЮЩЕЙСЯ конфигурации —
    минимизируется Σ score_i * size_i при ограничении «годовые издержки
    не выше cost_cap». Издержки найденного спора кладутся в manifest
    (extra["spores"]["cost_value"]).
    """
    load, dt_hours, solar_unit = prepare_series(scenario, weather_csv)
    load_arr = load.to_numpy(dtype=float)
    solar_arr = solar_unit.to_numpy(dtype=float)
    n = len(load_arr)
    rate = scenario.financial.discount_rate_fraction

    # Масштаб на долю года (аудит №3; калька annualisation_weight из
    # Calliope base.yaml:1199). Капитал и годовой O&M — величины «за
    # ГОД», топливо — за ГОРИЗОНТ ряда: без веса укороченный ряд платил
    # бы полный годовой капитал против топлива за пару часов, и оптимум
    # молча съезжал в сторону топлива. На полном годе вес = 1 —
    # поведение прежнее.
    year_fraction = n * dt_hours / HOURS_PER_YEAR

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

    # Оперативный резерв (свободная мощность дизеля = размер-переменная
    # минус выработка). Требование резерва тянет размеры дизеля/батареи
    # вверх ровно настолько, чтобы держать горячий запас каждый час.
    dg_headroom = [sizes["dg_kw"] - v["dg"][t] for t in range(n)]
    _add_operating_reserve(
        prob, scenario, n, dt_hours, load_arr, solar_arr, sizes, v, dg_headroom
    )

    # --- целевая функция: годовой эквивалент капитала + O&M + топливо ---
    # CRF по сроку жизни технологии — ровно те же коэффициенты, что
    # считает economics.py для готовой системы (согласованность слоёв).
    # Капитальные слагаемые × year_fraction (см. выше).
    objective = []
    if scenario.pv is not None:
        crf_pv = capital_recovery_factor(rate, scenario.pv.lifetime_years)
        objective.append(
            (crf_pv * scenario.pv.capex_usd_per_kw
             + scenario.pv.om_usd_per_kw_year)
            * year_fraction * sizes["pv_kwp"]
        )
    if scenario.battery is not None:
        b = scenario.battery
        crf_b = capital_recovery_factor(rate, b.lifetime_years)
        objective.append(
            (crf_b * b.capex_usd_per_kwh + b.om_usd_per_kwh_year)
            * year_fraction * sizes["batt_kwh"]
        )
        objective.append(
            crf_b * b.capex_usd_per_kw * year_fraction * sizes["batt_kw"])
    if scenario.diesel is not None:
        d = scenario.diesel
        crf_d = capital_recovery_factor(rate, d.lifetime_years)
        objective.append(
            (crf_d * d.capex_usd_per_kw + d.om_usd_per_kw_year)
            * year_fraction * sizes["dg_kw"]
        )
        # Цена топлива — левелизованная (изъян №6): эскалация свёрнута
        # в один коэффициент, LP остаётся линейным (паттерн pwf_fuel REopt).
        lf = fuel_levelization_factor(
            rate, d.fuel_escalation_fraction, scenario.financial.project_years)
        objective.append(
            pulp.lpSum(
                dt_hours * d.fuel_cost_usd_per_kwh * lf * v["dg"][t]
                for t in range(n)
            )
        )
        # Цена углерода (аудит №3): CO₂ из post-hoc поднят в целевую —
        # аналог Lifecycle_Emissions_Cost_CO2 REopt / cost-класса Calliope.
        if scenario.financial.co2_price_usd_per_ton:
            kg = d.co2_kg_per_kwh or DIESEL_CO2_KG_PER_KWH_DEFAULT
            objective.append(
                pulp.lpSum(
                    dt_hours * (scenario.financial.co2_price_usd_per_ton
                                / 1000.0) * kg * v["dg"][t]
                    for t in range(n)
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
    tiebreak = pulp.lpSum(
        SIZE_TIEBREAK_USD * s
        for s in sizes.values()
        if isinstance(s, pulp.LpVariable)
    )
    cost_expr = pulp.lpSum(objective)
    if spore_scores is None:
        prob += cost_expr + tiebreak
    else:
        # SPORES: издержки — в ограничение, целевая — скоринг «не повторяй
        # прежние конфигурации» (spores.yaml Calliope).
        if cost_cap is None:
            raise ValueError("SPORES: spore_scores требует cost_cap")
        prob += cost_expr <= cost_cap, "spores_cost_cap"
        prob += pulp.lpSum(
            spore_scores.get(k, 0.0) * s
            for k, s in sizes.items()
            if isinstance(s, pulp.LpVariable)
        ) + tiebreak

    # --- площадь под панели ---
    if scenario.pv is not None and scenario.site.roof_area_m2 is not None:
        m2_per_kwp = scenario.pv.m2_per_kwp or DEFAULT_M2_PER_KWP
        prob += (
            sizes["pv_kwp"] * m2_per_kwp <= scenario.site.roof_area_m2
        ), "roof_area"

    # --- связь мощность/ёмкость батареи (C-rate; аудит №3) ---
    # Аналог flow_cap_per_storage_cap_min/max Calliope: без связи солвер
    # может выбрать абсурдную пару (огромный PCS при крошечных ячейках).
    _add_c_rate(prob, scenario, sizes)

    if lp_snapshot_path is not None:
        prob.writeLP(lp_snapshot_path)

    solver_info = _solve(prob, solver)

    # Переменные размеров -> числа; дальше всё как в dispatch-режиме.
    solved_sizes = {
        k: (s.value() if isinstance(s, pulp.LpVariable) else s)
        for k, s in sizes.items()
    }
    units = _sizes_to_units(scenario, solved_sizes)

    extra = {
        "sizes": {k: round(x, 3) for k, x in solved_sizes.items()},
        "units": units,
        "reliability_mode": mode,
        "cyclic_soc": cyclic_soc,
    }
    if spore_scores is not None:
        # Издержки спора (его objective_value — скоринг, не деньги).
        extra["spores"] = {
            "cost_value": float(pulp.value(cost_expr)),
            "cost_cap": cost_cap,
        }

    sim = _extract_result(
        scenario, load, dt_hours, solar_unit, solved_sizes, v,
        source_model=SOURCE_MODEL_SIZING,
        solver_info=solver_info,
        results_dir=results_dir,
        write_outputs=write_outputs,
        extra=extra,
    )
    return SizingResult(sizes=solved_sizes, units=units, sim=sim)


def optimize_sizing_milp(
    scenario: Scenario,
    weather_csv: str | None = None,
    results_dir: str = "results",
    write_outputs: bool = True,
    cyclic_soc: bool = True,
    solver: str | None = None,
    time_limit: float | None = 120.0,
    gap: float | None = 0.01,
    lp_snapshot_path: str | None = None,
) -> SizingResult:
    """Шаг A: MILP-сайзинг парка — целые машины + честная физика дизеля.

    Три улучшения группы A в одной формулировке (паттерн Calliope
    units/operating_units + REopt binGenIsOnInTS):

      A2 — целочисленный сайзинг: размеры не непрерывны, а КРАТНЫ юниту
           (dg_kw = dg_units * unit_kw, аналогично PV-панели, шкафы,
           PCS). Экономика считается по реально закупаемому железу.
      A1 — топливо с холостым ходом: расход = наклон*выработка +
           intercept*работающие_юниты (REopt fuel_slope+intercept).
      A3 — стадирование парка: dg_op[t] (целое, ≤ установленных юнитов)
           — «сколько генсетов молотит в этот час»; включённый юнит
           обязан выдавать ≥ min_turn_down доли номинала.

    Расплата за целочисленность — ветвление (branch-and-bound): солвер
    медленнее LP. Параметры time_limit (сек) и gap (относительный зазор
    оптимальности, 0.01 = 1%) держат время под контролем; для тесных
    годовых задач добавь редукцию ряда (типовые сутки) на входе.

    Требует unit-размеров у присутствующих технологий (иначе штук нет);
    у дизеля unit_kw обязателен — без размера юнита нельзя стадировать.
    """
    load, dt_hours, solar_unit = prepare_series(scenario, weather_csv)
    load_arr = load.to_numpy(dtype=float)
    solar_arr = solar_unit.to_numpy(dtype=float)
    n = len(load_arr)
    rate = scenario.financial.discount_rate_fraction

    # Масштаб на долю года — как в LP-сайзере (Calliope
    # annualisation_weight): на полном годе 1, укороченный ряд платит
    # честную долю годового капитала.
    year_fraction = n * dt_hours / HOURS_PER_YEAR

    prob = pulp.LpProblem("greenhouse_sizing_milp", pulp.LpMinimize)

    # --- размеры как ЦЕЛОЕ число юнитов (A2) ---
    # size = units * unit_size; при отсутствии unit-размера технология
    # остаётся непрерывной (integer-сайзинг для неё просто не запрошен).
    sizes = {"pv_kwp": 0.0, "batt_kwh": 0.0, "batt_kw": 0.0, "dg_kw": 0.0}
    unit_vars: dict = {}

    def _int_units(name, unit, min_kw, max_kw):
        """Целочисленная переменная «число юнитов» в границах коридора.

        Границы в штуках: снизу ceil(min/unit) (уважаем нижний порог),
        сверху floor(max/unit) (не превышаем потолок). Если коридор уже
        одного юнита (частый случай — ФИКСИРОВАННЫЙ размер min==max, не
        кратный юниту: 1200 кВт генсетами по 500), берём ближайшее целое
        число юнитов к середине — целыми машинами точную дробь не купить.
        """
        lo = max(0, math.ceil(min_kw / unit - 1e-9))
        hi = math.floor(max_kw / unit + 1e-9)
        if hi < lo:
            hi = lo = max(0, round((min_kw + max_kw) / 2 / unit))
        return prob.add_variable(name, lowBound=lo, upBound=hi, cat="Integer")

    if scenario.pv is not None:
        if scenario.pv.unit_kw:
            unit_vars["pv"] = _int_units(
                "units_pv", scenario.pv.unit_kw,
                scenario.pv.min_kw, scenario.pv.max_kw,
            )
            sizes["pv_kwp"] = unit_vars["pv"] * scenario.pv.unit_kw
        else:
            sizes["pv_kwp"] = prob.add_variable(
                "size_pv_kwp", lowBound=scenario.pv.min_kw,
                upBound=scenario.pv.max_kw,
            )
    if scenario.battery is not None:
        b = scenario.battery
        if b.unit_kwh:
            unit_vars["batt_cab"] = _int_units(
                "units_batt_cab", b.unit_kwh, b.min_kwh, b.max_kwh)
            sizes["batt_kwh"] = unit_vars["batt_cab"] * b.unit_kwh
        else:
            sizes["batt_kwh"] = prob.add_variable(
                "size_batt_kwh", lowBound=b.min_kwh, upBound=b.max_kwh)
        if b.unit_kw:
            unit_vars["batt_pcs"] = _int_units(
                "units_batt_pcs", b.unit_kw, b.min_kw, b.max_kw)
            sizes["batt_kw"] = unit_vars["batt_pcs"] * b.unit_kw
        else:
            sizes["batt_kw"] = prob.add_variable(
                "size_batt_kw", lowBound=b.min_kw, upBound=b.max_kw)

    dg_op = None
    dg_unit_kw = None
    if scenario.diesel is not None:
        d = scenario.diesel
        if not d.unit_kw:
            raise RuntimeError(
                "MILP: у дизеля обязателен unit_kw (размер одного генсета) "
                "— без него нельзя стадировать парк"
            )
        dg_unit_kw = d.unit_kw
        unit_vars["dg"] = _int_units(
            "units_dg", d.unit_kw, d.min_kw, d.max_kw)
        sizes["dg_kw"] = unit_vars["dg"] * d.unit_kw
        # A3: сколько юнитов РАБОТАЕТ в каждый час (целое, ≤ установленных).
        hi = int(math.floor(d.max_kw / d.unit_kw + 1e-9))
        dg_op = prob.add_variable_dicts(
            "dg_units_on", range(n), lowBound=0, upBound=hi, cat="Integer")

    v = _build_lp_core(
        prob, scenario, n, dt_hours, load_arr, solar_arr, sizes,
        cyclic_soc=cyclic_soc,
    )

    # --- A1/A3: стадирование парка и минимальная загрузка ---
    if scenario.diesel is not None:
        turn_down = scenario.diesel.min_turn_down_fraction or 0.0
        for t in range(n):
            # Работать могут только установленные юниты.
            prob += dg_op[t] <= unit_vars["dg"], f"dg_units_avail_{t}"
            # Выдача ≤ мощности РАБОТАЮЩИХ юнитов (стоящий даёт 0).
            prob += v["dg"][t] <= dg_op[t] * dg_unit_kw, f"dg_stage_cap_{t}"
            # Включённый юнит не опускается ниже полки min_turn_down.
            if turn_down:
                prob += (
                    v["dg"][t] >= dg_op[t] * dg_unit_kw * turn_down
                ), f"dg_min_load_{t}"

    # --- оперативный резерв: у дизеля резерв дают ТОЛЬКО работающие юниты ---
    if scenario.diesel is not None:
        dg_headroom = [dg_op[t] * dg_unit_kw - v["dg"][t] for t in range(n)]
    else:
        dg_headroom = [0.0 for _ in range(n)]
    _add_operating_reserve(
        prob, scenario, n, dt_hours, load_arr, solar_arr, sizes, v, dg_headroom
    )

    # --- целевая функция ---
    # Капитальные слагаемые × year_fraction (масштаб на долю года).
    objective = []
    if scenario.pv is not None:
        crf_pv = capital_recovery_factor(rate, scenario.pv.lifetime_years)
        objective.append(
            (crf_pv * scenario.pv.capex_usd_per_kw
             + scenario.pv.om_usd_per_kw_year)
            * year_fraction * sizes["pv_kwp"]
        )
    if scenario.battery is not None:
        b = scenario.battery
        crf_b = capital_recovery_factor(rate, b.lifetime_years)
        objective.append(
            (crf_b * b.capex_usd_per_kwh + b.om_usd_per_kwh_year)
            * year_fraction * sizes["batt_kwh"]
        )
        objective.append(
            crf_b * b.capex_usd_per_kw * year_fraction * sizes["batt_kw"])
    if scenario.diesel is not None:
        d = scenario.diesel
        crf_d = capital_recovery_factor(rate, d.lifetime_years)
        objective.append(
            (crf_d * d.capex_usd_per_kw + d.om_usd_per_kw_year)
            * year_fraction * sizes["dg_kw"]
        )
        # Топливо: маргинальный расход на выработку (цена левелизована
        # эскалацией — изъян №6)...
        lf = fuel_levelization_factor(
            rate, d.fuel_escalation_fraction, scenario.financial.project_years)
        objective.append(
            pulp.lpSum(
                dt_hours * d.fuel_cost_usd_per_kwh * lf * v["dg"][t]
                for t in range(n)
            )
        )
        # ...плюс ПОСТОЯННЫЙ расход холостого хода на каждый работающий юнит
        # (A1, intercept): $ = цена_литра * литров/час * работающие_юниты.
        idle_l = d.fuel_idle_liters_per_hour or 0.0
        if idle_l:
            price_l = d.fuel_price_usd_per_liter
            objective.append(
                pulp.lpSum(
                    dt_hours * price_l * lf * idle_l * dg_op[t]
                    for t in range(n)
                )
            )
        # Цена углерода — как в LP-сайзере (аудит №3).
        if scenario.financial.co2_price_usd_per_ton:
            kg = d.co2_kg_per_kwh or DIESEL_CO2_KG_PER_KWH_DEFAULT
            objective.append(
                pulp.lpSum(
                    dt_hours * (scenario.financial.co2_price_usd_per_ton
                                / 1000.0) * kg * v["dg"][t]
                    for t in range(n)
                )
            )

    # надёжность (та же, что в LP-сайзере)
    mode = scenario.reliability.mode
    total_shortfall_kwh = pulp.lpSum(
        dt_hours * v["shortfall"][t] for t in range(n)
    )
    if mode == "hard":
        prob += total_shortfall_kwh == 0, "reliability_hard"
    elif mode == "lpsp":
        total_load_kwh = float(load_arr.sum() * dt_hours)
        prob += (
            total_shortfall_kwh
            <= scenario.reliability.lpsp_max_fraction * total_load_kwh
        ), "reliability_lpsp"
    else:
        objective.append(
            scenario.reliability.voll_usd_per_kwh * total_shortfall_kwh
        )

    # микроштраф от вырожденности — на непрерывные/целые размеры
    objective.append(
        pulp.lpSum(
            SIZE_TIEBREAK_USD * s
            for s in sizes.values()
            if isinstance(s, (pulp.LpVariable, pulp.LpAffineExpression))
        )
    )
    prob += pulp.lpSum(objective)

    # площадь под панели
    if scenario.pv is not None and scenario.site.roof_area_m2 is not None:
        m2_per_kwp = scenario.pv.m2_per_kwp or DEFAULT_M2_PER_KWP
        prob += (
            sizes["pv_kwp"] * m2_per_kwp <= scenario.site.roof_area_m2
        ), "roof_area"

    # C-rate коридор батареи — как в LP-сайзере.
    _add_c_rate(prob, scenario, sizes)

    if lp_snapshot_path is not None:
        prob.writeLP(lp_snapshot_path)

    solver_info = _solve(prob, solver, time_limit=time_limit, gap=gap)

    def _val(x):
        return float(x) if isinstance(x, (int, float)) else float(pulp.value(x))

    solved_sizes = {k: _val(s) for k, s in sizes.items()}
    units = _sizes_to_units(scenario, solved_sizes)

    # Сводка стадирования: сколько юнитов установлено и как парк дышит.
    staging = None
    if scenario.diesel is not None:
        on = [int(round(pulp.value(dg_op[t]))) for t in range(n)]
        staging = {
            "dg_unit_kw": dg_unit_kw,
            "dg_units_installed": int(round(pulp.value(unit_vars["dg"]))),
            "dg_units_on_max": max(on),
            "dg_units_on_mean": round(sum(on) / n, 3),
            "min_turn_down_fraction": scenario.diesel.min_turn_down_fraction,
            "fuel_idle_liters_per_hour": scenario.diesel.fuel_idle_liters_per_hour,
        }

    sim = _extract_result(
        scenario, load, dt_hours, solar_unit, solved_sizes, v,
        source_model=SOURCE_MODEL_MILP,
        solver_info=solver_info,
        results_dir=results_dir,
        write_outputs=write_outputs,
        extra={
            "sizes": {k: round(x, 3) for k, x in solved_sizes.items()},
            "units": units,
            "reliability_mode": mode,
            "cyclic_soc": cyclic_soc,
            "milp": True,
            "diesel_staging": staging,
        },
    )
    return SizingResult(sizes=solved_sizes, units=units, sim=sim)


@dataclass(frozen=True)
class RepresentativeSizingResult:
    """Ответ сайзера на типовых сутках: размеры + паспорт решения."""

    sizes: dict
    units: dict
    objective_value: float
    solver_info: dict
    lpsp: float | None
    n_clusters: int
    weights: list


def optimize_sizing_representative(
    scenario: Scenario,
    weather_csv: str | None = None,
    n_days: int = 12,
    seed: int = 0,
    solver: str | None = None,
) -> RepresentativeSizingResult:
    """Сайзинг на ТИПОВЫХ СУТКАХ с двухуровневым SOC (аудит №3, шаг 6).

    Год сжимается в K кластерных суток с весами (aggregate.py), а
    сезонность батареи сохраняется формулировкой inter-cluster storage
    из Calliope (storage_inter_cluster.yaml):

      s_intra[c,h] — ВИРТУАЛЬНЫЙ запас внутри типовых суток кластера c,
          стартует с 0 и может быть ОТРИЦАТЕЛЬНЫМ (это отклонение от
          межсуточного уровня, не абсолютный запас);
      smax/smin[c] — максимум/минимум s_intra за сутки кластера;
      soc_inter[d] — абсолютный уровень на НАЧАЛО каждых реальных суток
          d = 0..364; связь дней:
              soc_inter[d+1] == decay24 * soc_inter[d] + s_intra[c(d), 23]
          (кольцо: 365-е сутки перетекают в первые);
      границы на каждый день:
              soc_inter[d] + smax[c(d)] <= ёмкость
              decay24 * soc_inter[d] + smin[c(d)] >= пол SOC.

    Приближения v1 (документированы): ограничение 4h (no-overfill) и
    операционный резерв в этом режиме не поддержаны — резервные поля
    отвергаются громкой ошибкой. Размеры непрерывные (LP): цель режима —
    скорость и дорога к масштабируемому MILP.
    """
    from src.aggregate import build_representative_year

    rel = scenario.reliability
    if rel.operating_reserve_load_fraction or rel.operating_reserve_pv_fraction:
        raise ValueError(
            "Типовые сутки v1 не поддерживают операционный резерв — "
            "убери operating_reserve_* или используй optimize_sizing"
        )

    rep = build_representative_year(scenario, weather_csv, n_days, seed)
    k, h_day = rep.load_kw.shape
    dt = rep.dt_hours
    w = rep.weights
    rate = scenario.financial.discount_rate_fraction
    year_fraction = float((w.sum() * h_day * dt) / HOURS_PER_YEAR)  # == 1

    prob = pulp.LpProblem("greenhouse_sizing_rep", pulp.LpMinimize)

    # --- размеры (как в optimize_sizing) ---
    sizes = {"pv_kwp": 0.0, "batt_kwh": 0.0, "batt_kw": 0.0, "dg_kw": 0.0}
    if scenario.pv is not None:
        sizes["pv_kwp"] = prob.add_variable(
            "size_pv_kwp", lowBound=scenario.pv.min_kw,
            upBound=scenario.pv.max_kw)
    if scenario.battery is not None:
        b = scenario.battery
        sizes["batt_kwh"] = prob.add_variable(
            "size_batt_kwh", lowBound=b.min_kwh, upBound=b.max_kwh)
        sizes["batt_kw"] = prob.add_variable(
            "size_batt_kw", lowBound=b.min_kw, upBound=b.max_kw)
    if scenario.diesel is not None:
        sizes["dg_kw"] = prob.add_variable(
            "size_dg_kw", lowBound=scenario.diesel.min_kw,
            upBound=scenario.diesel.max_kw)

    has_batt = scenario.battery is not None
    if has_batt:
        eta = math.sqrt(scenario.battery.rte_fraction)
        soc_min_frac = scenario.battery.soc_min_fraction
        loss = scenario.battery.self_discharge_fraction_per_hour or 0.0
        decay = (1.0 - loss) ** dt
    else:
        eta, soc_min_frac, decay = 1.0, 0.0, 1.0
    decay24 = decay ** h_day

    idx = [(c, h) for c in range(k) for h in range(h_day)]
    charge = prob.add_variable_dicts("r_charge", idx, lowBound=0)
    discharge = prob.add_variable_dicts("r_discharge", idx, lowBound=0)
    dg = prob.add_variable_dicts("r_dg", idx, lowBound=0)
    curtail = prob.add_variable_dicts("r_curtail", idx, lowBound=0)
    shortfall = prob.add_variable_dicts("r_short", idx, lowBound=0)

    allow_dg_charge = (
        scenario.diesel is not None and scenario.diesel.can_charge_battery
        and has_batt
    )
    dg_to_batt = (prob.add_variable_dicts("r_dg2b", idx, lowBound=0)
                  if allow_dg_charge else None)

    # Внутрисуточный виртуальный запас (свободного знака) + max/min.
    s_intra = prob.add_variable_dicts("r_soc_intra", idx)
    smax = prob.add_variable_dicts("r_soc_max", range(k))
    smin = prob.add_variable_dicts("r_soc_min", range(k))

    for c in range(k):
        # Старт суток кластера — нулевое отклонение; max/min покрывают
        # и стартовую точку.
        prob += smax[c] >= 0, f"r_smax0_{c}"
        prob += smin[c] <= 0, f"r_smin0_{c}"
        for h in range(h_day):
            pv_gen = sizes["pv_kwp"] * float(rep.solar_unit[c, h])
            load_kw = float(rep.load_kw[c, h])

            prob += (
                pv_gen + discharge[c, h] + dg[c, h] + shortfall[c, h]
                == load_kw + charge[c, h] + curtail[c, h]
            ), f"r_balance_{c}_{h}"
            if dg_to_batt is None:
                prob += (charge[c, h] + curtail[c, h] <= pv_gen
                         ), f"r_split_{c}_{h}"
            else:
                prob += (charge[c, h] + curtail[c, h]
                         <= pv_gen + dg_to_batt[c, h]), f"r_split_{c}_{h}"
                prob += dg_to_batt[c, h] <= dg[c, h], f"r_dg2b_a_{c}_{h}"
                prob += dg_to_batt[c, h] <= charge[c, h], f"r_dg2b_b_{c}_{h}"
            prob += charge[c, h] <= sizes["batt_kw"], f"r_chcap_{c}_{h}"
            prob += discharge[c, h] <= sizes["batt_kw"], f"r_discap_{c}_{h}"
            prob += dg[c, h] <= sizes["dg_kw"], f"r_dgcap_{c}_{h}"

            prev = s_intra[c, h - 1] if h > 0 else 0.0
            prob += (
                s_intra[c, h]
                == decay * prev + dt * (eta * charge[c, h]
                                        - discharge[c, h] / eta)
            ), f"r_socdyn_{c}_{h}"
            prob += smax[c] >= s_intra[c, h], f"r_smax_{c}_{h}"
            prob += smin[c] <= s_intra[c, h], f"r_smin_{c}_{h}"

    # --- межсуточный уровень: 365 реальных суток кольцом ---
    n_real = len(rep.day_to_cluster)
    soc_inter = prob.add_variable_dicts("r_soc_inter", range(n_real), lowBound=0)
    for d in range(n_real):
        c = int(rep.day_to_cluster[d])
        nxt = (d + 1) % n_real
        prob += (
            soc_inter[nxt]
            == decay24 * soc_inter[d] + s_intra[c, h_day - 1]
        ), f"r_inter_{d}"
        prob += (
            soc_inter[d] + smax[c] <= sizes["batt_kwh"]
        ), f"r_inter_max_{d}"
        prob += (
            decay24 * soc_inter[d] + smin[c]
            >= soc_min_frac * sizes["batt_kwh"]
        ), f"r_inter_min_{d}"

    # --- целевая функция (веса кластеров делают топливо годовым) ---
    objective = []
    if scenario.pv is not None:
        crf_pv = capital_recovery_factor(rate, scenario.pv.lifetime_years)
        objective.append(
            (crf_pv * scenario.pv.capex_usd_per_kw
             + scenario.pv.om_usd_per_kw_year)
            * year_fraction * sizes["pv_kwp"])
    if scenario.battery is not None:
        b = scenario.battery
        crf_b = capital_recovery_factor(rate, b.lifetime_years)
        objective.append(
            (crf_b * b.capex_usd_per_kwh + b.om_usd_per_kwh_year)
            * year_fraction * sizes["batt_kwh"])
        objective.append(
            crf_b * b.capex_usd_per_kw * year_fraction * sizes["batt_kw"])
    if scenario.diesel is not None:
        d_ = scenario.diesel
        crf_d = capital_recovery_factor(rate, d_.lifetime_years)
        objective.append(
            (crf_d * d_.capex_usd_per_kw + d_.om_usd_per_kw_year)
            * year_fraction * sizes["dg_kw"])
        lf = fuel_levelization_factor(
            rate, d_.fuel_escalation_fraction, scenario.financial.project_years)
        objective.append(pulp.lpSum(
            float(w[c]) * dt * d_.fuel_cost_usd_per_kwh * lf * dg[c, h]
            for c, h in idx))
        if scenario.financial.co2_price_usd_per_ton:
            kg = d_.co2_kg_per_kwh or DIESEL_CO2_KG_PER_KWH_DEFAULT
            objective.append(pulp.lpSum(
                float(w[c]) * dt
                * (scenario.financial.co2_price_usd_per_ton / 1000.0)
                * kg * dg[c, h] for c, h in idx))

    total_short = pulp.lpSum(
        float(w[c]) * dt * shortfall[c, h] for c, h in idx)
    total_load = float(sum(
        w[c] * dt * rep.load_kw[c, h] for c in range(k) for h in range(h_day)))
    mode = rel.mode
    if mode == "hard":
        prob += total_short == 0, "r_hard"
    elif mode == "lpsp":
        prob += total_short <= rel.lpsp_max_fraction * total_load, "r_lpsp"
    else:
        objective.append(rel.voll_usd_per_kwh * total_short)

    objective.append(pulp.lpSum(
        SIZE_TIEBREAK_USD * s for s in sizes.values()
        if isinstance(s, pulp.LpVariable)))
    prob += pulp.lpSum(objective)

    if scenario.pv is not None and scenario.site.roof_area_m2 is not None:
        m2 = scenario.pv.m2_per_kwp or DEFAULT_M2_PER_KWP
        prob += sizes["pv_kwp"] * m2 <= scenario.site.roof_area_m2, "r_roof"
    _add_c_rate(prob, scenario, sizes)

    solver_info = _solve(prob, solver)

    solved = {k_: (s.value() if isinstance(s, pulp.LpVariable) else s)
              for k_, s in sizes.items()}
    units = _sizes_to_units(scenario, solved)
    short_val = float(pulp.value(total_short))
    return RepresentativeSizingResult(
        sizes=solved,
        units=units,
        objective_value=solver_info["objective_value"],
        solver_info=solver_info,
        lpsp=short_val / total_load if total_load > 0 else None,
        n_clusters=k,
        weights=[float(x) for x in w],
    )


# ---------- приватные помощники ----------


def _add_c_rate(prob: pulp.LpProblem, scenario: Scenario, sizes: dict) -> None:
    """C-rate коридор батареи: c_min * kWh <= kW <= c_max * kWh.

    Паттерн flow_cap_per_storage_cap_min/max Calliope (base.yaml:564):
    мощность PCS и ёмкость ячеек — физически связанные размеры; поля
    не заданы — ограничений нет (прежнее поведение).
    """
    b = scenario.battery
    if b is None:
        return
    if b.c_rate_max is not None:
        prob += (
            sizes["batt_kw"] <= b.c_rate_max * sizes["batt_kwh"]
        ), "c_rate_max"
    if b.c_rate_min is not None:
        prob += (
            sizes["batt_kw"] >= b.c_rate_min * sizes["batt_kwh"]
        ), "c_rate_min"


def _build_lp_core(
    prob: pulp.LpProblem,
    scenario: Scenario,
    n: int,
    dt_hours: float,
    load_arr,
    solar_arr,
    sizes: dict,
    cyclic_soc: bool,
    soc_init_kwh: float | None = None,
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

    # Заряд батареи от дизеля (cycle charging, аудит №2 изъян №2) —
    # только по явному флагу сценария: у REopt такой поток есть всегда
    # (Generator в techs.elec), у HOMER это стратегия Cycle Charging.
    allow_dg_charge = (
        scenario.diesel is not None
        and scenario.diesel.can_charge_battery
        and scenario.battery is not None
    )
    dg_to_batt = (
        prob.add_variable_dicts("dg_to_batt_kw", range(n), lowBound=0)
        if allow_dg_charge else None
    )

    # Нецикличный старт — полная батарея (REopt off-grid:
    # soc_init_fraction=1.0); в sizing это 1.0 * batt_kwh_var — линейно.
    # soc_init_kwh задаёт ЯВНЫЙ старт (rolling-horizon MPC переносит
    # запас между окнами).
    soc_init = sizes["batt_kwh"] if soc_init_kwh is None else soc_init_kwh

    # "Предыдущий" запас каждого шага — понадобится слою резерва
    # (сколько ещё разряда доступно над полом soc_min).
    soc_prev = {}

    for t in range(n):
        pv_gen_t = sizes["pv_kwp"] * solar_arr[t]

        # Баланс шага (REopt 8b).
        prob += (
            pv_gen_t + discharge[t] + dg[t] + shortfall[t]
            == load_arr[t] + charge[t] + curtail[t]
        ), f"balance_{t}"
        # Русла PV (REopt 4e): заряд и сброс питаются солнцем; при
        # включённом cycle charging заряд может добавить и дизель.
        if dg_to_batt is None:
            prob += charge[t] + curtail[t] <= pv_gen_t, f"pv_split_{t}"
        else:
            prob += (
                charge[t] + curtail[t] <= pv_gen_t + dg_to_batt[t]
            ), f"pv_split_{t}"
            # Дизельная часть заряда — часть выработки генсета...
            prob += dg_to_batt[t] <= dg[t], f"dg_charge_part_{t}"
            # ...и обязана реально идти в батарею (не в сброс): сброс
            # остаётся руслом ТОЛЬКО солнца, KPI curtail не искажается.
            prob += dg_to_batt[t] <= charge[t], f"dg_charge_used_{t}"
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
        soc_prev[t] = prev

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
        "eta": eta, "decay": decay, "soc_min_frac": soc_min_frac,
        "soc_prev": soc_prev, "dg_to_batt": dg_to_batt,
    }


def _add_operating_reserve(
    prob: pulp.LpProblem,
    scenario: Scenario,
    n: int,
    dt_hours: float,
    load_arr,
    solar_arr,
    sizes: dict,
    v: dict,
    dg_headroom,
) -> None:
    """Оперативный резерв (REopt operating_reserve_constraints.jl).

    В каждый час предоставленный резерв обязан покрыть требуемый:
      предоставляют — недогруженный дизель и свободный разряд батареи;
      требуют — доля нагрузки и доля выработки PV (страховка от облаков).
    Panель сама резерв НЕ даёт: она и есть источник неопределённости.

    dg_headroom — список выражений «свободная мощность дизеля в час t»:
      LP  — sizes["dg_kw"] - dg[t] (весь установленный минус выработка);
      MILP — dg_op[t]*unit_kw - dg[t] (только РАБОТАЮЩИЕ юниты — стоящий
      генсет вращающийся резерв не держит, как binGenIsOnInTS в REopt).

    Ничего не добавляет, если обе доли резерва не заданы (обратная
    совместимость: старые сценарии считаются ровно как раньше).
    """
    rel = scenario.reliability
    res_load = rel.operating_reserve_load_fraction or 0.0
    res_pv = rel.operating_reserve_pv_fraction or 0.0
    if not res_load and not res_pv:
        return

    has_batt = scenario.battery is not None
    has_dg = scenario.diesel is not None
    eta = v["eta"]
    decay = v["decay"]
    soc_min_frac = v["soc_min_frac"]

    op_dg = (
        prob.add_variable_dicts("opres_dg_kw", range(n), lowBound=0)
        if has_dg else None
    )
    op_bt = (
        prob.add_variable_dicts("opres_batt_kw", range(n), lowBound=0)
        if has_batt else None
    )

    for t in range(n):
        provided = []
        if has_dg:
            # Свободная мощность генсета над текущей выработкой.
            prob += op_dg[t] <= dg_headroom[t], f"opres_dg_cap_{t}"
            provided.append(op_dg[t])
        if has_batt:
            prev = v["soc_prev"][t]
            # Энергия: максимум AC-разряда над полом soc_min за шаг,
            # минус уже отдаваемый разряд (совпадает с available_kw
            # rule-симулятора: (soc - soc_min)*η/Δt).
            prob += (
                op_bt[t]
                <= (decay * prev - soc_min_frac * sizes["batt_kwh"])
                * eta / dt_hours - v["discharge"][t]
            ), f"opres_batt_energy_{t}"
            # Мощность: свободный разрядный канал PCS.
            prob += (
                op_bt[t] <= sizes["batt_kw"] - v["discharge"][t]
            ), f"opres_batt_power_{t}"
            provided.append(op_bt[t])
        required = (
            res_load * load_arr[t]
            + res_pv * sizes["pv_kwp"] * solar_arr[t]
        )
        prob += pulp.lpSum(provided) >= required, f"opres_req_{t}"


def _solve(
    prob: pulp.LpProblem,
    preference: str | None = None,
    time_limit: float | None = None,
    gap: float | None = None,
) -> dict:
    """Решает (MI)LP и возвращает паспорт солвера; не-Optimal — ошибка.

    time_limit / gap — только для MILP: предел времени в секундах и
    относительный зазор оптимальности (0.01 = принять решение в пределах
    1% от доказанного оптимума). У чистого LP зазора нет — оба None.
    """
    solver_name, solver = _pick_solver(preference, time_limit, gap)
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
        # Дизельная часть заряда (cycle charging): PV-к-нагрузке — это
        # выработка минус СОЛНЕЧНАЯ часть заряда, иначе pv_to_load ушёл
        # бы в минус, когда батарею наполняет генсет.
        dg_chg_t = (v["dg_to_batt"][t].value()
                    if v.get("dg_to_batt") is not None else 0.0)
        rec = TimestepRecord(
            run_id=run_id,
            timestamp=ts,
            load_kw=float(load_arr[t]),
            pv_gen_kw=float(pv_gen_t),
            pv_to_load_kw=float(pv_gen_t - (charge_t - dg_chg_t) - curtail_t),
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


def _pick_solver(
    preference: str | None = None,
    time_limit: float | None = None,
    gap: float | None = None,
):
    """Выбор солвера.

    preference: "highs" / "cbc" — взять именно этот (для кросс-
    солверной сверки: два НЕЗАВИСИМЫХ солвера обязаны дать один
    оптимум); None — HiGHS, а если недоступен, честный откат на CBC.
    time_limit / gap — предел времени и зазор оптимальности для MILP
    (HiGHS/CBC умеют целочисленность; параметры игнорируются, если None).
    """
    def _kw():
        kw = {"msg": False}
        if time_limit is not None:
            kw["timeLimit"] = time_limit
        if gap is not None:
            kw["gapRel"] = gap
        return kw

    if preference is not None:
        name = preference.lower()
        if name == "highs":
            return "HiGHS", pulp.HiGHS(**_kw())
        if name == "cbc":
            return "CBC", pulp.PULP_CBC_CMD(**_kw())
        raise ValueError(f"Неизвестный солвер {preference!r}: жду 'highs' или 'cbc'")

    try:
        solver = pulp.HiGHS(**_kw())
        if solver.available():
            return "HiGHS", solver
    except Exception:
        pass
    warnings.warn("HiGHS недоступен — решаю запасным CBC (медленнее)")
    return "CBC", pulp.PULP_CBC_CMD(**_kw())
