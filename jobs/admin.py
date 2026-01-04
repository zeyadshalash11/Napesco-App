# jobs/admin.py

from django.contrib import admin
from .models import (
    Customer, Contract, Job, DeliveryTicket, ReceivingTicket, 
    JobAttachment, DeliveryTicketItem, ReceivingTicketItem # <-- Import the new model
)

# This allows us to show the Contract inline with the Customer for easy editing
class ContractInline(admin.StackedInline):
    model = Contract
    filter_horizontal = ('items',)

@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ('name', 'created_at')
    search_fields = ('name',)
    inlines = [ContractInline]

@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = ('job_number', 'customer', 'date', 'status', 'rig')
    list_filter = ('job_type', 'customer', 'status', 'date')
    search_fields = ('job_number', 'customer__name', 'rig')
    autocomplete_fields = ('customer',)
    
    def get_readonly_fields(self, request, obj=None):
        if obj:
            return ('job_number',)
        return ()

    def get_fieldsets(self, request, obj=None):
        if obj:
            return (
                ('Primary Details', {'fields': ('job_type', 'customer', 'date', 'status', 'job_number')}),
                ('Location & Equipment', {'fields': ('rig', 'well', 'location', 'trans')}),
                ('Notes', {'fields': ('description',), 'classes': ('collapse',)}),
            )
        else:
            return (
                ('Primary Details', {'fields': ('job_type', 'customer', 'date', 'status')}),
                ('Location & Equipment', {'fields': ('rig', 'well', 'location', 'trans')}),
                ('Notes', {'fields': ('description',), 'classes': ('collapse',)}),
            )

class DeliveryTicketItemInline(admin.TabularInline):
    model = DeliveryTicketItem
    extra = 0
    autocomplete_fields = ['item'] # Makes finding items easier

@admin.register(DeliveryTicket)
class DeliveryTicketAdmin(admin.ModelAdmin):
    list_display = ('ticket_number', 'job', 'ticket_date')
    list_filter = ('ticket_date', 'job')
    date_hierarchy = 'ticket_date'
    readonly_fields = ('ticket_number',)
    inlines = [DeliveryTicketItemInline]
    
# --- START: NEW AND MODIFIED ADMIN CLASSES ---

# This is the new Inline for the Receiving Ticket page
class ReceivingTicketItemInline(admin.TabularInline):
    model = ReceivingTicketItem
    extra = 0  # Start with no empty extra rows
    autocomplete_fields = ['item'] # Use a search box for items
    # You can specify which fields to show in the inline view
    fields = ('item', 'usage_status') 

@admin.register(ReceivingTicket)
class ReceivingTicketAdmin(admin.ModelAdmin):
    list_display = ('ticket_number', 'job', 'ticket_date', 'is_fully_verified')
    list_filter = ('ticket_date', 'job')
    date_hierarchy = 'ticket_date'
    readonly_fields = ('ticket_number',)
    
    inlines = [ReceivingTicketItemInline]

