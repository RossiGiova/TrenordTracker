from datetime import date, datetime, timedelta

from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from . import stats
from .models import Line, Train, TrainRun


def _iso(dt):
    return dt.isoformat() if dt else None


def _stop_json(s, hist=None):
    return {
        "station": s.station.name,
        "sequence": s.sequence,
        "sched_arr": _iso(s.sched_arr),
        "sched_dep": _iso(s.sched_dep),
        "actual_arr": _iso(s.actual_arr),
        "actual_dep": _iso(s.actual_dep),
        "delay": s.delay_min,
        "reached": s.reached,
        "hist_delay": (hist or {}).get(s.sequence),
    }


def _run_json(run, now, detail=False, hist=None):
    stops = run.get_stops()
    pos = run.position(now)
    first, last = (stops[0], stops[-1]) if stops else (None, None)
    est = None
    if last and last.sched_arr:
        est = last.actual_arr or (last.sched_arr + timedelta(minutes=pos["delay"] or 0))
    data = {
        "id": run.id,
        "number": run.train.number,
        "line": run.train.line.code if run.train.line else None,
        "line_color": run.train.line.color if run.train.line else "#6c757d",
        "origin": first.station.name if first else None,
        "destination": last.station.name if last else None,
        "departure": _iso(first.sched_dep) if first else None,
        "sched_arrival": _iso(last.sched_arr) if last else None,
        "arrival": _iso(est),
        "arrival_is_actual": bool(last and last.actual_arr),
        "state": pos["state"],
        "position": pos["label"],
        "progress": pos["progress"],
        "delay": pos["delay"],
        "from_index": pos["from_index"],
        "to_index": pos["to_index"],
        "cancelled": run.cancelled,
        "updated_at": _iso(run.updated_at),
    }
    if detail:
        data["stops"] = [_stop_json(s, hist) for s in stops]
    return data


# ---------- Pagine ----------

def dashboard(request):
    return render(request, "trains/dashboard.html", {"lines": Line.objects.all()})


def line_detail(request, code):
    line = get_object_or_404(Line, code=code)
    trains = line.trains.select_related("origin", "destination")
    return render(request, "trains/line_detail.html", {"line": line, "lines": Line.objects.all(), "trains": trains})


def train_detail(request, number):
    train = get_object_or_404(Train.objects.select_related("line", "origin", "destination"), number=number)
    dates = list(train.runs.order_by("-service_date").values_list("service_date", flat=True)[:30])
    try:
        wanted = date.fromisoformat(request.GET.get("date", ""))
    except ValueError:
        wanted = timezone.localdate()
    run = train.runs.filter(service_date=wanted).first() or train.runs.order_by("-service_date").first()
    if run is None:
        raise Http404("Nessuna corsa per questo treno")
    return render(request, "trains/train_detail.html", {
        "train": train, "run": run, "dates": dates, "lines": Line.objects.all(),
        "is_today": run.service_date == timezone.localdate(),
    })


# ---------- API JSON ----------

def api_runs(request):
    now = timezone.now()
    qs = (TrainRun.objects.filter(service_date=timezone.localdate())
          .select_related("train__line").prefetch_related("stops__station"))
    line = request.GET.get("line")
    if line:
        qs = qs.filter(train__line__code=line)
    runs = [_run_json(r, now) for r in qs]
    runs.sort(key=lambda r: (r["departure"] or ""))
    return JsonResponse({"now": _iso(now), "runs": runs})


def api_run_detail(request, pk):
    run = get_object_or_404(TrainRun.objects.select_related("train__line"), pk=pk)
    hist = stats.train_history(run.train, exclude_date=run.service_date)
    return JsonResponse(_run_json(run, timezone.now(), detail=True, hist=hist))


def api_summary(request):
    """KPI di oggi per ogni linea + numero di treni in viaggio."""
    now = timezone.now()
    runs = (TrainRun.objects.filter(service_date=timezone.localdate())
            .select_related("train__line").prefetch_related("stops__station"))
    running = {}
    for r in runs:
        if r.train.line_id and r.position(now)["state"] in ("running", "at_station"):
            running[r.train.line_id] = running.get(r.train.line_id, 0) + 1
    out = []
    for line in Line.objects.all():
        k = stats.line_stats(line, days=1)["kpi"]
        out.append({"code": line.code, "name": line.name, "color": line.color,
                    "running": running.get(line.id, 0), **k})
    return JsonResponse({"lines": out})


def api_line_stats(request, code):
    line = get_object_or_404(Line, code=code)
    try:
        days = max(1, min(int(request.GET.get("days", 14)), 90))
    except ValueError:
        days = 14
    return JsonResponse(stats.line_stats(line, days))
