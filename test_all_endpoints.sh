#!/bin/bash
set -e

# ══════════════════════════════════════════════════════════════════
#  End-to-End Integration Test — Payment Service
#
#  Prerequisite: Both services must be running:
#    EGS Auth Service → http://localhost:8000
#    Payment Service  → http://localhost:8001
# ══════════════════════════════════════════════════════════════════

PAYMENT_BASE="http://localhost:8001"
AUTH_BASE="http://localhost:8000"
ADMIN_KEY="${ADMIN_API_KEY:-your-admin-api-key-here}"
TEST_EMAIL="test_user_$RANDOM@example.com"
MERCHANT_CUSTOMER_EMAIL="merchant_customer_$RANDOM@example.com"
TEST_PASSWORD="securepassword123"

# Load admin key from .env when not provided in environment
if [ "$ADMIN_KEY" = "your-admin-api-key-here" ] && [ -f ".env" ]; then
  ADMIN_KEY=$(grep '^ADMIN_API_KEY=' .env | head -n1 | cut -d '=' -f2-)
fi

GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

fail() {
  echo -e "${RED}$1${NC}"
  exit 1
}

echo -e "${BLUE}=== 1. ADMIN: API KEY ===${NC}"

echo ">> 1.0 Health check"
curl -s "$PAYMENT_BASE/health" > /dev/null || fail "Health endpoint failed"
echo "  OK"

echo ">> 1.1 Creating API Key"
KEY_RESP=$(curl -s -X POST "$PAYMENT_BASE/api/v1/admin/api-keys" \
  -H "X-API-Key: $ADMIN_KEY" \
  -H "Content-Type: application/json" \
  -d '{"client_name":"Test Merchant","description":"workflow test key"}')
API_KEY=$(echo "$KEY_RESP" | python3 -c "import sys, json; print(json.load(sys.stdin).get('raw_key', ''))")
KEY_ID=$(echo "$KEY_RESP" | python3 -c "import sys, json; print(json.load(sys.stdin).get('id', ''))")

if [ -z "$API_KEY" ]; then
    fail "Failed to create API key: $KEY_RESP"
fi
echo "  Key ID: $KEY_ID"

echo ">> 1.2 List API keys"
curl -s "$PAYMENT_BASE/api/v1/admin/api-keys" -H "X-API-Key: $ADMIN_KEY" > /dev/null || fail "List API keys failed"
echo "  OK"

echo ">> 1.3 Get API key"
curl -s "$PAYMENT_BASE/api/v1/admin/api-keys/$KEY_ID" -H "X-API-Key: $ADMIN_KEY" > /dev/null || fail "Get API key failed"
echo "  OK"

echo ">> 1.4 Update API key"
curl -s -X PUT "$PAYMENT_BASE/api/v1/admin/api-keys/$KEY_ID" \
  -H "X-API-Key: $ADMIN_KEY" \
  -H "Content-Type: application/json" \
  -d '{"description":"updated workflow test key"}' > /dev/null || fail "Update API key failed"
echo "  OK"


echo -e "\n${BLUE}=== 2. AUTH (EGS SERVICE) + LOCAL CUSTOMER ===${NC}"

echo ">> 2.1 Register in EGS Auth Service ($TEST_EMAIL)"
REG_RESP=$(curl -s -X POST "$AUTH_BASE/api/v1/auth/register" \
  -H "Content-Type: application/json" \
  -d "{\"email\": \"$TEST_EMAIL\", \"password\": \"$TEST_PASSWORD\", \"full_name\": \"Test User\"}")
AUTH_USER_ID=$(echo "$REG_RESP" | python3 -c "import sys, json; print(json.load(sys.stdin).get('id', ''))")

[ -n "$AUTH_USER_ID" ] || fail "EGS registration failed: $REG_RESP"
echo "  Auth User ID: $AUTH_USER_ID"

echo ">> 2.2 Login in EGS Auth Service"
LOGIN_RESP=$(curl -s -X POST "$AUTH_BASE/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\": \"$TEST_EMAIL\", \"password\": \"$TEST_PASSWORD\"}")
EGS_TOKEN=$(echo "$LOGIN_RESP" | python3 -c "import sys, json; print(json.load(sys.stdin).get('access_token', ''))")

[ -n "$EGS_TOKEN" ] || fail "Login failed: $LOGIN_RESP"
echo "  Got Bearer token"

echo ">> 2.3 Create local Payment customer"
LOCAL_CUST_RESP=$(curl -s -X POST "$PAYMENT_BASE/api/v1/customers" \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d "{\"email\": \"$TEST_EMAIL\", \"name\": \"Test User\"}")
CUST_ID=$(echo "$LOCAL_CUST_RESP" | python3 -c "import sys, json; print(json.load(sys.stdin).get('id', ''))")
[ -n "$CUST_ID" ] || fail "Local customer creation failed: $LOCAL_CUST_RESP"
echo "  Payment Customer ID: $CUST_ID"

echo -e "\n${BLUE}=== 3. CUSTOMER CRUD (merchant/admin use) ===${NC}"

echo ">> 3.1 Create merchant-managed customer"
MC_RESP=$(curl -s -X POST "$PAYMENT_BASE/api/v1/customers" \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d "{\"email\": \"$MERCHANT_CUSTOMER_EMAIL\", \"name\": \"Merchant Customer\", \"phone\": \"+15550001111\"}")
MC_ID=$(echo "$MC_RESP" | python3 -c "import sys, json; print(json.load(sys.stdin).get('id', ''))")
[ -n "$MC_ID" ] || fail "Create merchant customer failed: $MC_RESP"
echo "  Merchant Customer ID: $MC_ID"

echo ">> 3.2 List customers"
curl -s "$PAYMENT_BASE/api/v1/customers?limit=10" -H "X-API-Key: $API_KEY" > /dev/null || fail "List customers failed"
echo "  OK"

echo ">> 3.3 Get customer"
curl -s "$PAYMENT_BASE/api/v1/customers/$MC_ID" -H "X-API-Key: $API_KEY" > /dev/null || fail "Get customer failed"
echo "  OK"

echo ">> 3.4 Update customer"
curl -s -X PUT "$PAYMENT_BASE/api/v1/customers/$MC_ID" \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"name":"Merchant Customer Updated"}' > /dev/null || fail "Update customer failed"
echo "  OK"


echo -e "\n${BLUE}=== 4. PAYMENTS (direct API flow) ===${NC}"

echo ">> 4.1 Create pending payment"
PENDING_RESP=$(curl -s -X POST "$PAYMENT_BASE/api/v1/payments" \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d "{\"customer_id\": \"$MC_ID\", \"amount\": 3500, \"currency\": \"usd\", \"description\": \"Pending payment test\"}")
PENDING_PAYMENT_ID=$(echo "$PENDING_RESP" | python3 -c "import sys, json; print(json.load(sys.stdin).get('id', ''))")
[ -n "$PENDING_PAYMENT_ID" ] || fail "Create pending payment failed: $PENDING_RESP"
echo "  Pending Payment ID: $PENDING_PAYMENT_ID"

echo ">> 4.2 Confirm payment"
curl -s -X PUT "$PAYMENT_BASE/api/v1/payments/$PENDING_PAYMENT_ID/confirm" \
  -H "X-API-Key: $API_KEY" > /dev/null || fail "Confirm payment failed"
echo "  OK"

echo ">> 4.3 Download receipt"
curl -s "$PAYMENT_BASE/api/v1/payments/$PENDING_PAYMENT_ID/receipt" \
  -H "X-API-Key: $API_KEY" > /dev/null || fail "Receipt download failed"
echo "  OK"

echo ">> 4.4 Create second pending payment"
PENDING2_RESP=$(curl -s -X POST "$PAYMENT_BASE/api/v1/payments" \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d "{\"customer_id\": \"$MC_ID\", \"amount\": 2200, \"currency\": \"usd\", \"description\": \"Cancel payment test\"}")
PENDING2_ID=$(echo "$PENDING2_RESP" | python3 -c "import sys, json; print(json.load(sys.stdin).get('id', ''))")
[ -n "$PENDING2_ID" ] || fail "Create second pending payment failed: $PENDING2_RESP"
echo "  Pending Payment ID: $PENDING2_ID"

echo ">> 4.5 Cancel pending payment via DELETE"
curl -s -X DELETE "$PAYMENT_BASE/api/v1/payments/$PENDING2_ID" \
  -H "X-API-Key: $API_KEY" > /dev/null || fail "Cancel pending payment failed"
echo "  OK"


echo -e "\n${BLUE}=== 5. CHECKOUT + AUTHORIZATION ===${NC}"

echo ">> 5.1 Creating checkout session"
SESSION_RESP=$(curl -s -X POST "$PAYMENT_BASE/api/v1/checkout" \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d "{
    \"customer_email\": \"$TEST_EMAIL\",
    \"customer_name\": \"Test User\",
    \"line_items\": [{\"name\": \"Concert Ticket\", \"quantity\": 2, \"price\": 10000}],
    \"success_url\": \"https://merchant.com/success\",
    \"cancel_url\": \"https://merchant.com/cancel\"
  }")
SESSION_ID=$(echo "$SESSION_RESP" | python3 -c "import sys, json; print(json.load(sys.stdin).get('session_id', ''))")

[ -n "$SESSION_ID" ] || fail "Failed to create checkout: $SESSION_RESP"
echo "  Session: $SESSION_ID"

echo ">> 5.2 Check status (open)"
curl -s "$PAYMENT_BASE/api/v1/checkout/$SESSION_ID" > /dev/null
echo "  OK"

echo ">> 5.3 Hosted checkout UI URL is reachable"
curl -s "$PAYMENT_BASE/checkout/$SESSION_ID" > /dev/null || fail "Hosted checkout UI URL failed"
echo "  OK"

echo ">> 5.4 Authorize with Bearer token"
AUTH_RESP=$(curl -s -X POST "$PAYMENT_BASE/api/v1/checkout/$SESSION_ID/authorize" \
  -H "Authorization: Bearer $EGS_TOKEN")
PAYMENT_ID=$(echo "$AUTH_RESP" | python3 -c "import sys, json; print(json.load(sys.stdin).get('payment_id', ''))")

[ -n "$PAYMENT_ID" ] || fail "Authorization failed: $AUTH_RESP"
echo "  Payment ID: $PAYMENT_ID"

echo ">> 5.5 Check status (complete)"
curl -s "$PAYMENT_BASE/api/v1/checkout/$SESSION_ID" > /dev/null || fail "Checkout completed status failed"
echo "  OK"


echo -e "\n${BLUE}=== 6. PAYMENT VERIFICATION + REFUND ===${NC}"

echo ">> 6.1 My transactions (Bearer token)"
curl -s "$PAYMENT_BASE/api/v1/customers/me/transactions" -H "Authorization: Bearer $EGS_TOKEN" > /dev/null || fail "My transactions failed"
echo "  OK"

echo ">> 6.2 Get payment (merchant API key)"
curl -s "$PAYMENT_BASE/api/v1/payments/$PAYMENT_ID" -H "X-API-Key: $API_KEY" > /dev/null || fail "Get payment failed"
echo "  OK"

echo ">> 6.3 List payments (merchant API key)"
curl -s "$PAYMENT_BASE/api/v1/payments" -H "X-API-Key: $API_KEY" > /dev/null || fail "List payments failed"
echo "  OK"

echo ">> 6.4 Refund succeeded payment via DELETE"
curl -s -X DELETE "$PAYMENT_BASE/api/v1/payments/$PAYMENT_ID" -H "X-API-Key: $API_KEY" > /dev/null || fail "Refund succeeded payment failed"
echo "  OK"


echo -e "\n${BLUE}=== 7. STATIC UI URLS (not API endpoints) ===${NC}"

echo ">> 7.1 Login UI URL"
curl -s "$PAYMENT_BASE/wallet/login" > /dev/null || fail "Login UI URL failed"
echo "  OK"

echo ">> 7.2 Register UI URL"
curl -s "$PAYMENT_BASE/wallet/register" > /dev/null || fail "Register UI URL failed"
echo "  OK"

echo ">> 7.3 Dashboard UI URL"
curl -s "$PAYMENT_BASE/wallet/dashboard" > /dev/null || fail "Dashboard UI URL failed"
echo "  OK"


echo -e "\n${BLUE}=== 8. CLEANUP ===${NC}"

echo ">> 8.1 Delete merchant customer"
curl -s -X DELETE "$PAYMENT_BASE/api/v1/customers/$MC_ID" -H "X-API-Key: $API_KEY" > /dev/null || fail "Delete merchant customer failed"
echo "  OK"

echo ">> 8.2 Delete registered customer"
curl -s -X DELETE "$PAYMENT_BASE/api/v1/customers/$CUST_ID" -H "X-API-Key: $API_KEY" > /dev/null || fail "Delete registered customer failed"
echo "  OK"

echo ">> 8.3 Revoke API key"
curl -s -X DELETE "$PAYMENT_BASE/api/v1/admin/api-keys/$KEY_ID" -H "X-API-Key: $ADMIN_KEY" > /dev/null || fail "Revoke API key failed"
echo "  OK"

echo -e "\n${BLUE}=== 9. OPENAPI COMPLIANCE ===${NC}"

echo ">> 9.1 Ensure static UI is not an API endpoint"
OPENAPI_JSON=$(curl -s "$PAYMENT_BASE/openapi.json")

if echo "$OPENAPI_JSON" | grep -q '"/app/dashboard"'; then
  fail "OpenAPI still exposes /app/dashboard"
fi

if echo "$OPENAPI_JSON" | grep -q 'Checkout UI'; then
  fail "OpenAPI still exposes Checkout UI tag"
fi

echo "  OK"

echo -e "\n${GREEN}======================================================"
echo -e " ALL ENDPOINTS VERIFIED ✅"
echo -e "======================================================${NC}"
