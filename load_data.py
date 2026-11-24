"""Load the 9 Olist Brazilian E-Commerce CSVs into a SQLite database (olist.db).

Re-runnable: each table is dropped and recreated on every run.
Uses only the Python standard library.

Usage:  python load_data.py
"""
import csv
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DB_PATH = HERE / "olist.db"

# CSV file -> short table name
FILES = {
    "olist_customers_dataset.csv": "customers",
    "olist_geolocation_dataset.csv": "geolocation",
    "olist_order_items_dataset.csv": "order_items",
    "olist_order_payments_dataset.csv": "order_payments",
    "olist_order_reviews_dataset.csv": "order_reviews",
    "olist_orders_dataset.csv": "orders",
    "olist_products_dataset.csv": "products",
    "olist_sellers_dataset.csv": "sellers",
    "product_category_name_translation.csv": "category_translation",
}

# Columns that look numeric but must stay text (leading zeros matter).
FORCE_TEXT = {"customer_zip_code_prefix", "seller_zip_code_prefix",
              "geolocation_zip_code_prefix"}


def infer_type(values):
    """Return INTEGER, REAL or TEXT for a column's non-empty values."""
    kind = "INTEGER"
    for v in values:
        if v == "":
            continue
        if kind == "INTEGER":
            try:
                int(v)
                continue
            except ValueError:
                kind = "REAL"
        try:
            float(v)
        except ValueError:
            return "TEXT"
    return kind


def convert(value, col_type):
    if value == "":
        return None
    if col_type == "INTEGER":
        return int(value)
    if col_type == "REAL":
        return float(value)
    return value


def load_csv(conn, csv_path, table):
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        header = next(reader)
        rows = list(reader)

    types = []
    for i, col in enumerate(header):
        if col in FORCE_TEXT:
            types.append("TEXT")
        else:
            types.append(infer_type(r[i] for r in rows))

    cols_sql = ", ".join(f'"{c}" {t}' for c, t in zip(header, types))
    conn.execute(f'DROP TABLE IF EXISTS "{table}"')
    conn.execute(f'CREATE TABLE "{table}" ({cols_sql})')

    placeholders = ", ".join("?" for _ in header)
    conn.executemany(
        f'INSERT INTO "{table}" VALUES ({placeholders})',
        ([convert(v, t) for v, t in zip(r, types)] for r in rows),
    )
    return len(rows)


def main():
    missing = [name for name in FILES if not (HERE / name).exists()]
    if missing:
        print("Missing CSV files:")
        for name in missing:
            print(f"  - {name}")
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)
    try:
        for filename, table in FILES.items():
            n = load_csv(conn, HERE / filename, table)
            print(f"Loaded {table:<22} {n:>9,} rows  <- {filename}")
        conn.commit()
    finally:
        conn.close()
    print(f"\nDatabase written to {DB_PATH}")


if __name__ == "__main__":
    main()
