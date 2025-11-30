# inventory/management/commands/recalculate_quantities.py

from django.core.management.base import BaseCommand
from inventory.models import ProductCategory, InventoryItem

class Command(BaseCommand):
    help = 'Recalculates the TOTAL quantity for each ProductCategory based on all its items.'

    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.SUCCESS('Starting TOTAL quantity recalculation...'))

        all_categories = ProductCategory.objects.all()

        for category in all_categories:
            # Count ALL items in this category, regardless of status.
            total_count = InventoryItem.objects.filter(category=category).count()

            # Update the category's quantity field to the total count.
            category.quantity = total_count
            category.save()

            self.stdout.write(
                f"Updated '{category.name}': Found a total of {total_count} items."
            )

        self.stdout.write(self.style.SUCCESS('Finished recalculating all total quantities.'))