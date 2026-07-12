"""Профили GreenHouse: потребление и генерация во времени. Версия v0.2.

Что нового: build_load_profile стал диспетчером двух режимов —
синтетический профиль (как в v0.1) ИЛИ реальный временной ряд из CSV.
Формат CSV: две колонки с заголовком "timestamp,load_kw"; шаг ряда —
любой РАВНОМЕРНЫЙ (час, полчаса, сутки). Длительность шага для формулы
E = P * t все последующие слои берут из timestep_hours, а не считают
равной одному часу.

Профиль солнца (шаг 4) живёт в отдельном модуле src/solar.py.
"""

import numpy as np
import pandas as pd

from src.schema import Scenario

# Опорный год синтетического профиля. 2026 — невисокосный:
# 365 * 24 = 8760 часов.
BASE_YEAR = 2026
HOURS_PER_YEAR = 8760


def build_load_profile(scenario: Scenario) -> pd.Series:
    """Строит профиль нагрузки; выбор режима — по содержимому сценария.

    Возвращает pandas.Series с именем "load_kw" и timezone-aware
    индексом DatetimeIndex в часовом поясе площадки.
    Валидатор LoadConfig уже гарантировал, что заполнен ровно один
    режим, поэтому здесь достаточно простого ветвления (dispatch).
    """
    if scenario.load.profile_csv is not None:
        return _load_profile_from_csv(
            scenario.load.profile_csv, scenario.site.timezone
        )
    return _build_synthetic_profile(scenario)


def _build_synthetic_profile(scenario: Scenario) -> pd.Series:
    """Синтетический профиль: day_kw в рабочие часы, night_kw в остальные.

    Имя начинается с подчёркивания — соглашение Python: "внутренняя
    функция модуля, снаружи вызывай build_load_profile".
    """
    load = scenario.load

    # 1) Ось времени: 8760 почасовых отметок в поясе площадки.
    index = pd.date_range(
        start=f"{BASE_YEAR}-01-01 00:00",
        periods=HOURS_PER_YEAR,
        freq="h",
        tz=scenario.site.timezone,
    )

    # 2) Булева маска рабочих часов. Конец смены — СТРОГО меньше:
    #    по соглашению полуинтервала start <= X < end получаем
    #    ровно 10 рабочих часов для смены 8..18.
    is_work_hour = (index.hour >= load.work_start_hour) & (
        index.hour < load.work_end_hour
    )

    # 3) np.where(маска, A, B): где True — day_kw, иначе night_kw.
    values = np.where(is_work_hour, load.day_kw, load.night_kw)

    # 4) Значения + ось времени = именованный временной ряд.
    return pd.Series(values, index=index, name="load_kw")


def _load_profile_from_csv(path: str, tz: str) -> pd.Series:
    """Читает реальный временной ряд нагрузки из CSV.

    Ожидаемый формат файла (первая строка — заголовок):
        timestamp,load_kw
        2026-01-01 00:00,412.5
        ...
    Требования к ряду: минимум две строки, без дубликатов отметок,
    РАВНОМЕРНЫЙ шаг. Наивные отметки (без пояса) трактуются как
    местное время площадки.
    """
    df = pd.read_csv(path)

    # Проверяем структуру файла и падаем с понятным сообщением.
    required = {"timestamp", "load_kw"}
    if not required.issubset(df.columns):
        raise ValueError(
            f"CSV {path}: нужны колонки 'timestamp' и 'load_kw', "
            f"найдены {list(df.columns)}"
        )

    # Текстовые отметки -> DatetimeIndex; сортируем по времени.
    index = pd.DatetimeIndex(pd.to_datetime(df["timestamp"]))
    series = pd.Series(
        df["load_kw"].to_numpy(dtype=float), index=index, name="load_kw"
    ).sort_index()

    if len(series) < 2:
        raise ValueError(f"CSV {path}: нужен минимум две строки данных")
    if series.index.has_duplicates:
        raise ValueError(f"CSV {path}: в ряду есть повторяющиеся отметки времени")

    # Часовой пояс: tz_localize присваивает пояс наивному индексу,
    # tz_convert переводит уже "знающий пояс" индекс в пояс площадки.
    if series.index.tz is None:
        series = series.tz_localize(tz)
    else:
        series = series.tz_convert(tz)

    # Равномерность шага: timestep_hours (ниже) читает один Δt,
    # поэтому неравномерные ряды (например месячные: 28..31 день)
    # пока не поддержаны — им нужен массив весов шагов; это
    # запланированное расширение (аналог snapshot_weightings в PyPSA).
    n_unique_steps = series.index.to_series().diff().dropna().nunique()
    if n_unique_steps > 1:
        raise ValueError(
            f"CSV {path}: шаг ряда неравномерный. v0 поддерживает только "
            "равномерные ряды (час/полчаса/сутки); месячные данные — "
            "будущее расширение с весами шагов"
        )

    return series


def timestep_hours(series: pd.Series) -> float:
    """Длительность одного шага ряда в часах (Δt).

    Зачем: энергия = мощность * время (E = P * t). Симулятор и
    экономика берут Δt отсюда, а не считают его равным 1 часу, —
    поэтому ядро одинаково работает с часовыми (Δt=1), получасовыми
    (Δt=0.5) и суточными (Δt=24) данными. Тот же приём у больших
    игроков: time_steps_per_hour в REopt, snapshot_weightings в PyPSA.
    """
    delta = series.index[1] - series.index[0]
    return delta.total_seconds() / 3600.0
