import logging

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from trains.services import demo, timetable
from trains.services import viaggiatreno as vt
from django.conf import settings


class Command(BaseCommand):
    help = ("Scarica gli orari REALI dei treni Trenord da ViaggiaTreno (numeri, linee, fermate, orari) "
            "e rigenera la simulazione usando quelli. I ritardi restano simulati.")

    def add_arguments(self, parser):
        parser.add_argument("--hubs", help="solo queste stazioni, separate da virgola (default: ~20 stazioni principali)")
        parser.add_argument("--all-stations", action="store_true",
                            help="controlla tutte le stazioni lombarde (più completo ma molto più lento)")
        parser.add_argument("--start", type=int, default=4, help="prima ora della giornata da controllare")
        parser.add_argument("--end", type=int, default=23, help="ultima ora della giornata da controllare")
        parser.add_argument("--step", type=int, default=60, help="minuti tra una fascia oraria e l'altra")
        parser.add_argument("--history-days", type=int, default=14)
        parser.add_argument("--no-simulate", action="store_true", help="scarica solo timetable.json")

    def handle(self, *a, **o):
        logging.getLogger("trains.live").setLevel(logging.INFO)
        vt.DUMP_DIR = getattr(settings, "LIVE_DEBUG_DIR", None)
        hubs = [h.strip() for h in o["hubs"].split(",")] if o["hubs"] else (None if o["all_stations"] else vt.DEFAULT_HUBS)
        try:
            trains = timetable.collect(hubs=hubs, region=settings.LIVE_REGION, operators=settings.LIVE_OPERATORS or (),
                                       start=o["start"], end=o["end"], step=o["step"], workers=settings.LIVE_WORKERS)
        except Exception as e:
            raise CommandError(f"Download fallito: {e}")
        if not trains:
            raise CommandError("Nessun treno scaricato: controlla la connessione e debug_samples/partenze_sample.json. "
                               "La simulazione non è stata toccata.")
        timetable.save(trains, demo.TIMETABLE_PATH)
        lines = sorted({t["line"] for t in trains if t["line"]})
        self.stdout.write(self.style.SUCCESS(
            f"Salvati {len(trains)} treni reali in {demo.TIMETABLE_PATH.name} (linee riconosciute: {', '.join(lines) or 'nessuna'})."))
        if not o["no_simulate"]:
            self.stdout.write("Rigenero la simulazione con gli orari reali (cancella i treni presenti nel database)...")
            call_command("update_trains", provider="demo", reset=True, history_days=o["history_days"])
