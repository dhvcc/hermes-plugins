# Expense policy

Apply these rules to every receipt, in order of receipt id.

1. Convert to EUR with the rate for the receipt's month in `fx.csv` (EUR per unit). Round each approved
   amount to cents at the end.
2. Duplicates: a receipt with the same employee, date, vendor and amount as an earlier receipt (lower id) is a
   duplicate and gets 0.
3. Alcohol is never reimbursed.
4. Meals: at most 45.00 EUR per employee per calendar day in total. Fill the daily allowance in receipt id
   order; the receipt that crosses the limit is reimbursed partially, later ones that day get 0.
5. Taxis on Saturday or Sunday are reimbursed only if the receipt note mentions the airport.
6. Hotels: at most 160.00 EUR per night; the receipt states the number of nights.
7. Software is reimbursed only if the receipt carries an approval reference (`APR-...`).
8. Everything else is reimbursed in full.

Status per receipt: `approved` (full amount), `partial` (some), `rejected` (0, rules 3, 5, 6 or 7, or a meal
over the daily limit), `duplicate` (rule 2).
