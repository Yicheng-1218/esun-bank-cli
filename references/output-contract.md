# Output Contract v3

## Envelope

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
