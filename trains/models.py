from datetime import timedelta

from django.db import models
from django.utils import timezone


class Line(models.Model):
    code = models.CharField(max_length=10, unique=True)
    name = models.CharField(max_length=120, blank=True)
    color = models.CharField(max_length=7, default="#0d6efd")
    position = models.PositiveSmallIntegerField("ordine", default=0)

    class Meta:
        ordering = ["position", "code"]

    def __str__(self):
        return self.code


class Station(models.Model):
    code = models.CharField("codice", max_length=20, unique=True)
    name = models.CharField(max_length=120)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Train(models.Model):
    number = models.CharField("numero", max_length=10, unique=True)
    category = models.CharField(max_length=10, blank=True)
    line = models.ForeignKey(Line, null=True, blank=True, on_delete=models.SET_NULL, related_name="trains")
    origin = models.ForeignKey(Station, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    destination = models.ForeignKey(Station, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    # Per il provider ViaggiaTreno: codice stazione di origine (es. S01700)
    origin_code = models.CharField(max_length=20, blank=True)
    tracked = models.BooleanField("monitorato", default=False)
    is_demo = models.BooleanField("dato demo", default=False)
    # Dati per aggiornare la corsa su ViaggiaTreno senza cercarla ogni volta
    run_ts = models.BigIntegerField(null=True, blank=True)          # mezzanotte del giorno di servizio (ms)
    discovered_on = models.DateField(null=True, blank=True)         # ultimo giorno in cui è stato "visto" in stazione

    class Meta:
        ordering = ["number"]

    def __str__(self):
        return f"{self.number} ({self.line or self.category})"


class TrainRun(models.Model):
    """Una corsa di un treno in un determinato giorno."""

    train = models.ForeignKey(Train, on_delete=models.CASCADE, related_name="runs")
    service_date = models.DateField(db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    cancelled = models.BooleanField(default=False)

    class Meta:
        unique_together = [("train", "service_date")]
        ordering = ["-service_date", "train__number"]

    def __str__(self):
        return f"{self.train.number} {self.service_date}"

    def get_stops(self):
        if not hasattr(self, "_stops"):
            self._stops = sorted(self.stops.all(), key=lambda x: x.sequence)
        return self._stops

    def position(self, now=None):
        return compute_position(self.get_stops(), now or timezone.now())


class StopTime(models.Model):
    run = models.ForeignKey(TrainRun, on_delete=models.CASCADE, related_name="stops")
    station = models.ForeignKey(Station, on_delete=models.PROTECT, related_name="stop_times")
    sequence = models.PositiveSmallIntegerField()
    sched_arr = models.DateTimeField("arrivo programmato", null=True, blank=True)
    sched_dep = models.DateTimeField("partenza programmata", null=True, blank=True)
    actual_arr = models.DateTimeField("arrivo reale", null=True, blank=True)
    actual_dep = models.DateTimeField("partenza reale", null=True, blank=True)

    class Meta:
        ordering = ["run", "sequence"]
        unique_together = [("run", "sequence")]

    def __str__(self):
        return f"{self.run} #{self.sequence} {self.station}"

    # Orario "di riferimento": arrivo se c'è, altrimenti partenza (capolinea di origine)
    @property
    def ref_sched(self):
        return self.sched_arr or self.sched_dep

    @property
    def ref_actual(self):
        return self.actual_arr or self.actual_dep if self.sched_arr else self.actual_dep

    @property
    def delay_min(self):
        """Ritardo in minuti (negativo = anticipo) oppure None se non ancora rilevato."""
        s, a = self.ref_sched, self.ref_actual
        if s is None or a is None:
            return None
        return round((a - s).total_seconds() / 60)

    @property
    def reached(self):
        return self.actual_arr is not None or self.actual_dep is not None


def compute_position(stops, now):
    """Stato del treno: dove si trova (in stazione / in tratta A→B) e avanzamento %."""
    n = len(stops)
    if n == 0:
        return {"state": "unknown", "label": "Nessuna fermata", "progress": 0, "delay": None,
                "from_index": None, "to_index": None}
    reached = [i for i, s in enumerate(stops) if s.reached]
    if not reached:
        first = stops[0]
        return {"state": "not_started", "label": f"Non ancora partito da {first.station.name}",
                "progress": 0, "delay": None, "from_index": None, "to_index": 0}
    i = reached[-1]
    cur = stops[i]
    delay = cur.delay_min
    last = i == n - 1
    if last:
        return {"state": "arrived", "label": f"Arrivato a {cur.station.name}", "progress": 100,
                "delay": delay, "from_index": i, "to_index": None}
    if cur.actual_dep is None:
        return {"state": "at_station", "label": f"In stazione a {cur.station.name}",
                "progress": round(i / (n - 1) * 100), "delay": delay, "from_index": i, "to_index": i + 1}
    nxt = stops[i + 1]
    frac = 0.5
    if nxt.sched_arr:
        pred = nxt.sched_arr + timedelta(minutes=delay or 0)
        total = (pred - cur.actual_dep).total_seconds()
        if total > 0:
            frac = min(max((now - cur.actual_dep).total_seconds() / total, 0.0), 0.99)
    return {"state": "running", "label": f"In tratta {cur.station.name} → {nxt.station.name}",
            "progress": round((i + frac) / (n - 1) * 100), "delay": delay, "from_index": i, "to_index": i + 1}
