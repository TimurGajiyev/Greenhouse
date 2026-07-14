"""Перегенерация эталонных .lp-файлов (паттерн math-тестов Calliope).

Запуск из корня проекта:
    python scripts/regen_lp_baselines.py

Когда запускать: ТОЛЬКО после ОСОЗНАННОГО изменения математики модели
(новая переменная, ограничение, коэффициент). Тест
tests/test_improvements.py::test_lp_snapshot_matches_baseline сравнит
текущую формулировку с этими эталонами и упадёт при любом расхождении.
"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.schema import Scenario
from src.optimize import optimize_dispatch, optimize_sizing

# Тот же игрушечный сценарий, что в tests/test_improvements.py.
from tests.test_improvements import toy_battery_diesel

BASELINE_DIR = Path("tests/data/lp_baselines")


def main() -> None:
    BASELINE_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        optimize_dispatch(
            toy_battery_diesel(Path(tmp)), write_outputs=False,
            lp_snapshot_path=str(BASELINE_DIR / "toy_dispatch.lp"),
        )
        optimize_sizing(
            toy_battery_diesel(Path(tmp), open_dg=True), write_outputs=False,
            lp_snapshot_path=str(BASELINE_DIR / "toy_sizing.lp"),
        )
    print(f"эталоны обновлены в {BASELINE_DIR}/ — проверь диф и закоммить осознанно")


if __name__ == "__main__":
    main()
