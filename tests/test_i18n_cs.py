"""Тесты чешской локали (app_i18n_cs.py) и многоязычности в целом.

Главный тест — полнота: AST-разбором вытаскиваем из app.py ВСЕ строки,
попадающие в перевод (T / T2 / tab_footer / legend_help), и требуем
чешское значение для каждой. Регулярка, как в test_app.py, ловит только
односегментные T("..."), а здесь проверяются и многострочные тексты
подвалов — то есть именно те, где дыру заметить труднее всего.
"""

import ast
import re

import pytest
from streamlit.testing.v1 import AppTest

from app_i18n import (
    LANGUAGES,
    TRANSLATIONS,
    get_columns_help,
    get_glossary,
    make_t,
)
from app_i18n_cs import COLUMNS_HELP_CS, GLOSSARY_CS, TRANSLATIONS_CS

TRANSLATED_CALLS = {"T", "T2", "tab_footer", "legend_help"}


def live_strings() -> list[str]:
    """Все переводимые строки app.py.

    Два источника, потому что одного мало:
      1) прямые вызовы T("...") / tab_footer("...") — берём AST-разбором;
      2) КОСВЕННЫЕ: литерал лежит в кортеже/словаре (легенды графиков,
         статьи затрат, названия компонентов), а в T() приходит уже
         переменная — AST вызова такую строку не видит. Их ловим так:
         любой строковый литерал app.py, у которого есть английский
         перевод, переводится и в рантайме.
    Именно пункт 2 однажды был пропущен, и в чешской версии остались
    русские легенды — тест по отрисованному интерфейсу это поймал.
    """
    tree = ast.parse(open("app.py", encoding="utf-8").read())
    direct = []
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id in TRANSLATED_CALLS):
            for arg in node.args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    if arg.value != "DISCLAIMER":   # берётся из app.py
                        direct.append(arg.value)
    literals = {n.value for n in ast.walk(tree)
                if isinstance(n, ast.Constant) and isinstance(n.value, str)}
    indirect = sorted(literals & set(TRANSLATIONS))
    return list(dict.fromkeys(direct + indirect))


# ---------- полнота ----------

def test_czech_covers_every_live_string():
    """Ни одной строки без чешского перевода (иначе в CS-версии
    вылезет русский — молчаливая дыра)."""
    missing = [s for s in live_strings() if s not in TRANSLATIONS_CS]
    assert not missing, (
        f"нет чешского перевода для {len(missing)} строк, первые: "
        f"{[m[:60] for m in missing[:5]]}"
    )


def test_english_covers_every_live_string():
    """Тот же контроль для английского — чтобы добавление CS не
    замаскировало дыру в EN."""
    missing = [s for s in live_strings() if s not in TRANSLATIONS]
    assert not missing, [m[:60] for m in missing[:5]]


def test_czech_has_no_orphan_keys():
    """В чешском словаре нет мусора: каждый ключ реально используется
    приложением (иначе словарь тихо расходится с интерфейсом)."""
    used = set(live_strings())
    orphans = [k for k in TRANSLATIONS_CS if k not in used]
    assert not orphans, [o[:60] for o in orphans[:5]]


# ---------- корректность значений ----------

def test_czech_placeholders_match_source():
    """Плейсхолдеры {} / {:g} совпадают с русским ключом — иначе
    .format() упадёт именно на чешской версии."""
    ph = re.compile(r"\{[^}]*\}")
    bad = [k for k, v in TRANSLATIONS_CS.items()
           if ph.findall(k) != ph.findall(v)]
    assert not bad, [b[:60] for b in bad[:5]]


def test_czech_values_are_non_empty_and_translated():
    """Пустых значений нет; и это не копипаста русского (кириллица в
    чешском тексте — признак незаконченного перевода). Единственное
    исключение — подпись переключателя языков, намеренно двуязычная."""
    cyr = re.compile(r"[а-яА-ЯёЁ]")
    empty = [k for k, v in TRANSLATIONS_CS.items() if not v.strip()]
    assert not empty, [e[:60] for e in empty[:5]]
    untranslated = [k for k, v in TRANSLATIONS_CS.items()
                    if cyr.search(v) and k != "Язык / Language"]
    assert not untranslated, [u[:60] for u in untranslated[:5]]


def test_czech_glossary_and_columns_help():
    """Глоссарий и справка по колонкам переведены целиком."""
    cyr = re.compile(r"[а-яА-ЯёЁ]")
    for text in (GLOSSARY_CS, COLUMNS_HELP_CS):
        assert text.strip()
        assert not cyr.search(text)
    # Структура сохранена: столько же пунктов, сколько в русском.
    assert GLOSSARY_CS.count("- **") == get_glossary("RU").count("- **")
    assert (COLUMNS_HELP_CS.count("- **")
            == get_columns_help("RU").count("- **"))


# ---------- контракт make_t ----------

def test_make_t_dispatches_by_language():
    assert make_t("CS")("Надёжность") == "Spolehlivost"
    assert make_t("EN")("Надёжность") == "Reliability"
    assert make_t("RU")("Надёжность") == "Надёжность"


def test_unknown_language_falls_back_to_russian():
    """Неизвестный язык не роняет интерфейс — отдаёт язык-источник."""
    assert make_t("DE")("Надёжность") == "Надёжность"
    assert get_glossary("DE") == get_glossary("RU")
    assert get_columns_help("DE") == get_columns_help("RU")


def test_missing_key_falls_back_to_russian():
    assert make_t("CS")("строка которой нет") == "строка которой нет"


def test_languages_registry():
    assert LANGUAGES == ("RU", "EN", "CS")


# ---------- живое приложение ----------

@pytest.fixture(scope="module")
def app_cs():
    at = AppTest.from_file("app.py", default_timeout=300)
    at.session_state["lang"] = "CS"
    return at.run()


def test_app_czech_renders(app_cs):
    """CS-версия поднимается без ошибок и переводит заголовок/метрики."""
    assert not app_cs.exception
    assert not app_cs.error
    assert "Optimální konfigurace" in [x.value for x in app_cs.title]
    labels = [m.label for m in app_cs.metric]
    assert "Roční náklady" in labels
    assert "Diesel" in labels


def test_app_czech_tabs_and_sidebar(app_cs):
    """Вкладки и ключевые контролы сайдбара — по-чешски."""
    tabs = [t.label for t in app_cs.tabs]
    for expected in ("Konfigurace", "Dispečink", "Ekonomika",
                     "Kontrola spolehlivosti", "Rizika a ceny", "Scénáře"):
        assert expected in tabs
    slider_labels = [s.label for s in app_cs.sidebar.slider]
    assert any("Cena nafty" in l for l in slider_labels)
    assert any("Provozní rezerva" in l for l in slider_labels)
    assert any("Přepočítat" in b.label for b in app_cs.sidebar.button)


def test_app_czech_has_no_russian_leftovers(app_cs):
    """В отрисованном CS-интерфейсе не осталось кириллицы: ни в
    подписях, ни в подсказках, ни в заголовках графиков."""
    import json

    cyr = re.compile(r"[а-яА-ЯёЁ]")
    texts: list[str] = []
    for coll in (app_cs.markdown, app_cs.caption):
        for el in coll:
            v = el.value
            texts.append("".join(v) if isinstance(v, list) else str(v))
    texts += [m.label for m in app_cs.metric]
    texts += [t.label for t in app_cs.tabs]
    for coll in (app_cs.sidebar.slider, app_cs.sidebar.selectbox,
                 app_cs.sidebar.checkbox, app_cs.sidebar.button):
        for el in coll:
            texts.append(el.label)
            texts.append(getattr(el, "help", "") or "")
    for el in app_cs.get("plotly_chart"):
        spec = json.loads(el.proto.spec)
        title = (spec.get("layout", {}).get("title", {}) or {}).get("text", "")
        texts.append(title)
        for tr in spec.get("data", []):
            texts.append(str(tr.get("name", "")))

    # «Язык / Language» — намеренно на всех языках сразу (label скрыт).
    leftovers = [t for t in texts if cyr.search(t)
                 and "Язык / Language" not in t]
    assert not leftovers, f"кириллица в CS-интерфейсе: {leftovers[:3]}"
