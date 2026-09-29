"""Aggiornatore dati reali: scopre i treni Trenord e ne aggiorna orari/ritardi da ViaggiaTreno."""
import logging
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

import requests
from django.conf import settings
from django.db import close_old_connections
from django.utils import timezone

from trains.models import Line, Train, TrainRun

from . import ingest, linestyle
from . import viaggiatreno as vt

log = logging.getLogger("trains.live")

# ---------- assegnazione della linea (S1, S5, ...) ----------
# ViaggiaTreno non riporta il nome della linea (le sigle sono solo "REG 16914"): si ricava dalla
# numerazione Trenord, verificata sui dati reali (es. 245xx = S5, 246xx = S6, 249xx = S9...).

_S_BY_PREFIX = {
    "241": "S1", "242": "S2", "243": "S13", "245": "S5", "246": "S6", "247": "S7", "248": "S8",
    "249": "S9", "250": "S11", "251": "S11", "252": "S11", "256": "S12",
}
# categorie che non sono Trenord/regionali: scartate
EXCLUDED_CATEGORIES = {"EC", "IC", "ICN", "FR", "FA", "FB", "EN", "ES*", "ESC", "EXP"}


def _norm(name):
    s = re.sub(r"[^A-Z0-9 ]", " ", (name or "").upper())
    return " ".join(s.split())


def infer_line(comp, stops, number=""):
    """Codice linea dalla sigla (se c'è) oppure dal numero del treno e dai capolinea."""
    m = vt._LINE_RE.match(comp or "")
    if m:
        return m.group(1).upper()
    if not stops:
        return ""
    num = str(number)
    ends = _norm(stops[0].station_name) + " | " + _norm(stops[-1].station_name)
    if len(num) == 5 and num[:3] in _S_BY_PREFIX:
        return _S_BY_PREFIX[num[:3]]
    if "MALPENSA" in ends:
        if "CADORNA" in ends:
            return "MXP1"
        if "CENTRALE" in ends and len(num) <= 5:
            return "MXP2"
    if "CADORNA" in ends and len(num) == 3:
        if num[0] == "7" and "CAMNAGO" in ends:
            return "S4"
        if num[0] == "8" and "SARONNO" in ends:
            return "S3"
    return ""


# ---------- aggiornatore ----------

class LiveUpdater:
    def __init__(self, operators=None, region=None, workers=None, hubs=None, only_lines=None):
        self.operators = set(settings.LIVE_OPERATORS if operators is None else operators)
        self.region = settings.LIVE_REGION if region is None else region
        self.workers = workers or settings.LIVE_WORKERS
        self.hubs = hubs
        self.only_lines = set(only_lines) if only_lines else None
        self.session = requests.Session()
        self._codes = None
        self._last_discover = 0.0
        self._purged = False
        vt.DUMP_DIR = getattr(settings, "LIVE_DEBUG_DIR", None)

    # -- scoperta --
    def station_codes(self):
        if self._codes is None:
            if self.hubs:
                self._codes = [c for c in (vt.resolve_station(h, self.session) for h in self.hubs) if c]
            else:
                self._codes = vt.region_stations(self.region, self.session)
            log.info("Stazioni da controllare: %d", len(self._codes))
        return self._codes

    def discover(self):
        now = timezone.now()
        today = timezone.localdate()
        midnight_ms = int(datetime.combine(today, datetime.min.time(), tzinfo=vt.TZ).timestamp() * 1000)
        codes = self.station_codes()

        def work(code):
            try:
                return vt.station_departures(code, now, self.session)
            except Exception:
                return None

        found, failed = {}, 0
        with ThreadPoolExecutor(max_workers=self.workers) as ex:
            for rows in ex.map(work, codes):
                if rows is None:
                    failed += 1
                    continue
                for t in rows:
                    num, org = t.get("numeroTreno"), t.get("codOrigine")
                    op = t.get("codiceCliente")
                    if not num or not org:
                        continue
                    if self.operators and op is not None and op not in self.operators:
                        continue
                    if (t.get("categoria") or "").strip() in EXCLUDED_CATEGORIES:
                        continue
                    found[str(num)] = (org, t.get("dataPartenzaTreno") or midnight_ms,
                                       (t.get("categoria") or "").strip())
        new = 0
        for num, (org, ts, cat) in found.items():
            train, created = Train.objects.get_or_create(number=num, defaults={"is_demo": False})
            if train.is_demo:  # numero usato dal simulatore: ora è un treno reale
                train.runs.all().delete()
                train.is_demo = False
            train.tracked, train.origin_code, train.run_ts = True, org, int(ts)
            train.discovered_on, train.category = today, cat or train.category
            train.save()
            new += created
        self._last_discover = time.time()
        log.info("Scoperta: %d treni %s da %d stazioni (%d nuovi, %d stazioni non raggiunte)",
                 len(found), "Trenord" if self.operators else "", len(codes), new, failed)
        if not found and codes:
            log.warning("Nessun treno trovato: controlla debug_samples/partenze_sample.json e la connessione.")

    # -- aggiornamento --
    def _needs_update(self, train, now, today):
        run = TrainRun.objects.filter(train=train, service_date__gte=today - timedelta(days=1)).order_by("-service_date").first()
        if run is None:
            return True
        if run.cancelled:
            return False
        stops = run.get_stops()
        if not stops:
            return True
        last = stops[-1]
        if last.actual_arr is not None:
            return False
        if last.sched_arr and last.sched_arr < now - timedelta(minutes=120):
            return False
        first = stops[0].sched_dep
        return not (first and first - now > timedelta(minutes=30))

    def update(self):
        now, today = timezone.now(), timezone.localdate()
        trains = [t for t in Train.objects.filter(tracked=True, is_demo=False, discovered_on__gte=today - timedelta(days=1))
                  if t.origin_code and t.run_ts and self._needs_update(t, now, today)]
        if not trains:
            log.info("Nessun treno da aggiornare in questo momento.")
            return

        def work(t):
            try:
                return t, vt.fetch_run(t.number, t.origin_code, t.run_ts, self.session), None
            except Exception as e:
                return t, None, e

        ok = gone = errors = other = 0
        with ThreadPoolExecutor(max_workers=self.workers) as ex:
            for t, run, err in ex.map(work, trains):
                if err:
                    errors += 1
                    if errors <= 3:
                        log.warning("Treno %s: errore %s", t.number, err)
                    continue
                if run is None:
                    gone += 1
                    continue
                if self.operators and run.operator is not None and run.operator not in self.operators:
                    t.tracked = False
                    t.save(update_fields=["tracked"])
                    other += 1
                    continue
                code = run.line_code or infer_line("", run.stops, run.number) or (t.line.code if t.line_id else "")
                if self.only_lines and code not in self.only_lines:
                    continue
                run.line_code = code
                ingest.save_run(run)
                ok += 1
        self._purge_demo(ok)
        log.info("Aggiornati %d treni (%d non disponibili, %d di altri operatori, %d errori) su %d",
                 ok, gone, other, errors, len(trains))

    def _purge_demo(self, ok):
        if ok and not self._purged and settings.LIVE_PURGE_DEMO:
            n = Train.objects.filter(is_demo=True).count()
            if n:
                Train.objects.filter(is_demo=True).delete()
                log.info("Rimossi %d treni demo: da ora il sito mostra solo dati reali.", n)
            self._purged = True

    def backfill_lines(self):
        """Assegna la linea ai treni reali già nel database che ancora non ce l'hanno."""
        n = 0
        for t in Train.objects.filter(is_demo=False, line__isnull=True):
            run = t.runs.order_by("-service_date").first()
            if run is None:
                continue
            stops = [ingest.StopData(s.station.code, s.station.name) for s in run.get_stops()]
            code = infer_line("", stops, t.number)
            if code:
                name, color, order = linestyle.style_for(code)
                t.line, _ = Line.objects.get_or_create(
                    code=code, defaults={"name": name, "color": color, "position": order})
                t.save(update_fields=["line"])
                n += 1
        if n:
            log.info("Linea assegnata a %d treni già presenti", n)

    def cycle(self):
        if not getattr(self, "_backfilled", False):
            linestyle.apply_styles()
            self.backfill_lines()
            self._backfilled = True
        if time.time() - self._last_discover > settings.LIVE_DISCOVER_EVERY:
            self.discover()
        self.update()

    def loop(self):
        interval = settings.LIVE_INTERVAL
        log.info("Aggiornamento dati reali attivo: ogni %d s.", interval)
        while True:
            t0 = time.time()
            try:
                self.cycle()
            except requests.RequestException as e:
                log.warning("ViaggiaTreno non raggiungibile o risposta di errore (%s). Riprovo al prossimo ciclo.", e)
            except Exception:
                log.exception("Errore durante l'aggiornamento (riprovo al prossimo ciclo)")
            finally:
                close_old_connections()
            time.sleep(max(interval - (time.time() - t0), 10))

    def start_thread(self):
        th = threading.Thread(target=self.loop, name="live-updater", daemon=True)
        th.start()
        return th
