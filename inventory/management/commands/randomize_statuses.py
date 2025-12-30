# inventory/management/commands/randomize_statuses.py

import random
from django.core.management.base import BaseCommand
from inventory.models import InventoryItem

class Command(BaseCommand):
    help = 'Randomly assigns a new status to every item in the inventory.'

    def handle(self, *args, **kwargs):
        self.stdout.write("Starting to randomize inventory statuses...")

        # Get all inventory items from the database
        all_items = list(InventoryItem.objects.all())
        
        if not all_items:
            self.stdout.write(self.style.WARNING("No inventory items found to randomize."))
            return

        # Get the list of available status choices from the model
        # We extract just the value, e.g., 'available', 'on_job', etc.
        status_choices = [status[0] for status in InventoryItem.STATUS_CHOICES]

        updated_count = 0
        
        # Loop through every item and assign a random status
        for item in all_items:
            # Choose a random status from our list of choices
            new_status = random.choice(status_choices)
            item.status = new_status
            updated_count += 1

        # Use bulk_update for efficiency. This updates all items in a single database query.
        InventoryItem.objects.bulk_update(all_items, ['status'])

        # Print a success message to the terminal
        self.stdout.write(self.style.SUCCESS(f"Successfully randomized the status for {updated_count} items."))