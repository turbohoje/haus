#!/usr/bin/env bash
#
# Provision and deploy haus-tvsnap against the Cloudflare REST API.
#
# The haus box has no node, wrangler or terraform — only curl and python3 — so
# this drives api.cloudflare.com directly rather than following cf_metrics'
# terraform + wrangler pattern. It is idempotent: re-run it to push a worker.mjs
# change or rotate the shared key.
#
# Needs an API token (My Profile -> API Tokens -> Create Token) with:
#   Account | Workers R2 Storage  | Edit
#   Account | Workers Scripts     | Edit
#   Account | Account Settings    | Read
#
# Reads CF_API_TOKEN, CF_ACCOUNT_ID and API_KEY from .env beside this script.
# READ_KEY is optional; set it to also bind a read-only key.

set -euo pipefail

WD="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$WD/.env"
API="https://api.cloudflare.com/client/v4"

WORKER_NAME="haus-tvsnap"
BUCKET_NAME="haus-tvsnap"
COMPAT_DATE="2025-04-01"

[[ -f "$ENV_FILE" ]] || { echo "missing $ENV_FILE — copy env.example and fill it in" >&2; exit 1; }
# shellcheck disable=SC1090
set -a; source "$ENV_FILE"; set +a

for var in CF_API_TOKEN CF_ACCOUNT_ID API_KEY; do
  [[ -n "${!var:-}" ]] || { echo "$var is not set in $ENV_FILE" >&2; exit 1; }
done

auth=(-H "Authorization: Bearer $CF_API_TOKEN")

# Every endpoint here returns {"success":bool,"errors":[...]} — a 200 with
# success:false is common, so the status code alone is not enough.
check() {
  local body="$1" what="$2"
  if ! python3 -c "
import json, sys
d = json.load(sys.stdin)
if not d.get('success'):
    print(json.dumps(d.get('errors'), indent=2), file=sys.stderr)
    sys.exit(1)
" <<<"$body"; then
    echo "==> $what failed" >&2
    exit 1
  fi
}

# Deliberately not /user/tokens/verify: that endpoint only knows user-owned
# tokens and answers 1000 "Invalid API Token" for an account-owned one, even
# when the token works fine everywhere else. Reading the account instead proves
# the token and CF_ACCOUNT_ID together, which is what the rest of this needs.
echo "==> verifying token"
check "$(curl -sS "${auth[@]}" "$API/accounts/$CF_ACCOUNT_ID")" "token verify"

echo "==> creating R2 bucket $BUCKET_NAME"
bucket=$(curl -sS "${auth[@]}" -X POST "$API/accounts/$CF_ACCOUNT_ID/r2/buckets" \
  -H "Content-Type: application/json" \
  -d "{\"name\":\"$BUCKET_NAME\"}")
# 10004 = bucket already exists. Re-running the script is the normal path.
if ! grep -q '"success":true' <<<"$bucket" && ! grep -q '10004' <<<"$bucket"; then
  check "$bucket" "bucket create"
fi

echo "==> uploading worker $WORKER_NAME"
metadata=$(API_KEY="$API_KEY" READ_KEY="${READ_KEY:-}" BUCKET_NAME="$BUCKET_NAME" \
  COMPAT_DATE="$COMPAT_DATE" python3 -c "
import json, os
bindings = [
    {'type': 'r2_bucket',   'name': 'SNAP',    'bucket_name': os.environ['BUCKET_NAME']},
    {'type': 'secret_text', 'name': 'API_KEY', 'text': os.environ['API_KEY']},
]
# Left out entirely when unset, which keeps the worker single-key.
if os.environ['READ_KEY']:
    bindings.append({'type': 'secret_text', 'name': 'READ_KEY', 'text': os.environ['READ_KEY']})
print(json.dumps({
    'main_module': 'worker.mjs',
    'compatibility_date': os.environ['COMPAT_DATE'],
    'bindings': bindings,
}))")

check "$(curl -sS "${auth[@]}" -X PUT \
  "$API/accounts/$CF_ACCOUNT_ID/workers/scripts/$WORKER_NAME" \
  -F "metadata=$metadata;type=application/json" \
  -F "worker.mjs=@$WD/worker.mjs;type=application/javascript+module")" "worker upload"

echo "==> enabling workers.dev route"
check "$(curl -sS "${auth[@]}" -X POST \
  "$API/accounts/$CF_ACCOUNT_ID/workers/scripts/$WORKER_NAME/subdomain" \
  -H "Content-Type: application/json" -d '{"enabled":true}')" "subdomain enable"

subdomain=$(curl -sS "${auth[@]}" "$API/accounts/$CF_ACCOUNT_ID/workers/subdomain" \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['result']['subdomain'])")
worker_url="https://$WORKER_NAME.$subdomain.workers.dev"

# Fold the resolved URL back into .env so publish_snapshot.py needs no argument.
if grep -q '^WORKER_URL=' "$ENV_FILE"; then
  sed -i "s|^WORKER_URL=.*|WORKER_URL=$worker_url|" "$ENV_FILE"
else
  printf '\nWORKER_URL=%s\n' "$worker_url" >> "$ENV_FILE"
fi

echo
echo "deployed: $worker_url"
echo "WORKER_URL written to $ENV_FILE"
echo
echo "  ./publish_snapshot.py"
echo "  curl -sS -H \"X-API-Key: \$API_KEY\" $worker_url/snapshot"
