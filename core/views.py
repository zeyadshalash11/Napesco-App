from django.shortcuts import render
from django.db.models import Count
from inventory.models import InventoryItem
from jobs.models import Job
from django.contrib.auth.decorators import login_required 


@login_required
def dashboard_view(request):
    # Get counts for each status with separate, clear queries
    available_count = InventoryItem.objects.filter(status='available').count()
    on_job_count = InventoryItem.objects.filter(status='on_job').count()
    re_cut_count = InventoryItem.objects.filter(status='re-cut').count()
    lih_dbr_count = InventoryItem.objects.filter(status='lih-dbr').count()
    
    # --- NEW COUNT ---
    pending_inspection_count = InventoryItem.objects.filter(status='pending_inspection').count()

    total_items = available_count + on_job_count + re_cut_count + lih_dbr_count + pending_inspection_count
    attention_count = re_cut_count + lih_dbr_count

    active_jobs = Job.objects.filter(status='open').order_by('-date')

    context = {
        'total_items': total_items,
        'available_count': available_count,
        'on_job_count': on_job_count,
        'attention_count': attention_count,
        'pending_inspection_count': pending_inspection_count, # <-- PASS TO TEMPLATE
        'active_jobs': active_jobs,
    }
    return render(request, 'core/dashboard.html', context)