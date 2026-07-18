"""Схема входных данных GreenHouse. Версия v0.2.

Что нового по сравнению с v0.1 (и зачем):
1. Блоки технологий (pv, battery, diesel) стали НЕОБЯЗАТЕЛЬНЫМИ —
   отсутствие блока в JSON означает "этой технологии в проекте нет".
   Так же устроен REopt: технология строится, только если её ключ
   присутствует во входных данных.
2. У технологий появились размеры ЕДИНИЦЫ оборудования (unit_kw,
   unit_kwh) — чтобы из непрерывного оптимального размера (кВт, кВт*ч)
   получать целое число модулей / шкафов / генераторов к закупке.
3. Блок load поддерживает ДВА режима: синтетический профиль
   (day_kw/night_kw/часы смены) ИЛИ реальный временной ряд из CSV
   (profile_csv) — под будущие проекты с часовыми/суточными данными.

Каждый класс — модель (model) pydantic: описание полей (fields)
входного JSON, их типов и границ. При загрузке pydantic выполняет
валидацию и возбуждает ValidationError с путём до виновного поля.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SiteConfig(BaseModel):
    """Площадка: где физически стоит система."""

    # extra="forbid" — запрет неизвестных ключей во входном JSON:
    # опечатка в имени ключа становится громкой ошибкой, а не тихой дырой.
    model_config = ConfigDict(extra="forbid")

    name: str

    # Field(ge=..., le=...) — ограничения (constraints) значения:
    # ge/le = больше-или-равно / меньше-или-равно.
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)

    # Часовой пояс IANA (например "Asia/Aden"): профиль нагрузки и
    # профиль солнца обязаны жить в одном местном времени.
    timezone: str

    # Площадь под панели, м² (опционально, новое в шаге 8): потолок
    # для сайзера — pv_kwp * m2_per_kwp <= roof_area_m2.
    # None = ограничения площади нет.
    roof_area_m2: float | None = Field(default=None, gt=0)


class PVConfig(BaseModel):
    """Солнечные панели (PV — photovoltaics)."""

    model_config = ConfigDict(extra="forbid")

    # CAPEX (capital expenditure) — капитальные затраты: разовая цена
    # покупки и монтажа, задана "за 1 кВт" для масштабирования.
    capex_usd_per_kw: float = Field(gt=0)

    # O&M (operation and maintenance) — эксплуатация и обслуживание,
    # ежегодные расходы; часть OPEX (операционных затрат).
    om_usd_per_kw_year: float = Field(ge=0)

    # Коридор допустимого размера системы, кВт:
    # min == max — размер зафиксирован; min < max — выбирает оптимизатор.
    min_kw: float = Field(ge=0)
    max_kw: float = Field(gt=0)

    # Мощность ОДНОЙ панели, кВт (580 Вт = 0.58). Тип "float | None"
    # читается: число ИЛИ None; default=None делает поле необязательным.
    # None означает "перевод в штуки не нужен". Если задано — слой
    # результатов посчитает число панелей: ceil(размер / unit_kw).
    unit_kw: float | None = Field(default=None, gt=0)

    # Геометрия установки панелей (новое в шаге 4, оба поля необязательны).
    # tilt_deg — наклон панели от горизонтали в градусах: 0 = лежит
    # плашмя, 90 = стоит вертикально.
    # azimuth_deg — куда "смотрит" панель по сторонам света: 0 = север,
    # 90 = восток, 180 = юг, 270 = запад.
    # None = solar.py возьмёт дефолты в стиле REopt/PVWatts
    # (крыша: наклон 20°, азимут в сторону экватора).
    tilt_deg: float | None = Field(default=None, ge=0, le=90)
    azimuth_deg: float | None = Field(default=None, ge=0, lt=360)

    # Сколько м² крыши занимает 1 kWp (опционально, шаг 8). None =
    # сайзер возьмёт дефолт с пометкой ASSUMPTION (см. optimize.py).
    m2_per_kwp: float | None = Field(default=None, gt=0)

    # Запас на слабый год солнца (аудит №2, изъян №3): множитель на весь
    # удельный ряд выработки. TMY — медианный год (P50): в половине
    # реальных лет солнца МЕНЬШЕ (кейс OKC: факт −4.2% от TMY). Отрасль
    # (Solargis, NREL SAM) для критичных офф-грид систем рекомендует
    # P90 ≈ 0.95. None = 1.0 (P50 как есть).
    resource_scale_fraction: float | None = Field(default=None, gt=0.5, le=1.2)

    # Деградация панелей, доля/год (аудит №3): выработка усредняется по
    # жизни левелизационным коэффициентом (REopt utils.jl:54,
    # levelization_factor; их дефолт 0.5%/год) — панель года №20 не
    # считается новой. None = 0 (без деградации, прежнее поведение).
    degradation_fraction_per_year: float | None = Field(
        default=None, ge=0, lt=0.1)

    # Параметры PV-модуля и инвертора (v1.1: подняты из констант
    # solar.py в контракт по итогам верификационных кейсов OKC и NIST —
    # у вендоров эти числа в datasheet). None = дефолты solar.py.
    inverter_eff_fraction: float | None = Field(default=None, gt=0, le=1)
    dc_ac_ratio: float | None = Field(default=None, gt=0)
    # Температурный коэффициент мощности, доля/°C (отрицательный:
    # -0.0047 = -0.47%/°C — стандартный кристаллический кремний).
    gamma_pdc_per_c: float | None = Field(default=None, ge=-0.02, lt=0)
    # Тип монтажа для температурной модели: close_mount — вплотную к
    # крыше (греется сильнее), open_rack — на раме/земле (охлаждается).
    mount_type: Literal["close_mount", "open_rack"] | None = None

    # Срок службы, лет — вход для CRF (capital recovery factor,
    # формула превращения разовой покупки в равные годовые платежи).
    lifetime_years: int = Field(gt=0)

    # Декоратор @model_validator(mode="after") регистрирует метод как
    # проверку ПОСЛЕ валидации всех полей — для правил, связывающих
    # несколько полей сразу. self — созданный экземпляр (instance).
    @model_validator(mode="after")
    def validate_size_corridor(self):
        if self.max_kw < self.min_kw:
            raise ValueError("PV: max_kw не может быть меньше min_kw")
        return self  # валидатор режима "after" обязан вернуть экземпляр


class BatteryConfig(BaseModel):
    """Аккумуляторная система (BESS — battery energy storage system).

    У батареи ДВА независимых размера: ёмкость (кВт*ч — сколько
    хранит) и мощность (кВт — как быстро отдаёт/принимает).
    """

    model_config = ConfigDict(extra="forbid")

    capex_usd_per_kwh: float = Field(gt=0)

    # Цена за 1 кВт мощности — это цена PCS (power conversion system,
    # силовой преобразователь). 0 допустим: PCS уже в цене шкафов.
    capex_usd_per_kw: float = Field(ge=0)

    om_usd_per_kwh_year: float = Field(ge=0)

    # RTE (round-trip efficiency) — КПД полного цикла "зарядил-разрядил",
    # доля 0..1. gt=0 и le=1: КПД 0 — мусор, выше 1 — вечный двигатель.
    rte_fraction: float = Field(gt=0, le=1)

    # SOC (state of charge) — уровень заряда; ниже этой доли не
    # разряжаем, чтобы беречь ресурс ячеек.
    soc_min_fraction: float = Field(ge=0, lt=1)

    # Саморазряд: какая ДОЛЯ запаса утекает за один час простоя
    # (паттерн storage_loss из Calliope: множитель (1-loss)^Δt в
    # SOC-динамике). None = 0 (не моделируем). Для LFP-химии типично
    # ~1-2% в МЕСЯЦ, то есть ~2e-5 в час — уточнить по datasheet.
    self_discharge_fraction_per_hour: float | None = Field(
        default=None, ge=0, lt=1
    )

    # Коридоры двух размеров.
    min_kwh: float = Field(ge=0)
    max_kwh: float = Field(gt=0)
    min_kw: float = Field(ge=0)
    max_kw: float = Field(gt=0)

    # Размеры ЕДИНИЦЫ оборудования для перевода в штуки:
    # ёмкость одного шкафа (261 кВт*ч) и мощность одного PCS (125 кВт).
    unit_kwh: float | None = Field(default=None, gt=0)
    unit_kw: float | None = Field(default=None, gt=0)

    # C-rate коридор (аудит №3; Calliope flow_cap_per_storage_cap_min/max):
    # связь мощности и ёмкости, 1/ч. c_rate_max=0.5 значит «PCS не больше
    # половины ёмкости в час» (2-часовая батарея и медленнее). Без полей
    # kW и kWh независимы — солвер может выбрать абсурдную пару.
    c_rate_min: float | None = Field(default=None, gt=0)
    c_rate_max: float | None = Field(default=None, gt=0)

    lifetime_years: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_size_corridors(self):
        if self.max_kwh < self.min_kwh:
            raise ValueError("Battery: max_kwh не может быть меньше min_kwh")
        if self.max_kw < self.min_kw:
            raise ValueError("Battery: max_kw не может быть меньше min_kw")
        if (self.c_rate_min is not None and self.c_rate_max is not None
                and self.c_rate_max < self.c_rate_min):
            raise ValueError("Battery: c_rate_max не может быть меньше c_rate_min")
        return self


class DieselConfig(BaseModel):
    """Дизельный генератор (DG — diesel generator)."""

    model_config = ConfigDict(extra="forbid")

    capex_usd_per_kw: float = Field(gt=0)
    om_usd_per_kw_year: float = Field(ge=0)

    # Стоимость 1 кВт*ч из дизеля — КАНОНИЧЕСКОЕ поле, которым считают
    # деньги все слои. Задать его можно ДВУМЯ способами:
    #   (а) напрямую, как $/кВт*ч (плоский тариф, как в вендорском PDF);
    #   (б) через цену литра × удельный расход (как в REopt/HOMER:
    #       fuel_cost_per_gallon × fuel_slope_gal_per_kwh) — тогда это
    #       поле можно НЕ задавать, валидатор выведет его сам.
    # None разрешён только если задана пара (fuel_price_usd_per_liter,
    # fuel_liters_per_kwh). Топливная кривая с холостым ходом (intercept)
    # по-прежнему отложена — она требует MILP.
    fuel_cost_usd_per_kwh: float | None = Field(default=None, gt=0)

    # Цена ОДНОГО ЛИТРА дизеля (опционально, v1.1). Фундаментальный вход
    # у профи (REopt — цена за галлон, Calliope — cost_flow_in). Вместе с
    # fuel_liters_per_kwh даёт эффективные $/кВт*ч = цена_литра * л/кВт*ч.
    fuel_price_usd_per_liter: float | None = Field(default=None, gt=0)

    # Удельный расход топлива, литров на кВт*ч (опционально). Нужен и для
    # KPI (литры за год под завоз топлива), и для перевода цены литра в
    # $/кВт*ч. Типовой генсет на номинале — ~0.27 л/кВт*ч.
    fuel_liters_per_kwh: float | None = Field(default=None, gt=0)

    min_kw: float = Field(ge=0)
    max_kw: float = Field(gt=0)

    # Мощность одного генсета (1000 кВт) — для перевода в штуки И как
    # размер юнита в MILP-режиме (парк из целых машин).
    unit_kw: float | None = Field(default=None, gt=0)

    # --- поля MILP-режима (unit commitment, шаг A) ---
    # Минимальная загрузка РАБОТАЮЩЕГО генсета, доля номинала: включённый
    # юнит обязан выдавать не меньше (REopt min_turn_down_fraction, дефолт
    # off-grid 0.15). None = 0 (без нижней полки; юнит может работать в
    # любой точке). Используется только оптимизатором MILP.
    min_turn_down_fraction: float | None = Field(default=None, ge=0, le=1)

    # Расход на ХОЛОСТОЙ ход, литров в час на ОДИН работающий юнит —
    # постоянная составляющая топливной кривой (intercept в REopt:
    # fuel_intercept_gal_per_hr). Стоит денег, даже когда генсет почти не
    # нагружен, — поэтому MILP гасит лишние юниты. Требует
    # fuel_price_usd_per_liter, чтобы перевести литры в деньги. None = 0.
    fuel_idle_liters_per_hour: float | None = Field(default=None, ge=0)

    # Может ли генсет заряжать батарею (cycle charging; аудит №2, изъян
    # №2). REopt разрешает всегда (Generator входит в techs.elec), HOMER
    # делает это стратегией диспетчеризации (Cycle Charging / Combined
    # Dispatch — NPC до −20% против чистого load following). По умолчанию
    # выключено — включай для площадок с многодневной пасмурностью или
    # генсетом меньше пика: батарея сможет переносить дизельную энергию
    # во времени, а не стоять пустой.
    can_charge_battery: bool = False

    # Эскалация цены топлива, доля/год (аудит №2, изъян №6): реальные
    # цены дизеля в удалённой логистике растут, плоская цена на 20 лет
    # смещает оптимум к генсету. Учитывается ЛЕВЕЛИЗАЦИОННЫМ
    # коэффициентом (economics.fuel_levelization_factor) — LP остаётся
    # линейным. None = 0 (плоская цена, прежнее поведение).
    fuel_escalation_fraction: float | None = Field(default=None, ge=0, lt=0.5)

    # Операционные выбросы, кг CO2 на кВт*ч дизельной энергии (для цены
    # углерода в целевой функции; аудит №3). None = дефолт 0.72
    # (2.68 кг/л * ~0.27 л/кВт*ч).
    co2_kg_per_kwh: float | None = Field(default=None, gt=0)

    lifetime_years: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_size_corridor(self):
        if self.max_kw < self.min_kw:
            raise ValueError("Diesel: max_kw не может быть меньше min_kw")
        # Холостой ход задан, но нечем оценить его в деньгах.
        if (
            self.fuel_idle_liters_per_hour
            and self.fuel_price_usd_per_liter is None
        ):
            raise ValueError(
                "Diesel: fuel_idle_liters_per_hour требует "
                "fuel_price_usd_per_liter (перевод литров холостого хода в $)"
            )
        # Топливо: если $/кВт*ч не задан напрямую — вывести из цены литра.
        if self.fuel_cost_usd_per_kwh is None:
            if self.fuel_price_usd_per_liter is None or \
                    self.fuel_liters_per_kwh is None:
                raise ValueError(
                    "Diesel: задай ЛИБО fuel_cost_usd_per_kwh, ЛИБО пару "
                    "fuel_price_usd_per_liter + fuel_liters_per_kwh"
                )
            self.fuel_cost_usd_per_kwh = (
                self.fuel_price_usd_per_liter * self.fuel_liters_per_kwh
            )
        return self


class LoadConfig(BaseModel):
    """Нагрузка: сколько электричества потребляет объект.

    Два взаимоисключающих режима:
      А. Синтетический профиль — заданы все четыре поля:
         day_kw, night_kw, work_start_hour, work_end_hour.
      Б. Реальный временной ряд — задан profile_csv: путь к CSV-файлу
         с колонками "timestamp,load_kw". Шаг ряда может быть любым
         РАВНОМЕРНЫМ (час, полчаса, сутки) — длительность шага
         вычислит profiles.timestep_hours.
    """

    model_config = ConfigDict(extra="forbid")

    # Режим А (все поля необязательны по отдельности, но валидатор
    # ниже требует: либо заполнены все четыре, либо ни одного).
    day_kw: float | None = Field(default=None, gt=0)
    night_kw: float | None = Field(default=None, ge=0)
    # Соглашение полуинтервала: час X рабочий, если start <= X < end.
    work_start_hour: int | None = Field(default=None, ge=0, le=23)
    work_end_hour: int | None = Field(default=None, ge=1, le=24)

    # Режим Б.
    profile_csv: str | None = None

    @model_validator(mode="after")
    def validate_profile_mode(self):
        synthetic_fields = [
            self.day_kw,
            self.night_kw,
            self.work_start_hour,
            self.work_end_hour,
        ]
        all_synthetic = all(v is not None for v in synthetic_fields)
        any_synthetic = any(v is not None for v in synthetic_fields)
        has_csv = self.profile_csv is not None

        if has_csv and any_synthetic:
            raise ValueError(
                "Load: задай ЛИБО profile_csv, ЛИБО синтетические поля — не оба режима сразу"
            )
        if not has_csv and not all_synthetic:
            raise ValueError(
                "Load: заполни либо profile_csv, либо ВСЕ четыре поля "
                "day_kw / night_kw / work_start_hour / work_end_hour"
            )
        if all_synthetic and self.work_end_hour <= self.work_start_hour:
            raise ValueError(
                "Load: work_end_hour должен быть больше work_start_hour"
            )
        return self


class FinancialConfig(BaseModel):
    """Финансовые параметры расчёта."""

    model_config = ConfigDict(extra="forbid")

    # Ставка дисконтирования: насколько "деньги сегодня" ценнее
    # "денег через год". Вход для формулы CRF (шаг 6).
    discount_rate_fraction: float = Field(ge=0, lt=1)
    project_years: int = Field(gt=0)
    currency: str

    # Цена углерода, $/тонну CO2 (аудит №3): поднимает выбросы из
    # post-hoc KPI в ЦЕЛЕВУЮ функцию — аналог Lifecycle_Emissions_Cost
    # REopt и cost-класса co2 Calliope. None = выбросы не оптимизируются
    # (только справочный KPI, прежнее поведение).
    co2_price_usd_per_ton: float | None = Field(default=None, ge=0)


class ReliabilityConfig(BaseModel):
    """Требование к надёжности электроснабжения (расширено в шаге 8).

    Три политики — как в REopt (min_load_met_annual_fraction,
    dvUnservedLoad):
      hard — недопоставка запрещена вовсе (Σ shortfall == 0);
      lpsp — недопоставка не выше доли lpsp_max_fraction от спроса
             (LPSP <= x%): "99% надёжности достаточно, зато дешевле";
      voll — жёсткого требования нет, каждый недопоставленный kWh
             штрафуется ценой voll_usd_per_kwh в целевой функции —
             солвер сам решает, что дешевле: покрыть или потерять.
    """

    model_config = ConfigDict(extra="forbid")

    mode: Literal["hard", "lpsp", "voll"]

    # Параметры режимов; каждый обязателен ровно для своего режима.
    lpsp_max_fraction: float | None = Field(default=None, gt=0, lt=1)
    voll_usd_per_kwh: float | None = Field(default=None, gt=0)

    # Operating reserve (оперативный/вращающийся резерв) — необязательная
    # политика ПОВЕРХ основного режима, перенос из REopt
    # (operating_reserve_constraints.jl). В КАЖДЫЙ час система обязана
    # держать свободную мощность СВЕРХ текущей выработки: недогруженный
    # дизель (dg_kw - dg[t]) плюс доступный разряд батареи. Требуемый
    # резерв = доля нагрузки + доля выработки PV (солнце капризно —
    # облако роняет генерацию, резерв это страхует).
    #
    # Зачем это, а не прежний костыль diesel_firm_fraction (dg_kw >= доля
    # пика): LP-сайзер с идеальным предвидением режет дизель почти в ноль,
    # опираясь на батарею, и слепой контроллер потом даёт недопоставку
    # (battle-тест Феникса: 2.4% LPSP). Резерв закрывает это ПРИНЦИПИАЛЬНО
    # — час за часом требует горячий запас мощности, а не грубо «дизель на
    # весь пик»; резерв может дать и батарея. Аналог
    # operating_reserve_required_fraction (на нагрузку) и
    # techs_operating_reserve_req_fraction (на PV) в REopt.
    #
    # Доля резерва от НАГРУЗКИ каждого часа (0.10 = держать 10% сверх).
    operating_reserve_load_fraction: float | None = Field(
        default=None, ge=0, le=1
    )
    # Доля резерва от ВЫРАБОТКИ PV каждого часа (страховка от облаков).
    operating_reserve_pv_fraction: float | None = Field(
        default=None, ge=0, le=1
    )

    @model_validator(mode="after")
    def validate_mode_params(self):
        if self.mode == "lpsp" and self.lpsp_max_fraction is None:
            raise ValueError("Reliability: режим lpsp требует lpsp_max_fraction")
        if self.mode == "voll" and self.voll_usd_per_kwh is None:
            raise ValueError("Reliability: режим voll требует voll_usd_per_kwh")
        if self.mode == "hard" and (
            self.lpsp_max_fraction is not None or self.voll_usd_per_kwh is not None
        ):
            raise ValueError(
                "Reliability: режим hard не принимает lpsp_max_fraction/voll_usd_per_kwh"
            )
        return self


class Scenario(BaseModel):
    """Корневая модель: весь входной сценарий целиком.

    Поля-разделы — вложенные модели (nested models). Технологии
    объявлены как "Config | None = None": отсутствие ключа в JSON
    означает отсутствие технологии в проекте. Это тот же паттерн,
    что в REopt: там технология создаётся только по haskey(...),
    а их документация помечает ElectricStorage словом "optional".
    """

    model_config = ConfigDict(extra="forbid")

    name: str
    site: SiteConfig
    pv: PVConfig | None = None
    battery: BatteryConfig | None = None
    diesel: DieselConfig | None = None
    load: LoadConfig
    financial: FinancialConfig
    reliability: ReliabilityConfig

    @model_validator(mode="after")
    def validate_not_empty_system(self):
        # Пустая система (ни одной технологии) — бессмысленный вход.
        # А вот проверять "хватит ли выбранного набора для покрытия
        # нагрузки" схема НЕ должна: это работа симулятора и
        # оптимизатора — они честно покажут дефицит.
        if self.pv is None and self.battery is None and self.diesel is None:
            raise ValueError(
                "Scenario: нужен хотя бы один блок технологии (pv, battery или diesel)"
            )
        return self
