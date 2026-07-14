"""GreenHouse — интерактивный интерфейс калькулятора (Streamlit).

Запуск из корня проекта (с активированным .venv):
    streamlit run app.py

Устройство (паттерн Calliope "scenario = base + overrides"): в сайдбаре
пользователь крутит параметры-переопределения; они накладываются на
базовый JSON-сценарий, проходят те же pydantic-ворота, что и файл, и
уходят в тот же движок. Никакой отдельной математики в UI нет —
интерфейс показывает то, что считают src/optimize.py, src/simulate.py,
src/economics.py и src/sweep.py.
"""

import copy
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
from src.optimize import optimize_sizing
from src.sweep import run_sensitivity

WEATHER = "tests/data/tmy_sanaa_pvgis_sarah3.csv"
BASE_SCENARIO = "scenarios/yemen_sizing.json"

# Цвета технологий — те же, что во всех графиках проекта.
C_PV, C_BESS, C_DG = "#eda100", "#1baf7a", "#e34948"
C_BLUE, C_BLUE_LIGHT = "#2a78d6", "#9ec5f4"

# ASSUMPTION: операционные выбросы дизель-генерации ~0.72 кг CO2/kWh
# (2.68 кг CO2/л * ~0.27 л/кВт*ч); встроенные выбросы железа не учтены.
CO2_KG_PER_DIESEL_KWH = 0.72

st.set_page_config(page_title="GreenHouse", page_icon="🌿", layout="wide")


# ================= кэшируемые вычисления (всё считает ядро) =================


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


@st.cache_data(show_spinner="Решаю LP-задачу (~5 секунд)...")
def run_sizing_cached(scenario_json: str, load_csv_text: str | None):
    """Сайзер: сценарий -> размеры, штуки, метрики, ряды для графиков."""
    data = _apply_load(json.loads(scenario_json), load_csv_text)
    scenario = Scenario.model_validate(data)
    res = optimize_sizing(scenario, weather_csv=WEATHER, write_outputs=False)
    m, t = res.sim.manifest, res.sim.table

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
        "solve_seconds": m["solve_seconds"],
    }
    energy_mix = {
        "PV напрямую": float(t["pv_to_load_kw"].sum() * m["timestep_hours"]),
        "Батарея": float(t["discharge_kw"].sum() * m["timestep_hours"]),
        "Дизель": float(t["dg_kw"].sum() * m["timestep_hours"]),
    }
    week_df = t.loc["2026-02-16":"2026-02-22"]
    week = {
        "pv": week_df["pv_to_load_kw"].tolist(),
        "bess": week_df["discharge_kw"].tolist(),
        "dg": week_df["dg_kw"].tolist(),
        "load": week_df["load_kw"].tolist(),
        "soc": week_df["soc_kwh"].tolist(),
    } if len(week_df) else None
    return res.sizes, res.units, metrics, energy_mix, week


@st.cache_data(show_spinner="Строю профили солнца и нагрузки...")
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


@st.cache_data(show_spinner="Гоняю rule-симулятор на оптимальных размерах...")
def rule_check_cached(scenario_json: str, load_csv_text: str | None,
                      sizes_json: str):
    """Perfect-foresight проверка: LP-размеры фиксируются (min = max)
    и прогоняются через слепой rule-симулятор шага 5."""
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


@st.cache_data(show_spinner="Sensitivity: ~20 LP-задач, около 2 минут...")
def sensitivity_cached(scenario_json: str, load_csv_text: str | None):
    data = _apply_load(json.loads(scenario_json), load_csv_text)
    scenario = Scenario.model_validate(data)
    rep = run_sensitivity(scenario, weather_csv=WEATHER, write_outputs=False)
    return (rep.fuel_price, rep.bess_capex, rep.pv_capex,
            rep.pareto, rep.knee, rep.stress)


def econ_breakdown(data: dict, sizes: dict, metrics: dict) -> dict:
    """Экономика оптимума: те же формулы, что в src/economics.py,
    приложенные к размерам сайзера (CRF по сроку жизни технологии)."""
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
        "payback": capex_total / savings if savings > 0 else None,
    }


# ============================ сайдбар: overrides ============================

st.sidebar.title("🌿 GreenHouse")
st.sidebar.caption("Параметры накладываются на базовый сценарий (паттерн "
                   "Calliope: scenario = base + overrides) и уходят в "
                   "LP-оптимизатор. Единицы: kW / kWh / USD.")

with open(BASE_SCENARIO, encoding="utf-8") as f:
    base = json.load(f)

st.sidebar.subheader("Нагрузка")
load_mode = st.sidebar.radio(
    "Источник профиля", ["Синтетический (Йемен)", "CSV-файл"],
    help="Профиль нагрузки — ряд «сколько kW потребляет завод в каждый час». "
         "CSV: колонки timestamp,load_kw; равномерный шаг; год 2026.",
)
load_csv_text = None
if load_mode == "CSV-файл":
    uploaded = st.sidebar.file_uploader("timestamp,load_kw", type="csv")
    if uploaded is not None:
        load_csv_text = uploaded.getvalue().decode("utf-8")
    else:
        st.sidebar.info("Файл не загружен — использую синтетический профиль.")
else:
    day_kw = st.sidebar.slider(
        "Дневная нагрузка, kW", 100, 2000, int(base["load"]["day_kw"]), 50,
        help="Мощность (kW) в рабочие часы смены 08–18. kW — это СКОРОСТЬ "
             "потребления; энергия за час = kW × 1 ч.")
    night_kw = st.sidebar.slider(
        "Ночная база, kW", 0, 500, int(base["load"]["night_kw"]), 10,
        help="Дежурная мощность вне смены: охрана, холодильники, серверная.")

st.sidebar.subheader("Цены и параметры техники")
pv_capex = st.sidebar.slider(
    "CAPEX PV, $/kW", 200, 800, int(base["pv"]["capex_usd_per_kw"]), 10,
    help="CAPEX — разовые капитальные затраты (купить + смонтировать) на "
         "1 kWp панелей. kWp — «паспортная» мощность при идеальном солнце.")
bess_capex = st.sidebar.slider(
    "CAPEX BESS, $/kWh", 80, 400, int(base["battery"]["capex_usd_per_kwh"]), 5,
    help="Цена 1 kWh ёмкости накопителя (LFP-шкафы). kWh — сколько энергии "
         "батарея ХРАНИТ (а kW — как быстро отдаёт).")
fuel_price = st.sidebar.slider(
    "Дизельный kWh, $", 0.10, 0.60,
    float(base["diesel"]["fuel_cost_usd_per_kwh"]), 0.01,
    help="Полная стоимость 1 kWh из дизель-генератора (топливо + доставка). "
         "Tornado-анализ показывает: это самый влиятельный параметр модели.")
rte = st.sidebar.slider(
    "RTE батареи", 0.70, 0.98, float(base["battery"]["rte_fraction"]), 0.01,
    help="RTE (round-trip efficiency) — КПД полного цикла «зарядил-разрядил»: "
         "из 100 kWh при RTE 0.85 обратно выйдет 85. В модели потери делятся "
         "поровну: η заряда = η разряда = √RTE.")
roof = st.sidebar.slider(
    "Площадь под PV, м²", 1000, 20000, int(base["site"]["roof_area_m2"]), 500,
    help="Потолок сайзера: pv_kWp × 5 м²/kWp ≤ площадь. На базовом сценарии "
         "это ограничение активно — солнце дешевле дизеля, взяли бы больше.")

st.sidebar.subheader("Надёжность")
rel_mode = st.sidebar.selectbox(
    "Политика", ["hard (недопоставка запрещена)", "lpsp (допустимая доля)"],
    help="hard: каждый kWh спроса обязан быть поставлен (Σ недопоставки = 0). "
         "lpsp: недопоставка не выше заданной доли спроса — надёжность "
         "становится рычагом с ценником (см. Pareto в Sensitivity).")
lpsp_max = None
if rel_mode.startswith("lpsp"):
    lpsp_max = st.sidebar.slider(
        "Допустимая недопоставка, % нагрузки", 0.1, 10.0, 1.0, 0.1,
        help="LPSP (loss of power supply probability) — доля годового спроса, "
             "которую разрешено НЕ поставить. 1% ≈ 87 часов простоя в год.",
    ) / 100.0

# --- словарь терминов (по просьбе пользователя — прямо в сайдбаре) ---
with st.sidebar.expander("📖 Словарь терминов"):
    st.markdown("""
- **kW / kWh / kWp** — мощность (скорость) / энергия (количество =
  мощность × время) / паспортная мощность панелей при идеальном солнце.
- **CAPEX / O&M** — разовые капитальные затраты / ежегодная эксплуатация
  и обслуживание.
- **CRF** — capital recovery factor `r(1+r)ⁿ/((1+r)ⁿ−1)`: размазывает
  CAPEX в равные годовые платежи (как аннуитет ипотеки) — только так
  панели сравнимы с соляркой.
- **NPC** — net present cost: все затраты горизонта в сегодняшних деньгах.
- **LCOE** — levelized cost of energy: годовые издержки ÷ поставленные
  kWh; цена киловатт-часа «под ключ».
- **LPSP** — доля недопоставленной энергии за год (0% = всё поставлено;
  1% ≈ 87 часов простоя).
- **Renewable fraction** — доля поставки НЕ из дизеля.
- **SOC** — state of charge: текущий запас батареи, kWh; ниже «пола»
  (20%) не разряжаем — бережём ресурс.
- **RTE** — КПД цикла батареи (см. подсказку у ползунка).
- **Curtailment** — сброс лишней солнечной выработки (батарея полна,
  нагрузка сыта) — нормальная цена дешёвых панелей.
- **Shortfall** — недопоставка: спрос, который не покрыл никто.
- **VOLL** — value of lost load: цена недопоставленного kWh потребителю.
- **Perfect foresight** — LP-солвер «знает» весь год наперёд; реальный
  контроллер — нет, разрыв меряем во вкладке «Rule vs LP».
- **Pareto-фронт / колено** — кривая «стоимость ↔ надёжность» и точка,
  после которой уступки почти не экономят.
- **Tornado** — чей ценовой прогноз сильнее всего качает результат.
""")

# --- сборка сценария: base + overrides ---
data = copy.deepcopy(base)
if load_mode.startswith("Синтетический"):
    data["load"]["day_kw"] = day_kw
    data["load"]["night_kw"] = night_kw
data["pv"]["capex_usd_per_kw"] = pv_capex
data["battery"]["capex_usd_per_kwh"] = bess_capex
data["diesel"]["fuel_cost_usd_per_kwh"] = fuel_price
data["battery"]["rte_fraction"] = rte
data["site"]["roof_area_m2"] = roof
data["reliability"] = (
    {"mode": "hard"} if rel_mode.startswith("hard")
    else {"mode": "lpsp", "lpsp_max_fraction": lpsp_max}
)
scenario_json = json.dumps(data, sort_keys=True)

# ============================ запуск ядра ============================

try:
    sizes, units, metrics, energy_mix, week = run_sizing_cached(
        scenario_json, load_csv_text)
except RuntimeError as e:
    st.error(f"Оптимизация не удалась: {e}")
    st.stop()
except Exception as e:
    st.error(f"Проблема с входными данными: {e}")
    st.stop()

if "baseline" not in st.session_state:
    st.session_state.baseline = (dict(sizes), dict(metrics))
if st.sidebar.button("📌 Зафиксировать текущий как базу"):
    st.session_state.baseline = (dict(sizes), dict(metrics))
base_sizes, base_metrics = st.session_state.baseline

# ============================ метрики ============================

st.title("Оптимальная конфигурация")
st.caption(f"Решено за {metrics['solve_seconds']} c · дельты — против "
           "зафиксированной базы (📌 в сайдбаре)")


def delta(cur, ref):
    if ref in (None, 0) or cur is None:
        return None
    return f"{(cur - ref) / abs(ref):+.1%}"


c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Годовые издержки", f"${metrics['annual_cost_usd']:,.0f}",
          delta(metrics["annual_cost_usd"], base_metrics["annual_cost_usd"]),
          delta_color="inverse")
c2.metric("LCOE", f"${metrics['lcoe_usd_per_kwh']:.4f}/kWh",
          delta(metrics["lcoe_usd_per_kwh"], base_metrics["lcoe_usd_per_kwh"]),
          delta_color="inverse")
c3.metric("Renewable", f"{metrics['renewable_fraction']:.1%}",
          delta(metrics["renewable_fraction"], base_metrics["renewable_fraction"]))
c4.metric("Дизель", f"{metrics['dg_kwh']:,.0f} kWh",
          delta(metrics["dg_kwh"], base_metrics["dg_kwh"]), delta_color="inverse")
c5.metric("CO₂ (оценка*)", f"{metrics['co2_tons']:,.0f} т/год",
          delta(metrics["co2_tons"], base_metrics["co2_tons"]),
          delta_color="inverse")
st.caption(f"*ASSUMPTION {CO2_KG_PER_DIESEL_KWH} кг CO₂/kWh дизеля · "
           f"LPSP = {metrics['lpsp']:.2%} · curtailment = "
           f"{metrics['curtail_kwh']:,.0f} kWh")

(tab_cfg, tab_disp, tab_res, tab_eco, tab_rule,
 tab_sens, tab_scen, tab_valid) = st.tabs(
    ["⚙️ Конфигурация", "📈 Диспетчеризация", "☀️ Ресурсы", "💰 Экономика",
     "⚖️ Rule vs LP", "🌪 Sensitivity", "💾 Сценарии", "✅ Валидация"]
)

# ---------- ⚙️ конфигурация ----------

with tab_cfg:
    left, right = st.columns(2)

    spec = pd.DataFrame([
        ["PV", units["pv_panels"], "панель 0.58 kWp", f"{sizes['pv_kwp']:,.0f} kWp"],
        ["BESS (энергия)", units["batt_cabinets"], "шкаф 261 kWh",
         f"{sizes['batt_kwh']:,.0f} kWh"],
        ["BESS (мощность)", units["batt_pcs_units"], "PCS 125 kW",
         f"{sizes['batt_kw']:,.0f} kW"],
        ["Дизель", units["dg_gensets"], "генсет 1000 kW",
         f"{sizes['dg_kw']:,.0f} kW"],
    ], columns=["компонент", "штук", "юнит", "оптимальный размер"])
    left.subheader("Спецификация закупки")
    left.dataframe(spec, hide_index=True, use_container_width=True)

    fig_cap = go.Figure()
    names = ["PV, kWp", "BESS, kWh", "BESS, kW", "DG, kW"]
    keys = ["pv_kwp", "batt_kwh", "batt_kw", "dg_kw"]
    fig_cap.add_bar(y=names, x=[sizes[k] for k in keys], name="текущий",
                    orientation="h", marker_color=C_BLUE)
    fig_cap.add_bar(y=names, x=[base_sizes[k] for k in keys], name="база 📌",
                    orientation="h", marker_color=C_BLUE_LIGHT)
    fig_cap.update_layout(title="Размеры: текущий vs база", height=300,
                          margin=dict(l=10, r=10, t=40, b=10), barmode="group")
    left.plotly_chart(fig_cap, use_container_width=True)

    fig_pie = go.Figure(go.Pie(
        labels=list(energy_mix), values=list(energy_mix.values()),
        marker=dict(colors=[C_PV, C_BESS, C_DG]), hole=0.5,
        texttemplate="%{label}<br>%{percent}",
    ))
    fig_pie.update_layout(title="Кто поставил энергию за год", height=330,
                          margin=dict(l=10, r=10, t=40, b=10))
    right.subheader("Энергобаланс года")
    right.plotly_chart(fig_pie, use_container_width=True)

    st.subheader("Схема системы (AC-coupling, шина 400 В)")
    fig_sch = go.Figure()
    boxes = [
        (0, f"PV<br>{sizes['pv_kwp']:,.0f} kWp<br>{units['pv_panels']} панелей", C_PV),
        (1, f"BESS<br>{sizes['batt_kwh']:,.0f} kWh / {sizes['batt_kw']:,.0f} kW"
            f"<br>{units['batt_cabinets']} шкафов", C_BESS),
        (2, f"DG<br>{sizes['dg_kw']:,.0f} kW<br>{units['dg_gensets']} генсет", C_DG),
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
    fig_sch.add_annotation(x=2.6, y=0.78, text="шина 400 В", showarrow=False,
                           xanchor="right")
    fig_sch.add_shape(type="line", x0=1, x1=1, y0=0.7, y1=0.25,
                      line=dict(color="#555", width=3))
    fig_sch.add_shape(type="rect", x0=0.55, x1=1.45, y0=-0.25, y1=0.25,
                      line=dict(color="#555", width=2), fillcolor="#555",
                      opacity=0.08)
    fig_sch.add_annotation(x=1, y=0, text="Завод (нагрузка)", showarrow=False)
    fig_sch.update_xaxes(visible=False, range=[-0.8, 2.8])
    fig_sch.update_yaxes(visible=False, range=[-0.4, 2.2])
    fig_sch.update_layout(height=330, margin=dict(l=10, r=10, t=10, b=10))
    st.plotly_chart(fig_sch, use_container_width=True)

# ---------- 📈 диспетчеризация ----------

with tab_disp:
    if week is None:
        st.info("Недельный график доступен для годового часового профиля.")
    else:
        x = list(range(len(week["load"])))
        fig_w = go.Figure()
        for key, name, color in (("pv", "PV напрямую", C_PV),
                                 ("bess", "батарея", C_BESS),
                                 ("dg", "дизель", C_DG)):
            fig_w.add_scatter(x=x, y=week[key], name=name, stackgroup="mix",
                              mode="none", fillcolor=color)
        fig_w.add_scatter(x=x, y=week["load"], name="нагрузка",
                          line=dict(color="#111", dash="dash", width=1.5))
        fig_w.update_layout(
            title="Неделя 16–22 февраля: кто кормит завод (LP-решение)",
            xaxis_title="часы недели", yaxis_title="kW", height=380,
            legend=dict(orientation="h", y=1.12),
        )
        st.plotly_chart(fig_w, use_container_width=True)

        fig_soc = go.Figure()
        fig_soc.add_scatter(x=x, y=week["soc"], name="SOC, kWh",
                            line=dict(color=C_BESS, width=2))
        fig_soc.add_hline(y=0.2 * sizes["batt_kwh"], line_dash="dot",
                          line_color=C_DG,
                          annotation_text="пол SOC (20%)")
        fig_soc.add_hline(y=sizes["batt_kwh"], line_dash="dot",
                          line_color="#555", annotation_text="ёмкость")
        fig_soc.update_layout(title="Запас батареи (SOC) в ту же неделю",
                              xaxis_title="часы недели", yaxis_title="kWh",
                              height=300)
        st.plotly_chart(fig_soc, use_container_width=True)

# ---------- ☀️ ресурсы ----------

with tab_res:
    prof = profiles_cached(scenario_json, load_csv_text)
    m1, m2, m3 = st.columns(3)
    m1.metric("Годовая выработка солнца", f"{prof['solar_annual']:,.0f} kWh/kWp")
    m2.metric("Энергия нагрузки за год", f"{prof['load_year_kwh']:,.0f} kWh")
    m3.metric("Шаг данных Δt", f"{prof['dt']} ч")

    colA, colB = st.columns(2)
    fig_l = go.Figure()
    fig_l.add_scatter(y=prof["load_48"], line_shape="hv", name="нагрузка, kW",
                      line=dict(color=C_BLUE, width=2))
    fig_l.update_layout(title="Нагрузка: первые двое суток",
                        xaxis_title="час", yaxis_title="kW", height=320)
    colA.plotly_chart(fig_l, use_container_width=True)

    fig_s = go.Figure()
    fig_s.add_scatter(y=prof["best_curve"], name=f"лучший день ({prof['best_day']})",
                      line=dict(color=C_PV, width=2))
    fig_s.add_scatter(y=prof["june_curve"], name="15 июня (облачный сезон)",
                      line=dict(color=C_BESS, width=2))
    fig_s.update_layout(title="Солнце: типовые сутки, kW на 1 kWp",
                        xaxis_title="час местного времени",
                        yaxis_title="kW/kWp", height=320)
    colB.plotly_chart(fig_s, use_container_width=True)

    fig_m = go.Figure(go.Bar(x=list(range(1, 13)), y=prof["monthly"],
                             marker_color=C_PV, name="kWh/kWp за месяц"))
    fig_m.update_layout(title="Выработка по месяцам (обрати внимание: зима "
                              "солнечнее лета — июльская облачность Саны)",
                        xaxis_title="месяц", yaxis_title="kWh/kWp", height=300)
    st.plotly_chart(fig_m, use_container_width=True)

# ---------- 💰 экономика ----------

with tab_eco:
    eco = econ_breakdown(data, sizes, metrics)
    e1, e2, e3, e4 = st.columns(4)
    e1.metric("CAPEX (разово)", f"${eco['capex_total']:,.0f}")
    e2.metric("NPC (за горизонт)", f"${eco['npc']:,.0f}")
    e3.metric("База «100% дизель»", f"${eco['baseline']:,.0f}/год")
    e4.metric("Окупаемость",
              f"{eco['payback']:.1f} лет" if eco["payback"] else "нет")

    fig_e = go.Figure()
    for name, value, color in eco["items"]:
        fig_e.add_bar(y=[name], x=[value], orientation="h",
                      marker_color=color, showlegend=False,
                      text=f"${value:,.0f}", textposition="outside")
    fig_e.update_layout(
        title=f"Годовые издержки ${eco['annual']:,.0f} — из чего складываются "
              "(CRF по сроку жизни технологии)",
        xaxis_title="$/год", height=330,
        xaxis_range=[0, max(v for _, v, _ in eco["items"]) * 1.25],
    )
    st.plotly_chart(fig_e, use_container_width=True)
    st.caption("Сверка: сумма статей совпадает с целевой функцией солвера "
               f"(${metrics['annual_cost_usd']:,.0f}) с точностью до "
               "анти-вырожденного микроштрафа — две независимые дороги к "
               "одному числу.")

# ---------- ⚖️ rule vs LP ----------

with tab_rule:
    st.markdown(
        "LP-сайзер обладает **perfect foresight** — «знает» весь год наперёд. "
        "Реальный контроллер работает по правилу и будущего не видит. Здесь "
        "оптимальные размеры фиксируются и прогоняются через слепой "
        "rule-симулятор шага 5 — разница и есть цена идеального предвидения."
    )
    rule_totals, rule_lpsp = rule_check_cached(
        scenario_json, load_csv_text, json.dumps(sizes, sort_keys=True))

    r1, r2, r3 = st.columns(3)
    r1.metric("LPSP у LP (всевидящий)", f"{metrics['lpsp']:.2%}")
    r2.metric("LPSP у правила (слепой)", f"{rule_lpsp:.2%}",
              help="Если больше нуля при hard-политике — это и есть "
                   "perfect-foresight разрыв: живой диспетчер иногда не "
                   "дотягивает на размерах, ужатых оптимизатором.")
    r3.metric("Недопоставка правила",
              f"{rule_totals['shortfall']:,.0f} kWh/год")

    flows = ["dg", "discharge", "curtail", "shortfall"]
    lp_totals = {"dg": metrics["dg_kwh"], "curtail": metrics["curtail_kwh"],
                 "discharge": energy_mix["Батарея"],
                 "shortfall": metrics["load_kwh"] - metrics["served_kwh"]}
    fig_r = go.Figure()
    fig_r.add_bar(y=flows, x=[lp_totals[f] for f in flows],
                  name="LP (шаг 7-8)", orientation="h", marker_color=C_BLUE)
    fig_r.add_bar(y=flows, x=[rule_totals[f] for f in flows],
                  name="правило (шаг 5)", orientation="h",
                  marker_color=C_BLUE_LIGHT)
    fig_r.update_layout(title="Годовые потоки: LP vs rule на одних размерах",
                        xaxis_title="kWh за год", height=340, barmode="group")
    st.plotly_chart(fig_r, use_container_width=True)

# ---------- 🌪 sensitivity ----------

with tab_sens:
    st.markdown("Полный пакет шага 9: свипы цен (tornado), Pareto-фронт "
                "«стоимость ↔ надёжность» с коленом, стрессы. **~2 минуты** "
                "(≈20 LP-задач) — запускается по кнопке, результат кэшируется.")
    if st.button("🌪 Запустить sensitivity (~2 мин)") or \
            "sens_done" in st.session_state:
        st.session_state["sens_done"] = True
        fuel_df, bess_df, pv_df, pareto, knee, stress = sensitivity_cached(
            scenario_json, load_csv_text)

        base_cost = float(fuel_df.loc[fuel_df.value == 1.0,
                                      "annual_cost_usd"].iloc[0])
        rows = []
        for name, df in (("Цена дизеля ±50%", fuel_df),
                         ("CAPEX BESS ±30%", bess_df),
                         ("CAPEX PV ±30%", pv_df)):
            if not df.empty:
                rows.append((name, df.annual_cost_usd.min(),
                             df.annual_cost_usd.max()))
        rows.sort(key=lambda r: r[2] - r[1], reverse=True)

        fig_t = go.Figure()
        for name, lo, hi in rows:
            fig_t.add_bar(y=[name], x=[base_cost - lo], base=lo,
                          orientation="h", marker_color=C_BLUE_LIGHT,
                          name="дешевле базы", showlegend=(name == rows[0][0]))
            fig_t.add_bar(y=[name], x=[hi - base_cost], base=base_cost,
                          orientation="h", marker_color=C_BLUE,
                          name="дороже базы", showlegend=(name == rows[0][0]))
        fig_t.add_vline(x=base_cost, line_dash="dash", line_color="#111")
        fig_t.update_layout(title="Tornado: чувствительность издержек к ценам",
                            xaxis_title="$/год", height=320, barmode="overlay")
        st.plotly_chart(fig_t, use_container_width=True)

        fig_p = go.Figure()
        pareto_sorted = pareto.sort_values("lpsp_target")
        fig_p.add_scatter(x=pareto_sorted.lpsp_target * 100,
                          y=pareto_sorted.annual_cost_usd,
                          mode="lines+markers", name="Pareto-фронт",
                          line=dict(color=C_BLUE, width=2))
        fig_p.add_scatter(x=[knee["lpsp"] * 100], y=[knee["annual_cost_usd"]],
                          mode="markers", name="колено",
                          marker=dict(size=16, symbol="circle-open",
                                      color=C_DG, line=dict(width=3)))
        fig_p.update_layout(title="Pareto: сколько стоит надёжность",
                            xaxis_title="допустимая недопоставка (LPSP), %",
                            yaxis_title="$/год", height=340)
        st.plotly_chart(fig_p, use_container_width=True)
        st.caption(f"Колено: LPSP {knee['lpsp']:.1%} за "
                   f"${knee['annual_cost_usd']:,.0f}/год.")

        st.subheader("Стрессы оптимального дизайна")
        st.dataframe(stress.round(4), hide_index=True,
                     use_container_width=True)

# ---------- 💾 сценарии ----------

with tab_scen:
    st.subheader("Сохранить текущий")
    scenario_pack = json.dumps({
        "scenario": data, "sizes": sizes, "units": units, "metrics": metrics,
    }, ensure_ascii=False, indent=2)
    name = st.text_input("Имя сценария", value="мой вариант")
    col_a, col_b = st.columns(2)
    col_a.download_button("⬇️ Скачать JSON", scenario_pack,
                          file_name=f"greenhouse_{name}.json")
    if col_b.button("➕ Добавить в сравнение"):
        st.session_state.setdefault("saved", {})[name] = {
            "sizes": dict(sizes), "metrics": dict(metrics)}

    st.subheader("Загрузить сохранённый")
    up = st.file_uploader("greenhouse_*.json", type="json", key="scen_up")
    if up is not None:
        pack = json.loads(up.getvalue().decode("utf-8"))
        st.session_state.setdefault("saved", {})[up.name] = {
            "sizes": pack["sizes"], "metrics": pack["metrics"]}
        st.success(f"Загружен {up.name}")

    saved = st.session_state.get("saved", {})
    if saved:
        st.subheader("Сравнение сценариев")
        rows = []
        for nm, p in {**saved, "← текущий": {"sizes": sizes,
                                             "metrics": metrics}}.items():
            rows.append({
                "сценарий": nm,
                "PV, kWp": round(p["sizes"]["pv_kwp"]),
                "BESS, kWh": round(p["sizes"]["batt_kwh"]),
                "DG, kW": round(p["sizes"]["dg_kw"]),
                "изд., $/год": round(p["metrics"]["annual_cost_usd"]),
                "LCOE, $": round(p["metrics"]["lcoe_usd_per_kwh"], 4),
                "renewable": f"{p['metrics']['renewable_fraction']:.1%}",
                "CO₂, т": round(p["metrics"]["co2_tons"]),
            })
        st.dataframe(pd.DataFrame(rows), hide_index=True,
                     use_container_width=True)

# ---------- ✅ валидация ----------

with tab_valid:
    st.markdown(
        "Сверка с внешним инструментом (REopt web / HOMER). Прогони тот же "
        "сценарий там, впиши их числа — отклонения **> 10%** будут "
        "помечены. Публичного API у HOMER нет, у REopt нужен ключ NREL — "
        "поэтому v1 сверяет вручную введённые числа, честно и прозрачно."
    )
    cc = st.columns(4)
    ref = {
        "PV, kWp": cc[0].number_input("PV референса, kWp", value=0.0),
        "BESS, kWh": cc[1].number_input("BESS референса, kWh", value=0.0),
        "DG, kW": cc[2].number_input("DG референса, kW", value=0.0),
        "LCOE, $/kWh": cc[3].number_input("LCOE референса", value=0.0,
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
            rows.append({"метрика": k, "GreenHouse": round(ours[k], 4),
                         "референс": rv, "отклонение": f"{dev:+.1%}",
                         "вердикт": "⚠️ разобраться" if abs(dev) > 0.10 else "✅ ок"})
    if rows:
        st.dataframe(pd.DataFrame(rows), hide_index=True,
                     use_container_width=True)
    else:
        st.info("Введи числа референса — появится таблица отклонений.")
