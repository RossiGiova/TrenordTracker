# Trenord Tracker

Sito Django + Bootstrap + Chart.js per seguire i treni: orario programmato, orario **reale** di arrivo/partenza
a ogni fermata, **tratta in cui si trova il treno** e grafici sui ritardi per ogni linea.

## Avvio (Windows, PowerShell)

```powershell
cd trenord
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python manage.py runserver
```
Apri http://127.0.0.1:8000/

`runserver` scarica da solo i **dati reali** dei treni Trenord da ViaggiaTreno (orari programmati e reali,
ritardi) ogni 3 minuti; nel terminale compaiono righe `[live]`. Al primo dato reale salvato i dati simulati
vengono cancellati. **Lo storico dei ritardi si costruisce solo mentre il server e' acceso** (ViaggiaTreno
non fornisce lo storico): i grafici per linea diventano significativi dopo giorni di funzionamento.

Impostazioni in `config/settings.py` (`LIVE_*`). Per non scaricare dati: `runserver --no-live`.

## Solo per prove: simulazione
`python manage.py update_trains --provider demo --reset --history-days 14` genera treni e ritardi FINTI.
`python manage.py fetch_timetable` usa orari reali con ritardi comunque simulati. Non servono per il sito reale.

## Produzione
Per tenerlo acceso 24h su Linux (systemd, gunicorn, port forwarding) vedi **DEPLOY.md**.

## Pagine
- `/` - treni di oggi: posizione (in stazione / in tratta A -> B), avanzamento, arrivo programmato, arrivo stimato/reale, ritardo; filtri per linea e stato; KPI per linea.
- `/treno/<numero>/` - timeline fermate, orari programmati vs reali, grafico del ritardo per fermata (con media storica).
- `/linea/<codice>/` - grafici: ritardo medio e puntualita giornaliera, distribuzione ritardi, ritardo per stazione e per fascia oraria (1/7/14/30 giorni).
- `/api/...` - endpoint JSON usati dai grafici.

## Come funzionano i dati reali
1. **Scoperta** (ogni 30 min): per ogni stazione lombarda legge i treni in partenza e tiene quelli Trenord (`codiceCliente` 63).
2. **Aggiornamento** (ogni 3 min): per ogni treno in circolazione scarica `andamentoTreno` (fermate, orari
   programmati e reali) e lo salva. Salta i treni arrivati, soppressi o in partenza tra oltre 30 minuti.
3. **Linea** (S5, S9...): ViaggiaTreno non la riporta; si ricava dal numero del treno (es. 245xx = S5).
4. In `debug_samples/` ci sono esempi di risposte reali, utili per la diagnosi.

Fonte: API non ufficiali di ViaggiaTreno (github.com/MarcoBuster/railway-opendata, github.com/dltmtt/viaggiatreno-api).

## Struttura
- `trains/models.py` - Line, Station, Train, TrainRun (corsa del giorno), StopTime (orari prog./reali), calcolo posizione.
- `trains/services/` - `ingest.py` (salvataggio), `demo.py` (simulatore), `viaggiatreno.py` (dati reali).
- `trains/stats.py` - statistiche ritardi (puntuale = ritardo <= 5 minuti).
- `trains/templates`, `trains/static` - Bootstrap 5 + Chart.js 4 (da CDN).

## Note
- Progetto non ufficiale: non e' affiliato a Trenord, RFI o Trenitalia. I dati arrivano dalle API non ufficiali di
  ViaggiaTreno, che possono cambiare o limitare l'accesso senza preavviso. Usalo con richieste moderate.
- Il database (`db.sqlite3`), i campioni di risposta (`debug_samples/`) e `timetable.json` sono locali e non vanno
  nel repository (sono nel `.gitignore`). Nessuna chiave o password e' salvata nel codice: in produzione la chiave
  segreta sta in `/etc/trenord.env` (vedi DEPLOY.md).
