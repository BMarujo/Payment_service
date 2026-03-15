#!/bin/bash
set -e

BASE="http://localhost:8000"
ADMIN_KEY="your-admin-api-key-here"

TEST_EMAIL="auto_wallet_$RANDOM@example.com"

echo "1. Registering a Digital Wallet User..."
REG_RESP=$(curl -s -X POST "$BASE/api/v1/auth/register" \
  -H "Content-Type: application/json" \
  -d "{\"name\": \"Auto User\", \"email\": \"$TEST_EMAIL\", \"password\": \"supersecretpassword\"}")

# It might fail if already registered, but let's just proceed to testing the checkout creation.

echo -e "\n2. Creating API Key..."
KEY_RESP=$(curl -s -X POST "$BASE/api/v1/admin/api-keys" -H "X-API-Key: $ADMIN_KEY" -H "Content-Type: application/json" -d '{"client_name":"Checkout Test"}')
API_KEY=$(echo "$KEY_RESP" | python3 -c "import sys, json; print(json.load(sys.stdin).get('raw_key', ''))")

if [ -z "$API_KEY" ]; then
    echo "Failed to create API key."
    echo $KEY_RESP
    exit 1
fi
echo "API Key: $API_KEY..."

echo -e "\n3. Creating Checkout Session..."
SESSION_RESP=$(curl -s -X POST "$BASE/api/v1/checkout/sessions" \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d "{
    \"customer_email\": \"$TEST_EMAIL\",
    \"customer_name\": \"Auto User\",
    \"line_items\": [{\"name\": \"Premium Pass\", \"quantity\": 1, \"price\": 9900}],
    \"success_url\": \"https://example.com/success\",
    \"cancel_url\": \"https://example.com/cancel\"
  }")

SESSION_ID=$(echo "$SESSION_RESP" | python3 -c "import sys, json; print(json.load(sys.stdin).get('session_id', ''))")
CHECKOUT_URL=$(echo "$SESSION_RESP" | python3 -c "import sys, json; print(json.load(sys.stdin).get('checkout_url', ''))")

if [ -z "$SESSION_ID" ]; then
    echo "Failed to create session."
    echo $SESSION_RESP
    exit 1
fi
echo "Session ID: $SESSION_ID"
echo "Checkout URL: $CHECKOUT_URL"

echo -e "\n4. Testing API: POST /checkout/sessions/{id}/authorize ..."
# This simulates what the browser does on submit
AUTH_RESP=$(curl -s -X POST "$BASE/api/v1/checkout/sessions/$SESSION_ID/authorize" \
  -H "Content-Type: application/json" \
  -d '{"password": "supersecretpassword"}')

STATUS=$(echo "$AUTH_RESP" | python3 -c "import sys, json; print(json.load(sys.stdin).get('status', ''))")
PAYMENT_ID=$(echo "$AUTH_RESP" | python3 -c "import sys, json; print(json.load(sys.stdin).get('payment_id', ''))")

if [ "$STATUS" != "succeeded" ]; then
    echo "Failed to authorize payment."
    echo $AUTH_RESP
    exit 1
fi
echo "Authorization Succeeded! Internal Payment ID: $PAYMENT_ID"
echo "End-to-end backend digital wallet integration OK!"
