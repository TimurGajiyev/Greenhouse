"""Симулятор GreenHouse: rule-based dispatch. Версия v0.4 (шаг 5).

Что делает модуль: прогоняет год по шагам времени при ЗАДАННЫХ размерах
оборудования и сводит энергобаланс каждого шага. Отвечает на вопрос
"выдержит ли ЭТА конфигурация нагрузку и как именно" — режим проверки
вендорского предложения.

Правило приоритета (dispatch — "диспетчеризация", кто когда работает):
    1. PV кормит нагрузку напрямую;
    2. избыток PV заряжает батарею (в пределах мощности PCS и ёмкости);
    3. остаток избытка — curtailment (сброс: энергия есть, девать некуда);
    4. дефицит покрывает разряд батареи (не ниже soc_min);
    5. остаток дефицита — дизель (в пределах его мощности);
    6. что не покрыл никто — shortfall (недопоставка потребителю).

Это жёсткое правило, а не оптимизация: шаг 7 заменит его LP-солвером
и покажет, сколько денег оставляет на столе простая логика.

Уравнения — из REopt.jl (наш "оракул"):
  - баланс шага (load_balance.jl, 8b off-grid):
        pv_gen + discharge + dg + shortfall == load + charge + curtail
    В REopt сетевой вариант (8a) отличается ровно двумя слагаемыми
    (покупка из сети в приход, заряд от сети в расход) — поэтому баланс
    здесь собран как СУММА ПОТОКОВ: будущий грид-проект (Чехия,
    15-минутные данные) добавит поток, а не перепишет симулятор.
  - SOC-динамика (storage_constraints.jl, 4g):
        soc[t] = soc[t-1] + Δt * (η_ch * charge - discharge / η_dis)
  - КПД (electric_storage.jl): η_ch = η_dis = sqrt(RTE) — потери
    полного цикла делятся поровну между зарядом и разрядом.
  - стартовый заряд (electric_storage.jl): off-grid системы REopt
    начинают год с ПОЛНОЙ батареей (soc_init_fraction = 1.0).

Δt берётся ТОЛЬКО из timestep_hours(ряда нагрузки): час, 15 минут,
сутки — один и тот же код. Солнце (всегда часовое из TMY) приводится
к сетке нагрузки помощником _align_solar_to_load.

Выход: typed-записи (frozen dataclass) -> pandas.DataFrame -> Parquet
в results/ + manifest (JSON: run_id, git commit, hash входов, итоги).
"""

import hashlib
import json
import math
import subprocess
import uuid
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from src.profiles import build_load_profile, timestep_hours
from src.schema import Scenario
from src.solar import build_solar_profile

# Имя модели диспетчеризации — пишется в каждую запись и в manifest,
# чтобы при сравнении с LP-оптимизатором (шаг 7) не спутать источники.
SOURCE_MODEL = "rule_v1"

# Допуск проверки энергобаланса, kW: числа с плавающей точкой не дают
# точного нуля, но грубее 1e-6 — уже не ошибка округления, а баг.
BALANCE_TOL_KW = 1e-6

# ASSUMPTION: стартовый заряд батареи = 100% ёмкости — так делает REopt
# для off-grid (soc_init_fraction = 1.0 при off_grid_flag, см.
# reference/REopt.jl-master/src/core/energy_storage/electric_storage.jl);
# логика: автономную систему не запускают с пустым складом энергии.
SOC_INIT_FRACTION = 1.0


@dataclass(frozen=True)
class TimestepRecord:
    """Один шаг симуляции: все потоки в kW, запас энергии в kWh.

    frozen=True делает экземпляр неизменяемым (immutable): записанный
    результат нельзя случайно испортить позже — как строку в журнале.
    """

    run_id: str
    timestamp: pd.Timestamp
    load_kw: float          # нагрузка потребителя
    pv_gen_kw: float        # вся выработка PV
    pv_to_load_kw: float    # PV -> нагрузка напрямую
    charge_kw: float        # PV -> батарея (на AC-стороне, до КПД)
    discharge_kw: float     # батарея -> нагрузка (на AC-стороне)
    dg_kw: float            # дизель -> нагрузка
    curtail_kw: float       # сброшенный избыток PV
    shortfall_kw: float     # недопоставленная мощность
    soc_kwh: float          # запас в батарее НА КОНЕЦ шага
    source_model: str = SOURCE_MODEL


@dataclass(frozen=True)
class SimulationResult:
    """Итог прогона: таблица шагов + manifest + пути файлов (если писали)."""

    table: pd.DataFrame = field(repr=False)  # repr=False: не печатать 8760 строк
    manifest: dict
    parquet_path: Path | None
    manifest_path: Path | None


def run_simulation(
    scenario: Scenario,
    weather_csv: str | None = None,
    results_dir: str = "results",
    write_outputs: bool = True,
    dg_outage: tuple[str, str] | None = None,
    strategy: str = "load_following",
) -> SimulationResult:
    """Прогоняет сценарий через rule-based диспетчер за весь горизонт.

    weather_csv — кэшированная погода (None = интернет с fallback);
    results_dir — куда писать Parquet и manifest;
    write_outputs=False — только вернуть результат без файлов (тесты);
    dg_outage — стресс "топливный разрыв" (шаг 9): пара дат
        ("2026-07-10", "2026-07-16"), между которыми ВКЛЮЧИТЕЛЬНО
        дизель недоступен (мощность 0) — например, кончилось топливо;
    strategy — стратегия диспетчеризации (как в HOMER):
        "load_following" (дефолт) — генсет выдаёт ровно дефицит;
        "cycle_charging" — раз генсет уже работает, свободная мощность
        заряжает батарею (аудит №2, изъян №2): позже реже включаться.
    """
    if strategy not in ("load_following", "cycle_charging"):
        raise ValueError(
            f"Неизвестная стратегия {strategy!r}: жду 'load_following' "
            "или 'cycle_charging'"
        )
    # 1) Ряды: нагрузка задаёт сетку времени (Δt и горизонт), солнце
    #    приводится к ней. Без PV солнечный ряд — честные нули, и
    #    погода не нужна вовсе (дизель-онли работает оффлайн).
    load, dt_hours, solar_unit = prepare_series(scenario, weather_csv)

    # 2) Размеры из сценария. В режиме проверки вендора min == max;
    #    берём max_kw как установленный размер. None-технология = 0.
    pv_kwp = scenario.pv.max_kw if scenario.pv else 0.0
    batt_kwh = scenario.battery.max_kwh if scenario.battery else 0.0
    batt_kw = scenario.battery.max_kw if scenario.battery else 0.0
    dg_kw = scenario.diesel.max_kw if scenario.diesel else 0.0

    # 3) Параметры батареи. sqrt распределяет потери цикла поровну:
    #    η_ch * η_dis == RTE (приём REopt). Саморазряд — множитель
    #    (1-loss)^Δt к запасу на каждом шаге (паттерн Calliope).
    if scenario.battery is not None:
        eta = math.sqrt(scenario.battery.rte_fraction)
        soc_min_kwh = scenario.battery.soc_min_fraction * batt_kwh
        loss = scenario.battery.self_discharge_fraction_per_hour or 0.0
        decay = (1.0 - loss) ** dt_hours
    else:
        eta = 1.0  # значение не участвует в расчёте: потоки будут 0
        soc_min_kwh = 0.0
        decay = 1.0

    # Доступная мощность дизеля по шагам: постоянная, кроме окна
    # отказа (стресс-сценарий) — там честный ноль.
    dg_cap = pd.Series(dg_kw, index=load.index)
    if dg_outage is not None:
        dg_cap.loc[dg_outage[0]:dg_outage[1]] = 0.0

    run_id = uuid.uuid4().hex[:12]
    records = _dispatch_loop(
        run_id=run_id,
        load=load,
        solar_unit=solar_unit,
        dt_hours=dt_hours,
        pv_kwp=pv_kwp,
        batt_kwh=batt_kwh,
        batt_kw=batt_kw,
        soc_min_kwh=soc_min_kwh,
        eta=eta,
        decay=decay,
        dg_cap=dg_cap,
        strategy=strategy,
    )

    # 4) Список записей -> таблица с осью времени.
    table = pd.DataFrame([asdict(r) for r in records]).set_index("timestamp")

    manifest = _build_manifest(
        run_id, scenario, load, solar_unit, dt_hours, table,
        extra={"stress_dg_outage": list(dg_outage)} if dg_outage else None,
    )

    # 5) Файлы результатов (Parquet — колоночный бинарный формат:
    #    компактнее и быстрее CSV, читается pandas.read_parquet).
    parquet_path = manifest_path = None
    if write_outputs:
        parquet_path, manifest_path = write_results(table, manifest, results_dir)

    return SimulationResult(
        table=table,
        manifest=manifest,
        parquet_path=parquet_path,
        manifest_path=manifest_path,
    )


# ---------- помощники, разделяемые с оптимизатором (шаг 7) ----------


def prepare_series(
    scenario: Scenario, weather_csv: str | None
) -> tuple[pd.Series, float, pd.Series]:
    """Готовит входные ряды движка: (нагрузка, Δt, удельное солнце).

    Общий вход rule-симулятора и LP-оптимизатора: оба движка обязаны
    считать ОДНУ и ту же задачу (инвариант 9 — движок за интерфейсом).
    """
    load = build_load_profile(scenario)
    dt_hours = timestep_hours(load)

    if scenario.pv is not None:
        solar_unit = _align_solar_to_load(
            build_solar_profile(scenario, weather_csv=weather_csv), load
        )
    else:
        solar_unit = pd.Series(0.0, index=load.index, name="solar_kw_per_kwp")
    return load, dt_hours, solar_unit


def write_results(
    table: pd.DataFrame, manifest: dict, results_dir: str
) -> tuple[Path, Path]:
    """Пишет Parquet-таблицу и manifest рядом, возвращает пути."""
    out = Path(results_dir)
    out.mkdir(parents=True, exist_ok=True)
    run_id = manifest["run_id"]
    parquet_path = out / f"run_{run_id}.parquet"
    manifest_path = out / f"run_{run_id}_manifest.json"
    table.to_parquet(parquet_path)
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return parquet_path, manifest_path


# ---------- приватные помощники ----------


def _align_solar_to_load(solar: pd.Series, load: pd.Series) -> pd.Series:
    """Приводит часовой солнечный ряд к сетке времени нагрузки.

    Три случая (dt_l = шаг нагрузки, dt_s = шаг солнца, всегда 1 ч):
      dt_l == dt_s — ряды уже совпадают (проверяем индексы);
      dt_l <  dt_s — нагрузка мельче (15/30 минут): каждое часовое
          значение kW повторяется на под-шаги (ffill). Тот же приём,
          что repeat(..., inner=N) в REopt: мощность константна внутри
          часа, энергия сохраняется автоматически;
      dt_l >  dt_s — нагрузка крупнее (сутки): среднее kW за окно —
          среднее сохраняет энергию (mean(kW) * 24h == sum(kWh)).
    """
    dt_l = timestep_hours(load)
    dt_s = timestep_hours(solar)

    if dt_l == dt_s:
        aligned = solar if solar.index.equals(load.index) else solar.reindex(load.index)
    elif dt_l < dt_s:
        # Кратность: 60-минутный час делится на шаги 30/15/... без остатка.
        if (dt_s / dt_l) != int(dt_s / dt_l):
            raise ValueError(
                f"Шаг нагрузки {dt_l} ч не делит час солнечного ряда нацело"
            )
        aligned = solar.reindex(load.index, method="ffill")
    else:
        if (dt_l / dt_s) != int(dt_l / dt_s):
            raise ValueError(
                f"Шаг нагрузки {dt_l} ч не кратен часу солнечного ряда"
            )
        # resample: режем часовой ряд на окна по dt_l часов и усредняем.
        aligned = solar.resample(f"{int(dt_l)}h").mean().reindex(load.index)

    if aligned.isna().any():
        raise ValueError(
            "Солнечный ряд не покрывает ось нагрузки: проверь, что даты "
            f"load-CSV лежат внутри опорного года {solar.index[0].year} "
            "(TMY строится именно на нём)"
        )
    return aligned.rename("solar_kw_per_kwp")


def _dispatch_loop(
    run_id: str,
    load: pd.Series,
    solar_unit: pd.Series,
    dt_hours: float,
    pv_kwp: float,
    batt_kwh: float,
    batt_kw: float,
    soc_min_kwh: float,
    eta: float,
    decay: float,
    dg_cap: pd.Series,
    strategy: str = "load_following",
) -> list[TimestepRecord]:
    """Ядро симулятора: правило приоритета на каждом шаге времени.

    Все величины-потоки в kW (мощность НА ПРОТЯЖЕНИИ шага), запас в kWh.
    Перевод потока в энергию шага: kW * dt_hours.
    """
    soc = SOC_INIT_FRACTION * batt_kwh  # старт с полной батареей (см. выше)
    records: list[TimestepRecord] = []

    for ts, load_kw in load.items():
        # Саморазряд: запас "усыхает" за шаг ещё ДО потоков; дальше
        # все лимиты считаются от усохшего значения. При decay=1
        # (дефолт) строка ничего не меняет.
        soc = soc * decay

        pv_gen = pv_kwp * solar_unit[ts]

        # 1. PV -> нагрузка напрямую (бесплатно и без потерь).
        pv_to_load = min(pv_gen, load_kw)
        surplus = pv_gen - pv_to_load          # лишнее солнце
        deficit = load_kw - pv_to_load         # непокрытая нагрузка

        # 2. Избыток -> заряд. Три потолка: сам избыток, мощность PCS,
        #    свободное место в ёмкости. Место в kWh переводим в kW
        #    заряда: влезет (batt_kwh - soc) kWh, с учётом КПД на входе
        #    заряд мощностью x за шаг добавит x * η * dt kWh.
        headroom_kw = (
            (batt_kwh - soc) / (eta * dt_hours) if batt_kwh > 0 else 0.0
        )
        charge = min(surplus, batt_kw, headroom_kw)
        charge = max(charge, 0.0)  # защита от -1e-17 плавающей точки

        # 3. Что не влезло — сброс (curtailment).
        curtail = surplus - charge

        # 4. Дефицит -> разряд. Потолки: дефицит, PCS, доступная энергия
        #    над полом soc_min (разряд x отнимает x / η * dt kWh).
        available_kw = (
            (soc - soc_min_kwh) * eta / dt_hours if batt_kwh > 0 else 0.0
        )
        discharge = min(deficit, batt_kw, available_kw)
        discharge = max(discharge, 0.0)
        deficit -= discharge

        # 5. Остаток дефицита -> дизель в пределах ДОСТУПНОЙ мощности
        #    этого шага (в окне "топливного разрыва" она нулевая).
        dg = min(deficit, dg_cap[ts])

        # 6. Всё, что осталось, — недопоставка.
        shortfall = deficit - dg

        # 5б. Cycle charging (опция, HOMER CC; аудит №2 изъян №2): раз
        #     генсет уже работает — его свободная мощность заряжает
        #     батарею, чтобы позже реже включаться. Заряд и разряд в один
        #     шаг не смешиваем; charge_pv — солнечная часть заряда для
        #     проверки русла PV ниже.
        charge_pv = charge
        if (strategy == "cycle_charging" and dg > 0 and discharge <= 0.0
                and batt_kwh > 0):
            charge_cc = max(0.0, min(dg_cap[ts] - dg, batt_kw - charge,
                                     headroom_kw - charge))
            dg += charge_cc
            charge += charge_cc

        # SOC-динамика REopt: заряд приходит с КПД, разряд забирает с КПД.
        soc = soc + dt_hours * (eta * charge - discharge / eta)

        # Ворота валидации (инвариант 6): приход == расход на КАЖДОМ шаге.
        inflow = pv_gen + discharge + dg + shortfall
        outflow = load_kw + charge + curtail
        assert abs(inflow - outflow) < BALANCE_TOL_KW, (
            f"{ts}: энергобаланс нарушен: приход {inflow} != расход {outflow}"
        )
        # И выработка PV разошлась без остатка по трём руслам (солнечная
        # часть заряда — charge_pv; дизельная добавка русло не искажает).
        assert abs(pv_gen - (pv_to_load + charge_pv + curtail)) < BALANCE_TOL_KW

        records.append(
            TimestepRecord(
                run_id=run_id,
                timestamp=ts,
                load_kw=float(load_kw),
                pv_gen_kw=float(pv_gen),
                pv_to_load_kw=float(pv_to_load),
                charge_kw=float(charge),
                discharge_kw=float(discharge),
                dg_kw=float(dg),
                curtail_kw=float(curtail),
                shortfall_kw=float(shortfall),
                soc_kwh=float(soc),
            )
        )

    return records


def _build_manifest(
    run_id: str,
    scenario: Scenario,
    load: pd.Series,
    solar_unit: pd.Series,
    dt_hours: float,
    table: pd.DataFrame,
    source_model: str = SOURCE_MODEL,
    solver_info: dict | None = None,
    extra: dict | None = None,
) -> dict:
    """Паспорт прогона: кто, из чего и с каким итогом посчитан.

    Зачем: результат без manifest невозможно воспроизвести или
    сравнить — не знаешь ни версии кода, ни входов. Поля — по
    инварианту 8 CLAUDE.md.
    """
    total_load_kwh = float(load.sum() * dt_hours)
    total_shortfall_kwh = float(table["shortfall_kw"].sum() * dt_hours)

    solver_info = solver_info or {}
    return {
        "run_id": run_id,
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_model": source_model,
        "git_commit": _git_commit(),
        "inputs_hash": _inputs_hash(scenario, load, solar_unit),
        "scenario_name": scenario.name,
        "timestep_hours": dt_hours,
        "n_steps": int(len(table)),
        # Солвера в rule-based режиме нет (поля = None); LP-оптимизатор
        # (шаг 7) передаёт solver_info и заполняет их значениями.
        "solver": solver_info.get("solver"),
        "solver_status": solver_info.get("solver_status"),
        "objective_value": solver_info.get("objective_value"),
        "solve_seconds": solver_info.get("solve_seconds"),
        "totals_kwh": {
            "load": total_load_kwh,
            "pv_gen": float(table["pv_gen_kw"].sum() * dt_hours),
            "discharge": float(table["discharge_kw"].sum() * dt_hours),
            "dg": float(table["dg_kw"].sum() * dt_hours),
            "curtail": float(table["curtail_kw"].sum() * dt_hours),
            "shortfall": total_shortfall_kwh,
        },
        # LPSP (loss of power supply probability) — доля недопоставленной
        # энергии; главная метрика надёжности (0 = всё покрыто).
        "lpsp": total_shortfall_kwh / total_load_kwh if total_load_kwh else None,
        # Доп. поля вызывающего (сайзер кладёт сюда размеры и штуки).
        **(extra or {}),
    }


def _git_commit() -> str:
    """Хэш текущего коммита — какой версией кода посчитано."""
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            cwd=Path(__file__).resolve().parents[1],
        ).stdout.strip()
    except Exception:
        return "unknown"  # git недоступен — честно признаёмся


def _inputs_hash(scenario: Scenario, load: pd.Series, solar_unit: pd.Series) -> str:
    """SHA-256 всех входов: сценарий + оба ряда.

    Одинаковый hash == одинаковая задача: два прогона с равным hash
    обязаны дать равный результат (ядро — чистая функция).
    """
    h = hashlib.sha256()
    h.update(scenario.model_dump_json().encode())
    for series in (load, solar_unit):
        h.update(np.ascontiguousarray(series.to_numpy(dtype=float)).tobytes())
        h.update(series.index.asi8.tobytes())  # отметки времени как int64
    return h.hexdigest()
