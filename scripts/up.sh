#!/usr/bin/env bash
# Start the local Snipe-IT, create its admin and an API token the first time, and write the token to .env.
# Every secret is generated here and stays in the git-ignored files docker/.env and .env; none is printed.
set -euo pipefail
cd "$(dirname "$0")/.."
rnd() { openssl rand -hex 16; }

if [ ! -f docker/.env ]; then
  db_pw=$(rnd)
  cat > docker/.env <<ENV
APP_ENV=production
APP_DEBUG=false
APP_KEY=base64:$(openssl rand -base64 32)
APP_URL=http://localhost:8088
APP_TIMEZONE=UTC
APP_LOCALE=en-US
DB_CONNECTION=mariadb
DB_HOST=db
DB_PORT=3306
DB_DATABASE=snipeit
DB_USERNAME=snipeit
DB_PASSWORD=$db_pw
MYSQL_ROOT_PASSWORD=$(rnd)
MAIL_MAILER=log
API_TOKEN_EXPIRATION_YEARS=40
API_THROTTLE_PER_MINUTE=1000
ADMIN_PASSWORD=$(rnd)
ENV
fi

dc() { docker compose -f docker/compose.yml --env-file docker/.env "$@"; }
app() { dc exec -T -u docker app "$@"; }
dc up -d
echo "waiting for Snipe-IT…"
for _ in $(seq 1 90); do
  curl -fsS -o /dev/null http://127.0.0.1:8088/login 2>/dev/null && break
  sleep 2
done

if ! grep -q '^SNIPEIT_TOKEN=' .env 2>/dev/null; then
  pw=$(grep '^ADMIN_PASSWORD=' docker/.env | cut -d= -f2)
  # The image doesn't make API (Passport) keys on its own: make them and a personal-access client first.
  app php artisan passport:keys --force >/dev/null
  app php artisan passport:client --personal --name=mojood-mcp --no-interaction >/dev/null
  app php artisan snipeit:create-admin --first_name=Demo --last_name=Admin \
    --email=admin@harbor-trading.example --username=admin --password="$pw" >/dev/null 2>&1 || true
  app php artisan tinker --execute "$(sed 1d scripts/settings.php)" >/dev/null
  token=$(app php artisan tinker --execute \
    'echo \App\Models\User::where("username","admin")->first()->createToken("mojood-mcp")->accessToken;' | tail -1)
  case "$token" in eyJ*) ;; *) echo "could not create the API token" >&2; exit 1 ;; esac
  { echo "SNIPEIT_URL=http://127.0.0.1:8088"; echo "SNIPEIT_TOKEN=$token"; } >> .env
  echo "admin and API token created (in docker/.env and .env)"
fi
echo "Snipe-IT is up at http://localhost:8088"
