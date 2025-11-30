# inventory/models.py
from django.db import models

class ProductCategory(models.Model):
    name = models.CharField(max_length=200, unique=True)
    unit = models.CharField(max_length=100, blank=True, null=True, help_text="e.g., 'pcs', 'joint', 'meter'")
    quantity = models.PositiveIntegerField(default=0)   

    class Meta:
        verbose_name_plural = "Product Categories"
        ordering = ['name']

    def __str__(self):
        return self.name

class InventoryItem(models.Model):
    LOCATION_CHOICES = [
        ('maadi-yard', 'Maadi Yard'),
        ('abu-rudies-yard', 'Abu Rudies Yard'), 
    ]

    STATUS_CHOICES = [
        ('available', 'Available'),
        ('on_job', 'On Job'),
        ('re-cut', 'Re-cut'),
        ('lih-dbr', 'LIH-DBR'),
        ('pending_inspection', 'Pending Inspection'),
    ]

    serial_number = models.CharField(max_length=200, unique=True)
    category = models.ForeignKey(ProductCategory, on_delete=models.PROTECT, related_name="items")
    location = models.CharField(max_length=50, choices=LOCATION_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='available')    
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['category__name', 'serial_number']

    def __str__(self):
        return f"{self.category.name} - S/N: {self.serial_number}"