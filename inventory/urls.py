# inventory/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('', views.inventory_list_view, name='inventory_list'),
    path('details/<int:category_id>/<str:location>/', views.get_item_details_view, name='get_item_details'),
    path('details/', views.inventory_filtered_list_view, name='inventory_filtered_list'),
    path('download-template/', views.download_template_view, name='download_template'),
    path('import/', views.inventory_import_view, name='inventory_import'),
    path('import/results/', views.import_results_view, name='import_results'),
    path('change-status/', views.inventory_change_status_view, name='inventory_change_status'),
    path('ajax/search/', views.ajax_inventory_search, name='ajax_inventory_search'),
    path('export/', views.export_inventory_to_excel_view, name='export_inventory_to_excel'),

]   