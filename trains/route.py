"""Percorso di una linea (elenco ordinato delle stazioni), ricavato dalle corse recenti."""
import time
from datetime import timedelta

from django.utils import timezone

from .models import TrainRun

_CACHE = {}
TTL = 600  # secondi


def build_route(line):
    since = timezone.localdate() - timedelta(days=2)
    runs = (TrainRun.objects.filter(train__line=line, service_date__gte=since)
            .prefetch_related("stops__station")[:400])
    seqs = []
    for r in runs:
        st = [(s.station.code, s.station.name) for s in sorted(r.stops.all(), key=lambda x: x.sequence)]
        if len(st) >= 2:
            seqs.append(st)
    if not seqs:
        return []
    seqs.sort(key=len, reverse=True)
    order = [c for c, _ in seqs[0]]
    names = dict(seqs[0])
    for st in seqs[1:]:
        common = [order.index(c) for c, _ in st if c in order]
        inc = sum(b > a for a, b in zip(common, common[1:]))
        dec = sum(b < a for a, b in zip(common, common[1:]))
        if dec > inc:  # corsa nel verso opposto: la si legge al contrario
            st = st[::-1]
        prev = -1
        for c, n in st:
            if c in order:
                prev = order.index(c)
            else:
                order.insert(prev + 1, c)
                names[c] = n
                prev += 1
    return [{"code": c, "name": names[c]} for c in order]


def get_route(line, force=False):
    hit = _CACHE.get(line.id)
    if hit and not force and time.time() - hit[0] < TTL:
        return hit[1]
    route = build_route(line)
    _CACHE[line.id] = (time.time(), route)
    return route
