from django.urls import path
from . import views

urlpatterns = [
    path("", views.hmmsearch_form, name="hmmsearch_form"),
    path('status/<int:project_id>/', views.hmmsearch_status, name='hmmsearch_status'),
    path('task-status/<str:task_id>/', views.hmmsearch_task_status, name='hmmsearch_task_status'),
    path('download/<str:file_name>/', views.download_search_file, name='hmmsearch_download'),
]