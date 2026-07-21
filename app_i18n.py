"""Переводы интерфейса GreenHouse (RU/EN).

Русский — язык-источник (ключи словаря). EN — значения. Если перевода
нет, t() возвращает русский as-is (graceful fallback). Переводятся
ТОЛЬКО тексты интерфейса; числа, единицы (kW/kWh/USD) и внутренние
ключи данных не трогаются.

Для строк с подстановкой значений используются позиционные плейсхолдеры
{} — и в русском ключе, и в английском значении, чтобы .format() работал
одинаково в обоих языках.
"""

TRANSLATIONS: dict[str, str] = {
    # ---------- сайдбар: шапка и нагрузка ----------
    "Язык / Language": "Язык / Language",
    "Заполни параметры и нажми «Пересчитать» — они наложатся "
    "на базовый сценарий (паттерн Calliope: base + overrides) "
    "и уйдут в LP-оптимизатор. Единицы: kW / kWh / USD.":
        "Set the parameters and press “Recalculate” — they overlay the base "
        "scenario (Calliope pattern: base + overrides) and go to the LP "
        "optimizer. Units: kW / kWh / USD.",
    "Нагрузка": "Load",
    "Источник профиля": "Profile source",
    "Синтетический (Йемен)": "Synthetic (Yemen)",
    "CSV-файл": "CSV file",
    "Профиль нагрузки — ряд «сколько kW потребляет завод в каждый "
    "час». CSV: колонки timestamp,load_kw; равномерный шаг; 2026 год.":
        "Load profile — a series of “how many kW the plant draws each "
        "hour”. CSV: columns timestamp,load_kw; uniform step; year 2026.",
    "CSV (используется в режиме «CSV-файл»)":
        "CSV (used in “CSV file” mode)",
    "Дневная нагрузка, kW": "Daytime load, kW",
    "Мощность (kW) в рабочие часы смены 08–18; kW — СКОРОСТЬ "
    "потребления, энергия за час = kW × 1 ч. Для синтетики.":
        "Power (kW) during the 08–18 shift; kW is the RATE of consumption, "
        "energy per hour = kW × 1 h. For the synthetic profile.",
    "Ночная база, kW": "Night base, kW",
    "Дежурная мощность вне смены: охрана, холодильники, серверная.":
        "Standby power outside the shift: security, fridges, server room.",

    # ---------- цены ----------
    "Цены": "Prices",
    "CAPEX PV, $/kW": "CAPEX PV, $/kW",
    "Разовые капитальные затраты на 1 kWp панелей "
    "(купить + смонтировать).":
        "One-off capital cost per 1 kWp of panels (buy + install).",
    "CAPEX BESS, $/kWh": "CAPEX BESS, $/kWh",
    "Цена 1 kWh ёмкости накопителя (LFP-шкафы). kWh — сколько "
    "батарея ХРАНИТ; kW — как быстро отдаёт.":
        "Price of 1 kWh of storage capacity (LFP cabinets). kWh — how much "
        "the battery STORES; kW — how fast it delivers.",
    "Цена дизеля, $/литр": "Diesel price, $/liter",
    "Цена одного литра дизтоплива на площадке (с доставкой). "
    "Фундаментальный вход у REopt/HOMER; $/кВт*ч выводится из "
    "неё и удельного расхода. Tornado показывает: самый "
    "влиятельный параметр модели.":
        "Price of one liter of diesel on site (delivered). The fundamental "
        "input in REopt/HOMER; $/kWh is derived from it and the fuel "
        "consumption. Tornado shows it is the most influential parameter of "
        "the model.",
    "Удельный расход, л/кВт*ч": "Fuel consumption, L/kWh",
    "Сколько литров сжигает генсет на 1 кВт*ч на номинале "
    "(datasheet). Типовой дизель ~0.27. Холостой ход "
    "(intercept топливной кривой) v1 не моделирует — он "
    "требует MILP.":
        "How many liters the genset burns per 1 kWh at rated load "
        "(datasheet). A typical diesel ~0.27. Idle burn (the fuel-curve "
        "intercept) is not modeled in v1 — it requires MILP.",
    "→ эффективно ${}/кВт*ч дизеля": "→ effectively ${}/kWh of diesel",

    # ---------- PV-модуль ----------
    "PV-модуль и инвертор (datasheet)": "PV module & inverter (datasheet)",
    "КПД инвертора": "Inverter efficiency",
    "Номинальный КПД DC→AC. Дефолт 0.96 (REopt/PVWatts); "
    "в datasheet вендора обычно 0.95–0.985.":
        "Nominal DC→AC efficiency. Default 0.96 (REopt/PVWatts); a vendor "
        "datasheet usually says 0.95–0.985.",
    "Темп. коэффициент, %/°C": "Temp. coefficient, %/°C",
    "Потеря мощности на каждый °C нагрева ячейки выше 25 °C. "
    "Стандартный кремний −0.47; N-type TOPCon ~−0.30.":
        "Power loss per °C of cell heating above 25 °C. Standard silicon "
        "−0.47; N-type TOPCon ~−0.30.",
    "DC/AC (панели к инвертору)": "DC/AC (panels to inverter)",
    "Панелей ставят больше номинала инвертора: пики редки, "
    "инвертор дорог; излишек срезается (clipping).":
        "More panels than the inverter rating: peaks are rare, the inverter "
        "is expensive; the excess is clipped.",
    "Монтаж панелей": "Panel mounting",
    "close_mount (вплотную к крыше)": "close_mount (flush to roof)",
    "open_rack (на раме / земле)": "open_rack (on rack / ground)",
    "Влияет на температуру ячейки: на раме панели охлаждаются "
    "лучше (+1–2% выработки). Кейс NIST показал значимость.":
        "Affects cell temperature: on a rack panels cool better (+1–2% "
        "output). The NIST case showed this matters.",

    # ---------- батарея и коридоры ----------
    "Батарея и площадка": "Battery & site",
    "RTE батареи": "Battery RTE",
    "КПД полного цикла «зарядил-разрядил»: из 100 kWh при 0.85 "
    "обратно выйдет 85. В модели η заряда = η разряда = √RTE.":
        "Round-trip efficiency “charge-discharge”: of 100 kWh at 0.85 you "
        "get 85 back. In the model η charge = η discharge = √RTE.",
    "Площадь под PV, м²": "Area for PV, m²",
    "Потолок сайзера: pv_kWp × 5 м²/kWp ≤ площадь.":
        "Sizer ceiling: pv_kWp × 5 m²/kWp ≤ area.",
    "Коридоры поиска (максимумы)": "Search corridors (maxima)",
    "Макс. PV, kWp": "Max PV, kWp",
    "Верхняя граница поиска для солнца (нижняя 0). Итоговый "
    "потолок — минимум из этого и площади.":
        "Upper search bound for solar (lower is 0). The final ceiling is "
        "the minimum of this and the area.",
    "Макс. BESS, kWh": "Max BESS, kWh",
    "Верхняя граница поиска ёмкости накопителя.":
        "Upper search bound for storage capacity.",
    "Макс. DG, kW": "Max DG, kW",
    "Верхняя граница поиска дизеля. При политике hard она должна "
    "позволять покрыть пик — иначе честная ошибка «неразрешимо».":
        "Upper search bound for diesel. Under the hard policy it must allow "
        "covering the peak — otherwise an honest “infeasible” error.",

    # ---------- надёжность ----------
    "Надёжность": "Reliability",
    "Политика": "Policy",
    "hard — недопоставка запрещена": "hard — no unmet load allowed",
    "lpsp — допустимая доля недопоставки": "lpsp — allowed unmet fraction",
    "voll — недопоставка платная": "voll — unmet load is priced",
    "hard: каждый kWh спроса покрыт. lpsp: недопоставка не выше "
    "заданной доли. voll: солвер сам решает, что дешевле — "
    "поставить или заплатить штраф за тьму.":
        "hard: every kWh of demand is met. lpsp: unmet load no higher than "
        "a set fraction. voll: the solver decides what is cheaper — supply "
        "or pay the penalty for darkness.",
    "LPSP-цель, % (для режима lpsp)": "LPSP target, % (for lpsp mode)",
    "Допустимая доля годового спроса без поставки; "
    "1% ≈ 87 часов простоя в год.":
        "Allowed fraction of annual demand left unserved; "
        "1% ≈ 87 hours of downtime per year.",
    "VOLL, $/kWh (для режима voll)": "VOLL, $/kWh (for voll mode)",
    "Value of lost load — цена недопоставленного kWh для "
    "потребителя (простой производства). Дефолт REopt: $1.":
        "Value of lost load — price of an unserved kWh to the consumer "
        "(production downtime). REopt default: $1.",
    "Оперативный резерв, % нагрузки": "Operating reserve, % of load",
    "Горячий запас мощности сверх нагрузки в КАЖДЫЙ час "
    "(REopt operating reserve): недогруженный дизель + "
    "доступный разряд батареи. Принципиальная замена костылю "
    "«дизель на весь пик»: закрывает разрыв LP-предвидения и "
    "слепого контроллера. 0 = выключено.":
        "Hot power headroom above the load EVERY hour (REopt operating "
        "reserve): the underloaded diesel + the battery’s available "
        "discharge. A principled replacement for the “diesel on the whole "
        "peak” hack: it closes the gap between LP foresight and a blind "
        "controller. 0 = off.",
    "Резерв на PV, %": "Reserve on PV, %",
    "Дополнительный резерв, привязанный к выработке солнца: "
    "облако роняет PV — запас страхует. Panель сама резерв не "
    "даёт (она и есть источник неопределённости).":
        "Extra reserve tied to solar output: a cloud drops PV — the "
        "headroom insures against it. The panel itself provides no reserve "
        "(it is the source of uncertainty).",
    "Циклический SOC (годовое кольцо)": "Cyclic SOC (annual ring)",
    "Запас батареи в конце года «перетекает» в его начало "
    "(паттерн Calliope) — без бесплатной стартовой заправки. "
    "Выключи для сравнения с REopt-стилем (старт с полной).":
        "The battery charge at year end “flows” into its start (Calliope "
        "pattern) — no free initial charge. Turn off to compare with the "
        "REopt style (start full).",
    "Точный расчёт парка (MILP)": "Exact fleet model (MILP)",
    "Целые машины + стадирование дизеля (медленнее)":
        "Whole machines + diesel staging (slower)",
    "Вместо непрерывного LP решить MILP: размеры кратны юниту "
    "(целые панели/шкафы/генсеты), а дизель стадируется по "
    "часам — «сколько генсетов молотит сейчас» — с минимальной "
    "загрузкой и расходом на холостой ход. Честнее физика, но "
    "solver ветвит и считает десятки секунд вместо секунд.":
        "Instead of the continuous LP, solve a MILP: sizes are multiples of "
        "the unit (whole panels/cabinets/gensets), and diesel is staged by "
        "the hour — “how many gensets run now” — with a minimum load and "
        "idle burn. More honest physics, but the solver branches and takes "
        "tens of seconds instead of seconds.",
    "Мин. загрузка генсета, %": "Min genset load, %",
    "Включённый генсет не опускается ниже этой доли номинала "
    "(REopt min_turn_down_fraction, дефолт off-grid 15–30%). "
    "Работает только в MILP-режиме.":
        "A running genset stays above this fraction of its rating (REopt "
        "min_turn_down_fraction, off-grid default 15–30%). Works only in "
        "MILP mode.",
    "Холостой ход, л/ч на генсет": "Idle burn, L/h per genset",
    "Постоянный расход топлива работающего генсета сверх "
    "нагрузки (intercept топливной кривой REopt). Стоит денег "
    "даже вхолостую — MILP гасит лишние юниты. 0 = не "
    "моделировать. Работает только в MILP-режиме.":
        "A running genset’s constant fuel draw on top of the load (the "
        "intercept of the REopt fuel curve). It costs money even at idle — "
        "so MILP shuts down spare units. 0 = don’t model. Works only in "
        "MILP mode.",
    "MILP-парк: {} генсет(ов) по {:g} kW · одновременно в работе "
    "до {}, в среднем {} · целые машины и стадирование по часам":
        "MILP fleet: {} genset(s) of {:g} kW · up to {} running at once, "
        "{} on average · whole machines and hourly staging",
    "Пересчитать": "Recalculate",
    "Зафиксировать текущий как базу": "Fix current as baseline",

    # ---------- словарь терминов ----------
    "Словарь терминов": "Glossary",

    # ---------- главная: метрики ----------
    "Оптимальная конфигурация": "Optimal configuration",
    "Решено за {} c · дельты — против зафиксированной базы "
    "(кнопка в сайдбаре)":
        "Solved in {} s · deltas — vs the fixed baseline "
        "(button in the sidebar)",
    "Годовые издержки": "Annual cost",
    "Renewable": "Renewable",
    "Дизель": "Diesel",
    "CO₂ (оценка*)": "CO₂ (estimate*)",
    "*ASSUMPTION {} кг CO₂/kWh дизеля · LPSP = {} · curtailment = {} kWh":
        "*ASSUMPTION {} kg CO₂/kWh of diesel · LPSP = {} · curtailment = "
        "{} kWh",

    # ---------- вкладки ----------
    "Конфигурация": "Configuration",
    "Диспетчеризация": "Dispatch",
    "Ресурсы": "Resources",
    "Экономика": "Economics",
    "Сценарии": "Scenarios",
    "Валидация": "Validation",

    # ---------- вкладка «Конфигурация»: BOM ----------
    "Спецификация закупки": "Purchase specification",
    "Спецификация закупки (bill of materials)":
        "Purchase specification (bill of materials)",
    "Компонент": "Component",
    "Что заказать": "What to order",
    "Кол-во, шт": "Qty, pcs",
    "Номинал юнита": "Unit rating",
    "Установлено": "Installed",
    "Цена/юнит, $": "Unit price, $",
    "CAPEX, $": "CAPEX, $",
    "O&M, $/год": "O&M, $/yr",
    "Производство, kWh/год": "Output, kWh/yr",
    "ИТОГО": "TOTAL",
    "Что означает каждая колонка": "What each column means",
    "Кол-во и «установлено» — сколько ЦЕЛЫХ юнитов купить "
    "(ceil от LP-оптимума); подробно о каждой колонке — в развороте ниже.":
        "Qty and “installed” — how many WHOLE units to buy "
        "(ceil of the LP optimum); details on each column in the expander "
        "below.",
    "Солнечные панели (PV)": "Solar panels (PV)",
    "PV-панель": "PV panel",
    "Накопитель — ёмкость (BESS)": "Storage — energy (BESS)",
    "Батарейный шкаф": "Battery cabinet",
    "Накопитель — мощность (PCS)": "Storage — power (PCS)",
    "Инвертор PCS": "PCS inverter",
    "Дизель-генератор (DG)": "Diesel generator (DG)",
    "Дизель-генератор": "Diesel genset",
    "текущее решение (эта форма)": "current solution (this form)",
    "база (зафиксирована кнопкой)": "baseline (fixed by button)",
    "Размеры: текущее решение против базы":
        "Sizes: current solution vs baseline",
    "тёмная полоса — оптимум при текущих "
    "параметрах формы; светлая — «база», которую ты "
    "зафиксировал для сравнения. Разошлись — значит, твои "
    "изменения передвинули оптимум.":
        "the dark bar is the optimum at the current form parameters; the "
        "light one is the “baseline” you fixed for comparison. If they "
        "differ, your changes moved the optimum.",
    "Кто поставил энергию заводу за год":
        "Who supplied energy to the plant over the year",
    "Солнце напрямую": "Solar direct",
    "Солнце через батарею": "Solar via battery",
    "Энергобаланс года": "Annual energy balance",
    "жёлтое — солнце, ушедшее заводу сразу; "
    "зелёное — то же солнце, но отложенное батареей на "
    "вечер/ночь (минус потери цикла); красное — дизель. "
    "Красный сектор растёт — система дрейфует от «солнце с "
    "резервом» к «дизель с довеском».":
        "yellow — solar that went straight to the plant; green — the same "
        "solar deferred by the battery to evening/night (minus cycle "
        "losses); red — diesel. A growing red sector means the system "
        "drifts from “solar with backup” to “diesel with an add-on”.",
    "Схема системы (AC-coupling, шина 400 В)":
        "System diagram (AC-coupling, 400 V bus)",
    "шина 400 В": "400 V bus",
    "Завод (нагрузка)": "Plant (load)",
    "панелей": "panels",
    "шкафов": "cabinets",
    "генсет": "genset",
    "LP-оптимизатор перебрал все допустимые комбинации размеров и режимов "
    "работы за 8760 часов года и нашёл самую дешёвую, которая держит "
    "нагрузку при выбранной политике надёжности. Размеры он ищет "
    "непрерывными (так задача решается за секунды с гарантией оптимума), "
    "а таблица переводит их в целые штуки: ceil(размер / юнит). "
    "Схема — топология AC-coupling: все источники параллельно на одной "
    "шине 400 В, как в вендорском предложении.":
        "The LP optimizer searched every feasible combination of sizes and "
        "operating modes across the 8760 hours of the year and found the "
        "cheapest one that holds the load under the chosen reliability "
        "policy. It searches sizes as continuous values (so the problem "
        "solves in seconds with a guaranteed optimum), and the table "
        "converts them into whole units: ceil(size / unit). The diagram is "
        "the AC-coupling topology: all sources in parallel on one 400 V "
        "bus, as in the vendor proposal.",

    # ---------- вкладка «Диспетчеризация» ----------
    "Недельный график доступен для годового часового профиля.":
        "The weekly chart is available for an hourly annual profile.",
    "солнце → завод (напрямую)": "solar → plant (direct)",
    "батарея → завод (разряд запаса)": "battery → plant (discharge)",
    "дизель → завод (резерв)": "diesel → plant (backup)",
    "нагрузка завода (спрос)": "plant load (demand)",
    "Неделя 16–22 февраля: кто кормит завод (LP-решение)":
        "Week 16–22 Feb: who feeds the plant (LP solution)",
    "часы недели": "hours of the week",
    "три цветных слоя складываются (стек) и обязаны "
    "дотягиваться до пунктирного спроса — любой зазор был бы "
    "недопоставкой. Жёлтый низ — прямое солнце днём; зелёный "
    "появляется вечером (батарея отдаёт дневной запас); "
    "красный — предрассветные часы, когда батарея у пола.":
        "the three colored layers stack and must reach the dashed demand "
        "line — any gap would be unmet load. The yellow base is direct "
        "solar during the day; green appears in the evening (the battery "
        "releases its daytime charge); red is the pre-dawn hours when the "
        "battery is at its floor.",
    "запас батареи (SOC), kWh": "battery charge (SOC), kWh",
    "пол SOC (20% — бережём ресурс)": "SOC floor (20% — protect cells)",
    "ёмкость (потолок)": "capacity (ceiling)",
    "Запас батареи (SOC) в ту же неделю":
        "Battery charge (SOC) over the same week",
    "зелёная линия дышит сутками: днём вверх (заряд "
    "солнечным избытком), вечером вниз. Пунктирные линии — "
    "границы: ниже красной не разряжаем (ресурс ячеек), выше "
    "серой физически некуда. Линия редко касается потолка — "
    "батарея великовата; бьётся об пол каждую ночь — мала.":
        "the green line breathes daily: up in the day (charged by the solar "
        "surplus), down in the evening. The dashed lines are limits: below "
        "the red one we don’t discharge (cell life), above the gray one "
        "there is physically no room. If the line rarely touches the "
        "ceiling the battery is oversized; if it hits the floor every night "
        "it is undersized.",
    "Это «рентген» найденного решения на характерной неделе февраля. "
    "Именно по этим двум графикам мы поймали переразмеренность "
    "вендорской батареи: она наполнялась до потолка один день в году.":
        "This is an “X-ray” of the found solution over a typical February "
        "week. It was exactly these two charts that revealed the vendor "
        "battery was oversized: it reached the ceiling on a single day of "
        "the year.",

    # ---------- вкладка «Ресурсы» ----------
    "Годовая выработка солнца": "Annual solar yield",
    "Энергия нагрузки за год": "Annual load energy",
    "Шаг данных Δt": "Data step Δt",
    "спрос завода, kW": "plant demand, kW",
    "Нагрузка: первые двое суток": "Load: first two days",
    "час": "hour",
    "ступеньки — смена 08–18 на дневной мощности, "
    "ночью — дежурная база. Это СПРОС, который система обязана "
    "покрывать каждый час.":
        "the steps are the 08–18 shift at daytime power, with the standby "
        "base at night. This is the DEMAND the system must cover every "
        "hour.",
    "лучший день года ({})": "best day of the year ({})",
    "15 июня (облачный сезон)": "15 June (cloudy season)",
    "Солнце: типовые сутки, kW на 1 kWp":
        "Solar: typical days, kW per 1 kWp",
    "час местного времени": "local hour",
    "обе кривые — «сколько даёт 1 kWp панелей». "
    "Жёлтая — лучший день года (зимой!), зелёная — облачный "
    "июнь. Итоговая выработка = эта кривая × размер PV.":
        "both curves show “how much 1 kWp of panels delivers”. Yellow — "
        "the best day of the year (in winter!), green — cloudy June. Total "
        "output = this curve × PV size.",
    "выработка за месяц, kWh/kWp": "output per month, kWh/kWp",
    "Выработка по месяцам": "Output by month",
    "месяц": "month",
    "высота столбца — энергия месяца с 1 kWp. В Сане зима "
    "солнечнее лета (июльская облачность нагорья) — худший "
    "сезон солнца совпадает с круглогодичной нагрузкой, поэтому "
    "летом дизель работает больше.":
        "bar height is the month’s energy per 1 kWp. In Sana’a winter is "
        "sunnier than summer (July highland clouds) — the worst solar "
        "season coincides with the year-round load, so diesel runs more in "
        "summer.",
    "Это два входных ряда, из которых следует всё остальное: спрос "
    "(нагрузка по часам) и предложение (выработка 1 kWp из спутникового "
    "«типичного года» PVGIS через модель PVWatts). Любое странное число "
    "на других вкладках сначала проверяют здесь.":
        "These are the two input series from which everything else "
        "follows: demand (hourly load) and supply (1 kWp output from the "
        "satellite “typical year” PVGIS via the PVWatts model). Any strange "
        "number on the other tabs is checked here first.",

    # ---------- вкладка «Экономика» ----------
    "CAPEX (разово)": "CAPEX (one-off)",
    "NPC (за горизонт)": "NPC (over horizon)",
    "База «100% дизель»": "Baseline “100% diesel”",
    "Окупаемость": "Payback",
    "{} лет": "{} years",
    "нет": "none",
    "капитал PV": "PV capital",
    "капитал BESS": "BESS capital",
    "капитал DG": "DG capital",
    "O&M": "O&M",
    "топливо": "fuel",
    "Годовые издержки ${} — из чего складываются":
        "Annual cost ${} — what it consists of",
    "цвет полосы = технология (жёлтый PV, зелёный BESS, красный "
    "DG — как на всех графиках); серый — обслуживание всего "
    "железа, тёмно-красный — солярка. «Капитал X» — это CAPEX, "
    "размазанный формулой CRF в равные годовые платежи по сроку "
    "жизни технологии.":
        "bar color = technology (yellow PV, green BESS, red DG — as on all "
        "charts); gray is maintenance of all the hardware, dark red is "
        "fuel. “X capital” is CAPEX spread by the CRF formula into equal "
        "annual payments over the technology’s lifetime.",
    "Сверка: сумма статей совпадает с целевой функцией солвера "
    "(${}) с точностью до "
    "анти-вырожденного микроштрафа — две независимые дороги к "
    "одному числу.":
        "Cross-check: the sum of line items matches the solver’s objective "
        "(${}) up to the anti-degeneracy micro-penalty — two independent "
        "roads to one number.",
    "Деньги системы в одном месте: CRF превращает разовые покупки в "
    "годовые платежи, NPC собирает все затраты горизонта в сегодняшних "
    "деньгах, окупаемость меряется против базовой линии «вся энергия из "
    "дизеля». У Йемена бюджет ест топливо — потому tornado на вкладке "
    "Sensitivity ставит цену солярки на первое место.":
        "The system’s money in one place: CRF turns one-off purchases into "
        "annual payments, NPC gathers all horizon costs in today’s money, "
        "payback is measured against the “all energy from diesel” baseline. "
        "For Yemen fuel eats the budget — that is why the tornado on the "
        "Sensitivity tab ranks the diesel price first.",

    # ---------- вкладка «Rule vs LP» ----------
    "LP-сайзер обладает **perfect foresight** — «знает» весь год наперёд. "
    "Реальный контроллер работает по правилу и будущего не видит. Здесь "
    "оптимальные размеры фиксируются и прогоняются через слепой "
    "rule-симулятор шага 5 — разница и есть цена идеального предвидения.":
        "The LP sizer has **perfect foresight** — it “knows” the whole year "
        "ahead. A real controller follows a rule and cannot see the future. "
        "Here the optimal sizes are fixed and run through the blind "
        "rule-based simulator of step 5 — the difference is the price of "
        "perfect foresight.",
    "LPSP у LP (всевидящий)": "LPSP for LP (all-seeing)",
    "LPSP у правила (слепой)": "LPSP for the rule (blind)",
    "Больше нуля при hard-политике — это и есть "
    "perfect-foresight разрыв: живой диспетчер иногда не "
    "дотягивает на размерах, ужатых оптимизатором.":
        "Greater than zero under the hard policy is exactly the "
        "perfect-foresight gap: a live dispatcher sometimes falls short on "
        "sizes squeezed by the optimizer.",
    "Недопоставка правила": "Rule unmet load",
    "дизель": "diesel",
    "разряд батареи": "battery discharge",
    "сброс солнца": "solar curtailment",
    "недопоставка": "unmet load",
    "LP-оптимизатор (видит год наперёд)":
        "LP optimizer (sees the year ahead)",
    "правило (слепой контроллер)": "rule (blind controller)",
    "Годовые потоки: LP против правила на одних размерах":
        "Annual flows: LP vs rule at the same sizes",
    "kWh за год": "kWh per year",
    "пары полос сравнивают одинаковые потоки у двух диспетчеров "
    "НА ОДНИХ размерах железа. Тёмная (LP) — недостижимый идеал; "
    "светлая (правило) — приземлённая реальность. Смотри на "
    "«недопоставку»: если у правила она больше нуля — это цена "
    "отсутствия дара предвидения.":
        "pairs of bars compare the same flows for two dispatchers AT THE "
        "SAME hardware sizes. Dark (LP) is the unattainable ideal; light "
        "(rule) is grounded reality. Look at “unmet load”: if the rule’s is "
        "above zero, that is the price of having no foresight.",
    "Проверка на честность оптимизатора: LP-решение — нижняя граница "
    "затрат. Практический смысл: к LP-размерам дизеля стоит добавлять "
    "инженерный запас — вендоры делают именно это.":
        "A sanity check on the optimizer: the LP solution is the lower "
        "bound of cost. Practical takeaway: add an engineering margin to "
        "the LP diesel size — vendors do exactly that.",

    # ---------- вкладка «Sensitivity» ----------
    "Свипы цен (tornado), Pareto-фронт "
    "«стоимость ↔ надёжность» с коленом, стрессы. **~2 минуты** "
    "(≈20 LP-задач) — запускается по кнопке, результат кэшируется.":
        "Price sweeps (tornado), the “cost ↔ reliability” Pareto front with "
        "its knee, and stress tests. **~2 minutes** (≈20 LP problems) — "
        "started by a button, the result is cached.",
    "Запустить sensitivity (~2 мин)": "Run sensitivity (~2 min)",
    "Цена дизеля ±50%": "Diesel price ±50%",
    "CAPEX BESS ±30%": "CAPEX BESS ±30%",
    "CAPEX PV ±30%": "CAPEX PV ±30%",
    "параметр дешевле базового → издержки падают до этой точки":
        "parameter below base → cost falls to this point",
    "параметр дороже базового → издержки растут до этой точки":
        "parameter above base → cost rises to this point",
    "Tornado: чувствительность издержек к ценам":
        "Tornado: cost sensitivity to prices",
    "каждая строка — один параметр, качавшийся в своём "
    "диапазоне; пунктир — издержки при исходных ценах. Чем "
    "ДЛИННЕЕ полоса целиком, тем важнее уточнять прогноз "
    "этого параметра до подписания контракта.":
        "each row is one parameter swept across its range; the dashed line "
        "is the cost at the original prices. The LONGER the whole bar, the "
        "more important it is to refine that parameter’s forecast before "
        "signing the contract.",
    "Pareto-фронт (дешевле при такой надёжности не бывает)":
        "Pareto front (no cheaper at this reliability)",
    "колено — разумный компромисс": "knee — the reasonable trade-off",
    "Pareto: сколько стоит надёжность": "Pareto: the cost of reliability",
    "допустимая недопоставка (LPSP), %": "allowed unmet load (LPSP), %",
    "каждая точка — отдельная оптимизация с разрешённой "
    "недопоставкой. Слева-вверху дорогая абсолютная "
    "надёжность; вправо кривая быстро падает и — после "
    "красного колена — почти выполаживается: дальнейшие "
    "уступки дают копейки.":
        "each point is a separate optimization with allowed unmet load. "
        "Top-left is expensive absolute reliability; to the right the curve "
        "drops fast and — after the red knee — almost flattens: further "
        "concessions yield pennies.",
    "Стрессы оптимального дизайна": "Stress tests of the optimal design",
    "Входные цены — прогнозы, и надо знать, какие опасно прогнозировать "
    "плохо (tornado), почём каждая «девятка» надёжности (Pareto) и как "
    "дизайн переживает плохие сценарии — песчаную бурю и недельный "
    "топливный разрыв (таблица стрессов: хороший дизайн деградирует на "
    "доли процента, а не катастрофой).":
        "Input prices are forecasts, and you need to know which are "
        "dangerous to forecast badly (tornado), the price of each “nine” of "
        "reliability (Pareto), and how the design survives bad scenarios — "
        "a sandstorm and a week-long fuel gap (stress table: a good design "
        "degrades by fractions of a percent, not catastrophically).",

    # ---------- вкладка «Сценарии» ----------
    "Отчёт и сохранение": "Report & saving",
    "Скачать отчёт (HTML)": "Download report (HTML)",
    "Самодостаточная страница: метрики, "
    "спецификация, издержки и графики — можно "
    "отправить письмом.":
        "A self-contained page: metrics, specification, costs and charts — "
        "can be emailed.",
    "Имя сценария": "Scenario name",
    "имя сценария": "scenario name",
    "мой вариант": "my variant",
    "Скачать JSON": "Download JSON",
    "Добавить в сравнение": "Add to comparison",
    "Загрузить сохранённый": "Load a saved one",
    "Загружен {}": "Loaded {}",
    "Сравнение сценариев": "Scenario comparison",
    "← текущий": "← current",
    "сценарий": "scenario",
    "изд., $/год": "cost, $/yr",
    "LCOE, $": "LCOE, $",
    "renewable": "renewable",
    "CO₂, т": "CO₂, t",
    "Размеры оборудования по сценариям": "Equipment sizes by scenario",
    "LCOE по сценариям": "LCOE by scenario",
    "каждая группа столбцов — один сценарий из таблицы выше "
    "(имя в легенде). Так видно, как твои изменения "
    "передвигают и размеры закупки, и цену киловатт-часа.":
        "each group of bars is one scenario from the table above (name in "
        "the legend). This shows how your changes move both the purchase "
        "sizes and the cost per kilowatt-hour.",
    "Управление вариантами по паттерну Calliope «сценарий = база + "
    "переопределения». Скачанный JSON — самодостаточный пакет (входы + "
    "размеры + метрики) для письма или git; HTML-отчёт — то же для "
    "людей без Streamlit. Таблица и графики сравнения отвечают на "
    "главный переговорный вопрос: как меняются закупка и LCOE между "
    "вариантами.":
        "Managing variants by the Calliope pattern “scenario = base + "
        "overrides”. The downloaded JSON is a self-contained package "
        "(inputs + sizes + metrics) for email or git; the HTML report is "
        "the same for people without Streamlit. The comparison table and "
        "charts answer the main negotiation question: how procurement and "
        "LCOE change between variants.",

    # ---------- вкладка «Валидация» ----------
    "Сверка с внешним инструментом (REopt web / HOMER). Прогони тот же "
    "сценарий там, впиши их числа — отклонения **> 10%** будут "
    "помечены. Публичного API у HOMER нет, у REopt нужен ключ NREL — "
    "поэтому v1 сверяет вручную введённые числа, честно и прозрачно.":
        "Cross-check with an external tool (REopt web / HOMER). Run the "
        "same scenario there, enter their numbers — deviations **> 10%** "
        "are flagged. HOMER has no public API, REopt needs an NREL key — so "
        "v1 cross-checks manually entered numbers, honestly and "
        "transparently.",
    "PV референса, kWp": "Reference PV, kWp",
    "BESS референса, kWh": "Reference BESS, kWh",
    "DG референса, kW": "Reference DG, kW",
    "LCOE референса": "Reference LCOE",
    "метрика": "metric",
    "референс": "reference",
    "отклонение": "deviation",
    "вердикт": "verdict",
    "разобраться!": "investigate!",
    "ок": "ok",
    "Введи числа референса — появится таблица отклонений.":
        "Enter the reference numbers — a deviation table will appear.",
    "Внешний контроль качества: тот же сценарий в независимом "
    "инструменте, его числа — сюда, отклонение до 10% — нормальный "
    "разброс допущений. Уже проведённые сверки: Тонга в диапазоне HOMER "
    "(LCOE $0.27 при 0.25–0.32); DeGrussa против фактов ARENA "
    "(расхождение объяснено трекерами); PV-цепочка против NREL SAM и "
    "датчиков в Оклахоме (±2%); полигон NIST (нашёл, что параметры "
    "модуля должны быть полями схемы — теперь они в этой форме).":
        "External quality control: the same scenario in an independent "
        "tool, its numbers go here, deviation up to 10% is the normal "
        "spread of assumptions. Cross-checks already done: Tonga within the "
        "HOMER range (LCOE $0.27 vs 0.25–0.32); DeGrussa against ARENA "
        "facts (the gap explained by trackers); the PV chain against NREL "
        "SAM and sensors in Oklahoma (±2%); the NIST testbed (which "
        "revealed the module parameters should be schema fields — they now "
        "are, in this form).",

    # ---------- ошибки/сервис ----------
    "Оптимизация не удалась: {}": "Optimization failed: {}",
    "Проблема с входными данными: {}": "Input data problem: {}",

    # ---------- клиентская редакция v1.2 (без внутреннего жаргона) ----------
    "Заполни параметры и нажми «Пересчитать» — они наложатся "
    "на базовый сценарий, и калькулятор найдёт новый оптимум. "
    "Единицы: kW / kWh / USD.":
        "Set the parameters and press “Recalculate” — they overlay the base "
        "scenario and the calculator finds a new optimum. "
        "Units: kW / kWh / USD.",
    "Сколько литров сжигает генсет на 1 кВт*ч на номинале "
    "(datasheet). Типовой дизель ~0.27. Холостой ход "
    "учитывается в режиме точного расчёта парка (ниже).":
        "How many liters the genset burns per 1 kWh at rated load "
        "(datasheet). A typical diesel ~0.27. Idle burn is accounted for in "
        "the exact fleet mode (below).",
    "hard: каждый kWh спроса покрыт. lpsp: недопоставка не выше "
    "заданной доли. voll: модель сама решает, что дешевле — "
    "поставить или заплатить штраф за тьму.":
        "hard: every kWh of demand is met. lpsp: unmet load no higher than "
        "a set fraction. voll: the model decides what is cheaper — supply "
        "or pay the penalty for darkness.",
    "Горячий запас мощности сверх нагрузки в КАЖДЫЙ час: "
    "недогруженный дизель + доступный разряд батареи. Страхует "
    "реальную работу от сюрпризов и закрывает разрыв между "
    "идеальным планом и реальностью. 0 = выключено.":
        "Hot power headroom above the load EVERY hour: the underloaded "
        "diesel + the battery’s available discharge. Insures real operation "
        "against surprises and closes the gap between the ideal plan and "
        "reality. 0 = off.",
    "Дополнительный резерв, привязанный к выработке солнца: "
    "облако роняет PV — запас страхует. Панель сама резерв не "
    "даёт (она и есть источник неопределённости).":
        "Extra reserve tied to solar output: a cloud drops PV — the "
        "headroom insures against it. The panel itself provides no reserve "
        "(it is the source of uncertainty).",
    "MILP Точный расчёт парка (целые машины)":
        "MILP Exact fleet model (whole machines)",
    "Размеры кратны юниту (целые панели/шкафы/генсеты), а "
    "дизельный парк включается по часам — «сколько генсетов "
    "работает сейчас» — с минимальной загрузкой и холостым "
    "ходом. Честнее физика, но расчёт заметно дольше.":
        "Sizes are multiples of the unit (whole panels/cabinets/gensets), "
        "and the diesel fleet switches on by the hour — “how many gensets "
        "run now” — with a minimum load and idle burn. More honest physics, "
        "but the run takes noticeably longer.",
    "Включённый генсет не опускается ниже этой доли номинала "
    "(типично 15–30% у автономных систем). Работает только в "
    "точном расчёте парка.":
        "A running genset stays above this fraction of its rating "
        "(typically 15–30% for off-grid systems). Works only in the exact "
        "fleet mode.",
    "Постоянный расход топлива работающего генсета сверх "
    "нагрузки. Стоит денег даже вхолостую — модель гасит "
    "лишние генсеты. 0 = не моделировать. Работает только в "
    "точном расчёте парка.":
        "A running genset’s constant fuel draw on top of the load. It costs "
        "money even at idle — so the model shuts down spare gensets. 0 = "
        "don’t model. Works only in the exact fleet mode.",
    "Стрелки у метрик — сравнение с зафиксированной базой "
    "(кнопка «Зафиксировать текущий как базу» в сайдбаре)":
        "Metric arrows compare against the fixed baseline (the “Fix "
        "current as baseline” button in the sidebar)",
    "Парк генераторов: {} шт по {:g} kW · одновременно в работе "
    "до {}, в среднем {} (точный расчёт целыми машинами)":
        "Generator fleet: {} units of {:g} kW · up to {} running at once, "
        "{} on average (exact whole-machine mode)",
    "*Оценка: {} кг CO₂ на kWh дизеля · недопоставка (LPSP) = {} · "
    "сброс излишков солнца = {} kWh":
        "*Estimate: {} kg CO₂ per kWh of diesel · unmet load (LPSP) = {} · "
        "curtailed solar surplus = {} kWh",
    "Проверка надёжности": "Reliability check",
    "Риски и цены": "Risks & prices",
    "Кол-во и «установлено» — сколько ЦЕЛЫХ юнитов купить "
    "(оптимум, округлённый вверх до целых юнитов); подробно "
    "о каждой колонке — в развороте ниже.":
        "Qty and “installed” — how many WHOLE units to buy (the optimum "
        "rounded up to whole units); details on each column in the "
        "expander below.",
    "Потоки энергии за год": "Annual energy flows",
    "Солнце": "Solar",
    "Батарея": "Battery",
    "Сброс излишков": "Curtailed surplus",
    "Потери цикла": "Cycle losses",
    "ширина каждой ленты пропорциональна энергии за год "
    "(kWh). Видна вся дорога: сколько солнца ушло заводу "
    "напрямую, сколько — через батарею (и что потерялось в "
    "цикле), сколько добавил дизель и сколько излишков "
    "пришлось сбросить.":
        "the width of each ribbon is proportional to the year’s energy "
        "(kWh). The whole journey is visible: how much solar went straight "
        "to the plant, how much via the battery (and what was lost in the "
        "cycle), how much the diesel added and how much surplus had to be "
        "curtailed.",
    "Калькулятор перебрал все допустимые комбинации размеров и режимов "
    "работы за 8760 часов года и нашёл самую дешёвую, которая держит "
    "нагрузку при выбранной политике надёжности. Таблица переводит "
    "оптимум в целые единицы к закупке. Схема — топология AC-coupling: "
    "все источники параллельно на одной шине 400 В.":
        "The calculator searched every feasible combination of sizes and "
        "operating modes across the 8760 hours of the year and found the "
        "cheapest one that holds the load under the chosen reliability "
        "policy. The table converts the optimum into whole purchasable "
        "units. The diagram is the AC-coupling topology: all sources in "
        "parallel on one 400 V bus.",
    "Неделя 16–22 февраля: кто кормит завод":
        "Week 16–22 Feb: who feeds the plant",
    "Кто кормит завод по месяцам": "Who feeds the plant, month by month",
    "сезонный разрез года: в месяцы слабого солнца красный "
    "слой (дизель) толще. Помогает планировать завоз топлива "
    "по сезонам.":
        "the year in seasonal cross-section: in weak-sun months the red "
        "layer (diesel) is thicker. Helps plan fuel deliveries by season.",
    "Экономия против «100% дизель»": "Savings vs “100% diesel”",
    "Сверка: сумма статей совпадает с итогом оптимизации (${}) "
    "— две независимые дороги к одному числу.":
        "Cross-check: the sum of line items matches the optimization total "
        "(${}) — two independent roads to one number.",
    "всё из дизеля (только топливо)": "all-diesel (fuel only)",
    "гибрид (закупка + эксплуатация)": "hybrid (purchase + operation)",
    "окупаемость": "payback",
    "Накопленные затраты по годам проекта":
        "Cumulative cost over the project years",
    "год проекта": "project year",
    "красный пунктир — если продолжать жечь только дизель; "
    "синяя линия стартует выше (разовая закупка железа), но "
    "растёт медленнее (солнце бесплатное). Точка пересечения — "
    "окупаемость: дальше каждый год работает в плюс.":
        "the dashed red line is “keep burning diesel only”; the blue line "
        "starts higher (one-off hardware purchase) but grows slower (the "
        "sun is free). The crossing point is payback: beyond it every year "
        "works in your favor.",
    "Деньги системы в одном месте: CRF превращает разовые покупки в "
    "годовые платежи, NPC собирает все затраты горизонта в сегодняшних "
    "деньгах, окупаемость меряется против базовой линии «вся энергия из "
    "дизеля». У Йемена бюджет ест топливо — потому анализ на вкладке "
    "«Риски и цены» ставит цену солярки на первое место.":
        "The system’s money in one place: CRF turns one-off purchases into "
        "annual payments, NPC gathers all horizon costs in today’s money, "
        "payback is measured against the “all energy from diesel” baseline. "
        "For Yemen fuel eats the budget — that is why the analysis on the "
        "“Risks & prices” tab ranks the diesel price first.",
    "План оптимизатора «знает» весь год наперёд — реальный контроллер "
    "на площадке будущего не видит. Здесь найденные размеры проверяются "
    "пошаговым симулятором без предвидения — разница и есть запас "
    "прочности плана.":
        "The optimizer’s plan “knows” the whole year ahead — a real "
        "controller on site cannot see the future. Here the found sizes are "
        "checked by a step-by-step simulator with no foresight — the "
        "difference is the plan’s safety margin.",
    "LPSP: идеальный план": "LPSP: ideal plan",
    "LPSP: реальная работа": "LPSP: real operation",
    "Больше нуля при политике hard — реальная работа без "
    "предвидения иногда не дотягивает на размерах, ужатых "
    "оптимизацией. Лечится оперативным резервом (ползунок "
    "в сайдбаре).":
        "Greater than zero under the hard policy — real operation without "
        "foresight sometimes falls short on sizes squeezed by the "
        "optimization. Cured by the operating reserve (sidebar slider).",
    "Недопоставка в реальной работе": "Unmet load in real operation",
    "идеальный план (видит год наперёд)":
        "ideal plan (sees the year ahead)",
    "реальная работа (без предвидения)":
        "real operation (no foresight)",
    "Годовые потоки: идеальный план против реальной работы":
        "Annual flows: ideal plan vs real operation",
    "пары полос сравнивают одинаковые потоки НА ОДНИХ размерах "
    "железа. Тёмная — недостижимый идеал; светлая — "
    "приземлённая реальность. Смотри на «недопоставку»: если в "
    "реальной работе она больше нуля — добавь оперативный "
    "резерв (сайдбар) или инженерный запас.":
        "pairs of bars compare the same flows AT THE SAME hardware sizes. "
        "Dark is the unattainable ideal; light is grounded reality. Look at "
        "“unmet load”: if it is above zero in real operation — add an "
        "operating reserve (sidebar) or an engineering margin.",
    "Проверка плана на честность: найденное решение — нижняя граница "
    "затрат. Практический смысл: к размеру дизеля стоит добавлять "
    "инженерный запас — вендоры делают именно это.":
        "An honesty check of the plan: the found solution is the lower "
        "bound of cost. Practical takeaway: add an engineering margin to "
        "the diesel size — vendors do exactly that.",
    "Что будет с бюджетом при других ценах, почём каждая ступень "
    "надёжности и как план переживает плохие сценарии. Запускается по "
    "кнопке; результат сохраняется до изменения параметров.":
        "What happens to the budget under different prices, the cost of "
        "each step of reliability, and how the plan survives bad scenarios. "
        "Started by a button; the result is kept until the inputs change.",
    "Запустить анализ рисков": "Run risk analysis",
    "Что сильнее всего влияет на бюджет":
        "What moves the budget the most",
    "граница возможного (дешевле при такой надёжности не бывает)":
        "the frontier of the possible (no cheaper at this reliability)",
    "Сколько стоит надёжность": "The cost of reliability",
    "Входные цены — прогнозы, и надо знать, какие опасно прогнозировать "
    "плохо, почём каждая «девятка» надёжности и как дизайн переживает "
    "плохие сценарии — песчаную бурю и недельный топливный разрыв "
    "(таблица стрессов: хороший дизайн деградирует на доли процента, "
    "а не катастрофой).":
        "Input prices are forecasts, and you need to know which are "
        "dangerous to forecast badly, the price of each “nine” of "
        "reliability, and how the design survives bad scenarios — a "
        "sandstorm and a week-long fuel gap (stress table: a good design "
        "degrades by fractions of a percent, not catastrophically).",
    "Каждый вариант — самодостаточный пакет (входы + размеры + "
    "метрики): JSON — для архива и передачи, HTML-отчёт — для письма "
    "заказчику. Таблица и графики сравнения отвечают на главный "
    "переговорный вопрос: как меняются закупка и LCOE между вариантами.":
        "Each variant is a self-contained package (inputs + sizes + "
        "metrics): the JSON — for archiving and hand-off, the HTML report — "
        "for a letter to the client. The comparison table and charts answer "
        "the main negotiation question: how procurement and LCOE change "
        "between variants.",
    "Сверка с внешним инструментом (REopt web / HOMER). Прогони тот же "
    "сценарий там, впиши их числа — отклонения **> 10%** будут "
    "помечены. Публичного API у HOMER нет, у REopt нужен ключ NREL — "
    "поэтому сверка идёт по введённым вручную числам, честно и "
    "прозрачно.":
        "Cross-check with an external tool (REopt web / HOMER). Run the "
        "same scenario there, enter their numbers — deviations **> 10%** "
        "are flagged. HOMER has no public API, REopt needs an NREL key — so "
        "the cross-check uses manually entered numbers, honestly and "
        "transparently.",

    # ---------- фиксы аудита №2 (v1.3) ----------
    "Эскалация цены дизеля, %/год": "Diesel price escalation, %/yr",
    "Насколько цена топлива растёт каждый год сверх инфляции. "
    "Плоская цена на 20 лет занижает будущие расходы дизеля и "
    "смещает оптимум к генсету. Учитывается одним "
    "левелизационным коэффициентом (как в REopt).":
        "How much the fuel price grows each year above inflation. A flat "
        "price over 20 years understates future diesel spend and biases "
        "the optimum toward the genset. Applied as a single levelization "
        "factor (as in REopt).",
    "Солнечный год для расчёта": "Solar year for the calculation",
    "P50 — типичный год": "P50 — typical year",
    "P90 — запас на слабый год (−5%)": "P90 — weak-year margin (−5%)",
    "Спутниковый «типичный год» — это медиана (P50): в половине "
    "реальных лет солнца МЕНЬШЕ. Для критичных объектов отрасль "
    "рекомендует консервативный P90 — весь солнечный ряд "
    "умножается на 0.95.":
        "The satellite “typical year” is the median (P50): in half of real "
        "years there is LESS sun. For critical sites the industry "
        "recommends the conservative P90 — the whole solar series is "
        "multiplied by 0.95.",
    "Дизель может заряжать батарею (cycle charging)":
        "Diesel can charge the battery (cycle charging)",
    "Стратегия HOMER Cycle Charging: раз генсет уже работает, "
    "его свободная мощность заряжает батарею — позже реже "
    "включаться. Включай при многодневной пасмурности или "
    "генсете меньше пика. Проверка надёжности тоже использует "
    "эту стратегию.":
        "The HOMER Cycle Charging strategy: since the genset is already "
        "running, its spare power charges the battery — so it starts less "
        "often later. Enable for multi-day cloudy spells or a genset "
        "smaller than the peak. The reliability check uses the same "
        "strategy.",

    # ---------- большие блоки аудита №3 (v1.3) ----------
    "Если дизель пропал: кривая выживания":
        "If the diesel is gone: survival curve",
    "Доля часов года, из которых система переживает отказ":
        "Share of the year's start hours that survive the outage",
    "длительность отказа дизеля, часов": "diesel outage duration, hours",
    "Медиана выживания на солнце и батарее: {} ч · отказ "
    "стартует в каждый 3-й час года, запас батареи — из "
    "реальной траектории":
        "Median survival on solar and battery: {} h · the outage starts "
        "at every 3rd hour of the year, battery charge taken from the "
        "real trajectory",
    "каждый столбец — вероятность пережить отказ такой "
    "длины: отказ «запускался» из каждого 3-го часа года с "
    "тем запасом батареи, какой был в этот момент. Ночью "
    "запас мал — потому даже короткие отказы переживаются "
    "не всегда. Хочешь выше столбцы — больше батарея или "
    "оперативный резерв.":
        "each bar is the probability of surviving an outage of that "
        "length: the outage was “launched” from every 3rd hour of the "
        "year with whatever battery charge existed at that moment. At "
        "night the charge is low — so even short outages are not always "
        "survived. Want taller bars — more battery or an operating "
        "reserve.",
    "Проверка плана на честность: найденное решение — нижняя граница "
    "затрат, а кривая выживания показывает устойчивость к отказу "
    "дизеля не одним сценарием, а распределением по всему году. "
    "Практический смысл: к размеру дизеля стоит добавлять "
    "инженерный запас — вендоры делают именно это.":
        "An honesty check of the plan: the found solution is the lower "
        "bound of cost, and the survival curve shows resilience to a "
        "diesel outage as a distribution over the whole year, not a "
        "single scenario. Practical takeaway: add an engineering margin "
        "to the diesel size — vendors do exactly that.",
    "Альтернативные дизайны (SPORES)": "Alternative designs (SPORES)",
    "Почти та же цена — другое железо: поиск конфигураций "
    "не дороже оптимума +10%, максимально непохожих на "
    "найденную. Аргумент для переговоров и страховка от "
    "«а если батареи подорожают?»":
        "Nearly the same price — different hardware: a search for "
        "configurations no costlier than the optimum +10% and maximally "
        "unlike the one found. A negotiation argument and insurance "
        "against “what if batteries get expensive?”",
    "Найти альтернативы (+10% к издержкам)":
        "Find alternatives (+10% cost)",
    "оптимум": "optimum",
    "вариант {}": "variant {}",
    "Оптимум и альтернативы не дороже +10%":
        "The optimum and alternatives within +10%",
    "каждая группа столбцов — один дизайн: первый — "
    "оптимум, остальные — варианты в пределах потолка "
    "издержек. Если вариант почти без батареи стоит на "
    "7% дороже — это цена независимости от поставок "
    "аккумуляторов.":
        "each group of bars is one design: the first is the optimum, the "
        "rest are variants within the cost ceiling. If a nearly "
        "battery-free variant costs 7% more — that is the price of "
        "independence from battery supply.",
    "Каждый вариант — самодостаточный пакет (входы + размеры + "
    "метрики): JSON — для архива и передачи, HTML-отчёт — для письма "
    "заказчику. Таблица и графики сравнения отвечают на главный "
    "переговорный вопрос: как меняются закупка и LCOE между "
    "вариантами; SPORES добавляет к нему веер «другого железа за "
    "почти те же деньги».":
        "Each variant is a self-contained package (inputs + sizes + "
        "metrics): the JSON — for archiving and hand-off, the HTML "
        "report — for a letter to the client. The comparison table and "
        "charts answer the main negotiation question: how procurement "
        "and LCOE change between variants; SPORES adds a fan of "
        "“different hardware for nearly the same money”.",

    # ---------- плейбук клиентских графиков (аудит №4) ----------
    "Типовые сутки: кто кормит завод в среднем за год":
        "Typical day: who feeds the plant on average over the year",
    "час суток": "hour of day",
    "усреднённые по всем дням года сутки: жёлтое солнце "
    "днём, зелёная батарея вечером, красный дизель ночью — "
    "читается без пояснений. Пунктир — средний спрос; "
    "детали конкретной недели — на графиках ниже.":
        "a day averaged over all days of the year: yellow solar by day, "
        "green battery in the evening, red diesel at night — reads without "
        "explanations. The dashed line is average demand; the details of a "
        "specific week are in the charts below.",
    "Цена киловатт-часа: проект против «только дизель»":
        "Price per kilowatt-hour: the project vs “diesel only”",
    "только дизель": "diesel only",
    "проект PV+BESS+DG": "PV+BESS+DG project",
    "топливо дизеля": "diesel fuel",
    "левая колонка — сколько стоит киловатт-час, если жечь "
    "только дизель; правая — цена проекта, разложенная на "
    "слагаемые (цвета — как во всех графиках). Разница колонок "
    "— экономия на каждом киловатт-часе.":
        "the left column is the cost of a kilowatt-hour when burning "
        "diesel only; the right one is the project’s price broken into "
        "components (colors as on all charts). The difference between the "
        "columns is the saving on every kilowatt-hour.",
    "Водопад окупаемости: вложение и возврат по годам":
        "Payback waterfall: investment and returns by year",
    "CAPEX": "CAPEX",
    "окупился: год {}": "breaks even: year {}",
    "красный столбец — разовое вложение; зелёные — экономия "
    "каждого года против «только дизель» (с учётом дорожающего "
    "топлива). Где лесенка пересекает ноль — там деньги "
    "вернулись; дальше проект работает в плюс.":
        "the red bar is the one-off investment; the green ones are each "
        "year’s savings vs “diesel only” (fuel escalation included). Where "
        "the staircase crosses zero the money has returned; beyond that "
        "the project works in your favor.",

    # ---------- обёртки-помощники ----------
    "Что здесь происходит и зачем.": "What happens here and why.",
    "Как читать:": "How to read it:",
}

# Глоссарий вынесен отдельно (большой блок markdown).
GLOSSARY_RU = """
- **kW / kWh / kWp** — мощность (скорость) / энергия (количество =
  мощность × время) / паспортная мощность панелей при идеальном солнце.
- **CAPEX / O&M** — разовые капитальные затраты / ежегодная эксплуатация
  и обслуживание.
- **CRF** — capital recovery factor `r(1+r)ⁿ/((1+r)ⁿ−1)`: размазывает
  CAPEX в равные годовые платежи (как аннуитет ипотеки) — только так
  панели сравнимы с соляркой.
- **NPC** — net present cost: все затраты горизонта в сегодняшних деньгах.
- **LCOE** — levelized cost of energy: годовые издержки ÷ поставленные
  kWh; цена киловатт-часа «под ключ».
- **LPSP** — доля недопоставленной энергии за год (0% = всё поставлено;
  1% ≈ 87 часов простоя).
- **Renewable fraction** — доля поставки НЕ из дизеля.
- **SOC** — state of charge: текущий запас батареи, kWh; ниже «пола»
  (20%) не разряжаем — бережём ресурс.
- **RTE** — КПД цикла батареи (см. подсказку у ползунка).
- **Curtailment** — сброс лишней солнечной выработки (батарея полна,
  нагрузка сыта) — нормальная цена дешёвых панелей.
- **Shortfall** — недопоставка: спрос, который не покрыл никто.
- **VOLL** — value of lost load: цена недопоставленного kWh потребителю.
- **Clipping** — срезка пиков DC инвертором меньшего номинала (DC/AC).
- **Perfect foresight** — модель «знает» весь год наперёд; реальный
  контроллер — нет, разрыв меряем во вкладке «Проверка надёжности».
- **Pareto-фронт / колено** — кривая «стоимость ↔ надёжность» и точка,
  после которой уступки почти не экономят.
- **Tornado** — чей ценовой прогноз сильнее всего качает результат.
"""

GLOSSARY_EN = """
- **kW / kWh / kWp** — power (rate) / energy (quantity = power × time) /
  nameplate panel power under ideal sun.
- **CAPEX / O&M** — one-off capital cost / annual operation and
  maintenance.
- **CRF** — capital recovery factor `r(1+r)ⁿ/((1+r)ⁿ−1)`: spreads CAPEX
  into equal annual payments (like a mortgage annuity) — the only way
  panels become comparable with diesel.
- **NPC** — net present cost: all horizon costs in today’s money.
- **LCOE** — levelized cost of energy: annual cost ÷ energy served; the
  turnkey price of a kilowatt-hour.
- **LPSP** — fraction of energy not supplied over the year (0% = all
  supplied; 1% ≈ 87 hours of downtime).
- **Renewable fraction** — share of supply NOT from diesel.
- **SOC** — state of charge: current battery charge, kWh; below the
  “floor” (20%) we don’t discharge — protecting the cells.
- **RTE** — battery round-trip efficiency (see the slider tooltip).
- **Curtailment** — dumping surplus solar (battery full, load satisfied)
  — the normal price of cheap panels.
- **Shortfall** — unmet load: demand nobody covered.
- **VOLL** — value of lost load: price of an unserved kWh to the consumer.
- **Clipping** — trimming DC peaks by a smaller-rated inverter (DC/AC).
- **Perfect foresight** — the model “knows” the whole year ahead; a real
  controller does not — the gap is measured on the “Reliability check” tab.
- **Pareto front / knee** — the “cost ↔ reliability” curve and the point
  after which concessions barely save money.
- **Tornado** — whose price forecast shakes the result the most.
"""


COLUMNS_HELP_RU = """
- **Компонент** — подсистема микрогрида: солнечные панели, ёмкость
  батареи, мощность батареи (инверторы PCS) и дизель-генератор.
- **Что заказать** — конкретный физический товар, который закупают
  штуками (панель, батарейный шкаф, инвертор PCS, генсет).
- **Кол-во, шт** — сколько ЦЕЛЫХ юнитов купить: ceil(оптимум ÷ номинал
  юнита). Дробную мощность заказать нельзя.
- **Номинал юнита** — мощность или ёмкость ОДНОГО юнита (панель
  0.58 kWp, шкаф 261 kWh, PCS 125 kW, генсет 1000 kW).
- **Установлено** — кол-во × номинал: фактическая купленная
  мощность/ёмкость. Чуть выше непрерывного LP-оптимума — это запас
  округления вверх.
- **Цена/юнит, $** — стоимость одного юнита (номинал × цена за kW или
  kWh из сценария).
- **CAPEX, $** — разовые капитальные затраты строки: кол-во × цена
  юнита. Строка ИТОГО — суммарная закупка.
- **O&M, $/год** — ежегодное обслуживание этого оборудования. Топливо
  дизеля сюда НЕ входит — оно на вкладке «Экономика».
- **Производство, kWh/год** — годовая энергия: у PV — выработка панелей
  (часть напрямую заводу, часть в батарею, чуть-чуть в сброс); у ёмкости
  BESS — сколько батарея отдала за год (разряд); у мощности PCS —
  прочерк (это преобразователь, сам энергию не производит); у DG —
  выработка дизеля.
"""

COLUMNS_HELP_EN = """
- **Component** — the microgrid subsystem: solar panels, battery energy,
  battery power (PCS inverters) and the diesel generator.
- **What to order** — the concrete physical item bought in whole pieces
  (panel, battery cabinet, PCS inverter, genset).
- **Qty, pcs** — how many WHOLE units to buy: ceil(optimum ÷ unit
  rating). You cannot order a fractional capacity.
- **Unit rating** — power or energy of ONE unit (panel 0.58 kWp, cabinet
  261 kWh, PCS 125 kW, genset 1000 kW).
- **Installed** — qty × rating: the actual purchased power/capacity.
  Slightly above the continuous LP optimum — that is the round-up margin.
- **Unit price, $** — cost of one unit (rating × price per kW or kWh from
  the scenario).
- **CAPEX, $** — one-off capital cost of the row: qty × unit price. The
  TOTAL row is the whole purchase.
- **O&M, $/yr** — annual maintenance of this equipment. Diesel fuel is
  NOT included here — it is on the “Economics” tab.
- **Output, kWh/yr** — annual energy: for PV — panel generation (part
  straight to the plant, part to the battery, a little curtailed); for
  BESS energy — how much the battery delivered over the year (discharge);
  for PCS power — a dash (it is a converter, it does not produce energy
  itself); for DG — diesel output.
"""


# ---------- реестр языков ----------
# Русский — язык-источник (ключи), остальные — словари переводов.
# Добавить язык: положить словарь RU->XX рядом и вписать сюда одну
# строку; app.py подхватит его автоматически (список берётся отсюда).
from app_i18n_cs import COLUMNS_HELP_CS, GLOSSARY_CS, TRANSLATIONS_CS

LANGUAGES: tuple[str, ...] = ("RU", "EN", "CS")

_CATALOGS: dict[str, dict[str, str]] = {
    "EN": TRANSLATIONS,
    "CS": TRANSLATIONS_CS,
}

_GLOSSARIES: dict[str, str] = {
    "RU": GLOSSARY_RU,
    "EN": GLOSSARY_EN,
    "CS": GLOSSARY_CS,
}

_COLUMNS_HELP: dict[str, str] = {
    "RU": COLUMNS_HELP_RU,
    "EN": COLUMNS_HELP_EN,
    "CS": COLUMNS_HELP_CS,
}


def make_t(lang: str):
    """Возвращает функцию перевода t() для выбранного языка.

    Неизвестный язык или отсутствующий ключ — русский as-is: интерфейс
    не падает, просто показывает язык-источник (graceful fallback).
    """
    catalog = _CATALOGS.get(lang)

    def t(s: str) -> str:
        return catalog.get(s, s) if catalog is not None else s
    return t


def get_glossary(lang: str) -> str:
    """Словарь терминов на выбранном языке (нет — русский)."""
    return _GLOSSARIES.get(lang, GLOSSARY_RU)


def get_columns_help(lang: str) -> str:
    """Пояснения к колонкам спецификации (нет — русские)."""
    return _COLUMNS_HELP.get(lang, COLUMNS_HELP_RU)
