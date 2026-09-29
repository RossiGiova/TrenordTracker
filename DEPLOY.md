# Produzione su un portatile Linux (CachyOS/Arch) sempre acceso

Due servizi systemd: **trenord-web** (il sito, gunicorn) e **trenord-live** (scarica i dati reali da
ViaggiaTreno ogni 3 minuti). Partono all'avvio del portatile e si riavviano da soli se si bloccano.

## Installazione
```bash
sudo pacman -S --needed python git      # se manca
# copia la cartella del progetto sul portatile (git clone, scp, chiavetta...), poi:
cd trenord
bash deploy/install.sh
```
Lo script crea l'ambiente Python, il database, i file statici, il file `/etc/trenord.env` (chiave segreta
casuale, host consentiti) e attiva i due servizi. Alla fine stampa l'indirizzo: `http://IP-DEL-PORTATILE:8000/`.

Comandi utili:
```bash
systemctl status trenord-web trenord-live
journalctl -u trenord-live -f       # cosa sta scaricando ([live] Aggiornati N treni)
sudo systemctl restart trenord-web trenord-live
```

## Renderlo raggiungibile da fuori (tre modi, dal piu' sicuro)
1. **Tailscale o Cloudflare Tunnel** (consigliato): nessuna porta aperta sul router. Con Cloudflare Tunnel
   puntato a `http://localhost:8000` ottieni anche l'HTTPS. In `/etc/trenord.env` metti `BIND=127.0.0.1:8000`,
   `DJANGO_HTTPS=1` e aggiungi il tuo dominio a `DJANGO_ALLOWED_HOSTS`.
2. **Port forwarding + HTTPS con Caddy**: serve un dominio (anche gratuito, es. DuckDNS) che punta al tuo IP.
   Inoltra le porte 80 e 443 del router al portatile e usa `deploy/Caddyfile.example`
   (`sudo pacman -S caddy`). In `/etc/trenord.env`: `BIND=127.0.0.1:8000`, `DJANGO_HTTPS=1`.
3. **Port forwarding diretto sulla 8000**: funziona, ma e' HTTP senza cifratura e mostra il server a
   internet. Aggiungi IP pubblico/dominio a `DJANGO_ALLOWED_HOSTS` e riavvia i servizi.

Dopo ogni modifica di `/etc/trenord.env`: `sudo systemctl restart trenord-web`.

Note di sicurezza: il sito e' in sola lettura (nessun login) e l'area `/admin/` e' chiusa in produzione.
Tieni comunque il sistema aggiornato e, se lo esponi, il firewall attivo (`sudo ufw allow 8000` o 80/443).

## Manutenzione
- **Backup**: tutto lo storico e' in `db.sqlite3` (fermare i servizi o usare `sqlite3 db.sqlite3 ".backup copia.db"`).
- **Aggiornare il codice**: sostituisci i file, poi `bash deploy/install.sh` (non tocca il database) e riavvia.
- **Portatile**: disattiva la sospensione alla chiusura del coperchio (`HandleLidSwitch=ignore` in
  `/etc/systemd/logind.conf`) e la sospensione automatica, altrimenti i dati si fermano.
- Rete/luce assenti: al ritorno il programma riparte da solo, ma i treni conclusi nel frattempo (oltre ~2 ore)
  non si recuperano.
