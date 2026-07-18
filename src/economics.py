"""Экономика GreenHouse: CRF, годовые издержки, NPC, LCOE, payback.
Версия v0.5 (шаг 6).

Зачем модуль: симулятор (шаг 5) отвечает "сколько kWh и откуда",
этот слой переводит потоки в деньги и отвечает "почём".

Ключевая формула — CRF (capital recovery factor, коэффициент
возврата капитала):

    CRF(r, n) = r * (1+r)^n / ((1+r)^n - 1)

Смысл: превращает разовую покупку (CAPEX) в n РАВНЫХ годовых
платежей с учётом ставки дисконтирования r — как аннуитетный платёж
по ипотеке. Зачем "размазывать": солнечные панели живут 25 лет, а
дизель мы заправляем каждый год — сравнивать их лбами нельзя, пока
капитальные затраты не приведены к тем же годовым единицам, что и
топливо. При r=0 формула вырождается в честное CRF = 1/n.

Допущения v1 (все — сознательные, обсуждены в аудите):
  1. CRF считается ПО СРОКУ ЖИЗНИ каждой технологии (PV — 25 лет,
     BESS — 10, DG — 20), а не по горизонту проекта. Следствия:
     замены внутри горизонта не моделируются; остаточная стоимость
     (salvage) техники, переживающей проект, учтена неявно — техника
     "оплачивает" только годы своей жизни. REopt делает иначе (NPV
     с заменами и salvage) — для v1 наш способ проще и прозрачен.
  2. Топливо — плоские $/kWh (без кривой частичной загрузки).
  3. Базовая линия для окупаемости — "100% дизель": вся нагрузка
     по цене дизельного kWh, без CAPEX генераторов (у завода дизель
     уже есть — сравниваем только операционные деньги).

Связь с REopt: их off-grid LCOE = lcc / pwf / LoadMet
(src/results/financial.jl), где lcc/pwf — годовой эквивалент
жизненного цикла. Наши формулы дают то же:
  NPC = annual_cost / CRF(r, project_years)   (pwf == 1/CRF)
  LCOE = annual_cost / annual_served_kwh
"""

from dataclasses import dataclass

from src.schema import Scenario
from src.simulate import SimulationResult

# ASSUMPTION: цена дизельного kWh для БАЗОВОЙ линии, когда в сценарии
# нет блока diesel (например PV+BESS): $0.26/kWh из вендорского PDF.
# При наличии блока берётся его fuel_cost_usd_per_kwh.
BASELINE_DIESEL_USD_PER_KWH = 0.26

# ASSUMPTION: выбросы дизель-генерации ~0.72 кг CO2/kWh (2.68 кг/л *
# ~0.27 л/кВт*ч) — дефолт для цены углерода; переопределяется полем
# diesel.co2_kg_per_kwh. Та же цифра в optimize.py и app.py.
DIESEL_CO2_KG_PER_KWH = 0.72


@dataclass(frozen=True)
class TechEconomics:
    """Экономика одной технологии: капитал и его годовой эквивалент."""

    capex_usd: float            # разовая покупка
    crf: float                  # коэффициент возврата капитала
    annualized_capex_usd: float  # CRF * CAPEX — годовая "аренда" капитала
    om_usd_per_year: float      # эксплуатация и обслуживание


@dataclass(frozen=True)
class EconomicsReport:
    """Итоговая экономика системы. Все деньги — USD (инвариант 4)."""

    by_tech: dict[str, TechEconomics]  # разбивка: pv / battery / diesel
    capex_total_usd: float
    annualized_capex_usd: float
    om_usd_per_year: float
    fuel_usd_per_year: float
    co2_usd_per_year: float      # цена углерода (0, если не задана)
    annual_cost_usd: float       # CRF*CAPEX + O&M + топливо + CO2
    npc_usd: float               # Net Present Cost за горизонт проекта
    lcoe_usd_per_kwh: float | None   # None, если энергия не поставлялась
    baseline_usd_per_year: float     # "100% дизель" — годовая стоимость
    simple_payback_years: float | None  # None = не окупается


def capital_recovery_factor(rate: float, years: int) -> float:
    """CRF(r, n) — вторая публичная функция модуля (как timestep_hours
    в profiles): она нужна и оптимизатору шага 8 как коэффициент
    целевой функции."""
    if years <= 0:
        raise ValueError(f"CRF: срок должен быть положительным, получен {years}")
    if rate == 0:
        return 1.0 / years  # предел формулы при r -> 0
    growth = (1 + rate) ** years
    return rate * growth / (growth - 1)


def fuel_levelization_factor(
    rate: float, escalation: float | None, years: int
) -> float:
    """Левелизационный коэффициент эскалации топлива (аудит №2, изъян №6).

    Во сколько раз ПОСТОЯННАЯ (левелизованная) цена топлива выше цены
    года 1, если реальная цена растёт на escalation в год, а деньги
    дисконтируются по rate. Та же роль, что pwf_fuel/pwf у REopt:
    одно число, посчитанное заранее, — и LP остаётся линейным.

        LF = Σ_y ((1+e)/(1+r))^y / Σ_y (1/(1+r))^y,  y = 1..N

    escalation=None или 0 -> 1.0 (плоская цена, прежнее поведение).
    """
    if years <= 0:
        raise ValueError(f"LF: срок должен быть положительным, получен {years}")
    e = escalation or 0.0
    if e == 0.0:
        return 1.0
    pv_escalated = sum(((1 + e) / (1 + rate)) ** y for y in range(1, years + 1))
    pv_flat = sum((1 / (1 + rate)) ** y for y in range(1, years + 1))
    return pv_escalated / pv_flat


def production_levelization_factor(
    rate: float, degradation: float | None, years: int
) -> float:
    """Левелизационный коэффициент деградации выработки (аудит №3).

    Средняя за жизнь дисконтированная выработка относительно года 1 при
    деградации d в год (REopt utils.jl:54, levelization_factor при
    нулевой эскалации; деградация начинается со 2-го года):

        LF = Σ_y (1-d)^(y-1) / (1+r)^y  /  Σ_y 1/(1+r)^y,  y = 1..N

    degradation=None или 0 -> 1.0 (техника вечно новая — прежнее
    поведение). Множитель применяется к солнечному ряду (solar.py).
    """
    if years <= 0:
        raise ValueError(f"LF: срок должен быть положительным, получен {years}")
    d = degradation or 0.0
    if d == 0.0:
        return 1.0
    num = sum((1 - d) ** (y - 1) / (1 + rate) ** y for y in range(1, years + 1))
    den = sum(1 / (1 + rate) ** y for y in range(1, years + 1))
    return num / den


def _resolve_sizes(scenario: Scenario, sim_result: SimulationResult) -> dict:
    """Установленные размеры для денег (аудит №2, изъян №1).

    Приоритет: решённые размеры из manifest["sizes"] (их пишет сайзер).
    Их нет (rule-симуляция, LP-диспетчер) — берём сценарий, но ТОЛЬКО
    если коридор заморожен (min == max): считать CAPEX по потолку
    открытого коридора — молчаливое завышение в разы (проверено: x5.3
    на йеменском сценарии). Открытый коридор без решённых размеров —
    громкая ошибка, а не тихий мусор.
    """
    solved = sim_result.manifest.get("sizes")

    def pick(key: str, lo: float, hi: float, label: str) -> float:
        if solved is not None:
            return float(solved[key])
        if abs(hi - lo) > 1e-9 * max(1.0, abs(hi)):
            raise ValueError(
                f"Economics: у {label} открыт коридор [{lo}, {hi}], а в "
                "manifest нет решённых размеров. Считать деньги по потолку "
                "коридора нельзя — сначала зафиксируй размеры (min == max) "
                "или передай результат сайзера."
            )
        return hi

    sizes = {"pv_kw": 0.0, "batt_kwh": 0.0, "batt_kw": 0.0, "dg_kw": 0.0}
    if scenario.pv is not None:
        sizes["pv_kw"] = pick(
            "pv_kwp", scenario.pv.min_kw, scenario.pv.max_kw, "PV")
    if scenario.battery is not None:
        b = scenario.battery
        sizes["batt_kwh"] = pick("batt_kwh", b.min_kwh, b.max_kwh, "Battery")
        sizes["batt_kw"] = pick("batt_kw", b.min_kw, b.max_kw, "Battery PCS")
    if scenario.diesel is not None:
        sizes["dg_kw"] = pick(
            "dg_kw", scenario.diesel.min_kw, scenario.diesel.max_kw, "Diesel")
    return sizes


def compute_economics(
    scenario: Scenario, sim_result: SimulationResult
) -> EconomicsReport:
    """Считает экономику по сценарию и результату симуляции."""
    rate = scenario.financial.discount_rate_fraction
    totals = sim_result.manifest["totals_kwh"]

    # 0) Размеры: решённые из manifest, иначе замороженный сценарий
    #    (открытый коридор без решения — ошибка, см. _resolve_sizes).
    sizes = _resolve_sizes(scenario, sim_result)

    # 1) Капитал и O&M по технологиям (отсутствующая технология просто
    #    не попадает в словарь — суммы по пустому множеству дают 0).
    by_tech: dict[str, TechEconomics] = {}

    if scenario.pv is not None:
        by_tech["pv"] = _tech_economics(
            capex=scenario.pv.capex_usd_per_kw * sizes["pv_kw"],
            om=scenario.pv.om_usd_per_kw_year * sizes["pv_kw"],
            rate=rate,
            lifetime=scenario.pv.lifetime_years,
        )
    if scenario.battery is not None:
        b = scenario.battery
        by_tech["battery"] = _tech_economics(
            # У батареи два ценника: ячейки ($/kWh) и PCS ($/kW).
            capex=(b.capex_usd_per_kwh * sizes["batt_kwh"]
                   + b.capex_usd_per_kw * sizes["batt_kw"]),
            om=b.om_usd_per_kwh_year * sizes["batt_kwh"],
            rate=rate,
            lifetime=b.lifetime_years,
        )
    if scenario.diesel is not None:
        by_tech["diesel"] = _tech_economics(
            capex=scenario.diesel.capex_usd_per_kw * sizes["dg_kw"],
            om=scenario.diesel.om_usd_per_kw_year * sizes["dg_kw"],
            rate=rate,
            lifetime=scenario.diesel.lifetime_years,
        )

    capex_total = sum(t.capex_usd for t in by_tech.values())
    annualized_capex = sum(t.annualized_capex_usd for t in by_tech.values())
    om_year = sum(t.om_usd_per_year for t in by_tech.values())

    # 2) Топливо: kWh дизеля (энергия уже с учётом Δt — из manifest)
    #    умножить на цену. Нет дизеля — честный ноль. Эскалация цены
    #    (изъян №6): и наше топливо, и базовая линия «100% дизель»
    #    берутся по ЛЕВЕЛИЗОВАННОЙ цене — плоская цена на 20 лет
    #    занижала будущие OPEX дизеля и смещала оптимум к генсету.
    lf = fuel_levelization_factor(
        rate,
        scenario.diesel.fuel_escalation_fraction if scenario.diesel else None,
        scenario.financial.project_years,
    )
    fuel_price = (
        scenario.diesel.fuel_cost_usd_per_kwh
        if scenario.diesel is not None
        else BASELINE_DIESEL_USD_PER_KWH
    ) * lf
    fuel_year = totals["dg"] * (
        scenario.diesel.fuel_cost_usd_per_kwh * lf if scenario.diesel else 0.0
    )

    # 2б) Цена углерода (аудит №3): статья появляется, только если
    #     сценарий задал co2_price_usd_per_ton — согласована со
    #     слагаемым в целевой функции оптимизатора.
    co2_year = 0.0
    if (scenario.diesel is not None
            and scenario.financial.co2_price_usd_per_ton):
        kg = scenario.diesel.co2_kg_per_kwh or DIESEL_CO2_KG_PER_KWH
        co2_year = (totals["dg"] * kg / 1000.0
                    * scenario.financial.co2_price_usd_per_ton)

    annual_cost = annualized_capex + om_year + fuel_year + co2_year

    # 3) NPC: годовые издержки, приведённые к сегодняшним деньгам за
    #    горизонт проекта. Деление на CRF(r, горизонт) — это умножение
    #    на present worth factor (pwf в REopt).
    npc = annual_cost / capital_recovery_factor(rate, scenario.financial.project_years)

    # 4) LCOE: доллар годовых издержек на kWh ПОСТАВЛЕННОЙ энергии
    #    (нагрузка минус недопоставка) — как LoadMet у REopt.
    served_kwh = totals["load"] - totals["shortfall"]
    lcoe = annual_cost / served_kwh if served_kwh > 0 else None

    # 5) Простая окупаемость против базовой линии "100% дизель":
    #    сколько лет экономия на операционных деньгах возвращает CAPEX.
    #    Дисконтирование в "простой" окупаемости не применяется —
    #    поэтому она и называется простой (и это её ограничение).
    baseline_year = totals["load"] * fuel_price
    savings_year = baseline_year - (om_year + fuel_year)
    payback = capex_total / savings_year if savings_year > 0 else None

    return EconomicsReport(
        by_tech=by_tech,
        capex_total_usd=capex_total,
        annualized_capex_usd=annualized_capex,
        om_usd_per_year=om_year,
        fuel_usd_per_year=fuel_year,
        co2_usd_per_year=co2_year,
        annual_cost_usd=annual_cost,
        npc_usd=npc,
        lcoe_usd_per_kwh=lcoe,
        baseline_usd_per_year=baseline_year,
        simple_payback_years=payback,
    )


# ---------- приватные помощники ----------


def _tech_economics(
    capex: float, om: float, rate: float, lifetime: int
) -> TechEconomics:
    """Экономика одной технологии: CRF по ЕЁ сроку жизни (допущение 1)."""
    crf = capital_recovery_factor(rate, lifetime)
    return TechEconomics(
        capex_usd=capex,
        crf=crf,
        annualized_capex_usd=crf * capex,
        om_usd_per_year=om,
    )
