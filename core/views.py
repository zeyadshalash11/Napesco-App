from django.shortcuts import render
from django.db.models import Count
from inventory.models import InventoryItem
from jobs.models import Job
from django.contrib.auth.decorators import login_required 


@login_required
def dashboard_view(request):
    available_count = InventoryItem.objects.filter(status='available').count()
    on_job_count = InventoryItem.objects.filter(status='on_job').count()
    re_cut_count = InventoryItem.objects.filter(status='re-cut').count()
    sold_count = InventoryItem.objects.filter(status='sold').count()
    pending_inspection_count = InventoryItem.objects.filter(status='pending_inspection').count()

    lih_count = InventoryItem.objects.filter(status='lih').count()
    junk_count = InventoryItem.objects.filter(status='junk').count()

    total_items = available_count + on_job_count + re_cut_count + pending_inspection_count + sold_count + lih_count + junk_count

    active_jobs = Job.objects.filter(status='open').order_by('-date')

    context = {
        'total_items': total_items,
        'available_count': available_count,
        'on_job_count': on_job_count,
        're_cut_count': re_cut_count,
        'pending_inspection_count': pending_inspection_count,
        'active_jobs': active_jobs,
        'sold_count': sold_count,
        'lih_count': lih_count,
        'junk_count': junk_count,
    }
    return render(request, 'core/dashboard.html', context)