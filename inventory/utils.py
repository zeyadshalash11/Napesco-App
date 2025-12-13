import re
from django.db import transaction
from .models import InventoryItem, ProductCategory

def _norm(v):
    if v is None:
        return ""
    return str(v).strip()

def _norm_serial(v):
    return _norm(v).upper()

def _norm_key(v):
    v = _norm(v).lower()
    v = re.sub(r"\s+", " ", v)
    return v

def normalize_location(v):
    key = _norm_key(v)
    LOCATION_ALIASES = {
        "maadi yard": "maadi-yard",
        "maadi-yard": "maadi-yard",
        "abu rudies yard": "abu-rudies-yard",
        "abu-rudies yard": "abu-rudies-yard",
        "abu-rudies-yard": "abu-rudies-yard",
    }
    return LOCATION_ALIASES.get(key, _norm(v))

def normalize_status(v):
    key = _norm_key(v)
    STATUS_ALIASES = {
        "available": "available",
        "on job": "on_job",
        "on_job": "on_job",
        "pending inspection": "pending_inspection",
        "pending_inspection": "pending_inspection",
        "re cut": "re-cut",
        "re-cut": "re-cut",
        "lih dbr": "lih-dbr",
        "lih-dbr": "lih-dbr",
        "": "",
    }
    return STATUS_ALIASES.get(key, _norm(v))

def process_inventory_file(df, *, strict=False):
    """
    strict=False (your requested behavior):
      - skip only bad rows + report their errors
      - upsert: update existing by SerialNumber, create if new
    """
    summary = {
        "created": 0,
        "updated": 0,
        "skipped": 0,
        "errors": [],
        "warnings": [],
    }

    if df is None or df.empty:
        summary["errors"].append("The uploaded file is empty.")
        return summary

    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]

    required = {"CategoryName", "SerialNumber", "Location", "Status", "Unit"}
    missing = required - set(df.columns)
    if missing:
        summary["errors"].append(f"Missing required columns: {', '.join(sorted(missing))}")
        return summary

    df = df.dropna(how="all").copy()
    if df.empty:
        summary["errors"].append("The file contains only empty rows.")
        return summary

    df["_row"] = df.index + 2  # header=1

    # Normalize values
    df["CategoryName"] = df["CategoryName"].apply(_norm)
    df["SerialNumber"] = df["SerialNumber"].apply(_norm_serial)
    df["Location"] = df["Location"].apply(normalize_location)
    df["Status"] = df["Status"].apply(normalize_status)
    df["Unit"] = df["Unit"].apply(_norm)

    valid_locations = {k for k, _ in InventoryItem.LOCATION_CHOICES}
    valid_status = {k for k, _ in InventoryItem.STATUS_CHOICES}

    # Preload existing items by serial
    serials = df.loc[df["SerialNumber"] != "", "SerialNumber"].unique().tolist()
    existing_items = InventoryItem.objects.in_bulk(serials, field_name="serial_number") if serials else {}

    # Preload categories by name
    cat_names = sorted(set(df["CategoryName"].tolist()) - {""})
    cats_by_name = {c.name: c for c in ProductCategory.objects.filter(name__in=cat_names)}

    seen_serials_in_file = set()

    to_create = []
    to_update = []

    for _, r in df.iterrows():
        row_no = int(r["_row"])
        cat_name = r["CategoryName"]
        serial = r["SerialNumber"]
        location = r["Location"]
        status = r["Status"] or "available"
        unit = r["Unit"]

        row_errors = []

        # Validate required
        if not serial:
            row_errors.append("SerialNumber is empty.")
        if not cat_name:
            row_errors.append("CategoryName is empty.")
        if not location:
            row_errors.append("Location is empty.")

        # Validate choices (after mapping)
        if location and location not in valid_locations:
            row_errors.append(f"Location '{location}' is invalid. Use: {sorted(valid_locations)}")
        if status and status not in valid_status:
            row_errors.append(f"Status '{status}' is invalid. Use: {sorted(valid_status)}")

        # Detect duplicates inside the file (skip the repeated ones)
        if serial:
            if serial in seen_serials_in_file:
                row_errors.append(f"Duplicate SerialNumber '{serial}' in the uploaded file.")
            else:
                seen_serials_in_file.add(serial)

        # If row has errors => skip row, report errors, continue
        if row_errors:
            summary["skipped"] += 1
            summary["errors"].append(f"Row {row_no}: " + " | ".join(row_errors))
            continue

        # Category create/get + set unit on category if needed
        category = cats_by_name.get(cat_name)
        if not category:
            category = ProductCategory.objects.create(name=cat_name, unit=unit or None)
            cats_by_name[cat_name] = category
        else:
            if unit and not category.unit:
                category.unit = unit
                category.save(update_fields=["unit"])

        # UPSERT: update if exists else create
        existing = existing_items.get(serial)
        if existing:
            changed = False

            if existing.category_id != category.id:
                existing.category = category
                changed = True
            if existing.location != location:
                existing.location = location
                changed = True
            if existing.status != status:
                existing.status = status
                changed = True

            if changed:
                to_update.append(existing)
            else:
                # No changes, but it's not an error
                summary["warnings"].append(f"Row {row_no}: Serial '{serial}' already exists (no changes).")
        else:
            to_create.append(
                InventoryItem(
                    serial_number=serial,
                    category=category,
                    location=location,
                    status=status,
                )
            )

    # Save changes
    with transaction.atomic():
        if to_create:
            InventoryItem.objects.bulk_create(to_create, batch_size=1000)
        if to_update:
            InventoryItem.objects.bulk_update(to_update, ["category", "location", "status"], batch_size=1000)

    summary["created"] = len(to_create)
    summary["updated"] = len(to_update)
    return summary
