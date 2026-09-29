from django.conf import settings
from django.contrib.staticfiles.management.commands.runserver import Command as BaseCommand
from django.core.management import call_command


class Command(BaseCommand):
    help = BaseCommand.help + " In più: applica le migrazioni e avvia l'aggiornamento dei dati reali Trenord."

    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.add_argument("--no-live", action="store_true", help="non scaricare dati reali (usa solo il database)")

    def handle(self, *args, **options):
        self._live = settings.LIVE_UPDATER and not options.pop("no_live", False)
        super().handle(*args, **options)

    def inner_run(self, *args, **options):
        # eseguito una sola volta nel processo che serve le pagine (non nel controllore del reloader)
        call_command("migrate", interactive=False, verbosity=0)
        from trains.services.linestyle import apply_styles
        apply_styles()  # colori delle linee uguali per tutti i dati
        if self._live:
            from trains.services.live import LiveUpdater
            LiveUpdater().start_thread()
        super().inner_run(*args, **options)
