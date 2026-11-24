# Do late deliveries stop customers coming back?

A study of 56,387 first-time customers of Olist, a Brazilian online marketplace, using orders placed from 2016 to 2018.

## 1. The question

When a customer's **first order arrives late**, are they less likely to buy from us again?

## 2. Data and method

We used Olist's public order data: orders, customers, items, payments and reviews. For each customer we took their **first order** and checked two things:

- **Was it late?** It counts as late if it arrived on a later day than the date we promised. Arriving on the promised day counts as on time.
- **Did they come back?** We checked whether they placed another order within **180 days**. We only included customers we could follow for the full 180 days, so everyone had the same chance to return.

The key choices behind these numbers are logged in [decisions.md](decisions.md):
- We identify a person by Olist's customer ID for individuals, not the per-order ID.
- Only customers whose first order was delivered are included.
- The data effectively ends on 31 August 2018.
- A cancelled later order still counts as coming back. We checked that this doesn't change the result (see section 3).

## 3. Results

| First order | Customers | Came back within 180 days | Average review |
|---|---:|---:|---:|
| On time | 52,463 | **2.89%** | **4.3 stars** |
| Late | 3,924 (7%) | **2.50%** | **2.2 stars** |

**Repeat buying: slightly lower after a late order, but not proven.** Customers whose first order was late came back about 13% less often. However, a gap this size could easily be chance, and the statistics say "not significant" (p = 0.16).

Our data also didn't have enough late-order customers to settle the question. If the gap is real, a study of this size would miss it about 7 times out of 10. To detect it reliably we would need about 4 times as many late-order customers.

**Reviews: a large, clear drop.** Late orders average **2.2 stars**, against 4.3 for on-time orders. **57% of late orders get a 1-star review**, compared with 7% of on-time ones. This difference is far too large to be chance. Customers clearly notice and dislike late deliveries.

**Sensitivity check.** We reran the analysis counting only orders that were not cancelled as "coming back". The result barely moved (2.50% vs 2.87%) and is still not significant, so the conclusion stands.

## 4. Limitations

- **This shows a link, not cause and effect.** We observed what happened; we didn't run an experiment. Something else could explain both late delivery and lower repeat buying.
- **Late orders may be different orders.** Lateness may be more common in some regions, product types or sellers. Those customers might return less anyway. We haven't adjusted for this yet.
- **Lateness comes in waves.** Late deliveries cluster in a few months, such as the November 2017 Black Friday peak and February–March 2018. Customers who bought in those months may differ in other ways too.
- **Very few customers come back at all.** Only about 3% of customers order again within 180 days, late or not. A small number of repeat buyers makes small differences hard to measure.

## 5. Recommendation

1. **Treat late delivery as a customer-experience problem now.** The effect on reviews is large and certain. Bad reviews are visible to every future shopper, whatever happens to repeat buying.
2. **Don't claim late delivery costs us repeat customers, yet.** The data points that way but doesn't prove it.
3. **Check whether region, product type or seller explains the gap.** This is a cheap next step with the data we already have.
4. **Run an A/B test to measure the effect properly.** We can't deliberately make orders late, but we can test whether fixing the experience brings customers back:
   - **Who:** every customer whose first order arrives late.
   - **Random split:** half get an apology and a voucher for their next order (for example, R$20 off, valid for 180 days). The other half get our normal service.
   - **What we measure:** the share who place another order within 180 days. A useful early read is at 90 days.
   - **How big:** to detect a lift from 2.5% to 3.5%, we need about **4,600 customers in each group** (about 9,100 late first orders). At 2018 volumes of about 500 late first orders a month, that is about 18 months of sign-up plus 6 months of follow-up. A larger expected lift, around 1.4 points, needs about half the customers.
   - **Decision rule:** if the voucher group comes back clearly more often, and the extra sales cover the voucher cost, offer it to every late-delivery customer.

*Files: `load_data.py` builds the database, `schema.md` describes the tables, `analysis.sql` builds the analysis table, `stats_test.py` runs the tests, and `decisions.md` logs every decision.*
