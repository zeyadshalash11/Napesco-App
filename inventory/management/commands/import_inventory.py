# inventory/management/commands/import_inventory.py

import pandas as pd
from django.core.management.base import BaseCommand
from inventory.models import Item

class Command(BaseCommand):
    help = 'Imports inventory items from a CSV file'

    def handle(self, *args, **kwargs):
        file_path = 'inventory_data.csv'
        try:
            df = pd.read_csv(file_path)
        except FileNotFoundError:
            self.stdout.write(self.style.ERROR(f'File not found at {file_path}. Please make sure it is in the root project directory.'))
            return

        self.stdout.write(self.style.SUCCESS(f'Started importing items from {file_path}...'))

        # Loop through each row in the CSV
        for index, row in df.iterrows():
            # Use update_or_create to avoid duplicates based on the SKU
            item, created = Item.objects.update_or_create(
                sku=row['sku'],
                defaults={
                    'name': row['name'],
                    'quantity': row['quantity'],
                    'location': row['location']
                }
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f'Successfully created item: {item.name}'))
            else:
                self.stdout.write(self.style.WARNING(f'Updated existing item: {item.name}'))

        self.stdout.write(self.style.SUCCESS('Finished importing inventory.'))