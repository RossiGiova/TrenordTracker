from django.core.management.base import BaseCommand

from trains.services.live import LiveUpdater


class Command(BaseCommand):
    help = "Aggiornatore dati reali come processo a sé (per la produzione, con systemd). Non termina mai."

    def handle(self, *a, **o):
        LiveUpdater().loop()
