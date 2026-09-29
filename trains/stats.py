"""Statistiche sui ritardi per linea e per treno."""
from collections import defaultdict
from datetime import timedelta

from django.utils import timezone

from .models import StopTime, Train

BUCKETS = [("In orario (≤1')", -999, 1), ("Lieve (2-5')", 2, 5), ("Medio (6-15')", 6, 15), ("Forte (>15')", 16, 9999)]
ON_TIME_MIN = 5  # soglia standard di puntualità dei treni regionali


def _rows(qs):
    """Restituisce tuple (data, ora_locale, stazione, sequence, train_number, ritardo_min) per le fermate rilevate."""
    out = []
    for sa, sd, aa, ad, day, name, seq, num in qs.values_list(
        "sched_arr", "sched_dep", "actual_arr", "actual_dep",
        "run__service_date", "station__name", "sequence", "run__train__number",
    ):
        if sa is not None:
            s, a = sa, aa
        else:
            s, a = sd, ad
        if s is None or a is None:
            continue
        out.append((day, timezone.localtime(s).hour, name, seq, num, round((a - s).total_seconds() / 60)))
    return out


def _avg(v):
    return round(sum(v) / len(v), 2) if v else None


def _kpi(delays):
    if not delays:
        return {"n": 0, "avg": None, "on_time_pct": None, "max": None}
    return {
        "n": len(delays),
        "avg": _avg(delays),
        "on_time_pct": round(100 * sum(1 for d in delays if d <= ON_TIME_MIN) / len(delays), 1),
        "max": max(delays),
    }


def line_stats(line, days=14):
    today = timezone.localdate()
    since = today - timedelta(days=days - 1)
    qs = StopTime.objects.filter(run__train__line=line, run__service_date__gte=since)
    rows = _rows(qs)
    delays = [r[5] for r in rows]

    by_day = defaultdict(list)
    by_hour = defaultdict(list)
    by_station = defaultdict(list)
    for day, hour, name, seq, num, d in rows:
        by_day[day].append(d)
        by_hour[hour].append(d)
        by_station[name].append(d)

    day_labels = [since + timedelta(days=i) for i in range(days)]
    # ordine geografico delle stazioni: prendi il treno con numero più basso
    order = []
    t = Train.objects.filter(line=line).order_by("number").first()
    if t:
        r = t.runs.order_by("-service_date").first()
        if r:
            order = [s.station.name for s in r.get_stops()]
    stations = [n for n in order if n in by_station] or sorted(by_station)

    buckets = []
    for label, lo, hi in BUCKETS:
        buckets.append({"label": label, "count": sum(1 for d in delays if lo <= d <= hi)})

    return {
        "line": line.code,
        "days": days,
        "kpi": _kpi(delays),
        "by_day": [
            {"date": d.isoformat(), "avg": _avg(by_day[d]), "on_time_pct": _kpi(by_day[d])["on_time_pct"]}
            for d in day_labels
        ],
        "by_hour": [{"hour": h, "avg": _avg(by_hour[h]), "n": len(by_hour[h])} for h in sorted(by_hour)],
        "by_station": [{"station": n, "avg": _avg(by_station[n]), "max": max(by_station[n])} for n in stations],
        "buckets": buckets,
    }


def train_history(train, exclude_date=None, days=14):
    """Ritardo medio storico del treno per fermata (sequence)."""
    since = timezone.localdate() - timedelta(days=days)
    qs = StopTime.objects.filter(run__train=train, run__service_date__gte=since)
    if exclude_date:
        qs = qs.exclude(run__service_date=exclude_date)
    per = defaultdict(list)
    for day, hour, name, seq, num, d in _rows(qs):
        per[seq].append(d)
    return {seq: _avg(v) for seq, v in per.items()}
