from __future__ import annotations

import asyncio
import random
from datetime import date, datetime, timedelta

import asyncpg
from faker import Faker

from artoo.config import settings


fake = Faker()


def _dsn() -> str:
    raw = settings.postgres_dsn
    dsn = raw.replace("+psycopg2", "")
    return dsn.replace("postgres:5432", "localhost:5432")


async def seed() -> None:
    conn = await asyncpg.connect(_dsn())
    tables = ["gx", "rev_daily", "bkng", "rm_cat", "prop", "cust"]
    for tbl in tables:
        await conn.execute(f"TRUNCATE TABLE {tbl} RESTART IDENTITY CASCADE;")

    # seed categories
    cats = [
        ("STD", "Standard", 90.0, 2),
        ("SUP", "Superior", 140.0, 3),
        ("DLX", "Deluxe", 210.0, 3),
        ("STE", "Suite", 320.0, 4),
        ("PRS", "Presidential", 520.0, 4),
    ]
    await conn.executemany(
        "INSERT INTO rm_cat (cat_code, cat_name, cat_base_rate, cat_max_occ) VALUES ($1,$2,$3,$4)",
        cats,
    )

    # properties
    cities = [
        ("Barcelona", "ESP"),
        ("Madrid", "ESP"),
        ("Lisbon", "PRT"),
        ("Mexico City", "MEX"),
        ("London", "GBR"),
        ("Dubai", "ARE"),
    ]
    props = []
    for idx, (city, country) in enumerate(cities, start=1):
        props.append(
            (f"Logicalis Hotel {city}", city, country, random.randint(3, 5), random.randint(80, 220), random.choice(["RESORT", "URBAN", "BOUTIQUE"]))
        )
    await conn.executemany(
        "INSERT INTO prop (prop_name, prop_city, prop_country, prop_stars, prop_rooms, prop_type) VALUES ($1,$2,$3,$4,$5,$6)",
        props,
    )

    # customers
    customers = []
    tiers = ["BRZ", "SLV", "GLD", "PLT"]
    nationalities = ["ESP", "PRT", "GBR", "FRA", "USA", "MEX", "ARE", "DEU", "ITA", "NLD", "SWE", "NOR", "BRA", "ARG", "CHL"]
    for _ in range(500):
        dob = fake.date_of_birth(minimum_age=18, maximum_age=80)
        customers.append(
            (
                fake.first_name(),
                fake.last_name(),
                fake.email()[:100],
                fake.phone_number()[:20],
                dob,
                random.choice(nationalities),
                random.choice(tiers),
                datetime.utcnow(),
            )
        )
    await conn.executemany(
        """
        INSERT INTO cust (cust_fname, cust_lname, cust_email, cust_phone, cust_dob, cust_nat, cust_tier, cust_created)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
        """,
        customers,
    )

    cust_ids = list(range(1, len(customers) + 1))
    prop_ids = list(range(1, len(props) + 1))
    cat_ids = list(range(1, len(cats) + 1))

    # bookings
    bookings = []
    base_date = date.today() - timedelta(days=365)
    for bk_id in range(5000):
        cust_id = random.choice(cust_ids)
        prop_id = random.choice(prop_ids)
        cat_id = random.choice(cat_ids)
        checkin = base_date + timedelta(days=random.randint(0, 365))
        nights = random.randint(1, 7)
        checkout = checkin + timedelta(days=nights)
        guests = random.randint(1, 4)
        status = random.choices(["CONF", "CNCL", "NOSH", "COMP"], weights=[0.75, 0.1, 0.05, 0.1])[0]
        channel = random.choice(["WEB", "APP", "OTA", "PHONE", "WALKIN"])
        rate = cats[cat_id - 1][2]
        total = round(rate * nights * (1 + random.uniform(-0.15, 0.25)), 2)
        bookings.append(
            (
                cust_id,
                prop_id,
                cat_id,
                checkin,
                checkout,
                guests,
                total,
                random.choice(["VISA", "AMEX", "MC", "CASH", "BNKXFR"]),
                status,
                channel,
                datetime.utcnow(),
            )
        )
    await conn.executemany(
        """
        INSERT INTO bkng (cust_id, prop_id, cat_id, dt_chkin, dt_chkout, n_guests, tot_amt, pay_meth, bk_status, bk_channel, bk_created)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
        """,
        bookings,
    )

    # experiences
    experiences = []
    for bk_idx, booking in enumerate(bookings, start=1):
        if random.random() < 0.6:
            continue
        nps = random.randint(0, 10)
        experiences.append(
            (
                bk_idx,
                nps,
                random.randint(1, 5),
                random.randint(1, 5),
                random.randint(1, 5),
                fake.paragraph(nb_sentences=2),
                booking[3],
            )
        )
    await conn.executemany(
        """
        INSERT INTO gx (bk_id, nps_score, ov_rating, clean_rating, svc_rating, fb_text, gx_date)
        VALUES ($1,$2,$3,$4,$5,$6,$7)
        """,
        experiences,
    )

    # revenue daily
    rev_rows = []
    for prop_id in prop_ids:
        for day_offset in range(180):
            rev_date = base_date + timedelta(days=day_offset)
            occ = round(random.uniform(0.45, 0.92), 2) * 100
            adr = round(random.uniform(80, 320), 2)
            revpar = round(adr * (occ / 100), 2)
            rev_rows.append(
                (
                    prop_id,
                    rev_date,
                    occ,
                    adr,
                    revpar,
                    random.randint(20, 120),
                    random.randint(20, 120),
                    random.randint(1, 20),
                )
            )
    await conn.executemany(
        """
        INSERT INTO rev_daily (prop_id, rev_date, occ_pct, adr, revpar, n_checkins, n_checkouts, n_cancellations)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
        """,
        rev_rows,
    )

    await conn.close()


if __name__ == "__main__":
    asyncio.run(seed())
