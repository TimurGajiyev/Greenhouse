"""Тесты фиксов критического аудита №2 (v1.2).

Пять изъянов, закрытых в порядке «эффект/усилие»:
  №1  — экономика читает решённые размеры, а не потолок коридора;
  №10 — порог 1 Вт отсекает численный шум из моточасов дизеля;
  №2  — дизель может заряжать батарею (LP-поток dg→batt по флагу
        can_charge_battery + стратегия cycle_charging в симуляторе);
  №6  — эскалация цены топлива через левелизационный коэффициент;
  №3  — P90-множитель солнечного ряда (запас на слабый год).
"""

import json

import pandas as pd
import pytest

from src.schema import Scenario
from src.simulate import run_simulation, SimulationResult
from src.optimize import optimize_sizing
from src.economics import compute_economics, fuel_levelization_factor
from src.kpi import compute_kpi
from src.solar import build_solar_profile

SCENARIO_SIZING = "scenarios/yemen_sizing.json"
SCENARIO_VENDOR = "scenarios/yemen_vendor.json"
WEATHER_CSV = "tests/data/tmy_sanaa_pvgis_sarah3.csv"


def load_dict(path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ================= №1: экономика по решённым размерам =================

def test_economics_uses_solved_sizes_from_manifest():
    """Сайзер с ОТКРЫТЫМИ коридорами: экономика обязана считать деньги
    по решённым размерам из manifest, а не по потолку коридора
    (до фикса: CAPEX завышался в 5.3 раза, молча)."""
    data = load_dict(SCENARIO_SIZING)
    res = optimize_sizing(Scenario.model_validate(data),
                          weather_csv=WEATHER_CSV, write_outputs=False)
    eco = compute_economics(Scenario.model_validate(data), res.sim)

    s = res.sim.manifest["sizes"]
    expected_capex = (
        398 * s["pv_kwp"]
        + 196 * s["batt_kwh"] + 0 * s["batt_kw"]
        + 307 * s["dg_kw"]
    )
    assert eco.capex_total_usd == pytest.approx(expected_capex, rel=1e-6)
    # И это заведомо НЕ потолок коридора (5000 kWp и т.д.).
    ceiling_capex = 398 * 5000 + 196 * 20000 + 307 * 2000
    assert eco.capex_total_usd < 0.5 * ceiling_capex


def test_economics_open_corridor_without_sizes_raises():
    """Симуляция (без решённых размеров) на сценарии с открытым
    коридором — громкая ошибка, а не тихий CAPEX по потолку."""
    data = load_dict(SCENARIO_SIZING)  # коридоры открыты
    sim = run_simulation(Scenario.model_validate(data),
                         weather_csv=WEATHER_CSV, write_outputs=False)
    with pytest.raises(ValueError, match="коридор"):
        compute_economics(Scenario.model_validate(data), sim)


# ================= №10: порог моточасов =================

def test_dg_hours_ignores_solver_noise():
    """Шаги с dg <= 1 Вт — численный шум, не работа генсета."""
    scenario = Scenario.model_validate(load_dict(SCENARIO_VENDOR))
    idx = pd.date_range("2026-01-01", periods=5, freq="h")
    table = pd.DataFrame({
        "dg_kw": [0.0, 1e-9, 5e-4, 0.1, 5.0],
        "shortfall_kw": [0.0] * 5,
    }, index=idx)
    manifest = {
        "timestep_hours": 1.0,
        "totals_kwh": {"load": 5.0, "shortfall": 0.0, "dg": 5.1,
                       "pv_gen": 0.0, "curtail": 0.0, "discharge": 0.0},
    }
    sim = SimulationResult(table=table, manifest=manifest,
                           parquet_path=None, manifest_path=None)
    kpi = compute_kpi(scenario, sim)
    # Только 0.1 и 5.0 выше порога 1 Вт -> 2 часа, а не 4.
    assert kpi.dg_hours == pytest.approx(2.0)


# ================= №2: дизель заряжает батарею =================

def _dg_batt_scenario(tmp_path, can_charge: bool) -> Scenario:
    """Игрушка, где БЕЗ dg→batt задача неразрешима: пик 140 kW выше
    генсета 100 kW, солнца нет, батарея (RTE=1) может спасти, только
    если её наполнит дизель в час низкой нагрузки (кольцо SOC)."""
    csv = tmp_path / "dgbatt.csv"
    csv.write_text(
        "timestamp,load_kw\n"
        "2026-01-01 00:00,60\n2026-01-01 01:00,140\n",
        encoding="utf-8",
    )
    return Scenario.model_validate({
        "name": "dg-charges-battery",
        "site": {"name": "x", "latitude": 15.28, "longitude": 44.08,
                 "timezone": "Asia/Aden"},
        "battery": {
            "capex_usd_per_kwh": 100, "capex_usd_per_kw": 0,
            "om_usd_per_kwh_year": 0, "rte_fraction": 1.0,
            "soc_min_fraction": 0.0,
            "min_kwh": 100, "max_kwh": 100, "min_kw": 200, "max_kw": 200,
            "lifetime_years": 10,
        },
        "diesel": {
            "capex_usd_per_kw": 100, "om_usd_per_kw_year": 0,
            "fuel_cost_usd_per_kwh": 0.26,
            "can_charge_battery": can_charge,
            "min_kw": 100, "max_kw": 100, "lifetime_years": 10,
        },
        "load": {"profile_csv": str(csv)},
        "financial": {"discount_rate_fraction": 0.0, "project_years": 10,
                      "currency": "USD"},
        "reliability": {"mode": "hard"},
    })


def test_lp_dg_charges_battery_when_enabled(tmp_path):
    """С флагом: генсет в час 60 кВт работает на 100, лишние 40 — в
    батарею; в час пика 140 = 100 (генсет) + 40 (разряд). Недопоставки
    нет, топливо ровно 200 kWh * 0.26."""
    res = optimize_sizing(_dg_batt_scenario(tmp_path, True),
                          write_outputs=False)
    m = res.sim.manifest
    assert m["totals_kwh"]["shortfall"] == pytest.approx(0)
    assert m["totals_kwh"]["dg"] == pytest.approx(200)
    assert m["totals_kwh"]["discharge"] == pytest.approx(40)
    # pv_to_load не ушёл в минус, когда батарею наполняет генсет.
    assert float(res.sim.table["pv_to_load_kw"].min()) >= -1e-6


def test_lp_dg_charge_forbidden_by_default(tmp_path):
    """Без флага (дефолт, прежнее поведение) заряд только от солнца —
    солнца нет, пик не покрыть, hard честно неразрешим."""
    with pytest.raises(RuntimeError):
        optimize_sizing(_dg_batt_scenario(tmp_path, False),
                        write_outputs=False)


def test_rule_cycle_charging_beats_load_following(tmp_path):
    """Симулятор: нагрузка [150,150,40,150], генсет 100, батарея 100
    (старт полной, RTE=1). Load following: батарея опустела и стоит
    пустой -> недопоставка 100 kWh. Cycle charging: в час затишья
    генсет догружается и кладёт 60 kWh в батарею -> недопоставка 50."""
    csv = tmp_path / "cc.csv"
    csv.write_text(
        "timestamp,load_kw\n"
        "2026-01-01 00:00,150\n2026-01-01 01:00,150\n"
        "2026-01-01 02:00,40\n2026-01-01 03:00,150\n",
        encoding="utf-8",
    )
    data = {
        "name": "cc-toy",
        "site": {"name": "x", "latitude": 15.28, "longitude": 44.08,
                 "timezone": "Asia/Aden"},
        "battery": {
            "capex_usd_per_kwh": 100, "capex_usd_per_kw": 0,
            "om_usd_per_kwh_year": 0, "rte_fraction": 1.0,
            "soc_min_fraction": 0.0,
            "min_kwh": 100, "max_kwh": 100, "min_kw": 200, "max_kw": 200,
            "lifetime_years": 10,
        },
        "diesel": {
            "capex_usd_per_kw": 100, "om_usd_per_kw_year": 0,
            "fuel_cost_usd_per_kwh": 0.26,
            "min_kw": 100, "max_kw": 100, "lifetime_years": 10,
        },
        "load": {"profile_csv": str(csv)},
        "financial": {"discount_rate_fraction": 0.0, "project_years": 10,
                      "currency": "USD"},
        "reliability": {"mode": "hard"},
    }
    scenario = Scenario.model_validate(data)
    lf = run_simulation(scenario, write_outputs=False)
    cc = run_simulation(scenario, write_outputs=False,
                        strategy="cycle_charging")
    assert lf.manifest["totals_kwh"]["shortfall"] == pytest.approx(100)
    assert cc.manifest["totals_kwh"]["shortfall"] == pytest.approx(50)


def test_rule_unknown_strategy_rejected(tmp_path):
    scenario = _dg_batt_scenario(tmp_path, True)
    with pytest.raises(ValueError, match="стратег"):
        run_simulation(scenario, write_outputs=False, strategy="magic")


# ================= №6: эскалация топлива =================

def test_fuel_levelization_factor_hand():
    """r=0, e=5%, N=3: (1.05 + 1.1025 + 1.157625) / 3 = 1.103375."""
    assert fuel_levelization_factor(0.0, 0.05, 3) == pytest.approx(1.103375)
    # Без эскалации коэффициент — ровно 1 (прежнее поведение).
    assert fuel_levelization_factor(0.08, None, 20) == 1.0
    assert fuel_levelization_factor(0.08, 0.0, 20) == 1.0


def test_escalation_shifts_optimum_away_from_diesel():
    """Йемен: эскалация топлива 10%/год удорожает дизельный kWh ->
    оптимум сдвигается от генсета (дизельной энергии не больше,
    издержки выше)."""
    base_data = load_dict(SCENARIO_SIZING)
    base = optimize_sizing(Scenario.model_validate(base_data),
                           weather_csv=WEATHER_CSV, write_outputs=False)

    esc_data = load_dict(SCENARIO_SIZING)
    esc_data["diesel"]["fuel_escalation_fraction"] = 0.10
    esc = optimize_sizing(Scenario.model_validate(esc_data),
                          weather_csv=WEATHER_CSV, write_outputs=False)

    assert (esc.sim.manifest["objective_value"]
            > base.sim.manifest["objective_value"])
    assert (esc.sim.manifest["totals_kwh"]["dg"]
            <= base.sim.manifest["totals_kwh"]["dg"] + 1e-6)


def test_economics_applies_levelized_fuel():
    """Дизель-онли, ставка 0, N=10, эскалация 5%: топливо года ровно
    в LF раз дороже плоского (LF при r=0 — среднее (1+e)^y)."""
    data = load_dict(SCENARIO_VENDOR)
    del data["pv"]
    del data["battery"]
    data["diesel"] = {
        "capex_usd_per_kw": 100, "om_usd_per_kw_year": 10,
        "fuel_cost_usd_per_kwh": 0.26,
        "fuel_escalation_fraction": 0.05,
        "min_kw": 100, "max_kw": 100, "lifetime_years": 10,
    }
    data["load"] = {"day_kw": 100, "night_kw": 100,
                    "work_start_hour": 8, "work_end_hour": 18}
    data["financial"] = {"discount_rate_fraction": 0.0,
                         "project_years": 10, "currency": "USD"}
    scenario = Scenario.model_validate(data)
    sim = run_simulation(scenario, write_outputs=False)
    eco = compute_economics(scenario, sim)
    lf = fuel_levelization_factor(0.0, 0.05, 10)
    assert eco.fuel_usd_per_year == pytest.approx(876_000 * 0.26 * lf)


# ================= №3: P90-множитель солнца =================

def test_solar_resource_scale_fraction():
    """Множитель 0.95 масштабирует ВЕСЬ удельный ряд линейно."""
    data = load_dict(SCENARIO_VENDOR)
    base = build_solar_profile(Scenario.model_validate(data),
                               weather_csv=WEATHER_CSV)
    data["pv"]["resource_scale_fraction"] = 0.95
    scaled = build_solar_profile(Scenario.model_validate(data),
                                 weather_csv=WEATHER_CSV)
    assert scaled.sum() == pytest.approx(0.95 * base.sum(), rel=1e-9)
    assert (scaled - 0.95 * base).abs().max() < 1e-12


def test_p90_sizing_is_more_conservative():
    """P90 (солнца меньше) не может сделать систему дешевле: издержки
    оптимума не ниже, чем на P50."""
    base = optimize_sizing(
        Scenario.model_validate(load_dict(SCENARIO_SIZING)),
        weather_csv=WEATHER_CSV, write_outputs=False)
    data = load_dict(SCENARIO_SIZING)
    data["pv"]["resource_scale_fraction"] = 0.95
    p90 = optimize_sizing(Scenario.model_validate(data),
                          weather_csv=WEATHER_CSV, write_outputs=False)
    assert (p90.sim.manifest["objective_value"]
            >= base.sim.manifest["objective_value"] - 1e-6)


# ============ аудит №3: вес доли года (annualisation weight) ============

def test_milp_objective_scales_capital_to_horizon(tmp_path):
    """MILP, 3 часа [80,150,60], генсеты по 100 кВт, min-загрузка 0.5,
    холостой ход 5 л/ч, ставка 0. Ручной оптимум:
      установлено 2 юнита -> капитал+O&M за год (0.1*100+10)*200 = 4000,
      доля горизонта 4000*3/8760 = 1.369863;
      топливо 290 кВт*ч * 0.27 = 78.3; холостой ход 4 юнито-часа * 5 л
      * $1 = 20; objective = 99.669863."""
    from src.optimize import optimize_sizing_milp
    csv = tmp_path / "aw_milp.csv"
    csv.write_text(
        "timestamp,load_kw\n"
        "2026-01-01 00:00,80\n2026-01-01 01:00,150\n2026-01-01 02:00,60\n",
        encoding="utf-8",
    )
    scenario = Scenario.model_validate({
        "name": "aw-milp",
        "site": {"name": "x", "latitude": 15.28, "longitude": 44.08,
                 "timezone": "Asia/Aden"},
        "diesel": {"capex_usd_per_kw": 100, "om_usd_per_kw_year": 10,
                   "fuel_price_usd_per_liter": 1.0,
                   "fuel_liters_per_kwh": 0.27,
                   "fuel_idle_liters_per_hour": 5.0,
                   "min_turn_down_fraction": 0.5,
                   "min_kw": 0, "max_kw": 400, "unit_kw": 100,
                   "lifetime_years": 10},
        "load": {"profile_csv": str(csv)},
        "financial": {"discount_rate_fraction": 0.0, "project_years": 10,
                      "currency": "USD"},
        "reliability": {"mode": "hard"},
    })
    res = optimize_sizing_milp(scenario, write_outputs=False)
    expected = 4000 * 3 / 8760 + 290 * 0.27 + 4 * 5 * 1.0
    assert res.sim.manifest["objective_value"] == pytest.approx(
        expected, rel=1e-4)


def test_year_fraction_is_one_for_full_year():
    """Полный год: вес = 1, объектив = прежний годовой (совместимость).
    Проверяем через сверку с экономикой: объектив сайзера на замороженном
    решении равен CRF*CAPEX + O&M + топливо (микроштраф в допуске)."""
    data = load_dict(SCENARIO_SIZING)
    res = optimize_sizing(Scenario.model_validate(data),
                          weather_csv=WEATHER_CSV, write_outputs=False)
    eco = compute_economics(Scenario.model_validate(data), res.sim)
    assert res.sim.manifest["objective_value"] == pytest.approx(
        eco.annual_cost_usd, rel=1e-3)


# ============ аудит №3: C-rate связь мощности и ёмкости ============

def test_c_rate_max_couples_power_to_energy():
    """Йемен: без связи оптимум берёт ~0.32 кВт на кВт*ч; c_rate_max=0.25
    (батарея не быстрее 4 часов) обязан прижать мощность к 0.25*ёмкость."""
    data = load_dict(SCENARIO_SIZING)
    data["battery"]["c_rate_max"] = 0.25
    res = optimize_sizing(Scenario.model_validate(data),
                          weather_csv=WEATHER_CSV, write_outputs=False)
    ratio = res.sizes["batt_kw"] / res.sizes["batt_kwh"]
    assert ratio <= 0.25 + 1e-6
    assert res.sim.manifest["totals_kwh"]["shortfall"] == pytest.approx(0)


def test_c_rate_min_enforced():
    """c_rate_min=0.5: мощность не ниже половины ёмкости в час."""
    data = load_dict(SCENARIO_SIZING)
    data["battery"]["c_rate_min"] = 0.5
    res = optimize_sizing(Scenario.model_validate(data),
                          weather_csv=WEATHER_CSV, write_outputs=False)
    assert (res.sizes["batt_kw"]
            >= 0.5 * res.sizes["batt_kwh"] - 1e-6)


def test_c_rate_bad_pair_rejected_by_schema():
    data = load_dict(SCENARIO_SIZING)
    data["battery"]["c_rate_min"] = 0.5
    data["battery"]["c_rate_max"] = 0.25
    with pytest.raises(Exception, match="c_rate"):
        Scenario.model_validate(data)


# ============ аудит №3: деградация PV (левелизация выработки) ============

def test_production_levelization_factor_hand():
    """r=0, d=50%, N=2: (1 + 0.5) / 2 = 0.75; d=0 -> ровно 1."""
    from src.economics import production_levelization_factor
    assert production_levelization_factor(0.0, 0.5, 2) == pytest.approx(0.75)
    assert production_levelization_factor(0.08, None, 25) == 1.0
    assert production_levelization_factor(0.08, 0.0, 25) == 1.0


def test_pv_degradation_scales_profile():
    """Деградация 0.5%/год: весь ряд умножен на LF (r=8%, жизнь 25 лет),
    LF строго меньше 1."""
    from src.economics import production_levelization_factor
    data = load_dict(SCENARIO_VENDOR)
    base = build_solar_profile(Scenario.model_validate(data),
                               weather_csv=WEATHER_CSV)
    data["pv"]["degradation_fraction_per_year"] = 0.005
    deg = build_solar_profile(Scenario.model_validate(data),
                              weather_csv=WEATHER_CSV)
    lf = production_levelization_factor(0.08, 0.005, 25)
    assert lf < 1.0
    assert deg.sum() == pytest.approx(lf * base.sum(), rel=1e-9)


# ============ аудит №3: цена углерода в целевой функции ============

def test_co2_price_enters_objective(tmp_path):
    """Дизель-онли, фиксированный размер: добавка к объективу равна
    ровно цена/т * кг/кВт*ч * кВт*ч / 1000 (потоки не меняются —
    другого источника нет)."""
    csv = tmp_path / "co2.csv"
    csv.write_text(
        "timestamp,load_kw\n"
        "2026-01-01 00:00,100\n2026-01-01 01:00,150\n2026-01-01 02:00,120\n",
        encoding="utf-8",
    )

    def scen(price):
        fin = {"discount_rate_fraction": 0.0, "project_years": 10,
               "currency": "USD"}
        if price:
            fin["co2_price_usd_per_ton"] = price
        return Scenario.model_validate({
            "name": "co2-toy",
            "site": {"name": "x", "latitude": 15.28, "longitude": 44.08,
                     "timezone": "Asia/Aden"},
            "diesel": {"capex_usd_per_kw": 100, "om_usd_per_kw_year": 10,
                       "fuel_cost_usd_per_kwh": 0.26,
                       "co2_kg_per_kwh": 0.7,
                       "min_kw": 150, "max_kw": 150, "lifetime_years": 10},
            "load": {"profile_csv": str(csv)},
            "financial": fin,
            "reliability": {"mode": "hard"},
        })

    base = optimize_sizing(scen(None), write_outputs=False)
    priced = optimize_sizing(scen(100.0), write_outputs=False)
    delta = (priced.sim.manifest["objective_value"]
             - base.sim.manifest["objective_value"])
    # 370 кВт*ч * 0.7 кг * $100/т / 1000 = $25.9
    assert delta == pytest.approx(25.9, rel=1e-6)


def test_co2_price_in_economics_report(tmp_path):
    """Экономический отчёт несёт ту же CO2-статью, что и целевая."""
    csv = tmp_path / "co2e.csv"
    csv.write_text(
        "timestamp,load_kw\n"
        "2026-01-01 00:00,100\n2026-01-01 01:00,100\n",
        encoding="utf-8",
    )
    data = {
        "name": "co2-eco",
        "site": {"name": "x", "latitude": 15.28, "longitude": 44.08,
                 "timezone": "Asia/Aden"},
        "diesel": {"capex_usd_per_kw": 100, "om_usd_per_kw_year": 10,
                   "fuel_cost_usd_per_kwh": 0.26, "co2_kg_per_kwh": 0.7,
                   "min_kw": 100, "max_kw": 100, "lifetime_years": 10},
        "load": {"profile_csv": str(csv)},
        "financial": {"discount_rate_fraction": 0.0, "project_years": 10,
                      "currency": "USD", "co2_price_usd_per_ton": 50.0},
        "reliability": {"mode": "hard"},
    }
    scenario = Scenario.model_validate(data)
    sim = run_simulation(scenario, write_outputs=False)
    eco = compute_economics(scenario, sim)
    # 200 кВт*ч * 0.7 кг * $50/т / 1000 = $7
    assert eco.co2_usd_per_year == pytest.approx(7.0)
    assert eco.annual_cost_usd == pytest.approx(
        eco.annualized_capex_usd + eco.om_usd_per_year
        + eco.fuel_usd_per_year + 7.0)
