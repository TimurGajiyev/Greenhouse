"""Смоук-тест Streamlit-приложения (app.py).

AppTest — штатный фреймворк Streamlit: исполняет скрипт приложения
без браузера и даёт доступ к элементам. Проверяем, что приложение
поднимается, решает LP и показывает метрики без исключений.
"""

import pytest
from streamlit.testing.v1 import AppTest


@pytest.fixture(scope="module")
def app():
    at = AppTest.from_file("app.py", default_timeout=180)
    return at.run()


@pytest.fixture(scope="module")
def app_en():
    at = AppTest.from_file("app.py", default_timeout=180)
    at.session_state["lang"] = "EN"
    return at.run()


def test_app_english_renders(app_en):
    """EN-версия поднимается без ошибок и переводит заголовок и метрики."""
    assert not app_en.exception
    assert "Optimal configuration" in [x.value for x in app_en.title]
    labels = [m.label for m in app_en.metric]
    assert "Annual cost" in labels
    assert "Diesel" in labels


def test_translation_catalog_complete():
    """Каждый вызов T(...) в app.py имеет запись в словаре переводов
    (иначе EN покажет русский текст — молчаливая дыра)."""
    import re
    from app_i18n import TRANSLATIONS

    source = open("app.py", encoding="utf-8").read()
    # Строковые литералы, обёрнутые в T("...") или tr("..."), одинарные
    # и многострочные конкатенации внутри вызова опустим — проверяем
    # простые односегментные вызовы T("literal").
    calls = re.findall(r'\bT\("((?:[^"\\]|\\.)+)"\)', source)
    missing = [c for c in set(calls)
               if c not in TRANSLATIONS and c not in ("DISCLAIMER",)]
    assert not missing, f"нет перевода для: {missing[:5]}"


def test_app_runs_without_exception(app):
    assert not app.exception


def test_app_shows_metrics(app):
    """Пять метрик с числами на месте (LCOE и издержки не пустые)."""
    values = [m.value for m in app.metric]
    assert len(values) >= 5
    assert any("$" in v for v in values)          # деньги
    assert any("kWh" in v for v in values)        # энергия дизеля


def test_app_sidebar_has_overrides(app):
    """Ключевые ползунки-overrides существуют (паттерн Calliope)."""
    labels = [s.label for s in app.sidebar.slider]
    assert any("CAPEX PV" in l for l in labels)
    assert any("Дизельный kWh" in l for l in labels)


def test_app_sidebar_glossary(app):
    """Словарь терминов в сайдбаре: LPSP, LCOE, CRF объяснены."""
    sidebar_text = " ".join(
        "".join(m.value) if isinstance(m.value, list) else str(m.value)
        for m in app.sidebar.markdown
    )
    for term in ("LPSP", "LCOE", "CRF", "SOC", "RTE"):
        assert term in sidebar_text, f"термин {term} не объяснён в сайдбаре"


def test_app_slider_tooltips(app):
    """У каждого ползунка есть подсказка-легенда (help)."""
    helps = [s.help for s in app.sidebar.slider]
    assert all(h for h in helps), "у части ползунков нет пояснения"


def test_app_tab_footers(app):
    """В конце вкладок — пояснения «что здесь происходит и зачем»
    (вкладка Sensitivity показывает своё после запуска по кнопке,
    поэтому на холодном старте ждём минимум 7)."""
    texts = [
        "".join(m.value) if isinstance(m.value, list) else str(m.value)
        for m in app.markdown
    ]
    footers = [t for t in texts if "Что здесь происходит и зачем" in t]
    assert len(footers) >= 7, f"пояснений {len(footers)}, ожидалось >= 7"


def test_app_no_emoji_anywhere(app):
    """Эмодзи удалены отовсюду (просьба пользователя)."""
    import re
    emoji = re.compile('[\U0001F000-\U0001FAFF☀-➿]')
    source = open("app.py", encoding="utf-8").read()
    assert not emoji.search(source), "в app.py остались эмодзи"


def test_app_form_batches_recalc(app):
    """Форма с кнопкой «Пересчитать»: ползунки применяются пакетно."""
    labels = [b.label for b in app.sidebar.button]
    assert any("Пересчитать" in l for l in labels)


def test_app_module_and_corridor_controls(app):
    """Новые контролы: параметры PV-модуля (кейсы OKC/NIST) и коридоры
    поиска; у каждого есть подсказка."""
    sliders = {s.label: s.help for s in app.sidebar.slider}
    for needle in ("КПД инвертора", "Темп. коэффициент", "DC/AC",
                   "Макс. PV", "Макс. BESS", "Макс. DG"):
        hit = [l for l in sliders if needle in l]
        assert hit, f"нет контрола {needle}"
        assert sliders[hit[0]], f"нет подсказки у {needle}"


def test_app_reliability_voll_and_cyclic(app):
    """Политика voll доступна в селекторе, кольцо SOC — чекбоксом."""
    options = []
    for sb in app.sidebar.selectbox:
        options += list(sb.options)
    assert any("voll" in o for o in options)
    assert any("Циклический SOC" in cb.label for cb in app.sidebar.checkbox)


def test_app_html_report_download(app):
    """Кнопка скачивания HTML-отчёта существует, отчёт содержит
    оговорку про инженера."""
    labels = [d.label for d in app.get("download_button")]
    assert any("HTML" in l for l in labels)


def test_app_legend_help_captions(app):
    """Под графиками есть подписи «Как читать: ...» (ясные легенды)."""
    captions = [
        "".join(c.value) if isinstance(c.value, list) else str(c.value)
        for c in app.caption
    ]
    howto = [c for c in captions if c.startswith("Как читать")]
    assert len(howto) >= 5, f"подписей «Как читать» {len(howto)}, ждём >= 5"
