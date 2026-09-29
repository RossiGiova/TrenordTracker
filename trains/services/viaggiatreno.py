"""Provider ViaggiaTreno (API non ufficiali di RFI/Trenitalia, usate anche dal sito viaggiatreno.it).

Attenzione: non è un'API documentata né garantita; i campi possono cambiare. Il codice è scritto in
modo difensivo. Serve accesso a Internet: eseguirlo dal tuo PC.
"""
import re
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

from .ingest import RunData, StopData

BASE = "http://www.viaggiatreno.it/infomobilita/resteasy/viaggiatreno"
TZ = ZoneInfo("Europe/Rome")
HEADERS = {"User-Agent": "Mozilla/5.0 (trenord-tracker)"}

# Stazioni "hub" da cui scoprire i treni (nomi risolti in codici a runtime).
DEFAULT_HUBS = [
    "MILANO CENTRALE", "MILANO CADORNA", "MILANO PORTA GARIBALDI", "MILANO LAMBRATE", "MILANO ROGOREDO", "MILANO BOVISA",
    "MILANO GRECO PIRELLI", "RHO", "MONZA", "SARONNO", "VARESE", "GALLARATE", "COMO SAN GIOVANNI",
    "LECCO", "TREVIGLIO", "LODI", "PAVIA", "NOVARA", "SEREGNO", "BERGAMO", "BRESCIA", "MELEGNANO",
]

_DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
# "S5 23480", "RE 2513", "REG 10905", "MXP1 ..." -> codice linea
_LINE_RE = re.compile(r"^\s*(S\d{1,2}|RE\d{0,2}|R\d{1,2}|MXP\d?)\b", re.I)


DUMP_DIR = None  # se impostato (Path), salva un esempio di risposta reale per facilitare la diagnosi


def _dump(name, data):
    if DUMP_DIR is None:
        return
    try:
        import json
        DUMP_DIR.mkdir(parents=True, exist_ok=True)
        f = DUMP_DIR / name
        if not f.exists():
            f.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError:
        pass


def _ts(ms):
    if not ms:
        return None
    return datetime.fromtimestamp(int(ms) / 1000, tz=TZ)


def _js_date(dt):
    """Formato che si aspetta l'endpoint 'partenze': 'Tue Sep 29 2026 18:44:00 GMT+0200'."""
    dt = dt.astimezone(TZ)
    off = dt.strftime("%z")
    return f"{_DAYS[dt.weekday()]} {_MONTHS[dt.month - 1]} {dt.day:02d} {dt.year} {dt:%H:%M:%S} GMT{off}"


def _get(session, path, **kw):
    s = session or requests
    r = s.get(f"{BASE}/{path}", headers=HEADERS, timeout=15, **kw)
    r.raise_for_status()
    return r


# ---------- Ricerca ----------

def search_station(prefix, session=None):
    """[(nome, codice)] delle stazioni che iniziano per 'prefix'."""
    r = _get(session, f"autocompletaStazione/{requests.utils.quote(prefix)}")
    out = []
    for line in r.text.strip().splitlines():
        if "|" in line:
            name, code = line.split("|", 1)
            out.append((name.strip(), code.strip()))
    return out


def resolve_station(name, session=None):
    """Codice stazione (es. S01700) dal nome; preferisce una corrispondenza esatta."""
    found = search_station(name, session)
    for n, c in found:
        if n.upper() == name.upper():
            return c
    return found[0][1] if found else None


def region_stations(region, session=None):
    """Codici di tutte le stazioni di una regione (1 = Lombardia)."""
    r = _get(session, f"elencoStazioni/{region}")
    if r.status_code == 204 or not r.content:
        return []
    out = []
    for st in r.json() or []:
        code = st.get("codiceStazione") or st.get("codStazione")
        if code:
            out.append(code)
    return out


def station_departures(code, when, session=None):
    """Lista grezza dei treni in partenza da una stazione (finestra di circa 90 minuti)."""
    r = _get(session, f"partenze/{code}/{requests.utils.quote(_js_date(when), safe='')}")
    if r.status_code == 204 or not r.content:
        return []
    try:
        rows = r.json()
    except ValueError:
        return []
    if isinstance(rows, list) and rows:
        _dump("partenze_sample.json", rows[:3])
    return rows if isinstance(rows, list) else []


def search_train(number, session=None):
    """Ritorna [(origin_code, origin_name, timestamp_ms), ...] per un numero treno."""
    r = _get(session, f"cercaNumeroTrenoTrenoAutocomplete/{number}")
    out = []
    for line in r.text.strip().splitlines():
        # formato: "10905 - MILANO CENTRALE|10905-S01700-1727820000000"
        try:
            label, key = line.split("|")
            _, origin_code, ts = key.split("-")
            out.append((origin_code, label.split(" - ", 1)[1].strip(), int(ts)))
        except (ValueError, IndexError):
            continue
    return out


# ---------- Andamento treno ----------

def parse_run(j, number, origin_code, ts_ms):
    fermate = j.get("fermate") or []
    if not fermate:
        return None
    stops = []
    for idx, f in enumerate(fermate):
        sa = _ts(f.get("arrivo_teorico"))
        sd = _ts(f.get("partenza_teorica"))
        prog = _ts(f.get("programmata"))
        # primo/ultimo stop hanno spesso solo "programmata"
        if sa is None and sd is None:
            if idx == 0:
                sd = prog
            else:
                sa = prog
        stops.append(StopData(
            station_code=f.get("id") or f.get("stazione", ""),
            station_name=(f.get("stazione") or "").title(),
            sched_arr=sa, sched_dep=sd,
            actual_arr=_ts(f.get("arrivoReale")),
            actual_dep=_ts(f.get("partenzaReale")),
        ))
    comp = j.get("compNumeroTreno") or ""
    m = _LINE_RE.match(comp)
    service_date = datetime.fromtimestamp(ts_ms / 1000, tz=TZ).date()
    return RunData(
        number=str(number), service_date=service_date, stops=stops,
        category=(j.get("categoria") or comp.split(" ")[0] or "").strip(),
        origin_code=origin_code,
        line_code=m.group(1).upper() if m else "",
        operator=j.get("codiceCliente"),
        cancelled=j.get("provvedimento") == 1 or j.get("tipoTreno") == "ST",
    )


def fetch_run(number, origin_code, ts_ms, session=None):
    r = _get(session, f"andamentoTreno/{origin_code}/{number}/{ts_ms}")
    if r.status_code == 204 or not r.content:
        return None  # treno non (più) disponibile, per esempio soppresso
    try:
        j = r.json()
    except ValueError:
        return None
    _dump("andamento_sample.json", j)
    return parse_run(j, number, origin_code, ts_ms)


def fetch_by_number(number, session=None):
    """Cerca il treno per numero e scarica la corsa più recente."""
    found = search_train(number, session)
    if not found:
        return None
    origin_code, _, ts = max(found, key=lambda x: x[2])
    return fetch_run(number, origin_code, ts, session)
