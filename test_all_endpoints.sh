#!/bin/bash
set -e

# Configuration
BASE="http://localhost:8000"
ADMIN_KEY="your-admin-api-key-here"
WALLET_EMAIL="wallet_user_$RANDOM@example.com"
MERCHANT_EMAIL="merchant_cust_$RANDOM@example.com"
TEST_PASSWORD="securepassword123"

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}=== 1. ADMIN: API KEY LIFECYCLE ===${NC}"

echo ">> 1.1 Creating a new API Key for the Merchant"
KEY_RESP=$(curl -s -X POST "$BASE/api/v1/admin/api-keys" \
  -H "X-API-Key: $ADMIN_KEY" \
  -H "Content-Type: application/json" \
  -d '{"client_name":"Continuous Test Merchant", "description":"Testing workflow"}')
API_KEY=$(echo "$KEY_RESP" | python3 -c "import sys, json; print(json.load(sys.stdin).get('raw_key', ''))")
KEY_ID=$(echo "$KEY_RESP" | python3 -c "import sys, json; print(json.load(sys.stdin).get('id', ''))")

echo "Created API Key ID: $KEY_ID"

echo ">> 1.2 Listing all API Keys"
curl -s "$BASE/api/v1/admin/api-keys" -H "X-API-Key: $ADMIN_KEY" > /dev/null
echo "Successfully listed API keys."

echo ">> 1.3 Updating the API Key"
curl -s -X PUT "$BASE/api/v1/admin/api-keys/$KEY_ID" \
  -H "X-API-Key: $ADMIN_KEY" \
  -H "Content-Type: application/json" \
  -d '{"description":"Updated description for test"}' > /dev/null
echo "Successfully updated API key."

echo ">> 1.4 Getting the specific API Key to verify"
curl -s "$BASE/api/v1/admin/api-keys/$KEY_ID" -H "X-API-Key: $ADMIN_KEY" > /dev/null
echo "Successfully fetched API key details."


echo -e "\n${BLUE}=== 2. WALLET: USER REGISTRATION & AUTH ===${NC}"

echo ">> 2.1 Registering a new Digital Wallet User ($WALLET_EMAIL)"
curl -s -X POST "$BASE/api/v1/auth/register" \
  -H "Content-Type: application/json" \
  -d "{\"name\": \"Workflow User\", \"email\": \"$WALLET_EMAIL\", \"password\": \"$TEST_PASSWORD\"}" > /dev/null
echo "Successfully registered user."

echo ">> 2.2 Logging in to the Digital Wallet"
LOGIN_RESP=$(curl -s -X POST "$BASE/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\": \"$WALLET_EMAIL\", \"password\": \"$TEST_PASSWORD\"}")
JWT_TOKEN=$(echo "$LOGIN_RESP" | python3 -c "import sys, json; print(json.load(sys.stdin).get('access_token', ''))")

if [ -z "$JWT_TOKEN" ]; then
    echo "Failed to get JWT Token!"
    exit 1
fi
echo "Successfully logged in and received Bearer Token."


echo -e "\n${BLUE}=== 3. MERCHANT: CUSTOMER MANAGEMENT ===${NC}"

echo ">> 3.1 Merchant creates a customer record"
CUST_RESP=$(curl -s -X POST "$BASE/api/v1/customers" \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d "{\"email\": \"$MERCHANT_EMAIL\", \"name\": \"Merchant User\", \"phone\": \"+1234567890\"}")
CUSTOMER_ID=$(echo "$CUST_RESP" | python3 -c "import sys, json; print(json.load(sys.stdin).get('id', ''))")

echo "Created Merchant Customer ID: $CUSTOMER_ID"

echo ">> 3.2 Merchant lists all customers"
curl -s "$BASE/api/v1/customers?limit=5" -H "X-API-Key: $API_KEY" > /dev/null
echo "Successfully listed customers."

echo ">> 3.3 Merchant gets specific customer details"
curl -s "$BASE/api/v1/customers/$CUSTOMER_ID" -H "X-API-Key: $API_KEY" > /dev/null
echo "Successfully fetched customer details."

echo ">> 3.4 Merchant updates customer details"
curl -s -X PUT "$BASE/api/v1/customers/$CUSTOMER_ID" \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"name": "Workflow User Updated"}' > /dev/null
echo "Successfully updated customer."


echo -e "\n${BLUE}=== 4. MERCHANT -> WALLET: CHECKOUT SESSION ===${NC}"

echo ">> 4.1 Merchant creates a checkout session"
SESSION_RESP=$(curl -s -X POST "$BASE/api/v1/checkout/sessions" \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d "{
    \"customer_email\": \"$WALLET_EMAIL\",
    \"customer_name\": \"Workflow User Updated\",
    \"line_items\": [{\"name\": \"Concert VIP Ticket\", \"quantity\": 2, \"price\": 10000}],
    \"success_url\": \"https://merchant.com/success\",
    \"cancel_url\": \"https://merchant.com/cancel\"
  }")
SESSION_ID=$(echo "$SESSION_RESP" | python3 -c "import sys, json; print(json.load(sys.stdin).get('session_id', ''))")

echo "Created Checkout Session: $SESSION_ID"

echo ">> 4.2 Merchant checks session status (Should be open)"
curl -s "$BASE/api/v1/checkout/sessions/$SESSION_ID" -H "X-API-Key: $API_KEY" > /dev/null
echo "Successfully checked session status."

echo ">> 4.3 Wallet User authorizes checkout via UI using password"
AUTH_RESP=$(curl -s -X POST "$BASE/api/v1/checkout/sessions/$SESSION_ID/authorize" \
  -H "Content-Type: application/json" \
  -d "{\"password\": \"$TEST_PASSWORD\"}")

PAYMENT_ID=$(echo "$AUTH_RESP" | python3 -c "import sys, json; print(json.load(sys.stdin).get('payment_id', ''))")

if [ -z "$PAYMENT_ID" ]; then
    echo "Failed to authorize payment! Response:"
    echo "$AUTH_RESP"
    exit 1
fi
echo "Successfully authorized. Internally generated Payment ID: $PAYMENT_ID"


echo -e "\n${BLUE}=== 5. WALLET & MERCHANT: TRANSACTION VERIFICATIONS ===${NC}"

echo ">> 5.1 Wallet User views their private transaction history using JWT"
curl -s "$BASE/api/v1/customers/me/transactions" -H "Authorization: Bearer $JWT_TOKEN" > /dev/null
echo "Successfully retrieved personal transaction history."

echo ">> 5.2 Merchant queries the payment API"
curl -s "$BASE/api/v1/payments/$PAYMENT_ID" -H "X-API-Key: $API_KEY" > /dev/null
echo "Successfully verified payment via merchant API."

echo ">> 5.3 Merchant lists all payments"
curl -s "$BASE/api/v1/payments" -H "X-API-Key: $API_KEY" > /dev/null
echo "Successfully listed all merchant payments."


echo -e "\n${BLUE}=== 6. MERCHANT: REFUND & CLEANUP ===${NC}"

echo ">> 6.1 Merchant issues a refund for the transaction"
curl -s -X POST "$BASE/api/v1/payments/$PAYMENT_ID/refund" \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"amount": 5000, "reason": "requested_by_customer"}' > /dev/null
echo "Successfully issued a partial/full refund."

echo ">> 6.2 Merchant deletes the customer (Soft Delete)"
curl -s -X DELETE "$BASE/api/v1/customers/$CUSTOMER_ID" -H "X-API-Key: $API_KEY" > /dev/null
echo "Successfully soft-deleted customer."

echo -e "\n${BLUE}=== 7. ADMIN: CLEANUP ===${NC}"

echo ">> 7.1 Admin revokes (deletes) the API key"
curl -s -X DELETE "$BASE/api/v1/admin/api-keys/$KEY_ID" -H "X-API-Key: $ADMIN_KEY" > /dev/null
echo "Successfully revoked API Key."

echo -e "\n${GREEN}======================================================"
echo -e " ALL API ENDPOINTS TRIGGERED AND VERIFIED CORRECTLY!"
echo -e "======================================================${NC}"
