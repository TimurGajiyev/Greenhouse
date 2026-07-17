"""GreenHouse — интерактивный интерфейс калькулятора (Streamlit).

Запуск из корня проекта (с активированным .venv):
    streamlit run app.py

Устройство (паттерн Calliope "scenario = base + overrides"): в сайдбаре
пользователь заполняет ФОРМУ переопределений; по кнопке «Пересчитать»
они накладываются на базовый JSON-сценарий, проходят те же
pydantic-ворота, что и файл, и уходят в тот же движок. Никакой
отдельной математики в UI нет — интерфейс показывает то, что считают
src/optimize.py, src/simulate.py, src/economics.py и src/sweep.py.

Двуязычие: переключатель RU/EN у заголовка. Русский — язык-источник,
переводы в app_i18n.py; переводятся ТОЛЬКО тексты (числа, единицы и
внутренние ключи данных остаются как есть).
"""

import copy
import datetime
import json
import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.schema import Scenario
from src.profiles import build_load_profile, timestep_hours
from src.solar import build_solar_profile
from src.simulate import run_simulation
from src.economics import capital_recovery_factor
from src.optimize import optimize_sizing, optimize_sizing_milp
from src.sweep import run_sensitivity
# app_i18n перезагружаем явно: Streamlit hot-reload обновляет только
# главный скрипт, а импортированные модули берёт из кэша sys.modules —
# без reload правки переводов не подхватываются до перезапуска сервера
# (и падают ImportError на новых символах).
import importlib
import app_i18n as _i18n
importlib.reload(_i18n)
make_t = _i18n.make_t
GLOSSARY_RU, GLOSSARY_EN = _i18n.GLOSSARY_RU, _i18n.GLOSSARY_EN
COLUMNS_HELP_RU, COLUMNS_HELP_EN = _i18n.COLUMNS_HELP_RU, _i18n.COLUMNS_HELP_EN

WEATHER = "tests/data/tmy_sanaa_pvgis_sarah3.csv"
BASE_SCENARIO = "scenarios/yemen_sizing.json"

# Цвета технологий — те же, что во всех графиках проекта.
C_PV, C_BESS, C_DG = "#eda100", "#1baf7a", "#e34948"
C_BLUE, C_BLUE_LIGHT = "#2a78d6", "#9ec5f4"

# ASSUMPTION: операционные выбросы дизель-генерации ~0.72 кг CO2/kWh
# (2.68 кг CO2/л * ~0.27 л/кВт*ч); встроенные выбросы железа не учтены.
CO2_KG_PER_DIESEL_KWH = 0.72

st.set_page_config(page_title="GreenHouse", layout="wide")


# ================= кэшируемые вычисления (всё считает ядро) =================
# Внутри кэш-функций текст НЕ переводится: они возвращают данные (ключи
# energy_mix — русские, служат ключами; перевод только при отрисовке).


def _materialize_load_csv(load_csv_text: str | None) -> str | None:
    """Загруженный CSV — во временный файл (ядро читает по пути)."""
    if load_csv_text is None:
        return None
    upload_path = Path("results") / "_ui_upload_load.csv"
    upload_path.parent.mkdir(exist_ok=True)
    upload_path.write_text(load_csv_text, encoding="utf-8")
    return str(upload_path)


def _apply_load(data: dict, load_csv_text: str | None) -> dict:
    data = copy.deepcopy(data)
    path = _materialize_load_csv(load_csv_text)
    if path is not None:
        data["load"] = {"profile_csv": path}
    return data


@st.cache_data(show_spinner="LP...")
def run_sizing_cached(scenario_json: str, load_csv_text: str | None,
                      cyclic_soc: bool, milp: bool = False):
    """Сайзер: сценарий -> размеры, штуки, метрики, ряды для графиков.

    milp=True — MILP-режим (целые машины + стадирование парка + холостой
    ход дизеля); медленнее LP, зато честная физика. LP — быстрый дефолт.
    """
    data = _apply_load(json.loads(scenario_json), load_csv_text)
    scenario = Scenario.model_validate(data)
    if milp:
        res = optimize_sizing_milp(scenario, weather_csv=WEATHER,
                                   write_outputs=False, cyclic_soc=cyclic_soc)
    else:
        res = optimize_sizing(scenario, weather_csv=WEATHER, write_outputs=False,
                              cyclic_soc=cyclic_soc)
    m, tbl = res.sim.manifest, res.sim.table

    load_kwh = m["totals_kwh"]["load"]
    served = load_kwh - m["totals_kwh"]["shortfall"]
    fuel_price = data.get("diesel", {}).get("fuel_cost_usd_per_kwh", 0.0)
    metrics = {
        "annual_cost_usd": m["objective_value"],
        "lcoe_usd_per_kwh": m["objective_value"] / served if served else None,
        "renewable_fraction": 1 - m["totals_kwh"]["dg"] / served if served else None,
        "dg_kwh": m["totals_kwh"]["dg"],
        "fuel_usd": m["totals_kwh"]["dg"] * fuel_price,
        "co2_tons": m["totals_kwh"]["dg"] * CO2_KG_PER_DIESEL_KWH / 1000,
        "lpsp": m["lpsp"],
        "load_kwh": load_kwh,
        "served_kwh": served,
        "curtail_kwh": m["totals_kwh"]["curtail"],
        "pv_gen_kwh": m["totals_kwh"]["pv_gen"],
        "solve_seconds": m["solve_seconds"],
        # Сводка стадирования парка (только в MILP-режиме; иначе None).
        "staging": m.get("diesel_staging"),
    }
    # Ключи energy_mix — русские и служат ЛИНКАМИ (используются ниже как
    # ключи lookup); переводятся только при отрисовке.
    energy_mix = {
        "Солнце напрямую": float(tbl["pv_to_load_kw"].sum() * m["timestep_hours"]),
        "Солнце через батарею": float(tbl["discharge_kw"].sum() * m["timestep_hours"]),
        "Дизель": float(tbl["dg_kw"].sum() * m["timestep_hours"]),
    }
    week_df = tbl.loc["2026-02-16":"2026-02-22"]
    week = {
        "pv": week_df["pv_to_load_kw"].tolist(),
        "bess": week_df["discharge_kw"].tolist(),
        "dg": week_df["dg_kw"].tolist(),
        "load": week_df["load_kw"].tolist(),
        "soc": week_df["soc_kwh"].tolist(),
    } if len(week_df) else None
    # Помесячный разрез поставки (kWh за месяц по источникам) — сезонный
    # взгляд для клиента: в месяцы слабого солнца дизельный слой толще.
    # Только числовые колонки: в таблице есть и строковые (run_id).
    monthly_df = (tbl[["pv_to_load_kw", "discharge_kw", "dg_kw"]]
                  .resample("MS").sum() * m["timestep_hours"])
    monthly = {
        "labels": [int(ts.month) for ts in monthly_df.index],
        "pv": monthly_df["pv_to_load_kw"].tolist(),
        "bess": monthly_df["discharge_kw"].tolist(),
        "dg": monthly_df["dg_kw"].tolist(),
    } if len(monthly_df) >= 2 else None
    return res.sizes, res.units, metrics, energy_mix, week, monthly


@st.cache_data(show_spinner="profiles...")
def profiles_cached(scenario_json: str, load_csv_text: str | None):
    """Ряды для вкладки «Ресурсы»: нагрузка 48 ч, солнце (сутки/месяцы)."""
    data = _apply_load(json.loads(scenario_json), load_csv_text)
    scenario = Scenario.model_validate(data)

    load = build_load_profile(scenario)
    dt = timestep_hours(load)

    solar = build_solar_profile(scenario, weather_csv=WEATHER)
    daily = solar.resample("D").sum()
    best_day = str(daily.idxmax().date())
    return {
        "load_48": load.iloc[:48].tolist(),
        "dt": dt,
        "load_year_kwh": float(load.sum() * dt),
        "solar_annual": float(solar.sum()),
        "best_day": best_day,
        "best_curve": solar[best_day].tolist(),
        "june_curve": solar["2026-06-15"].tolist(),
        "monthly": solar.resample("MS").sum().round(1).tolist(),
    }


@st.cache_data(show_spinner="rule...")
def rule_check_cached(scenario_json: str, load_csv_text: str | None,
                      sizes_json: str):
    """Perfect-foresight проверка: оптимальные размеры фиксируются
    (min = max) и прогоняются через слепой rule-симулятор без предвидения."""
    data = _apply_load(json.loads(scenario_json), load_csv_text)
    sizes = json.loads(sizes_json)
    if data.get("pv"):
        data["pv"]["min_kw"] = data["pv"]["max_kw"] = max(sizes["pv_kwp"], 0.001)
    if data.get("battery"):
        data["battery"]["min_kwh"] = data["battery"]["max_kwh"] = max(
            sizes["batt_kwh"], 0.001)
        data["battery"]["min_kw"] = data["battery"]["max_kw"] = max(
            sizes["batt_kw"], 0.001)
    if data.get("diesel"):
        data["diesel"]["min_kw"] = data["diesel"]["max_kw"] = max(
            sizes["dg_kw"], 0.001)
    scenario = Scenario.model_validate(data)
    sim = run_simulation(scenario, weather_csv=WEATHER, write_outputs=False)
    return sim.manifest["totals_kwh"], sim.manifest["lpsp"]


@st.cache_data(show_spinner="sensitivity...")
def sensitivity_cached(scenario_json: str, load_csv_text: str | None):
    data = _apply_load(json.loads(scenario_json), load_csv_text)
    scenario = Scenario.model_validate(data)
    rep = run_sensitivity(scenario, weather_csv=WEATHER, write_outputs=False)
    return (rep.fuel_price, rep.bess_capex, rep.pv_capex,
            rep.pareto, rep.knee, rep.stress)


def tab_footer(text_ru: str) -> None:
    """Пояснение в конце вкладки: что на ней происходит и зачем."""
    st.divider()
    st.markdown(f"**{T('Что здесь происходит и зачем.')}** {T(text_ru)}")


def legend_help(text_ru: str) -> None:
    """Подпись «как читать легенду» сразу под графиком."""
    st.caption(f"{T('Как читать:')} {T(text_ru)}")


def econ_breakdown(data: dict, sizes: dict, metrics: dict) -> dict:
    """Экономика оптимума: те же формулы, что в src/economics.py,
    приложенные к размерам сайзера (CRF по сроку жизни технологии).
    Имена статей — русские ключи; переводятся при отрисовке."""
    rate = data["financial"]["discount_rate_fraction"]
    years = data["financial"]["project_years"]
    items, capex_total, om_total = [], 0.0, 0.0

    if data.get("pv"):
        p = data["pv"]
        capex = p["capex_usd_per_kw"] * sizes["pv_kwp"]
        crf = capital_recovery_factor(rate, p["lifetime_years"])
        items.append(("капитал PV", crf * capex, C_PV))
        capex_total += capex
        om_total += p["om_usd_per_kw_year"] * sizes["pv_kwp"]
    if data.get("battery"):
        b = data["battery"]
        capex = (b["capex_usd_per_kwh"] * sizes["batt_kwh"]
                 + b["capex_usd_per_kw"] * sizes["batt_kw"])
        crf = capital_recovery_factor(rate, b["lifetime_years"])
        items.append(("капитал BESS", crf * capex, C_BESS))
        capex_total += capex
        om_total += b["om_usd_per_kwh_year"] * sizes["batt_kwh"]
    if data.get("diesel"):
        d = data["diesel"]
        capex = d["capex_usd_per_kw"] * sizes["dg_kw"]
        crf = capital_recovery_factor(rate, d["lifetime_years"])
        items.append(("капитал DG", crf * capex, C_DG))
        capex_total += capex
        om_total += d["om_usd_per_kw_year"] * sizes["dg_kw"]

    items.append(("O&M", om_total, "#898781"))
    items.append(("топливо", metrics["fuel_usd"], "#b91f1f"))
    annual = sum(v for _, v, _ in items)

    baseline = metrics["load_kwh"] * data.get("diesel", {}).get(
        "fuel_cost_usd_per_kwh", 0.26)
    savings = baseline - (om_total + metrics["fuel_usd"])
    return {
        "items": items,
        "annual": annual,
        "capex_total": capex_total,
        "npc": annual / capital_recovery_factor(rate, years),
        "baseline": baseline,
        # Живые деньги года (без CRF-аннуитета) — для кривой накопленных
        # затрат: закупка платится один раз, дальше только O&M + топливо.
        "opex": om_total + metrics["fuel_usd"],
        "savings": savings,
        "payback": capex_total / savings if savings > 0 else None,
    }


def bom_rows(data, sizes, units, metrics, energy_mix) -> list[dict]:
    """Bill of materials — «что заказать» по компонентам (как в HOMER/REopt).

    На каждый компонент: физический юнит, число штук (ceil от непрерывного
    оптимума), номинал юнита, УСТАНОВЛЕННАЯ мощность/ёмкость (штук × юнит,
    её и покупают), цена юнита, CAPEX строки, годовой O&M и годовая
    энергия. Имена — русские ключи (переводятся при отрисовке)."""
    rows: list[dict] = []

    def add(comp, equip, unit_size, unit_txt, qty, cont, price_per,
            capex_per, om_per, om_base, output):
        # Установленное = штук × номинал юнита (то, что реально покупаешь).
        installed = (qty * unit_size) if qty is not None else cont
        rows.append({
            "comp": comp, "equip": equip,
            "unit": f"{unit_size:g} {unit_txt}",
            "qty": qty,
            "installed": f"{installed:,.0f} {unit_txt}",
            "optimal": f"{cont:,.1f} {unit_txt}",
            "unit_price": unit_size * price_per,
            "capex": (qty * unit_size if qty is not None else cont) * capex_per,
            "om": (qty * unit_size if qty is not None else cont) * om_base * om_per,
            "output": output,
        })

    if data.get("pv") and sizes.get("pv_kwp", 0) > 0:
        p = data["pv"]
        add("Солнечные панели (PV)", "PV-панель", p.get("unit_kw", 1), "kWp",
            units.get("pv_panels"), sizes["pv_kwp"],
            p["capex_usd_per_kw"], p["capex_usd_per_kw"], p["om_usd_per_kw_year"],
            1.0, metrics.get("pv_gen_kwh"))
    if data.get("battery") and sizes.get("batt_kwh", 0) > 0:
        b = data["battery"]
        add("Накопитель — ёмкость (BESS)", "Батарейный шкаф",
            b.get("unit_kwh", 1), "kWh", units.get("batt_cabinets"),
            sizes["batt_kwh"], b["capex_usd_per_kwh"], b["capex_usd_per_kwh"],
            b["om_usd_per_kwh_year"], 1.0,
            energy_mix.get("Солнце через батарею"))
        add("Накопитель — мощность (PCS)", "Инвертор PCS",
            b.get("unit_kw", 1), "kW", units.get("batt_pcs_units"),
            sizes["batt_kw"], b["capex_usd_per_kw"], b["capex_usd_per_kw"],
            0.0, 0.0, None)
    if data.get("diesel") and sizes.get("dg_kw", 0) > 0:
        d = data["diesel"]
        add("Дизель-генератор (DG)", "Дизель-генератор", d.get("unit_kw", 1),
            "kW", units.get("dg_gensets"), sizes["dg_kw"],
            d["capex_usd_per_kw"], d["capex_usd_per_kw"], d["om_usd_per_kw_year"],
            1.0, energy_mix.get("Дизель"))
    return rows


def build_html_report(data, sizes, units, metrics, energy_mix, eco, figs,
                      tr) -> str:
    """Самодостаточный HTML-отчёт для отправки заказчику (язык — tr)."""
    fig_html = ""
    for i, fig in enumerate(figs):
        fig_html += fig.to_html(full_html=False,
                                include_plotlyjs=("cdn" if i == 0 else False))
    bom = bom_rows(data, sizes, units, metrics, energy_mix)
    rows_spec = "".join(
        f"<tr><td>{tr(r['comp'])}</td><td>{tr(r['equip'])}</td>"
        f"<td>{'—' if r['qty'] is None else int(r['qty'])}</td>"
        f"<td>{r['unit']}</td><td>{r['installed']}</td>"
        f"<td>${r['unit_price']:,.0f}</td><td>${r['capex']:,.0f}</td></tr>"
        for r in bom)
    bom_capex = sum(r["capex"] for r in bom)
    rows_eco = "".join(f"<tr><td>{tr(n)}</td><td>${v:,.0f}/yr</td></tr>"
                       for n, v, _ in eco["items"])
    payback = (tr("{} лет").format(f"{eco['payback']:.1f}")
               if eco["payback"] else tr("нет"))
    return f"""<!doctype html><html><head><meta charset="utf-8">
<title>GreenHouse — {tr('Оптимальная конфигурация')}</title>
<style>body{{font-family:system-ui,sans-serif;max-width:960px;margin:2em auto;
padding:0 1em;color:#0b0b0b}}table{{border-collapse:collapse;margin:1em 0}}
td,th{{border:1px solid #ddd;padding:6px 12px}}h1,h2{{color:#1a4f8b}}
.metric{{display:inline-block;margin:0 2em 1em 0}}
.metric b{{font-size:1.4em;display:block}}</style></head><body>
<h1>GreenHouse — {tr('Оптимальная конфигурация')}</h1>
<p>{tr('Имя сценария')}: {data.get('name', '')} ·
{datetime.date.today().isoformat()}</p>
<div>
<span class="metric"><b>${metrics['annual_cost_usd']:,.0f}</b>{tr('Годовые издержки')}</span>
<span class="metric"><b>${metrics['lcoe_usd_per_kwh']:.4f}</b>LCOE, $/kWh</span>
<span class="metric"><b>{metrics['renewable_fraction']:.1%}</b>{tr('Renewable')}</span>
<span class="metric"><b>{metrics['co2_tons']:,.0f} t</b>CO₂</span>
<span class="metric"><b>{metrics['lpsp']:.2%}</b>LPSP</span>
</div>
<h2>{tr('Спецификация закупки (bill of materials)')}</h2>
<table><tr><th>{tr('Компонент')}</th><th>{tr('Что заказать')}</th>
<th>{tr('Кол-во, шт')}</th><th>{tr('Номинал юнита')}</th>
<th>{tr('Установлено')}</th><th>{tr('Цена/юнит, $')}</th>
<th>{tr('CAPEX, $')}</th></tr>{rows_spec}
<tr><td><b>{tr('ИТОГО')}</b></td><td></td><td></td><td></td><td></td><td></td>
<td><b>${bom_capex:,.0f}</b></td></tr></table>
<h2>{tr('Годовые издержки')}: ${eco['annual']:,.0f}</h2>
<table><tr><th></th><th>$/yr</th></tr>{rows_eco}</table>
<p>CAPEX ${eco['capex_total']:,.0f} · NPC ${eco['npc']:,.0f} ·
{tr('Окупаемость')} {payback}</p>
<h2></h2>{fig_html}
<hr><p><i>{tr('DISCLAIMER')}</i></p></body></html>"""


# ============================ сайдбар: язык + форма ============================

st.sidebar.title("GreenHouse")
# Переключатель языка — сразу под заголовком; при смене весь скрипт
# перерисовывается на выбранном языке (t читает актуальный выбор).
lang = st.sidebar.segmented_control(
    "Язык / Language", ["RU", "EN"], default="RU", key="lang",
    label_visibility="collapsed")
if lang is None:
    lang = "RU"
T = make_t(lang)
# Оговорка для HTML-отчёта — на текущем языке (без ключа в общем словаре).
DISCLAIMER = {
    "RU": "Модель — инструмент понимания и проверки вендорских предложений, "
          "НЕ замена лицензированному инженеру для финального проектирования.",
    "EN": "The model is a tool for understanding and checking vendor "
          "proposals, NOT a replacement for a licensed engineer for final "
          "design.",
}[lang]


def T2(s):
    """t() с подстраховкой для DISCLAIMER (нет в общем словаре)."""
    return DISCLAIMER if s == "DISCLAIMER" else T(s)


st.sidebar.caption(T(
    "Заполни параметры и нажми «Пересчитать» — они наложатся "
    "на базовый сценарий, и калькулятор найдёт новый оптимум. "
    "Единицы: kW / kWh / USD."))

with open(BASE_SCENARIO, encoding="utf-8") as f:
    base = json.load(f)

# Источник нагрузки — ВНЕ формы: переключатель мгновенно перерисовывает
# сайдбар, и загрузчик CSV показывается только в своём режиме. Опции —
# стабильные ключи ("synthetic"/"csv"), подписи через format_func: логика
# не зависит от языка отображения.
st.sidebar.subheader(T("Нагрузка"))
load_mode = st.sidebar.radio(
    T("Источник профиля"), ["synthetic", "csv"],
    format_func=lambda k: T("Синтетический (Йемен)") if k == "synthetic"
    else T("CSV-файл"),
    help=T("Профиль нагрузки — ряд «сколько kW потребляет завод в каждый "
           "час». CSV: колонки timestamp,load_kw; равномерный шаг; 2026 год."))
uploaded = None
day_kw = int(base["load"]["day_kw"])
night_kw = int(base["load"]["night_kw"])
if load_mode == "csv":
    uploaded = st.sidebar.file_uploader(
        T("CSV (используется в режиме «CSV-файл»)"), type="csv")

with st.sidebar.form("params"):
    if load_mode != "csv":
        day_kw = st.slider(
            T("Дневная нагрузка, kW"), 100, 2000, day_kw, 50,
            help=T("Мощность (kW) в рабочие часы смены 08–18; kW — СКОРОСТЬ "
                   "потребления, энергия за час = kW × 1 ч. Для синтетики."))
        night_kw = st.slider(
            T("Ночная база, kW"), 0, 500, night_kw, 10,
            help=T("Дежурная мощность вне смены: охрана, холодильники, "
                   "серверная."))

    st.subheader(T("Цены"))
    pv_capex = st.slider(
        T("CAPEX PV, $/kW"), 200, 800, int(base["pv"]["capex_usd_per_kw"]), 10,
        help=T("Разовые капитальные затраты на 1 kWp панелей "
               "(купить + смонтировать)."))
    bess_capex = st.slider(
        T("CAPEX BESS, $/kWh"), 80, 400,
        int(base["battery"]["capex_usd_per_kwh"]), 5,
        help=T("Цена 1 kWh ёмкости накопителя (LFP-шкафы). kWh — сколько "
               "батарея ХРАНИТ; kW — как быстро отдаёт."))
    # Топливо дизеля — как у профи (REopt: цена за галлон × расход;
    # Calliope: cost_flow_in): фундаментальный вход — ЦЕНА ЛИТРА, а
    # $/кВт*ч выводится = цена_литра × удельный_расход.
    fuel_price_l = st.slider(
        T("Цена дизеля, $/литр"), 0.30, 2.50, 0.96, 0.01,
        help=T("Цена одного литра дизтоплива на площадке (с доставкой). "
               "Фундаментальный вход у REopt/HOMER; $/кВт*ч выводится из "
               "неё и удельного расхода. Tornado показывает: самый "
               "влиятельный параметр модели."))
    fuel_l_per_kwh = st.slider(
        T("Удельный расход, л/кВт*ч"), 0.20, 0.40, 0.27, 0.01,
        help=T("Сколько литров сжигает генсет на 1 кВт*ч на номинале "
               "(datasheet). Типовой дизель ~0.27. Холостой ход "
               "учитывается в режиме точного расчёта парка (ниже)."))
    st.caption(T("→ эффективно ${}/кВт*ч дизеля").format(
        f"{fuel_price_l * fuel_l_per_kwh:.3f}"))

    st.subheader(T("PV-модуль и инвертор (datasheet)"))
    inv_eff = st.slider(
        T("КПД инвертора"), 0.90, 0.99, 0.96, 0.005,
        help=T("Номинальный КПД DC→AC. Дефолт 0.96 (REopt/PVWatts); "
               "в datasheet вендора обычно 0.95–0.985."))
    gamma_pct = st.slider(
        T("Темп. коэффициент, %/°C"), -0.60, -0.20, -0.47, 0.01,
        help=T("Потеря мощности на каждый °C нагрева ячейки выше 25 °C. "
               "Стандартный кремний −0.47; N-type TOPCon ~−0.30."))
    dc_ac = st.slider(
        T("DC/AC (панели к инвертору)"), 1.0, 1.5, 1.2, 0.05,
        help=T("Панелей ставят больше номинала инвертора: пики редки, "
               "инвертор дорог; излишек срезается (clipping)."))
    mount = st.selectbox(
        T("Монтаж панелей"), ["close_mount", "open_rack"],
        format_func=lambda k: T("close_mount (вплотную к крыше)")
        if k == "close_mount" else T("open_rack (на раме / земле)"),
        help=T("Влияет на температуру ячейки: на раме панели охлаждаются "
               "лучше (+1–2% выработки). Кейс NIST показал значимость."))

    st.subheader(T("Батарея и площадка"))
    rte = st.slider(
        T("RTE батареи"), 0.70, 0.98, float(base["battery"]["rte_fraction"]),
        0.01,
        help=T("КПД полного цикла «зарядил-разрядил»: из 100 kWh при 0.85 "
               "обратно выйдет 85. В модели η заряда = η разряда = √RTE."))
    roof = st.slider(
        T("Площадь под PV, м²"), 1000, 20000,
        int(base["site"]["roof_area_m2"]), 500,
        help=T("Потолок сайзера: pv_kWp × 5 м²/kWp ≤ площадь."))

    st.subheader(T("Коридоры поиска (максимумы)"))
    max_pv = st.slider(
        T("Макс. PV, kWp"), 500, 8000, int(base["pv"]["max_kw"]), 100,
        help=T("Верхняя граница поиска для солнца (нижняя 0). Итоговый "
               "потолок — минимум из этого и площади."))
    max_bess = st.slider(
        T("Макс. BESS, kWh"), 1000, 30000, int(base["battery"]["max_kwh"]),
        500, help=T("Верхняя граница поиска ёмкости накопителя."))
    max_dg = st.slider(
        T("Макс. DG, kW"), 500, 4000, int(base["diesel"]["max_kw"]), 100,
        help=T("Верхняя граница поиска дизеля. При политике hard она должна "
               "позволять покрыть пик — иначе честная ошибка «неразрешимо»."))

    st.subheader(T("Надёжность"))
    rel_mode = st.selectbox(
        T("Политика"), ["hard", "lpsp", "voll"],
        format_func=lambda k: {
            "hard": T("hard — недопоставка запрещена"),
            "lpsp": T("lpsp — допустимая доля недопоставки"),
            "voll": T("voll — недопоставка платная")}[k],
        help=T("hard: каждый kWh спроса покрыт. lpsp: недопоставка не выше "
               "заданной доли. voll: модель сама решает, что дешевле — "
               "поставить или заплатить штраф за тьму."))
    lpsp_max_pct = st.slider(
        T("LPSP-цель, % (для режима lpsp)"), 0.1, 10.0, 1.0, 0.1,
        help=T("Допустимая доля годового спроса без поставки; "
               "1% ≈ 87 часов простоя в год."))
    voll = st.number_input(
        T("VOLL, $/kWh (для режима voll)"), 0.1, 20.0, 1.0, 0.1,
        help=T("Value of lost load — цена недопоставленного kWh для "
               "потребителя (простой производства). Дефолт REopt: $1."))
    reserve_load_pct = st.slider(
        T("Оперативный резерв, % нагрузки"), 0, 50, 0, 5,
        help=T("Горячий запас мощности сверх нагрузки в КАЖДЫЙ час: "
               "недогруженный дизель + доступный разряд батареи. Страхует "
               "реальную работу от сюрпризов и закрывает разрыв между "
               "идеальным планом и реальностью. 0 = выключено."))
    reserve_pv_pct = st.slider(
        T("Резерв на PV, %"), 0, 50, 0, 5,
        help=T("Дополнительный резерв, привязанный к выработке солнца: "
               "облако роняет PV — запас страхует. Панель сама резерв не "
               "даёт (она и есть источник неопределённости)."))
    cyclic = st.checkbox(
        T("Циклический SOC (годовое кольцо)"), value=True,
        help=T("Запас батареи в конце года «перетекает» в его начало "
               "(паттерн Calliope) — без бесплатной стартовой заправки. "
               "Выключи для сравнения с REopt-стилем (старт с полной)."))

    st.subheader(T("Точный расчёт парка (целые машины)"))
    milp_on = st.checkbox(
        T("Целые машины + стадирование дизеля (медленнее)"), value=False,
        help=T("Размеры кратны юниту (целые панели/шкафы/генсеты), а "
               "дизельный парк включается по часам — «сколько генсетов "
               "работает сейчас» — с минимальной загрузкой и холостым "
               "ходом. Честнее физика, но расчёт заметно дольше."))
    turndown_pct = st.slider(
        T("Мин. загрузка генсета, %"), 0, 60, 30, 5,
        help=T("Включённый генсет не опускается ниже этой доли номинала "
               "(типично 15–30% у автономных систем). Работает только в "
               "точном расчёте парка."))
    idle_lph = st.slider(
        T("Холостой ход, л/ч на генсет"), 0.0, 30.0, 0.0, 1.0,
        help=T("Постоянный расход топлива работающего генсета сверх "
               "нагрузки. Стоит денег даже вхолостую — модель гасит "
               "лишние генсеты. 0 = не моделировать. Работает только в "
               "точном расчёте парка."))

    submitted = st.form_submit_button(T("Пересчитать"), type="primary",
                                      width="stretch")

if st.sidebar.button(T("Зафиксировать текущий как базу")):
    st.session_state.pop("baseline", None)  # пересоздастся после расчёта

with st.sidebar.expander(T("Словарь терминов")):
    st.markdown(GLOSSARY_EN if lang == "EN" else GLOSSARY_RU)

# --- сборка сценария: base + overrides из формы ---
data = copy.deepcopy(base)
load_csv_text = None
if load_mode == "csv" and uploaded is not None:
    load_csv_text = uploaded.getvalue().decode("utf-8")
else:
    data["load"]["day_kw"] = day_kw
    data["load"]["night_kw"] = night_kw
data["pv"]["capex_usd_per_kw"] = pv_capex
data["pv"]["max_kw"] = max_pv
data["pv"]["inverter_eff_fraction"] = inv_eff
data["pv"]["gamma_pdc_per_c"] = round(gamma_pct / 100, 5)
data["pv"]["dc_ac_ratio"] = dc_ac
data["pv"]["mount_type"] = mount  # стабильный ключ, не подпись
data["battery"]["capex_usd_per_kwh"] = bess_capex
data["battery"]["rte_fraction"] = rte
data["battery"]["max_kwh"] = max_bess
# Эффективные $/кВт*ч = цена литра × удельный расход. Пишем и цену
# литра/расход (для BOM/KPI), и производный $/кВт*ч (им считают деньги
# все слои, и его же качает tornado-свип).
eff_fuel_usd_per_kwh = round(fuel_price_l * fuel_l_per_kwh, 4)
data["diesel"]["fuel_price_usd_per_liter"] = fuel_price_l
data["diesel"]["fuel_liters_per_kwh"] = fuel_l_per_kwh
data["diesel"]["fuel_cost_usd_per_kwh"] = eff_fuel_usd_per_kwh
data["diesel"]["max_kw"] = max_dg
data["site"]["roof_area_m2"] = roof
data["reliability"] = (
    {"mode": "hard"} if rel_mode == "hard" else
    {"mode": "lpsp", "lpsp_max_fraction": lpsp_max_pct / 100} if
    rel_mode == "lpsp" else
    {"mode": "voll", "voll_usd_per_kwh": voll}
)
# Оперативный резерв — необязательная надстройка поверх любого режима.
if reserve_load_pct:
    data["reliability"]["operating_reserve_load_fraction"] = reserve_load_pct / 100
if reserve_pv_pct:
    data["reliability"]["operating_reserve_pv_fraction"] = reserve_pv_pct / 100
# Параметры дизеля для MILP-режима (в LP-режиме игнорируются оптимизатором).
if milp_on and data.get("diesel"):
    if turndown_pct:
        data["diesel"]["min_turn_down_fraction"] = turndown_pct / 100
    if idle_lph:
        data["diesel"]["fuel_idle_liters_per_hour"] = idle_lph
scenario_json = json.dumps(data, sort_keys=True)

# ============================ запуск ядра ============================

try:
    sizes, units, metrics, energy_mix, week, monthly = run_sizing_cached(
        scenario_json, load_csv_text, cyclic, milp_on)
except RuntimeError as e:
    st.error(T("Оптимизация не удалась: {}").format(e))
    st.stop()
except Exception as e:
    st.error(T("Проблема с входными данными: {}").format(e))
    st.stop()

if "baseline" not in st.session_state:
    st.session_state.baseline = (dict(sizes), dict(metrics))
base_sizes, base_metrics = st.session_state.baseline

# ============================ метрики ============================

st.title(T("Оптимальная конфигурация"))
st.caption(T("Стрелки у метрик — сравнение с зафиксированной базой "
             "(кнопка «Зафиксировать текущий как базу» в сайдбаре)"))
if metrics.get("staging"):
    s = metrics["staging"]
    st.caption(T("Парк генераторов: {} шт по {:g} kW · одновременно в работе "
                 "до {}, в среднем {} (точный расчёт целыми машинами)")
               .format(s["dg_units_installed"], s["dg_unit_kw"],
                       s["dg_units_on_max"], s["dg_units_on_mean"]))


def delta(cur, ref):
    if ref in (None, 0) or cur is None:
        return None
    return f"{(cur - ref) / abs(ref):+.1%}"


c1, c2, c3, c4, c5 = st.columns(5)
c1.metric(T("Годовые издержки"), f"${metrics['annual_cost_usd']:,.0f}",
          delta(metrics["annual_cost_usd"], base_metrics["annual_cost_usd"]),
          delta_color="inverse")
c2.metric("LCOE", f"${metrics['lcoe_usd_per_kwh']:.4f}/kWh",
          delta(metrics["lcoe_usd_per_kwh"], base_metrics["lcoe_usd_per_kwh"]),
          delta_color="inverse")
c3.metric(T("Renewable"), f"{metrics['renewable_fraction']:.1%}",
          delta(metrics["renewable_fraction"], base_metrics["renewable_fraction"]))
c4.metric(T("Дизель"), f"{metrics['dg_kwh']:,.0f} kWh",
          delta(metrics["dg_kwh"], base_metrics["dg_kwh"]), delta_color="inverse")
c5.metric(T("CO₂ (оценка*)"), f"{metrics['co2_tons']:,.0f} t/yr",
          delta(metrics["co2_tons"], base_metrics["co2_tons"]),
          delta_color="inverse")
st.caption(T("*Оценка: {} кг CO₂ на kWh дизеля · недопоставка (LPSP) = {} · "
             "сброс излишков солнца = {} kWh")
           .format(CO2_KG_PER_DIESEL_KWH, f"{metrics['lpsp']:.2%}",
                   f"{metrics['curtail_kwh']:,.0f}"))

(tab_cfg, tab_disp, tab_res, tab_eco, tab_rule,
 tab_sens, tab_scen, tab_valid) = st.tabs(
    [T("Конфигурация"), T("Диспетчеризация"), T("Ресурсы"), T("Экономика"),
     T("Проверка надёжности"), T("Риски и цены"), T("Сценарии"),
     T("Валидация")]
)

# ---------- конфигурация ----------

with tab_cfg:
    st.subheader(T("Спецификация закупки (bill of materials)"))
    _bom = bom_rows(data, sizes, units, metrics, energy_mix)
    _spec_rows = []
    for r in _bom:
        _spec_rows.append({
            T("Компонент"): T(r["comp"]),
            T("Что заказать"): T(r["equip"]),
            T("Кол-во, шт"): "—" if r["qty"] is None else str(int(r["qty"])),
            T("Номинал юнита"): r["unit"],
            T("Установлено"): r["installed"],
            T("Цена/юнит, $"): f"{r['unit_price']:,.0f}",
            T("CAPEX, $"): f"{r['capex']:,.0f}",
            T("O&M, $/год"): f"{r['om']:,.0f}",
            T("Производство, kWh/год"):
                "—" if r["output"] is None else f"{r['output']:,.0f}",
        })
    # Строка ИТОГО по CAPEX и O&M.
    _spec_rows.append({
        T("Компонент"): T("ИТОГО"), T("Что заказать"): "", T("Кол-во, шт"): "",
        T("Номинал юнита"): "", T("Установлено"): "",
        T("Цена/юнит, $"): "",
        T("CAPEX, $"): f"{sum(r['capex'] for r in _bom):,.0f}",
        T("O&M, $/год"): f"{sum(r['om'] for r in _bom):,.0f}",
        T("Производство, kWh/год"): "",
    })
    st.dataframe(pd.DataFrame(_spec_rows), hide_index=True, width="stretch")
    st.caption(T("Кол-во и «установлено» — сколько ЦЕЛЫХ юнитов купить "
                 "(оптимум, округлённый вверх до целых юнитов); подробно "
                 "о каждой колонке — в развороте ниже."))
    with st.expander(T("Что означает каждая колонка")):
        st.markdown(COLUMNS_HELP_EN if lang == "EN" else COLUMNS_HELP_RU)

    left, right = st.columns(2)

    fig_cap = go.Figure()
    names = ["PV, kWp", "BESS, kWh", "BESS, kW", "DG, kW"]
    keys = ["pv_kwp", "batt_kwh", "batt_kw", "dg_kw"]
    fig_cap.add_bar(y=names, x=[sizes[k] for k in keys],
                    name=T("текущее решение (эта форма)"),
                    orientation="h", marker_color=C_BLUE)
    fig_cap.add_bar(y=names, x=[base_sizes[k] for k in keys],
                    name=T("база (зафиксирована кнопкой)"),
                    orientation="h", marker_color=C_BLUE_LIGHT)
    fig_cap.update_layout(title=T("Размеры: текущее решение против базы"),
                          height=300,
                          margin=dict(l=10, r=10, t=40, b=10), barmode="group")
    left.plotly_chart(fig_cap, width="stretch")
    with left:
        legend_help("тёмная полоса — оптимум при текущих "
                    "параметрах формы; светлая — «база», которую ты "
                    "зафиксировал для сравнения. Разошлись — значит, твои "
                    "изменения передвинули оптимум.")

    fig_pie = go.Figure(go.Pie(
        labels=[T(l) for l in energy_mix], values=list(energy_mix.values()),
        marker=dict(colors=[C_PV, C_BESS, C_DG]), hole=0.5,
        texttemplate="%{label}<br>%{percent}",
    ))
    fig_pie.update_layout(title=T("Кто поставил энергию заводу за год"),
                          height=330, margin=dict(l=10, r=10, t=40, b=10))
    right.subheader(T("Энергобаланс года"))
    right.plotly_chart(fig_pie, width="stretch")
    with right:
        legend_help("жёлтое — солнце, ушедшее заводу сразу; "
                    "зелёное — то же солнце, но отложенное батареей на "
                    "вечер/ночь (минус потери цикла); красное — дизель. "
                    "Красный сектор растёт — система дрейфует от «солнце с "
                    "резервом» к «дизель с довеском».")

    # Sankey годового потока энергии — фирменный клиентский визуал
    # HOMER/REopt-отчётов: ширина ленты = энергия за год, видна вся дорога
    # от источника до завода, включая потери и сброс.
    pv_direct_y = energy_mix.get("Солнце напрямую", 0.0)
    via_batt_y = energy_mix.get("Солнце через батарею", 0.0)
    dg_year_y = energy_mix.get("Дизель", 0.0)
    curtail_y = metrics["curtail_kwh"]
    charge_y = max(metrics["pv_gen_kwh"] - pv_direct_y - curtail_y, 0.0)
    loss_y = max(charge_y - via_batt_y, 0.0)
    sankey_links = [
        (0, 3, pv_direct_y, "rgba(237,161,0,0.55)"),
        (0, 2, charge_y, "rgba(237,161,0,0.35)"),
        (0, 4, curtail_y, "rgba(160,160,160,0.45)"),
        (2, 3, via_batt_y, "rgba(27,175,122,0.55)"),
        (2, 5, loss_y, "rgba(160,160,160,0.45)"),
        (1, 3, dg_year_y, "rgba(227,73,72,0.55)"),
    ]
    sankey_links = [l for l in sankey_links if l[2] > 1e-6]
    if sankey_links:
        st.subheader(T("Потоки энергии за год"))
        fig_sk = go.Figure(go.Sankey(
            node=dict(
                label=[T("Солнце"), T("Дизель-генератор"), T("Батарея"),
                       T("Завод (нагрузка)"), T("Сброс излишков"),
                       T("Потери цикла")],
                pad=18, thickness=16,
                color=[C_PV, C_DG, C_BESS, "#555", "#999", "#999"]),
            link=dict(source=[l[0] for l in sankey_links],
                      target=[l[1] for l in sankey_links],
                      value=[round(l[2]) for l in sankey_links],
                      color=[l[3] for l in sankey_links]),
        ))
        fig_sk.update_layout(height=360, margin=dict(l=10, r=10, t=10, b=10))
        st.plotly_chart(fig_sk, width="stretch")
        legend_help("ширина каждой ленты пропорциональна энергии за год "
                    "(kWh). Видна вся дорога: сколько солнца ушло заводу "
                    "напрямую, сколько — через батарею (и что потерялось в "
                    "цикле), сколько добавил дизель и сколько излишков "
                    "пришлось сбросить.")

    st.subheader(T("Схема системы (AC-coupling, шина 400 В)"))
    fig_sch = go.Figure()
    boxes = [
        (0, f"PV<br>{sizes['pv_kwp']:,.0f} kWp<br>{units['pv_panels']} "
            f"{T('панелей')}", C_PV),
        (1, f"BESS<br>{sizes['batt_kwh']:,.0f} kWh / {sizes['batt_kw']:,.0f} kW"
            f"<br>{units['batt_cabinets']} {T('шкафов')}", C_BESS),
        (2, f"DG<br>{sizes['dg_kw']:,.0f} kW<br>{units['dg_gensets']} "
            f"{T('генсет')}", C_DG),
    ]
    for x, label, color in boxes:
        fig_sch.add_shape(type="rect", x0=x - 0.35, x1=x + 0.35, y0=1.2, y1=2.0,
                          line=dict(color=color, width=2), fillcolor=color,
                          opacity=0.15)
        fig_sch.add_annotation(x=x, y=1.6, text=label, showarrow=False)
        fig_sch.add_shape(type="line", x0=x, x1=x, y0=1.2, y1=0.7,
                          line=dict(color=color, width=3))
    fig_sch.add_shape(type="line", x0=-0.6, x1=2.6, y0=0.7, y1=0.7,
                      line=dict(color="#555", width=5))
    fig_sch.add_annotation(x=2.6, y=0.78, text=T("шина 400 В"), showarrow=False,
                           xanchor="right")
    fig_sch.add_shape(type="line", x0=1, x1=1, y0=0.7, y1=0.25,
                      line=dict(color="#555", width=3))
    fig_sch.add_shape(type="rect", x0=0.55, x1=1.45, y0=-0.25, y1=0.25,
                      line=dict(color="#555", width=2), fillcolor="#555",
                      opacity=0.08)
    fig_sch.add_annotation(x=1, y=0, text=T("Завод (нагрузка)"), showarrow=False)
    fig_sch.update_xaxes(visible=False, range=[-0.8, 2.8])
    fig_sch.update_yaxes(visible=False, range=[-0.4, 2.2])
    fig_sch.update_layout(height=330, margin=dict(l=10, r=10, t=10, b=10))
    st.plotly_chart(fig_sch, width="stretch")

    tab_footer(
        "Калькулятор перебрал все допустимые комбинации размеров и режимов "
        "работы за 8760 часов года и нашёл самую дешёвую, которая держит "
        "нагрузку при выбранной политике надёжности. Таблица переводит "
        "оптимум в целые единицы к закупке. Схема — топология AC-coupling: "
        "все источники параллельно на одной шине 400 В."
    )

# ---------- диспетчеризация ----------

with tab_disp:
    if week is None:
        st.info(T("Недельный график доступен для годового часового профиля."))
    else:
        x = list(range(len(week["load"])))
        fig_w = go.Figure()
        for key, name_ru, color in (
                ("pv", "солнце → завод (напрямую)", C_PV),
                ("bess", "батарея → завод (разряд запаса)", C_BESS),
                ("dg", "дизель → завод (резерв)", C_DG)):
            fig_w.add_scatter(x=x, y=week[key], name=T(name_ru),
                              stackgroup="mix", mode="none", fillcolor=color)
        fig_w.add_scatter(x=x, y=week["load"], name=T("нагрузка завода (спрос)"),
                          line=dict(color="#111", dash="dash", width=1.5))
        fig_w.update_layout(
            title=T("Неделя 16–22 февраля: кто кормит завод"),
            xaxis_title=T("часы недели"), yaxis_title="kW", height=380,
            legend=dict(orientation="h", y=1.14),
        )
        st.plotly_chart(fig_w, width="stretch")
        legend_help("три цветных слоя складываются (стек) и обязаны "
                    "дотягиваться до пунктирного спроса — любой зазор был бы "
                    "недопоставкой. Жёлтый низ — прямое солнце днём; зелёный "
                    "появляется вечером (батарея отдаёт дневной запас); "
                    "красный — предрассветные часы, когда батарея у пола.")

        fig_soc = go.Figure()
        fig_soc.add_scatter(x=x, y=week["soc"],
                            name=T("запас батареи (SOC), kWh"),
                            line=dict(color=C_BESS, width=2))
        fig_soc.add_hline(y=0.2 * sizes["batt_kwh"], line_dash="dot",
                          line_color=C_DG,
                          annotation_text=T("пол SOC (20% — бережём ресурс)"))
        fig_soc.add_hline(y=sizes["batt_kwh"], line_dash="dot",
                          line_color="#555",
                          annotation_text=T("ёмкость (потолок)"))
        fig_soc.update_layout(title=T("Запас батареи (SOC) в ту же неделю"),
                              xaxis_title=T("часы недели"), yaxis_title="kWh",
                              height=300)
        st.plotly_chart(fig_soc, width="stretch")
        legend_help("зелёная линия дышит сутками: днём вверх (заряд "
                    "солнечным избытком), вечером вниз. Пунктирные линии — "
                    "границы: ниже красной не разряжаем (ресурс ячеек), выше "
                    "серой физически некуда. Линия редко касается потолка — "
                    "батарея великовата; бьётся об пол каждую ночь — мала.")

    # Сезонный разрез: поставка по месяцам (стек по источникам) — стандарт
    # клиентских отчётов HOMER («monthly electric production»).
    if monthly is not None:
        fig_mm = go.Figure()
        for key, name_ru, color in (
                ("pv", "солнце → завод (напрямую)", C_PV),
                ("bess", "батарея → завод (разряд запаса)", C_BESS),
                ("dg", "дизель → завод (резерв)", C_DG)):
            fig_mm.add_bar(x=monthly["labels"], y=monthly[key],
                           name=T(name_ru), marker_color=color)
        fig_mm.update_layout(barmode="stack",
                             title=T("Кто кормит завод по месяцам"),
                             xaxis_title=T("месяц"), yaxis_title="kWh",
                             height=340, legend=dict(orientation="h", y=1.14))
        st.plotly_chart(fig_mm, width="stretch")
        legend_help("сезонный разрез года: в месяцы слабого солнца красный "
                    "слой (дизель) толще. Помогает планировать завоз топлива "
                    "по сезонам.")

    tab_footer(
        "Это «рентген» найденного решения на характерной неделе февраля. "
        "Именно по этим двум графикам мы поймали переразмеренность "
        "вендорской батареи: она наполнялась до потолка один день в году."
    )

# ---------- ресурсы ----------

with tab_res:
    prof = profiles_cached(scenario_json, load_csv_text)
    m1, m2, m3 = st.columns(3)
    m1.metric(T("Годовая выработка солнца"),
              f"{prof['solar_annual']:,.0f} kWh/kWp")
    m2.metric(T("Энергия нагрузки за год"),
              f"{prof['load_year_kwh']:,.0f} kWh")
    m3.metric(T("Шаг данных Δt"), f"{prof['dt']} h")

    colA, colB = st.columns(2)
    fig_l = go.Figure()
    fig_l.add_scatter(y=prof["load_48"], line_shape="hv",
                      name=T("спрос завода, kW"),
                      line=dict(color=C_BLUE, width=2))
    fig_l.update_layout(title=T("Нагрузка: первые двое суток"),
                        xaxis_title=T("час"), yaxis_title="kW", height=320)
    colA.plotly_chart(fig_l, width="stretch")
    with colA:
        legend_help("ступеньки — смена 08–18 на дневной мощности, "
                    "ночью — дежурная база. Это СПРОС, который система обязана "
                    "покрывать каждый час.")

    fig_s = go.Figure()
    fig_s.add_scatter(y=prof["best_curve"],
                      name=T("лучший день года ({})").format(prof["best_day"]),
                      line=dict(color=C_PV, width=2))
    fig_s.add_scatter(y=prof["june_curve"],
                      name=T("15 июня (облачный сезон)"),
                      line=dict(color=C_BESS, width=2))
    fig_s.update_layout(title=T("Солнце: типовые сутки, kW на 1 kWp"),
                        xaxis_title=T("час местного времени"),
                        yaxis_title="kW/kWp", height=320)
    colB.plotly_chart(fig_s, width="stretch")
    with colB:
        legend_help("обе кривые — «сколько даёт 1 kWp панелей». "
                    "Жёлтая — лучший день года (зимой!), зелёная — облачный "
                    "июнь. Итоговая выработка = эта кривая × размер PV.")

    fig_m = go.Figure(go.Bar(x=list(range(1, 13)), y=prof["monthly"],
                             marker_color=C_PV,
                             name=T("выработка за месяц, kWh/kWp")))
    fig_m.update_layout(title=T("Выработка по месяцам"),
                        xaxis_title=T("месяц"), yaxis_title="kWh/kWp",
                        height=300)
    st.plotly_chart(fig_m, width="stretch")
    legend_help("высота столбца — энергия месяца с 1 kWp. В Сане зима "
                "солнечнее лета (июльская облачность нагорья) — худший "
                "сезон солнца совпадает с круглогодичной нагрузкой, поэтому "
                "летом дизель работает больше.")

    tab_footer(
        "Это два входных ряда, из которых следует всё остальное: спрос "
        "(нагрузка по часам) и предложение (выработка 1 kWp из спутникового "
        "«типичного года» PVGIS через модель PVWatts). Любое странное число "
        "на других вкладках сначала проверяют здесь."
    )

# ---------- экономика ----------

with tab_eco:
    eco = econ_breakdown(data, sizes, metrics)
    e1, e2, e3, e4, e5 = st.columns(5)
    e1.metric(T("CAPEX (разово)"), f"${eco['capex_total']:,.0f}")
    e2.metric(T("NPC (за горизонт)"), f"${eco['npc']:,.0f}")
    e3.metric(T("База «100% дизель»"), f"${eco['baseline']:,.0f}/yr")
    e4.metric(T("Экономия против «100% дизель»"),
              f"${eco['savings']:,.0f}/yr")
    e5.metric(T("Окупаемость"),
              T("{} лет").format(f"{eco['payback']:.1f}") if eco["payback"]
              else T("нет"))

    fig_e = go.Figure()
    for name_ru, value, color in eco["items"]:
        fig_e.add_bar(y=[T(name_ru)], x=[value], orientation="h",
                      marker_color=color, showlegend=False,
                      text=f"${value:,.0f}", textposition="outside")
    fig_e.update_layout(
        title=T("Годовые издержки ${} — из чего складываются").format(
            f"{eco['annual']:,.0f}"),
        xaxis_title="$/yr", height=330,
        xaxis_range=[0, max(v for _, v, _ in eco["items"]) * 1.25],
    )
    st.plotly_chart(fig_e, width="stretch")
    legend_help("цвет полосы = технология (жёлтый PV, зелёный BESS, красный "
                "DG — как на всех графиках); серый — обслуживание всего "
                "железа, тёмно-красный — солярка. «Капитал X» — это CAPEX, "
                "размазанный формулой CRF в равные годовые платежи по сроку "
                "жизни технологии.")
    st.caption(T("Сверка: сумма статей совпадает с итогом оптимизации (${}) "
                 "— две независимые дороги к одному числу.")
               .format(f"{metrics['annual_cost_usd']:,.0f}"))

    # Кривая накопленных затрат — главный переговорный график: где линия
    # гибрида пересекает линию «жечь только дизель», там и окупаемость.
    years_ax = list(range(0, int(data["financial"]["project_years"]) + 1))
    fig_cf = go.Figure()
    fig_cf.add_scatter(x=years_ax, y=[eco["baseline"] * y for y in years_ax],
                       name=T("всё из дизеля (только топливо)"),
                       line=dict(color=C_DG, width=2, dash="dash"))
    fig_cf.add_scatter(x=years_ax,
                       y=[eco["capex_total"] + eco["opex"] * y
                          for y in years_ax],
                       name=T("гибрид (закупка + эксплуатация)"),
                       line=dict(color=C_BLUE, width=2))
    if eco["payback"] and eco["payback"] <= years_ax[-1]:
        fig_cf.add_vline(x=eco["payback"], line_dash="dot", line_color="#555",
                         annotation_text=T("окупаемость"))
    fig_cf.update_layout(title=T("Накопленные затраты по годам проекта"),
                         xaxis_title=T("год проекта"), yaxis_title="$",
                         height=340, legend=dict(orientation="h", y=1.12))
    st.plotly_chart(fig_cf, width="stretch")
    legend_help("красный пунктир — если продолжать жечь только дизель; "
                "синяя линия стартует выше (разовая закупка железа), но "
                "растёт медленнее (солнце бесплатное). Точка пересечения — "
                "окупаемость: дальше каждый год работает в плюс.")

    tab_footer(
        "Деньги системы в одном месте: CRF превращает разовые покупки в "
        "годовые платежи, NPC собирает все затраты горизонта в сегодняшних "
        "деньгах, окупаемость меряется против базовой линии «вся энергия из "
        "дизеля». У Йемена бюджет ест топливо — потому анализ на вкладке "
        "«Риски и цены» ставит цену солярки на первое место."
    )

# ---------- rule vs LP ----------

with tab_rule:
    st.markdown(T(
        "План оптимизатора «знает» весь год наперёд — реальный контроллер "
        "на площадке будущего не видит. Здесь найденные размеры проверяются "
        "пошаговым симулятором без предвидения — разница и есть запас "
        "прочности плана."))
    rule_totals, rule_lpsp = rule_check_cached(
        scenario_json, load_csv_text, json.dumps(sizes, sort_keys=True))

    r1, r2, r3 = st.columns(3)
    r1.metric(T("LPSP: идеальный план"), f"{metrics['lpsp']:.2%}")
    r2.metric(T("LPSP: реальная работа"), f"{rule_lpsp:.2%}",
              help=T("Больше нуля при политике hard — реальная работа без "
                     "предвидения иногда не дотягивает на размерах, ужатых "
                     "оптимизацией. Лечится оперативным резервом (ползунок "
                     "в сайдбаре)."))
    r3.metric(T("Недопоставка в реальной работе"),
              f"{rule_totals['shortfall']:,.0f} kWh")

    flows = ["dg", "discharge", "curtail", "shortfall"]
    flow_names = {"dg": "дизель", "discharge": "разряд батареи",
                  "curtail": "сброс солнца", "shortfall": "недопоставка"}
    lp_totals = {"dg": metrics["dg_kwh"], "curtail": metrics["curtail_kwh"],
                 "discharge": energy_mix["Солнце через батарею"],
                 "shortfall": metrics["load_kwh"] - metrics["served_kwh"]}
    fig_r = go.Figure()
    fig_r.add_bar(y=[T(flow_names[f]) for f in flows],
                  x=[lp_totals[f] for f in flows],
                  name=T("идеальный план (видит год наперёд)"),
                  orientation="h", marker_color=C_BLUE)
    fig_r.add_bar(y=[T(flow_names[f]) for f in flows],
                  x=[rule_totals[f] for f in flows],
                  name=T("реальная работа (без предвидения)"),
                  orientation="h", marker_color=C_BLUE_LIGHT)
    fig_r.update_layout(
        title=T("Годовые потоки: идеальный план против реальной работы"),
        xaxis_title=T("kWh за год"), height=340, barmode="group")
    st.plotly_chart(fig_r, width="stretch")
    legend_help("пары полос сравнивают одинаковые потоки НА ОДНИХ размерах "
                "железа. Тёмная — недостижимый идеал; светлая — "
                "приземлённая реальность. Смотри на «недопоставку»: если в "
                "реальной работе она больше нуля — добавь оперативный "
                "резерв (сайдбар) или инженерный запас.")

    tab_footer(
        "Проверка плана на честность: найденное решение — нижняя граница "
        "затрат. Практический смысл: к размеру дизеля стоит добавлять "
        "инженерный запас — вендоры делают именно это."
    )

# ---------- sensitivity ----------

with tab_sens:
    st.markdown(T(
        "Что будет с бюджетом при других ценах, почём каждая ступень "
        "надёжности и как план переживает плохие сценарии. Запускается по "
        "кнопке; результат сохраняется до изменения параметров."))
    if st.button(T("Запустить анализ рисков")) or \
            "sens_done" in st.session_state:
        st.session_state["sens_done"] = True
        fuel_df, bess_df, pv_df, pareto, knee, stress = sensitivity_cached(
            scenario_json, load_csv_text)

        base_cost = float(fuel_df.loc[fuel_df.value == 1.0,
                                      "annual_cost_usd"].iloc[0])
        rows = []
        for name_ru, df in (("Цена дизеля ±50%", fuel_df),
                            ("CAPEX BESS ±30%", bess_df),
                            ("CAPEX PV ±30%", pv_df)):
            if not df.empty:
                rows.append((name_ru, df.annual_cost_usd.min(),
                             df.annual_cost_usd.max()))
        rows.sort(key=lambda r: r[2] - r[1], reverse=True)

        fig_t = go.Figure()
        for name_ru, lo, hi in rows:
            fig_t.add_bar(y=[T(name_ru)], x=[base_cost - lo], base=lo,
                          orientation="h", marker_color=C_BLUE_LIGHT,
                          name=T("параметр дешевле базового → издержки падают "
                                 "до этой точки"),
                          showlegend=(name_ru == rows[0][0]))
            fig_t.add_bar(y=[T(name_ru)], x=[hi - base_cost], base=base_cost,
                          orientation="h", marker_color=C_BLUE,
                          name=T("параметр дороже базового → издержки растут "
                                 "до этой точки"),
                          showlegend=(name_ru == rows[0][0]))
        fig_t.add_vline(x=base_cost, line_dash="dash", line_color="#111")
        fig_t.update_layout(
            title=T("Что сильнее всего влияет на бюджет"),
            xaxis_title="$/yr", height=330, barmode="overlay",
            legend=dict(orientation="h", y=-0.35))
        st.plotly_chart(fig_t, width="stretch")
        legend_help("каждая строка — один параметр, качавшийся в своём "
                    "диапазоне; пунктир — издержки при исходных ценах. Чем "
                    "ДЛИННЕЕ полоса целиком, тем важнее уточнять прогноз "
                    "этого параметра до подписания контракта.")

        fig_p = go.Figure()
        pareto_sorted = pareto.sort_values("lpsp_target")
        fig_p.add_scatter(x=pareto_sorted.lpsp_target * 100,
                          y=pareto_sorted.annual_cost_usd,
                          mode="lines+markers",
                          name=T("граница возможного (дешевле при такой "
                                 "надёжности не бывает)"),
                          line=dict(color=C_BLUE, width=2))
        fig_p.add_scatter(x=[knee["lpsp"] * 100], y=[knee["annual_cost_usd"]],
                          mode="markers",
                          name=T("колено — разумный компромисс"),
                          marker=dict(size=16, symbol="circle-open",
                                      color=C_DG, line=dict(width=3)))
        fig_p.update_layout(title=T("Сколько стоит надёжность"),
                            xaxis_title=T("допустимая недопоставка (LPSP), %"),
                            yaxis_title="$/yr", height=360,
                            legend=dict(orientation="h", y=-0.3))
        st.plotly_chart(fig_p, width="stretch")
        legend_help("каждая точка — отдельная оптимизация с разрешённой "
                    "недопоставкой. Слева-вверху дорогая абсолютная "
                    "надёжность; вправо кривая быстро падает и — после "
                    "красного колена — почти выполаживается: дальнейшие "
                    "уступки дают копейки.")

        st.subheader(T("Стрессы оптимального дизайна"))
        st.dataframe(stress.round(4), hide_index=True, width="stretch")

    tab_footer(
        "Входные цены — прогнозы, и надо знать, какие опасно прогнозировать "
        "плохо, почём каждая «девятка» надёжности и как дизайн переживает "
        "плохие сценарии — песчаную бурю и недельный топливный разрыв "
        "(таблица стрессов: хороший дизайн деградирует на доли процента, "
        "а не катастрофой)."
    )

# ---------- сценарии ----------

with tab_scen:
    st.subheader(T("Отчёт и сохранение"))
    eco_now = econ_breakdown(data, sizes, metrics)
    # Отчёт для клиента: размеры, энергобаланс, окупаемость и типовая неделя.
    report_figs = [fig_cap, fig_pie, fig_cf]
    if week is not None:
        report_figs.append(fig_w)
    html_report = build_html_report(data, sizes, units, metrics, energy_mix,
                                    eco_now, report_figs, T2)
    rcol1, rcol2, rcol3 = st.columns(3)
    rcol1.download_button(T("Скачать отчёт (HTML)"), html_report,
                          file_name="greenhouse_report.html",
                          mime="text/html",
                          help=T("Самодостаточная страница: метрики, "
                                 "спецификация, издержки и графики — можно "
                                 "отправить письмом."))
    scenario_pack = json.dumps({
        "scenario": data, "sizes": sizes, "units": units, "metrics": metrics,
    }, ensure_ascii=False, indent=2)
    name = rcol2.text_input(T("Имя сценария"), value=T("мой вариант"),
                            label_visibility="collapsed",
                            placeholder=T("имя сценария"))
    rcol2.download_button(T("Скачать JSON"), scenario_pack,
                          file_name=f"greenhouse_{name}.json")
    if rcol3.button(T("Добавить в сравнение")):
        st.session_state.setdefault("saved", {})[name] = {
            "sizes": dict(sizes), "metrics": dict(metrics)}

    st.subheader(T("Загрузить сохранённый"))
    up = st.file_uploader("greenhouse_*.json", type="json", key="scen_up")
    if up is not None:
        pack = json.loads(up.getvalue().decode("utf-8"))
        st.session_state.setdefault("saved", {})[up.name] = {
            "sizes": pack["sizes"], "metrics": pack["metrics"]}
        st.success(T("Загружен {}").format(up.name))

    saved = st.session_state.get("saved", {})
    if saved:
        st.subheader(T("Сравнение сценариев"))
        all_runs = {**saved,
                    T("← текущий"): {"sizes": sizes, "metrics": metrics}}
        rows = []
        for nm, p in all_runs.items():
            rows.append({
                T("сценарий"): nm,
                "PV, kWp": round(p["sizes"]["pv_kwp"]),
                "BESS, kWh": round(p["sizes"]["batt_kwh"]),
                "DG, kW": round(p["sizes"]["dg_kw"]),
                T("изд., $/год"): round(p["metrics"]["annual_cost_usd"]),
                T("LCOE, $"): round(p["metrics"]["lcoe_usd_per_kwh"], 4),
                T("renewable"): f"{p['metrics']['renewable_fraction']:.1%}",
                T("CO₂, т"): round(p["metrics"]["co2_tons"]),
            })
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

        # Наложение сценариев: размеры и LCOE бок о бок.
        fig_ov = go.Figure()
        for nm, p in all_runs.items():
            fig_ov.add_bar(x=["PV, kWp", "BESS, kWh", "DG, kW"],
                           y=[p["sizes"]["pv_kwp"], p["sizes"]["batt_kwh"],
                              p["sizes"]["dg_kw"]],
                           name=nm)
        fig_ov.update_layout(title=T("Размеры оборудования по сценариям"),
                             yaxis_title="kW / kWh", height=340,
                             barmode="group")
        st.plotly_chart(fig_ov, width="stretch")

        fig_lc = go.Figure()
        fig_lc.add_bar(
            x=list(all_runs),
            y=[p["metrics"]["lcoe_usd_per_kwh"] for p in all_runs.values()],
            marker_color=C_BLUE, name="LCOE, $/kWh",
            text=[f"{p['metrics']['lcoe_usd_per_kwh']:.4f}"
                  for p in all_runs.values()],
            textposition="outside")
        fig_lc.update_layout(title=T("LCOE по сценариям"), height=300,
                             yaxis_title="$/kWh")
        st.plotly_chart(fig_lc, width="stretch")
        legend_help("каждая группа столбцов — один сценарий из таблицы выше "
                    "(имя в легенде). Так видно, как твои изменения "
                    "передвигают и размеры закупки, и цену киловатт-часа.")

    tab_footer(
        "Каждый вариант — самодостаточный пакет (входы + размеры + "
        "метрики): JSON — для архива и передачи, HTML-отчёт — для письма "
        "заказчику. Таблица и графики сравнения отвечают на главный "
        "переговорный вопрос: как меняются закупка и LCOE между вариантами."
    )

# ---------- валидация ----------

with tab_valid:
    st.markdown(T(
        "Сверка с внешним инструментом (REopt web / HOMER). Прогони тот же "
        "сценарий там, впиши их числа — отклонения **> 10%** будут "
        "помечены. Публичного API у HOMER нет, у REopt нужен ключ NREL — "
        "поэтому сверка идёт по введённым вручную числам, честно и "
        "прозрачно."))
    cc = st.columns(4)
    ref = {
        "PV, kWp": cc[0].number_input(T("PV референса, kWp"), value=0.0),
        "BESS, kWh": cc[1].number_input(T("BESS референса, kWh"), value=0.0),
        "DG, kW": cc[2].number_input(T("DG референса, kW"), value=0.0),
        "LCOE, $/kWh": cc[3].number_input(T("LCOE референса"), value=0.0,
                                          format="%.4f"),
    }
    ours = {
        "PV, kWp": sizes["pv_kwp"], "BESS, kWh": sizes["batt_kwh"],
        "DG, kW": sizes["dg_kw"], "LCOE, $/kWh": metrics["lcoe_usd_per_kwh"],
    }
    rows = []
    for k, rv in ref.items():
        if rv and rv > 0:
            dev = (ours[k] - rv) / rv
            rows.append({T("метрика"): k, "GreenHouse": round(ours[k], 4),
                         T("референс"): rv, T("отклонение"): f"{dev:+.1%}",
                         T("вердикт"): T("разобраться!") if abs(dev) > 0.10
                         else T("ок")})
    if rows:
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    else:
        st.info(T("Введи числа референса — появится таблица отклонений."))

    tab_footer(
        "Внешний контроль качества: тот же сценарий в независимом "
        "инструменте, его числа — сюда, отклонение до 10% — нормальный "
        "разброс допущений. Уже проведённые сверки: Тонга в диапазоне HOMER "
        "(LCOE $0.27 при 0.25–0.32); DeGrussa против фактов ARENA "
        "(расхождение объяснено трекерами); PV-цепочка против NREL SAM и "
        "датчиков в Оклахоме (±2%); полигон NIST (нашёл, что параметры "
        "модуля должны быть полями схемы — теперь они в этой форме)."
    )
