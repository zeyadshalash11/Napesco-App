from django.shortcuts import render
from .models import Job
from django.shortcuts import render, get_object_or_404, redirect
from inventory.models import InventoryItem
from django.contrib import messages
from django.db import transaction
from .models import Job, DeliveryTicket, DeliveryTicketItem,ReceivingTicket , JobAttachment ,Contract
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
from django.contrib.auth.decorators import login_required
from .forms import JobAttachmentForm, JobForm 

@login_required
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

@login_required
def load_available_items_view(request, job_id):
    location = request.GET.get('location')
    items = InventoryItem.objects.filter(status='available', location=location)
    return render(request, 'jobs/partials/_delivery_item_list.html', {'items': items})

@login_required
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

@login_required
def job_detail_view(request, job_id):
    job = get_object_or_404(Job, id=job_id)
    attachment_form = JobAttachmentForm()

    if request.method == 'POST':
        # ---------- Attachments ----------
        if 'submit_attachment' in request.POST:
            form = JobAttachmentForm(request.POST, request.FILES)
            if form.is_valid():
                files = request.FILES.getlist('file')
                caption = form.cleaned_data.get('caption', '')
                for f in files:
                    JobAttachment.objects.create(job=job, file=f, caption=caption)
                messages.success(request, f"{len(files)} file(s) uploaded successfully.")
            else:
                messages.error(request, "There was an error with your upload.")
            return redirect('job_detail', job_id=job.id)

        # ---------- Tickets (Delivery / Receiving) ----------
        try:
            with transaction.atomic():

                # ===== DELIVERY =====
                if 'submit_delivery' in request.POST:
                    selected_ids = request.POST.getlist('selected_items')
                    if not selected_ids:
                        raise Exception("You must select at least one item to deliver.")

                    # Lock rows to prevent race conditions (two users delivering same item)
                    items_to_process = list(
                        InventoryItem.objects.select_for_update()
                        .filter(id__in=selected_ids, status='available')
                    )

                    if len(items_to_process) != len(selected_ids):
                        raise Exception("Some selected items are no longer available. Please reload and try again.")

                    ticket = DeliveryTicket.objects.create(job=job, created_by=request.user)

                    delivery_lines = []
                    items_to_update = []

                    for item in items_to_process:
                        # Expect a checkbox/hidden input in template:
                        # name="delivery_sold_<id>" value "1" if sold else "0"
                        is_sold = request.POST.get(f"delivery_sold_{item.id}") == "1"

                        if is_sold:
                            item.status = 'sold'
                            is_returnable = False
                        else:
                            item.status = 'on_job'
                            is_returnable = True

                        items_to_update.append(item)
                        delivery_lines.append(
                            DeliveryTicketItem(
                                ticket=ticket,
                                item=item,
                                is_returnable=is_returnable
                            )
                        )

                    InventoryItem.objects.bulk_update(items_to_update, ['status'])
                    DeliveryTicketItem.objects.bulk_create(delivery_lines)

                    messages.success(request, f"Successfully created Delivery Ticket {ticket.ticket_number}.")

                # ===== RECEIVING =====
                elif 'submit_receiving' in request.POST:
                    selected_ids = request.POST.getlist('selected_items')
                    if not selected_ids:
                        raise Exception("You must select at least one item to receive.")

                    ticket = ReceivingTicket.objects.create(job=job, created_by=request.user)

                    # Lock items while updating
                    items_to_process = list(
                        InventoryItem.objects.select_for_update()
                        .filter(id__in=selected_ids)
                    )

                    items_to_update = []
                    for item in items_to_process:
                        status_key = f'new_status_{item.id}'
                        new_status = request.POST.get(status_key, 'available')
                        item.status = new_status
                        items_to_update.append(item)

                    InventoryItem.objects.bulk_update(items_to_update, ['status'])

                    # ReceivingTicket still uses normal M2M, this is fine:
                    ticket.items.add(*items_to_process)

                    messages.success(request, f"Successfully created Receiving Ticket {ticket.ticket_number}.")

        except Exception as e:
            messages.error(request, f"An error occurred: {e}")

        return redirect('job_detail', job_id=job.id)

    # ---------------- GET LOGIC ----------------

    # Delivery tickets now use lines__item (through model)
    delivery_tickets_qs = job.delivery_tickets.all().prefetch_related('lines__item')

    # Receiving still uses direct items M2M
    receiving_tickets_qs = job.receiving_tickets.all().prefetch_related('items')

    ticket_history_list = []

    for ticket in delivery_tickets_qs:
        ticket_history_list.append({
            'type': 'Delivery',
            'ticket_obj': ticket,
            # list of DeliveryTicketItem objects (each has .item and .is_returnable)
            'items_list': list(ticket.lines.all())
        })

    for ticket in receiving_tickets_qs:
        ticket_history_list.append({
            'type': 'Receiving',
            'ticket_obj': ticket,
            # list of InventoryItem objects
            'items_list': list(ticket.items.all())
        })

    ticket_history = sorted(
        ticket_history_list, key=lambda t: t['ticket_obj'].ticket_date, reverse=True
    )

    # Compute "still out" items: returnable delivered items that are not received yet
    returnable_delivered_ids = DeliveryTicketItem.objects.filter(
        ticket__job=job,
        is_returnable=True
    ).values_list('item_id', flat=True)

    received_ids = ReceivingTicket.objects.filter(
        job=job
    ).values_list('items__id', flat=True)

    on_job_items = InventoryItem.objects.filter(
        deliveryticketitem__ticket__job=job,
        deliveryticketitem__is_returnable=True,
        status='on_job'
    ).select_related('category').distinct()

    attachments = job.attachments.all()

    context = {
        'job': job,
        'on_job_items': on_job_items,
        'ticket_history': ticket_history,
        'attachment_form': attachment_form,
        'attachments': attachments,
    }
    return render(request, 'jobs/job_detail.html', context)

@login_required
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
    items_on_ticket = list(ticket.items.select_related('category').all())


    # Group items by category and count them
    items_by_category = {}
    for item in items_on_ticket:
        category_name = item.category.name
        if category_name not in items_by_category:
            # Initialize with a count and a list for serials
            items_by_category[category_name] = {'count': 0, 'serials': [], 'unit': item.category.unit}
        
        # Increment the count and add the serial number
        items_by_category[category_name]['count'] += 1
        items_by_category[category_name]['serials'].append(item.serial_number)
    # This logic for embedding the logo is the same for both

    # 1. Get the logged-in user's full name. Fallback to username if not set.
    driver_name = request.GET.get('driver_name', '')
    truck_no = request.GET.get('truck_no', '')
    notes_text = request.GET.get('notes', '')
    # For delivery tickets, we also get the id_license
    id_license = request.GET.get('id_license', '') 

    # Initialize context variables
    context = {
        'ticket': ticket,
        'job': job,
        'items_by_category': items_by_category,
        'driver_name': driver_name,
        'truck_no': truck_no,
        'notes': notes_text,
        'id_license': id_license, # Pass it for delivery tickets
    }

    # Now, get the user's name from the correct source
    if ticket.created_by:
        creator_name = ticket.created_by.get_full_name() or ticket.created_by.username
    else:
        creator_name = "N/A" # Fallback if ticket has no creator

    # Add the correct variable to the context based on ticket type
    if ticket_type == 'delivery':
        context['delivered_by'] = creator_name
    elif ticket_type == 'receiving':
        context['received_by'] = creator_name

    html_string = render_to_string(template_name, context)
    pdf_file = HTML(string=html_string, base_url=request.build_absolute_uri()).write_pdf()

    response = HttpResponse(pdf_file, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{ticket.ticket_number}.pdf"'
    
    return response

@login_required
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

@login_required
def reopen_job_view(request, job_id):
    job = get_object_or_404(Job, id=job_id)
    job.status = 'open'
    job.save()
    messages.success(request, f"Job '{job.job_number}' has been re-opened.")
    return redirect('job_list')


@login_required
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

@login_required
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
    

@login_required 
def job_create_view(request):
    if request.method == 'POST':
        form = JobForm(request.POST)
        if form.is_valid():
            new_job = form.save() # This automatically triggers your model's save() method!
            messages.success(request, f"Successfully created Job: {new_job.job_number}")
            return redirect('job_detail', job_id=new_job.id) # Redirect to the new job's detail page
    else:
        form = JobForm()

    context = {
        'form': form
    }
    return render(request, 'jobs/job_form.html', context)    