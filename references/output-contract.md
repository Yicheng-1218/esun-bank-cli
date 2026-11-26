# Output Contract v3

## Envelope

v4 CLI retains schema version 3.0 for normalized transactions and adds
optional issued-statement/installment results. Successful CLI responses
also include `request`:

```json
{"transport":"httpx","mode":"local_cache","bank_logins":0}
```

`mode` is `bank_live` (one login) or `local_cache` (zero logins).
When requested, `statements` and/or `installments` are included,
along with `statement_coverage`. The latter records the requested
statement-month count, not proof of complete data. Pending/unbilled
transactions are excluded. `installments.active` is based on explicit
remaining amounts in the latest issued statement; missing evidence
must not be interpreted as a zero balance.

Every command returns:

```json
{
  "schema_version": "3.0",
  "period": {"start": "YYYY-MM-DD", "end": "YYYY-MM-DD"},
  "requested_sources": [],
  "accounts": [],
  "transactions": [],
  "summary": {}
}
```

## Transaction

All sources share exactly these top-level fields:

```json
{
  "source": "credit_card | debit_card | twd_account",
  "date": "YYYY-MM-DD | null",
  "account_id": "masked string | null",
  "description": "string | null",
  "amount": {"value": "decimal string | null", "currency": "string | null"},
  "original_amount": {"value": "decimal string | null", "currency": "string | null"},
  "direction": "debit | credit | null",
  "direction_raw": "source value | null",
  "status": "string | null",
  "balance_after": {"value": "decimal string | null", "currency": "string | null"},
  "counterparty": {"bank_code": "string | null", "account_id": "masked string | null"},
  "metadata": {}
}
```

Non-applicable nested objects may be null.

Money never uses floating-point JSON numbers. Values are canonical decimal strings.

## Accounts

Each account in `accounts[]` has `source`, `kind`, `account_id`, `label`, and `is_primary` fields. The `account_id` is masked, and `is_primary` may be null for TWD accounts.

## Period / missing dates

`period` is a rolling calendar-month interval ending on the execution date (inclusive), not a fixed 30-day window. Transactions with parsed dates outside the interval are excluded; records with an unparseable date are retained with `date: null`. Callers must not assume these undated records are confirmed to be within the interval.
