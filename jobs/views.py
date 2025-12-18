import base64
from django.shortcuts import render
from django.urls import reverse
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
import os
from io import BytesIO
import zipfile
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
def job_export_view(request, job_id):
    job = get_object_or_404(Job, id=job_id)

    # Get all tickets for the job
    all_tickets = list(job.delivery_tickets.all()) + list(job.receiving_tickets.all())
    base_url = request.build_absolute_uri('/') # Base URL for WeasyPrint

    in_memory_zip = BytesIO()
    with zipfile.ZipFile(in_memory_zip, 'w', zipfile.ZIP_DEFLATED) as zf:
        
        # Generate and add a PDF for each ticket
        if not all_tickets:
            zf.writestr("no_tickets_found.txt", "This job has no delivery or receiving tickets.")
        else:
            for ticket in all_tickets:
                ticket_type_str = 'delivery' if isinstance(ticket, DeliveryTicket) else 'receiving'
                
                # Call the helper to get the PDF content.
                # We pass 'None' for extra_context because there's no driver info for a bulk export.
                pdf_content, ticket_number = generate_ticket_pdf_content(
                    ticket_type_str, ticket.id, base_url, extra_context=None
                )
                
                if pdf_content:
                    pdf_filename = f"Ticket_{ticket_number}_{ticket_type_str.capitalize()}.pdf"
                    zf.writestr(pdf_filename, pdf_content)

        # Add all job attachments
        for attachment in job.attachments.all():
            file_name = os.path.basename(attachment.file.name)
            with attachment.file.open('rb') as f:
                zf.writestr(file_name, f.read())

    in_memory_zip.seek(0)
    response = HttpResponse(in_memory_zip, content_type='application/zip')
    response['Content-Disposition'] = f'attachment; filename="job_{job.job_number}_export.zip"'
    
    return response

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

    preselect_receive_ids = request.GET.getlist('preselect_receive')
    
    on_job_items_for_js = [{
        'id': item.id,
        'serial': item.serial_number,
        'category': item.category.name,
        'location': item.get_location_display()
    } for item in on_job_items]

    context = {
        'job': job,
        'on_job_items': on_job_items,
        'ticket_history': ticket_history,
        'attachment_form': attachment_form,
        'attachments': attachments,
        'preselect_receive_ids': preselect_receive_ids,
        'on_job_items_json': on_job_items_for_js,
    }
    return render(request, 'jobs/job_detail.html', context)

def generate_ticket_pdf_content(ticket_type, ticket_id, base_url, extra_context=None):
    """
    Generates PDF content for a ticket using the app's specific logic.
    - base_url is required for WeasyPrint to find static files like CSS/images.
    - extra_context is a dict for optional data like driver_name, truck_no, etc.
    """
    # 1. Fetch the ticket object
    if ticket_type == 'delivery':
        ticket = get_object_or_404(DeliveryTicket, id=ticket_id)
        template_name = 'jobs/pdf/delivery_ticket_pdf.html'
        # Delivery tickets get items from the 'lines' related manager
        items_on_ticket = [line.item for line in ticket.lines.select_related('item__category').all()]
    elif ticket_type == 'receiving':
        ticket = get_object_or_404(ReceivingTicket, id=ticket_id)
        template_name = 'jobs/pdf/receiving_ticket_pdf.html'
        # Receiving tickets get items directly from the 'items' manager
        items_on_ticket = list(ticket.items.select_related('category').all())
    else:
        # This case should not be reached with valid URLs
        return None, None

    job = ticket.job

    # 2. Group items by category (your exact logic)
    items_by_category = {}
    for item in items_on_ticket:
        category_name = item.category.name
        if category_name not in items_by_category:
            items_by_category[category_name] = {'count': 0, 'serials': [], 'unit': item.category.unit}
        
        items_by_category[category_name]['count'] += 1
        items_by_category[category_name]['serials'].append(item.serial_number)

    # 3. Build the context dictionary
    context = {
        'ticket': ticket,
        'job': job,
        'items_by_category': items_by_category,
    }

    # Add optional context if provided (for driver name, etc.)
    if extra_context:
        context.update(extra_context)
    
    # Add the creator's name to the context
    creator_name = ticket.created_by.get_full_name() or ticket.created_by.username if ticket.created_by else "N/A"
    if ticket_type == 'delivery':
        context['delivered_by'] = creator_name
    elif ticket_type == 'receiving':
        context['received_by'] = creator_name

    # 4. Render HTML and generate PDF
    html_string = render_to_string(template_name, context)
    pdf_file = HTML(string=html_string, base_url=base_url).write_pdf()

    # 5. Return the raw PDF content and the ticket number
    return pdf_file, ticket.ticket_number

@login_required
def ticket_pdf_view(request, ticket_type, ticket_id):
    # Gather the extra context from the URL GET parameters
    extra_context = {
        'driver_name': request.GET.get('driver_name', ''),
        'truck_no': request.GET.get('truck_no', ''),
        'notes': request.GET.get('notes', ''),
        'id_license': request.GET.get('id_license', ''),
    }

    base_url = request.build_absolute_uri()
    
    # Call the helper to do all the hard work
    pdf_content, ticket_number = generate_ticket_pdf_content(
        ticket_type, ticket_id, base_url, extra_context
    )

    if not pdf_content:
        return HttpResponse("Ticket not found or type is invalid", status=404)

    # Create and return the response
    response = HttpResponse(pdf_content, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{ticket_number}.pdf"'
    
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
    search_type = request.GET.get('type', 'available')
    query = request.GET.get('q', '').strip()

    id_list_str = request.GET.get('ids', '')
    if id_list_str:
        try:
            # Convert comma-separated string of IDs into a list of integers
            id_list = [int(id_str) for id_str in id_list_str.split(',')]
            queryset = InventoryItem.objects.filter(id__in=id_list)
        except ValueError:
            return JsonResponse([], safe=False)
        
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

@login_required
def ticket_edit_view(request, ticket_type, ticket_id):
    # 1. Determine the model and get the ticket instance
    if ticket_type == 'delivery':
        model = DeliveryTicket
    elif ticket_type == 'receiving':
        model = ReceivingTicket
    else:
        messages.error(request, "Invalid ticket type.")
        return redirect('dashboard') # Or wherever is appropriate

    ticket = get_object_or_404(model, id=ticket_id)
    job = ticket.job

    # 2. Get the items currently on the ticket
    if ticket_type == 'delivery':
        # For delivery, items are accessed via the 'lines' through model
        current_item_ids = ticket.lines.values_list('item_id', flat=True)
    else:
        # For receiving, it's a direct many-to-many
        current_item_ids = ticket.items.values_list('id', flat=True)

    # 3. Handle the form submission (POST request)
    if request.method == 'POST':
        
        new_item_ids_str = request.POST.getlist('items')
        
        # Convert the new list of IDs to integers for comparison.
        new_item_ids = {int(id_str) for id_str in new_item_ids_str}

        # The 'current_item_ids' from before the POST is the original list.
        original_item_ids = set(current_item_ids)
    
        removed_item_ids = original_item_ids - new_item_ids

        if removed_item_ids:
            if ticket_type == 'delivery':
                # If removed from a DELIVERY ticket, the item becomes AVAILABLE again.
                InventoryItem.objects.filter(id__in=removed_item_ids).update(status='available')
            elif ticket_type == 'receiving':
                # If removed from a RECEIVING ticket, the item is still ON THE JOB.
                InventoryItem.objects.filter(id__in=removed_item_ids).update(status='on_job')

        # Update the items
        if ticket_type == 'delivery':
            # For 'through' models, we must manage the relationship manually
            # This is a simple but effective way: clear existing and add new
            ticket.lines.all().delete() # Remove old item lines
            new_lines = []
            for item_id in new_item_ids:
                item = InventoryItem.objects.get(id=item_id)
                # We assume any edited item is still returnable; this could be made more complex if needed.
                new_lines.append(DeliveryTicketItem(ticket=ticket, item=item, is_returnable=True))
            DeliveryTicketItem.objects.bulk_create(new_lines)
        else: # Receiving
            # Direct M2M is easy; .set() handles adding and removing
            ticket.items.set(new_item_ids)

        # For Delivery tickets, update the date (as per your business rule)
        if ticket_type == 'delivery':
            new_date = request.POST.get('ticket_date')
            if new_date:
                # We update the original 'ticket_date', not 'updated_at'
                ticket.ticket_date = new_date

        # Update the 'modified_by' field and save
        ticket.modified_by = request.user
        ticket.save()

        messages.success(request, f"Ticket {ticket.ticket_number} updated successfully.")
        return redirect('job_detail', job_id=job.id)

    # 4. Prepare context for rendering the form (GET request)
    # Find all items that could potentially be on this ticket:
    # EITHER items currently available OR items already on this specific ticket.
    potential_items = InventoryItem.objects.filter(
        Q(status='available') | Q(id__in=current_item_ids)
    ).distinct().select_related('category')

    context = {
        'ticket': ticket,
        'ticket_type': ticket_type,
        'job': job,
        'potential_items': potential_items,
        'current_item_ids': list(current_item_ids),
    }
    return render(request, 'jobs/ticket_edit.html', context)

@login_required
def delivery_ticket_quick_create_view(request, job_id):
    job = get_object_or_404(Job, id=job_id)

    if request.method == 'POST':
        submitted_text = request.POST.get('serial_numbers_text', '')
        
        # 1. Clean the input: split by line, strip whitespace, remove empty lines
        submitted_serials = {s.strip() for s in submitted_text.splitlines() if s.strip()}

        if not submitted_serials:
            messages.error(request, "You must enter at least one serial number.")
            return redirect('delivery_ticket_quick_create', job_id=job.id)

        # 2. Find all matching inventory items in one query
        found_items = InventoryItem.objects.filter(serial_number__in=submitted_serials)

        # 3. Validate the items
        found_serials = {item.serial_number for item in found_items}
        not_found_serials = submitted_serials - found_serials
        
        unavailable_items = [
            item for item in found_items if item.status != 'available'
        ]

        # If there are any errors, build a message and stop
        if not_found_serials or unavailable_items:
            error_message = "Could not create ticket due to the following errors:"
            if not_found_serials:
                error_message += f"<br>- Not Found: {', '.join(not_found_serials)}"
            if unavailable_items:
                unavailable_list = [f"{item.serial_number} (status: {item.get_status_display()})" for item in unavailable_items]
                error_message += f"<br>- Not Available: {', '.join(unavailable_list)}"
            
            messages.error(request, error_message)
            # Re-render the page with the user's original input to let them fix it
            context = {'job': job, 'submitted_serials': submitted_text}
            return render(request, 'jobs/delivery_ticket_quick_create.html', context)
        
        # 4. If all validations pass, create the ticket
        try:
            with transaction.atomic():
                # Create the delivery ticket
                ticket = DeliveryTicket.objects.create(job=job, created_by=request.user)

                # Create ticket lines and prepare items for status update
                delivery_lines = []
                for item in found_items:
                    delivery_lines.append(
                        DeliveryTicketItem(ticket=ticket, item=item, is_returnable=True)
                    )
                    item.status = 'on_job' # Set status for bulk update

                # Perform bulk operations for efficiency
                DeliveryTicketItem.objects.bulk_create(delivery_lines)
                InventoryItem.objects.bulk_update(found_items, ['status'])

                messages.success(request, f"Successfully created Delivery Ticket {ticket.ticket_number} with {len(found_items)} items.")
                return redirect('job_detail', job_id=job.id)

        except Exception as e:
            messages.error(request, f"A database error occurred: {e}")
            context = {'job': job, 'submitted_serials': submitted_text}
            return render(request, 'jobs/delivery_ticket_quick_create.html', context)

    # For a GET request, just show the blank form
    context = {'job': job}
    return render(request, 'jobs/delivery_ticket_quick_create.html', context)


@login_required
def receiving_ticket_quick_create_view(request, job_id):
    job = get_object_or_404(Job, id=job_id)

    if request.method == 'POST':
        submitted_text = request.POST.get('serial_numbers_text', '')
        submitted_serials = {s.strip() for s in submitted_text.splitlines() if s.strip()}

        if not submitted_serials:
            messages.error(request, "You must enter at least one serial number.")
            return redirect('receiving_ticket_quick_create', job_id=job.id)

        # The "Smarter" Logic: Find items that are BOTH 'on_job' AND were delivered for THIS job.
        # This is the crucial safety check.
        items_on_this_job = DeliveryTicketItem.objects.filter(
            ticket__job=job, 
            is_returnable=True
        ).values_list('item_id', flat=True)

        found_items = InventoryItem.objects.filter(
            serial_number__in=submitted_serials,
            status='on_job',
            id__in=items_on_this_job
        )

        found_serials = {item.serial_number for item in found_items}
        not_found_serials = submitted_serials - found_serials

        if not_found_serials:
            messages.warning(request, f"The following serial numbers could not be found or are not valid for this job: {', '.join(not_found_serials)}")

        if not found_items:
            messages.error(request, "No valid items were found to receive.")
            return redirect('receiving_ticket_quick_create', job_id=job.id)
            
        # Instead of creating a ticket, we redirect to the job detail page,
        # passing the found item IDs as URL parameters.
        found_item_ids = [str(item.id) for item in found_items]
        
        # We use a special query parameter name like 'preselect_receive'
        redirect_url = f"{reverse('job_detail', args=[job.id])}?preselect_receive={'&preselect_receive='.join(found_item_ids)}"
        
        return redirect(redirect_url)

    context = {'job': job}
    return render(request, 'jobs/receiving_ticket_quick_create.html', context)