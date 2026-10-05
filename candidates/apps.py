from django.apps import AppConfig
import os

class CandidatesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'candidates'

    def ready(self):
        # Prevent scheduler from running twice when Django development server auto-reloads
        if os.environ.get('RUN_MAIN', None) != 'true':
            from .scheduler import start_scheduler
            start_scheduler()
