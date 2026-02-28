# 💳 Payment Service

A **production-ready payment microservice** built with FastAPI and Stripe, designed for microservices architectures. Fully independent — integrate it into event ticketing platforms, e-commerce systems, SaaS products, or any application that needs payment processing.

---

## ✨ Features

| Feature | Description |
|---------|-------------|
| **Stripe Integration** | Full PaymentIntent lifecycle — create, confirm, cancel |
| **Refunds** | Full and partial refunds with reason tracking |
| **Customer Management** | CRUD synced with Stripe Customer objects |
| **PDF Receipts** | Auto-generated professional PDF receipts |
| **Webhook Handling** | Stripe webhook receiver with signature verification |
| **Idempotency** | `Idempotency-Key` header prevents duplicate operations |
| **Rate Limiting** | Redis-backed sliding window rate limiter per API key |
| **API Key Auth** | `X-API-Key` header for service-to-service authentication |
| **OpenAPI Docs** | Interactive Swagger UI at `/docs` and ReDoc at `/redoc` |
| **Health Probes** | `/health` and `/ready` endpoints for orchestrators |
| **Correlation IDs** | `X-Correlation-ID` header on every request/response |
| **RFC 7807 Errors** | Standardized Problem Details error responses |
| **Structured Logging** | JSON-formatted logs with correlation IDs |
| **Dockerized** | Docker Compose setup with PostgreSQL and Redis |

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────┐
│                   Payment Service                    │
│                                                     │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────┐  │
│  │ FastAPI   │  │ Middleware│  │ API v1 Router    │  │
│  │ App       │→ │ Stack    │→ │                  │  │
│  │           │  │ • Auth   │  │ • /payments      │  │
│  │ • CORS    │  │ • Rate   │  │ • /refunds       │  │
│  │ • Errors  │  │   Limit  │  │ • /customers     │  │
│  │ • Logging │  │ • Corr ID│  │ • /webhooks      │  │
│  └──────────┘  └──────────┘  └────────┬─────────┘  │
│                                        │            │
│  ┌─────────────────────────────────────▼─────────┐  │
│  │              Service Layer                     │  │
│  │  • PaymentService    • RefundService           │  │
│  │  • CustomerService   • ReceiptService          │  │
│  │  • StripeService (SDK wrapper)                 │  │
│  └──────────┬──────────────────┬─────────────────┘  │
│             │                  │                     │
│  ┌──────────▼──────┐  ┌───────▼──────────┐          │
│  │  PostgreSQL     │  │  Redis           │          │
│  │  • Payments     │  │  • Idempotency   │          │
│  │  • Refunds      │  │  • Rate limits   │          │
│  │  • Customers    │  │                  │          │
│  │  • Receipts     │  │                  │          │
│  └─────────────────┘  └──────────────────┘          │
│             │                                        │
│  ┌──────────▼──────────────────────────────────────┐ │
│  │                  Stripe API                      │ │
│  │  PaymentIntents • Refunds • Customers • Webhooks │ │
│  └──────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────┘
```

---

## 🚀 Quick Start

### Prerequisites

- **Docker** & **Docker Compose** installed
- **Stripe account** (free) — [sign up here](https://dashboard.stripe.com/register)

### 1. Clone and configure

```bash
cd Payment_service

# Create environment file from template
cp .env.example .env
```

### 2. Set up Stripe

1. Go to the [Stripe Dashboard](https://dashboard.stripe.com/test/apikeys)
2. Copy your **Secret key** (starts with `sk_test_...`)
3. Paste it into `.env` as `STRIPE_SECRET_KEY`

For webhooks (optional for testing):
1. Go to [Stripe Webhooks](https://dashboard.stripe.com/test/webhooks)
2. Add endpoint: `http://your-domain:8000/api/v1/webhooks/stripe`
3. Select events: `payment_intent.succeeded`, `payment_intent.payment_failed`, `payment_intent.canceled`
4. Copy the **Signing secret** (starts with `whsec_...`)
5. Paste it into `.env` as `STRIPE_WEBHOOK_SECRET`

### 3. Launch

```bash
# Build and start all services
docker compose up --build -d

# Verify everything is healthy
docker compose ps

# Check health
curl http://localhost:8000/health

# Check readiness (DB + Redis connectivity)
curl http://localhost:8000/ready
```

### 4. Explore the API

Open your browser:
- **Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc**: [http://localhost:8000/redoc](http://localhost:8000/redoc)
- **OpenAPI JSON**: [http://localhost:8000/openapi.json](http://localhost:8000/openapi.json)

---

## 📡 API Reference

All endpoints (except health and webhooks) require the `X-API-Key` header.

### Payments

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/payments` | Create a payment |
| `GET` | `/api/v1/payments` | List payments (paginated) |
| `GET` | `/api/v1/payments/{id}` | Get payment details |
| `POST` | `/api/v1/payments/{id}/confirm` | Confirm a payment |
| `POST` | `/api/v1/payments/{id}/cancel` | Cancel a payment |
| `GET` | `/api/v1/payments/{id}/receipt` | Download PDF receipt |

### Refunds

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/refunds` | Create a refund |
| `GET` | `/api/v1/refunds` | List refunds (paginated) |
| `GET` | `/api/v1/refunds/{id}` | Get refund details |

### Customers

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/customers` | Create a customer |
| `GET` | `/api/v1/customers` | List customers |
| `GET` | `/api/v1/customers/{id}` | Get customer details |
| `PUT` | `/api/v1/customers/{id}` | Update customer |
| `DELETE` | `/api/v1/customers/{id}` | Delete customer (soft) |

### Webhooks

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/webhooks/stripe` | Stripe webhook receiver |

### Health

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Liveness probe |
| `GET` | `/ready` | Readiness probe |

---

## 🧪 Usage Examples

### Create a customer

```bash
curl -X POST http://localhost:8000/api/v1/customers \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-secret-api-key-here" \
  -d '{
    "email": "john@example.com",
    "name": "John Doe",
    "phone": "+1234567890"
  }'
```

### Create a payment

```bash
# Using Stripe test card token
curl -X POST http://localhost:8000/api/v1/payments \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-secret-api-key-here" \
  -H "Idempotency-Key: unique-key-123" \
  -d '{
    "amount": 5000,
    "currency": "usd",
    "payment_method_id": "pm_card_visa",
    "description": "VIP Concert Ticket",
    "metadata": {
      "event_id": "evt_001",
      "ticket_type": "VIP"
    }
  }'
```

### List payments with filters

```bash
curl "http://localhost:8000/api/v1/payments?status=succeeded&limit=10" \
  -H "X-API-Key: your-secret-api-key-here"
```

### Create a refund

```bash
curl -X POST http://localhost:8000/api/v1/refunds \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-secret-api-key-here" \
  -d '{
    "payment_id": "<PAYMENT_UUID>",
    "amount": 2500,
    "reason": "requested_by_customer",
    "description": "Customer requested partial refund"
  }'
```

### Download receipt

```bash
curl -o receipt.pdf \
  "http://localhost:8000/api/v1/payments/<PAYMENT_UUID>/receipt" \
  -H "X-API-Key: your-secret-api-key-here"
```

---

## 🃏 Stripe Test Cards

When using Stripe in test mode, use these payment method IDs:

| Payment Method | Behavior |
|---------------|----------|
| `pm_card_visa` | Succeeds |
| `pm_card_visa_debit` | Succeeds (debit) |
| `pm_card_mastercard` | Succeeds |
| `pm_card_chargeDeclined` | Fails (decline) |
| `pm_card_chargeDeclinedInsufficientFunds` | Fails (insufficient funds) |
| `pm_card_chargeDeclinedFraudulent` | Fails (fraudulent) |

See the [Stripe Testing docs](https://docs.stripe.com/testing) for more test cards.

---

## ⚙️ Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `APP_NAME` | Payment Service | Application name |
| `APP_VERSION` | 1.0.0 | Application version |
| `DEBUG` | false | Enable debug mode |
| `ENVIRONMENT` | production | Environment name |
| `API_KEY` | — | **Required.** API key for authentication |
| `DATABASE_URL` | — | PostgreSQL connection URL |
| `REDIS_URL` | — | Redis connection URL |
| `STRIPE_SECRET_KEY` | — | **Required.** Stripe secret key (`sk_test_...`) |
| `STRIPE_WEBHOOK_SECRET` | — | Stripe webhook signing secret |
| `RATE_LIMIT_REQUESTS` | 100 | Max requests per window |
| `RATE_LIMIT_WINDOW_SECONDS` | 60 | Rate limit window in seconds |
| `LOG_LEVEL` | INFO | Logging level |

---

## 🗄️ Database

The service uses **PostgreSQL** with **SQLAlchemy** (async) and **Alembic** for migrations.

### Tables

- **customers** — Customer profiles synced with Stripe
- **payments** — Payment records with full lifecycle tracking
- **refunds** — Refund records linked to payments
- **receipts** — Generated PDF receipts stored as binary

### Running migrations

```bash
# Auto-create tables on startup (development)
# Tables are created automatically via SQLAlchemy on app start

# Using Alembic for production migrations
docker compose exec api alembic upgrade head
```

---

## 🧪 Running Tests

```bash
# Run tests inside the container
docker compose exec api pytest tests/ -v --tb=short

# Run with coverage
docker compose exec api pytest tests/ -v --cov=app --cov-report=term-missing
```

---

## 🛠️ Development

### Hot reloading

The `docker-compose.yml` mounts `./app` into the container. Changes are reflected immediately when using uvicorn in development mode.

To enable auto-reload:

```bash
# In docker-compose.yml, change the API command to:
# command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Ports

| Service | Internal | External |
|---------|----------|----------|
| API | 8000 | 8000 |
| PostgreSQL | 5432 | 5433 |
| Redis | 6379 | 6380 |

### Logs

```bash
# View API logs
docker compose logs -f api

# View all service logs
docker compose logs -f
```

---

## 📁 Project Structure

```
Payment_service/
├── docker-compose.yml          # Multi-service Docker setup
├── Dockerfile                  # API container image
├── .env.example                # Environment template
├── requirements.txt            # Python dependencies
├── alembic.ini                 # Alembic config
├── alembic/                    # Database migrations
│   ├── env.py
│   └── versions/
│       └── 001_initial.py
├── app/
│   ├── main.py                 # FastAPI app factory
│   ├── config.py               # Pydantic settings
│   ├── database.py             # Async SQLAlchemy setup
│   ├── models/                 # SQLAlchemy ORM models
│   │   ├── payment.py
│   │   ├── refund.py
│   │   ├── customer.py
│   │   └── receipt.py
│   ├── schemas/                # Pydantic request/response schemas
│   │   ├── payment.py
│   │   ├── refund.py
│   │   ├── customer.py
│   │   ├── receipt.py
│   │   └── common.py
│   ├── api/v1/                 # API endpoints
│   │   ├── router.py
│   │   ├── payments.py
│   │   ├── refunds.py
│   │   ├── customers.py
│   │   ├── webhooks.py
│   │   └── health.py
│   ├── services/               # Business logic
│   │   ├── stripe_service.py
│   │   ├── payment_service.py
│   │   ├── refund_service.py
│   │   ├── customer_service.py
│   │   └── receipt_service.py
│   ├── middleware/             # Cross-cutting concerns
│   │   ├── idempotency.py
│   │   └── rate_limiter.py
│   └── utils/                  # Shared utilities
│       ├── exceptions.py
│       └── logging.py
└── tests/                      # Test suite
    ├── conftest.py
    ├── test_payments.py
    ├── test_refunds.py
    ├── test_customers.py
    └── test_webhooks.py
```

---

## 🔌 Integration Guide

### As a microservice

This service is designed to be called by other services in your platform:

1. **Set an API key** in `.env` and share it with consuming services
2. **Create customers** when users register on your platform
3. **Create payments** when processing orders/tickets
4. **Handle webhooks** for async payment status updates
5. **Generate receipts** after successful payments

### Example: Event Ticketing Integration

```
┌──────────────┐     ┌─────────────────┐     ┌──────────────┐
│  Frontend    │────▶│  Ticket Service  │────▶│  Payment     │
│  (React)     │     │  (your service)  │     │  Service     │
└──────────────┘     └─────────────────┘     └──────┬───────┘
                                                     │
                                              ┌──────▼───────┐
                                              │   Stripe     │
                                              └──────────────┘
```

1. Frontend creates an order via Ticket Service
2. Ticket Service calls Payment Service `POST /api/v1/payments`
3. Payment Service processes via Stripe and returns result
4. Ticket Service confirms the ticket reservation
5. Stripe sends webhook → Payment Service updates status

---

## 📄 License

MIT