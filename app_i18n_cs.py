"""Чешские переводы интерфейса GreenHouse (RU -> CS).

Контракт тот же, что у английского словаря в app_i18n.py: КЛЮЧ — русская
строка-источник (ровно та, что стоит в app.py внутри T(...) / tab_footer /
legend_help), ЗНАЧЕНИЕ — чешский перевод. Нет ключа — t() честно вернёт
русский (graceful fallback), интерфейс не падает.

Переводятся ТОЛЬКО тексты. Числа, единицы (kW / kWh / USD), внутренние
ключи данных и позиционные плейсхолдеры {} / {:g} сохраняются один в один —
иначе .format() сломается на другом языке.

Полноту охвата стережёт тест tests/test_i18n_cs.py: он AST-разбором
вытаскивает из app.py все переводимые строки и требует чешское значение
для каждой.
"""

TRANSLATIONS_CS: dict[str, str] = {
    # ---------- подвалы вкладок и большие пояснения ----------
    "Заполни параметры и нажми «Пересчитать» — они наложатся "
    "на базовый сценарий, и калькулятор найдёт новый оптимум. "
    "Единицы: kW / kWh / USD.":
        "Vyplň parametry a stiskni «Přepočítat» — překryjí základní scénář "
        "a kalkulátor najde nové optimum. Jednotky: kW / kWh / USD.",
    "Нагрузка": "Zatížení",
    "Источник профиля": "Zdroj profilu",
    "Зафиксировать текущий как базу": "Uložit současné jako základ",
    "Оптимальная конфигурация": "Optimální konfigurace",
    "Стрелки у метрик — сравнение с зафиксированной базой "
    "(кнопка «Зафиксировать текущий как базу» в сайдбаре)":
        "Šipky u metrik porovnávají s uloženým základem (tlačítko «Uložit "
        "současné jako základ» v postranním panelu)",
    "Годовые издержки": "Roční náklady",
    "Renewable": "Obnovitelné",
    "Дизель": "Diesel",
    "CO₂ (оценка*)": "CO₂ (odhad*)",
    "Калькулятор перебрал все допустимые комбинации размеров и режимов "
    "работы за 8760 часов года и нашёл самую дешёвую, которая держит "
    "нагрузку при выбранной политике надёжности. Таблица переводит "
    "оптимум в целые единицы к закупке. Схема — топология AC-coupling: "
    "все источники параллельно на одной шине 400 В.":
        "Kalkulátor prošel všechny přípustné kombinace velikostí a "
        "provozních režimů za 8760 hodin roku a našel nejlevnější, která "
        "udrží zatížení při zvolené politice spolehlivosti. Tabulka "
        "převádí optimum na celé jednotky k nákupu. Schéma je topologie "
        "AC-coupling: všechny zdroje paralelně na jedné sběrnici 400 V.",
    "Это «рентген» найденного решения на характерной неделе февраля. "
    "Именно по этим двум графикам мы поймали переразмеренность "
    "вендорской батареи: она наполнялась до потолка один день в году.":
        "Toto je «rentgen» nalezeného řešení v charakteristickém únorovém "
        "týdnu. Právě podle těchto dvou grafů jsme odhalili "
        "předimenzovanou baterii dodavatele: naplnila se až po strop "
        "jediný den v roce.",
    "высота столбца — энергия месяца с 1 kWp. В Сане зима "
    "солнечнее лета (июльская облачность нагорья) — худший "
    "сезон солнца совпадает с круглогодичной нагрузкой, поэтому "
    "летом дизель работает больше.":
        "výška sloupce je energie měsíce z 1 kWp. V Saná je zima "
        "slunečnější než léto (červencová oblačnost náhorní plošiny) — "
        "nejhorší solární sezóna se kryje s celoročním zatížením, proto "
        "diesel v létě běží více.",
    "Это два входных ряда, из которых следует всё остальное: спрос "
    "(нагрузка по часам) и предложение (выработка 1 kWp из спутникового "
    "«типичного года» PVGIS через модель PVWatts). Любое странное число "
    "на других вкладках сначала проверяют здесь.":
        "Toto jsou dvě vstupní řady, ze kterých plyne všechno ostatní: "
        "poptávka (zatížení po hodinách) a nabídka (výroba 1 kWp ze "
        "satelitního «typického roku» PVGIS přes model PVWatts). Každé "
        "podivné číslo na ostatních záložkách se ověřuje nejdřív tady.",
    "левая колонка — сколько стоит киловатт-час, если жечь "
    "только дизель; правая — цена проекта, разложенная на "
    "слагаемые (цвета — как во всех графиках). Разница колонок "
    "— экономия на каждом киловатт-часе.":
        "levý sloupec je cena kilowatthodiny, když se pálí jen diesel; "
        "pravý je cena projektu rozložená na složky (barvy jako ve všech "
        "grafech). Rozdíl sloupců je úspora na každé kilowatthodině.",
    "цвет полосы = технология (жёлтый PV, зелёный BESS, красный "
    "DG — как на всех графиках); серый — обслуживание всего "
    "железа, тёмно-красный — солярка. «Капитал X» — это CAPEX, "
    "размазанный формулой CRF в равные годовые платежи по сроку "
    "жизни технологии.":
        "barva pruhu = technologie (žlutá PV, zelená BESS, červená DG — "
        "jako ve všech grafech); šedá je údržba veškerého zařízení, "
        "tmavě červená je nafta. «Kapitál X» je CAPEX rozprostřený "
        "vzorcem CRF do stejných ročních plateb po dobu životnosti "
        "technologie.",
    "красный пунктир — если продолжать жечь только дизель; "
    "синяя линия стартует выше (разовая закупка железа), но "
    "растёт медленнее (солнце бесплатное). Точка пересечения — "
    "окупаемость: дальше каждый год работает в плюс.":
        "červená čárkovaná čára je «pálit dál jen diesel»; modrá čára "
        "startuje výš (jednorázový nákup zařízení), ale roste pomaleji "
        "(slunce je zdarma). Průsečík je návratnost: dál každý rok "
        "pracuje ve váš prospěch.",
    "красный столбец — разовое вложение; зелёные — экономия "
    "каждого года против «только дизель» (с учётом дорожающего "
    "топлива). Где лесенка пересекает ноль — там деньги "
    "вернулись; дальше проект работает в плюс.":
        "červený sloupec je jednorázová investice; zelené jsou úspory "
        "každého roku proti «jen diesel» (včetně zdražujícího paliva). "
        "Kde schodiště protne nulu, tam se peníze vrátily; dál projekt "
        "pracuje ve váš prospěch.",
    "Деньги системы в одном месте: CRF превращает разовые покупки в "
    "годовые платежи, NPC собирает все затраты горизонта в сегодняшних "
    "деньгах, окупаемость меряется против базовой линии «вся энергия из "
    "дизеля». У Йемена бюджет ест топливо — потому анализ на вкладке "
    "«Риски и цены» ставит цену солярки на первое место.":
        "Peníze systému na jednom místě: CRF mění jednorázové nákupy na "
        "roční platby, NPC sbírá všechny náklady horizontu v dnešních "
        "penězích, návratnost se měří proti základní linii «veškerá "
        "energie z dieselu». V Jemenu spolyká rozpočet palivo — proto "
        "analýza na záložce «Rizika a ceny» staví cenu nafty na první "
        "místo.",
    "пары полос сравнивают одинаковые потоки НА ОДНИХ размерах "
    "железа. Тёмная — недостижимый идеал; светлая — "
    "приземлённая реальность. Смотри на «недопоставку»: если в "
    "реальной работе она больше нуля — добавь оперативный "
    "резерв (сайдбар) или инженерный запас.":
        "dvojice pruhů porovnávají stejné toky PŘI STEJNÝCH velikostech "
        "zařízení. Tmavý je nedosažitelný ideál; světlý je přízemní "
        "realita. Sleduj «nedodávku»: pokud je v reálném provozu nad "
        "nulou — přidej provozní rezervu (postranní panel) nebo "
        "inženýrskou zálohu.",
    "каждый столбец — вероятность пережить отказ такой "
    "длины: отказ «запускался» из каждого 3-го часа года с "
    "тем запасом батареи, какой был в этот момент. Ночью "
    "запас мал — потому даже короткие отказы переживаются "
    "не всегда. Хочешь выше столбцы — больше батарея или "
    "оперативный резерв.":
        "každý sloupec je pravděpodobnost přežít výpadek této délky: "
        "výpadek se «spouštěl» z každé 3. hodiny roku s tou zásobou "
        "baterie, jaká v tu chvíli byla. V noci je zásoba malá — proto "
        "ani krátké výpadky nejsou vždy přežity. Chceš vyšší sloupce — "
        "větší baterii nebo provozní rezervu.",
    "Проверка плана на честность: найденное решение — нижняя граница "
    "затрат, а кривая выживания показывает устойчивость к отказу "
    "дизеля не одним сценарием, а распределением по всему году. "
    "Практический смысл: к размеру дизеля стоит добавлять "
    "инженерный запас — вендоры делают именно это.":
        "Kontrola poctivosti plánu: nalezené řešení je dolní mez "
        "nákladů, a křivka přežití ukazuje odolnost proti výpadku "
        "dieselu ne jedním scénářem, ale rozdělením přes celý rok. "
        "Praktický závěr: k velikosti dieselu se vyplatí přidat "
        "inženýrskou zálohu — dodavatelé dělají přesně to.",
    "Входные цены — прогнозы, и надо знать, какие опасно прогнозировать "
    "плохо, почём каждая «девятка» надёжности и как дизайн переживает "
    "плохие сценарии — песчаную бурю и недельный топливный разрыв "
    "(таблица стрессов: хороший дизайн деградирует на доли процента, "
    "а не катастрофой).":
        "Vstupní ceny jsou prognózy a je třeba vědět, které je nebezpečné "
        "odhadnout špatně, kolik stojí každá «devítka» spolehlivosti a jak "
        "návrh přežije špatné scénáře — písečnou bouři a týdenní výpadek "
        "paliva (tabulka zátěží: dobrý návrh degraduje o zlomky procenta, "
        "ne katastrofou).",
    "Каждый вариант — самодостаточный пакет (входы + размеры + "
    "метрики): JSON — для архива и передачи, HTML-отчёт — для письма "
    "заказчику. Таблица и графики сравнения отвечают на главный "
    "переговорный вопрос: как меняются закупка и LCOE между "
    "вариантами; SPORES добавляет к нему веер «другого железа за "
    "почти те же деньги».":
        "Každá varianta je soběstačný balík (vstupy + velikosti + "
        "metriky): JSON pro archiv a předání, HTML report pro dopis "
        "zákazníkovi. Srovnávací tabulka a grafy odpovídají na hlavní "
        "vyjednávací otázku: jak se mezi variantami mění nákup a LCOE; "
        "SPORES k tomu přidává vějíř «jiného zařízení za skoro stejné "
        "peníze».",
    "Внешний контроль качества: тот же сценарий в независимом "
    "инструменте, его числа — сюда, отклонение до 10% — нормальный "
    "разброс допущений. Уже проведённые сверки: Тонга в диапазоне HOMER "
    "(LCOE $0.27 при 0.25–0.32); DeGrussa против фактов ARENA "
    "(расхождение объяснено трекерами); PV-цепочка против NREL SAM и "
    "датчиков в Оклахоме (±2%); полигон NIST (нашёл, что параметры "
    "модуля должны быть полями схемы — теперь они в этой форме).":
        "Externí kontrola kvality: stejný scénář v nezávislém nástroji, "
        "jeho čísla sem, odchylka do 10% je normální rozptyl předpokladů. "
        "Již provedená porovnání: Tonga v rozsahu HOMER (LCOE $0.27 proti "
        "0.25–0.32); DeGrussa proti faktům ARENA (rozdíl vysvětlen "
        "trackery); PV řetězec proti NREL SAM a senzorům v Oklahomě "
        "(±2%); polygon NIST (odhalil, že parametry modulu mají být poli "
        "schématu — nyní jsou v tomto formuláři).",

    # ---------- сайдбар: нагрузка и цены ----------
    "Профиль нагрузки — ряд «сколько kW потребляет завод в каждый "
    "час». CSV: колонки timestamp,load_kw; равномерный шаг; 2026 год.":
        "Profil zatížení — řada «kolik kW závod odebírá v každé hodině». "
        "CSV: sloupce timestamp,load_kw; rovnoměrný krok; rok 2026.",
    "CSV (используется в режиме «CSV-файл»)":
        "CSV (použije se v režimu «CSV soubor»)",
    "Цены": "Ceny",
    "CAPEX PV, $/kW": "CAPEX PV, $/kW",
    "CAPEX BESS, $/kWh": "CAPEX BESS, $/kWh",
    "Цена дизеля, $/литр": "Cena nafty, $/litr",
    "Удельный расход, л/кВт*ч": "Měrná spotřeba, l/kWh",
    "Эскалация цены дизеля, %/год": "Eskalace ceny nafty, %/rok",
    "PV-модуль и инвертор (datasheet)": "PV modul a střídač (datasheet)",
    "КПД инвертора": "Účinnost střídače",
    "Темп. коэффициент, %/°C": "Teplotní koeficient, %/°C",
    "DC/AC (панели к инвертору)": "DC/AC (panely ke střídači)",
    "Монтаж панелей": "Montáž panelů",
    "Солнечный год для расчёта": "Solární rok pro výpočet",
    "Батарея и площадка": "Baterie a lokalita",
    "RTE батареи": "RTE baterie",
    "Площадь под PV, м²": "Plocha pro PV, m²",
    "Коридоры поиска (максимумы)": "Rozsahy hledání (maxima)",
    "Макс. PV, kWp": "Max. PV, kWp",
    "Макс. BESS, kWh": "Max. BESS, kWh",
    "Макс. DG, kW": "Max. DG, kW",
    "Надёжность": "Spolehlivost",
    "Политика": "Politika",
    "LPSP-цель, % (для режима lpsp)": "Cíl LPSP, % (pro režim lpsp)",
    "VOLL, $/kWh (для режима voll)": "VOLL, $/kWh (pro režim voll)",
    "Оперативный резерв, % нагрузки": "Provozní rezerva, % zatížení",
    "Резерв на PV, %": "Rezerva na PV, %",
    "Дизель может заряжать батарею (cycle charging)":
        "Diesel může nabíjet baterii (cycle charging)",
    "Циклический SOC (годовое кольцо)": "Cyklický SOC (roční kruh)",
    "MILP Точный расчёт парка (целые машины)":
        "MILP Přesný výpočet parku (celé stroje)",
    "Целые машины + стадирование дизеля (медленнее)":
        "Celé stroje + postupné spínání dieselu (pomalejší)",
    "Мин. загрузка генсета, %": "Min. zatížení agregátu, %",
    "Холостой ход, л/ч на генсет": "Volnoběh, l/h na agregát",
    "Пересчитать": "Přepočítat",
    "Словарь терминов": "Slovník pojmů",

    # ---------- вкладки ----------
    "Конфигурация": "Konfigurace",
    "Диспетчеризация": "Dispečink",
    "Ресурсы": "Zdroje",
    "Экономика": "Ekonomika",
    "Проверка надёжности": "Kontrola spolehlivosti",
    "Риски и цены": "Rizika a ceny",
    "Сценарии": "Scénáře",
    "Валидация": "Validace",

    # ---------- вкладка «Конфигурация» ----------
    "Спецификация закупки (bill of materials)":
        "Specifikace nákupu (kusovník)",
    "Кол-во и «установлено» — сколько ЦЕЛЫХ юнитов купить "
    "(оптимум, округлённый вверх до целых юнитов); подробно "
    "о каждой колонке — в развороте ниже.":
        "Počet a «instalováno» — kolik CELÝCH jednotek koupit (optimum "
        "zaokrouhlené nahoru na celé jednotky); podrobně ke každému "
        "sloupci v rozbalení níže.",
    "тёмная полоса — оптимум при текущих "
    "параметрах формы; светлая — «база», которую ты "
    "зафиксировал для сравнения. Разошлись — значит, твои "
    "изменения передвинули оптимум.":
        "tmavý pruh je optimum při současných parametrech formuláře; "
        "světlý je «základ», který sis uložil pro srovnání. Rozešly se — "
        "znamená to, že tvé změny posunuly optimum.",
    "Энергобаланс года": "Energetická bilance roku",
    "жёлтое — солнце, ушедшее заводу сразу; "
    "зелёное — то же солнце, но отложенное батареей на "
    "вечер/ночь (минус потери цикла); красное — дизель. "
    "Красный сектор растёт — система дрейфует от «солнце с "
    "резервом» к «дизель с довеском».":
        "žlutá je slunce, které šlo do závodu rovnou; zelená je totéž "
        "slunce, ale odložené baterií na večer/noc (mínus ztráty cyklu); "
        "červená je diesel. Roste-li červený sektor, systém se posouvá "
        "od «slunce se zálohou» k «dieselu s přídavkem».",
    "ширина каждой ленты пропорциональна энергии за год "
    "(kWh). Видна вся дорога: сколько солнца ушло заводу "
    "напрямую, сколько — через батарею (и что потерялось в "
    "цикле), сколько добавил дизель и сколько излишков "
    "пришлось сбросить.":
        "šířka každé stuhy je úměrná energii za rok (kWh). Je vidět celá "
        "cesta: kolik slunce šlo do závodu přímo, kolik přes baterii "
        "(a co se ztratilo v cyklu), kolik přidal diesel a kolik "
        "přebytků bylo nutné oříznout.",
    "Схема системы (AC-coupling, шина 400 В)":
        "Schéma systému (AC-coupling, sběrnice 400 V)",

    # ---------- вкладка «Диспетчеризация» ----------
    "усреднённые по всем дням года сутки: жёлтое солнце "
    "днём, зелёная батарея вечером, красный дизель ночью — "
    "читается без пояснений. Пунктир — средний спрос; "
    "детали конкретной недели — на графиках ниже.":
        "den zprůměrovaný přes všechny dny roku: žluté slunce přes den, "
        "zelená baterie večer, červený diesel v noci — čte se bez "
        "vysvětlivek. Čárkovaná čára je průměrná poptávka; detaily "
        "konkrétního týdne jsou v grafech níže.",
    "три цветных слоя складываются (стек) и обязаны "
    "дотягиваться до пунктирного спроса — любой зазор был бы "
    "недопоставкой. Жёлтый низ — прямое солнце днём; зелёный "
    "появляется вечером (батарея отдаёт дневной запас); "
    "красный — предрассветные часы, когда батарея у пола.":
        "tři barevné vrstvy se sčítají (stack) a musí dosáhnout k "
        "čárkované poptávce — jakákoli mezera by byla nedodávka. Žlutý "
        "spodek je přímé slunce ve dne; zelená se objevuje večer (baterie "
        "vydává denní zásobu); červená jsou předrozbřeskové hodiny, kdy "
        "je baterie na dně.",
    "зелёная линия дышит сутками: днём вверх (заряд "
    "солнечным избытком), вечером вниз. Пунктирные линии — "
    "границы: ниже красной не разряжаем (ресурс ячеек), выше "
    "серой физически некуда. Линия редко касается потолка — "
    "батарея великовата; бьётся об пол каждую ночь — мала.":
        "zelená čára dýchá v denním rytmu: ve dne nahoru (nabíjení "
        "solárním přebytkem), večer dolů. Čárkované čáry jsou meze: pod "
        "červenou nevybíjíme (životnost článků), nad šedou fyzicky není "
        "kam. Dotýká-li se čára stropu zřídka, baterie je předimenzovaná; "
        "naráží-li na dno každou noc, je malá.",
    "сезонный разрез года: в месяцы слабого солнца красный "
    "слой (дизель) толще. Помогает планировать завоз топлива "
    "по сезонам.":
        "sezónní řez rokem: v měsících se slabým sluncem je červená "
        "vrstva (diesel) silnější. Pomáhá plánovat závoz paliva po "
        "sezónách.",

    # ---------- вкладка «Ресурсы» ----------
    "Годовая выработка солнца": "Roční výroba ze slunce",
    "Энергия нагрузки за год": "Energie zatížení za rok",
    "Шаг данных Δt": "Krok dat Δt",
    "ступеньки — смена 08–18 на дневной мощности, "
    "ночью — дежурная база. Это СПРОС, который система обязана "
    "покрывать каждый час.":
        "schody jsou směna 08–18 na denním výkonu, v noci pohotovostní "
        "základ. Toto je POPTÁVKA, kterou systém musí pokrýt každou "
        "hodinu.",
    "обе кривые — «сколько даёт 1 kWp панелей». "
    "Жёлтая — лучший день года (зимой!), зелёная — облачный "
    "июнь. Итоговая выработка = эта кривая × размер PV.":
        "obě křivky ukazují «kolik dá 1 kWp panelů». Žlutá je nejlepší "
        "den roku (v zimě!), zelená je oblačný červen. Výsledná výroba = "
        "tato křivka × velikost PV.",

    # ---------- вкладка «Экономика» ----------
    "CAPEX (разово)": "CAPEX (jednorázově)",
    "NPC (за горизонт)": "NPC (za horizont)",
    "База «100% дизель»": "Základ «100% diesel»",
    "Экономия против «100% дизель»": "Úspora proti «100% diesel»",
    "Окупаемость": "Návratnost",

    # ---------- вкладка «Проверка надёжности» ----------
    "План оптимизатора «знает» весь год наперёд — реальный контроллер "
    "на площадке будущего не видит. Здесь найденные размеры проверяются "
    "пошаговым симулятором без предвидения — разница и есть запас "
    "прочности плана.":
        "Plán optimalizátoru «zná» celý rok dopředu — reálný regulátor na "
        "místě do budoucnosti nevidí. Zde se nalezené velikosti ověřují "
        "krokovým simulátorem bez předvídavosti — rozdíl je bezpečnostní "
        "rezerva plánu.",
    "LPSP: идеальный план": "LPSP: ideální plán",
    "LPSP: реальная работа": "LPSP: reálný provoz",
    "Недопоставка в реальной работе": "Nedodávka v reálném provozu",
    "Если дизель пропал: кривая выживания":
        "Když diesel vypadne: křivka přežití",

    # ---------- вкладка «Риски и цены» ----------
    "Что будет с бюджетом при других ценах, почём каждая ступень "
    "надёжности и как план переживает плохие сценарии. Запускается по "
    "кнопке; результат сохраняется до изменения параметров.":
        "Co se stane s rozpočtem při jiných cenách, kolik stojí každý "
        "stupeň spolehlivosti a jak plán přežije špatné scénáře. Spouští "
        "se tlačítkem; výsledek se uchová do změny parametrů.",
    "каждая строка — один параметр, качавшийся в своём "
    "диапазоне; пунктир — издержки при исходных ценах. Чем "
    "ДЛИННЕЕ полоса целиком, тем важнее уточнять прогноз "
    "этого параметра до подписания контракта.":
        "každý řádek je jeden parametr rozkývaný ve svém rozsahu; "
        "čárkovaná čára jsou náklady při původních cenách. Čím DELŠÍ je "
        "pruh celkově, tím důležitější je zpřesnit prognózu tohoto "
        "parametru před podpisem smlouvy.",
    "каждая точка — отдельная оптимизация с разрешённой "
    "недопоставкой. Слева-вверху дорогая абсолютная "
    "надёжность; вправо кривая быстро падает и — после "
    "красного колена — почти выполаживается: дальнейшие "
    "уступки дают копейки.":
        "každý bod je samostatná optimalizace s povolenou nedodávkou. "
        "Vlevo nahoře je drahá absolutní spolehlivost; doprava křivka "
        "rychle klesá a — za červeným kolenem — se téměř vyrovnává: "
        "další ústupky přinášejí drobné.",

    # ---------- вкладка «Сценарии» ----------
    "Отчёт и сохранение": "Report a uložení",
    "Скачать отчёт (HTML)": "Stáhnout report (HTML)",
    "Имя сценария": "Název scénáře",
    "Скачать JSON": "Stáhnout JSON",
    "Добавить в сравнение": "Přidat do srovnání",
    "Загрузить сохранённый": "Načíst uložený",
    "каждая группа столбцов — один сценарий из таблицы выше "
    "(имя в легенде). Так видно, как твои изменения "
    "передвигают и размеры закупки, и цену киловатт-часа.":
        "každá skupina sloupců je jeden scénář z tabulky výše (název v "
        "legendě). Tak je vidět, jak tvé změny posouvají jak velikosti "
        "nákupu, tak cenu kilowatthodiny.",
    "Альтернативные дизайны (SPORES)": "Alternativní návrhy (SPORES)",
    "Почти та же цена — другое железо: поиск конфигураций "
    "не дороже оптимума +10%, максимально непохожих на "
    "найденную. Аргумент для переговоров и страховка от "
    "«а если батареи подорожают?»":
        "Skoro stejná cena — jiné zařízení: hledání konfigurací ne "
        "dražších než optimum +10%, maximálně nepodobných té nalezené. "
        "Argument pro vyjednávání a pojistka proti «co když baterie "
        "zdraží?»",
    "каждая группа столбцов — один дизайн: первый — "
    "оптимум, остальные — варианты в пределах потолка "
    "издержек. Если вариант почти без батареи стоит на "
    "7% дороже — это цена независимости от поставок "
    "аккумуляторов.":
        "každá skupina sloupců je jeden návrh: první je optimum, ostatní "
        "jsou varianty v mezích stropu nákladů. Stojí-li varianta téměř "
        "bez baterie o 7% víc — to je cena nezávislosti na dodávkách "
        "akumulátorů.",

    # ---------- вкладка «Валидация» ----------
    "Сверка с внешним инструментом (REopt web / HOMER). Прогони тот же "
    "сценарий там, впиши их числа — отклонения **> 10%** будут "
    "помечены. Публичного API у HOMER нет, у REopt нужен ключ NREL — "
    "поэтому сверка идёт по введённым вручную числам, честно и "
    "прозрачно.":
        "Porovnání s externím nástrojem (REopt web / HOMER). Spusť tam "
        "stejný scénář, zapiš jejich čísla — odchylky **> 10%** budou "
        "označeny. HOMER nemá veřejné API, REopt vyžaduje klíč NREL — "
        "proto porovnání probíhá podle ručně zadaných čísel, poctivě a "
        "transparentně.",

    # ---------- подсказки ползунков (help) ----------
    "Дневная нагрузка, kW": "Denní zatížení, kW",
    "Ночная база, kW": "Noční základ, kW",
    "Мощность (kW) в рабочие часы смены 08–18; kW — СКОРОСТЬ "
    "потребления, энергия за час = kW × 1 ч. Для синтетики.":
        "Výkon (kW) v pracovních hodinách směny 08–18; kW je RYCHLOST "
        "spotřeby, energie za hodinu = kW × 1 h. Pro syntetický profil.",
    "Дежурная мощность вне смены: охрана, холодильники, серверная.":
        "Pohotovostní výkon mimo směnu: ostraha, chlazení, serverovna.",
    "Разовые капитальные затраты на 1 kWp панелей "
    "(купить + смонтировать).":
        "Jednorázové kapitálové náklady na 1 kWp panelů "
        "(nákup + montáž).",
    "Цена 1 kWh ёмкости накопителя (LFP-шкафы). kWh — сколько "
    "батарея ХРАНИТ; kW — как быстро отдаёт.":
        "Cena 1 kWh kapacity úložiště (LFP skříně). kWh je kolik baterie "
        "ULOŽÍ; kW je jak rychle vydá.",
    "Цена одного литра дизтоплива на площадке (с доставкой). "
    "Фундаментальный вход у REopt/HOMER; $/кВт*ч выводится из "
    "неё и удельного расхода. Tornado показывает: самый "
    "влиятельный параметр модели.":
        "Cena jednoho litru nafty na místě (včetně dopravy). Základní "
        "vstup v REopt/HOMER; $/kWh se z ní a z měrné spotřeby odvozuje. "
        "Analýza rizik ukazuje: nejvlivnější parametr modelu.",
    "Сколько литров сжигает генсет на 1 кВт*ч на номинале "
    "(datasheet). Типовой дизель ~0.27. Холостой ход "
    "учитывается в режиме точного расчёта парка (ниже).":
        "Kolik litrů spálí agregát na 1 kWh při jmenovitém zatížení "
        "(datasheet). Typický diesel ~0.27. Volnoběh se zohledňuje v "
        "režimu přesného výpočtu parku (níže).",
    "Насколько цена топлива растёт каждый год сверх инфляции. "
    "Плоская цена на 20 лет занижает будущие расходы дизеля и "
    "смещает оптимум к генсету. Учитывается одним "
    "левелизационным коэффициентом (как в REopt).":
        "O kolik cena paliva roste každý rok nad inflaci. Plochá cena na "
        "20 let podhodnocuje budoucí výdaje na diesel a posouvá optimum "
        "k agregátu. Zohledněno jedním levelizačním koeficientem (jako "
        "v REopt).",
    "Номинальный КПД DC→AC. Дефолт 0.96 (REopt/PVWatts); "
    "в datasheet вендора обычно 0.95–0.985.":
        "Jmenovitá účinnost DC→AC. Výchozí 0.96 (REopt/PVWatts); v "
        "datasheetu dodavatele obvykle 0.95–0.985.",
    "Потеря мощности на каждый °C нагрева ячейки выше 25 °C. "
    "Стандартный кремний −0.47; N-type TOPCon ~−0.30.":
        "Ztráta výkonu na každý °C ohřevu článku nad 25 °C. Standardní "
        "křemík −0.47; N-type TOPCon ~−0.30.",
    "Панелей ставят больше номинала инвертора: пики редки, "
    "инвертор дорог; излишек срезается (clipping).":
        "Panelů se instaluje více, než je jmenovitý výkon střídače: "
        "špičky jsou vzácné, střídač je drahý; přebytek se ořezává "
        "(clipping).",
    "Влияет на температуру ячейки: на раме панели охлаждаются "
    "лучше (+1–2% выработки). Кейс NIST показал значимость.":
        "Ovlivňuje teplotu článku: na rámu se panely chladí lépe "
        "(+1–2% výroby). Případ NIST ukázal, že na tom záleží.",
    "Спутниковый «типичный год» — это медиана (P50): в половине "
    "реальных лет солнца МЕНЬШЕ. Для критичных объектов отрасль "
    "рекомендует консервативный P90 — весь солнечный ряд "
    "умножается на 0.95.":
        "Satelitní «typický rok» je medián (P50): v polovině reálných "
        "let je slunce MÉNĚ. Pro kritické objekty obor doporučuje "
        "konzervativní P90 — celá solární řada se násobí 0.95.",
    "КПД полного цикла «зарядил-разрядил»: из 100 kWh при 0.85 "
    "обратно выйдет 85. В модели η заряда = η разряда = √RTE.":
        "Účinnost celého cyklu «nabít-vybít»: ze 100 kWh při 0.85 se "
        "vrátí 85. V modelu η nabíjení = η vybíjení = √RTE.",
    "Потолок сайзера: pv_kWp × 5 м²/kWp ≤ площадь.":
        "Strop dimenzování: pv_kWp × 5 m²/kWp ≤ plocha.",
    "Верхняя граница поиска для солнца (нижняя 0). Итоговый "
    "потолок — минимум из этого и площади.":
        "Horní mez hledání pro slunce (dolní je 0). Výsledný strop je "
        "minimum z této hodnoty a plochy.",
    "Верхняя граница поиска ёмкости накопителя.":
        "Horní mez hledání kapacity úložiště.",
    "Верхняя граница поиска дизеля. При политике hard она должна "
    "позволять покрыть пик — иначе честная ошибка «неразрешимо».":
        "Horní mez hledání dieselu. Při politice hard musí umožnit "
        "pokrýt špičku — jinak přijde poctivá chyba «neřešitelné».",
    "hard: каждый kWh спроса покрыт. lpsp: недопоставка не выше "
    "заданной доли. voll: модель сама решает, что дешевле — "
    "поставить или заплатить штраф за тьму.":
        "hard: každá kWh poptávky je pokryta. lpsp: nedodávka ne vyšší "
        "než zadaný podíl. voll: model sám rozhodne, co je levnější — "
        "dodat, nebo zaplatit pokutu za tmu.",
    "Допустимая доля годового спроса без поставки; "
    "1% ≈ 87 часов простоя в год.":
        "Přípustný podíl roční poptávky bez dodávky; "
        "1% ≈ 87 hodin výpadku za rok.",
    "Value of lost load — цена недопоставленного kWh для "
    "потребителя (простой производства). Дефолт REopt: $1.":
        "Value of lost load — cena nedodané kWh pro odběratele (prostoj "
        "výroby). Výchozí hodnota REopt: $1.",
    "Горячий запас мощности сверх нагрузки в КАЖДЫЙ час: "
    "недогруженный дизель + доступный разряд батареи. Страхует "
    "реальную работу от сюрпризов и закрывает разрыв между "
    "идеальным планом и реальностью. 0 = выключено.":
        "Horká rezerva výkonu nad zatížením v KAŽDÉ hodině: nedotížený "
        "diesel + dostupné vybití baterie. Pojišťuje reálný provoz proti "
        "překvapením a uzavírá mezeru mezi ideálním plánem a realitou. "
        "0 = vypnuto.",
    "Дополнительный резерв, привязанный к выработке солнца: "
    "облако роняет PV — запас страхует. Панель сама резерв не "
    "даёт (она и есть источник неопределённости).":
        "Dodatečná rezerva vázaná na výrobu ze slunce: mrak srazí PV — "
        "rezerva to pojistí. Panel sám rezervu nedává (je právě zdrojem "
        "nejistoty).",
    "Стратегия HOMER Cycle Charging: раз генсет уже работает, "
    "его свободная мощность заряжает батарею — позже реже "
    "включаться. Включай при многодневной пасмурности или "
    "генсете меньше пика. Проверка надёжности тоже использует "
    "эту стратегию.":
        "Strategie HOMER Cycle Charging: když už agregát běží, jeho "
        "volný výkon nabíjí baterii — aby se později spouštěl méně "
        "často. Zapni při vícedenní oblačnosti nebo když je agregát "
        "menší než špička. Kontrola spolehlivosti používá stejnou "
        "strategii.",
    "Запас батареи в конце года «перетекает» в его начало "
    "(паттерн Calliope) — без бесплатной стартовой заправки. "
    "Выключи для сравнения с REopt-стилем (старт с полной).":
        "Zásoba baterie na konci roku «přetéká» na jeho začátek (vzor "
        "Calliope) — bez darované startovní náplně. Vypni pro srovnání "
        "se stylem REopt (start s plnou).",
    "Размеры кратны юниту (целые панели/шкафы/генсеты), а "
    "дизельный парк включается по часам — «сколько генсетов "
    "работает сейчас» — с минимальной загрузкой и холостым "
    "ходом. Честнее физика, но расчёт заметно дольше.":
        "Velikosti jsou násobky jednotky (celé panely/skříně/agregáty) a "
        "dieselový park se spíná po hodinách — «kolik agregátů teď běží» "
        "— s minimálním zatížením a volnoběhem. Poctivější fyzika, ale "
        "výpočet je znatelně delší.",
    "Включённый генсет не опускается ниже этой доли номинала "
    "(типично 15–30% у автономных систем). Работает только в "
    "точном расчёте парка.":
        "Zapnutý agregát neklesne pod tento podíl jmenovitého výkonu "
        "(typicky 15–30% u ostrovních systémů). Funguje jen v přesném "
        "výpočtu parku.",
    "Постоянный расход топлива работающего генсета сверх "
    "нагрузки. Стоит денег даже вхолостую — модель гасит "
    "лишние генсеты. 0 = не моделировать. Работает только в "
    "точном расчёте парка.":
        "Stálá spotřeba paliva běžícího agregátu nad rámec zatížení. "
        "Stojí peníze i na volnoběh — model zbytečné agregáty vypíná. "
        "0 = nemodelovat. Funguje jen v přesném výpočtu parku.",
    "Больше нуля при политике hard — реальная работа без "
    "предвидения иногда не дотягивает на размерах, ужатых "
    "оптимизацией. Лечится оперативным резервом (ползунок "
    "в сайдбаре).":
        "Nad nulou při politice hard — reálný provoz bez předvídavosti "
        "občas nedosáhne na velikosti stlačené optimalizací. Léčí se "
        "provozní rezervou (posuvník v postranním panelu).",
    "Самодостаточная страница: метрики, "
    "спецификация, издержки и графики — можно "
    "отправить письмом.":
        "Soběstačná stránka: metriky, specifikace, náklady a grafy — "
        "lze poslat e-mailem.",

    # ---------- шапка и спецификация ----------
    "*Оценка: {} кг CO₂ на kWh дизеля · недопоставка (LPSP) = {} · "
    "сброс излишков солнца = {} kWh":
        "*Odhad: {} kg CO₂ na kWh dieselu · nedodávka (LPSP) = {} · "
        "ořez solárních přebytků = {} kWh",
    "Компонент": "Komponenta",
    "Что заказать": "Co objednat",
    "Кол-во, шт": "Počet, ks",
    "Номинал юнита": "Jmenovitá hodnota jednotky",
    "Установлено": "Instalováno",
    "Цена/юнит, $": "Cena/jednotka, $",
    "CAPEX, $": "CAPEX, $",
    "O&M, $/год": "O&M, $/rok",
    "Производство, kWh/год": "Výroba, kWh/rok",
    "ИТОГО": "CELKEM",
    "Что означает каждая колонка": "Co znamená každý sloupec",
    "текущее решение (эта форма)": "současné řešení (tento formulář)",
    "база (зафиксирована кнопкой)": "základ (uložen tlačítkem)",
    "Размеры: текущее решение против базы":
        "Velikosti: současné řešení proti základu",
    "Кто поставил энергию заводу за год":
        "Kdo dodal energii závodu za rok",
    "Потоки энергии за год": "Toky energie za rok",
    "шина 400 В": "sběrnice 400 V",
    "Завод (нагрузка)": "Závod (zatížení)",

    # ---------- графики: подписи и легенды ----------
    "Недельный график доступен для годового часового профиля.":
        "Týdenní graf je dostupný pro roční hodinový profil.",
    "спрос завода, kW": "poptávka závodu, kW",
    "Нагрузка: первые двое суток": "Zatížení: první dva dny",
    "час": "hodina",
    "15 июня (облачный сезон)": "15. června (oblačná sezóna)",
    "Солнце: типовые сутки, kW на 1 kWp":
        "Slunce: typické dny, kW na 1 kWp",
    "час местного времени": "hodina místního času",
    "Выработка по месяцам": "Výroba po měsících",
    "месяц": "měsíc",
    "нет": "není",
    "топливо дизеля": "palivo dieselu",
    "только дизель": "jen diesel",
    "Цена киловатт-часа: проект против «только дизель»":
        "Cena kilowatthodiny: projekt proti «jen diesel»",
    "всё из дизеля (только топливо)": "vše z dieselu (jen palivo)",
    "гибрид (закупка + эксплуатация)": "hybrid (nákup + provoz)",
    "Накопленные затраты по годам проекта":
        "Kumulované náklady po letech projektu",
    "год проекта": "rok projektu",
    "CAPEX": "CAPEX",
    "Водопад окупаемости: вложение и возврат по годам":
        "Vodopád návratnosti: investice a návrat po letech",
    "идеальный план (видит год наперёд)":
        "ideální plán (vidí rok dopředu)",
    "реальная работа (без предвидения)":
        "reálný provoz (bez předvídavosti)",
    "Годовые потоки: идеальный план против реальной работы":
        "Roční toky: ideální plán proti reálnému provozu",
    "kWh за год": "kWh za rok",
    "Доля часов года, из которых система переживает отказ":
        "Podíl hodin roku, ze kterých systém přežije výpadek",
    "Запустить анализ рисков": "Spustit analýzu rizik",
    "Стрессы оптимального дизайна": "Zátěžové testy optimálního návrhu",
    "мой вариант": "moje varianta",
    "имя сценария": "název scénáře",
    "Сравнение сценариев": "Srovnání scénářů",
    "← текущий": "← současný",
    "Найти альтернативы (+10% к издержкам)":
        "Najít alternativy (+10% k nákladům)",
    "PV референса, kWp": "PV reference, kWp",
    "BESS референса, kWh": "BESS reference, kWh",
    "DG референса, kW": "DG reference, kW",
    "LCOE референса": "LCOE reference",
    "Введи числа референса — появится таблица отклонений.":
        "Zadej referenční čísla — objeví se tabulka odchylek.",
    "Что здесь происходит и зачем.": "Co se tu děje a proč.",
    "Как читать:": "Jak to číst:",
    "Синтетический (Йемен)": "Syntetický (Jemen)",
    "CSV-файл": "CSV soubor",
    "→ эффективно ${}/кВт*ч дизеля": "→ efektivně ${}/kWh dieselu",
    "Парк генераторов: {} шт по {:g} kW · одновременно в работе "
    "до {}, в среднем {} (точный расчёт целыми машинами)":
        "Park agregátů: {} ks po {:g} kW · současně v provozu až {}, "
        "v průměru {} (přesný výpočet celými stroji)",
    "нагрузка завода (спрос)": "zatížení závodu (poptávka)",
    "Типовые сутки: кто кормит завод в среднем за год":
        "Typický den: kdo živí závod v průměru za rok",
    "час суток": "hodina dne",
    "Неделя 16–22 февраля: кто кормит завод":
        "Týden 16.–22. února: kdo živí závod",
    "часы недели": "hodiny týdne",
    "запас батареи (SOC), kWh": "zásoba baterie (SOC), kWh",
    "пол SOC (20% — бережём ресурс)":
        "spodní mez SOC (20% — šetříme životnost)",
    "ёмкость (потолок)": "kapacita (strop)",
    "Запас батареи (SOC) в ту же неделю":
        "Zásoba baterie (SOC) ve stejném týdnu",
    "Кто кормит завод по месяцам": "Kdo živí závod po měsících",
    "выработка за месяц, kWh/kWp": "výroba za měsíc, kWh/kWp",
    "проект PV+BESS+DG": "projekt PV+BESS+DG",
    "Сверка: сумма статей совпадает с итогом оптимизации (${}) "
    "— две независимые дороги к одному числу.":
        "Kontrola: součet položek se shoduje s výsledkem optimalizace "
        "(${}) — dvě nezávislé cesty k jednomu číslu.",
    "Медиана выживания на солнце и батарее: {} ч · отказ "
    "стартует в каждый 3-й час года, запас батареи — из "
    "реальной траектории":
        "Medián přežití na slunci a baterii: {} h · výpadek startuje "
        "v každé 3. hodině roku, zásoba baterie z reálné trajektorie",
    "Что сильнее всего влияет на бюджет": "Co nejvíce hýbe rozpočtem",
    "граница возможного (дешевле при такой надёжности не бывает)":
        "hranice možného (levněji to při této spolehlivosti nejde)",
    "колено — разумный компромисс": "koleno — rozumný kompromis",
    "Сколько стоит надёжность": "Kolik stojí spolehlivost",
    "допустимая недопоставка (LPSP), %": "přípustná nedodávka (LPSP), %",
    "Размеры оборудования по сценариям":
        "Velikosti zařízení podle scénářů",
    "LCOE по сценариям": "LCOE podle scénářů",
    "оптимум": "optimum",
    "Оптимум и альтернативы не дороже +10%":
        "Optimum a alternativy ne dražší než +10%",
    "close_mount (вплотную к крыше)": "close_mount (těsně u střechy)",
    "open_rack (на раме / земле)": "open_rack (na rámu / zemi)",
    "P50 — типичный год": "P50 — typický rok",
    "P90 — запас на слабый год (−5%)": "P90 — rezerva na slabý rok (−5%)",
    "Оптимизация не удалась: {}": "Optimalizace se nezdařila: {}",
    "Проблема с входными данными: {}": "Problém se vstupními daty: {}",
    "панелей": "panelů",
    "шкафов": "skříní",
    "генсет": "agregát",
    "лучший день года ({})": "nejlepší den roku ({})",
    "{} лет": "{} let",
    "Годовые издержки ${} — из чего складываются":
        "Roční náklady ${} — z čeho se skládají",
    "окупаемость": "návratnost",
    "длительность отказа дизеля, часов":
        "délka výpadku dieselu, hodin",
    "параметр дешевле базового → издержки падают до этой точки":
        "parametr levnější než základ → náklady klesnou do tohoto bodu",
    "параметр дороже базового → издержки растут до этой точки":
        "parametr dražší než základ → náklady vzrostou do tohoto bodu",
    "Загружен {}": "Načteno {}",
    "сценарий": "scénář",
    "изд., $/год": "nákl., $/rok",
    "LCOE, $": "LCOE, $",
    "renewable": "obnovitelné",
    "CO₂, т": "CO₂, t",
    "метрика": "metrika",
    "референс": "reference",
    "отклонение": "odchylka",
    "вердикт": "verdikt",
    "hard — недопоставка запрещена": "hard — nedodávka zakázána",
    "lpsp — допустимая доля недопоставки":
        "lpsp — přípustný podíl nedodávky",
    "voll — недопоставка платная": "voll — nedodávka je zpoplatněna",
    "вариант {}": "varianta {}",
    "разобраться!": "prověřit!",
    "ок": "ok",
    "окупился: год {}": "návratnost: rok {}",
    "Солнце": "Slunce",
    "Дизель-генератор": "Dieselagregát",
    "Батарея": "Baterie",
    "Сброс излишков": "Ořez přebytků",
    "Потери цикла": "Ztráty cyklu",

    # ---------- КОСВЕННЫЕ переводы ----------
    # Эти строки лежат литералами в кортежах/словарях (легенды графиков,
    # статьи затрат, названия компонентов спецификации), а в T() приходит
    # уже переменная. AST-разбор вызовов их не видит — их полноту
    # стережёт тест по отрисованному интерфейсу (кириллицы быть не должно).
    "Язык / Language": "Язык / Language",   # намеренно на всех языках

    # легенды стековых графиков (типовые сутки / неделя / месяцы)
    "солнце → завод (напрямую)": "slunce → závod (přímo)",
    "батарея → завод (разряд запаса)": "baterie → závod (vybíjení zásoby)",
    "дизель → завод (резерв)": "diesel → závod (záloha)",

    # секторы энергобаланса года (пирог и Sankey)
    "Солнце напрямую": "Slunce přímo",
    "Солнце через батарею": "Slunce přes baterii",

    # статьи годовых издержек
    "капитал PV": "kapitál PV",
    "капитал BESS": "kapitál BESS",
    "капитал DG": "kapitál DG",
    "O&M": "O&M",
    "топливо": "palivo",

    # компоненты спецификации закупки
    "Солнечные панели (PV)": "Solární panely (PV)",
    "PV-панель": "PV panel",
    "Накопитель — ёмкость (BESS)": "Úložiště — kapacita (BESS)",
    "Батарейный шкаф": "Bateriová skříň",
    "Накопитель — мощность (PCS)": "Úložiště — výkon (PCS)",
    "Инвертор PCS": "Střídač PCS",
    "Дизель-генератор (DG)": "Dieselagregát (DG)",

    # потоки на графике «идеальный план против реальной работы»
    "дизель": "diesel",
    "разряд батареи": "vybíjení baterie",
    "сброс солнца": "ořez slunce",
    "недопоставка": "nedodávka",

    # строки анализа рисков (tornado)
    "Цена дизеля ±50%": "Cena nafty ±50%",
    "CAPEX BESS ±30%": "CAPEX BESS ±30%",
    "CAPEX PV ±30%": "CAPEX PV ±30%",
}


GLOSSARY_CS = """
- **kW / kWh / kWp** — výkon (rychlost) / energie (množství = výkon ×
  čas) / štítkový výkon panelů při ideálním slunci.
- **CAPEX / O&M** — jednorázové kapitálové náklady / roční provoz a
  údržba.
- **CRF** — capital recovery factor `r(1+r)ⁿ/((1+r)ⁿ−1)`: rozprostře
  CAPEX do stejných ročních plateb (jako anuita hypotéky) — jen tak jsou
  panely srovnatelné s naftou.
- **NPC** — net present cost: všechny náklady horizontu v dnešních
  penězích.
- **LCOE** — levelized cost of energy: roční náklady ÷ dodané kWh; cena
  kilowatthodiny «na klíč».
- **LPSP** — podíl nedodané energie za rok (0% = vše dodáno;
  1% ≈ 87 hodin výpadku).
- **Renewable fraction** — podíl dodávky, který NEPOCHÁZÍ z dieselu.
- **SOC** — state of charge: aktuální zásoba baterie, kWh; pod «spodní
  mez» (20%) nevybíjíme — šetříme životnost.
- **RTE** — účinnost cyklu baterie (viz nápověda u posuvníku).
- **Curtailment** — ořez přebytečné solární výroby (baterie plná,
  zatížení pokryto) — normální cena levných panelů.
- **Shortfall** — nedodávka: poptávka, kterou nikdo nepokryl.
- **VOLL** — value of lost load: cena nedodané kWh pro odběratele.
- **Clipping** — ořez DC špiček střídačem s nižším jmenovitým výkonem
  (DC/AC).
- **Perfect foresight** — model «zná» celý rok dopředu; reálný regulátor
  ne — mezeru měříme na záložce «Kontrola spolehlivosti».
- **Paretova hranice / koleno** — křivka «náklady ↔ spolehlivost» a bod,
  za kterým ústupky téměř nešetří.
- **Tornado** — čí cenová prognóza nejvíce rozkývá výsledek.
"""


COLUMNS_HELP_CS = """
- **Komponenta** — podsystém mikrosítě: solární panely, kapacita
  baterie, výkon baterie (střídače PCS) a dieselagregát.
- **Co objednat** — konkrétní fyzické zboží, které se nakupuje po kusech
  (panel, bateriová skříň, střídač PCS, agregát).
- **Počet, ks** — kolik CELÝCH jednotek koupit: zaokrouhlení nahoru
  (optimum ÷ jmenovitá hodnota jednotky). Zlomkový výkon objednat nelze.
- **Jmenovitá hodnota jednotky** — výkon nebo kapacita JEDNÉ jednotky
  (panel 0.58 kWp, skříň 261 kWh, PCS 125 kW, agregát 1000 kW).
- **Instalováno** — počet × jmenovitá hodnota: skutečně zakoupený
  výkon/kapacita. Mírně nad spojitým optimem — to je rezerva
  zaokrouhlení nahoru.
- **Cena/jednotka, $** — cena jedné jednotky (jmenovitá hodnota × cena
  za kW nebo kWh ze scénáře).
- **CAPEX, $** — jednorázové kapitálové náklady řádku: počet × cena
  jednotky. Řádek CELKEM je souhrnný nákup.
- **O&M, $/rok** — roční údržba tohoto zařízení. Palivo dieselu sem
  NEPATŘÍ — je na záložce «Ekonomika».
- **Výroba, kWh/rok** — roční energie: u PV výroba panelů (část přímo do
  závodu, část do baterie, něco málo do ořezu); u kapacity BESS kolik
  baterie za rok vydala (vybití); u výkonu PCS pomlčka (je to měnič, sám
  energii nevyrábí); u DG výroba dieselu.
"""

