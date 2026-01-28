# management/commands/generate_team_codes.py
from django.core.management.base import BaseCommand
from stato.models import Team
import random
import string


class Command(BaseCommand):
    help = 'Generate team codes for teams that don\'t have one'

    def handle(self, *args, **options):
        teams_without_code = Team.objects.filter(team_code__isnull=True) | Team.objects.filter(team_code='')
        count = 0
        
        for team in teams_without_code:
            # Generate unique 6-character code
            while True:
                code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
                if not Team.objects.filter(team_code=code).exists():
                    team.team_code = code
                    team.save()
                    count += 1
                    self.stdout.write(
                        self.style.SUCCESS(f'Generated code {code} for team: {team.team_name}')
                    )
                    break
        
        self.stdout.write(
            self.style.SUCCESS(f'\nGenerated {count} team code(s)')
        )
