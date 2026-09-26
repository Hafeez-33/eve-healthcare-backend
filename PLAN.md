# EVE Healthcare — Backend Engineering Implementation Blueprint & Plan

**Document Version:** 1.0.0  
**Status:** FROZEN — SOURCE OF TRUTH  
**Target Stack:** Python 3.11+ | FastAPI | PostgreSQL 16 | SQLAlchemy 2.0 | Alembic | Pydantic v2 | Pytest | Docker Compose  

---

## 1. Executive Summary & Objective

This document serves as the **single implementation source of truth** for the EVE Healthcare SDE Intern Backend Engineering Assessment. 

The objective is to engineer a production-ready, clean, maintainable backend service for diagnostic test bookings and simulated payments with strict transactional guarantees, rigorous webhook idempotency, and robust error handling.

All future development sessions, agents, and contributors must strictly adhere to the architecture, database models, state machines, and phase constraints defined in this document.

---

## 2. Core Architecture & Layered Design

The service follows a strict **Layered Architecture** with unidirectional dependencies:

```
┌────────────────────────────────────────────────────────┐
│                      Client Layer                      │
└───────────────────────────┬────────────────────────────┘
                            │ HTTP / JSON
                            ▼
┌────────────────────────────────────────────────────────┐
│                   API Controllers                      │
│                (app/api/v1/*.py)                       │
│  - Request parsing & Pydantic schema validation        │
│  - Authentication & Dependency Injection (deps.py)     │
│  - HTTP status code translation                        │
└───────────────────────────┬────────────────────────────┘
                            │ Clean Python Types / DTOs
                            ▼
┌────────────────────────────────────────────────────────┐
│                    Service Layer                       │
│               (app/services/*.py)                      │
│  - Core business logic & state transition validation   │
│  - Atomic database transaction boundaries              │
│  - Row-level locking & concurrency guards              │
│  - Webhook idempotency engine                          │
└───────────────────────────┬────────────────────────────┘
                            │ ORM Entities
                            ▼
┌────────────────────────────────────────────────────────┐
│               Data Access & ORM Models                 │
│                 (app/models/*.py)                      │
│  - SQLAlchemy 2.0 Declarative Models                   │
│  - Database constraints, indexes, cascade rules        │
└───────────────────────────┬────────────────────────────┘
                            │ SQL / Sessions
                            ▼
┌────────────────────────────────────────────────────────┐
│                  PostgreSQL Database                   │
│            (Docker / Production Container)             │
└────────────────────────────────────────────────────────┘
```

### Architectural Principles:
1. **Separation of Concerns:** Route handlers (`api/`) must remain thin; no raw SQL, database transactions, or complex business logic in routes.
2. **Centralized Business Rules:** Booking state machine rules, pricing snapshots, and idempotency checks reside exclusively in the `services/` layer.
3. **Explicit Database Transactions:** Service methods control unit-of-work boundaries (`begin`, `commit`, `rollback`) explicitly for sensitive operations.

---

## 3. Database Design (Frozen Schema)

The database schema consists of **exactly six primary tables**. No additional tables (such as RBAC roles or junction tables) are permitted without an approved architectural revision.

```
┌────────────────────────┐         1:N         ┌────────────────────────┐
│         users          │ ──────────────────< │        bookings        │
├────────────────────────┤                     ├────────────────────────┤
│ id (PK, UUID)          │                     │ id (PK, UUID)          │
│ email (UQ, VARCHAR)    │                     │ user_id (FK, UUID)     │
│ hashed_password (TEXT) │                     │ centre_id (FK, UUID)   │
│ full_name (VARCHAR)    │                     │ test_id (FK, UUID)     │
│ created_at (TIMESTAMPTZ│                     │ appointment_at (TSTZ)  │
│ updated_at (TIMESTAMPTZ│                     │ amount (NUMERIC(10,2)) │
└────────────────────────┘                     │ status (ENUM)          │
                                               │ created_at (TIMESTAMPTZ│
┌────────────────────────┐                     │ updated_at (TIMESTAMPTZ│
│   diagnostic_centres   │                     └───────────┬────────────┘
├────────────────────────┤                                 │
│ id (PK, UUID)          │         1:N                     │ 1:N
│ name (VARCHAR)         │ ──────────────────< ┐           │
│ location (TEXT)        │                     │           ▼
│ contact_number (VARCHAR│                     │ ┌────────────────────────┐
│ created_at (TIMESTAMPTZ│                     │ │        payments        │
└───────────┬────────────┘                     │ ├────────────────────────┤
            │                                  │ │ id (PK, UUID)          │
            │ 1:N                              │ │ booking_id (FK, UUID)  │
            │                                  │ │ txn_reference (UQ,STR) │
            ▼                                  │ │ amount (NUMERIC(10,2)) │
┌────────────────────────┐                     │ │ status (ENUM)          │
│    diagnostic_tests    │                     │ │ payment_method (STR)   │
├────────────────────────┤                     │ │ created_at (TIMESTAMPTZ│
│ id (PK, UUID)          │                     └────────────────────────┘
│ centre_id (FK, UUID)   │ ────────────────────┘
│ name (VARCHAR)         │
│ description (TEXT)     │                     ┌────────────────────────┐
│ price (NUMERIC(10,2))  │                     │     webhook_events     │
│ is_active (BOOLEAN)    │                     ├────────────────────────┤
│ created_at (TIMESTAMPTZ│                     │ id (PK, UUID)          │
└────────────────────────┘                     │ event_id (UQ, VARCHAR) │
                                               │ event_type (VARCHAR)   │
                                               │ booking_id (FK, UUID)  │
                                               │ payload (JSONB)        │
                                               │ processed_at (TSTZ)    │
                                               └────────────────────────┘
```

### Table Specifications

#### 1. `users`
* `id`: `UUID`, Primary Key, default `gen_random_uuid()`
* `email`: `VARCHAR(255)`, `UNIQUE`, `NOT NULL`, indexed (normalized lowercase)
* `hashed_password`: `VARCHAR(255)`, `NOT NULL`
* `full_name`: `VARCHAR(150)`, `NOT NULL`
* `created_at`: `TIMESTAMPTZ`, `NOT NULL`, default `CURRENT_TIMESTAMP`
* `updated_at`: `TIMESTAMPTZ`, `NOT NULL`, default `CURRENT_TIMESTAMP`

#### 2. `diagnostic_centres`
* `id`: `UUID`, Primary Key, default `gen_random_uuid()`
* `name`: `VARCHAR(200)`, `NOT NULL`
* `location`: `TEXT`, `NOT NULL`
* `contact_number`: `VARCHAR(30)`, `NOT NULL`
* `created_at`: `TIMESTAMPTZ`, `NOT NULL`, default `CURRENT_TIMESTAMP`
* *Indexes*: `ix_diagnostic_centres_name`

#### 3. `diagnostic_tests`
* `id`: `UUID`, Primary Key, default `gen_random_uuid()`
* `centre_id`: `UUID`, `NOT NULL`, Foreign Key $\rightarrow$ `diagnostic_centres.id` (`ON DELETE RESTRICT`)
* `name`: `VARCHAR(200)`, `NOT NULL`
* `description`: `TEXT`, nullable
* `price`: `NUMERIC(10, 2)`, `NOT NULL`, Check Constraint: `price > 0`
* `is_active`: `BOOLEAN`, `NOT NULL`, default `TRUE`
* `created_at`: `TIMESTAMPTZ`, `NOT NULL`, default `CURRENT_TIMESTAMP`
* *Constraints*: `UNIQUE(centre_id, name)` (no duplicate test names per centre)
* *Indexes*: `ix_diagnostic_tests_centre_id`

#### 4. `bookings`
* `id`: `UUID`, Primary Key, default `gen_random_uuid()`
* `user_id`: `UUID`, `NOT NULL`, Foreign Key $\rightarrow$ `users.id` (`ON DELETE RESTRICT`)
* `centre_id`: `UUID`, `NOT NULL`, Foreign Key $\rightarrow$ `diagnostic_centres.id` (`ON DELETE RESTRICT`)
* `test_id`: `UUID`, `NOT NULL`, Foreign Key $\rightarrow$ `diagnostic_tests.id` (`ON DELETE RESTRICT`)
* `appointment_datetime`: `TIMESTAMPTZ`, `NOT NULL`
* `amount`: `NUMERIC(10, 2)`, `NOT NULL` (**Historical price snapshot at booking time**)
* `status`: `VARCHAR(20)` / `ENUM('PENDING', 'CONFIRMED', 'FAILED', 'CANCELLED')`, `NOT NULL`, default `'PENDING'`
* `created_at`: `TIMESTAMPTZ`, `NOT NULL`, default `CURRENT_TIMESTAMP`
* `updated_at`: `TIMESTAMPTZ`, `NOT NULL`, default `CURRENT_TIMESTAMP`
* *Indexes*:
  * `ix_bookings_user_id` on `user_id`
  * `ix_bookings_status` on `status`
  * `ix_bookings_appointment_datetime` on `appointment_datetime`

#### 5. `payments`
* `id`: `UUID`, Primary Key, default `gen_random_uuid()`
* `booking_id`: `UUID`, `NOT NULL`, Foreign Key $\rightarrow$ `bookings.id` (`ON DELETE RESTRICT`)
* `transaction_reference`: `VARCHAR(100)`, `UNIQUE`, `NOT NULL` (**Second-layer uniqueness**)
* `amount`: `NUMERIC(10, 2)`, `NOT NULL`
* `status`: `VARCHAR(20)` / `ENUM('SUCCESS', 'FAILED')`, `NOT NULL`
* `payment_method`: `VARCHAR(50)`, `NOT NULL`, default `'SIMULATED'`
* `created_at`: `TIMESTAMPTZ`, `NOT NULL`, default `CURRENT_TIMESTAMP`
* *Indexes*:
  * `ix_payments_booking_id` on `booking_id`
  * `uq_payments_transaction_reference` on `transaction_reference`

#### 6. `webhook_events`
* `id`: `UUID`, Primary Key, default `gen_random_uuid()`
* `event_id`: `VARCHAR(100)`, `UNIQUE`, `NOT NULL` (**Primary webhook idempotency token**)
* `event_type`: `VARCHAR(50)`, `NOT NULL`
* `booking_id`: `UUID`, nullable, Foreign Key $\rightarrow$ `bookings.id` (`ON DELETE SET NULL`)
* `payload`: `JSONB`, `NOT NULL`
* `processed_at`: `TIMESTAMPTZ`, `NOT NULL`, default `CURRENT_TIMESTAMP`
* *Indexes*:
  * `uq_webhook_events_event_id` on `event_id`

---

## 4. Frozen Design Decisions & Scope Limits

### 1. Test/Centre Relationship: Direct 1:N Model
* **Decision**: Each diagnostic test belongs to exactly one diagnostic centre (`diagnostic_centres 1:N diagnostic_tests`).
* **Rationale**: Simpler and cleaner than an M:N junction table with separate global tests. Naturally allows Centre A to charge ₹450 for a CBC test while Centre B charges ₹500 for the same test.
* **Invariant**: Do not create a separate global `tests` table + `centre_tests` junction table for this assessment.

### 2. No Role-Based Access Control (RBAC) / Admin Roles
* **Decision**: No `role` column, no `ADMIN`/`USER` enum, no permissions table.
* **Rationale**: The assessment does not specify RBAC. Adding full RBAC adds unnecessary complexity without adding value to the evaluation criteria.
* **Rule**: Catalogue creation endpoints (`POST /centres/`, `POST /centres/{id}/tests`) require standard JWT authentication. Production RBAC is documented in README as a future enhancement.

### 3. Price Snapshotting Invariant
* **Decision**: When a booking is created, `bookings.amount` is permanently captured from `diagnostic_tests.price`.
* **Invariant**: Any future modification to `diagnostic_tests.price` **must never** alter the amount of existing bookings (whether `PENDING`, `CONFIRMED`, `FAILED`, or `CANCELLED`).

### 4. Database Engine Policy
* **Decision**: **PostgreSQL 16** is the mandatory development AND automated testing database.
* **Rule**: Do NOT use SQLite as the test database. The assessment relies heavily on PostgreSQL-specific behavior: row-level locking (`SELECT FOR UPDATE`), `JSONB`, transactional isolation, and PostgreSQL `ON CONFLICT` constraints. Tests must run against a PostgreSQL test container or test instance.

---

## 5. Authentication & Security Specifications

### Endpoints
* `POST /auth/signup`
* `POST /auth/login`

### Rules & Invariants
1. **Email Normalization**: Emails must be converted to lowercase and stripped of leading/trailing whitespace before validation or querying.
2. **Password Security**:
   * Minimum length: 8 characters.
   * Hashing algorithm: `bcrypt` via Passlib or pwdlib.
   * Plaintext passwords must never be stored, logged, or returned in API responses.
3. **Duplicate Prevention**: If email already exists, return `HTTP 409 Conflict` (`{"detail": "Email already registered", "code": "USER_ALREADY_EXISTS"}`).
4. **JWT Implementation**:
   * Algorithm: `HS256`.
   * Secret Key: Read from `SECRET_KEY` environment variable.
   * Expiration: Default 60 minutes (`ACCESS_TOKEN_EXPIRE_MINUTES=60`).
   * Claims: `sub` (User UUID string), `exp` (expiration), `iat` (issued-at).
   * Invalid or expired tokens must yield `HTTP 401 Unauthorized` (`{"detail": "Could not validate credentials", "code": "TOKEN_INVALID"}`).
5. **Dependency Injection**:
   * Reusable `get_current_user` dependency in `app/api/deps.py` extracting and verifying the Bearer token, loading the active user from DB.

---

## 6. Booking System & State Machine

### Booking Creation (`POST /bookings/`)
* Input: `centre_id`, `test_id`, `appointment_datetime`.
* Validation:
  1. User must be authenticated via JWT.
  2. Centre must exist in DB.
  3. Test must exist in DB.
  4. Test must belong to the specified centre (`test.centre_id == centre.id`).
  5. `appointment_datetime` must be strictly in the future (`> CURRENT_TIMESTAMP`).
* Snapshot: Retrieve `test.price` and assign to `booking.amount`.
* Status: Set initial status to `PENDING`.

### Booking State Machine

```
                        ┌─────────────┐
                        │   (Start)   │
                        └──────┬──────┘
                               │
                      POST /bookings/
                               │
                               ▼
                        ┌─────────────┐
        ┌───────────────┤   PENDING   ├───────────────┐
        │               └──────┬──────┘               │
        │                      │                      │
Payment FAILED                 │ Payment SUCCESS      │ User Cancels
(or Webhook FAILED)            │ (or Webhook SUCCESS) │ (PATCH /cancel)
        │                      │                      │
        ▼                      ▼                      ▼
 ┌─────────────┐        ┌─────────────┐        ┌─────────────┐
 │   FAILED    │        │  CONFIRMED  │        │  CANCELLED  │
 │  (Terminal) │        │  (Terminal) │        │  (Terminal) │
 └─────────────┘        └─────────────┘        └─────────────┘
```

### Transition Enforcement Rules
* **Allowed Transitions**:
  * `NONE` $\rightarrow$ `PENDING` (Booking creation)
  * `PENDING` $\rightarrow$ `CONFIRMED` (Successful payment or webhook)
  * `PENDING` $\rightarrow$ `FAILED` (Failed payment or webhook)
  * `PENDING` $\rightarrow$ `CANCELLED` (User cancellation)
* **Terminal States**: `CONFIRMED`, `FAILED`, `CANCELLED`.
* **Disallowed Transitions**:
  * `CONFIRMED` $\rightarrow$ `*` (Terminal; reject with `409 Conflict`)
  * `FAILED` $\rightarrow$ `*` (Terminal; reject with `409 Conflict`)
  * `CANCELLED` $\rightarrow$ `*` (Terminal; reject with `409 Conflict`)
* **Layering Rule**: All state-transition validation must be implemented in `app/services/booking_service.py`, never in route controllers.

### Ownership & IDOR Protection
* A user can only view, cancel, or pay for their own bookings.
* Endpoints:
  * `GET /bookings/`: Filtered by `booking.user_id == current_user.id`.
  * `GET /bookings/{id}`: Verify `booking.user_id == current_user.id`; return `HTTP 403 Forbidden` on mismatch.
  * `PATCH /bookings/{id}/cancel`: Verify ownership; return `HTTP 403 Forbidden` on mismatch.
  * `POST /payments/`: Verify ownership; return `HTTP 403 Forbidden` on mismatch.

---

## 7. Simulated Payment Service

### Endpoint
`POST /payments/`

### Request Payload
```json
{
  "booking_id": "b1a11111-1111-1111-1111-111111111111",
  "simulate_status": "SUCCESS"
}
```
*(Allowed `simulate_status`: `SUCCESS`, `FAILED`. Default: `SUCCESS`)*

### Execution Rules
1. **Existence & Ownership**: Verify booking exists and belongs to `current_user.id`. If not owned $\rightarrow$ `403 Forbidden`.
2. **Status Check**: Verify booking is currently `PENDING`. If already `CONFIRMED`, `FAILED`, or `CANCELLED` $\rightarrow$ `409 Conflict`.
3. **Atomicity & Row Locking**:
   * Acquire a row-level lock on the booking: `SELECT * FROM bookings WHERE id = :id FOR UPDATE`.
   * Generate unique `transaction_reference = f"TXN_SIM_{uuid4().hex[:12].upper()}"`.
   * Create `payments` record with `amount = booking.amount`, `status = simulate_status`.
   * If `simulate_status == "SUCCESS"`: transition booking to `CONFIRMED`.
   * If `simulate_status == "FAILED"`: transition booking to `FAILED`.
   * Commit the single transaction.
4. **Second Payment Protection**: Any subsequent call to `/payments/` will find the booking in a terminal state and be rejected with `HTTP 409 Conflict`.

---

## 8. Webhook Idempotency & Concurrency Architecture

### Endpoint
`POST /payments/webhook/`

### Payload Contract
```json
{
  "event_id": "evt_live_1234567890abcdef",
  "event_type": "payment.updated",
  "timestamp": "2026-09-26T10:07:00Z",
  "data": {
    "transaction_reference": "TXN_PG_987654321",
    "booking_id": "b1a11111-1111-1111-1111-111111111111",
    "amount": "450.00",
    "status": "SUCCESS"
  }
}
```

### Two Independent Uniqueness Guarantees
1. `webhook_events.event_id` **UNIQUE**: Prevents duplicate provider events from triggering reprocessing.
2. `payments.transaction_reference` **UNIQUE**: Prevents duplicate payment records for the same transaction reference.

### Concurrency & Atomicity Workflow

```
Incoming Webhook Request
        │
        ▼
BEGIN DB TRANSACTION
        │
        ▼
INSERT INTO webhook_events(event_id, event_type, booking_id, payload)
VALUES (...) ON CONFLICT (event_id) DO NOTHING RETURNING id;
        │
   ┌────┴──────────────────────────┐
   │                               │
Row Returned?                      No Row Returned (Duplicate)
   │                               │
   ▼ (Unique New Event)            ▼
Lock Booking Row:             ROLLBACK / EXIT TRANSACTION
SELECT * FROM bookings             │
WHERE id = :id FOR UPDATE          ▼
   │                          Return HTTP 200 OK
Validate:                     {"status": "already_processed",
1. booking exists? (404)       "event_id": "..."}
2. payload.amount == booking.amount?
   If mismatch -> ROLLBACK & 400 AMOUNT_MISMATCH
   │
Check existing payment:
SELECT * FROM payments WHERE txn_ref = :ref FOR UPDATE;
If not exists:
  INSERT INTO payments(booking_id, txn_ref, amount, status)
   │
Update Booking Status:
If payload.status == "SUCCESS" and booking.status == "PENDING":
  booking.status = "CONFIRMED"
Else if payload.status == "FAILED" and booking.status == "PENDING":
  booking.status = "FAILED"
   │
COMMIT DB TRANSACTION
   │
   ▼
Return HTTP 200 OK
{"status": "processed", "event_id": "...", "booking_status": "..."}
```

### Critical Webhook Rules:
* **Repeated Delivery**: Identical webhook events must return `HTTP 200 OK` with `status: "already_processed"` to halt provider retry storms without mutating data.
* **Amount Protection**: If `payload.amount != booking.amount`, reject with `HTTP 400 Bad Request` (`code: AMOUNT_MISMATCH`) and do not confirm the booking.
* **Concurrent Duplicate Delivery**: When two identical webhook requests hit the server concurrently, the database-level `ON CONFLICT` / `UNIQUE` constraint guarantees exactly one process executes and commits; the other returns `already_processed`.

---

## 9. API Endpoint Inventory & Error Contract

### Complete API Surface

| Method | Endpoint | Auth | Purpose |
|---|---|:---:|---|
| `POST` | `/auth/signup` | Public | Register new user account |
| `POST` | `/auth/login` | Public | Authenticate user & return JWT token |
| `GET` | `/centres/` | Public | List diagnostic centres (with tests) |
| `GET` | `/centres/{id}` | Public | Get single diagnostic centre details |
| `POST` | `/centres/` | JWT | Create a diagnostic centre |
| `POST` | `/centres/{id}/tests` | JWT | Add diagnostic test to centre |
| `POST` | `/bookings/` | JWT | Book a diagnostic test |
| `GET` | `/bookings/` | JWT | List authenticated user's bookings |
| `GET` | `/bookings/{id}` | JWT | Get single booking details (ownership scoped) |
| `PATCH`| `/bookings/{id}/cancel` | JWT | Cancel a pending booking (ownership scoped) |
| `POST` | `/payments/` | JWT | Simulate direct payment for pending booking |
| `POST` | `/payments/webhook/` | Public / Secret | Ingest simulated payment gateway webhook |
| `GET` | `/health` | Public | Healthcheck for container & DB connectivity |

### Standard HTTP Status Codes
* `200 OK`: Successful retrieval or synchronous update.
* `201 Created`: Resource successfully created.
* `400 Bad Request`: Business rule violation (e.g., test/centre mismatch, amount mismatch).
* `401 Unauthorized`: Missing, invalid, or expired JWT.
* `403 Forbidden`: Cross-user ownership violation (IDOR).
* `404 Not Found`: Target entity not found in database.
* `409 Conflict`: State machine conflict (e.g., paying for confirmed booking, email exists).
* `422 Unprocessable Entity`: Request validation failure (malformed payload, past date).

### Standard Error Contract
All application error responses must strictly conform to:
```json
{
  "detail": "Descriptive human-readable explanation",
  "code": "MACHINE_READABLE_ERROR_CODE"
}
```
*Never leak raw database error messages, stack traces, or internal secrets.*

---

## 10. Project Directory Layout

```
eve-healthcare/
├── .env.example
├── .gitignore
├── Dockerfile
├── docker-compose.yml
├── PLAN.md                     # Single source of truth (this file)
├── README.md                   # Comprehensive documentation & setup
├── requirements.txt            # Pinned dependencies
├── alembic.ini                 # Alembic migration configuration
├── alembic/
│   ├── env.py                  # Alembic environment with model imports
│   ├── script.py.mako
│   └── versions/
│       └── 0001_initial_schema.py
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI application factory & lifespan
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py           # Pydantic Settings
│   │   ├── database.py         # SQLAlchemy engine & sessionmaker
│   │   ├── security.py         # Password hashing & JWT token functions
│   │   └── exceptions.py       # Global exception handlers
│   ├── models/
│   │   ├── __init__.py         # Export all models for Alembic
│   │   ├── base.py             # Declarative Base
│   │   ├── user.py
│   │   ├── centre.py
│   │   ├── test.py
│   │   ├── booking.py
│   │   ├── payment.py
│   │   └── webhook.py
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── user.py
│   │   ├── centre.py
│   │   ├── test.py
│   │   ├── booking.py
│   │   ├── payment.py
│   │   └── webhook.py
│   ├── api/
│   │   ├── __init__.py
│   │   ├── deps.py             # Dependency injection (get_db, get_current_user)
│   │   └── v1/
│   │       ├── __init__.py
│   │       ├── auth.py
│   │       ├── centres.py
│   │       ├── bookings.py
│   │       ├── payments.py
│   │       └── health.py
│   ├── services/
│   │   ├── __init__.py
│   │   ├── auth_service.py
│   │   ├── centre_service.py
│   │   ├── booking_service.py
│   │   └── payment_service.py
│   └── scripts/
│       ├── __init__.py
│       └── seed.py             # Initial database seed script
└── tests/
    ├── __init__.py
    ├── conftest.py             # Pytest fixtures (DB session, TestClient, test data)
    ├── test_auth.py            # Signup, login, JWT validation
    ├── test_centres.py         # Catalogue retrieval & creation
    ├── test_bookings.py        # Booking creation, snapshot, state transitions, IDOR
    ├── test_payments.py        # Simulated payment flows & terminal state checks
    └── test_webhook_idempotency.py # Webhook idempotency, concurrency & mismatch
```

---

## 11. Test Strategy & Test Inventory

### Testing Mandates:
1. **PostgreSQL as Test Database**: Automated integration tests must execute against PostgreSQL. SQLite is prohibited as the primary test target.
2. **Isolation**: Each test must execute inside a rolling database transaction or clean up created records to prevent state pollution.
3. **Coverage Target**: Complete coverage of happy paths, negative paths, state transitions, security boundaries, and concurrency.

### Comprehensive Test Inventory

| Suite | Test Function | Target Behavior / Assertion |
|---|---|---|
| **Auth** | `test_signup_success` | Valid signup creates user, hashes password, returns 201. |
| **Auth** | `test_signup_duplicate_email` | Registering existing email returns 409 Conflict. |
| **Auth** | `test_signup_invalid_email` | Malformed email returns 422 Unprocessable Entity. |
| **Auth** | `test_signup_weak_password` | Password < 8 characters returns 422 Unprocessable Entity. |
| **Auth** | `test_login_success` | Correct credentials return JWT access token with bearer type. |
| **Auth** | `test_login_invalid_password` | Incorrect password returns 401 Unauthorized. |
| **Auth** | `test_expired_jwt` | Expired token returns 401 Unauthorized. |
| **Auth** | `test_tampered_jwt` | Malformed/tampered token returns 401 Unauthorized. |
| **Centres** | `test_list_centres` | Returns list of centres with nested tests and prices. |
| **Centres** | `test_create_centre_and_test` | Authenticated user adds centre and test; test price > 0 enforced. |
| **Centres** | `test_create_test_negative_price`| Test with price <= 0 returns 422 Unprocessable Entity. |
| **Bookings**| `test_create_booking_success` | Creates booking; status `PENDING`, amount snapshotted from test. |
| **Bookings**| `test_create_booking_unauthenticated`| Missing JWT returns 401 Unauthorized. |
| **Bookings**| `test_create_booking_past_date` | Appointment in past returns 422 Unprocessable Entity. |
| **Bookings**| `test_create_booking_invalid_centre`| Non-existent centre UUID returns 404 Not Found. |
| **Bookings**| `test_create_booking_centre_mismatch`| Test belonging to Centre B requested for Centre A returns 400. |
| **Bookings**| `test_booking_price_snapshot_invariant`| Changing test price in DB does not alter existing booking amount. |
| **Bookings**| `test_list_own_bookings` | User only sees their own bookings; zero cross-tenant leakage. |
| **Bookings**| `test_cross_user_booking_access`| User B accessing User A's booking returns 403 Forbidden. |
| **Bookings**| `test_cancel_pending_booking` | User cancels `PENDING` booking; status moves to `CANCELLED`. |
| **Bookings**| `test_cancel_confirmed_booking`| User attempting to cancel `CONFIRMED` booking returns 409 Conflict. |
| **Payments**| `test_simulated_payment_success`| `POST /payments/` with SUCCESS updates booking to `CONFIRMED`. |
| **Payments**| `test_simulated_payment_failure`| `POST /payments/` with FAILED updates booking to `FAILED`. |
| **Payments**| `test_payment_unauthorized_user`| User B paying for User A's booking returns 403 Forbidden. |
| **Payments**| `test_payment_on_confirmed_booking`| Duplicate payment on `CONFIRMED` booking returns 409 Conflict. |
| **Payments**| `test_payment_on_cancelled_booking`| Payment on `CANCELLED` booking returns 409 Conflict. |
| **Payments**| `test_payment_on_failed_booking`| Payment on `FAILED` booking returns 409 Conflict. |
| **Webhook** | `test_webhook_success_confirms_booking`| Webhook event updates booking to `CONFIRMED` & records payment. |
| **Webhook** | `test_webhook_idempotency_duplicate_event`| Duplicate `event_id` returns 200 `already_processed` with 0 mutations. |
| **Webhook** | `test_webhook_amount_mismatch` | Amount discrepancy returns 400 `AMOUNT_MISMATCH`; booking stays `PENDING`. |
| **Webhook** | `test_webhook_concurrent_duplicates`| 5 concurrent identical webhooks execute safely: 1 processed, 4 already_processed. |
| **Webhook** | `test_payment_txn_reference_uniqueness`| Duplicate `transaction_reference` is rejected by DB constraint. |

---

## 12. Docker & Local Development Strategy

### Docker Compose Services
1. **`db`**:
   * Image: `postgres:16-alpine`.
   * Environment: `POSTGRES_DB=eve_healthcare`, `POSTGRES_USER=postgres`, `POSTGRES_PASSWORD=postgres`.
   * Volume: `postgres_data:/var/lib/postgresql/data`.
   * Healthcheck: `pg_isready -U postgres -d eve_healthcare`.
2. **`web`**:
   * Build: Context `.`, multi-stage or lean Python 3.11-slim Dockerfile.
   * Ports: `8000:8000`.
   * Depends On: `db` with `condition: service_healthy`.
   * Command: Wait for DB readiness $\rightarrow$ run `alembic upgrade head` $\rightarrow$ run optional seed $\rightarrow$ start Uvicorn.

---

## 13. Documentation & README Blueprint

The final `README.md` must thoroughly cover:
1. **Project Overview & Objectives**
2. **Tech Stack & Justification** (FastAPI, PostgreSQL 16, SQLAlchemy 2.0, Pydantic v2)
3. **Architecture & Folder Structure**
4. **Environment Configuration** (`.env.example` reference)
5. **How to Run Locally via Docker Compose** (`docker compose up --build`)
6. **How to Run Locally without Docker** (Virtualenv + local PostgreSQL)
7. **Database Migrations & Seeding Commands** (`alembic upgrade head`, `python -m app.scripts.seed`)
8. **Interactive API Documentation** (`http://localhost:8000/docs`)
9. **Complete API Reference & cURL Examples** for entire user flow (Signup $\rightarrow$ Login $\rightarrow$ Centres $\rightarrow$ Book $\rightarrow$ Pay / Webhook)
10. **Database Schema & Entity Relationship Overview**
11. **Booking State Machine & Transition Rules**
12. **Simulated Payment & Webhook Idempotency Design**
13. **Running the Test Suite** (`pytest -v`)
14. **Design Assumptions & Decisions**
15. **Future Production Enhancements** (Redis, Celery, RBAC, Distributed Tracing)

---

## 14. Sequential Implementation Phases (0% to 100%)

```
PHASE 0: Analysis & Master Blueprint  [COMPLETED]
   └── Analysis, API specs, schema, state machine, and PLAN.md frozen.

PHASE 1: Project Foundation & Configuration  [Target: 10%]
   ├── requirements.txt, .env.example, .gitignore
   ├── app/core/config.py (Pydantic BaseSettings)
   ├── app/core/database.py (SQLAlchemy 2.0 engine & session)
   └── app/main.py (FastAPI entrypoint with healthcheck)

PHASE 2: Database Schema & Migrations  [Target: 25%]
   ├── app/models/*.py (User, Centre, Test, Booking, Payment, WebhookEvent)
   ├── alembic/ configuration & initial migration (0001_initial_schema.py)
   └── app/scripts/seed.py (Diagnostic centres & tests seed data)

PHASE 3: Authentication & Security Engine  [Target: 40%]
   ├── app/core/security.py (bcrypt password hashing, JWT encode/decode)
   ├── app/api/deps.py (get_current_user dependency)
   ├── app/schemas/user.py & app/services/auth_service.py
   └── app/api/v1/auth.py (POST /auth/signup, POST /auth/login) + tests

PHASE 4: Diagnostic Centres & Tests Module  [Target: 50%]
   ├── app/schemas/centre.py & test.py
   ├── app/services/centre_service.py
   └── app/api/v1/centres.py (GET /centres/, GET /centres/{id}, POST /centres/) + tests

PHASE 5: Booking System & State Machine  [Target: 65%]
   ├── app/schemas/booking.py
   ├── app/services/booking_service.py (Price snapshot, slot validation, state guards)
   └── app/api/v1/bookings.py (POST /bookings/, GET /bookings/, PATCH /cancel) + tests

PHASE 6: Payments & Webhook Idempotency Engine  [Target: 80%]
   ├── app/schemas/payment.py & webhook.py
   ├── app/services/payment_service.py (Row locking, ON CONFLICT, idempotency, amount check)
   └── app/api/v1/payments.py (POST /payments/, POST /payments/webhook/) + tests

PHASE 7: Comprehensive Testing & Security Hardening  [Target: 90%]
   ├── tests/conftest.py (PostgreSQL fixtures, test tokens)
   ├── Full pytest suite (all 30+ tests from Section 11)
   └── Concurrency test verifying identical concurrent webhooks execute exactly once

PHASE 8: Docker, Documentation & Submission Readiness  [Target: 100%]
   ├── Dockerfile & docker-compose.yml with DB healthcheck
   ├── README.md with complete cURL walkthrough and architecture diagrams
   └── Final repository audit (clean git tree, no leaked credentials)
```

---

## 15. Rules for Future Agents & Contributors

> [!IMPORTANT]
> **MANDATORY EXECUTION RULES FOR ALL FUTURE AGENTS:**
> 1. **Strict Phase Sequencing**: NEVER implement multiple phases at once unless explicitly instructed. Implement one phase at a time.
> 2. **Check Before Executing**: Before starting any phase:
>    * Read `PLAN.md`.
>    * Verify that the previous phase is 100% complete and tested.
>    * Implement ONLY the files and features assigned to that phase.
> 3. **Verify Against Invariants**:
>    * Never introduce SQLite as the test database.
>    * Never introduce RBAC or Admin roles.
>    * Never introduce Redis or Celery.
>    * Never alter the 1:N Centre-to-Test model without prior approval.
>    * Never bypass row-level locking or webhook `ON CONFLICT` idempotency.
> 4. **Report & Stop**: At the conclusion of each phase:
>    * Report exactly what was implemented and changed.
>    * Run and report test verification results.
>    * Report what remains for the next phase.
>    * STOP and wait for user confirmation before advancing.

---

## 16. Definition of Done (Assessment Checklist)

- [ ] All mandatory requirements from the assessment are implemented.
- [ ] User authentication with bcrypt password hashing and JWT issuance is functional.
- [ ] Reusable `get_current_user` dependency protects secured routes.
- [ ] Diagnostic centres and test catalog APIs function with price validation.
- [ ] Direct 1:N Centre-to-Test relationship is respected; test pricing is centre-specific.
- [ ] Booking creation snapshots test price into `bookings.amount`.
- [ ] Appointment date is validated to be strictly in the future.
- [ ] Server-side ownership checks prevent cross-user IDOR access on all booking and payment endpoints.
- [ ] Booking state machine enforces `PENDING`, `CONFIRMED`, `FAILED`, `CANCELLED` transitions.
- [ ] Terminal states reject illegal transitions with `HTTP 409 Conflict`.
- [ ] Simulated payment endpoint (`POST /payments/`) updates booking atomically with row-level locks.
- [ ] Webhook endpoint (`POST /payments/webhook/`) is strictly idempotent via `webhook_events.event_id UNIQUE`.
- [ ] Duplicate webhook submissions return `HTTP 200 OK` with `status: "already_processed"`.
- [ ] Concurrent duplicate webhooks are handled safely via database-level `ON CONFLICT`.
- [ ] Webhook amount mismatch is rejected with `HTTP 400 Bad Request` (`AMOUNT_MISMATCH`).
- [ ] `payments.transaction_reference` is unique, preventing duplicate payment rows.
- [ ] All database changes are managed through Alembic migrations.
- [ ] Automated tests in Pytest execute against PostgreSQL and pass cleanly.
- [ ] Edge cases (concurrency, tamper, unauthorized, invalid IDs) are verified by tests.
- [ ] Multi-container setup with `docker compose up --build` works out of the box.
- [ ] Database seed script populates sample centres and diagnostic tests.
- [ ] OpenAPI documentation is accessible at `/docs`.
- [ ] Comprehensive `README.md` is complete with setup, schema, state machine, and cURL walkthrough.
- [ ] No secrets, credentials, or `.env` files committed to Git.