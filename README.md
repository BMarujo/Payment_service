# Payment Service

A **production-ready payment microservice** built with FastAPI, designed for microservices architectures. Authentication is delegated to the **external EGS Auth Service** for centralized user management.

---

## Features

| Feature | Description |
|---------|-------------|
| **External Auth (EGS)** | Token verification delegated to the EGS Auth Service via `/verify` |
| **Hosted Checkout** | Checkout flow with Bearer token authorization via EGS |
| **Payments** | Full payment lifecycle — create, confirm, cancel, refund |
| **Refunds** | Full and partial refunds with reason tracking |
| **Customer Management** | CRUD for payment service customer records |
| **PDF Receipts** | Auto-generated professional PDF receipts |
| **Multi-Tenant API Keys** | Database-backed API key management with SHA-256 hashing |
| **Idempotency** | `Idempotency-Key` header prevents duplicate operations |
| **Rate Limiting** | Redis-backed sliding window rate limiter, per-key configurable |
| **OpenAPI Docs** | Interactive Swagger UI at `/docs` and ReDoc at `/redoc` |
| **Health Probe** | `/health` endpoint for orchestrators |
| **Correlation IDs** | `X-Correlation-ID` header on every request/response |
| **RFC 7807 Errors** | Standardized Problem Details error responses |
| **Structured Logging** | JSON-formatted logs with correlation IDs |
| **Observability** | OpenTelemetry tracing + metrics, Grafana KPI dashboards, Jaeger traces |
| **Dockerized** | Docker Compose setup with PostgreSQL, Redis, and observability stack |

---

## Architecture

```
┌───────────────────────────────────────────────────────────────────┐
│                                                                   │
│  ┌──────────────────┐                  ┌──────────────────────┐  │
│  │  EGS Auth Service│                  │  Payment Service     │  │
│  │  (port 8000)     │◄──── /verify ────│  (port 8001)         │  │
│  │                  │  X-Service-Auth   │                      │  │
│  │  • /register     │                  │  • /checkout          │  │
│  │  • /login        │                  │  • /payments          │  │
│  │  • /verify       │                  │  • /customers         │  │
│  │  • /logout       │                  │  • /admin/api-keys    │  │
│  │  • /me           │                  │  • /refunds           │  │
│  └────────┬─────────┘                  └────────┬─────────────┘  │
│           │                                      │                │
│  ┌────────▼─────────┐                  ┌────────▼─────────────┐  │
│  │ PostgreSQL (auth)│                  │ PostgreSQL (payments) │  │
│  │ Redis (tokens)   │                  │ Redis (rate limits)   │  │
│  └──────────────────┘                  └──────────────────────┘  │
└───────────────────────────────────────────────────────────────────┘
```

---

## Quick Start

### Prerequisites

- **Docker** & **Docker Compose** installed
- **EGS Auth Service** running on port 8000 (see `EGS/auth-service/`)

### 1. Start the EGS Auth Service

```bash
cd EGS/auth-service
docker compose up --build -d
# Verify it's healthy:
curl http://localhost:8000/health
```

### 2. Configure & launch the Payment Service

```bash
cd Payment_service

# Create environment file from template
cp .env.example .env
```

Edit `.env` and set:
- `ADMIN_API_KEY` — a strong secret for the admin bootstrap key
- `INTERNAL_SERVICE_KEY` — must match the EGS Auth Service's `INTERNAL_SERVICE_KEY`
- `AUTH_SERVICE_URL` — URL of the EGS Auth Service (default: `http://host.docker.internal:8000`)

```bash
# Build and start all services
docker compose up --build -d

# Verify everything is healthy
curl http://localhost:8001/health
```

### 3. Create your first tenant API key

```bash
curl -X POST http://localhost:8001/api/v1/admin/api-keys \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-admin-api-key-here" \
  -d '{"client_name": "My Ticket Service"}'
```

The response includes a `raw_key` field (e.g., `ps_live_a1b2c3d4...`). **Save it — it's shown only once.**

### 4. Explore the API

- **Swagger UI**: [http://localhost:8001/docs](http://localhost:8001/docs)
- **ReDoc**: [http://localhost:8001/redoc](http://localhost:8001/redoc)

### 5. UI URLs (not API endpoints)

These are static UI pages/URLs for browser navigation. They are **not** API endpoints and are intentionally hidden from OpenAPI docs.

- **Login UI**: `http://localhost:8001/wallet/login`
- **Sign Up UI**: `http://localhost:8001/wallet/register`
- **Checkout UI**: `http://localhost:8001/checkout/{session_id}`
- **Dashboard UI**: `http://localhost:8001/wallet/dashboard`

---

## Authentication Model

Authentication is handled by the **external EGS Auth Service**:

1. Users register via EGS Auth (`POST /api/v1/auth/register` on Auth Service)
2. Users login via EGS Auth (`POST /api/v1/auth/login` on Auth Service) and receive a Bearer token
3. Merchants create/manage local Payment customers via Payment API (`/api/v1/customers*`)
4. The EGS Bearer token is used for checkout authorization and viewing transaction history

### Two types of auth in the Payment Service:

| Auth Type | Header | Used For |
|-----------|--------|----------|
| **API Key** | `X-API-Key` | Merchant/admin endpoints (payments, customers, API key management) |
| **Bearer Token** (EGS) | `Authorization: Bearer <token>` | End-user endpoints (checkout authorization, transaction history) |

---

## API Key Management

### Admin Key (bootstrap)

Set via `ADMIN_API_KEY` in `.env`. This key can:
- Create, list, update, and revoke tenant API keys
- Access all payment/refund/customer endpoints

### Tenant Keys (per-client)

Created via the admin endpoints. Each key:
- Is a random 56-character token prefixed with `ps_live_`
- Is **hashed (SHA-256)** before storage
- Can have **custom rate limits** and **scopes**
- Can be **revoked** at any time

---

## API Reference

### Checkout Sessions

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `POST` | `/api/v1/checkout` | API Key | Create a checkout session |
| `GET` | `/api/v1/checkout/{id}` | Public | Check session status |
| `POST` | `/api/v1/checkout/{id}/authorize` | Bearer Token | Authorize payment with EGS token |

**Checkout flow:**
1. Merchant calls `POST /checkout` with line items and redirect URLs
2. Response includes `checkout_url` — redirect the end-user there
3. User logs in (via EGS) and authorizes the payment with their Bearer token
4. Payment succeeds instantly → user is redirected to `success_url`

### Payments

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/payments` | Create a payment |
| `GET` | `/api/v1/payments` | List payments (paginated) |
| `GET` | `/api/v1/payments/{id}` | Get payment details |
| `PUT` | `/api/v1/payments/{id}/confirm` | Confirm a payment |
| `DELETE` | `/api/v1/payments/{id}` | Cancel or refund a payment |
| `GET` | `/api/v1/payments/{id}/receipt` | Download PDF receipt |

### Customers

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/customers` | Create a customer (merchant use) |
| `GET` | `/api/v1/customers` | List customers |
| `GET` | `/api/v1/customers/{id}` | Get customer details |
| `PUT` | `/api/v1/customers/{id}` | Update customer |
| `DELETE` | `/api/v1/customers/{id}` | Delete customer (soft) |
| `GET` | `/api/v1/customers/me/transactions` | Get my transactions (Bearer) |

### Refunds

Refunds are handled automatically by `DELETE /api/v1/payments/{id}` — if the payment has succeeded, it issues a full refund. For partial refunds, use `POST /api/v1/payments/{id}/refund`.

### Admin

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/admin/api-keys` | Create API key |
| `GET` | `/api/v1/admin/api-keys` | List API keys |
| `GET` | `/api/v1/admin/api-keys/{id}` | Get key details |
| `PUT` | `/api/v1/admin/api-keys/{id}` | Update key |
| `DELETE` | `/api/v1/admin/api-keys/{id}` | Revoke key |

### Health

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Liveness probe |

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `APP_NAME` | Payment Service | Application name |
| `APP_VERSION` | 1.0.0 | Application version |
| `DEBUG` | false | Enable debug mode |
| `ENVIRONMENT` | production | Environment name |
| `ADMIN_API_KEY` | — | **Required.** Admin bootstrap key |
| `AUTH_SERVICE_URL` | `http://localhost:8000` | **Required.** EGS Auth Service URL |
| `INTERNAL_SERVICE_KEY` | — | **Required.** Shared secret with EGS Auth Service |
| `DATABASE_URL` | — | PostgreSQL connection URL |
| `REDIS_URL` | — | Redis connection URL |
| `RATE_LIMIT_REQUESTS` | 100 | Default max requests per window |
| `RATE_LIMIT_WINDOW_SECONDS` | 60 | Default rate limit window |
| `LOG_LEVEL` | INFO | Logging level |

---

## Ports

| Service | Internal | External |
|---------|----------|----------|
| Payment API | 8000 | **8001** |
| PostgreSQL | 5432 | 5433 |
| Redis | 6379 | 6380 |
| EGS Auth Service | 8000 | 8000 |

---

## Integration Guide

### Example: Event Ticketing Integration

```
┌──────────────┐     ┌─────────────────┐     ┌──────────────────┐     ┌──────────────┐
│  Frontend    │────>│  Ticket Service  │────>│  Payment Service │────>│  EGS Auth    │
│  (React)     │     │  (your service)  │     │  (port 8001)     │     │  (port 8000) │
└──────────────┘     └─────────────────┘     └──────────────────┘     └──────────────┘
```

1. Admin creates a tenant API key for the Ticket Service
2. Frontend creates an order via Ticket Service
3. Ticket Service calls `POST /api/v1/checkout` with its API key
4. User is redirected to the checkout page and logs in via EGS Auth
5. User authorizes payment with their EGS Bearer token
6. Payment succeeds → Ticket Service confirms the reservation

---

## Project Structure

```
Payment_service/
├── docker-compose.yml          # Multi-service Docker setup
├── Dockerfile                  # API container image
├── entrypoint.sh               # Auto-migration + app startup
├── .env.example                # Environment template
├── requirements.txt            # Python dependencies
├── alembic.ini                 # Alembic config
├── alembic/                    # Database migrations
├── EGS/                        # External Auth Service
│   └── auth-service/           # EGS Auth Service (separate docker-compose)
├── app/
│   ├── main.py                 # FastAPI app factory
│   ├── config.py               # Pydantic settings
│   ├── database.py             # Async SQLAlchemy setup
│   ├── telemetry.py            # OpenTelemetry setup & auto-instrumentation
│   ├── metrics.py              # Business KPI metric definitions
│   ├── models/                 # SQLAlchemy ORM models
│   ├── schemas/                # Pydantic request/response schemas
│   ├── api/v1/                 # API endpoints
│   │   ├── router.py
│   │   ├── payments.py
│   │   ├── customers.py
│   │   ├── checkout.py
│   │   ├── api_keys.py
│   │   └── health.py
│   ├── services/               # Business logic
│   │   ├── auth_client.py      # EGS Auth /verify client
│   │   ├── payment_service.py
│   │   ├── refund_service.py
│   │   ├── customer_service.py
│   │   ├── receipt_service.py
│   │   └── api_key_service.py
│   ├── static/                 # Frontend HTML pages
│   │   ├── checkout.html
│   │   ├── login.html
│   │   ├── register.html
│   │   └── dashboard.html
│   └── utils/
│       ├── exceptions.py
│       └── logging.py
├── observability/              # Observability stack config
│   ├── otel-collector-config.yaml
│   ├── prometheus.yml
│   └── grafana/
│       ├── provisioning/       # Auto-configured datasources & dashboard providers
│       └── dashboards/         # Pre-built Grafana dashboard JSON
├── test_all_endpoints.sh       # End-to-end integration test
└── api_workflow.txt            # Manual API workflow reference
```

---

## Observability & KPIs

The service includes a full observability stack powered by **OpenTelemetry**.

### Dashboards & Tools

| Tool | URL | Purpose |
|------|-----|--------|
| **Grafana** | `http://localhost:3000` | KPI dashboards (login: `admin` / `admin`) |
| **Jaeger** | `http://localhost:16686` | Distributed trace explorer |
| **Prometheus** | `http://localhost:9090` | Raw metrics queries |

### Business KPIs (tracked automatically)

| KPI | Description |
|-----|-------------|
| Payment Volume | Total money processed, by currency |
| Transaction Count | Payments by status (succeeded / failed / canceled) |
| Success Rate | Percentage of succeeded payments |
| Refund Rate | Number and volume of refunds |
| Checkout Conversion | Sessions created vs completed |
| Customer Registrations | New customer sign-ups over time |

### Operational KPIs

| KPI | Description |
|-----|-------------|
| Request Latency | p50 / p95 / p99 response times |
| Error Rate | 4xx and 5xx responses per minute |
| EGS Auth Latency | External auth service call duration |
| Rate Limit Hits | Requests rejected by rate limiter |

### Distributed Tracing

Every request is traced end-to-end across:
- **FastAPI** HTTP handler
- **SQLAlchemy** database queries
- **Redis** cache operations
- **httpx** outgoing calls to EGS Auth Service

Open **Jaeger** at `http://localhost:16686`, select service `payment-service`, and explore traces.

### Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `OTEL_ENABLED` | `true` | Set to `false` to disable telemetry |
| `OTEL_SERVICE_NAME` | `payment-service` | Service name in traces |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://otel-collector:4317` | OTel Collector gRPC endpoint |

---

## License

MIT
