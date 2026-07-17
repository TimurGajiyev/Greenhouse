"""KPI GreenHouse: технические показатели года из симуляции.
Версия v0.5 (шаг 6).

KPI (key performance indicators) — сводка "как система прожила год"
в терминах энергии и надёжности; деньги считает economics.py.
Источник данных — SimulationResult шага 5: totals из manifest
(энергии уже умножены на Δt) + таблица шагов для счётчика часов.
"""

from dataclasses import dataclass

from src.schema import Scenario
from src.simulate import SimulationResult

# Δt достаём из manifest, а не "предполагаем час": инвариант 1.

# Порог «генсет работает», кВт: всё, что ниже 1 Вт, — численный шум
# солвера, а не работа машины (аудит №2, изъян №10).
DG_ON_THRESHOLD_KW = 1e-3


@dataclass(frozen=True)
class KpiReport:
    """Технические итоги года. Энергии в kWh, доли 0..1."""

    load_kwh: float              # спрос за год
    served_kwh: float            # реально поставлено (load - shortfall)
    shortfall_kwh: float         # недопоставка
    lpsp: float | None           # доля недопоставки (None: нагрузки не было)
    renewable_fraction: float | None  # доля чистой энергии в поставке
    pv_gen_kwh: float            # вся выработка PV
    curtail_kwh: float           # сброшенный избыток
    curtail_fraction_of_pv: float | None  # доля сброса от выработки PV
    dg_kwh: float                # энергия дизеля
    dg_hours: float              # часов работы дизеля за год
    dg_fuel_usd: float           # стоимость топлива за год
    dg_fuel_liters: float | None  # литры; None = удельный расход не задан


def compute_kpi(scenario: Scenario, sim_result: SimulationResult) -> KpiReport:
    """Собирает KPI-отчёт по результату симуляции."""
    totals = sim_result.manifest["totals_kwh"]
    dt_hours = sim_result.manifest["timestep_hours"]
    table = sim_result.table

    load = totals["load"]
    shortfall = totals["shortfall"]
    served = load - shortfall
    dg = totals["dg"]

    # Renewable fraction: какая доля ПОСТАВЛЕННОЙ энергии пришла не из
    # дизеля. Поставка = PV напрямую + разряд батареи + дизель, поэтому
    # чистая доля = 1 - дизель/поставка.
    renewable = (1.0 - dg / served) if served > 0 else None

    # LPSP = Σ shortfall / Σ load (метрика надёжности, 0 = идеал).
    lpsp = (shortfall / load) if load > 0 else None

    pv_gen = totals["pv_gen"]
    curtail = totals["curtail"]

    # Часы работы дизеля: число шагов с мощностью выше порога * Δt.
    # Порог 1 Вт (аудит №2, изъян №10): LP-солвер может вернуть не
    # точный ноль, а 1e-9 кВт — без порога каждый такой шаг считался
    # бы часом работы генсета (вход графика ТО). На HiGHS/CBC шума
    # не наблюдалось (проверено), порог — страховка на будущее.
    dg_hours = float((table["dg_kw"] > DG_ON_THRESHOLD_KW).sum()) * dt_hours

    # Деньги топлива: цена из сценария; литры — ТОЛЬКО при заданном
    # удельном расходе (fuel_liters_per_kwh), иначе честный None —
    # числа не выдумываем (см. # ASSUMPTION в schema.DieselConfig).
    if scenario.diesel is not None:
        dg_fuel_usd = dg * scenario.diesel.fuel_cost_usd_per_kwh
        liters_per_kwh = scenario.diesel.fuel_liters_per_kwh
        dg_fuel_liters = dg * liters_per_kwh if liters_per_kwh else None
    else:
        dg_fuel_usd = 0.0
        dg_fuel_liters = None

    return KpiReport(
        load_kwh=load,
        served_kwh=served,
        shortfall_kwh=shortfall,
        lpsp=lpsp,
        renewable_fraction=renewable,
        pv_gen_kwh=pv_gen,
        curtail_kwh=curtail,
        curtail_fraction_of_pv=(curtail / pv_gen) if pv_gen > 0 else None,
        dg_kwh=dg,
        dg_hours=dg_hours,
        dg_fuel_usd=dg_fuel_usd,
        dg_fuel_liters=dg_fuel_liters,
    )
