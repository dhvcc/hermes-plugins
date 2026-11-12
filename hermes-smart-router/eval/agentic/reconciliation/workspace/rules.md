# Reconciliation rules

- Match bank transactions to invoices by the invoice number in the reference. References are typed by hand:
  expect lower case, missing dashes, `O` instead of `0`, and several invoice numbers in one payment.
- A payment that names several invoices pays them in the order listed, each in full until the money runs out.
- A payment without a usable reference belongs to an invoice of the same client with exactly that open amount.
- Banks may deduct a transfer fee: if the open amount of an invoice is 2.00 EUR or less after a payment, the
  invoice counts as paid.
- Ignore transactions that are not client payments (rent, salaries, card fees, refunds we sent).

Status: `paid`, `partial` (something received, more than 2.00 EUR still open) or `unpaid`.
