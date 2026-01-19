from django.urls import path
from .views import hmmbuild_form, download_model, hmmbuild_status, hmmbuild_task_status

urlpatterns = [
    path('', hmmbuild_form, name='hmmbuild_form'),
    path('status/<int:project_id>/', hmmbuild_status, name='hmmbuild_status'),
    path('task-status/<str:task_id>/', hmmbuild_task_status, name='hmmbuild_task_status'),
    path('download/<str:file_name>/', download_model, name='download_result'),
]
