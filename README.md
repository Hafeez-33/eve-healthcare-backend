# EVE Healthcare — Backend Service

A backend service for diagnostic test bookings and simulated payments built with Python, FastAPI, and PostgreSQL.

> **Current Implementation Status:** Phase 1 Complete (Project Foundation & Configuration).  
> Diagnostic centres, bookings, payments, and webhook flows are outlined in [`PLAN.md`](./PLAN.md) and will be implemented in subsequent phases.

---

## Technology Stack

- **Language:** Python 3.11+
- **Framework:** FastAPI
- **Database:** PostgreSQL 16
- **ORM:** SQLAlchemy 2.0
- **Database Migrations:** Alembic
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
| `GET` | `/docs` | Interactive Swagger / OpenAPI documentation | No |

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
