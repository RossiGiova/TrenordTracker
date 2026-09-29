#!/usr/bin/env bash
# Installa Trenord Tracker come servizio su Linux con systemd (testato per Arch/CachyOS).
# Uso, dalla cartella del progetto:   bash deploy/install.sh
set -euo pipefail

APP="$(cd "$(dirname "$0")/.." && pwd)"
USER_NAME="${SUDO_USER:-$USER}"
ENVFILE=/etc/trenord.env

command -v python >/dev/null || { echo "Manca python: sudo pacman -S python"; exit 1; }

echo "==> Ambiente virtuale e dipendenze"
python -m venv "$APP/.venv"
"$APP/.venv/bin/pip" install -q --upgrade pip
"$APP/.venv/bin/pip" install -q -r "$APP/requirements.txt"

if [ ! -f "$ENVFILE" ]; then
  echo "==> Creo $ENVFILE"
  SECRET="$("$APP/.venv/bin/python" -c 'import secrets; print(secrets.token_urlsafe(50))')"
  HOSTS="localhost,127.0.0.1,$(hostname),$(hostname -I 2>/dev/null | tr ' ' ',' | sed 's/,$//')"
  TMP="$(mktemp)"
  cat > "$TMP" <<ENV
DJANGO_DEBUG=0
DJANGO_SECRET_KEY=$SECRET
# host da cui il sito e' raggiungibile (aggiungi qui il tuo dominio o IP pubblico):
DJANGO_ALLOWED_HOSTS=$HOSTS
# 0.0.0.0:8000 = raggiungibile dalla rete locale/port forwarding; 127.0.0.1:8000 = solo dietro Caddy/tunnel
BIND=0.0.0.0:8000
# metti 1 solo se il sito e' dietro HTTPS (Caddy, Cloudflare Tunnel...)
DJANGO_HTTPS=0
ENV
  sudo install -m 600 -o root -g root "$TMP" "$ENVFILE"
  rm -f "$TMP"
fi

echo "==> Database e file statici"
set -a; eval "$(sudo cat "$ENVFILE" | grep -E '^[A-Z_]+=' )"; set +a
cd "$APP"
"$APP/.venv/bin/python" manage.py migrate --noinput
"$APP/.venv/bin/python" manage.py collectstatic --noinput -v0

echo "==> Servizi systemd"
for u in trenord-web trenord-live; do
  sed -e "s|@USER@|$USER_NAME|g" -e "s|@APP@|$APP|g" "$APP/deploy/$u.service" | sudo tee "/etc/systemd/system/$u.service" >/dev/null
done
sudo systemctl daemon-reload
sudo systemctl enable --now trenord-web trenord-live

echo
echo "Fatto. Sito: http://$(hostname -I | awk '{print $1}'):8000/"
echo "Log dati reali:  journalctl -u trenord-live -f"
echo "Log sito:        journalctl -u trenord-web -f"
