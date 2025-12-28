from django.urls import path
from . import views

urlpatterns = [
    path('', views.job_list_view, name='job_list'),
    path('<int:job_id>/', views.job_detail_view, name='job_detail'),
    
    path('create/', views.job_create_view, name='job_create'),

    path(
      'load-available-items/<int:job_id>/', 
      views.load_available_items_view, 
      name='load_available_items'
    ),
    path(
      'load-on-job-items/<int:job_id>/', 
      views.load_on_job_items_view, 
      name='load_on_job_items'
    ),

    path(
        'ticket/<str:ticket_type>/<int:ticket_id>/pdf/', 
        views.ticket_pdf_view, 
        name='ticket_pdf'
    ),

    path('end-job/<int:job_id>/', views.end_job_view, name='end_job'),
    path('reopen-job/<int:job_id>/', views.reopen_job_view, name='reopen_job'),
    
    path('ajax/smart-search/<int:job_id>/', views.smart_search_items_view, name='ajax_smart_search'),
    path('quick-create-delivery/<int:job_id>/', views.delivery_ticket_quick_create_view, name='delivery_ticket_quick_create'),
    path('quick-create-receiving/<int:job_id>/', views.receiving_ticket_quick_create_view, name='receiving_ticket_quick_create'),
    path('ajax/bulk-check-contract/<int:job_id>/', views.bulk_check_contract_view, name='ajax_bulk_check_contract'),
    path('receiving-ticket/<int:ticket_id>/upload-report/', views.upload_inspection_report_view, name='upload_inspection_report'),
    
    path('ticket/edit/<str:ticket_type>/<int:ticket_id>/', views.ticket_edit_view, name='ticket_edit'),
    
    path('export/<int:job_id>/', views.job_export_view, name='job_export')

]