"""Provider DEMO: genera linee, treni e ritardi verosimili (dati inventati, per provare il sito).

Le fermate/linee sono indicative e i ritardi sono casuali (ma deterministici per treno+giorno,
così rilanciando il comando il treno "avanza" in modo coerente con l'ora attuale).
"""
import json
import random
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from .ingest import RunData, StopData

TZ = ZoneInfo("Europe/Rome")

# Orari reali scaricati con `manage.py fetch_timetable` (se il file esiste, sostituiscono i treni inventati)
TIMETABLE_PATH = Path(__file__).resolve().parents[2] / "timetable.json"

# (codice, nome, colore, base numerazione, cadenza in minuti, [(stazione, minuti dalla fermata precedente)])
# Linee e fermate indicative (dati DEMO): servono a provare il sito.
def _l(*pairs):
    return [(n, m) for n, m in pairs]


LINES = [
    ("S1", "Saronno - Milano - Lodi", "#e2001a", 21000, 30, _l(
        ("Saronno", 0), ("Caronno Pertusella", 4), ("Cesate", 5), ("Garbagnate Milanese", 5), ("Bollate Nord", 6),
        ("Milano Bovisa", 9), ("Milano Lancetti", 4), ("Milano Porta Garibaldi", 4), ("Milano Repubblica", 3),
        ("Milano Porta Vittoria", 5), ("Milano Rogoredo", 5), ("San Donato Milanese", 4), ("San Giuliano Milanese", 5),
        ("Melegnano", 6), ("Lodi", 14))),
    ("S2", "Mariano Comense - Milano - Rogoredo", "#00a651", 22000, 60, _l(
        ("Mariano Comense", 0), ("Meda", 6), ("Seveso", 7), ("Varedo", 6), ("Paderno Dugnano", 6),
        ("Cormano-Cusano Milanino", 6), ("Milano Bovisa", 8), ("Milano Lancetti", 4), ("Milano Porta Garibaldi", 4),
        ("Milano Repubblica", 3), ("Milano Porta Vittoria", 5), ("Milano Rogoredo", 5))),
    ("S3", "Saronno - Milano Cadorna", "#f39200", 20000, 60, _l(
        ("Saronno", 0), ("Caronno Pertusella", 4), ("Cesate", 5), ("Garbagnate Parco delle Groane", 4),
        ("Bollate Nord", 6), ("Novate Milanese", 5), ("Milano Bovisa", 6), ("Milano Domodossola", 5), ("Milano Cadorna", 4))),
    ("S4", "Camnago-Lentate - Milano Cadorna", "#7b3f98", 27000, 60, _l(
        ("Camnago-Lentate", 0), ("Seveso", 8), ("Varedo", 6), ("Paderno Dugnano", 6),
        ("Cormano-Cusano Milanino", 6), ("Milano Bovisa", 8), ("Milano Domodossola", 5), ("Milano Cadorna", 4))),
    ("S5", "Varese - Milano - Treviglio", "#8e44ad", 23000, 30, _l(
        ("Varese", 0), ("Gallarate", 17), ("Legnano", 12), ("Rho", 11), ("Milano Certosa", 8),
        ("Milano Porta Garibaldi", 7), ("Milano Lambrate", 9), ("Pioltello Limito", 8), ("Treviglio", 20))),
    ("S6", "Novara - Milano - Treviglio", "#e67e22", 24000, 30, _l(
        ("Novara", 0), ("Magenta", 20), ("Rho", 14), ("Milano Certosa", 8), ("Milano Porta Garibaldi", 7),
        ("Milano Lambrate", 9), ("Pioltello Limito", 8), ("Treviglio", 20))),
    ("S7", "Lecco - Molteno - Milano Porta Garibaldi", "#0072bc", 28000, 60, _l(
        ("Lecco", 0), ("Molteno", 12), ("Renate-Veduggio", 7), ("Triuggio", 5), ("Macherio-Sovico", 5),
        ("Monza", 8), ("Sesto San Giovanni", 8), ("Milano Greco Pirelli", 5), ("Milano Porta Garibaldi", 9))),
    ("S8", "Lecco - Carnate - Milano Porta Garibaldi", "#00a7b5", 29000, 60, _l(
        ("Lecco", 0), ("Calolziocorte-Olginate", 8), ("Airuno", 6), ("Cernusco-Merate", 7), ("Osnago", 4),
        ("Carnate-Usmate", 5), ("Arcore", 4), ("Monza", 6), ("Sesto San Giovanni", 8),
        ("Milano Greco Pirelli", 5), ("Milano Porta Garibaldi", 9))),
    ("S9", "Saronno - Milano - Albairate", "#27ae60", 25000, 30, _l(
        ("Saronno", 0), ("Ceriano Laghetto-Groane", 5), ("Seregno", 12), ("Monza", 9), ("Sesto San Giovanni", 8),
        ("Milano Greco Pirelli", 5), ("Milano Lambrate", 9), ("Milano Rogoredo", 7), ("Milano San Cristoforo", 12),
        ("Trezzano sul Naviglio", 6), ("Albairate-Vermezzo", 10))),
    ("S11", "Chiasso - Milano - Rho", "#c0392b", 26000, 30, _l(
        ("Chiasso", 0), ("Como San Giovanni", 9), ("Cantù", 14), ("Seregno", 14), ("Monza", 9),
        ("Sesto San Giovanni", 8), ("Milano Greco Pirelli", 5), ("Milano Centrale", 7),
        ("Milano Porta Garibaldi", 6), ("Rho Fiera", 12))),
    ("S12", "Bovisa - Milano - Melegnano", "#a0522d", 30000, 30, _l(
        ("Milano Bovisa", 0), ("Milano Lancetti", 4), ("Milano Porta Garibaldi", 4), ("Milano Repubblica", 3),
        ("Milano Porta Vittoria", 5), ("Milano Rogoredo", 5), ("San Donato Milanese", 4),
        ("San Giuliano Milanese", 5), ("Melegnano", 6))),
    ("S13", "Garbagnate - Milano - Pavia", "#6d6e71", 31000, 60, _l(
        ("Garbagnate Milanese", 0), ("Bollate Nord", 6), ("Milano Bovisa", 9), ("Milano Lancetti", 4),
        ("Milano Porta Garibaldi", 4), ("Milano Repubblica", 3), ("Milano Porta Vittoria", 5), ("Milano Rogoredo", 5),
        ("Locate Triulzi", 10), ("Villamaggiore", 9), ("Certosa di Pavia", 6), ("Pavia", 10))),
    ("MXP1", "Malpensa Express: Milano Cadorna - Malpensa", "#d4145a", 40000, 30, _l(
        ("Milano Cadorna", 0), ("Milano Bovisa", 6), ("Saronno", 16), ("Busto Arsizio Nord", 10),
        ("Malpensa Aeroporto T1", 8), ("Malpensa Aeroporto T2", 4))),
    ("MXP2", "Malpensa Express: Milano Centrale - Malpensa", "#ee7203", 41000, 30, _l(
        ("Milano Centrale", 0), ("Milano Porta Garibaldi", 6), ("Milano Bovisa", 6), ("Saronno", 16),
        ("Busto Arsizio Nord", 10), ("Malpensa Aeroporto T1", 8), ("Malpensa Aeroporto T2", 4))),
]


def _slug(name):
    return "D" + "".join(c for c in name.upper() if c.isalnum())[:12]


def _delays(rng, n, hour):
    """Ritardo (minuti) a ogni fermata: cresce lungo la tratta, più probabile in ora di punta."""
    peak = hour in (7, 8, 17, 18, 19)
    base = rng.choice([0, 0, 0, 1, 1, 2, 3]) + (rng.choice([0, 1, 2, 4]) if peak else 0)
    incident = rng.random() < (0.10 if peak else 0.05)
    out, d = [], float(base)
    hit = rng.randrange(1, n) if incident else -1
    for i in range(n):
        d += rng.gauss(0.25, 0.7)
        if i == hit:
            d += rng.uniform(6, 20)
        d = max(d, -1)
        out.append(round(d))
    out[0] = max(0, min(out[0], 3))
    return out


def build_run(line, direction, dep_time, day, now):
    code, name, color, base, _headway, stops = line
    seq = stops if direction == 0 else list(reversed(stops))
    # tempi di percorrenza: nel verso inverso si usano i tempi della tratta opposta
    gaps = [g for _, g in stops][1:]
    gaps = gaps if direction == 0 else list(reversed(gaps))
    number = str(base + int(dep_time.hour * 60 + dep_time.minute) // 5 * 2 + direction)
    rng = random.Random(f"{number}-{day.isoformat()}")

    t = datetime.combine(day, dep_time, tzinfo=TZ)
    delays = _delays(rng, len(seq), dep_time.hour)
    stop_list = []
    for i, (sname, _) in enumerate(seq):
        if i > 0:
            t += timedelta(minutes=gaps[i - 1])
        first, last = i == 0, i == len(seq) - 1
        sa = None if first else t
        sd = None if last else t + timedelta(minutes=0 if first else 1)
        d = timedelta(minutes=delays[i])
        aa = None if first or (sa + d) > now else sa + d
        ad = None if last or (sd + d) > now else sd + d
        stop_list.append(StopData(_slug(sname), sname, sa, sd, aa, ad))
        if not first:
            t = sd or t
    return RunData(
        number=number, service_date=day, stops=stop_list, category="S",
        line_code=code, line_name=name, line_color=color, line_order=LINES.index(line), demo=True,
    )


def load_timetable():
    try:
        return json.loads(TIMETABLE_PATH.read_text(encoding="utf-8")).get("trains") or []
    except (OSError, ValueError):
        return []


def _meta(code):
    for i, (c, name, color, *_rest) in enumerate(LINES):
        if c == code:
            return name, color, i
    return code, "#6c757d", 100


def build_run_from_timetable(t, day, now):
    """Treno con orari REALI (da timetable.json) e ritardi simulati come per gli altri."""
    base = datetime.combine(day, time(0, 0), tzinfo=TZ)
    stops = t["stops"]
    first_dep = base + timedelta(minutes=stops[0]["dep"] if stops[0].get("dep") is not None else stops[0]["arr"])
    rng = random.Random(f"{t['number']}-{day.isoformat()}")
    delays = _delays(rng, len(stops), first_dep.hour)
    out = []
    for i, s in enumerate(stops):
        sa = base + timedelta(minutes=s["arr"]) if s.get("arr") is not None else None
        sd = base + timedelta(minutes=s["dep"]) if s.get("dep") is not None else None
        d = timedelta(minutes=delays[i])
        aa = sa + d if sa and (sa + d) <= now else None
        ad = sd + d if sd and (sd + d) <= now else None
        out.append(StopData(s["code"], s["name"], sa, sd, aa, ad))
    name, color, order = _meta(t.get("line") or "")
    return RunData(number=str(t["number"]), service_date=day, stops=out, category=t.get("category", ""),
                   line_code=t.get("line") or "", line_name=name, line_color=color, line_order=order, demo=True)


def generate_day(day: date, now: datetime, start=6, end=21):
    real = load_timetable()
    if real:
        return [build_run_from_timetable(t, day, now) for t in real if len(t.get("stops", [])) >= 2]
    return _generate_invented_day(day, now, start, end)


def _generate_invented_day(day: date, now: datetime, start=6, end=21):
    runs = []
    for line in LINES:
        headway = line[4]
        for direction in (0, 1):
            offset = 0 if direction == 0 else 15
            t = datetime.combine(day, time(start, 0)) + timedelta(minutes=offset)
            last = datetime.combine(day, time(end, 30))
            while t <= last:
                runs.append(build_run(line, direction, t.time(), day, now))
                t += timedelta(minutes=headway)
    return runs
