
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
    list_display = ('job_number', 'customer', 'date', 'status', 'rig')
    list_filter = ('job_type', 'customer', 'status', 'date')
    search_fields = ('job_number', 'customer__name', 'rig')
    autocomplete_fields = ('customer',)
    
    # We will define readonly_fields and fieldsets inside a method now

    def get_readonly_fields(self, request, obj=None):
        # If the object already exists (i.e., this is a "Change" page)
        if obj:
            return ('job_number',)
        # Otherwise (this is an "Add" page)
        return ()

    def get_fieldsets(self, request, obj=None):
        # If this is a "Change" page for an existing object
        if obj:
            return (
                ('Primary Details', {
                    'fields': ('job_type', 'customer', 'date', 'status', 'job_number')
                }),
                ('Location & Equipment', {
                    'fields': ('rig', 'well', 'location', 'trans') # <-- ENSURE THIS IS 'trans'
                }),
                ('Notes', {
                    'fields': ('description',),
                    'classes': ('collapse',)
                }),
            )
        # If this is an "Add" page for a new object
        else:
            return (
                ('Primary Details', {
                    'fields': ('job_type', 'customer', 'date', 'status')
                }),
                ('Location & Equipment', {
                    'fields': ('rig', 'well', 'location', 'trans') # <-- ENSURE THIS IS 'trans'
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