# Folio.no Setup Guide

Folio.no is a Norwegian business banking service that provides transaction data through a GraphQL API.

## Getting Your Folio Credentials

### 1. Get Your Session Cookie

1. Log in to your Folio account at https://app.folio.no
2. Open your browser's Developer Tools (F12)
3. Go to the Network tab
4. Refresh the page
5. Look for any request to `app.folio.no`
6. In the request headers, find the `Cookie` header
7. Copy the value after `folioSession=` (this is your session cookie)

### 2. Get Your Organization Number

Your organization number (org number) is your Norwegian business registration number.

## Configure AccountantAI

Add these values to your `.env` file:

```env
# Folio.no API
FOLIO_SESSION_COOKIE=your-session-cookie-here
FOLIO_ORG_NUMBER=your-org-number-here
```

## API Features

The Folio integration provides:

1. **Transaction Sync**: Fetches booked activities (transactions) from your Folio accounts
2. **Payment Detection**: Identifies incoming payments to your accounts
3. **Expense Tracking**: Tracks outgoing payments (expenses)
4. **Category Extraction**: Preserves Folio's accounting categories
5. **Account Information**: Can fetch account balances and details

## Available Endpoints

- `POST /payments/sync` - Sync incoming payments from Folio
- `POST /expenses/sync` - Sync expense transactions from Folio
- `POST /expenses/match-receipts` - Match Folio expenses to uploaded receipts
- `GET /expenses/unmatched` - View expenses without matched receipts
- `POST /expenses/auto-categorize` - Use AI to categorize expenses

## Transaction Matching

The system matches Folio transactions to receipts based on:
- **Amount**: Exact or close match (within 2%)
- **Date**: Transaction date vs invoice date (closer dates = higher confidence)
- **Merchant**: Name matching between Folio merchant and receipt vendor
- **AI Verification**: Additional AI analysis for complex matches

## Important Notes

1. **Session Expiry**: The Folio session cookie may expire. You'll need to refresh it periodically.
2. **Date Ranges**: The API fetches transactions within specified date ranges to avoid overloading.
3. **Norwegian Focus**: Folio is designed for Norwegian businesses, so all amounts are in NOK.

## Troubleshooting

### Connection Failed
- Verify your session cookie is still valid
- Check your organization number is correct
- Ensure you're using the correct format (no spaces or special characters)

### No Transactions Found
- Check the date range in your queries
- Verify you have transactions in the specified period
- Ensure your Folio account has the necessary permissions