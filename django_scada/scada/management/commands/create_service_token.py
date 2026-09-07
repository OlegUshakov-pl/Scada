from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from scada.auth import generate_token
from scada.models import ServiceToken


class Command(BaseCommand):
    help = "Create a service token for /api/* access. Raw token is printed once (only its hash is stored)."

    def add_arguments(self, parser):
        parser.add_argument("--user", required=True, help="Owner username (token inherits this user's future permissions)")
        parser.add_argument("--name", default="logic_engine", help="Token label")

    def handle(self, *args, **options):
        User = get_user_model()
        try:
            user = User.objects.get(username=options["user"], is_active=True)
        except User.DoesNotExist:
            raise CommandError(f"Active user '{options['user']}' not found. Create it first (admin or createsuperuser).")
        raw, key_hash = generate_token()
        ServiceToken.objects.create(user=user, name=options["name"], key_hash=key_hash)
        self.stdout.write(self.style.SUCCESS(f"Token for user '{user.username}' ({options['name']}) created."))
        # Raw token goes to plain stdout so it can be captured into env/secret storage
        self.stdout.write(f"SCADA_API_TOKEN={raw}")
        self.stdout.write("Store it now: it cannot be shown again (only sha256 is kept in DB).")
