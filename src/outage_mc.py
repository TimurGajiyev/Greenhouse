"""Вероятностный симулятор отключений GreenHouse. Версия v1.3
(аудит №3, шаг 7; перенос идеи REopt outagesim/outage_simulator.jl).

Вопрос, на который отвечает модуль: «если дизель пропал (сломался /
кончилось топливо) в час X — сколько часов система проживёт на солнце
и батарее?» REopt отвечает на него не одним стресс-окном, а ПОЛНЫМ
перебором: отказ стартует в КАЖДЫЙ час года, и по 8760 исходам
строится распределение выживания. Это детерминированный аналог
Монте-Карло: вместо случайной выборки — вся генеральная совокупность
стартов.

Механика одного прогона (simulate_outage REopt, load following):
  старт — запас батареи из НОРМАЛЬНОЙ работы в час X (таблица прогона);
  дальше на каждом часе: PV кормит нагрузку, избыток заряжает батарею
  (КПД √RTE), дефицит кроет разряд (не ниже пола SOC) и, если разрешён,
  аварийный дизель с ограниченным баком; первый час с недопоставкой —
  конец выживания.

Выход — кривая выживания: P(прожить >= D часов) по каждому D, плюс
квантили распределения выживших часов.
"""

import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from src.schema import Scenario


@dataclass(frozen=True)
class OutageSurvival:
    """Распределение выживания без штатного дизеля."""

    survival_by_duration: dict      # {часы D: доля стартов, переживших D}
    survived_hours: np.ndarray = field(repr=False)  # (n_starts,)
    quantiles: dict = field(default_factory=dict)   # p10/p50/p90, часов
    n_starts: int = 0


def outage_survival_curve(
    scenario: Scenario,
    sim_table: pd.DataFrame,
    durations_hours: tuple[int, ...] = (4, 8, 12, 24, 48, 72),
    dg_available_kw: float = 0.0,
    fuel_tank_liters: float | None = None,
    starts_step: int = 1,
) -> OutageSurvival:
    """Кривая выживания: отказ стартует в каждый starts_step-й час года.

    sim_table — таблица штатного прогона (нужны load_kw, pv_gen_kw,
    soc_kwh: запас на момент отказа берётся из реальной траектории);
    dg_available_kw — мощность АВАРИЙНОГО генсета в отказе (0 = дизель
    недоступен полностью — наш «топливный разрыв»);
    fuel_tank_liters — бак аварийного генсета (None = не ограничен);
    требует diesel.fuel_liters_per_kwh для перевода литров в кВт*ч.
    """
    load = sim_table["load_kw"].to_numpy(dtype=float)
    pv = sim_table["pv_gen_kw"].to_numpy(dtype=float)
    soc0 = sim_table["soc_kwh"].to_numpy(dtype=float)
    n = len(load)
    dt = 1.0  # часовой ряд (инвариант таблиц прогонов)

    b = scenario.battery
    if b is not None:
        batt_kwh = b.max_kwh
        batt_kw = b.max_kw
        eta = math.sqrt(b.rte_fraction)
        floor = b.soc_min_fraction * batt_kwh
    else:
        batt_kwh = batt_kw = 0.0
        eta = 1.0
        floor = 0.0

    liters_per_kwh = (
        scenario.diesel.fuel_liters_per_kwh
        if scenario.diesel is not None else None
    )
    if dg_available_kw > 0 and fuel_tank_liters is not None \
            and not liters_per_kwh:
        raise ValueError(
            "outage: бак в литрах требует diesel.fuel_liters_per_kwh"
        )

    max_d = max(durations_hours)
    starts = range(0, n, starts_step)
    survived = np.empty(len(list(starts)), dtype=float)

    for si, s in enumerate(range(0, n, starts_step)):
        soc = float(soc0[s])
        fuel = fuel_tank_liters
        hours = max_d
        for i in range(max_d):
            t = (s + i) % n  # кольцо года, как в REopt
            deficit = load[t] - pv[t]
            if deficit <= 0:
                # Избыток солнца заряжает батарею.
                room_kw = (batt_kwh - soc) / (eta * dt) if batt_kwh else 0.0
                soc += eta * dt * min(-deficit, batt_kw, max(room_kw, 0.0))
                soc = min(soc, batt_kwh)
                continue
            # Аварийный дизель (если есть) кроет первым.
            if dg_available_kw > 0:
                dg_out = min(deficit, dg_available_kw)
                if fuel is not None:
                    fuel_can_kwh = fuel / liters_per_kwh
                    dg_out = min(dg_out, fuel_can_kwh / dt)
                    fuel -= dg_out * dt * liters_per_kwh
                deficit -= dg_out
            # Остаток — разряд батареи.
            if deficit > 1e-9:
                avail_kw = (soc - floor) * eta / dt if batt_kwh else 0.0
                dis = min(deficit, batt_kw, max(avail_kw, 0.0))
                soc -= dis * dt / eta
                deficit -= dis
            if deficit > 1e-6:
                hours = i  # первый непокрытый час — конец выживания
                break
        survived[si] = hours

    curve = {
        int(d): float((survived >= d).mean()) for d in durations_hours
    }
    quantiles = {
        "p10": float(np.quantile(survived, 0.10)),
        "p50": float(np.quantile(survived, 0.50)),
        "p90": float(np.quantile(survived, 0.90)),
    }
    return OutageSurvival(
        survival_by_duration=curve,
        survived_hours=survived,
        quantiles=quantiles,
        n_starts=len(survived),
    )
