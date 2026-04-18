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
    return raw.replace("+psycopg2", "")


async def seed() -> None:
    conn = await asyncpg.connect(_dsn())
    tables = ["reviews", "order_items", "orders", "products", "customers"]
    for tbl in tables:
        await conn.execute(f"TRUNCATE TABLE {tbl} RESTART IDENTITY CASCADE;")

    categories = [
        ("Electronics", "Smartphones", "TechBrand", 299.0, 180.0),
        ("Electronics", "Laptops", "TechBrand", 899.0, 540.0),
        ("Electronics", "Headphones", "SoundMax", 79.0, 35.0),
        ("Clothing", "T-Shirts", "UrbanWear", 25.0, 8.0),
        ("Clothing", "Jeans", "UrbanWear", 55.0, 20.0),
        ("Clothing", "Jackets", "UrbanWear", 120.0, 45.0),
        ("Home", "Coffee Makers", "BrewPro", 89.0, 40.0),
        ("Home", "Blenders", "BrewPro", 49.0, 22.0),
        ("Home", "Vacuum Cleaners", "CleanTech", 199.0, 90.0),
        ("Sports", "Running Shoes", "ActiveFit", 95.0, 38.0),
        ("Sports", "Yoga Mats", "ActiveFit", 30.0, 10.0),
        ("Books", "Fiction", "PageTurner", 15.0, 5.0),
    ]

    products = []
    skus = set()
    for cat, sub, brand, base_price, cost in categories:
        for i in range(1, random.randint(3, 6)):
            sku = f"{sub[:3].upper()}-{brand[:3].upper()}-{i:03d}"
            while sku in skus:
                sku = f"{sub[:3].upper()}-{brand[:3].upper()}-{random.randint(100, 999):03d}"
            skus.add(sku)
            price = round(base_price * random.uniform(0.8, 1.4), 2)
            cost_p = round(cost * random.uniform(0.8, 1.2), 2)
            products.append(
                (
                    sku,
                    f"{brand} {sub} Model {i}",
                    cat,
                    sub,
                    brand,
                    price,
                    cost_p,
                    random.randint(10, 500),
                    random.random() > 0.05,
                )
            )
    await conn.executemany(
        "INSERT INTO products (sku, name, category, subcategory, brand, unit_price, cost_price, stock_qty, is_active) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)",
        products,
    )

    customers = []
    segments = ["BRONZE", "SILVER", "GOLD", "PLATINUM"]
    countries = [
        "ESP",
        "PRT",
        "GBR",
        "FRA",
        "USA",
        "MEX",
        "DEU",
        "ITA",
        "NLD",
        "SWE",
        "BRA",
        "ARG",
        "COL",
        "CHL",
    ]
    for _ in range(500):
        dob = fake.date_of_birth(minimum_age=18, maximum_age=80)
        customers.append(
            (
                fake.first_name(),
                fake.last_name(),
                fake.email()[:100],
                fake.phone_number()[:20],
                dob,
                random.choice(countries),
                random.choice(segments),
                datetime.now(),
            )
        )
    await conn.executemany(
        "INSERT INTO customers (first_name, last_name, email, phone, date_of_birth, country, segment, created_at) VALUES ($1,$2,$3,$4,$5,$6,$7,$8)",
        customers,
    )

    cust_ids = list(range(1, len(customers) + 1))
    prod_ids = list(range(1, len(products) + 1))

    orders = []
    base_date = date.today() - timedelta(days=365)
    for _ in range(5000):
        cust_id = random.choice(cust_ids)
        order_date = base_date + timedelta(
            days=random.randint(0, 365),
            hours=random.randint(0, 23),
            minutes=random.randint(0, 59),
        )
        status = random.choices(
            ["COMPLETED", "SHIPPED", "PROCESSING", "CANCELLED", "RETURNED"],
            weights=[0.55, 0.15, 0.10, 0.12, 0.08],
        )[0]
        channel = random.choice(["WEB", "MOBILE_APP", "MARKETPLACE", "SOCIAL", "EMAIL"])
        payment = random.choice(["CREDIT_CARD", "DEBIT_CARD", "PAYPAL", "BNPL", "BANK_TRANSFER"])
        shipping = round(random.uniform(3.99, 15.99), 2)
        discount = round(random.choice([0, 0, 0, 5, 10, 15, 20, 25]), 2)
        orders.append(
            (
                cust_id,
                order_date,
                status,
                channel,
                payment,
                shipping,
                0.0,
                discount,
            )
        )
    await conn.executemany(
        "INSERT INTO orders (customer_id, order_date, status, channel, payment_method, shipping_cost, total_amount, discount_pct) VALUES ($1,$2,$3,$4,$5,$6,$7,$8)",
        orders,
    )

    order_items = []
    for order_idx, order in enumerate(orders, start=1):
        n_items = random.choices([1, 2, 3, 4, 5], weights=[0.40, 0.30, 0.18, 0.08, 0.04])[0]
        order_total = 0.0
        for _ in range(n_items):
            prod_id = random.choice(prod_ids)
            qty = random.randint(1, 3)
            unit_price = products[prod_id - 1][5]
            line_total = round(unit_price * qty * (1 - order[7] / 100), 2)
            order_total += line_total
            order_items.append((order_idx, prod_id, qty, unit_price, line_total))
        order_total = round(order_total + order[5], 2)
        await conn.execute(
            "UPDATE orders SET total_amount = $1 WHERE order_id = $2",
            order_total,
            order_idx,
        )
    await conn.executemany(
        "INSERT INTO order_items (order_id, product_id, quantity, unit_price, line_total) VALUES ($1,$2,$3,$4,$5)",
        order_items,
    )

    reviews = []
    for order_idx in range(1, len(orders) + 1):
        if random.random() < 0.35:
            continue
        item_rows = [r for r in order_items if r[0] == order_idx]
        if not item_rows:
            continue
        item = random.choice(item_rows)
        rating = random.choices([1, 2, 3, 4, 5], weights=[0.05, 0.08, 0.15, 0.32, 0.40])[0]
        titles = [
            "Great product",
            "Not bad",
            "Exceeded expectations",
            "Could be better",
            "Worth the price",
            "Highly recommend",
            "Disappointing",
            "Perfect",
            "Good value",
            "Average quality",
        ]
        reviews.append(
            (
                order_idx,
                item[1],
                rating,
                random.choice(titles),
                fake.paragraph(nb_sentences=random.randint(1, 4)),
                date.today() - timedelta(days=random.randint(1, 300)),
            )
        )
    await conn.executemany(
        "INSERT INTO reviews (order_id, product_id, rating, title, body, review_date) VALUES ($1,$2,$3,$4,$5,$6)",
        reviews,
    )

    daily_sales = []
    for prod_id in prod_ids:
        for day_offset in range(180):
            sale_date = base_date + timedelta(days=day_offset)
            units = random.randint(0, 15)
            if units == 0:
                continue
            price = products[prod_id - 1][5]
            revenue = round(units * price, 2)
            returns = random.choices([0, 0, 0, 0, 1, 2], weights=[0.7, 0.1, 0.1, 0.05, 0.03, 0.02])[
                0
            ]
            net = round(revenue * (1 - returns * 0.05), 2)
            daily_sales.append((sale_date, prod_id, units, revenue, returns, net))
    await conn.executemany(
        "INSERT INTO daily_sales (sale_date, product_id, units_sold, revenue, returns, net_revenue) VALUES ($1,$2,$3,$4,$5,$6)",
        daily_sales,
    )

    await conn.close()


if __name__ == "__main__":
    asyncio.run(seed())
