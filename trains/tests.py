"""Test offline: simulano le risposte di ViaggiaTreno (formato documentato) senza usare la rete."""
from datetime import datetime
from unittest import mock
from zoneinfo import ZoneInfo

from django.test import TestCase, override_settings

from trains.models import Train, TrainRun
from trains.services import demo, ingest
from trains.services import viaggiatreno as vt
from trains.services.live import LiveUpdater, infer_line

TZ = ZoneInfo("Europe/Rome")


def ms(h, m):
    d = datetime.now(TZ).replace(hour=h, minute=m, second=0, microsecond=0)
    return int(d.timestamp() * 1000)


def midnight_ms():
    return ms(0, 0)


class FakeResp:
    def __init__(self, data, status=200):
        self._d, self.status_code = data, status
        self.content = b"x" if data not in (None, "") else b""
        self.text = data if isinstance(data, str) else ""

    def json(self):
        return self._d

    def raise_for_status(self):
        pass


def fake_get(session, path, **kw):
    if path.startswith("elencoStazioni"):
        return FakeResp([{"codiceStazione": "S01700"}, {"codStazione": "S01645"}])
    if path.startswith("partenze"):
        return FakeResp([
            {"numeroTreno": 23480, "codOrigine": "S00500", "dataPartenzaTreno": midnight_ms(),
             "codiceCliente": 63, "categoria": "S"},
            {"numeroTreno": 9999, "codOrigine": "S06421", "dataPartenzaTreno": midnight_ms(),
             "codiceCliente": 1, "categoria": "FR"},          # Trenitalia: da scartare
        ])
    if path.startswith("andamentoTreno"):
        return FakeResp({"compNumeroTreno": "S5 23480", "categoria": "S", "codiceCliente": 63, "fermate": [
            {"stazione": "MILANO CENTRALE", "id": "S01700", "programmata": ms(0, 5),
             "partenza_teorica": ms(0, 5), "partenzaReale": ms(0, 7)},
            {"stazione": "RHO", "id": "S01000", "arrivo_teorico": ms(0, 20), "partenza_teorica": ms(0, 21),
             "arrivoReale": ms(0, 24), "partenzaReale": None},
            {"stazione": "VARESE", "id": "S00500", "programmata": ms(0, 55), "arrivo_teorico": ms(0, 55)},
        ]})
    raise AssertionError(path)


class ViaggiaTrenoTests(TestCase):
    def test_js_date(self):
        s = vt._js_date(datetime(2026, 9, 29, 18, 44, tzinfo=TZ))
        self.assertEqual(s, "Tue Sep 29 2026 18:44:00 GMT+0200")

    @override_settings(LIVE_PURGE_DEMO=True)
    def test_live_cycle_filters_trenord_and_purges_demo(self):
        # dati demo già presenti (anche con lo stesso numero di un treno reale)
        for r in demo.generate_day(datetime.now(TZ).date(), datetime.now(TZ))[:20]:
            ingest.save_run(r)
        demo_before = Train.objects.filter(is_demo=True).count()
        self.assertGreater(demo_before, 0)

        with mock.patch.object(vt, "_get", fake_get):
            LiveUpdater().cycle()

        self.assertFalse(Train.objects.filter(is_demo=True).exists())      # demo rimossi
        self.assertFalse(Train.objects.filter(number="9999").exists())      # non-Trenord scartato
        t = Train.objects.get(number="23480")
        self.assertEqual(t.line.code, "S5")
        run = TrainRun.objects.get(train=t)
        self.assertEqual(len(run.get_stops()), 3)
        self.assertEqual(run.get_stops()[1].delay_min, 4)
        self.assertEqual(run.position()["state"], "at_station")

    @override_settings(LIVE_PURGE_DEMO=False)
    def test_live_can_keep_demo(self):
        for r in demo.generate_day(datetime.now(TZ).date(), datetime.now(TZ))[:5]:
            ingest.save_run(r)
        with mock.patch.object(vt, "_get", fake_get):
            LiveUpdater().cycle()
        self.assertTrue(Train.objects.filter(is_demo=True).exists())
        self.assertTrue(Train.objects.filter(number="23480", is_demo=False).exists())

    def test_infer_line(self):
        def st(*names):
            return [ingest.StopData("x", n) for n in names]
        self.assertEqual(infer_line("REG 24565", st("Varese", "Treviglio"), "24565"), "S5")
        self.assertEqual(infer_line("REG 24161", st("Saronno", "Lodi"), "24161"), "S1")
        self.assertEqual(infer_line("REG 869", st("Milano Cadorna", "Saronno"), "869"), "S3")
        self.assertEqual(infer_line("REG 771", st("Milano Cadorna", "Camnago-Lentate"), "771"), "S4")
        self.assertEqual(infer_line("REG 371", st("Milano Cadorna", "Malpensa Aeroporto Terminal 2"), "371"), "MXP1")
        self.assertEqual(infer_line("S11 26480", st("A", "B"), "26480"), "S11")
        self.assertEqual(infer_line("REG 10069", st("Milano Rogoredo", "Alessandria"), "10069"), "")


class TimetableTests(TestCase):
    def test_collect_and_simulate(self):
        import tempfile
        from pathlib import Path
        from trains.services import timetable
        with mock.patch.object(vt, "_get", fake_get):
            trains = timetable.collect(hubs=None, region=1, operators=(63,), start=8, end=9, step=60)
        self.assertEqual([t["number"] for t in trains], ["23480"])
        self.assertEqual(trains[0]["line"], "S5")
        self.assertEqual(trains[0]["stops"][1], {"code": "S01000", "name": "Rho", "arr": 20, "dep": 21})
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "timetable.json"
            timetable.save(trains, path)
            with mock.patch.object(demo, "TIMETABLE_PATH", path):
                runs = demo.generate_day(datetime.now(TZ).date(), datetime.now(TZ))
        self.assertEqual(len(runs), 1)
        self.assertTrue(runs[0].demo)
        self.assertEqual(runs[0].stops[1].sched_arr.hour, 0)
        self.assertEqual(runs[0].stops[1].sched_arr.minute, 20)


class LineStyleTests(TestCase):
    def test_real_lines_get_palette_colors(self):
        from trains.models import Line
        from trains.services import linestyle
        Line.objects.create(code="S5")          # creata "in blu" dai dati reali
        Line.objects.create(code="S9", color="#0d6efd")
        self.assertEqual(linestyle.apply_styles(), 2)
        self.assertEqual(Line.objects.get(code="S5").color, "#8e44ad")
        self.assertEqual(Line.objects.get(code="S9").color, "#27ae60")
        run = ingest.RunData(number="24565", service_date=datetime.now(TZ).date(), line_code="S6",
                             stops=[ingest.StopData("a", "A"), ingest.StopData("b", "B")])
        ingest.save_run(run)
        self.assertEqual(Line.objects.get(code="S6").color, "#e67e22")


class LineLiveTests(TestCase):
    """Vista 'dove sono i treni adesso': percorso della linea + posizione dei treni."""

    NAMES = ["Lecco", "Airuno", "Monza", "Greco Pirelli", "Garibaldi"]

    def _run(self, line, number, names, base, actual_upto, delay=3):
        from datetime import timedelta
        from trains.models import Station, StopTime
        def stn(n):
            return Station.objects.get_or_create(code=n[:3].upper() + str(self.NAMES.index(n)), defaults={"name": n})[0]
        tr = Train.objects.create(number=number, category="REG", line=line, origin=stn(names[0]),
                                  destination=stn(names[-1]), origin_code="x", tracked=True)
        run = TrainRun.objects.create(train=tr, service_date=base.date())
        for i, n in enumerate(names):
            st = stn(n)
            sched = base + timedelta(minutes=10 * i)
            kw = dict(run=run, station=st, sequence=i, sched_arr=sched, sched_dep=sched)
            if i <= actual_upto:
                kw.update(actual_arr=sched + timedelta(minutes=delay), actual_dep=sched + timedelta(minutes=delay))
            StopTime.objects.create(**kw)
        return run

    def test_route_and_positions(self):
        from datetime import timedelta
        from django.utils import timezone
        from trains.models import Line
        from trains import route as routes
        line = Line.objects.create(code="S8", name="Lecco - Milano", color="#00a7b5")
        base = timezone.now().replace(microsecond=0) - timedelta(minutes=15)
        self._run(line, "24501", self.NAMES, base, 1)                      # verso Milano, tra Airuno e Monza
        self._run(line, "24502", self.NAMES[::-1], base, 0, delay=0)       # verso Lecco, appena partito
        routes._CACHE.clear()
        d = self.client.get("/api/lines/S8/live/").json()
        self.assertEqual([s["name"] for s in d["route"]], self.NAMES)
        by = {t["number"]: t for t in d["trains"]}
        self.assertEqual(set(by), {"24501", "24502"})
        self.assertEqual(by["24501"]["direction"], 1)
        self.assertEqual(by["24502"]["direction"], -1)
        self.assertTrue(1 <= by["24501"]["route_pos"] <= 2)
        self.assertGreaterEqual(by["24502"]["route_pos"], 3)
        self.assertEqual(by["24501"]["delay"], 3)
        self.assertEqual(by["24501"]["next_station"], "Monza")

    def test_empty_when_no_trains(self):
        from trains.models import Line
        Line.objects.create(code="S9", name="x", color="#000000")
        d = self.client.get("/api/lines/S9/live/").json()
        self.assertEqual(d["trains"], [])
        self.assertEqual(self.client.get("/api/lines/ZZ/live/").status_code, 404)
