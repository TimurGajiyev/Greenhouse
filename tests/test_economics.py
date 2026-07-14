"""Тесты экономики (src/economics.py). Версия v0.5 (шаг 6).

Контрольные числа посчитаны руками (см. комментарии) — тесты
сверяют код с бумагой, а не код с кодом.
"""

import json

import pytest

from src.schema import Scenario
from src.simulate import run_simulation
from src.economics import capital_recovery_factor, compute_economics

SCENARIO_PATH = "scenarios/yemen_vendor.json"
WEATHER_CSV = "tests/data/tmy_sanaa_pvgis_sarah3.csv"


def yemen_dict() -> dict:
    with open(SCENARIO_PATH, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def yemen_run():
    """Один прогон Йемена на весь файл тестов (scope='module'):
    симуляция детерминирована, гонять её в каждом тесте — трата времени."""
    scenario = Scenario.model_validate(yemen_dict())
    sim = run_simulation(scenario, weather_csv=WEATHER_CSV, write_outputs=False)
    return scenario, sim


# ---------- CRF против ручного расчёта ----------

def test_crf_hand_calculation():
    """r=8%, n=10: 1.08^10 = 2.158925; CRF = 0.08*2.158925/1.158925
    = 0.1490295 (посчитано на бумаге)."""
    assert capital_recovery_factor(0.08, 10) == pytest.approx(0.1490295, abs=1e-7)


def test_crf_zero_rate_is_straight_line():
    """При r=0 аннуитет вырождается в равные доли: CRF = 1/n."""
    assert capital_recovery_factor(0.0, 25) == pytest.approx(1 / 25)


def test_crf_rejects_bad_years():
    with pytest.raises(ValueError):
        capital_recovery_factor(0.08, 0)


# ---------- вырожденный кейс: одна технология, простые числа ----------

def test_lcoe_degenerate_diesel_only():
    """Дизель-онли, ставка 0, простые числа — всё сверяемо на бумаге:
      нагрузка 100 kW круглый год = 876 000 kWh;
      CAPEX 100 $/kW * 100 kW = 10 000; CRF(0,10) = 0.1 -> 1 000/год;
      O&M 10 $/kW = 1 000/год; топливо 0.26 * 876 000 = 227 760/год;
      итого 229 760/год; LCOE = 229 760 / 876 000 = 0.262283;
      NPC = 229 760 * 10 = 2 297 600.
    Окупаемости нет: дизель против дизельной базовой линии экономит
    отрицательные деньги (добавились CAPEX и O&M)."""
    data = yemen_dict()
    del data["pv"]
    del data["battery"]
    data["diesel"] = {
        "capex_usd_per_kw": 100, "om_usd_per_kw_year": 10,
        "fuel_cost_usd_per_kwh": 0.26,
        "min_kw": 100, "max_kw": 100, "lifetime_years": 10,
    }
    data["load"] = {"day_kw": 100, "night_kw": 100,
                    "work_start_hour": 8, "work_end_hour": 18}
    data["financial"] = {"discount_rate_fraction": 0.0,
                         "project_years": 10, "currency": "USD"}
    scenario = Scenario.model_validate(data)
    sim = run_simulation(scenario, write_outputs=False)
    eco = compute_economics(scenario, sim)

    assert eco.capex_total_usd == 10_000
    assert eco.annual_cost_usd == pytest.approx(229_760)
    assert eco.lcoe_usd_per_kwh == pytest.approx(229_760 / 876_000)
    assert eco.npc_usd == pytest.approx(2_297_600)
    assert eco.simple_payback_years is None


# ---------- согласованность единиц: Δt из данных ----------

def test_fuel_cost_respects_timestep():
    """Суточный CSV (Δt=24): энергия дизеля 2845 kW-суток * 24 ч =
    68 280 kWh -> топливо 17 752.8 $. Если бы код молча считал
    'шаг = час', вышло бы в 24 раза меньше."""
    data = yemen_dict()
    del data["pv"]
    del data["battery"]
    data["load"] = {"profile_csv": "tests/data/sample_load_daily.csv"}
    scenario = Scenario.model_validate(data)
    sim = run_simulation(scenario, write_outputs=False)
    eco = compute_economics(scenario, sim)
    assert eco.fuel_usd_per_year == pytest.approx(68_280 * 0.26)


# ---------- Йемен: полные числа ----------

def test_yemen_capex_exact(yemen_run):
    """CAPEX сверен с бумагой: PV 398*1500=597 000;
    BESS 196*3132+0*1500=613 872; DG 307*1000=307 000;
    итого 1 517 872."""
    scenario, sim = yemen_run
    eco = compute_economics(scenario, sim)
    assert eco.by_tech["pv"].capex_usd == 597_000
    assert eco.by_tech["battery"].capex_usd == 613_872
    assert eco.by_tech["diesel"].capex_usd == 307_000
    assert eco.capex_total_usd == 1_517_872


def test_yemen_annualized_capex(yemen_run):
    """Годовой эквивалент капитала (руками):
    PV: CRF(8%,25)=0.093679 * 597 000 = 55 926;
    BESS: CRF(8%,10)=0.149029 * 613 872 = 91 485;
    DG: CRF(8%,20)=0.101852 * 307 000 = 31 269; итого ~178 680."""
    scenario, sim = yemen_run
    eco = compute_economics(scenario, sim)
    assert eco.annualized_capex_usd == pytest.approx(178_680, rel=1e-3)


def test_yemen_npc_identity(yemen_run):
    """NPC == годовые издержки / CRF(ставка, горизонт) — identity,
    связывающая наш NPC с pwf REopt."""
    scenario, sim = yemen_run
    eco = compute_economics(scenario, sim)
    crf_project = capital_recovery_factor(0.08, 10)
    assert eco.npc_usd == pytest.approx(eco.annual_cost_usd / crf_project)


def test_yemen_payback_plausible(yemen_run):
    """Окупаемость против '100% дизель' — окрестность 2.8 года
    (снимок при текущем солнечном профиле; изменится профиль —
    осознанно обновить)."""
    scenario, sim = yemen_run
    eco = compute_economics(scenario, sim)
    assert eco.simple_payback_years == pytest.approx(2.82, abs=0.1)
