from django.shortcuts import render
from .models import Job
from django.shortcuts import render, get_object_or_404, redirect
from inventory.models import InventoryItem
from django.contrib import messages
from django.db import transaction
from .models import Job, DeliveryTicket, ReceivingTicket , JobAttachment ,Contract
from operator import attrgetter
from .forms import JobAttachmentForm
from django.conf import settings
from django.http import HttpResponse
from django.template.loader import render_to_string
from weasyprint import HTML
import base64
from django.contrib.staticfiles import finders
from django.http import JsonResponse
from django.db.models import Q

def job_list_view(request):
    search_query = request.GET.get('q', '')
    queryset = Job.objects.all()

    if search_query:
        # Search in job_number OR customer OR date
        # The date search is a simple "contains" search
        queryset = queryset.filter(
            Q(job_number__icontains=search_query) |
            Q(customer__icontains=search_query) | # <-- THIS IS THE PROBLEM
            Q(date__icontains=search_query)
        )

    context = {
        'jobs': queryset.order_by('-date'), # Order the final results
        'search_query': search_query,
    }
    return render(request, 'jobs/job_list.html', context)

def load_available_items_view(request, job_id):
    location = request.GET.get('location')
    items = InventoryItem.objects.filter(status='available', location=location)
    return render(request, 'jobs/partials/_delivery_item_list.html', {'items': items})


def load_on_job_items_view(request, job_id):
    job = get_object_or_404(Job, id=job_id) # Get the job object
    
    # Use the same robust logic as the main page
    all_items_ever_delivered_for_job = InventoryItem.objects.filter(
        delivery_tickets__job=job
    ).distinct()

    items_to_receive = []
    for item in all_items_ever_delivered_for_job:
        if item.status == 'on_job':
            last_delivery = item.delivery_tickets.filter(job=job).order_by('-ticket_date').first()
            last_receiving = item.receiving_tickets.filter(job=job).order_by('-ticket_date').first()
            if last_delivery:
                if not last_receiving or last_delivery.ticket_date > last_receiving.ticket_date:
                    items_to_receive.append(item)

    return render(request, 'jobs/partials/_receiving_item_list.html', {'items': items_to_receive})

def job_detail_view(request, job_id):
    job = get_object_or_404(Job, id=job_id)
    # Initialize the attachment form for use in both GET and POST contexts
    attachment_form = JobAttachmentForm()

    if request.method == 'POST':
        # --- NEW: Attachment Form Handling ---
        # Check if the 'submit_attachment' button was pressed
        if 'submit_attachment' in request.POST:
            form = JobAttachmentForm(request.POST, request.FILES)
            if form.is_valid():
                # Get all the files uploaded (handles multiple file selection)
                files = request.FILES.getlist('file')
                caption = form.cleaned_data['caption']
                # Loop through each file and create an attachment object for it
                for f in files:
                    JobAttachment.objects.create(job=job, file=f, caption=caption)
                messages.success(request, f"{len(files)} file(s) uploaded successfully.")
            else:
                messages.error(request, "There was an error with your upload.")
            return redirect('job_detail', job_id=job.id)

        # --- EXISTING TICKET LOGIC (Wrapped in an 'else' block) ---
        else:
            try:
                with transaction.atomic():
                    if 'submit_delivery' in request.POST:
                        ticket = DeliveryTicket.objects.create(job=job)
                        items_to_process = InventoryItem.objects.filter(id__in=request.POST.getlist('selected_items'), status='available')
                        if len(items_to_process) != len(request.POST.getlist('selected_items')):
                            raise Exception("Some selected items are no longer available. Please reload and try again.")
                        for item in items_to_process:
                            item.status = 'on_job'
                            item.save()
                            ticket.items.add(item)
                        messages.success(request, f"Successfully created Delivery Ticket {ticket.ticket_number}.")

                    elif 'submit_receiving' in request.POST:
                        ticket = ReceivingTicket.objects.create(job=job)
                        items_to_process_ids = request.POST.getlist('selected_items')
                        if not items_to_process_ids:
                            raise Exception("You must select at least one item to receive.")
                        items_to_process = InventoryItem.objects.filter(id__in=items_to_process_ids)
                        for item in items_to_process:
                            status_key = f'new_status_{item.id}'
                            new_status = request.POST.get(status_key, 'available')
                            item.status = new_status
                            item.save()
                            ticket.items.add(item)
                        messages.success(request, f"Successfully created Receiving Ticket {ticket.ticket_number}.")
            except Exception as e:
                messages.error(request, f"An error occurred: {e}")
            return redirect('job_detail', job_id=job.id)

    # --- GET LOGIC (Add attachments to context) ---
    delivery_tickets_qs = job.delivery_tickets.all().prefetch_related('items')
    receiving_tickets_qs = job.receiving_tickets.all().prefetch_related('items')
    
    ticket_history_list = []
    for ticket in delivery_tickets_qs:
        ticket_history_list.append({
            'type': 'Delivery', 'ticket_obj': ticket, 'items': list(ticket.items.all())
        })
    for ticket in receiving_tickets_qs:
        ticket_history_list.append({
            'type': 'Receiving', 'ticket_obj': ticket, 'items': list(ticket.items.all())
        })

    ticket_history = sorted(
        ticket_history_list, key=lambda t: t['ticket_obj'].ticket_date, reverse=True
    )

    all_items_ever_delivered_for_job = InventoryItem.objects.filter(
        delivery_tickets__job=job
    ).distinct()
    on_job_items = []
    for item in all_items_ever_delivered_for_job:
        if item.status == 'on_job':
            last_delivery = item.delivery_tickets.filter(job=job).order_by('-ticket_date').first()
            last_receiving = item.receiving_tickets.filter(job=job).order_by('-ticket_date').first()
            if last_delivery:
                if not last_receiving or last_delivery.ticket_date > last_receiving.ticket_date:
                    on_job_items.append(item)
    
    # NEW: Fetch existing attachments for this job
    attachments = job.attachments.all()
    
    context = {
        'job': job,
        'on_job_items': on_job_items,
        'ticket_history': ticket_history,
        'attachment_form': attachment_form, # NEW: Add form to context
        'attachments': attachments,         # NEW: Add attachments to context
    }
    return render(request, 'jobs/job_detail.html', context)


def ticket_pdf_view(request, ticket_type, ticket_id):
    ticket = None
    template_name = '' # Variable to hold the template path

    if ticket_type == 'delivery':
        ticket = get_object_or_404(DeliveryTicket, id=ticket_id)
        template_name = 'jobs/pdf/delivery_ticket_pdf.html' # Use the existing delivery template
    elif ticket_type == 'receiving':
        ticket = get_object_or_404(ReceivingTicket, id=ticket_id)
        template_name = 'jobs/pdf/receiving_ticket_pdf.html' # Use the NEW receiving template
    
    if not ticket:
        return HttpResponse("Ticket not found or type is invalid", status=404)

    job = ticket.job
    items_on_ticket = ticket.items.all()

    # Group items by category and count them
    items_by_category = {}
    for item in items_on_ticket:
        category_name = item.category.name
        if category_name not in items_by_category:
            # Initialize with a count and a list for serials
            items_by_category[category_name] = {'count': 0, 'serials': []}
        
        # Increment the count and add the serial number
        items_by_category[category_name]['count'] += 1
        items_by_category[category_name]['serials'].append(item.serial_number)
    # This logic for embedding the logo is the same for both

    logo_path = finders.find('img/napesco_logo.png')
    encoded_string = ""
    if logo_path:
        with open(logo_path, "rb") as image_file:
            encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
    logo_data_uri = f"data:image/webp;base64,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,{encoded_string}"
     
    notes_text = request.GET.get('notes', '')
 
    context = {
        'ticket': ticket,
        'job': job,
        'items_by_category': items_by_category,
        'logo_data_uri': logo_data_uri,
        'notes': notes_text,
    }

    html_string = render_to_string(template_name, context)
    pdf_file = HTML(string=html_string, base_url=request.build_absolute_uri()).write_pdf()

    response = HttpResponse(pdf_file, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{ticket.ticket_number}.pdf"'
    
    return response

def end_job_view(request, job_id):
    job = get_object_or_404(Job, id=job_id)

    # --- THIS IS THE NEW, CORRECT LOGIC ---
    # We use the same robust calculation from the job detail page.
    all_items_ever_delivered_for_job = InventoryItem.objects.filter(
        delivery_tickets__job=job
    ).distinct()

    on_job_items = []
    for item in all_items_ever_delivered_for_job:
        if item.status == 'on_job':
            last_delivery = item.delivery_tickets.filter(job=job).order_by('-ticket_date').first()
            last_receiving = item.receiving_tickets.filter(job=job).order_by('-ticket_date').first()
            if last_delivery:
                if not last_receiving or last_delivery.ticket_date > last_receiving.ticket_date:
                    on_job_items.append(item)

    # THE CORE CHECK: Is the list of items currently on job empty?
    if len(on_job_items) == 0:
        # SUCCESS: No items are currently out. Close the job.
        job.status = 'closed'
        job.save()
        messages.success(request, f"Job '{job.job_number}' has been successfully closed.")
    else:
        # FAILURE: There are still items on the job.
        unreturned_serials = ", ".join([item.serial_number for item in on_job_items])
        messages.error(
            request, 
            f"Cannot close job '{job.job_number}'. The following items have not been returned: {unreturned_serials}"
        )
    
    return redirect('job_list')


def reopen_job_view(request, job_id):
    job = get_object_or_404(Job, id=job_id)
    job.status = 'open'
    job.save()
    messages.success(request, f"Job '{job.job_number}' has been re-opened.")
    return redirect('job_list')


# Add this new view and delete the old search_..._views

def smart_search_items_view(request, job_id):
    query = request.GET.get('q', '').strip()
    # 'search_type' will be 'available' or 'on_job'
    search_type = request.GET.get('type', 'available')

    if not query:
        return JsonResponse([], safe=False)

    queryset = InventoryItem.objects.all()

    if search_type == 'available':
        queryset = queryset.filter(status='available')
    elif search_type == 'on_job':
        job = get_object_or_404(Job, id=job_id)
        # Use our robust "on job" logic to get the correct item PKs
        all_items_ever_delivered_for_job = InventoryItem.objects.filter(delivery_tickets__job=job).distinct()
        on_job_items_pks = []
        for item in all_items_ever_delivered_for_job:
            if item.status == 'on_job':
                # (... include the full timestamp comparison logic here ...)
                last_delivery = item.delivery_tickets.filter(job=job).order_by('-ticket_date').first()
                last_receiving = item.receiving_tickets.filter(job=job).order_by('-ticket_date').first()
                if last_delivery and (not last_receiving or last_delivery.ticket_date > last_receiving.ticket_date):
                    on_job_items_pks.append(item.pk)
        queryset = queryset.filter(pk__in=on_job_items_pks)

    # Filter by the user's search query
    items = queryset.filter(serial_number__icontains=query)[:20]
    
    # Return a rich JSON object with all the data we need
    results = [{
        'id': item.id, 
        'serial': item.serial_number,
        'category': item.category.name,
        'location': item.get_location_display()
    } for item in items]
    
    return JsonResponse(results, safe=False)


def bulk_check_contract_view(request, job_id):
    item_ids = request.GET.getlist('item_ids[]')
    if not item_ids:
        return JsonResponse({'error': 'No item IDs provided'}, status=400)

    try:
        job = Job.objects.select_related('customer__contract').get(id=job_id)
        
        # If customer has no contract, all items are out of contract
        if not hasattr(job.customer, 'contract'):
            items_out_of_contract = InventoryItem.objects.filter(id__in=item_ids)
        else:
            contract_item_categories = job.customer.contract.items.all()
            # Find all items from the selection that are NOT in the contract categories
            items_out_of_contract = InventoryItem.objects.filter(id__in=item_ids).exclude(category__in=contract_item_categories)

        # Return a list of the serial numbers for the out-of-contract items
        out_of_contract_serials = [item.serial_number for item in items_out_of_contract]
        return JsonResponse({'out_of_contract_serials': out_of_contract_serials})

    except Job.DoesNotExist:
        return JsonResponse({'error': 'Job not found'}, status=404)