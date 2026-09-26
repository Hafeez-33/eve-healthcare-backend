# EVE Healthcare — Backend Service

A backend service for diagnostic test bookings and simulated payments built with Python, FastAPI, and PostgreSQL.

> **Current Implementation Status:** Phase 7 Complete (Comprehensive Testing, Edge Cases & Security Hardening).  
> 113 automated tests passing against PostgreSQL with 100% state machine, security, and concurrency coverage.




---

## Technology Stack

- **Language:** Python 3.11+
- **Framework:** FastAPI
- **Database:** PostgreSQL 16
- **ORM:** SQLAlchemy 2.0
- **Database Migrations:** Alembic
- **Security & Auth:** PyJWT, bcrypt
- **Configuration & Validation:** Pydantic v2 / pydantic-settings
- **Testing:** Pytest & HTTPX
- **Server:** Uvicorn

---

## Prerequisites

- Python 3.11 or higher
- PostgreSQL 16
- Git

---

## Local Environment Setup

### 1. Clone & Navigate
```bash
git clone https://github.com/Hafeez-33/eve-healthcare-backend.git
cd eve-healthcare-backend
```

### 2. Create and Activate Virtual Environment
```bash
# Windows (PowerShell)
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Linux / macOS
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Configure Environment Variables
Copy the example environment configuration:
```bash
cp .env.example .env
```
Update `.env` with your local PostgreSQL connection string and secrets:
```env
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/eve_healthcare
SECRET_KEY=your-secure-random-secret-key-min-32-chars
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60
WEBHOOK_SECRET=optional-webhook-secret
PROJECT_NAME="EVE Healthcare API"
DEBUG=True
```

---

## Database Migrations & Seeding

### 1. Apply Alembic Migrations
Apply all schema migrations to create the six core tables:
```bash
alembic upgrade head
```

Verify current migration head:
```bash
alembic current
```

### 2. Seed Initial Centres & Tests (Optional / Development)
Populate realistic diagnostic centres and diagnostic tests:
```bash
python -m app.scripts.seed
```

---

## Running the Application

Start the development server with hot reload:
```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Once started:
- **Root Endpoint:** `http://127.0.0.1:8000/`
- **Health Check:** `http://127.0.0.1:8000/health`
- **Interactive OpenAPI Documentation:** `http://127.0.0.1:8000/docs`

---

## Currently Available Endpoints

| Method | Endpoint | Description | Auth Required |
|---|---|---|:---:|
| `GET` | `/` | Application root status message | No |
| `GET` | `/health` | Health check endpoint | No |
| `POST` | `/auth/signup` | User signup with bcrypt password hashing | No |
| `POST` | `/auth/login` | User login and signed JWT access token issuance | No |
| `GET` | `/centres/` | List diagnostic centres and offered tests | No |
| `GET` | `/centres/{id}` | Get single diagnostic centre details | No |
| `POST` | `/centres/` | Create a new diagnostic centre | Bearer JWT |
| `GET` | `/centres/{id}/tests` | List tests offered by a centre | No |
| `POST` | `/centres/{id}/tests` | Add diagnostic test with centre-specific pricing | Bearer JWT |
| `POST` | `/bookings/` | Book diagnostic test (historical price snapshot) | Bearer JWT |
| `GET` | `/bookings/` | List authenticated user's bookings | Bearer JWT |
| `GET` | `/bookings/{id}` | Get single booking details (ownership scoped) | Bearer JWT |
| `PATCH`| `/bookings/{id}/cancel` | Cancel a pending booking (ownership scoped) | Bearer JWT |
| `POST` | `/payments/` | Simulate payment for pending booking (atomic row lock) | Bearer JWT |
| `POST` | `/payments/webhook/` | Process provider webhook (atomic ON CONFLICT idempotency) | Public |
| `GET` | `/docs` | Interactive Swagger / OpenAPI documentation | No |


### Example cURL Requests


#### 1. User Signup
```bash
curl -X POST "http://127.0.0.1:8000/auth/signup" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "jane.doe@example.com",
    "password": "SecurePassword123!",
    "full_name": "Jane Doe"
  }'
```

#### 2. User Login
```bash
curl -X POST "http://127.0.0.1:8000/auth/login" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "jane.doe@example.com",
    "password": "SecurePassword123!"
  }'
```

#### 3. List Centres
```bash
curl -X GET "http://127.0.0.1:8000/centres/"
```

#### 4. Create Diagnostic Centre (Authenticated)
```bash
curl -X POST "http://127.0.0.1:8000/centres/" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <YOUR_ACCESS_TOKEN>" \
  -d '{
    "name": "Apollo Clinic",
    "location": "Koramangala, Bangalore",
    "contact_number": "+918025531234"
  }'
```

#### 5. Add Test to Centre (Authenticated)
```bash
curl -X POST "http://127.0.0.1:8000/centres/<CENTRE_ID>/tests" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <YOUR_ACCESS_TOKEN>" \
  -d '{
    "name": "Complete Blood Count (CBC)",
    "description": "Measures red/white blood cells and platelets",
    "price": "450.00"
  }'
```

#### 6. Create Diagnostic Test Booking (Authenticated)
```bash
curl -X POST "http://127.0.0.1:8000/bookings/" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <YOUR_ACCESS_TOKEN>" \
  -d '{
    "centre_id": "<CENTRE_ID>",
    "test_id": "<TEST_ID>",
    "appointment_datetime": "2026-10-15T10:30:00Z"
  }'
```

#### 7. List User's Bookings (Authenticated)
```bash
curl -X GET "http://127.0.0.1:8000/bookings/" \
  -H "Authorization: Bearer <YOUR_ACCESS_TOKEN>"
```

#### 8. Simulate Payment for Booking (Authenticated)
```bash
curl -X POST "http://127.0.0.1:8000/payments/" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <YOUR_ACCESS_TOKEN>" \
  -d '{
    "booking_id": "<BOOKING_ID>",
    "simulate_status": "SUCCESS"
  }'
```

#### 9. Simulate Payment Gateway Webhook (Provider Callback)
```bash
curl -X POST "http://127.0.0.1:8000/payments/webhook/" \
  -H "Content-Type: application/json" \
  -d '{
    "event_id": "evt_live_1234567890abcdef",
    "event_type": "payment.updated",
    "timestamp": "2026-09-26T10:07:00Z",
    "data": {
      "transaction_reference": "TXN_PG_987654321",
      "booking_id": "<BOOKING_ID>",
      "amount": "450.00",
      "status": "SUCCESS"
    }
  }'
```

---



## Running Tests

Execute the automated test suite with pytest:
```bash
pytest -v
```

---

## Project Structure (Phase 1 Foundation)

```
eve-healthcare-backend/
├── .env.example            # Example configuration template
├── .gitignore              # Standard gitignore (secrets, venv, cache)
├── alembic.ini             # Alembic migration configuration
├── alembic/                # Migration scripts and environment
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
├── app/
│   ├── __init__.py
│   ├── main.py             # FastAPI entrypoint & health endpoints
│   ├── api/                # API router and dependencies
│   │   ├── __init__.py
│   │   └── deps.py         # DB session dependency
│   ├── core/               # Configuration and database connectivity
│   │   ├── __init__.py
│   │   ├── config.py       # Pydantic Settings
│   │   └── database.py     # SQLAlchemy 2.0 engine & sessionmaker
│   ├── models/             # SQLAlchemy ORM models (Phase 2+)
│   │   └── __init__.py
│   ├── schemas/            # Pydantic request/response schemas (Phase 3+)
│   │   └── __init__.py
│   └── services/           # Business logic & services (Phase 3+)
│       └── __init__.py
├── PLAN.md                 # Complete assessment blueprint & source of truth
├── README.md               # Project documentation
├── requirements.txt        # Pinned dependency ranges
└── tests/                  # Test suite
    ├── __init__.py
    └── test_health.py      # App import and health endpoint tests
```
