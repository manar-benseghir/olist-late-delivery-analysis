-- analysis.sql
-- Builds the table first_orders: one row per customer (customer_unique_id),
-- describing their FIRST order, whether it arrived late, and whether they
-- placed another order within 180 days.
--
-- Question: do customers whose first order arrived late come back to buy less?
--
-- Definitions
--   Customer     = customers.customer_unique_id (customer_id is per order).
--   First order  = the customer's earliest order of any status (ties on the
--                  timestamp broken by order_id). The customer is kept only if
--                  that first order was delivered and has a delivery date.
--   Late         = delivered on a later calendar day than the estimated date
--                  (delivered ON the estimated day counts as on time).
--   days_late    = delivered date minus estimated date, in whole calendar days
--                  (negative = early, 0 = on the estimated day, >0 = late).
--   Repeat       = any order (any status) placed strictly after the first
--                  order's timestamp and within 180 days of it.
--   Repeat (non-canceled) = same, but the later order must not be 'canceled'.
--                  Used only as a sensitivity check (is_repeat_noncanceled).
--   Eligible     = first order placed at least 180 days before the effective
--                  end of the data (2018-08-31 23:59:59), so everyone had the
--                  same 180-day window to come back.
--
-- Items, payments and reviews are each aggregated to one row per order_id
-- before joining, so the joins can't multiply rows.
--
-- Run with:  python -c "import sqlite3; c=sqlite3.connect('olist.db'); c.executescript(open('analysis.sql').read())"

DROP TABLE IF EXISTS first_orders;

CREATE TABLE first_orders AS
WITH
params AS (
    -- Effective end of the data. The last purchase timestamp is 2018-10-17,
    -- but Sep-Oct 2018 contain only 20 orders, all canceled, so real activity
    -- ends on 2018-08-31. Using that date gives every customer a fully
    -- observed 180-day window.
    SELECT '2018-08-31 23:59:59' AS data_end
),

-- Every order, tagged with the real customer
cust_orders AS (
    SELECT c.customer_unique_id,
           c.customer_state,
           o.order_id,
           o.order_status,
           o.order_purchase_timestamp,
           o.order_delivered_customer_date,
           o.order_estimated_delivery_date,
           ROW_NUMBER() OVER (
               PARTITION BY c.customer_unique_id
               ORDER BY o.order_purchase_timestamp, o.order_id
           ) AS order_rank
    FROM orders o
    JOIN customers c ON c.customer_id = o.customer_id
),

-- One row per order: items
items_per_order AS (
    SELECT order_id,
           COUNT(*)                   AS n_items,
           COUNT(DISTINCT product_id) AS n_products,
           COUNT(DISTINCT seller_id)  AS n_sellers,
           SUM(price)                 AS items_price,
           SUM(freight_value)         AS freight_value
    FROM order_items
    GROUP BY order_id
),

-- One row per order: payments
payments_per_order AS (
    SELECT order_id,
           SUM(payment_value)         AS payment_value,
           COUNT(*)                   AS n_payments,
           MAX(payment_installments)  AS max_installments
    FROM order_payments
    GROUP BY order_id
),

-- One row per order: reviews (average score if several reviews)
reviews_per_order AS (
    SELECT order_id,
           AVG(review_score)          AS review_score,
           COUNT(*)                   AS n_reviews
    FROM order_reviews
    GROUP BY order_id
),

-- Each customer's first order, delivered only, inside the eligibility window
first_order AS (
    SELECT co.*
    FROM cust_orders co, params p
    WHERE co.order_rank = 1
      AND co.order_status = 'delivered'
      AND co.order_delivered_customer_date IS NOT NULL
      AND julianday(co.order_purchase_timestamp) <= julianday(p.data_end) - 180
),

-- Orders placed after the first one, within 180 days
repeat_orders AS (
    SELECT f.customer_unique_id,
           COUNT(*)                         AS n_orders_180d,
           SUM(o.order_status <> 'canceled') AS n_orders_180d_noncanceled,
           MIN(julianday(o.order_purchase_timestamp)
               - julianday(f.order_purchase_timestamp)) AS days_to_next_order
    FROM first_order f
    JOIN cust_orders o
      ON o.customer_unique_id = f.customer_unique_id
     AND o.order_purchase_timestamp >  f.order_purchase_timestamp
     AND julianday(o.order_purchase_timestamp)
         <= julianday(f.order_purchase_timestamp) + 180
    GROUP BY f.customer_unique_id
)

SELECT
    f.customer_unique_id,
    f.customer_state,
    f.order_id                                   AS first_order_id,
    f.order_purchase_timestamp                   AS first_purchase_ts,
    f.order_estimated_delivery_date              AS estimated_delivery_date,
    f.order_delivered_customer_date              AS delivered_date,
    CASE WHEN date(f.order_delivered_customer_date) > date(f.order_estimated_delivery_date)
         THEN 1 ELSE 0 END                       AS is_late,
    CAST(julianday(date(f.order_delivered_customer_date))
         - julianday(date(f.order_estimated_delivery_date)) AS INTEGER) AS days_late,
    ROUND(julianday(f.order_delivered_customer_date)
          - julianday(f.order_purchase_timestamp), 2)      AS delivery_days,
    i.n_items,
    i.n_products,
    i.n_sellers,
    i.items_price,
    i.freight_value,
    p.payment_value,
    p.n_payments,
    p.max_installments,
    r.review_score,
    r.n_reviews,
    COALESCE(ro.n_orders_180d, 0)                AS n_orders_180d,
    CASE WHEN ro.n_orders_180d > 0 THEN 1 ELSE 0 END AS is_repeat,
    -- Sensitivity version: only repeat orders whose status is not 'canceled'
    COALESCE(ro.n_orders_180d_noncanceled, 0)    AS n_orders_180d_noncanceled,
    CASE WHEN ro.n_orders_180d_noncanceled > 0 THEN 1 ELSE 0 END AS is_repeat_noncanceled,
    ROUND(ro.days_to_next_order, 2)              AS days_to_next_order
FROM first_order f
LEFT JOIN items_per_order    i  ON i.order_id = f.order_id
LEFT JOIN payments_per_order p  ON p.order_id = f.order_id
LEFT JOIN reviews_per_order  r  ON r.order_id = f.order_id
LEFT JOIN repeat_orders      ro ON ro.customer_unique_id = f.customer_unique_id;


-- ---------------------------------------------------------------------------
-- Summary: customers, % late, and repeat rate for late vs on-time
-- ---------------------------------------------------------------------------
SELECT COUNT(*)                          AS customers,
       ROUND(100.0 * AVG(is_late), 2)    AS pct_late,
       ROUND(100.0 * AVG(is_repeat), 2)  AS repeat_rate_pct
FROM first_orders;

SELECT CASE is_late WHEN 1 THEN 'late' ELSE 'on time' END AS first_order,
       COUNT(*)                          AS customers,
       SUM(is_repeat)                    AS repeaters,
       ROUND(100.0 * AVG(is_repeat), 2)  AS repeat_rate_pct
FROM first_orders
GROUP BY is_late;
