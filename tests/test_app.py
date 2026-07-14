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
