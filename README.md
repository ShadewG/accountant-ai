# AccountantAI

An AI-powered accounting automation system that integrates Gmail, Folio.no, and Fiken to automatically process receipts and manage accounting entries.

## Features

- **Automatic Receipt Collection**: Extracts receipts from Gmail emails
- **Manual Upload**: Support for manual receipt upload
- **AI Analysis**: Uses OpenAI GPT-4 Vision to analyze and extract data from receipts
- **Payment Matching**: Automatically matches bank transactions from Folio.no to receipts
- **Accounting Automation**: Creates entries in Fiken accounting system
- **Norwegian Support**: Special handling for Norwegian receipts and VAT

## Architecture

```
Gmail → Receipt Processor → OpenAI Analysis → Data Mapper → Fiken
                 ↑                                ↑
          Manual Upload                    Folio.no Transactions
```

## Setup

### Prerequisites

- Python 3.9+
- PostgreSQL database
- Redis (for task queue)
- API credentials for:
  - Gmail API
  - OpenAI API
  - Folio.no (session cookie and org number)
  - Fiken API

### Installation

1. Clone the repository:
```bash
cd accountant-ai
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Copy and configure environment variables:
```bash
cp .env.example .env
# Edit .env with your credentials
```

4. Initialize the database:
```bash
alembic upgrade head
```

5. Run the application:
```bash
uvicorn src.api.main:app --reload
```

## API Endpoints

### Authentication
- `GET /auth/gmail` - Start Gmail OAuth flow
- `GET /auth/fiken` - Start Fiken OAuth flow

### Receipts
- `POST /receipts/upload` - Upload receipt manually
- `GET /receipts` - List receipts
- `GET /receipts/{id}` - Get receipt details
- `POST /receipts/sync-email` - Sync receipts from Gmail

### Payments & Expenses
- `POST /payments/sync` - Sync payments from Folio.no
- `GET /payments` - List payments
- `POST /expenses/sync` - Sync expenses from Folio.no
- `POST /expenses/match-receipts` - Match expenses to receipts
- `GET /expenses/unmatched` - List unmatched expenses

### Matching
- `POST /match/auto` - Auto-match payments to receipts
- `POST /match/manual` - Manually match payment to receipt

### Accounting
- `POST /accounting/sync/{receipt_id}` - Sync receipt to Fiken
- `POST /accounting/sync-all` - Sync all matched receipts
- `GET /accounting/entries` - List accounting entries

### System
- `GET /status` - Get system status
- `GET /health` - Health check

## Configuration

### Gmail Setup
1. Create a Google Cloud project
2. Enable Gmail API
3. Create OAuth2 credentials
4. Add redirect URI: `http://localhost:8000/auth/gmail/callback`

### Fiken Setup
1. Register your application with Fiken
2. Get client ID and secret
3. Enable API and Project modules in Fiken

### Folio.no Setup
1. Log in to your Folio.no account
2. Get your session cookie from browser developer tools
3. Use your Norwegian organization number
4. See `docs/FOLIO_SETUP.md` for detailed instructions

## Usage

1. **Connect Services**: Visit `/auth/gmail` and `/auth/fiken` to authenticate

2. **Process Receipts**:
   - Automatic: Run `/receipts/sync-email` to fetch from Gmail
   - Manual: Upload via `/receipts/upload`

3. **Sync Transactions**: 
   - Run `/payments/sync` to fetch payments from Folio.no
   - Run `/expenses/sync` to fetch expenses from Folio.no

4. **Match & Sync**: 
   - Run `/match/auto` to match payments to receipts
   - Run `/accounting/sync-all` to create entries in Fiken

## Development

### Project Structure
```
accountant-ai/
├── src/
│   ├── api/          # FastAPI endpoints
│   ├── services/     # Service integrations
│   ├── models/       # Database models
│   ├── config/       # Configuration
│   └── utils/        # Utilities
├── tests/            # Test files
├── docs/             # Documentation
└── scripts/          # Utility scripts
```

### Testing
```bash
pytest tests/
```

### Code Style
```bash
black src/
flake8 src/
mypy src/
```

## Security

- All credentials stored securely in environment variables
- OAuth tokens encrypted in database
- File uploads validated and sanitized
- API authentication required for all endpoints

## License

MIT