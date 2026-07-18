"""Типовые сутки (representative days) GreenHouse. Версия v1.3.

Зачем: полный год — это 8760 шагов; для LP это секунды, но MILP
(целые машины, стадирование) на таком горизонте не масштабируется.
Отраслевое решение (Calliope, Kotzur et al.) — кластеризовать 365
суток в K «типовых» и оптимизировать K*24 шага с ВЕСАМИ (сколько
реальных суток представляет каждый кластер). Сезонная батарея при
этом не теряется: двухуровневый SOC (см. optimize_sizing_representative)
связывает типовые сутки в полную 365-дневную цепочку.

Кластеризация — k-means по признаку «сутки»: вектор из 24 часов
нагрузки + 24 часов солнца (обе части нормированы, чтобы ни один
ряд не доминировал по масштабу). Реализация — чистый numpy
(детерминированная при фиксированном seed; k-means++-посев).
Представитель кластера — ЦЕНТРОИД (среднее суток кластера): средние
сохраняют годовую энергию точнее медоидов.

Ограничение v1: только часовой год (8760 точек, Δt = 1 ч) — ровно
тот случай, ради которого агрегация и нужна.
"""

from dataclasses import dataclass, field

import numpy as np

from src.schema import Scenario
from src.simulate import prepare_series

HOURS_PER_DAY = 24
DAYS_PER_YEAR = 365


@dataclass(frozen=True)
class RepresentativeYear:
    """Год, сжатый в K типовых суток.

    load_kw / solar_unit — матрицы (K, 24): профиль каждого кластера;
    weights — сколько реальных суток представляет кластер (Σ = 365);
    day_to_cluster — для каждых реальных суток номер кластера (365,).
    """

    load_kw: np.ndarray = field(repr=False)
    solar_unit: np.ndarray = field(repr=False)
    weights: np.ndarray
    day_to_cluster: np.ndarray = field(repr=False)
    dt_hours: float = 1.0

    @property
    def n_clusters(self) -> int:
        return len(self.weights)


def build_representative_year(
    scenario: Scenario,
    weather_csv: str | None = None,
    n_days: int = 12,
    seed: int = 0,
) -> RepresentativeYear:
    """Строит типовые сутки из часового года сценария."""
    load, dt_hours, solar_unit = prepare_series(scenario, weather_csv)
    if dt_hours != 1.0 or len(load) != DAYS_PER_YEAR * HOURS_PER_DAY:
        raise ValueError(
            "Типовые сутки поддерживают только часовой год (8760 точек); "
            f"получено {len(load)} точек с шагом {dt_hours} ч"
        )
    if not 1 <= n_days <= DAYS_PER_YEAR:
        raise ValueError(f"n_days должно быть в [1, 365], получено {n_days}")

    load_days = load.to_numpy(dtype=float).reshape(DAYS_PER_YEAR, HOURS_PER_DAY)
    solar_days = solar_unit.to_numpy(dtype=float).reshape(
        DAYS_PER_YEAR, HOURS_PER_DAY)

    # Признаки: нагрузка и солнце в одном векторе, каждая часть
    # нормирована своим максимумом (иначе кВт нагрузки задавили бы
    # безразмерное солнце).
    load_scale = max(load_days.max(), 1e-9)
    solar_scale = max(solar_days.max(), 1e-9)
    features = np.hstack([load_days / load_scale, solar_days / solar_scale])

    labels = _kmeans(features, n_days, seed)

    # Представители — центроиды по ИСХОДНЫМ (ненормированным) рядам.
    k = int(labels.max()) + 1
    load_c = np.zeros((k, HOURS_PER_DAY))
    solar_c = np.zeros((k, HOURS_PER_DAY))
    weights = np.zeros(k)
    for c in range(k):
        mask = labels == c
        weights[c] = mask.sum()
        load_c[c] = load_days[mask].mean(axis=0)
        solar_c[c] = solar_days[mask].mean(axis=0)

    return RepresentativeYear(
        load_kw=load_c,
        solar_unit=solar_c,
        weights=weights,
        day_to_cluster=labels,
        dt_hours=dt_hours,
    )


# ---------- приватные помощники ----------


def _kmeans(x: np.ndarray, k: int, seed: int, n_iter: int = 100) -> np.ndarray:
    """Детерминированный k-means (numpy): метки кластера для каждой строки.

    Посев — k-means++ (дальние точки вероятнее), фиксированный seed.
    Пустой кластер переселяется в самую дальнюю от центроидов точку.
    """
    rng = np.random.default_rng(seed)
    n = len(x)
    k = min(k, n)

    # k-means++: первый центр случайный, следующие — пропорционально
    # квадрату расстояния до ближайшего уже выбранного.
    centers = np.empty((k, x.shape[1]))
    centers[0] = x[rng.integers(n)]
    d2 = ((x - centers[0]) ** 2).sum(axis=1)
    for j in range(1, k):
        probs = d2 / d2.sum() if d2.sum() > 0 else np.full(n, 1 / n)
        centers[j] = x[rng.choice(n, p=probs)]
        d2 = np.minimum(d2, ((x - centers[j]) ** 2).sum(axis=1))

    labels = np.zeros(n, dtype=int)
    for _ in range(n_iter):
        dist = ((x[:, None, :] - centers[None, :, :]) ** 2).sum(axis=2)
        new_labels = dist.argmin(axis=1)
        if (new_labels == labels).all() and _ > 0:
            break
        labels = new_labels
        for c in range(k):
            mask = labels == c
            if mask.any():
                centers[c] = x[mask].mean(axis=0)
            else:  # пустой кластер -> самая дальняя точка
                far = dist.min(axis=1).argmax()
                centers[c] = x[far]
                labels[far] = c
    return labels
