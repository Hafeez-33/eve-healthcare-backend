# EVE Healthcare — Backend API

Production-ready backend service for diagnostic centre discovery, appointment bookings, and payment processing built with Python, FastAPI, SQLAlchemy 2.0, Alembic, and PostgreSQL 16.

---

## Table of Contents

- [Project Overview](#project-overview)
- [Architecture](#architecture)
- [Technology Stack](#technology-stack)
- [Repository Structure](#repository-structure)
- [Environment Variables](#environment-variables)
- [Local Setup](#local-setup)
- [PostgreSQL Setup](#postgresql-setup)
- [Alembic Migrations](#alembic-migrations)
- [Seed Data](#seed-data)
- [Running the FastAPI Application](#running-the-fastapi-application)
- [Running Tests](#running-tests)
- [Docker Compose Setup](#docker-compose-setup)
- [Swagger / OpenAPI Documentation](#swagger--openapi-documentation)
- [Main API Endpoints](#main-api-endpoints)
- [Authentication](#authentication)
- [Booking State Machine](#booking-state-machine)
- [Payment & Webhook Behavior](#payment--webhook-behavior)
- [Webhook Idempotency & Concurrency](#webhook-idempotency--concurrency)

---

## Project Overview

The **EVE Healthcare Backend API** provides a diagnostic appointment management and payment processing platform. Key capabilities include:

- **User Authentication**: Secure user registration, password hashing with `bcrypt`, and stateless JWT access token authentication.
- **Diagnostic Centres & Tests Catalogue**: Browsing diagnostic centres, centre-specific test listings, and adding diagnostic tests to centres as an authenticated user.
- **Booking Management**: Appointment booking with historical price snapshotting to guarantee immutable billing values even if catalogue prices change later.
- **Strict Booking State Machine**: Controlled transitions (`PENDING` -> `CONFIRMED`, `FAILED`, or `CANCELLED`) with rigid enforcement against illegal transitions from terminal states.
- **Simulated Payment Gateway**: Direct payment simulation and external webhook processing.
- **Webhook Idempotency & Concurrency Protection**: Atomic `INSERT ... ON CONFLICT DO NOTHING` combined with PostgreSQL row-level locking (`SELECT ... FOR UPDATE`) to guarantee safe concurrent webhook processing without double-confirmation or duplicate records.

---

## Architecture

The application adopts a clean, layered architecture:

```
[ HTTP Requests ]
       │
       ▼
[ FastAPI Routers ] (app/api/v1/)
       │ Validates request DTOs / Schemas & extracts JWT identity
       ▼
[ Service Layer ] (app/services/)
       │ Enforces business rules, state machine, and transaction boundaries
       ▼
[ SQLAlchemy 2.0 ORM ] (app/models/)
       │ Maps Python entities to relational schema with explicit constraints
       ▼
[ PostgreSQL 16 Engine ] (app/core/database.py)
       Atomic transactions, unique constraints, foreign keys, and row-level locks
```

### Architectural Highlights
- **Thin Controllers / Routers**: Routers are focused strictly on HTTP handling, status codes, dependency injection, and schema translation.
- **Isolated Service Layer**: Business logic (state transitions, payment handling, and ownership verification) resides in pure service functions.
- **Declarative Database Constraints**: Data integrity is enforced at the database level through unique indexes, check constraints (`CHECK (price > 0)`), and foreign key restrict rules.
- **Pessimistic Locking**: `SELECT ... FOR UPDATE` serializes state transitions on bookings under concurrent operations.

---

## Technology Stack

- **Language**: Python 3.12+ (3.11+ supported)
- **Web Framework**: FastAPI 0.111+
- **ASGI Server**: Uvicorn 0.30+
- **Database Engine**: PostgreSQL 16
- **Database Driver**: `psycopg` (psycopg 3 binary)
- **ORM**: SQLAlchemy 2.0
- **Database Migrations**: Alembic 1.13+
- **Data Validation & Settings**: Pydantic v2 & `pydantic-settings`
- **Security & Tokens**: `bcrypt` & `PyJWT`
- **Automated Testing**: `pytest` 8.2+ & `httpx` (113 test cases)
- **Containerization**: Docker & Docker Compose v2

---

## Repository Structure

```
eve-healthcare-backend/
├── .dockerignore            # Docker build context exclusions
├── .env.example            # Environment variable template
├── .gitignore              # Git ignore rules (secrets, venv, pycache)
├── Dockerfile              # Production Python 3.12 slim container
├── docker-compose.yml      # Multi-container setup (PostgreSQL 16 + FastAPI)
├── requirements.txt        # Pinned Python package dependencies
├── alembic.ini             # Alembic configuration file
├── alembic/                # Database migrations
│   ├── env.py              # Migration environment (loads app.models and settings)
│   ├── script.py.mako      # Migration script template
│   └── versions/           # Migration revisions
│       └── 60e99a34f6de_create_initial_schema.py
├── app/                    # Application source code
│   ├── __init__.py
│   ├── main.py             # FastAPI entrypoint, router mounting, healthcheck
│   ├── api/
│   │   ├── __init__.py
│   │   ├── deps.py         # DB session & JWT authentication dependencies
│   │   └── v1/
│   │       ├── __init__.py
│   │       ├── auth.py     # Signup & login routes
│   │       ├── bookings.py # Booking creation, listing, cancellation routes
│   │       ├── centres.py  # Diagnostic centres and tests routes
│   │       └── payments.py # Payment simulation & webhook routes
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py       # Pydantic Settings configuration
│   │   ├── database.py     # SQLAlchemy engine & SessionLocal
│   │   └── security.py     # Password hashing & JWT helpers
│   ├── models/             # SQLAlchemy ORM models
│   │   ├── __init__.py
│   │   ├── base.py         # Declarative Base
│   │   ├── booking.py      # Booking model
│   │   ├── diagnostic_centre.py # DiagnosticCentre model
│   │   ├── diagnostic_test.py   # DiagnosticTest model
│   │   ├── enums.py        # BookingStatus & PaymentStatus enums
│   │   ├── payment.py      # Payment model
│   │   ├── user.py         # User model
│   │   └── webhook_event.py# WebhookEvent model
│   ├── schemas/            # Pydantic request/response schemas
│   │   ├── __init__.py
│   │   ├── auth.py
│   │   ├── booking.py
│   │   ├── diagnostic_centre.py
│   │   ├── diagnostic_test.py
│   │   └── payment.py
│   ├── scripts/
│   │   ├── __init__.py
│   │   └── seed.py         # Idempotent database seeder
│   └── services/           # Core domain services
│       ├── __init__.py
│       ├── auth_service.py
│       ├── booking_service.py
│       ├── centre_service.py
│       └── payment_service.py
└── tests/                  # Automated test suite (113 tests)
    ├── __init__.py
    ├── conftest.py         # Test fixtures & database isolation
    ├── test_auth.py        # Auth & JWT tests
    ├── test_bookings.py    # Booking & state machine tests
    ├── test_centres.py     # Centres & tests catalog tests
    ├── test_database_models.py # Model constraint tests
    ├── test_hardening_and_edge_cases.py # Security & boundary tests
    ├── test_health.py      # Root & health endpoint tests
    ├── test_payments.py    # Payment simulation tests
    └── test_webhook_idempotency.py # Webhook idempotency & concurrency tests
```

---

## Environment Variables

The application is configured using environment variables loaded via Pydantic Settings (`app/core/config.py`).

| Variable | Description | Default / Example (Local) | Example (Docker Compose) |
|---|---|---|---|
| `DATABASE_URL` | PostgreSQL connection URL | `postgresql://postgres:postgres@localhost:5432/eve_healthcare` | `postgresql://postgres:postgres@db:5432/eve_healthcare` |
| `POSTGRES_USER` | PostgreSQL user (Docker container) | `postgres` | `postgres` |
| `POSTGRES_PASSWORD` | PostgreSQL password (Docker container) | `postgres` | `postgres` |
| `POSTGRES_DB` | PostgreSQL database name | `eve_healthcare` | `eve_healthcare` |
| `SECRET_KEY` | Secret key for signing JWT tokens | *min 32-character secure string* | *min 32-character secure string* |
| `JWT_ALGORITHM` | JWT cryptographic algorithm | `HS256` | `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | JWT token validity duration | `60` | `60` |
| `WEBHOOK_SECRET` | Optional provider webhook secret | `None` | `None` |
| `PROJECT_NAME` | OpenAPI and app project title | `"EVE Healthcare API"` | `"EVE Healthcare API"` |
| `DEBUG` | FastAPI debug mode flag | `False` | `False` |

---

## Local Setup

### 1. Clone the Repository
```bash
git clone https://github.com/Hafeez-33/eve-healthcare-backend.git
cd eve-healthcare-backend
```

### 2. Create and Activate Virtual Environment
```bash
# On Linux/macOS:
python3 -m venv .venv
source .venv/bin/activate

# On Windows (PowerShell):
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 3. Install Dependencies
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Configure Environment
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
Ensure `DATABASE_URL` in `.env` matches your local PostgreSQL credentials:
```env
DATABASE_URL=postgresql://postgres:yourpassword@localhost:5432/eve_healthcare
```

---

## PostgreSQL Setup

Ensure PostgreSQL 16 is installed and running locally, then create the database:
```sql
CREATE DATABASE eve_healthcare;
```

---

## Alembic Migrations

The database schema is managed exclusively through Alembic migrations.

### Apply Migrations
```bash
alembic upgrade head
```

### Check Migration Status
```bash
alembic current
```

---

## Seed Data

An idempotent seed script is provided to populate initial diagnostic centres and test catalogues.

```bash
python -m app.scripts.seed
```

### Idempotency Behavior
- Checks for existing centres by `name` before inserting.
- Checks for existing tests by `(centre_id, name)` before inserting.
- Can be safely executed multiple times without generating duplicate records.
- Does not seed dummy users, bookings, or payments.

---

## Running the FastAPI Application

Start the Uvicorn ASGI server:
```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Once running:
- **Root Status**: `http://127.0.0.1:8000/`
- **Health Check**: `http://127.0.0.1:8000/health`
- **Interactive Swagger Docs**: `http://127.0.0.1:8000/docs`
- **ReDoc Documentation**: `http://127.0.0.1:8000/redoc`

---

## Running Tests

Run the complete automated test suite using `pytest`:
```bash
pytest -v
```

The test suite runs against the configured PostgreSQL database and includes **113 passing tests** verifying:
- Authentication & JWT validation (`tests/test_auth.py`)
- Diagnostic centre & test catalog CRUD (`tests/test_centres.py`)
- Booking creation, listing, ownership, and price snapshotting (`tests/test_bookings.py`)
- Database models, constraints, and relationships (`tests/test_database_models.py`)
- Payment simulation & transaction references (`tests/test_payments.py`)
- Webhook idempotency, payload validation, and concurrent deliveries (`tests/test_webhook_idempotency.py`)
- Security boundaries, token tampering, and edge cases (`tests/test_hardening_and_edge_cases.py`)

---

## Docker Compose Setup

A clean, production-oriented multi-container setup is defined in `docker-compose.yml`:
- **`db`**: Official PostgreSQL 16 (`postgres:16-alpine`) with persistent volume `postgres_data` and built-in healthcheck (`pg_isready -U postgres -d eve_healthcare`).
- **`web`**: Python 3.12 slim application container waiting for `db` to become healthy before starting.

### 1. Build and Start Containers
```bash
docker compose up -d --build
```

### 2. Verify Container Status & Health
```bash
docker compose ps
```
The `eve_healthcare_db` container will show `(healthy)` and `eve_healthcare_web` will be `Up`.

### 3. Apply Alembic Migrations inside Container
```bash
docker compose exec web alembic upgrade head
```

### 4. Seed Initial Catalog Data
```bash
docker compose exec web python -m app.scripts.seed
```

### 5. Access the API
- API: `http://localhost:8000/`
- Interactive Swagger UI: `http://localhost:8000/docs`

### 6. Stop Containers
```bash
# Stop containers while preserving database volume
docker compose down

# Stop containers and remove persistent volume (clean reset)
docker compose down -v
```

---

## Swagger / OpenAPI Documentation

FastAPI automatically generates an OpenAPI 3.1.0 specification available at:
- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`
- **Raw OpenAPI JSON**: `http://localhost:8000/openapi.json`

### OpenAPI Verification
- **Bearer Security Scheme**: All protected endpoints (`/centres/` POST, `/centres/{id}/tests` POST, `/bookings/` routes, `/payments/` POST) explicitly declare the `HTTPBearer` security requirement.
- **Public Webhook Route**: `/payments/webhook/` is explicitly marked as public (`security: None`), allowing external payment provider callbacks without JWT tokens.
- **Privacy & Security**: Internal attributes like `password` and `hashed_password` are excluded from all response schemas (`UserResponse`, etc.).

---

## Main API Endpoints

| Method | Endpoint | Description | Auth |
|---|---|---|:---:|
| `GET` | `/` | Application status and running information | None |
| `GET` | `/health` | Application health check endpoint | None |
| `POST` | `/auth/signup` | Register a new user with bcrypt password hashing | None |
| `POST` | `/auth/login` | Authenticate user and issue signed JWT access token | None |
| `GET` | `/centres/` | List all diagnostic centres (with pagination) | None |
| `GET` | `/centres/{id}` | Retrieve details of a specific diagnostic centre | None |
| `POST` | `/centres/` | Register a new diagnostic centre | Bearer JWT |
| `GET` | `/centres/{id}/tests` | List all active diagnostic tests offered by a centre | None |
| `POST` | `/centres/{id}/tests` | Add a diagnostic test to a centre with pricing | Bearer JWT |
| `POST` | `/bookings/` | Book a test at a centre (captures price snapshot) | Bearer JWT |
| `GET` | `/bookings/` | List bookings belonging to the authenticated user | Bearer JWT |
| `GET` | `/bookings/{id}` | Retrieve single booking details (ownership scoped) | Bearer JWT |
| `PATCH`| `/bookings/{id}/cancel` | Cancel a pending booking (ownership scoped) | Bearer JWT |
| `POST` | `/payments/` | Simulate direct payment for a pending booking | Bearer JWT |
| `POST` | `/payments/webhook/` | Process payment provider webhook (atomic & idempotent) | None (Public) |

---

### End-to-End Walkthrough via cURL

#### 1. User Signup
```bash
curl -X POST "http://localhost:8000/auth/signup" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "sarah.connor@example.com",
    "password": "SecurePassword123!",
    "full_name": "Sarah Connor"
  }'
```

#### 2. User Login
```bash
curl -X POST "http://localhost:8000/auth/login" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "sarah.connor@example.com",
    "password": "SecurePassword123!"
  }'
```
Response:
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

#### 3. List Diagnostic Centres
```bash
curl -X GET "http://localhost:8000/centres/"
```

#### 4. Add a Diagnostic Centre (Authenticated)
```bash
curl -X POST "http://localhost:8000/centres/" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <TOKEN>" \
  -d '{
    "name": "Eve Diagnostics North",
    "location": "Hebbal, Bangalore",
    "contact_number": "+919876543212"
  }'
```

#### 5. Add a Diagnostic Test to Centre (Authenticated)
```bash
curl -X POST "http://localhost:8000/centres/<CENTRE_ID>/tests" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <TOKEN>" \
  -d '{
    "name": "Comprehensive Metabolic Panel (CMP)",
    "description": "Evaluation of organ function and glucose levels",
    "price": "650.00"
  }'
```

#### 6. Create a Booking (Authenticated)
```bash
curl -X POST "http://localhost:8000/bookings/" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <TOKEN>" \
  -d '{
    "centre_id": "<CENTRE_ID>",
    "test_id": "<TEST_ID>",
    "appointment_datetime": "2026-10-25T14:30:00Z"
  }'
```
Response:
```json
{
  "id": "7b8e192a-...",
  "user_id": "3c9a101b-...",
  "centre_id": "<CENTRE_ID>",
  "test_id": "<TEST_ID>",
  "appointment_datetime": "2026-10-25T14:30:00Z",
  "amount": "650.00",
  "status": "PENDING",
  "created_at": "...",
  "updated_at": "..."
}
```

#### 7. Retrieve User's Bookings
```bash
curl -X GET "http://localhost:8000/bookings/" \
  -H "Authorization: Bearer <TOKEN>"
```

#### 8. Cancel a Pending Booking
```bash
curl -X PATCH "http://localhost:8000/bookings/<BOOKING_ID>/cancel" \
  -H "Authorization: Bearer <TOKEN>"
```

#### 9. Simulate Direct Payment
```bash
curl -X POST "http://localhost:8000/payments/" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <TOKEN>" \
  -d '{
    "booking_id": "<BOOKING_ID>",
    "simulate_status": "SUCCESS"
  }'
```

#### 10. Process Payment Webhook Callback
```bash
curl -X POST "http://localhost:8000/payments/webhook/" \
  -H "Content-Type: application/json" \
  -d '{
    "event_id": "evt_live_89104810239",
    "event_type": "payment.updated",
    "timestamp": "2026-09-26T12:00:00Z",
    "data": {
      "transaction_reference": "TXN_PG_7810239102",
      "booking_id": "<BOOKING_ID>",
      "amount": "650.00",
      "status": "SUCCESS"
    }
  }'
```

---

## Authentication

- **Scheme**: Standard HTTP Bearer Token (`Authorization: Bearer <access_token>`).
- **Algorithm**: HMAC-SHA256 (`HS256`) signed with `SECRET_KEY`.
- **Claims**: The JWT payload contains the `sub` claim encoding the user's UUID and `exp` defining token expiration.
- **Password Storage**: Passwords are never stored in plaintext. They are hashed using `bcrypt` with automatic salting.
- **Ownership Scope**: Bookings and payments strictly enforce ownership. A user accessing another user's booking receives `403 Forbidden` without leaking the target resource's existence or details.

---

## Booking State Machine

The booking lifecycle follows a strictly enforced state machine:

```
                  ┌───────────────┐
                  │    PENDING    │
                  └───────┬───────┘
          ┌───────────────┼───────────────┐
          │ (payment ok)  │ (fail)        │ (cancel)
          ▼               ▼               ▼
   ┌─────────────┐ ┌─────────────┐ ┌─────────────┐
   │  CONFIRMED  │ │   FAILED    │ │  CANCELLED  │
   │  (terminal) │ │  (terminal) │ │  (terminal) │
   └─────────────┘ └─────────────┘ └─────────────┘
```

### State Transition Invariants
1. **Initial State**: Every created booking starts in `PENDING` status.
2. **Allowed Transitions**:
   - `PENDING` $\rightarrow$ `CONFIRMED`: Upon successful payment simulation or valid `SUCCESS` payment webhook.
   - `PENDING` $\rightarrow$ `FAILED`: Upon failed payment simulation or valid `FAILED` payment webhook.
   - `PENDING` $\rightarrow$ `CANCELLED`: Upon explicit cancellation request by the booking owner.
3. **Terminal States**:
   - `CONFIRMED`, `FAILED`, and `CANCELLED` are immutable terminal states.
   - Any attempt to transition a booking out of a terminal state is rejected with `409 Conflict`.
   - Cancellation is rejected on `CONFIRMED`, `FAILED`, or `CANCELLED` bookings (`409 Conflict`).
   - Payment creation is rejected on `CONFIRMED`, `FAILED`, or `CANCELLED` bookings (`409 Conflict`).
4. **Historical Price Snapshot**:
   - The booking's `amount` is snapshotted from `DiagnosticTest.price` at the exact moment of booking creation.
   - Subsequent price updates to the test in the catalogue have zero effect on existing bookings.

---

## Payment & Webhook Behavior

- **Amount Integrity**: Payment amount is strictly derived from the booking's snapshot `amount`. The client cannot specify an arbitrary amount.
- **Transaction References**: Every payment transaction reference is unique and enforced by a database unique constraint.
- **Amount Mismatch Protection**: In webhook processing, if the webhook payload amount differs from the booking's snapshot amount, the request is rejected with `400 Bad Request` (`AMOUNT_MISMATCH`), and the booking remains in its current state.
- **Provider Status Mapping**:
  - `PaymentStatus.SUCCESS` $\rightarrow$ booking transitions to `CONFIRMED`.
  - `PaymentStatus.FAILED` $\rightarrow$ booking transitions to `FAILED`.

---

## Webhook Idempotency & Concurrency

Payment gateways routinely retry webhook delivery. The service guarantees absolute idempotency and concurrency safety through database-level primitives:

### 1. Atomic Idempotency Key Insertion
The webhook event table enforces uniqueness on `event_id`:
```sql
INSERT INTO webhook_events (id, event_id, event_type, payload, processed_at)
VALUES (:id, :event_id, :event_type, :payload, :processed_at)
ON CONFLICT (event_id) DO NOTHING
RETURNING id;
```
- Eliminates race-prone "SELECT then INSERT" patterns.
- If the `event_id` was already processed, `RETURNING id` returns `None`. The transaction rolls back immediately and returns HTTP `200 OK` with:
  ```json
  {
    "status": "already_processed",
    "event_id": "<EVENT_ID>",
    "booking_status": null
  }
  ```

### 2. Concurrent Duplicate Delivery Safety
When duplicate webhooks A and B arrive simultaneously:
1. PostgreSQL handles row-level lock arbitration on the unique index of `webhook_events.event_id`.
2. One transaction successfully inserts and receives the generated `id`.
3. The other transaction detects the conflict, performs `DO NOTHING`, returns `None`, and exits cleanly with `"already_processed"`.
4. No duplicate `Payment` or `WebhookEvent` records are ever created.

### 3. Pessimistic Row Locking (`with_for_update`)
When modifying the booking record:
```python
booking = db.scalar(
    select(Booking)
    .where(Booking.id == payload.data.booking_id)
    .with_for_update()
)
```
- Acquires an exclusive row-level lock on the booking.
- Prevents concurrent modifications between simultaneous webhooks and user cancellations.
- Guarantees state machine rules are evaluated against the most up-to-date row state.
