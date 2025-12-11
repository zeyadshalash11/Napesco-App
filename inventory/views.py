from django.shortcuts import render , redirect
from django.db.models import Count
from .models import InventoryItem, ProductCategory
from django.contrib import messages
from django.db import models
from django.core.management import call_command
from django.http import FileResponse
from django.contrib.staticfiles import finders
from .utils import process_inventory_file 
import pandas as pd
from django.contrib.auth.decorators import login_required 

@login_required
def inventory_list_view(request):
    search_query = request.GET.get('q', '')

    # Start with the base query that we will group later
    base_queryset = InventoryItem.objects.all()

    # If there is a search query, we apply the filter logic
    if search_query:
        # We want to find items where EITHER the serial number contains the query
        # OR the related category's name contains the query.
        # This gives us a list of all individual items that match.
        matching_items = base_queryset.filter(
            models.Q(serial_number__icontains=search_query) |
            models.Q(category__name__icontains=search_query)
        )
        
        # Now, we find out which unique category IDs these matching items belong to.
        matching_category_ids = matching_items.values_list('category_id', flat=True).distinct()
        
        # We will now use these category IDs to filter our main summary query.
        # However, the summary query is on the base_queryset, so we can just filter it directly.
        base_queryset = base_queryset.filter(category_id__in=matching_category_ids)

    # Now, perform the aggregation on the (potentially filtered) base_queryset
    summary_query = base_queryset.values(
        'location', 
        'category__id', 
        'category__name'
    ).annotate(
        quantity=Count('id')
    ).order_by('location', 'category__name')

    # The rest of the logic remains the same
    maadi_summary = []
    abu_rudies_summary = []

    for item in summary_query:
        location = item.get('location', '').strip()
        if location == 'maadi-yard':
            maadi_summary.append(item)
        elif location == 'abu-rudies-yard':
            abu_rudies_summary.append(item)
    
    context = {
        'maadi_summary': maadi_summary,
        'abu_rudies_summary': abu_rudies_summary,
        'search_query': search_query,
    }
    return render(request, 'inventory/inventory_list.html', context)

@login_required
def get_item_details_view(request, category_id, location):
    # This view is now simple again. It only fetches and returns details.
    items = InventoryItem.objects.filter(category_id=category_id, location=location)
    context = {
        'items': items
    }
    return render(request, 'inventory/_item_details.html', context)

@login_required
def inventory_filtered_list_view(request):
    title = "Inventory Details"
    status_filter = request.GET.get('status', None)
    search_query = request.GET.get('q', '')

    queryset = InventoryItem.objects.all()

    if status_filter:
        if status_filter == 'available':
            title = "Available Items"
            queryset = queryset.filter(status='available')
        elif status_filter == 'on_job':
            title = "Items On Job"
            queryset = queryset.filter(status='on_job')
        elif status_filter == 'pending_inspection':
            title = "Items Pending Inspection"
            queryset = queryset.filter(status='pending_inspection')
        elif status_filter == 'attention':
            title = "Items Requiring Attention"
            queryset = queryset.filter(models.Q(status='re-cut') | models.Q(status='lih-dbr'))
    
    if search_query:
        # Search by serial number or category name
        queryset = queryset.filter(
            models.Q(serial_number__icontains=search_query) |
            models.Q(category__name__icontains=search_query)
        )

    context = {
        'title': title,
        'items': queryset,
        'search_query': search_query,
        'status_filter': status_filter,
    }
    return render(request, 'inventory/inventory_filtered_list.html', context)

@login_required
def download_template_view(request):
    file_path = finders.find('downloads/import_template.xlsx')
    response = FileResponse(open(file_path, 'rb'), as_attachment=True, filename='import_template.xlsx')
    return response

@login_required
def import_results_view(request):
    summary = request.session.get('import_summary', None)
    # Clear the summary from the session so it doesn't show again on refresh
    if 'import_summary' in request.session:
        del request.session['import_summary']
    
    return render(request, 'inventory/import_results.html', {'summary': summary})

@login_required
def inventory_import_view(request):
    if request.method == 'POST':
        file = request.FILES.get('inventory_file')

        if not file:
            messages.error(request, "No file was selected for upload.")
            return redirect('inventory_import')
        
        try:
            # Read the file into a pandas DataFrame
            if file.name.endswith('.xlsx'):
                df = pd.read_excel(file)
            elif file.name.endswith('.csv'):
                df = pd.read_csv(file)
            else:
                messages.error(request, "Unsupported file format. Please upload a .xlsx or .csv file.")
                return redirect('inventory_import')

            # Call our reusable processing function
            summary = process_inventory_file(df)

            # Recalculate quantities if there were no critical errors
            if "A critical error occurred" not in str(summary['errors']):
                call_command('recalculate_quantities')
            
            # Store summary in session and redirect to results page
            request.session['import_summary'] = summary
            return redirect('import_results')

        except Exception as e:
            messages.error(request, f"An error occurred while processing the file: {e}")
            return redirect('inventory_import')

    return render(request, 'inventory/import_form.html')