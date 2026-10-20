"""Seed the FNOL insurance demo (home + auto). Deterministic (fixed seeds); fictional data only.

Must stay in sync with demos/insurance/init.sh.
"""

from __future__ import annotations

import asyncio
import random
from datetime import date, datetime, timedelta
from typing import Any

import asyncpg  # type: ignore[import-untyped]
from faker import Faker

from artoo.config import settings

SEED = 42
random.seed(SEED)
fake = Faker("es_ES")
Faker.seed(SEED)

N_CUSTOMERS = 500
N_CLAIMS = 3000
MONTHS = 24

CITIES = [
    "Madrid",
    "Barcelona",
    "Valencia",
    "Sevilla",
    "Bilbao",
    "Zaragoza",
    "Málaga",
    "Palma",
    "Valladolid",
    "A Coruña",
]
TRADES = {
    "TOW": "Grúas",
    "PLB": "Fontanería",
    "ELC": "Electricidad",
    "LCK": "Cerrajería",
    "GLZ": "Cristalería",
}

# (code, name, line, base limit, assistance trade)
COVERAGES = [
    ("H-WTR", "Daños por agua", "HOME", 6000, "PLB"),
    ("H-ELC", "Daños eléctricos", "HOME", 3000, "ELC"),
    ("H-BRK", "Robo en vivienda", "HOME", 8000, "LCK"),
    ("H-GLS", "Rotura de cristales", "HOME", 1500, "GLZ"),
    ("H-LCK", "Asistencia cerrajería", "HOME", 400, "LCK"),
    ("H-FIR", "Incendio", "HOME", 60000, None),
    ("A-COL", "Colisión", "AUTO", 12000, "TOW"),
    ("A-BKD", "Asistencia en carretera", "AUTO", 600, "TOW"),
    ("A-GLA", "Lunas", "AUTO", 900, "GLZ"),
    ("A-THF", "Robo de vehículo", "AUTO", 15000, None),
]
# loss type -> (coverage code, line, description templates)
LOSS_TYPES: dict[str, tuple[str, str, list[str]]] = {
    "WTR": (
        "H-WTR",
        "HOME",
        [
            "Fuga en tubería del baño",
            "Rotura de lavadora, inundación en cocina",
            "Gotera desde el vecino de arriba",
        ],
    ),
    "ELC": (
        "H-ELC",
        "HOME",
        [
            "Sobretensión, se quemó el frigorífico",
            "Cortocircuito en el cuadro eléctrico",
            "Apagón y daños en electrodomésticos",
        ],
    ),
    "BRK": (
        "H-BRK",
        "HOME",
        [
            "Entrada por la ventana, faltan joyas",
            "Robo con fuerza en la puerta",
            "Intento de robo, cerradura forzada",
        ],
    ),
    "GLS": (
        "H-GLS",
        "HOME",
        ["Rotura de luna de ventana por granizo", "Cristal de puerta balconera roto"],
    ),
    "LCK": (
        "H-LCK",
        "HOME",
        ["Cliente fuera de casa, llaves dentro", "Llave rota en la cerradura"],
    ),
    "COL": (
        "A-COL",
        "AUTO",
        ["Colisión trasera en semáforo", "Golpe lateral en aparcamiento", "Choque en rotonda"],
    ),
    "BKD": (
        "A-BKD",
        "AUTO",
        ["Batería agotada, no arranca", "Pinchazo en autovía", "Avería de motor en carretera"],
    ),
    "GLA": ("A-GLA", "AUTO", ["Impacto de piedra en parabrisas", "Luna trasera rota"]),
}
# seasonal weight by month for each loss type (index 0 = Jan)
SEASON: dict[str, list[float]] = {
    "WTR": [3, 3, 2, 1.5, 1, 1, 1, 1, 1.5, 2, 3, 3],
    "ELC": [1.5, 1, 1, 1, 1.5, 2.5, 3, 3, 2, 1, 1, 1.5],
    "BRK": [1, 1, 1, 1, 1, 1.5, 2.5, 3, 1.5, 1, 1.5, 2],
    "GLS": [1, 1, 1.5, 2, 2, 1, 1, 1, 1, 1, 1, 1],
    "LCK": [1] * 12,
    "COL": [1.5, 1, 1, 1.2, 1.5, 2, 3, 3, 2, 1.5, 1.5, 2],
    "BKD": [2, 1.5, 1, 1, 1, 1.5, 2.5, 2.5, 1.5, 1, 1.5, 2],
    "GLA": [1] * 12,
}
LOSS_WEIGHT = {"WTR": 22, "ELC": 12, "BRK": 7, "GLS": 8, "LCK": 11, "COL": 17, "BKD": 20, "GLA": 3}
CHANNELS = [("APP", 45), ("TEL", 30), ("WEB", 17), ("AGT", 8)]
TRADE_COST = {
    "TOW": (90, 320),
    "PLB": (80, 600),
    "ELC": (70, 450),
    "LCK": (60, 250),
    "GLZ": (90, 700),
}
TRADE_RATE = {"TOW": (45, 70), "PLB": (38, 65), "ELC": (40, 70), "LCK": (45, 80), "GLZ": (42, 75)}


def _dsn() -> str:
    return str(settings.postgres_dsn).replace("+psycopg2", "")


def _wchoice(pairs: list[tuple[str, float]]) -> str:
    return random.choices([p[0] for p in pairs], weights=[p[1] for p in pairs])[0]


def _nif() -> str:
    num = random.randint(10_000_000, 99_999_999)
    return f"{num}{'TRWAGMYFPDXBNJZSQVHLCKE'[num % 23]}"


async def seed() -> None:
    conn = await asyncpg.connect(_dsn())
    for tbl in ["clm_evt", "clm_dsp", "clm", "pol_cvg", "pol", "ptnr", "cvg", "cust"]:
        await conn.execute(f"TRUNCATE TABLE {tbl} RESTART IDENTITY CASCADE;")

    today = datetime.now().replace(microsecond=0)
    start = today - timedelta(days=30 * MONTHS)

    # coverages
    await conn.executemany(
        "INSERT INTO cvg (cvg_code, cvg_name, line, lim_eur, trade) VALUES ($1,$2,$3,$4,$5)",
        COVERAGES,
    )
    cvg_id = {c[0]: i for i, c in enumerate(COVERAGES, start=1)}

    # customers (a few repeat claimants to feed the fraud cluster)
    customers: list[tuple[Any, ...]] = []
    for _ in range(N_CUSTOMERS):
        since = start.date() - timedelta(days=random.randint(0, 365 * 8))
        customers.append(
            (
                fake.first_name(),
                fake.last_name(),
                fake.email(),
                f"+34 6{random.randint(10_000_000, 99_999_999)}",
                _nif(),
                fake.date_of_birth(minimum_age=20, maximum_age=80),
                random.choice(CITIES),
                random.choices(["STD", "PRM", "VIP"], weights=[75, 20, 5])[0],
                since,
            )
        )
    await conn.executemany(
        "INSERT INTO cust (fname,lname,email,phone,nif,dob,city,seg,cust_since) "
        "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)",
        customers,
    )
    cust_city = {i: c[6] for i, c in enumerate(customers, start=1)}

    # policies: each customer has HOME and/or AUTO
    policies: list[tuple[Any, ...]] = []
    pol_line: dict[int, str] = {}
    pol_cust: dict[int, int] = {}
    pol_start: dict[int, date] = {}
    pol_end: dict[int, date | None] = {}
    pol_covers: dict[int, set[str]] = {}
    pol_cvg_rows: list[tuple[Any, ...]] = []
    pid = 0
    for cid in range(1, N_CUSTOMERS + 1):
        lines = random.choices([["HOME"], ["AUTO"], ["HOME", "AUTO"]], weights=[35, 25, 40])[0]
        for line in lines:
            pid += 1
            st = start.date() - timedelta(days=random.randint(0, 900))
            status = random.choices(["ACT", "LAP", "CAN"], weights=[88, 7, 5])[0]
            end = None if status == "ACT" else st + timedelta(days=random.randint(400, 1100))
            prem = round(
                random.uniform(180, 520) if line == "HOME" else random.uniform(320, 900), 2
            )
            ded = random.choice([0, 100, 150, 300, 500])
            policies.append((cid, f"POL-{line[0]}-{pid:06d}", line, status, st, end, prem, ded))
            pol_line[pid], pol_cust[pid], pol_start[pid], pol_end[pid] = line, cid, st, end
            codes = [c[0] for c in COVERAGES if c[2] == line]
            # not every policy carries every coverage (feeds "no coverage" rejections)
            mandatory = {"H-FIR"} if line == "HOME" else {"A-COL"}
            chosen = {c for c in codes if c in mandatory or random.random() < 0.72}
            pol_covers[pid] = chosen
            for code in sorted(chosen):
                base = next(c[3] for c in COVERAGES if c[0] == code)
                pol_cvg_rows.append(
                    (pid, cvg_id[code], round(base * random.choice([0.8, 1, 1.5, 2]), 2), ded)
                )
    await conn.executemany(
        "INSERT INTO pol (cust_id,pol_no,line,pol_stat,dt_start,dt_end,prem_eur,ded_eur) "
        "VALUES ($1,$2,$3,$4,$5,$6,$7,$8)",
        policies,
    )
    await conn.executemany(
        "INSERT INTO pol_cvg (pol_id,cvg_id,lim_eur,ded_eur) VALUES ($1,$2,$3,$4)", pol_cvg_rows
    )

    # partners: 8 per trade; some slow/expensive, a few inactive
    partners: list[tuple[Any, ...]] = []
    ptnr_trade: dict[int, str] = {}
    ptnr_city: dict[int, str] = {}
    ptnr_resp: dict[int, int] = {}
    ptnr_rate: dict[int, float] = {}
    n = 0
    for trade, label in TRADES.items():
        for k in range(8):
            n += 1
            city = CITIES[(k + len(partners)) % len(CITIES)]
            slow = k == 0  # one slow partner per trade
            resp = random.randint(75, 110) if slow else random.randint(22, 60)
            rate = round(random.uniform(*TRADE_RATE[trade]) * (1.4 if k == 1 else 1), 2)
            rating = round(random.uniform(2.6, 3.6) if slow else random.uniform(3.7, 4.9), 2)
            partners.append(
                (f"{label} {fake.last_name()} {city}", trade, city, rating, resp, rate, k != 7)
            )
            ptnr_trade[n], ptnr_city[n], ptnr_resp[n], ptnr_rate[n] = trade, city, resp, rate
    await conn.executemany(
        "INSERT INTO ptnr (ptnr_name,trade,city,rating,avg_resp_min,rate_eur_h,is_active) "
        "VALUES ($1,$2,$3,$4,$5,$6,$7)",
        partners,
    )
    active = {i: p[6] for i, p in enumerate(partners, start=1)}

    # fraud cluster: a few customers with repeated burglary claims
    fraud_custs = set(random.sample(range(1, N_CUSTOMERS + 1), 10))
    home_pols_of_fraud = [
        p for p, c in pol_cust.items() if c in fraud_custs and pol_line[p] == "HOME"
    ]

    loss_types = list(LOSS_WEIGHT)
    claims: list[tuple[Any, ...]] = []
    dispatches: list[tuple[Any, ...]] = []
    events: list[tuple[Any, ...]] = []
    for clm_id in range(1, N_CLAIMS + 1):
        is_fraud = bool(home_pols_of_fraud) and random.random() < 0.025
        for _ in range(100):
            if random.random() < 0.015:  # recent claims keep the pipeline "alive" (open statuses)
                ts = today - timedelta(minutes=random.randint(1, 6 * 60))
            else:
                ts = start + timedelta(
                    seconds=random.randint(0, int((today - start).total_seconds()))
                )
            if is_fraud:
                lt = "BRK"
            else:
                lt = random.choices(
                    loss_types,
                    weights=[LOSS_WEIGHT[t] * SEASON[t][ts.month - 1] for t in loss_types],
                )[0]
            code, line, descs = LOSS_TYPES[lt]
            candidates = (
                home_pols_of_fraud if is_fraud else [p for p, ln in pol_line.items() if ln == line]
            )
            pol = random.choice(candidates)
            if pol_start[pol] <= ts.date():
                break
        reported = ts
        loss_dt = (reported - timedelta(days=random.choice([0, 0, 0, 1, 1, 2, 5]))).date()
        chnl = _wchoice([(c, w) for c, w in CHANNELS])
        sev = random.choices(["LOW", "MED", "HIGH"], weights=[55, 35, 10])[0]
        base = {"LOW": (80, 500), "MED": (400, 2500), "HIGH": (2000, 14000)}[sev]
        est = round(random.uniform(*base), 2)

        end = pol_end[pol]
        covered = code in pol_covers[pol]
        lapsed = end is not None and end < loss_dt
        rej = None
        if lapsed:
            rej = "POLICY_LAPSED"
        elif not covered:
            rej = "NO_COVERAGE"
        elif random.random() < 0.02:
            rej = "EXCLUSION"
        cvg = cvg_id[code] if covered else None

        fraud = (
            random.randint(70, 98) if is_fraud else min(100, int(random.betavariate(1.2, 12) * 100))
        )
        age_days = (today - reported).days
        trade = next(c[4] for c in COVERAGES if c[0] == code)

        evts: list[tuple[str, datetime]] = [("NEW", reported)]
        stat = "NEW"
        appr = None
        if rej:
            stat = "REJ"
            evts.append(("TRI", reported + timedelta(minutes=random.randint(5, 40))))
            evts.append(("REJ", reported + timedelta(hours=random.randint(1, 48))))
        else:
            evts.append(("TRI", reported + timedelta(minutes=random.randint(3, 25))))
            stat = "TRI"
            if trade:
                cands = [i for i, t in ptnr_trade.items() if t == trade and active[i]]
                local = [i for i in cands if ptnr_city[i] == cust_city[pol_cust[pol]]]
                ptn = random.choice(local or cands)
                disp = evts[-1][1] + timedelta(minutes=random.randint(2, 15))
                evts.append(("ASG", disp))
                stat = "ASG"
                arrival = disp + timedelta(minutes=max(10, int(random.gauss(ptnr_resp[ptn], 12))))
                done = arrival + timedelta(minutes=random.randint(30, 210))
                cost = round(random.uniform(*TRADE_COST[trade]) * (0.8 + ptnr_rate[ptn] / 100), 2)
                rating = None
                dstat = "ASG"
                d_arr: datetime | None = None
                d_done: datetime | None = None
                if arrival <= today:
                    evts.append(("INP", arrival))
                    stat, dstat, d_arr = "INP", "ARR", arrival
                if done <= today:
                    stat, dstat, d_done = "CLS", "DONE", done
                    evts.append(("CLS", done + timedelta(hours=random.randint(1, 72))))
                    rating = max(1, min(5, round(random.gauss(5.2 - ptnr_resp[ptn] / 30, 1))))
                if age_days > 20 and dstat != "DONE":
                    dstat, stat = "CAN", "CLS"
                    d_arr = d_done = None
                    evts.append(("CLS", reported + timedelta(days=3)))
                dispatches.append((clm_id, ptn, disp, d_arr, d_done, dstat, cost, rating))
                appr = round(min(est, cost * 1.1), 2) if dstat == "DONE" else None
            else:
                if age_days > 10:
                    stat = "CLS"
                    evts.append(("CLS", reported + timedelta(days=random.randint(2, 9))))
                    appr = round(est * random.uniform(0.6, 1.0), 2)
                else:
                    stat = "INP"
                    evts.append(("INP", reported + timedelta(hours=random.randint(2, 30))))
            if stat == "CLS" and appr is None and not trade:
                appr = round(est * random.uniform(0.6, 1.0), 2)

        evts = [e for e in evts if e[1] <= today]
        claims.append(
            (
                clm_id,
                pol,
                cvg,
                reported,
                loss_dt,
                chnl,
                lt,
                stat,
                sev,
                est,
                appr,
                fraud,
                random.choice(descs),
                rej,
            )
        )
        for st_code, st_ts in evts:
            events.append((clm_id, st_code, st_ts))

    await conn.executemany(
        "INSERT INTO clm (clm_id,pol_id,cvg_id,reported_at,loss_dt,chnl,loss_typ,clm_stat,sev,"
        "est_amt_eur,appr_amt_eur,fraud_score,loss_desc,rej_reason) "
        "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14)",
        claims,
    )
    await conn.executemany(
        "INSERT INTO clm_dsp (clm_id,ptnr_id,dt_dispatch,dt_arrival,dt_done,dsp_stat,cost_eur,cust_rating) "
        "VALUES ($1,$2,$3,$4,$5,$6,$7,$8)",
        dispatches,
    )
    await conn.executemany("INSERT INTO clm_evt (clm_id,evt_stat,evt_ts) VALUES ($1,$2,$3)", events)
    await conn.execute(
        "SELECT setval(pg_get_serial_sequence('clm','clm_id'), (SELECT max(clm_id) FROM clm))"
    )

    counts = {
        t: await conn.fetchval(f"SELECT count(*) FROM {t}")
        for t in ["cust", "pol", "pol_cvg", "cvg", "ptnr", "clm", "clm_dsp", "clm_evt"]
    }
    print("Seeded insurance demo:", counts)
    await conn.close()


if __name__ == "__main__":
    asyncio.run(seed())
