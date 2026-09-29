"""Salvataggio nel database dei dati restituiti dai provider (demo o reali)."""
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional

from django.db import transaction

from .linestyle import style_for

from trains.models import Line, Station, StopTime, Train, TrainRun


@dataclass
class StopData:
    station_code: str
    station_name: str
    sched_arr: Optional[datetime] = None
    sched_dep: Optional[datetime] = None
    actual_arr: Optional[datetime] = None
    actual_dep: Optional[datetime] = None


@dataclass
class RunData:
    number: str
    service_date: date
    stops: list = field(default_factory=list)
    category: str = ""
    line_code: str = ""
    line_name: str = ""
    line_color: str = ""
    line_order: int = 0
    origin_code: str = ""
    cancelled: bool = False
    operator: Optional[int] = None
    demo: bool = False


def _station(code, name):
    st, created = Station.objects.get_or_create(code=code, defaults={"name": name})
    if not created and name and st.name != name:
        st.name = name
        st.save(update_fields=["name"])
    return st


@transaction.atomic
def save_run(data: RunData, keep_line=True):
    """Crea/aggiorna treno, corsa e fermate. Le fermate vengono sostituite."""
    train, _ = Train.objects.get_or_create(number=data.number, defaults={"is_demo": data.demo})
    changed = False
    if train.is_demo != data.demo:
        if data.demo:
            return None  # i dati demo non sovrascrivono mai quelli reali
        # dati reali su un numero che era demo: si riparte puliti
        train.runs.all().delete()
        train.is_demo, changed = False, True
    if data.category and train.category != data.category:
        train.category, changed = data.category, True
    if data.origin_code and train.origin_code != data.origin_code:
        train.origin_code, changed = data.origin_code, True
    if data.line_code:
        name, color, order = style_for(data.line_code)
        line, _ = Line.objects.get_or_create(
            code=data.line_code,
            defaults={"name": data.line_name or name, "color": data.line_color or color,
                      "position": data.line_order or order},
        )
        if train.line_id != line.id:
            train.line, changed = line, True
    if data.stops:
        o = _station(data.stops[0].station_code, data.stops[0].station_name)
        d = _station(data.stops[-1].station_code, data.stops[-1].station_name)
        if train.origin_id != o.id or train.destination_id != d.id:
            train.origin, train.destination, changed = o, d, True
    if changed:
        train.save()

    run, _ = TrainRun.objects.get_or_create(train=train, service_date=data.service_date)
    if run.cancelled != data.cancelled:
        run.cancelled = data.cancelled
        run.save()
    run.stops.all().delete()
    StopTime.objects.bulk_create(
        StopTime(
            run=run,
            station=_station(s.station_code, s.station_name),
            sequence=i,
            sched_arr=s.sched_arr,
            sched_dep=s.sched_dep,
            actual_arr=s.actual_arr,
            actual_dep=s.actual_dep,
        )
        for i, s in enumerate(data.stops)
    )
    return run
