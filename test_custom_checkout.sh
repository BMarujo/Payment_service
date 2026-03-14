#!/bin/bash
set -e

BASE="http://localhost:8000"
ADMIN_KEY="your-admin-api-key-here"

echo "1. Creating API Key..."
KEY_RESP=$(curl -s -X POST "$BASE/api/v1/admin/api-keys" -H "X-API-Key: $ADMIN_KEY" -H "Content-Type: application/json" -d '{"client_name":"Checkout Test"}')
API_KEY=$(echo "$KEY_RESP" | python3 -c "import sys, json; print(json.load(sys.stdin).get('raw_key', ''))")

if [ -z "$API_KEY" ]; then
    echo "Failed to create API key."
    echo $KEY_RESP
    exit 1
fi
echo "API Key: $API_KEY..."

echo -e "\n2. Creating Checkout Session..."
SESSION_RESP=$(curl -s -X POST "$BASE/api/v1/checkout/sessions" \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "customer_email": "auto@example.com",
    "customer_name": "Auto User",
    "line_items": [{"name": "Premium Pass", "quantity": 1, "price": 9900}],
    "success_url": "https://example.com/success",
    "cancel_url": "https://example.com/cancel"
  }')

SESSION_ID=$(echo "$SESSION_RESP" | python3 -c "import sys, json; print(json.load(sys.stdin).get('session_id', ''))")
CHECKOUT_URL=$(echo "$SESSION_RESP" | python3 -c "import sys, json; print(json.load(sys.stdin).get('checkout_url', ''))")

if [ -z "$SESSION_ID" ]; then
    echo "Failed to create session."
    echo $SESSION_RESP
    exit 1
fi
echo "Session ID: $SESSION_ID"
echo "Checkout URL: $CHECKOUT_URL"

echo -e "\n3. Testing API: POST /checkout/sessions/{id}/pay ..."
# This simulates what the browser does on submit
PAY_RESP=$(curl -s -X POST "$BASE/api/v1/checkout/sessions/$SESSION_ID/pay" \
  -H "Content-Type: application/json")

CLIENT_SECRET=$(echo "$PAY_RESP" | python3 -c "import sys, json; print(json.load(sys.stdin).get('client_secret', ''))")

if [ -z "$CLIENT_SECRET" ]; then
    echo "Failed to process payment."
    echo $PAY_RESP
    exit 1
fi
echo "Client Secret generated: $CLIENT_SECRET"
echo "Backend checkout integration OK!"
