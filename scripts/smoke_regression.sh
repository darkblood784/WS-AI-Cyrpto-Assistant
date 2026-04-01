#!/usr/bin/env bash
set -euo pipefail

API_BASE="${API_BASE:-http://127.0.0.1:8010}"

echo "[1/9] health"
curl -fsS "${API_BASE}/health" >/dev/null

EMAIL="smoke_$(date +%s)_$RANDOM@example.com"
PASSWORD='StrongPass!123'

echo "[2/9] register ${EMAIL}"
REGISTER_JSON="$(curl -fsS -X POST "${API_BASE}/auth/register" \
  -H 'Content-Type: application/json' \
  -d "{\"email\":\"${EMAIL}\",\"password\":\"${PASSWORD}\"}")"

echo "[3/9] read verify token from backend logs"
TOKEN="$(docker compose logs backend --tail=2000 \
  | grep EMAIL_VERIFY \
  | grep "${EMAIL}" \
  | tail -n1 \
  | sed -E 's/.*token=([^ ]+).*/\1/')"

if [[ -z "${TOKEN}" ]]; then
  echo "ERROR: verification token not found in backend logs for ${EMAIL}" >&2
  exit 1
fi

echo "[4/9] verify email"
curl -fsS -X POST "${API_BASE}/auth/verify" \
  -H 'Content-Type: application/json' \
  -d "{\"token\":\"${TOKEN}\"}" >/dev/null

echo "[5/9] login"
TOKEN_JSON="$(curl -fsS -X POST "${API_BASE}/auth/login" \
  -H 'Content-Type: application/json' \
  -d "{\"email\":\"${EMAIL}\",\"password\":\"${PASSWORD}\"}")"
ACCESS_TOKEN="$(python - <<'PY' "${TOKEN_JSON}"
import json,sys
print(json.loads(sys.argv[1])["access_token"])
PY
)"

AUTH_HEADER=("Authorization: Bearer ${ACCESS_TOKEN}")

echo "[6/9] alias check: /auth/me vs /me"
AUTH_ME="$(curl -fsS -H "${AUTH_HEADER[0]}" "${API_BASE}/auth/me")"
ME_ALIAS="$(curl -fsS -H "${AUTH_HEADER[0]}" "${API_BASE}/me")"
python - <<'PY' "${AUTH_ME}" "${ME_ALIAS}"
import json,sys
a=json.loads(sys.argv[1]); b=json.loads(sys.argv[2])
assert a["id"] == b["id"], "id mismatch between /auth/me and /me"
assert a["email"] == b["email"], "email mismatch between /auth/me and /me"
print("  ok: /auth/me and /me match")
PY

echo "[7/9] entitlements schema check"
ENTS="$(curl -fsS -H "${AUTH_HEADER[0]}" "${API_BASE}/entitlements")"
python - <<'PY' "${ENTS}"
import json,sys
e=json.loads(sys.argv[1])
for k in ("plan_id","plan_code","plan_name","limits","features"):
    assert k in e, f"missing key: {k}"
for k in ("daily_messages_limit","monthly_messages_limit","per_minute_messages_limit","context_messages_limit","context_chars_limit"):
    assert k in e["limits"], f"missing limits.{k}"
for k in ("chat_basic","indicators_basic","indicators_advanced","strategy_builder","exports","alerts","long_term_memory"):
    assert k in e["features"], f"missing features.{k}"
print("  ok: entitlements payload includes limits+features")
PY

echo "[8/9] thread route aliases"
T1="$(curl -fsS -X POST "${API_BASE}/threads" \
  -H "${AUTH_HEADER[0]}" \
  -H 'Content-Type: application/json' \
  -d '{"title":"smoke-thread-1"}')"
T2="$(curl -fsS -X POST "${API_BASE}/chat/threads" \
  -H "${AUTH_HEADER[0]}" \
  -H 'Content-Type: application/json' \
  -d '{"title":"smoke-thread-2"}')"
THREAD1="$(python - <<'PY' "${T1}"
import json,sys; print(json.loads(sys.argv[1])["id"])
PY
)"
THREAD2="$(python - <<'PY' "${T2}"
import json,sys; print(json.loads(sys.argv[1])["id"])
PY
)"
curl -fsS -H "${AUTH_HEADER[0]}" "${API_BASE}/threads/${THREAD1}" >/dev/null
curl -fsS -H "${AUTH_HEADER[0]}" "${API_BASE}/chat/threads/${THREAD2}" >/dev/null
echo "  ok: thread aliases work"

echo "[9/9] usage increment + optional cache smoke"
USAGE_BEFORE="$(curl -fsS -H "${AUTH_HEADER[0]}" "${API_BASE}/usage")"
CHAT_RESP="$(curl -fsS -X POST "${API_BASE}/chat" \
  -H "${AUTH_HEADER[0]}" \
  -H 'Content-Type: application/json' \
  -d '{"message":"BTC price today?","mode":"chat"}')"
USAGE_AFTER="$(curl -fsS -H "${AUTH_HEADER[0]}" "${API_BASE}/usage")"
python - <<'PY' "${USAGE_BEFORE}" "${USAGE_AFTER}"
import json,sys
b=json.loads(sys.argv[1]); a=json.loads(sys.argv[2])
assert a["day"]["used"] == b["day"]["used"] + 1, "day usage did not increment by 1"
print("  ok: usage increments on chat")
PY

# Optional cache behavior test (depends on plan entitlements)
set +e
I1="$(curl -sS -X POST "${API_BASE}/chat" \
  -H "${AUTH_HEADER[0]}" \
  -H 'Content-Type: application/json' \
  -d '{"message":"ETH RSI on 1h","mode":"indicators_basic"}')"
if echo "${I1}" | python - <<'PY'
import json,sys
try:
    j=json.load(sys.stdin)
    raise SystemExit(0 if j.get("ok") else 1)
except Exception:
    raise SystemExit(1)
PY
then
  I2="$(curl -sS -X POST "${API_BASE}/chat" \
    -H "${AUTH_HEADER[0]}" \
    -H 'Content-Type: application/json' \
    -d '{"message":"ETH RSI on 1h","mode":"indicators_basic"}')"
  echo "${I2}" | python - <<'PY'
import json,sys
j=json.load(sys.stdin)
assert j.get("cache", {}).get("hit") is True, "expected cache.hit=true on repeated indicators request"
print("  ok: cache hit on repeated indicators request")
PY
else
  echo "  skip: indicators_basic cache check (mode not enabled for this user plan)"
fi
set -e

echo "ALL SMOKE CHECKS PASSED"
