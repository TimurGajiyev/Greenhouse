"""Солнечный профиль GreenHouse. Версия v0.3 (шаг 4).

Что делает модуль: строит почасовой годовой ряд УДЕЛЬНОЙ выработки —
kW переменного тока на 1 kWp установленной мощности панелей.
Дальше симулятор (шаг 5) и оптимизатор (шаги 7-8) просто умножают
этот ряд на размер системы: pv_gen[t] = pv_kwp * profile[t].
Тот же приём у REopt: там это "production factor" (безразмерный ряд
0..~1, см. reference/REopt.jl-master/src/core/production_factor.jl).

Откуда погода: TMY (Typical Meteorological Year — "типичный
метеорологический год"): для каждого календарного месяца из многолетнего
архива (у PVGIS — 2005-2023) выбран самый ТИПИЧНЫЙ реальный месяц,
и из 12 таких месяцев склеен один "средний" год. Мы считаем не
"как было в 2023", а "как бывает обычно".

Три компоненты солнечной облучённости (irradiance, Вт/м^2):
  GHI (Global Horizontal Irradiance)  — вся энергия на горизонтальную
      площадку: прямые лучи + рассеянный свет неба;
  DNI (Direct Normal Irradiance)      — только прямые лучи, на площадку,
      постоянно повёрнутую "лицом" к солнцу;
  DHI (Diffuse Horizontal Irradiance) — только рассеянный свет неба
      (без прямых лучей) на горизонтальную площадку.
Панель наклонена, поэтому по этим трём компонентам пересчитываем
облучённость её плоскости (POA — plane of array) — это называется
transposition (транспозиция).

Модель панели — PVWatts (NREL): упрощённая, но отраслевой стандарт
первого приближения; её же зовёт REopt через свой API.

Источники погоды по приоритету:
  1) PVGIS (сервис Евросоюза, спутниковая база SARAH3) — основной;
  2) NASA POWER — запасной (но это фактический год, не TMY);
  3) кэшированный файл tests/data/ — оффлайн-режим, честно сообщаем.
"""

import warnings

import numpy as np
import pandas as pd
import pvlib

from src.profiles import BASE_YEAR, HOURS_PER_YEAR
from src.schema import Scenario

# ---------- параметры модели (все именованные, чтобы было видно,
# ---------- что именно мы предполагаем, и легко менять) ----------

# Дефолтная геометрия, если сценарий её не задал — как в REopt
# (reference/REopt.jl-master/src/core/pv.jl):
# ASSUMPTION: наклон 20 градусов — дефолт REopt для крышных систем
# (array_type=1, "Rooftop, Fixed"); у вендора точного угла нет.
DEFAULT_TILT_DEG = 20.0

# Потери системы по категориям, в ПРОЦЕНТАХ (как в PVWatts).
# Значения — дефолты PVWatts v5, кроме soiling.
# ASSUMPTION: soiling (загрязнение панелей) поднят с дефолтных 2% до 5%
# из-за песка/пыли в Йемене — цифра из рисков CLAUDE.md; точное значение
# могла бы дать статистика очистки панелей на площадке.
LOSSES_PERCENT = dict(
    soiling=5.0,       # загрязнение (песок, пыль)
    shading=3.0,       # затенение соседними объектами
    snow=0.0,          # снег — в Йемене не бывает
    mismatch=2.0,      # разброс характеристик панелей в цепочке
    wiring=2.0,        # потери в проводах DC-стороны
    connections=0.5,   # потери в контактах/разъёмах
    lid=1.5,           # LID (light-induced degradation) — быстрая потеря
                       # первых часов работы кремниевой панели на свету
    nameplate_rating=1.0,  # реальная мощность чуть ниже паспортной таблички
    age=0.0,           # старение — v1 не моделирует (см. вне scope)
    availability=3.0,  # простои на обслуживание/поломки
)

# Температурный коэффициент мощности gamma (доля/°C): на сколько падает
# мощность панели на каждый градус нагрева ячейки выше 25 °C.
# ASSUMPTION: -0.47%/°C — дефолт PVWatts v5 для module_type=0 (standard,
# кристаллический кремний); у вендора N-type TOPCon чуть лучше (~-0.30),
# точное значение — в datasheet панели.
GAMMA_PDC_PER_C = -0.0047

# КПД инвертора (номинальный) и отношение DC/AC — дефолты REopt/PVWatts.
INVERTER_EFFICIENCY = 0.96
DC_AC_RATIO = 1.2

# Кэшированная погода для оффлайн-режима (скачана с PVGIS 2026-07-12,
# база SARAH3, годы 2005-2023, площадка Сана 15.28N 44.08E).
# Известный артефакт ИСХОДНЫХ данных PVGIS: 16 октября облучённость
# нулевая весь день (пропуск спутниковых данных). Оставлено как есть —
# данные не подделываем; де-факто это готовый "день песчаной бури"
# (~0.3% годовой выработки).
CACHED_WEATHER_CSV = "tests/data/tmy_sanaa_pvgis_sarah3.csv"

# Насколько далеко (в градусах) координаты сценария могут отходить от
# площадки кэшированного файла, чтобы кэш ещё считался пригодным.
CACHE_COORD_TOLERANCE_DEG = 0.1

# Координаты площадки кэшированного файла (Сана).
CACHED_WEATHER_LAT = 15.2811
CACHED_WEATHER_LON = 44.0811


def build_solar_profile(
    scenario: Scenario, weather_csv: str | None = None
) -> pd.Series:
    """Строит почасовой годовой ряд удельной выработки PV.

    Возвращает pandas.Series с именем "solar_kw_per_kwp":
    kW переменного тока на 1 kWp панелей, индекс — те же 8760 часов
    года BASE_YEAR в поясе площадки, что и у профиля нагрузки.

    weather_csv — путь к кэшированному погодному файлу; None означает
    "сначала пробуем интернет (PVGIS, затем NASA POWER), затем кэш".
    """
    site = scenario.site

    # 1) Погода: DataFrame с колонками ghi/dni/dhi/temp_air/wind_speed
    #    и почасовым UTC-индексом года BASE_YEAR.
    weather = _get_weather(site.latitude, site.longitude, weather_csv)

    # 2) Геометрия панели: из сценария или дефолты в стиле REopt.
    tilt, azimuth = _resolve_geometry(scenario)

    # 3) Физика PVWatts: погода -> kW на 1 kWp (индекс пока UTC).
    ac_per_kwp = _pvwatts_ac_per_kwp(
        weather, site.latitude, site.longitude, tilt, azimuth
    )

    # 4) Переставляем ряд на местную ось времени площадки — чтобы он
    #    совпал с профилем нагрузки час в час.
    return _to_local_year_grid(ac_per_kwp, site.timezone)


# ---------- приватные помощники ----------


def _get_weather(lat: float, lon: float, weather_csv: str | None) -> pd.DataFrame:
    """Достаёт погодный год: явный файл / PVGIS / NASA POWER / кэш."""
    if weather_csv is not None:
        return _read_weather_csv(weather_csv)

    try:
        return _fetch_pvgis_tmy(lat, lon)
    except Exception as e:  # сеть недоступна или сервис лежит
        warnings.warn(f"PVGIS недоступен ({e}); пробую NASA POWER")

    try:
        return _fetch_nasa_power_year(lat, lon)
    except Exception as e:
        warnings.warn(f"NASA POWER недоступен ({e}); пробую локальный кэш")

    # Оффлайн-режим: кэш пригоден только для "своей" площадки —
    # погода Саны не годится для другой точки мира.
    if (
        abs(lat - CACHED_WEATHER_LAT) <= CACHE_COORD_TOLERANCE_DEG
        and abs(lon - CACHED_WEATHER_LON) <= CACHE_COORD_TOLERANCE_DEG
    ):
        warnings.warn(
            "Интернета нет — использую кэшированный TMY "
            f"({CACHED_WEATHER_CSV}, PVGIS SARAH3, скачан 2026-07-12)"
        )
        return _read_weather_csv(CACHED_WEATHER_CSV)

    raise RuntimeError(
        "Не удалось получить погоду: PVGIS и NASA POWER недоступны, "
        f"а кэш {CACHED_WEATHER_CSV} снят для другой площадки "
        f"({CACHED_WEATHER_LAT}, {CACHED_WEATHER_LON}). "
        "Подключи интернет или положи свой погодный CSV."
    )


def _fetch_pvgis_tmy(lat: float, lon: float) -> pd.DataFrame:
    """Скачивает TMY с PVGIS и приводит к нашему формату.

    coerce_year=BASE_YEAR: месяцы TMY взяты из разных реальных лет,
    поэтому pvlib "переклеивает" их на один условный год — наш опорный.
    map_variables=True переименовывает колонки в стандарт pvlib
    (ghi/dni/dhi/temp_air/wind_speed).
    """
    data, _meta = pvlib.iotools.get_pvgis_tmy(
        lat, lon, map_variables=True, coerce_year=BASE_YEAR
    )
    return data[["ghi", "dni", "dhi", "temp_air", "wind_speed"]]


def _fetch_nasa_power_year(lat: float, lon: float) -> pd.DataFrame:
    """Запасной источник: NASA POWER, фактический 2023 год.

    Честное отличие от TMY: это погода КОНКРЕТНОГО года, а не
    "типичного", поэтому предупреждаем пользователя.
    """
    warnings.warn(
        "NASA POWER отдаёт фактический 2023 год, а не TMY — "
        "результат может отличаться от типичного"
    )
    data, _meta = pvlib.iotools.get_nasa_power(
        lat,
        lon,
        start=pd.Timestamp(2023, 1, 1, tz="UTC"),
        end=pd.Timestamp(2023, 12, 31, 23, tz="UTC"),
        map_variables=True,
    )
    data = data[["ghi", "dni", "dhi", "temp_air", "wind_speed"]]
    # Переносим отметки на опорный год (2023 тоже невисокосный: 8760 ч).
    data.index = data.index.map(lambda ts: ts.replace(year=BASE_YEAR))
    return data


def _read_weather_csv(path: str) -> pd.DataFrame:
    """Читает кэшированный погодный файл (формат — как сохранил шаг 4).

    Колонки: time_utc,ghi,dni,dhi,temp_air,wind_speed; отметки в UTC.
    """
    df = pd.read_csv(path, index_col="time_utc", parse_dates=True)

    required = {"ghi", "dni", "dhi", "temp_air", "wind_speed"}
    if not required.issubset(df.columns):
        raise ValueError(
            f"Погодный CSV {path}: нужны колонки {sorted(required)}, "
            f"найдены {list(df.columns)}"
        )
    if df.index.tz is None:
        # Наивные отметки в погодном файле считаем UTC (так сохраняет
        # PVGIS); это НЕ местное время площадки, в отличие от load-CSV.
        df = df.tz_localize("UTC")
    if len(df) != HOURS_PER_YEAR:
        raise ValueError(
            f"Погодный CSV {path}: ожидалось {HOURS_PER_YEAR} часов, "
            f"найдено {len(df)}"
        )
    return df


def _resolve_geometry(scenario: Scenario) -> tuple[float, float]:
    """Наклон и азимут панели: из сценария или дефолты REopt."""
    pv = scenario.pv
    lat = scenario.site.latitude

    tilt = pv.tilt_deg if pv is not None and pv.tilt_deg is not None else DEFAULT_TILT_DEG

    if pv is not None and pv.azimuth_deg is not None:
        azimuth = pv.azimuth_deg
    else:
        # В северном полушарии панель смотрит на юг (180°), в южном —
        # на север (0°): туда, где солнце проводит большую часть дня.
        azimuth = 180.0 if lat >= 0 else 0.0

    return tilt, azimuth


def _pvwatts_ac_per_kwp(
    weather: pd.DataFrame,
    lat: float,
    lon: float,
    tilt: float,
    azimuth: float,
) -> pd.Series:
    """Цепочка PVWatts: погода -> kW переменного тока на 1 kWp.

    Шаги (каждый — стандартная функция pvlib):
      положение солнца -> облучённость плоскости панели (POA) ->
      температура ячейки -> DC-мощность -> потери -> инвертор.
    """
    times = weather.index

    # 1) Положение солнца для каждого часа: зенитный угол (zenith —
    #    угол между солнцем и вертикалью; >90° = солнце под горизонтом)
    #    и азимут солнца.
    solpos = pvlib.solarposition.get_solarposition(times, lat, lon)

    # 2) Транспозиция: GHI/DNI/DHI -> облучённость наклонной плоскости
    #    панели (POA). Модель haydavies — компромисс точность/простота;
    #    dni_extra — внеатмосферная облучённость, нужна этой модели.
    #    (PVWatts официально использует более сложную модель Perez —
    #    для v1 разница в пределах пары процентов.)
    dni_extra = pvlib.irradiance.get_extra_radiation(times)
    poa = pvlib.irradiance.get_total_irradiance(
        surface_tilt=tilt,
        surface_azimuth=azimuth,
        solar_zenith=solpos["apparent_zenith"],
        solar_azimuth=solpos["azimuth"],
        dni=weather["dni"],
        ghi=weather["ghi"],
        dhi=weather["dhi"],
        dni_extra=dni_extra,
        model="haydavies",
    )
    # poa_global — суммарная облучённость плоскости панели, Вт/м^2.
    # fillna(0): ночью формулы дают NaN (нет солнца) — это честный ноль.
    poa_global = poa["poa_global"].fillna(0.0)

    # 3) Температура ячейки: чем жарче ячейка, тем ниже мощность.
    #    Модель SAPM с параметрами close_mount_glass_glass —
    #    панели вплотную к крыше охлаждаются хуже, чем на раме.
    # ASSUMPTION: тип монтажа close_mount — по фото вендора не ясно;
    #    вариант open_rack дал бы на ~1-2% больше выработки.
    temp_params = pvlib.temperature.TEMPERATURE_MODEL_PARAMETERS["sapm"][
        "close_mount_glass_glass"
    ]
    cell_temp = pvlib.temperature.sapm_cell(
        poa_global, weather["temp_air"], weather["wind_speed"], **temp_params
    )

    # 4) DC-мощность на 1 kWp: формула PVWatts
    #    P = P_ном * (POA/1000) * (1 + gamma * (T_ячейки - 25)).
    #    pdc0=1.0 значит "система номиналом 1 кВт" — получаем удельный ряд.
    pdc = pvlib.pvsystem.pvwatts_dc(
        poa_global, cell_temp, pdc0=1.0, gamma_pdc=GAMMA_PDC_PER_C
    )

    # 5) Системные потери одним множителем: pvwatts_losses комбинирует
    #    категории (проценты) в суммарный процент потерь.
    loss_percent = pvlib.pvsystem.pvwatts_losses(**LOSSES_PERCENT)
    pdc = pdc * (1 - loss_percent / 100.0)

    # 6) Инвертор: DC -> AC с КПД и "срезкой" (clipping) — инвертор
    #    рассчитан на 1/DC_AC_RATIO от мощности панелей, всё сверх его
    #    номинала теряется. pdc0 здесь — DC-предел ИНВЕРТОРА.
    ac = pvlib.inverter.pvwatts(
        pdc, pdc0=1.0 / DC_AC_RATIO, eta_inv_nom=INVERTER_EFFICIENCY
    )

    # Ночью инвертор "выключен" — формула даёт NaN; и защищаемся от
    # микроскопических отрицательных значений плавающей точки.
    return ac.fillna(0.0).clip(lower=0.0)


def _to_local_year_grid(series_utc: pd.Series, tz: str) -> pd.Series:
    """Переставляет UTC-ряд на местную ось времени площадки.

    Проблема: погода и расчёт живут в UTC, а профиль нагрузки — в поясе
    площадки (Asia/Aden = UTC+3). Простой tz_convert сдвинул бы ряд на
    3 часа В СОСЕДНИЙ ГОД (последние часы 31 декабря стали бы 1 января
    следующего года) — и индексы с нагрузкой не совпали бы.

    Решение — "прокрутка" (roll), стандартный приём для TMY: значения
    циклически сдвигаются на смещение пояса, последние часы года
    заворачиваются в его начало. Год ведь ТИПИЧНЫЙ, а не реальный —
    склейка "31 декабря -> 1 января" здесь так же условна, как и склейка
    месяцев из разных лет внутри самого TMY.
    """
    # Смещение пояса площадки от UTC в часах (у Adena это ровно +3).
    target_index = pd.date_range(
        start=f"{BASE_YEAR}-01-01 00:00",
        periods=HOURS_PER_YEAR,
        freq="h",
        tz=tz,
    )
    offset_hours = target_index[0].utcoffset().total_seconds() / 3600.0

    # Дробные смещения (например Иран +3:30) потребовали бы интерполяции —
    # v1 поддерживает только целочасовые пояса.
    if offset_hours != int(offset_hours):
        raise ValueError(
            f"Пояс {tz}: смещение {offset_hours} ч не целое — "
            "v1 поддерживает только целочасовые пояса"
        )

    # np.roll сдвигает массив по кругу: значение UTC-полуночи 1 января
    # должно встать на позицию местных 03:00 (индекс 3 при UTC+3).
    values = np.roll(series_utc.to_numpy(), int(offset_hours))

    return pd.Series(values, index=target_index, name="solar_kw_per_kwp")
