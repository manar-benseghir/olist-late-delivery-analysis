# Olist database schema (`olist.db`)

Every result below comes from running SQL against `olist.db`. None of it is assumed from the dataset documentation. The queries are in the [SQL used](#sql-used) section at the end.

## Diagram

```
                          category_translation
                          PK product_category_name
                                    │ 1
                                    │ (13 products / 2 categories have no translation)
                                    │ N
customers ──1:1── orders ──1:N── order_items ──N:1── products
PK customer_id    PK order_id    PK (order_id,        PK product_id
   │                 │ │            order_item_id)
   │                 │ │                 │ N
   │                 │ │                 │
   │                 │ │                 └──N:1── sellers
   │                 │ │                          PK seller_id
   │                 │ │                             │
   │                 │ └──1:N── order_payments       │
   │                 │          PK (order_id,        │
   │                 │              payment_sequential)
   │                 │                               │
   │                 └──1:N── order_reviews          │
   │                          PK (review_id, order_id)
   │                                                 │
   └── customer_zip_code_prefix ┐   ┌── seller_zip_code_prefix
                                ▼   ▼
                             geolocation
                    (no unique key; ~53 rows per zip prefix)
```

## 1. Primary keys (what is unique in each table)

| Table | Primary key | Rows | Distinct key values | Unique? |
|---|---|---:|---:|---|
| customers | `customer_id` | 99,441 | 99,441 | Yes |
| orders | `order_id` | 99,441 | 99,441 | Yes |
| order_items | `(order_id, order_item_id)` | 112,650 | 112,650 | Yes |
| order_payments | `(order_id, payment_sequential)` | 103,886 | 103,886 | Yes |
| order_reviews | `(review_id, order_id)` | 99,224 | 99,224 | Yes |
| products | `product_id` | 32,951 | 32,951 | Yes |
| sellers | `seller_id` | 3,095 | 3,095 | Yes |
| category_translation | `product_category_name` | 71 | 71 | Yes |
| geolocation | none | 1,000,163 | 19,015 zip prefixes | No |

Columns that look like keys but are not unique:

- **`customers.customer_unique_id`**: 96,096 distinct values across 99,441 rows. `customer_id` is a new ID for each order, and `customer_unique_id` is the actual person. 2,997 people have more than one `customer_id`, and one has 17. To count real customers or repeat buyers, use `customer_unique_id`.
- **`order_reviews.review_id`**: 98,410 distinct values. 789 review IDs are attached to more than one order.
- **`order_reviews.order_id`**: 98,673 distinct values. 547 orders have 2 or 3 reviews.
- **`geolocation.geolocation_zip_code_prefix`**: 19,015 distinct prefixes in 1,000,163 rows, with up to 1,146 rows per prefix. There is no unique key in this table.

## 2. Foreign keys: does every value exist in the parent table?

| Child column | Parent column | Child rows checked | Orphan rows | Orphan distinct values | Result |
|---|---|---:|---:|---:|---|
| orders.customer_id | customers.customer_id | 99,441 | 0 | 0 | All match |
| order_items.order_id | orders.order_id | 112,650 | 0 | 0 | All match |
| order_items.product_id | products.product_id | 112,650 | 0 | 0 | All match |
| order_items.seller_id | sellers.seller_id | 112,650 | 0 | 0 | All match |
| order_payments.order_id | orders.order_id | 103,886 | 0 | 0 | All match |
| order_reviews.order_id | orders.order_id | 99,224 | 0 | 0 | All match |
| products.product_category_name | category_translation.product_category_name | 32,341 (non-null) | **13** | **2** | Missing translations |
| customers.customer_zip_code_prefix | geolocation.geolocation_zip_code_prefix | 99,441 | **278** | **157** | Missing zips |
| sellers.seller_zip_code_prefix | geolocation.geolocation_zip_code_prefix | 3,095 | **7** | **7** | Missing zips |

- The two categories with no English translation are `pc_gamer` and `portateis_cozinha_e_preparadores_de_alimentos`. Join `products` to `category_translation` with a LEFT JOIN, or these 13 products will disappear.
- `geolocation` is a lookup by zip prefix, not a strict parent table. Some zip prefixes are missing from it, so join it with a LEFT JOIN as well. A zip prefix has many rows in `geolocation`, so aggregate it first (for example, one average lat/lng per prefix). Otherwise the join will multiply your rows.

## 3. Cardinality (one-to-one or one-to-many?)

The checks count how many child rows each parent row has.

| Relationship | Parents | 0 children | 1 child | More than 1 | Max | Type |
|---|---:|---:|---:|---:|---:|---|
| customers → orders | 99,441 | 0 | 99,441 | 0 | 1 | **1:1** |
| orders → order_items | 99,441 | 775 | 88,863 | 9,803 | 21 | **1:N** (some orders have none) |
| orders → order_payments | 99,441 | 1 | 96,479 | 2,961 | 29 | **1:N** |
| orders → order_reviews | 99,441 | 768 | 98,126 | 547 | 3 | **1:N** (usually 1) |
| products → order_items | 32,951 | 0 | 18,117 | 14,834 | 527 | **1:N** |
| sellers → order_items | 3,095 | 0 | 509 | 2,586 | 2,033 | **1:N** |
| category_translation → products | 71 | 0 | 1 | 70 | 3,029 | **1:N** |
| customer_unique_id → customer_id | 96,096 | 0 | 93,099 | 2,997 | 17 | **1:N** |
| review_id ↔ order_id | | | | | | **N:M**: 789 reviews cover several orders, and 547 orders have several reviews |

What this means for joins:

- **customers–orders is strictly 1:1** on `customer_id`. To follow one person across orders, use `customer_unique_id`.
- **orders–sellers and orders–products are many-to-many** through `order_items`. One order can contain items from several sellers and products.
- **Don't join items, payments and reviews to orders in a single query.** Each one has a 1:N relationship to orders, so joining them together multiplies rows and inflates sums. Aggregate each one per `order_id` first, then join the results.
- 775 orders have no items. Most of them are `unavailable` (603) or `canceled` (164).
- 1 order (`bfbd0f9bdef84302105ad712db648a6c`, status `delivered`) has no payment record.

## 4. Nulls and duplicate rows

"Duplicate rows" means rows that are identical in every column.

| Table | Rows | Duplicate rows | Columns with nulls (count) |
|---|---:|---:|---|
| customers | 99,441 | 0 | none |
| orders | 99,441 | 0 | order_approved_at (160), order_delivered_carrier_date (1,783), order_delivered_customer_date (2,965) |
| order_items | 112,650 | 0 | none |
| order_payments | 103,886 | 0 | none |
| order_reviews | 99,224 | 0 | review_comment_title (87,656), review_comment_message (58,247) |
| products | 32,951 | 0 | product_category_name, product_name_lenght, product_description_lenght, product_photos_qty (610 each, the same 610 products); product_weight_g, product_length_cm, product_height_cm, product_width_cm (2 each) |
| sellers | 3,095 | 0 | none |
| category_translation | 71 | 0 | none |
| geolocation | 1,000,163 | **261,831** | none |

Notes:

- **Orders:** most null dates match the order status. For example, an order that hasn't shipped yet has no carrier date. Some don't fit that pattern, and the table below breaks the null dates down by status. 14 `delivered` orders have no approval date, and 8 `delivered` orders have no delivery date. Filter these out of delivery-time calculations.

  | Status | approved_at null | carrier_date null | customer_date null |
  |---|---:|---:|---:|
  | delivered | 14 | 2 | 8 |
  | shipped | 0 | 0 | 1,107 |
  | canceled | 141 | 550 | 619 |
  | unavailable | 0 | 609 | 609 |
  | invoiced | 0 | 314 | 314 |
  | processing | 0 | 301 | 301 |
  | created | 5 | 5 | 5 |
  | approved | 0 | 2 | 2 |

- **Reviews:** comment titles and messages are optional, so nulls there are expected. Every review has a score.
- **Products:** 610 products have no category and no name or description data at all.
- **Geolocation:** 26% of its rows are exact duplicates. In addition, 8,556 zip prefixes map to more than one spelling of the city name.

## SQL used

These queries ran against `olist.db` in SQLite. Where the same check ran on several tables, one example is shown, and the others differ only in table and column names.

### 1. Primary key uniqueness

The key is unique when `total_rows = distinct_keys`.

```sql
-- Single-column key
SELECT COUNT(*) AS total_rows,
       (SELECT COUNT(*) FROM (SELECT DISTINCT customer_id FROM customers)) AS distinct_keys
FROM customers;

-- Composite key
SELECT COUNT(*) AS total_rows,
       (SELECT COUNT(*) FROM (SELECT DISTINCT order_id, order_item_id FROM order_items)) AS distinct_keys
FROM order_items;
```

The same check ran on `customers.customer_unique_id`; `orders.order_id`; `products.product_id`; `sellers.seller_id`; `category_translation.product_category_name`; `order_reviews` (`review_id` alone, `order_id` alone, then both together); `order_payments (order_id, payment_sequential)`; and `geolocation.geolocation_zip_code_prefix`.

### 2. Foreign key orphans

This counts child rows whose value has no match in the parent table.

```sql
SELECT COUNT(*)                                                          AS child_rows_with_value,
       SUM(p.product_category_name IS NULL)                              AS orphan_rows,
       COUNT(DISTINCT CASE WHEN p.product_category_name IS NULL
                           THEN ch.product_category_name END)            AS orphan_distinct_values
FROM products ch
LEFT JOIN (SELECT DISTINCT product_category_name FROM category_translation) p
       ON ch.product_category_name = p.product_category_name
WHERE ch.product_category_name IS NOT NULL;

-- Which category values are missing from the translation table
SELECT DISTINCT p.product_category_name
FROM products p
LEFT JOIN category_translation t USING (product_category_name)
WHERE p.product_category_name IS NOT NULL
  AND t.product_category_name IS NULL;
```

The same check ran for each pair in the foreign key table in section 2.

### 3. Cardinality

This counts the children of each parent row, then summarizes those counts.

```sql
SELECT COUNT(*)    AS parents,
       SUM(n = 0)  AS with_0_children,
       SUM(n = 1)  AS with_1,
       SUM(n > 1)  AS with_many,
       MAX(n)      AS max_children
FROM (
    SELECT p.order_id, COUNT(ch.order_id) AS n
    FROM orders p
    LEFT JOIN order_items ch ON ch.order_id = p.order_id
    GROUP BY p.order_id
);

-- Number of customer_ids per real person
SELECT COUNT(*) AS unique_customers, SUM(n > 1) AS with_multiple_customer_ids, MAX(n) AS max_ids
FROM (SELECT customer_unique_id, COUNT(*) AS n FROM customers GROUP BY customer_unique_id);

-- review_id <-> order_id in both directions
SELECT COUNT(*) FROM (SELECT review_id FROM order_reviews GROUP BY review_id HAVING COUNT(*) > 1);
SELECT COUNT(*) FROM (SELECT order_id  FROM order_reviews GROUP BY order_id  HAVING COUNT(*) > 1);

-- Rows per zip prefix in geolocation
SELECT COUNT(*) AS zips, SUM(n > 1) AS zips_with_many_rows, MAX(n) AS max_rows
FROM (SELECT geolocation_zip_code_prefix, COUNT(*) AS n FROM geolocation GROUP BY 1);

-- Status of orders that have no items
SELECT o.order_status, COUNT(*)
FROM orders o
LEFT JOIN (SELECT DISTINCT order_id FROM order_items) i ON i.order_id = o.order_id
WHERE i.order_id IS NULL
GROUP BY 1;

-- Orders with no payment record
SELECT o.order_id, o.order_status
FROM orders o
LEFT JOIN (SELECT DISTINCT order_id FROM order_payments) p USING (order_id)
WHERE p.order_id IS NULL;
```

### 4. Nulls and duplicate rows

```sql
-- Nulls per column (one SUM(... IS NULL) for each column in the table)
SELECT COUNT(*),
       SUM(order_approved_at IS NULL),
       SUM(order_delivered_carrier_date IS NULL),
       SUM(order_delivered_customer_date IS NULL)
       -- ...and so on for the remaining columns
FROM orders;

-- Exact duplicate rows
SELECT COUNT(*) - (SELECT COUNT(*) FROM (SELECT DISTINCT * FROM geolocation)) AS duplicate_rows
FROM geolocation;

-- Null order dates by status
SELECT order_status,
       SUM(order_approved_at IS NULL),
       SUM(order_delivered_carrier_date IS NULL),
       SUM(order_delivered_customer_date IS NULL)
FROM orders
GROUP BY 1;

-- Zip prefixes with more than one city spelling
SELECT COUNT(*)
FROM (SELECT geolocation_zip_code_prefix, COUNT(DISTINCT geolocation_city) AS n
      FROM geolocation GROUP BY 1 HAVING n > 1);
```
