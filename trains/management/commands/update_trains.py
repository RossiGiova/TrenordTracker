import time
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from trains.models import Line, Train
from trains.services import demo, ingest
from trains.services.live import LiveUpdater


class Command(BaseCommand):
    help = ("Genera/aggiorna la simulazione (provider demo, default) oppure fa una passata di ritardi reali "
            "da ViaggiaTreno (provider viaggiatreno).")

    def add_arguments(self, parser):
        parser.add_argument("--provider", default="demo", choices=["demo", "viaggiatreno"])
        parser.add_argument("--reset", action="store_true", help="(demo) cancella prima TUTTI i treni già presenti nel database")
        parser.add_argument("--history-days", type=int, default=0, help="(demo) giorni di storico da generare")
        parser.add_argument("--numbers", nargs="*", default=[], help="(viaggiatreno) aggiungi questi numeri treno")
        parser.add_argument("--line", help="(viaggiatreno) linea da associare ai --numbers")
        parser.add_argument("--hubs", help="(viaggiatreno) usa solo queste stazioni, separate da virgola")
        parser.add_argument("--only-lines", help="(viaggiatreno) segui solo queste linee, es. S1,S5")
        parser.add_argument("--watch", type=int, default=0, help="ripeti ogni N secondi")

    def handle(self, *a, **o):
        if o["provider"] == "demo":
            return self.run_demo(o["history_days"], o["reset"])
        up = LiveUpdater(
            hubs=[h.strip() for h in o["hubs"].split(",")] if o["hubs"] else None,
            only_lines=[x.strip().upper() for x in o["only_lines"].split(",")] if o["only_lines"] else None,
        )
        for n in o["numbers"]:
            t, _ = Train.objects.get_or_create(number=n)
            t.tracked = True
            if o["line"]:
                t.line, _ = Line.objects.get_or_create(code=o["line"])
            t.save()
        while True:
            t0 = time.time()
            up.cycle()
            if not o["watch"]:
                break
            time.sleep(max(o["watch"] - (time.time() - t0), 5))

    def run_demo(self, history_days, reset=False):
        if reset:
            Train.objects.all().delete()
        now, today = timezone.now(), timezone.localdate()
        count = 0
        for d in [today - timedelta(days=i) for i in range(history_days, -1, -1)]:
            for r in demo.generate_day(d, now):
                count += bool(ingest.save_run(r))
        self.stdout.write(self.style.SUCCESS(f"Demo: salvate {count} corse."))
