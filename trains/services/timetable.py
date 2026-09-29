"""Scarica da ViaggiaTreno gli ORARI PROGRAMMATI reali dei treni Trenord e li salva in timetable.json.

I ritardi restano simulati (vedi demo.py): qui si prendono solo numeri treno, linee, fermate e orari.
"""
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

import requests

from . import viaggiatreno as vt
from .live import EXCLUDED_CATEGORIES, infer_line

log = logging.getLogger("trains.live")


def _minutes(dt, midnight):
    return None if dt is None else int(round((dt - midnight).total_seconds() / 60))


def collect(hubs=None, region=1, operators=(63,), start=4, end=23, step=60, workers=6, session=None):
    """Ritorna la lista di treni [{number, line, category, stops:[{code,name,arr,dep}]}]."""
    session = session or requests.Session()
    if hubs:
        codes = [c for c in (vt.resolve_station(h, session) for h in hubs) if c]
    else:
        codes = vt.region_stations(region, session)
    day0 = datetime.now(vt.TZ).replace(hour=0, minute=0, second=0, microsecond=0)
    whens = [day0 + timedelta(hours=h) for h in range(start, end + 1, max(step // 60, 1))]
    log.info("Cerco treni: %d stazioni x %d fasce orarie", len(codes), len(whens))

    def dep(task):
        code, when = task
        try:
            return vt.station_departures(code, when, session)
        except Exception:
            return []

    found = {}
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for rows in ex.map(dep, [(c, w) for c in codes for w in whens]):
            for t in rows:
                num, org = t.get("numeroTreno"), t.get("codOrigine")
                op = t.get("codiceCliente")
                if not num or not org or (operators and op is not None and op not in operators):
                    continue
                if (t.get("categoria") or "").strip() in EXCLUDED_CATEGORIES:
                    continue
                found.setdefault(str(num), (org, t.get("dataPartenzaTreno") or int(day0.timestamp() * 1000)))
    log.info("Trovati %d treni: scarico le fermate", len(found))

    def detail(item):
        num, (org, ts) = item
        try:
            return vt.fetch_run(num, org, int(ts), session)
        except Exception:
            return None

    trains = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for run in ex.map(detail, list(found.items())):
            if run is None or run.cancelled or len(run.stops) < 2:
                continue
            if operators and run.operator is not None and run.operator not in operators:
                continue
            midnight = datetime.combine(run.service_date, datetime.min.time(), tzinfo=vt.TZ)
            stops = [{"code": s.station_code, "name": s.station_name,
                      "arr": _minutes(s.sched_arr, midnight), "dep": _minutes(s.sched_dep, midnight)}
                     for s in run.stops if s.sched_arr or s.sched_dep]
            if len(stops) < 2:
                continue
            trains.append({"number": run.number, "category": run.category,
                           "line": run.line_code or infer_line("", run.stops, run.number), "stops": stops})
    trains.sort(key=lambda t: t["number"])
    return trains


def save(trains, path):
    data = {"generated": datetime.now(vt.TZ).isoformat(timespec="seconds"), "trains": trains}
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
