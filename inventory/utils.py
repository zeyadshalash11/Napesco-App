# inventory/utils.py
import pandas as pd
from django.db import transaction
from .models import ProductCategory, InventoryItem

def process_inventory_file(dataframe):
    items_created = 0
    items_updated = 0
    errors = []
    
    location_choices = [choice[0] for choice in InventoryItem.LOCATION_CHOICES]
    status_choices = [choice[0] for choice in InventoryItem.STATUS_CHOICES]

    try:
        with transaction.atomic():
            # Get a list of all existing category names once to speed up checks
            existing_categories = {cat.name.lower(): cat for cat in ProductCategory.objects.all()}

            for index, row in dataframe.iterrows():
                try:
                    # 1. Read and clean data
                    category_name_raw = str(row.get('CategoryName', '')).strip()
                    serial_number = str(row.get('SerialNumber', '')).strip()
                    location_raw = str(row.get('Location', '')).strip()
                    status_raw = str(row.get('Status', '')).strip()
                    unit_raw = str(row.get('Unit', '')).strip() 

                    location = location_raw.replace(' ', '-').lower() 
                    status = status_raw.lower()
                    
                    # 2. VALIDATION (for everything EXCEPT category)
                    if not category_name_raw:
                        errors.append(f"Row {index + 2}: Missing CategoryName.")
                        continue
                    if not serial_number:
                        errors.append(f"Row {index + 2}: Missing SerialNumber.")
                        continue
                    # We can skip location/status validation if we want to be more lenient
                    # but it's safer to keep it for now.
                    if location not in location_choices:
                        errors.append(f"Row {index + 2}: Invalid Location '{location_raw}'.")
                        continue
                    if status not in status_choices:
                        errors.append(f"Row {index + 2}: Invalid Status '{status_raw}'.")
                        continue

                    # 3. AUTOMATICALLY GET OR CREATE THE CATEGORY
                    category_name_lower = category_name_raw.lower()
                    if category_name_lower in existing_categories:
                        category = existing_categories[category_name_lower]
                    else:
                        # If not found, create it
                        category = ProductCategory.objects.create(name=category_name_raw, unit=unit_raw)
                        # Add it to our local dictionary to avoid creating it again
                        existing_categories[category_name_lower] = category

                    # 4. PROCESS THE INVENTORY ITEM
                    item, created = InventoryItem.objects.update_or_create(
                        serial_number=serial_number,
                        defaults={
                            'category': category,
                            'location': location,
                            'status': status,
                        }
                    )
                    if created:
                        items_created += 1
                    else:
                        items_updated += 1

                except Exception as e:
                    errors.append(f"Row {index + 2}: An unexpected error occurred - {e}")

    except Exception as e:
        errors.append(f"A critical error occurred: {e}. The import has been rolled back.")

    return { 'created': items_created, 'updated': items_updated, 'errors': errors }