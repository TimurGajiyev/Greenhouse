"""Rolling-horizon MPC-диспетчер GreenHouse. Версия v1.3 (аудит №3, шаг 7).

Зачем: LP-диспетчер обладает идеальным предвидением — «знает» весь год
наперёд; rule-симулятор вовсе не смотрит вперёд. Реальный контроллер
посередине: у него есть ПРОГНОЗ на ближайшие сутки-двое. MPC (model
predictive control, скользящий горизонт) моделирует ровно это — как
отдельный режим mpc/ у REopt и operate-режим (окна) у Calliope:

    1) решить LP на окне [t, t+horizon) с текущим запасом батареи;
    2) ИСПОЛНИТЬ только первые commit часов решения;
    3) сдвинуть окно на commit и повторить.

Предвидение внутри окна — идеальное («прогноз сбывается»); честность
достигается тем, что решения за пределами окна контроллер не видит.
horizon > commit — стандартный приём MPC: хвост окна (lookahead)
защищает от близоруких решений на границе, но не исполняется.

Ядро окна — тот же _build_lp_core, что у диспетчера и сайзера
(инвариант «один движок»); цель окна — топливо + VOLL * недопоставка,
как в optimize_dispatch.
"""

import uuid
from dataclasses import asdict

import pandas as pd
import pulp

from src.optimize import (
    VOLL_DEFAULT_USD_PER_KWH,
    _add_operating_reserve,
    _build_lp_core,
    _solve,
)
from src.schema import Scenario
from src.simulate import (
    SimulationResult,
    TimestepRecord,
    _build_manifest,
    prepare_series,
    write_results,
)

SOURCE_MODEL_MPC = "mpc_v1"


def optimize_dispatch_rolling(
    scenario: Scenario,
    weather_csv: str | None = None,
    horizon_hours: int = 48,
    commit_hours: int = 24,
    voll_usd_per_kwh: float = VOLL_DEFAULT_USD_PER_KWH,
    soc_init_fraction: float = 1.0,
    solver: str | None = None,
    results_dir: str = "results",
    write_outputs: bool = False,
) -> SimulationResult:
    """Диспетчеризация скользящим горизонтом при ФИКСИРОВАННЫХ размерах.

    horizon_hours — сколько часов контроллер «видит» вперёд;
    commit_hours — сколько из них исполняется до пересчёта
    (commit <= horizon; horizon == длине ряда воспроизводит
    perfect-foresight LP-диспетчер — удобная проверка).
    """
    if commit_hours <= 0 or horizon_hours < commit_hours:
        raise ValueError(
            "MPC: нужно 0 < commit_hours <= horizon_hours, получено "
            f"commit={commit_hours}, horizon={horizon_hours}"
        )

    load, dt_hours, solar_unit = prepare_series(scenario, weather_csv)
    load_arr = load.to_numpy(dtype=float)
    solar_arr = solar_unit.to_numpy(dtype=float)
    n = len(load_arr)

    sizes = {
        "pv_kwp": scenario.pv.max_kw if scenario.pv else 0.0,
        "batt_kwh": scenario.battery.max_kwh if scenario.battery else 0.0,
        "batt_kw": scenario.battery.max_kw if scenario.battery else 0.0,
        "dg_kw": scenario.diesel.max_kw if scenario.diesel else 0.0,
    }
    fuel_price = (scenario.diesel.fuel_cost_usd_per_kwh
                  if scenario.diesel else 0.0)

    soc_now = soc_init_fraction * sizes["batt_kwh"]
    records: list[TimestepRecord] = []
    run_id = uuid.uuid4().hex[:12]
    n_windows = 0
    total_solve_seconds = 0.0

    t0 = 0
    while t0 < n:
        w_end = min(t0 + horizon_hours, n)
        w_n = w_end - t0
        commit = min(commit_hours, w_n)

        prob = pulp.LpProblem(f"mpc_window_{t0}", pulp.LpMinimize)
        v = _build_lp_core(
            prob, scenario, w_n, dt_hours,
            load_arr[t0:w_end], solar_arr[t0:w_end], sizes,
            cyclic_soc=False, soc_init_kwh=soc_now,
        )
        dg_headroom = [sizes["dg_kw"] - v["dg"][t] for t in range(w_n)]
        _add_operating_reserve(
            prob, scenario, w_n, dt_hours,
            load_arr[t0:w_end], solar_arr[t0:w_end], sizes, v, dg_headroom,
        )
        prob += pulp.lpSum(
            dt_hours * (fuel_price * v["dg"][t]
                        + voll_usd_per_kwh * v["shortfall"][t])
            for t in range(w_n)
        )
        info = _solve(prob, solver)
        n_windows += 1
        total_solve_seconds += info["solve_seconds"]

        # Исполняем только первые commit часов найденного плана.
        for i in range(commit):
            ts = load.index[t0 + i]
            pv_gen = sizes["pv_kwp"] * float(solar_arr[t0 + i])
            charge_i = v["charge"][i].value()
            curtail_i = v["curtail"][i].value()
            dg_chg_i = (v["dg_to_batt"][i].value()
                        if v.get("dg_to_batt") is not None else 0.0)
            records.append(TimestepRecord(
                run_id=run_id,
                timestamp=ts,
                load_kw=float(load_arr[t0 + i]),
                pv_gen_kw=float(pv_gen),
                pv_to_load_kw=float(
                    pv_gen - (charge_i - dg_chg_i) - curtail_i),
                charge_kw=float(charge_i),
                discharge_kw=float(v["discharge"][i].value()),
                dg_kw=float(v["dg"][i].value()),
                curtail_kw=float(curtail_i),
                shortfall_kw=float(v["shortfall"][i].value()),
                soc_kwh=float(v["soc"][i].value()),
                source_model=SOURCE_MODEL_MPC,
            ))
        soc_now = float(v["soc"][commit - 1].value())
        t0 += commit

    table = pd.DataFrame([asdict(r) for r in records]).set_index("timestamp")
    manifest = _build_manifest(
        run_id, scenario, load, solar_unit, dt_hours, table,
        source_model=SOURCE_MODEL_MPC,
        solver_info={
            "solver": info["solver"],
            "solver_status": "Optimal",
            "objective_value": float(
                (table["dg_kw"].sum() * dt_hours * fuel_price)
                + table["shortfall_kw"].sum() * dt_hours * voll_usd_per_kwh),
            "solve_seconds": round(total_solve_seconds, 3),
        },
        extra={
            "mpc_horizon_hours": horizon_hours,
            "mpc_commit_hours": commit_hours,
            "mpc_windows": n_windows,
        },
    )
    parquet_path = manifest_path = None
    if write_outputs:
        parquet_path, manifest_path = write_results(
            table, manifest, results_dir)
    return SimulationResult(
        table=table, manifest=manifest,
        parquet_path=parquet_path, manifest_path=manifest_path,
    )
