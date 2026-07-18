"""SPORES GreenHouse: почти-оптимальные альтернативные дизайны.
Версия v1.3 (аудит №3; перенос идеи spores.yaml / SPORES-режима Calliope).

SPORES (Spatially/technologically-explicit Practically Optimal REsultS):
один оптимум — это ТОЧКА, а заказчику нужен ВЫБОР. Метод: зафиксировать
потолок издержек «оптимум + slack» (например +10%) и искать конфигурации,
МАКСИМАЛЬНО НЕПОХОЖИЕ на уже найденные, — целевая функция становится
Σ score_i * size_i, где score растёт у технологий, которые уже
использовались (скоринг relative_deployment Calliope: += size/upper).

Выход — веер дизайнов «почти той же цены, но другого железа»: аргумент
в переговорах («если батареи подорожают — вот вариант с меньшей BESS
за +7% издержек»).
"""

from dataclasses import dataclass, field

from src.optimize import optimize_sizing
from src.schema import Scenario

SIZE_KEYS = ("pv_kwp", "batt_kwh", "batt_kw", "dg_kw")


@dataclass(frozen=True)
class SporeDesign:
    """Один дизайн: размеры, штуки, честные годовые издержки."""

    name: str
    sizes: dict
    units: dict
    cost_usd_per_year: float
    lpsp: float | None


@dataclass(frozen=True)
class SporesReport:
    base: SporeDesign
    spores: list[SporeDesign] = field(default_factory=list)
    cost_cap_usd_per_year: float = 0.0
    slack_fraction: float = 0.0


def find_spores(
    scenario: Scenario,
    weather_csv: str | None = None,
    n_spores: int = 3,
    slack: float = 0.10,
    solver: str | None = None,
) -> SporesReport:
    """Ищет n_spores почти-оптимальных альтернатив оптимуму.

    slack — допустимая наценка к издержкам оптимума (0.10 = +10%).
    """
    if n_spores < 1:
        raise ValueError(f"SPORES: n_spores >= 1, получено {n_spores}")
    if slack <= 0:
        raise ValueError(f"SPORES: slack должен быть > 0, получено {slack}")

    base = optimize_sizing(scenario, weather_csv=weather_csv,
                           write_outputs=False, solver=solver)
    base_cost = base.sim.manifest["objective_value"]
    cap = (1.0 + slack) * base_cost

    # Нормировка скоринга — верх коридора каждой технологии.
    uppers = {
        "pv_kwp": scenario.pv.max_kw if scenario.pv else 1.0,
        "batt_kwh": scenario.battery.max_kwh if scenario.battery else 1.0,
        "batt_kw": scenario.battery.max_kw if scenario.battery else 1.0,
        "dg_kw": scenario.diesel.max_kw if scenario.diesel else 1.0,
    }

    def design(name, res, cost) -> SporeDesign:
        return SporeDesign(
            name=name,
            sizes=dict(res.sizes),
            units=dict(res.units),
            cost_usd_per_year=float(cost),
            lpsp=res.sim.manifest.get("lpsp"),
        )

    report_base = design("optimum", base, base_cost)
    scores = {k: 0.0 for k in SIZE_KEYS}
    prev = base.sizes
    spores: list[SporeDesign] = []

    for i in range(1, n_spores + 1):
        # relative_deployment: чем больше техника использовалась в
        # предыдущем дизайне, тем дороже её повторять.
        for k in SIZE_KEYS:
            if prev.get(k, 0.0) > 1e-6:
                scores[k] += prev[k] / max(uppers[k], 1e-9)
        spore = optimize_sizing(
            scenario, weather_csv=weather_csv, write_outputs=False,
            solver=solver, cost_cap=cap, spore_scores=dict(scores),
        )
        cost = spore.sim.manifest["spores"]["cost_value"]
        spores.append(design(f"spore_{i}", spore, cost))
        prev = spore.sizes

    return SporesReport(
        base=report_base,
        spores=spores,
        cost_cap_usd_per_year=float(cap),
        slack_fraction=slack,
    )
