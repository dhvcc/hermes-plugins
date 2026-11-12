# Metric definitions

- Price list: `plans.json`. Annual plans are billed yearly at the yearly price; their MRR is yearly price / 12.
- A subscription counts on a month-end date if it started on or before that date and has not ended by then
  (an `ended` date on or before the month end means it no longer counts).
- MRR at month end: sum of the MRR of every counting subscription, after its discount (`discount_pct`).
- Churned customers in a month: customers with at least one subscription ending in that month and no
  subscription counting at that month end.
- Report MRR rounded to cents.
