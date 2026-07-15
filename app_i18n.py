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
- **Perfect foresight** — LP-солвер «знает» весь год наперёд; реальный
  контроллер — нет, разрыв меряем во вкладке «Rule vs LP».
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
- **Perfect foresight** — the LP solver “knows” the whole year ahead; a
  real controller does not — the gap is measured on the “Rule vs LP” tab.
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


def make_t(lang: str):
    """Возвращает функцию перевода t() для выбранного языка."""
    def t(s: str) -> str:
        if lang == "EN":
            return TRANSLATIONS.get(s, s)
        return s
    return t
