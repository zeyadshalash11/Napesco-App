from django.contrib import admin
from .models import ProductCategory, InventoryItem

@admin.register(ProductCategory)
class ProductCategoryAdmin(admin.ModelAdmin):
    # Add 'quantity' to the display
    list_display = ('name', 'unit', 'quantity')
    search_fields = ('name', 'unit')

@admin.register(InventoryItem)
class InventoryItemAdmin(admin.ModelAdmin):
    list_display = (
        'serial_number', 
        'category',  
        'location', 
        'status',  
        'updated_at'
    )
    list_editable = ('status',) 

    list_filter = ('location', 'status', 'category')
    search_fields = ('serial_number', 'category__name')
    date_hierarchy = 'updated_at'
    fields = ('serial_number', 'category', 'location', 'status', 'recut_reason')
     
     
