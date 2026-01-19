from django.urls import path
from . import views

urlpatterns = [
    path("", views.hmmemit_form, name="hmmemit_form"),
    path('status/<int:project_id>/', views.hmmemit_status, name='hmmemit_status'),
    path('task-status/<str:task_id>/', views.hmmemit_task_status, name='hmmemit_task_status'),
    path('download/<str:file_name>/', views.download_emit, name='hmmemit_download'),
]
