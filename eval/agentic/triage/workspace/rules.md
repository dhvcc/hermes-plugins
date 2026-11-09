# Triage rules (we are Northwind Studio, domain northwind.studio)

For every email in ./mail decide one action:

- `pay`: an invoice or payment request addressed to us from a known supplier (see suppliers.csv). Due date = the
  due date in the email.
- `reply`: a client (see clients.csv) asks a question or requests something. Due date = 2 business days after the
  email date (Mon-Fri), unless the client states an earlier deadline, which then wins.
- `schedule`: someone proposes a meeting time. Due date = the proposed meeting date.
- `report`: a payment request or "updated bank details" email from a sender that is not a known supplier or client.
  Due date = the email date.
- `ignore`: newsletters, notifications and everything else. No due date.

Write triage.csv with columns file,action,due (YYYY-MM-DD, empty for ignore).
