"""Тесты больших блоков аудита №3 (v1.3): типовые сутки + двухуровневый
SOC, rolling-horizon MPC, вероятностный симулятор отключений, SPORES.
"""

import json

import numpy as np
import pandas as pd
import pytest

from src.schema import Scenario
from src.aggregate import build_representative_year
from src.optimize import optimize_dispatch, optimize_sizing, \
    optimize_sizing_representative
from src.simulate import run_simulation, SimulationResult
from src.mpc import optimize_dispatch_rolling
from src.outage_mc import outage_survival_curve
from src.spores import find_spores

SCENARIO_SIZING = "scenarios/yemen_sizing.json"
SCENARIO_VENDOR = "scenarios/yemen_vendor.json"
WEATHER_CSV = "tests/data/tmy_sanaa_pvgis_sarah3.csv"


def load_dict(path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ================= типовые сутки: кластеризация =================

def test_representative_year_shapes_and_weights():
    scenario = Scenario.model_validate(load_dict(SCENARIO_SIZING))
    rep = build_representative_year(scenario, WEATHER_CSV, n_days=6, seed=1)
    assert rep.load_kw.shape == (rep.n_clusters, 24)
    assert rep.solar_unit.shape == (rep.n_clusters, 24)
    assert rep.weights.sum() == pytest.approx(365)
    assert rep.day_to_cluster.shape == (365,)
    assert set(np.unique(rep.day_to_cluster)) <= set(range(rep.n_clusters))
    # Детерминизм: тот же seed — тот же разрез года.
    rep2 = build_representative_year(scenario, WEATHER_CSV, n_days=6, seed=1)
    assert (rep.day_to_cluster == rep2.day_to_cluster).all()


def test_representative_year_conserves_energy():
    """Центроиды с весами сохраняют годовые суммы точно (среднее по
    кластеру * размер кластера == сумма кластера)."""
    scenario = Scenario.model_validate(load_dict(SCENARIO_SIZING))
    rep = build_representative_year(scenario, WEATHER_CSV, n_days=8, seed=0)
    from src.simulate import prepare_series
    load, dt, solar = prepare_series(scenario, WEATHER_CSV)
    agg_load = float((rep.weights[:, None] * rep.load_kw).sum())
    agg_solar = float((rep.weights[:, None] * rep.solar_unit).sum())
    assert agg_load == pytest.approx(float(load.sum()), rel=1e-9)
    assert agg_solar == pytest.approx(float(solar.sum()), rel=1e-9)


def test_representative_rejects_non_hourly_year(tmp_path):
    csv = tmp_path / "short.csv"
    csv.write_text("timestamp,load_kw\n2026-01-01 00:00,10\n"
                   "2026-01-01 01:00,10\n", encoding="utf-8")
    data = load_dict(SCENARIO_SIZING)
    data["load"] = {"profile_csv": str(csv)}
    with pytest.raises(ValueError, match="8760"):
        build_representative_year(Scenario.model_validate(data), WEATHER_CSV)


# ================= типовые сутки: сайзер =================

def test_representative_sizing_close_to_full_year():
    """Сайзинг на 10 типовых сутках близок к полному году: PV упирается
    в ту же крышу, издержки в пределах 10% (кластеризация сглаживает
    крайности — лёгкий оптимизм ожидаем и задокументирован)."""
    data = load_dict(SCENARIO_SIZING)
    rep = optimize_sizing_representative(
        Scenario.model_validate(data), weather_csv=WEATHER_CSV, n_days=10)
    full = optimize_sizing(Scenario.model_validate(data),
                           weather_csv=WEATHER_CSV, write_outputs=False)

    assert rep.sizes["pv_kwp"] == pytest.approx(full.sizes["pv_kwp"], rel=1e-6)
    rel_gap = abs(rep.objective_value
                  / full.sim.manifest["objective_value"] - 1)
    assert rel_gap < 0.10
    assert rep.lpsp == pytest.approx(0.0, abs=1e-9)  # hard-режим держит
    assert rep.solver_info["solver_status"] == "Optimal"


def test_representative_rejects_operating_reserve():
    data = load_dict(SCENARIO_SIZING)
    data["reliability"]["operating_reserve_load_fraction"] = 0.2
    with pytest.raises(ValueError, match="резерв"):
        optimize_sizing_representative(
            Scenario.model_validate(data), weather_csv=WEATHER_CSV)


# ================= rolling-horizon MPC =================

def _mpc_toy(tmp_path) -> Scenario:
    """Игрушка, где близорукость наказуема: 2 часа [100, 100], дизель
    только 60 кВт, батарея 100 кВт*ч (старт полной, RTE=1, пола нет).
    Дальновидный план: делить батарею пополам (дизель оба часа на 60).
    Близорукий (окно 1 ч): сжечь батарею в час 0 бесплатно, а в час 1
    остаться с дизелем 60 и недопоставкой 40."""
    csv = tmp_path / "mpc_toy.csv"
    csv.write_text("timestamp,load_kw\n2026-01-01 00:00,100\n"
                   "2026-01-01 01:00,100\n", encoding="utf-8")
    return Scenario.model_validate({
        "name": "mpc-toy",
        "site": {"name": "x", "latitude": 15.28, "longitude": 44.08,
                 "timezone": "Asia/Aden"},
        "battery": {"capex_usd_per_kwh": 100, "capex_usd_per_kw": 0,
                    "om_usd_per_kwh_year": 0, "rte_fraction": 1.0,
                    "soc_min_fraction": 0.0,
                    "min_kwh": 100, "max_kwh": 100,
                    "min_kw": 100, "max_kw": 100, "lifetime_years": 10},
        "diesel": {"capex_usd_per_kw": 100, "om_usd_per_kw_year": 0,
                   "fuel_cost_usd_per_kwh": 0.26,
                   "min_kw": 60, "max_kw": 60, "lifetime_years": 10},
        "load": {"profile_csv": str(csv)},
        "financial": {"discount_rate_fraction": 0.0, "project_years": 10,
                      "currency": "USD"},
        "reliability": {"mode": "hard"},
    })


def test_mpc_full_horizon_reproduces_perfect_foresight(tmp_path):
    """Окно на весь ряд == perfect-foresight LP-диспетчер."""
    scenario = _mpc_toy(tmp_path)
    lp = optimize_dispatch(scenario, write_outputs=False)
    mpc = optimize_dispatch_rolling(scenario, horizon_hours=2, commit_hours=2)
    assert mpc.manifest["totals_kwh"]["dg"] == pytest.approx(
        lp.manifest["totals_kwh"]["dg"], abs=1e-6)
    assert mpc.manifest["totals_kwh"]["shortfall"] == pytest.approx(
        lp.manifest["totals_kwh"]["shortfall"], abs=1e-6)
    assert mpc.manifest["totals_kwh"]["shortfall"] == pytest.approx(0)


def test_mpc_myopia_costs_real_money(tmp_path):
    """Окно 1 час: батарея сжигается сразу (в окне она бесплатна),
    в час 1 — недопоставка 40 kWh. Ровно та близорукость, которую
    ловит rolling-horizon."""
    scenario = _mpc_toy(tmp_path)
    myopic = optimize_dispatch_rolling(scenario, horizon_hours=1,
                                       commit_hours=1)
    assert myopic.manifest["totals_kwh"]["shortfall"] == pytest.approx(40)
    # Запас честно переносится между окнами: после часа 0 батарея пуста.
    assert float(myopic.table["soc_kwh"].iloc[0]) == pytest.approx(0, abs=1e-6)
    assert myopic.manifest["mpc_windows"] == 2


def test_mpc_validates_window(tmp_path):
    with pytest.raises(ValueError, match="commit"):
        optimize_dispatch_rolling(_mpc_toy(tmp_path), horizon_hours=1,
                                  commit_hours=2)


def test_mpc_vendor_year_between_lp_and_rule():
    """Йемен, фиксированные вендорские размеры: MPC с суточным
    предвидением не хуже слепого правила и не лучше всевидящего LP."""
    scenario = Scenario.model_validate(load_dict(SCENARIO_VENDOR))
    lp = optimize_dispatch(scenario, weather_csv=WEATHER_CSV,
                           write_outputs=False)
    rule = run_simulation(scenario, weather_csv=WEATHER_CSV,
                          write_outputs=False)
    mpc = optimize_dispatch_rolling(scenario, weather_csv=WEATHER_CSV,
                                    horizon_hours=48, commit_hours=24)
    lp_dg = lp.manifest["totals_kwh"]["dg"]
    rule_dg = rule.manifest["totals_kwh"]["dg"]
    mpc_dg = mpc.manifest["totals_kwh"]["dg"]
    assert mpc.manifest["totals_kwh"]["shortfall"] == pytest.approx(0)
    assert mpc_dg >= lp_dg - 1e-6              # нижняя граница — предвидение
    assert mpc_dg <= rule_dg * 1.02 + 1e-6     # и не хуже слепого правила


# ================= вероятностный симулятор отключений =================

def _outage_scenario(batt_kwh=100.0, batt_kw=50.0) -> Scenario:
    return Scenario.model_validate({
        "name": "outage-toy",
        "site": {"name": "x", "latitude": 15.28, "longitude": 44.08,
                 "timezone": "Asia/Aden"},
        "battery": {"capex_usd_per_kwh": 100, "capex_usd_per_kw": 0,
                    "om_usd_per_kwh_year": 0, "rte_fraction": 1.0,
                    "soc_min_fraction": 0.0,
                    "min_kwh": batt_kwh, "max_kwh": batt_kwh,
                    "min_kw": batt_kw, "max_kw": batt_kw,
                    "lifetime_years": 10},
        "diesel": {"capex_usd_per_kw": 100, "om_usd_per_kw_year": 0,
                   "fuel_cost_usd_per_kwh": 0.26,
                   "fuel_liters_per_kwh": 0.27,
                   "min_kw": 100, "max_kw": 100, "lifetime_years": 10},
        "load": {"day_kw": 10, "night_kw": 10,
                 "work_start_hour": 8, "work_end_hour": 18},
        "financial": {"discount_rate_fraction": 0.0, "project_years": 10,
                      "currency": "USD"},
        "reliability": {"mode": "hard"},
    })


def _flat_table(n=48, load=10.0, pv=0.0, soc=100.0) -> pd.DataFrame:
    idx = pd.date_range("2026-01-01", periods=n, freq="h")
    return pd.DataFrame({
        "load_kw": load, "pv_gen_kw": pv, "soc_kwh": soc,
    }, index=idx)


def test_outage_hand_battery_only():
    """Батарея 100 кВт*ч, нагрузка 10 кВт, солнца нет: ровно 10 часов
    из любого старта."""
    surv = outage_survival_curve(
        _outage_scenario(), _flat_table(), durations_hours=(4, 8, 12, 24))
    assert (surv.survived_hours == 10).all()
    assert surv.survival_by_duration == {4: 1.0, 8: 1.0, 12: 0.0, 24: 0.0}
    assert surv.quantiles["p50"] == pytest.approx(10)


def test_outage_pv_covers_forever():
    """Солнце равно нагрузке — дефицита нет, выживание бесконечно
    (обрезано максимальной проверяемой длительностью)."""
    surv = outage_survival_curve(
        _outage_scenario(), _flat_table(pv=10.0), durations_hours=(24, 72))
    assert surv.survival_by_duration == {24: 1.0, 72: 1.0}


def test_outage_fuel_tank_extends_survival():
    """Аварийный генсет 10 кВт с баком 27 л (= 100 кВт*ч при 0.27 л/кВт*ч)
    добавляет ровно 10 часов к 10 батарейным: итого 20."""
    surv = outage_survival_curve(
        _outage_scenario(), _flat_table(), durations_hours=(12, 24),
        dg_available_kw=10.0, fuel_tank_liters=27.0)
    assert (surv.survived_hours == 20).all()
    assert surv.survival_by_duration == {12: 1.0, 24: 0.0}


def test_outage_tank_requires_consumption():
    data = json.loads(_outage_scenario().model_dump_json(exclude_none=True))
    del data["diesel"]["fuel_liters_per_kwh"]
    with pytest.raises(ValueError, match="fuel_liters_per_kwh"):
        outage_survival_curve(
            Scenario.model_validate(data), _flat_table(),
            dg_available_kw=10.0, fuel_tank_liters=27.0)


# ================= SPORES =================

def test_spores_respect_cap_and_differ():
    """Спор обязан стоить не дороже потолка и отличаться железом от
    оптимума (иначе он бесполезен как альтернатива)."""
    scenario = Scenario.model_validate(load_dict(SCENARIO_SIZING))
    rep = find_spores(scenario, weather_csv=WEATHER_CSV,
                      n_spores=1, slack=0.10)
    assert len(rep.spores) == 1
    spore = rep.spores[0]
    assert spore.cost_usd_per_year <= rep.cost_cap_usd_per_year + 1e-4
    # Хотя бы один размер сдвинулся заметно (>5% от оптимума).
    moved = any(
        abs(spore.sizes[k] - rep.base.sizes[k])
        > 0.05 * max(rep.base.sizes[k], 1.0)
        for k in ("pv_kwp", "batt_kwh", "batt_kw", "dg_kw")
    )
    assert moved
    # hard-режим: альтернатива тоже держит нагрузку.
    assert spore.lpsp == pytest.approx(0.0, abs=1e-9)


def test_spores_validation():
    scenario = Scenario.model_validate(load_dict(SCENARIO_SIZING))
    with pytest.raises(ValueError):
        find_spores(scenario, n_spores=0)
    with pytest.raises(ValueError):
        find_spores(scenario, slack=0.0)
