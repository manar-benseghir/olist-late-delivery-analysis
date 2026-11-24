# Decisions log

Every decision and correction in this project, in order. Each entry records what happened, what we decided, and why.

Each entry also says who made the decision:
- **User:** you set it.
- **Claude:** I chose it where your rules left room.
- **Correction:** an earlier choice that was changed.

Research question: *do customers whose first order arrived late come back to buy less?*

---

## Before the analysis session

### D1. Replaced the pre-merged single-table dataset (correction, user)
- **What happened:** The first download was a pre-merged, single-table version of the Olist dataset. It wasn't relational.
- **Decision:** Throw it away and use the original 9-file Olist Brazilian E-Commerce dataset.
- **Why:** A pre-merged table hides how orders, items, payments and reviews relate. It has also already joined one-to-many tables together, so rows are duplicated and totals are unreliable. The original files let us check keys and control joins ourselves.

### D2. Re-downloaded the full zip after files were missing (correction, user)
- **What happened:** The first download of the original dataset contained only 4 of the 9 CSV files.
- **Decision:** Re-download the full zip.
- **Why:** The analysis needs all 9 tables. Orders, customers, items, payments and reviews are all used in the analysis table.

---

## Loading the data

### D3. Check that all 9 files exist before loading anything (user)
- **What happened:** Because of D2, we checked the folder first.
- **Decision:** The loader stops and lists any missing file before it touches the database. All 9 files were present.
- **Why:** This prevents a partial database that quietly lacks a table.

### D4. SQLite database with short table names (user)
- **What happened:** The files needed to go into one queryable database.
- **Decision:** The database is `olist.db`, with one table per CSV and short names: `customers`, `geolocation`, `order_items`, `order_payments`, `order_reviews`, `orders`, `products`, `sellers`, `category_translation`. The loader is `load_data.py`.
- **Why:** One file is easy to share and query, and short names make the SQL readable.

### D5. How the loader works (Claude)
- **What happened:** The loader needed to be reliable to run again.
- **Decision:**
  - It drops and recreates every table on each run, so a second run never duplicates rows.
  - It uses only Python's standard library, so there is nothing to install.
  - It works out whether each column is a whole number, a decimal or text from the values in that column.
  - Empty cells are stored as NULL.
  - It reads the files as UTF-8 and ignores the invisible byte-order mark some files start with.
- **Why:** Anyone can rebuild the database with `python load_data.py` and get the same result.

### D6. Zip code prefixes stored as text (Claude)
- **What happened:** `customer_zip_code_prefix`, `seller_zip_code_prefix` and `geolocation_zip_code_prefix` look numeric.
- **Decision:** Store them as text.
- **Why:** Brazilian zip prefixes can start with 0. Storing them as numbers would drop the leading zeros and break matches.

### D7. Kept the original column names, misspellings included (Claude)
- **What happened:** `products` has the misspelled columns `product_name_lenght` and `product_description_lenght`.
- **Decision:** Keep the names exactly as they are in the source files.
- **Why:** The names then match the dataset's documentation and other people's work on it. Renaming can be done later in a view if needed.

---

## Checking the schema (`schema.md`)

### D8. Check every relationship with SQL instead of assuming (user)
- **What happened:** We needed to know how the tables relate.
- **Decision:** For every table, check uniqueness, missing parent values, one-to-one versus one-to-many, nulls and exact duplicate rows with SQL. The results and queries are in `schema.md`.
- **Why:** The dataset's documentation doesn't guarantee clean keys, and several turned out not to be clean (see D9 and D10).

### D9. Primary keys as found (Claude, from the checks)
- **What happened:** Several columns that look like keys aren't unique.
- **Decision:** Use these keys:
  - Single-column keys: `customer_id`, `order_id`, `product_id`, `seller_id`, `product_category_name`.
  - Two-column keys: `order_items (order_id, order_item_id)`, `order_payments (order_id, payment_sequential)` and `order_reviews (review_id, order_id)`.
  - `geolocation` has no key.
- **Why:**
  - `review_id` alone repeats across 789 orders.
  - `order_id` repeats in reviews for 547 orders.
  - `geolocation` has about 53 rows per zip prefix, and 26% of its rows are exact duplicates.

### D10. LEFT JOIN to category translations and geolocation (Claude, recommendation)
- **What happened:** 13 products have categories with no English translation (`pc_gamer`, `portateis_cozinha_e_preparadores_de_alimentos`). 157 customer zip prefixes and 7 seller zip prefixes are missing from `geolocation`.
- **Decision:**
  - Join both tables with LEFT JOIN so these rows aren't lost.
  - Reduce `geolocation` to one row per zip prefix before joining it.
- **Why:** An inner join would silently drop rows. Joining the full `geolocation` table would multiply rows. Neither table is used in the analysis yet.

### D11. Rewrote a slow check query (correction, Claude)
- **What happened:** A check query took more than 5 minutes and was stopped. It used a NOT EXISTS subquery between `orders` and `order_items`, and `order_items` has no index on `order_id`.
- **Decision:** Rewrite it as a LEFT JOIN against the distinct list of order IDs. The rewritten version runs in seconds.
- **Why:** The results are the same and it's much faster. We use the same pattern in later queries.

---

## The analysis table (`first_orders`, `analysis.sql`)

### D12. Use `customer_unique_id` as the customer (user)
- **What happened:** `customer_id` is new for every order, so each one has exactly one order. In other words, `customers` and `orders` are 1:1.
- **Decision:** Identify customers by `customer_unique_id`.
- **Why:** With `customer_id`, nobody could ever be a repeat buyer. 2,997 people have more than one `customer_id`, and one has 17.

### D13. Total items, payments and reviews per order before joining (user)
- **What happened:** Items, payments and reviews are each one-to-many with orders.
- **Decision:** Reduce each one to a single row per `order_id` first, then join.
- **Why:** Joining them directly multiplies rows and inflates totals. As a check, the summed item price plus freight in `first_orders` matched the summed payments within 0.02%.

### D14. First order = earliest order of any status, kept only if delivered (Claude, interpreting the user's rule)
- **What happened:** The rule "each customer's first order, delivered orders only" could mean either "the first order, if it was delivered" or "the first *delivered* order".
- **Decision:** Take the customer's earliest order of any status. Keep the customer only if that order was delivered and has a delivery date. This drops 102 customers whose first order was canceled or not delivered.
- **Why:** The question is about the customer's *first* experience. A later delivered order isn't their first order. Switching to the other reading is a one-line change.

### D15. Tied first orders: pick by `order_id`; a repeat must be strictly later (Claude)
- **What happened:** 276 customers placed several orders at the exact same first timestamp.
- **Decision:**
  - Among tied orders, the one with the lowest `order_id` is the first order.
  - A repeat order must have a purchase time strictly later than the first order's.
- **Why:** Orders placed at the same moment are one shopping session, not a return visit.

### D16. Repeat = another order within 180 days (user)
- **What happened:** We needed a definition of "came back".
- **Decision:** A customer is a repeat buyer if they placed another order within 180 days after the first order.
- **Why:** A fixed window lets us compare customers fairly, whatever date they first ordered.

### D17. Canceled and other non-delivered orders count as repeats (Claude)
- **What happened:** The repeat rule didn't say which order statuses count.
- **Decision:** Any later order counts, whatever its status, including canceled.
- **Why:** Placing an order shows the customer came back, even if it was canceled later. Counting only delivered repeats would be a different question.

### D18. Only include customers with a full 180-day window (user)
- **What happened:** A customer whose first order was close to the end of the data would have had less time to come back.
- **Decision:** Only include customers whose first order was at least 180 days before the end of the data.
- **Why:** Everyone then has the same chance to repeat.

### D19. End of data: 2018-10-17, then 2018-08-31 (correction, user)
- **What happened:**
  - Following D18 literally, the first build used the last purchase timestamp, 2018-10-17.
  - Checking orders per month showed that September and October 2018 contain only 20 orders, all canceled. Real activity ends on 2018-08-31.
  - With the October date, customers who first ordered in March and April 2018 had about 1.5 months less time to come back, which breaks the goal of D18.
- **Decision:** Fix the end of data at `2018-08-31 23:59:59`. The latest first order included is now from 2018-03-04.
- **Why:** This gives every customer a fully observed 180-day window, as D18 intended.

### D20. Late is decided by calendar day (correction, user)
- **What happened:**
  - The first rule compared timestamps: `order_delivered_customer_date > order_estimated_delivery_date`.
  - The estimated date is always stored as midnight, so an order delivered at any time *on* the estimated day counted as late.
- **Decision:**
  - An order is late only if it was delivered on a later calendar day than the estimated date.
  - `days_late` is the delivery date minus the estimated date in whole calendar days: negative means early, 0 means on the day, and anything above 0 means late.
- **Why:** Delivery on the promised day is on time from the customer's point of view. Under the final cutoff, 612 customers were reclassified from late to on time. `is_late` and `days_late > 0` agree on every row.

### D21. Review score: average of several reviews; missing reviews stay NULL (user and Claude)
- **What happened:** Some first orders have several reviews, and some have none.
- **Decision:**
  - Average the scores when there are several (user). This applies to 243 customers.
  - Leave `review_score` as NULL when there is no review (Claude). This applies to 420 customers.
- **Why:**
  - Averaging gives one score per order without multiplying rows.
  - Filling missing reviews with any value would invent data.

### D22. Extra columns kept in `first_orders` (Claude)
- **What happened:** The table had room for order and delivery detail.
- **Decision:** Keep these columns:
  - `customer_state`
  - `delivery_days`
  - Item, product and seller counts, price and freight
  - Payment total, number of payments and maximum installments
  - `n_orders_180d` and `days_to_next_order`
- **Why:** They may help explain differences between late and on-time customers later, for example order value or region. One first order has no payment record, so its payment columns are NULL. This is the delivered order with no payment found in `schema.md`.

### D23. No statistical test at first (user; superseded by D25)
- **What happened:** The first results showed a gap between late and on-time customers.
- **Decision:** Report only descriptive numbers until the table definitions were settled.
- **Why:** Your choice. The comparison needed a proper test before drawing a conclusion, especially as only 98 customers with a late first order came back. The tests were run later, in D25–D30.

**Current result.** It uses the 2018-08-31 cutoff (D19) and the calendar-day late rule (D20).

| First order | Customers | Ordered again within 180 days | Repeat rate |
|---|---:|---:|---:|
| All | 56,387 | 1,612 | 2.86% |
| Late | 3,924 (6.96%) | 98 | 2.50% |
| On time | 52,463 | 1,514 | 2.89% |

---

## Working rule

### D24. Keep this log up to date (user)
- **Decision:** Update `decisions.md` after every step of the project, without being asked.
- **Why:** This keeps a full, auditable record of how the analysis was built.

---

## Statistical tests (`stats_test.py`)

### D25. Run the tests with Python's standard library only (Claude)
- **What happened:** You asked for the tests. scipy, statsmodels and pandas aren't installed. Only numpy is.
- **Decision:**
  - Write the tests in `stats_test.py` with the standard library only, like `load_data.py`. Nothing was installed.
  - Write the t-distribution calculation by hand.
  - Check it against known table values: t = 2.228 with 10 degrees of freedom gives p = 0.05, and t = 3.0 with 5 gives p = 0.0301. Both match.
- **Why:**
  - Anyone can run `python stats_test.py` without setting anything up.
  - The results don't depend on library versions.

### D26. Repeat rate: two-proportion z-test (user and Claude)
- **What happened:** The plan was to compare the repeat rate for late vs on-time first orders (you).
- **Decision:**
  - Use a two-sided test, with the difference measured as late minus on time.
  - The z statistic assumes both groups share one repeat rate (Claude).
  - The 95% confidence interval uses each group's own rate (Claude).
- **Why:**
  - The test asks how surprising the gap would be if the true rates were equal. That is exactly what a shared rate represents.
  - The confidence interval describes the true gap, so it shouldn't assume the gap is zero. This is the standard textbook pairing.
- **Result:**
  - Late customers came back at 2.50% and on-time customers at 2.89%, a difference of −0.39 points.
  - The 95% confidence interval runs from −0.90 to +0.12 points, with p = 0.159.
  - This is **not significant at 0.05**. The interval includes 0, so the data can't rule out "no difference".

### D27. Power analysis assumptions (Claude)
- **What happened:** You asked how many late-order customers we would need.
- **Decision:**
  - Assume the true rates are exactly the ones we observed (2.50% vs 2.89%).
  - Use a two-sided test at α = 0.05, and give the numbers for 80% and 90% power.
  - Show two group mixes:
    - Today's mix of 13.4 on-time customers per late customer.
    - Equal group sizes.
- **Why:**
  - 80% power is the usual standard.
  - Today's mix is what more Olist data would give us. Equal groups show the most efficient design.
- **Result:**
  - The power we actually had was **28%**, so the test was likely to miss a gap this size even if it is real.
  - For 80% power we would need **14,988 late customers** at today's mix. That is 3.8× what we have, and about 215,000 customers in total.
  - With equal groups we would need 27,256 customers in each group.

### D28. Review score: Welch t-test plus Mann-Whitney; customers with no review excluded (Claude)
- **What happened:** You asked to compare the average review score as a second check.
- **Decision:**
  - Use the Welch t-test, which allows the two groups to vary by different amounts. It does, with standard deviations of 1.54 vs 1.16.
  - Add a Mann-Whitney rank test, because scores are 1–5 ratings rather than true measurements.
  - Exclude the customers whose first order has no review: 93 late and 327 on-time.
- **Why:**
  - With very unequal groups, the plain t-test can give wrong p-values.
  - The two tests make different assumptions, so if both agree, the result doesn't depend on that choice.
  - There is no score to compare for customers without a review.
- **Result:**
  - Late orders average **2.17 stars** and on-time orders **4.27 stars**, a difference of −2.09 stars. The 95% confidence interval is −2.14 to −2.04.
  - Both tests give p < 1e-300.
  - 57% of late first orders got 1 star, against 7% of on-time ones.
- **How to read it:** Customers clearly *notice* and dislike late delivery. That hasn't yet shown up as a measurable drop in coming back. This test only confirms that lateness matters to customers. It isn't evidence about repeat buying.

### D29. Added a non-canceled repeat column for the sensitivity check (Claude)
- **What happened:** You asked to rerun test 1 counting only non-canceled orders as repeats.
- **Decision:**
  - Add `n_orders_180d_noncanceled` and `is_repeat_noncanceled` to `first_orders` in `analysis.sql`.
  - Exclude only status `canceled`. `unavailable` orders still count as repeats.
  - Leave `is_repeat` (D17) as the main definition.
- **Why:**
  - Keeping both columns in the table means the check can be reproduced from the SQL.
  - "Non-canceled" was your wording, so other statuses weren't excluded. Rebuilding the table didn't change any other numbers.

### D30. Sensitivity check result: conclusion unchanged (user)
- **What happened:** Only 7 customers had a canceled order as their only repeat, and all 7 had an on-time first order.
- **Decision:** Keep the conclusion from D26.
- **Why:**
  - Late customers came back at 2.50% and on-time customers at 2.87%, a difference of −0.38 points.
  - The 95% confidence interval runs from −0.88 to +0.13 points, with p = 0.173.
  - This is still not significant, so counting canceled orders as repeats (D17) doesn't drive the result.

**Statistical result so far.** Customers with a late first order came back about 13% less often, at 0.87× the on-time rate. That difference isn't statistically significant (p = 0.16), and the test only had 28% power. The data neither shows an effect nor rules out a real one this size. Customers do give late orders far worse reviews, at 2.2 vs 4.3 stars.

---

## Write-up (`README.md`)

### D31. A one-page README for a non-technical manager (user)
- **What happened:** You asked for the findings in plain English, on about one page.
- **Decision:**
  - Write `README.md` with five sections: question, data and method, results, limitations, recommendation.
  - Link the key decisions to this file.
  - Avoid statistical terms, apart from one p-value.
- **Why:** The reader needs the conclusion and what to do next, not the method.

### D32. No charts (user rule; matplotlib not installed)
- **What happened:** Your rule was to add two PNG charts only if matplotlib was available. It isn't installed.
- **Decision:** Skip the charts and don't install matplotlib. The README uses one summary table instead.
- **Why:** That was your stated rule. It also keeps the project standard-library only (D5, D25).

### D33. A/B test design in the recommendation (Claude)
- **What happened:** The README needed a simple experiment to measure the effect properly.
- **Decision:**
  - **What gets tested:** we can't make orders late on purpose, so the test randomizes a *recovery offer* instead. Half of the customers whose first order arrives late get an apology and a voucher, and the other half get normal service.
  - **What we measure:** coming back within 180 days, with an early read at 90 days.
  - **Group size:** 4,600 customers in each group, enough to detect a lift from 2.5% to 3.5% with 80% power at α = 0.05. This uses the same calculation as D27.
- **Why:**
  - **Why not test the delay itself:** making orders late on purpose would harm customers. A test that pads the promised delivery dates would only change a few orders' late status, so any effect would be too diluted to detect.
  - **Why this test:** a recovery offer is ethical, and it is a decision the team can actually act on.
  - **Why a 1-point lift:** detecting a 0.39-point gap would need about 27,000 customers in each group (D27). That isn't practical when there are about 500 late first orders a month.
  - **Where the monthly figure comes from:** it is the average from January to August 2018, from a count of late first orders per month.
- **Also found:** late first orders cluster in a few months: November 2017 (877) and February–March 2018 (890 and 1,293), against about 100–400 in most other months. The README mentions this as a limitation.
