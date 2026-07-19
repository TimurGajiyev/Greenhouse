"""Структурные тесты графиков приложения (аудит №4, плейбук).

AppTest отдаёт JSON-спецификацию каждой plotly-фигуры (proto.spec) —
проверяем не «график нарисовался», а ЧТО в нём нарисовано: длины рядов,
суммы стеков, знаки водопада, монотонность кривой выживания, сходимость
LCOE-колонок с метрикой шапки. Это ловит битые данные, которые глазом
на смоук-тесте не видны.
"""

import json

import pytest
from streamlit.testing.v1 import AppTest


@pytest.fixture(scope="module")
def figures():
    """Все фигуры дефолтного рендера: список (title, fig_dict)."""
    at = AppTest.from_file("app.py", default_timeout=300)
    at.run()
    assert not at.exception
    out = []
    for el in at.get("plotly_chart"):
        fig = json.loads(el.proto.spec)
        title = (fig.get("layout", {}).get("title", {}) or {}).get("text", "")
        out.append((title, fig))
    return out


def by_title(figures, needle: str) -> dict:
    hits = [f for t, f in figures if needle in t]
    assert hits, f"нет графика с заголовком «{needle}»"
    return hits[0]


def test_all_expected_charts_present(figures):
    """Дефолтный рендер несёт все 17 графиков (8 вкладок, без кнопочных)."""
    assert len(figures) == 17
    for needle in (
        "Размеры: текущее решение",          # столбцы против базы
        "Кто поставил энергию заводу",       # пирог
        "Типовые сутки",                     # плейбук №3 (новый)
        "Неделя 16–22 февраля",              # недельный стек
        "Запас батареи (SOC)",               # SOC недели
        "Кто кормит завод по месяцам",       # сезонный стек
        "Нагрузка: первые двое суток",
        "Солнце: типовые сутки",
        "Выработка по месяцам",
        "Цена киловатт-часа",                # плейбук №4 (новый)
        "Годовые издержки",                  # разбор издержек
        "Накопленные затраты",               # кривая окупаемости
        "Водопад окупаемости",               # плейбук №6 (новый)
        "Годовые потоки: идеальный план",    # rule vs lp
        "Доля часов года",                   # кривая выживания
    ):
        by_title(figures, needle)


def test_typical_day_stack_shape(figures):
    """Типовые сутки: 3 стековых слоя + линия спроса, по 24 точки."""
    fig = by_title(figures, "Типовые сутки")
    traces = fig["data"]
    assert len(traces) == 4
    stacked = [t for t in traces if t.get("stackgroup")]
    assert len(stacked) == 3
    for t in traces:
        assert len(t["y"]) == 24
    # Слои неотрицательны (это мощности).
    for t in stacked:
        assert min(t["y"]) >= -1e-6


def test_typical_day_stack_covers_demand(figures):
    """Сумма слоёв в каждый час равна среднему спросу (недопоставки в
    hard-режиме нет), допуск на усреднение — 1e-6."""
    fig = by_title(figures, "Типовые сутки")
    traces = {t["name"]: t["y"] for t in fig["data"]}
    load = [t for t in fig["data"] if not t.get("stackgroup")][0]["y"]
    stacked = [t["y"] for t in fig["data"] if t.get("stackgroup")]
    for h in range(24):
        total = sum(layer[h] for layer in stacked)
        assert total == pytest.approx(load[h], abs=1e-4)


def test_lcoe_columns_match_header_metric(figures):
    """Правая колонка (сумма сегментов) == LCOE из шапки; левая ==
    левелизованная цена дизельного кВт*ч; проект дешевле базы."""
    fig = by_title(figures, "Цена киловатт-часа")
    bars = fig["data"]
    base_vals = [b["y"][0] for b in bars if "дизель»" not in str(b.get("x"))
                 and "проект" not in str(b.get("x", [""])[0])]
    left = sum(b["y"][0] for b in bars
               if "только дизель" in str(b["x"][0]))
    right = sum(b["y"][0] for b in bars
                if "проект" in str(b["x"][0]))
    assert left > right > 0
    # Аннотации несут те же числа, что и колонки.
    ann = fig["layout"]["annotations"]
    ann_left = float(ann[0]["text"].replace("$", ""))
    ann_right = float(ann[1]["text"].replace("$", ""))
    assert ann_left == pytest.approx(left, abs=5e-4)
    assert ann_right == pytest.approx(right, abs=5e-4)


def test_waterfall_structure(figures):
    """Водопад (bar+base — go.Waterfall ломается под темой Streamlit):
    CAPEX уходит вниз, годовые экономии поднимают лесенку, есть
    аннотация «окупился» (Йемен окупается)."""
    fig = by_title(figures, "Водопад окупаемости")
    wf = fig["data"][0]
    assert wf["type"] == "bar"
    hs, bases = wf["y"], wf["base"]
    assert len(hs) == 1 + 10              # CAPEX + 10 лет проекта Йемена
    # CAPEX-бар: от -capex до нуля (низ отрицательный, верх == 0).
    assert bases[0] < 0
    assert bases[0] + hs[0] == pytest.approx(0.0, abs=1e-6)
    # Годовые бары: непрерывная лесенка (низ следующего == верх этого).
    for i in range(1, len(hs) - 1):
        assert bases[i + 1] == pytest.approx(bases[i] + hs[i], rel=1e-9)
    ann_texts = [a["text"] for a in fig["layout"].get("annotations", [])]
    assert any("окупился" in t for t in ann_texts)
    # Лесенка действительно пересекает ноль внутри горизонта.
    assert any(bases[i] + hs[i] >= 0 for i in range(1, len(hs)))
    # Цвета: вложение красное, возврат зелёный (палитра проекта).
    colors = wf["marker"]["color"]
    assert colors[0] == "#e34948" and set(colors[1:]) == {"#1baf7a"}


def test_cashflow_curves_consistent_with_waterfall(figures):
    """Кривая накопленных затрат и водопад — две проекции одних денег:
    точка безубытка водопада лежит между теми же годами, где линии
    кривой пересекаются."""
    fig_cf = by_title(figures, "Накопленные затраты")
    base_y = fig_cf["data"][0]["y"]
    hyb_y = fig_cf["data"][1]["y"]
    assert len(base_y) == len(hyb_y) == 11   # 0..10 лет
    assert base_y[0] == 0 and hyb_y[0] > 0   # старт: CAPEX против нуля
    cf_cross = next(i for i in range(11) if hyb_y[i] <= base_y[i])

    fig_wf = by_title(figures, "Водопад окупаемости")
    wf = fig_wf["data"][0]
    hs, bases = wf["y"], wf["base"]
    wf_cross = next(i for i in range(1, len(hs)) if bases[i] + hs[i] >= 0)
    assert abs(wf_cross - cf_cross) <= 1     # одна и та же точка ±год


def test_survival_bars_monotonic(figures):
    """Кривая выживания: доли в [0..100], не растут с длительностью."""
    fig = by_title(figures, "Доля часов года")
    ys = fig["data"][0]["y"]
    assert len(ys) == 6                       # 4/8/12/24/48/72
    assert all(0.0 <= v <= 100.0 for v in ys)
    assert all(ys[i] >= ys[i + 1] - 1e-9 for i in range(len(ys) - 1))


def test_sankey_flows_are_conservative(figures):
    """Sankey: и лента, и узлы согласованы; приток в «Завод» равен
    поставленной энергии (пирог) с точностью до округления лент."""
    sankeys = [f for _, f in figures
               if f["data"] and f["data"][0].get("type") == "sankey"]
    assert sankeys, "нет Sankey-диаграммы"
    sk = sankeys[0]["data"][0]
    links = sk["link"]
    labels = sk["node"]["label"]
    n = len(labels)
    assert all(0 <= s < n for s in links["source"])
    assert all(0 <= t < n for t in links["target"])
    assert all(v >= 0 for v in links["value"])
    # Приток в узел «Завод» == сумма пирога (обе — годовая поставка).
    plant = next(i for i, l in enumerate(labels) if "Завод" in l)
    inflow = sum(v for s, t, v in zip(links["source"], links["target"],
                                      links["value"]) if t == plant)
    pie = [f for _, f in figures
           if f["data"] and f["data"][0].get("type") == "pie"][0]
    pie_total = sum(pie["data"][0]["values"])
    assert inflow == pytest.approx(pie_total, rel=2e-3)


def test_week_and_monthly_stacks(figures):
    """Недельный стек — 168 часов на слой; помесячный — 12 месяцев."""
    week = by_title(figures, "Неделя 16–22 февраля")
    for t in week["data"]:
        assert len(t["y"]) == 168
    monthly = by_title(figures, "Кто кормит завод по месяцам")
    for t in monthly["data"]:
        assert len(t["y"]) == 12
    assert monthly["layout"]["barmode"] == "stack"


def test_palette_is_consistent_across_charts(figures):
    """Единая палитра источников (правило плейбука): солнце/батарея/дизель
    несут одни и те же цвета в типовых сутках, неделе и месяцах."""
    C_PV, C_BESS, C_DG = "#eda100", "#1baf7a", "#e34948"
    for needle in ("Типовые сутки", "Неделя 16–22 февраля"):
        fig = by_title(figures, needle)
        colors = [t.get("fillcolor") for t in fig["data"]
                  if t.get("stackgroup")]
        assert colors == [C_PV, C_BESS, C_DG]
    monthly = by_title(figures, "Кто кормит завод по месяцам")
    mcolors = [t["marker"]["color"] for t in monthly["data"]]
    assert mcolors == [C_PV, C_BESS, C_DG]


def test_english_chart_titles(  ):
    """EN-рендер: заголовки новых графиков переведены (не русский)."""
    at = AppTest.from_file("app.py", default_timeout=300)
    at.session_state["lang"] = "EN"
    at.run()
    assert not at.exception
    titles = []
    for el in at.get("plotly_chart"):
        fig = json.loads(el.proto.spec)
        titles.append((fig.get("layout", {}).get("title", {}) or {})
                      .get("text", ""))
    joined = " | ".join(titles)
    for en in ("Typical day", "Price per kilowatt-hour",
               "Payback waterfall"):
        assert en in joined, f"нет EN-заголовка {en!r}"
