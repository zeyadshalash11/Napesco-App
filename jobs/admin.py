
from django.contrib import admin
from .models import Customer, Contract, Job, DeliveryTicket, ReceivingTicket, JobAttachment


# This allows us to show the Contract inline with the Customer for easy editing
class ContractInline(admin.StackedInline):
    model = Contract
    filter_horizontal = ('items',) # Use a nice widget for selecting contract items

@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ('name', 'created_at')
    search_fields = ('name',)
    inlines = [ContractInline] # Add the Contract editor directly to the Customer page

@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    # Use 'job_number' instead of 'job_name'
    list_display = ('job_number', 'customer', 'date', 'status', 'rig')
    
    # Add 'job_type' to the filters
    list_filter = ('job_type', 'customer', 'status', 'date')
    
    # Use 'job_number' for searching
    search_fields = ('job_number', 'customer__name', 'rig')
    
    autocomplete_fields = ('customer',)
    
    # Make the auto-generated number read-only
    readonly_fields = ('job_number',)
    
    fieldsets = (
        ('Primary Details', {
            'fields': ('job_type', 'customer', 'date', 'status', 'job_number')
        }),
        ('Location & Equipment', {
            'fields': ('rig', 'well', 'location', 'trans')
        }),
        ('Notes', {
            'fields': ('description',),
            'classes': ('collapse',)
        }),
    )
    
@admin.register(DeliveryTicket)
class DeliveryTicketAdmin(admin.ModelAdmin):
    # Add 'ticket_number' to the display and make it read-only
    list_display = ('ticket_number', 'job', 'ticket_date')
    filter_horizontal = ('items',)
    list_filter = ('ticket_date', 'job')
    date_hierarchy = 'ticket_date'
    readonly_fields = ('ticket_number',) # The ticket number is auto-generated

@admin.register(ReceivingTicket)
class ReceivingTicketAdmin(admin.ModelAdmin):
    # Add 'ticket_number' to the display and make it read-only
    list_display = ('ticket_number', 'job', 'ticket_date')
    filter_horizontal = ('items',)
    list_filter = ('ticket_date', 'job')
    date_hierarchy = 'ticket_date'
    readonly_fields = ('ticket_number',)