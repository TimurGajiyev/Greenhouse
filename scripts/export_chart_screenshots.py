"""Скриншоты всех графиков приложения -> results/charts/*.png.

Запуск из корня проекта (с активированным .venv):
    python scripts/export_chart_screenshots.py [RU|EN]

Как работает: AppTest рендерит app.py без браузера, из каждого
plotly-элемента извлекается JSON-спецификация фигуры (proto.spec),
фигура восстанавливается и пишется в PNG через kaleido. Это те же
самые фигуры, что видит пользователь, — с живыми данными базового
сценария.
"""

import json
import re
import sys
from pathlib import Path

import plotly.graph_objects as go
from streamlit.testing.v1 import AppTest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

OUT_DIR = Path("results/charts")


def slug(text: str, fallback: str) -> str:
    text = text.strip() or fallback
    text = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE)
    text = re.sub(r"[\s]+", "_", text)
    return text[:60]


def main() -> None:
    lang = sys.argv[1].upper() if len(sys.argv) > 1 else "RU"
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    at = AppTest.from_file("app.py", default_timeout=300)
    if lang == "EN":
        at.session_state["lang"] = "EN"
    at.run()
    assert not at.exception, at.exception

    els = at.get("plotly_chart")
    print(f"Фигур в рендере ({lang}): {len(els)}")
    for i, el in enumerate(els, 1):
        spec = json.loads(el.proto.spec)
        fig = go.Figure(spec)
        title = (spec.get("layout", {}).get("title", {}) or {}).get("text", "")
        kind = spec["data"][0].get("type", "scatter") if spec["data"] else "x"
        name = f"{i:02d}_{slug(title, kind)}_{lang}.png"
        path = OUT_DIR / name
        fig.write_image(str(path), width=1000, height=520, scale=1)
        print(f"  {path}")
    print("Готово.")


if __name__ == "__main__":
    main()
