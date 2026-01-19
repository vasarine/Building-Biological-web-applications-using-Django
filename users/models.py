from django.db import models
from django.contrib.auth.models import User
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType


class UserActionHistory(models.Model):
    ACTION_TYPES = [
        ('project_created', 'Project Created'),
        ('project_completed', 'Project Completed'),
        ('project_failed', 'Project Failed'),
        ('project_deleted', 'Project Deleted'),
        ('project_shared', 'Project Shared'),
        ('project_visibility_changed', 'Visibility Changed'),
        ('file_downloaded', 'File Downloaded'),
    ]

    TOOL_TYPES = [
        ('hmmbuild', 'HMMBUILD'),
        ('hmmemit', 'HMMEMIT'),
        ('hmmsearch', 'HMMSEARCH'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='action_history', null=True, blank=True)
    action_type = models.CharField(max_length=50, choices=ACTION_TYPES)
    tool_type = models.CharField(max_length=20, choices=TOOL_TYPES)
    timestamp = models.DateTimeField(auto_now_add=True)

    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, null=True, blank=True)
    object_id = models.PositiveIntegerField(null=True, blank=True)
    project = GenericForeignKey('content_type', 'object_id')

    project_name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=20, default='success', choices=[('success', 'Success'), ('failure', 'Failure')])
    error_message = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['-timestamp']
        verbose_name = 'User Action History'
        verbose_name_plural = 'User Action Histories'
        indexes = [
            models.Index(fields=['-timestamp', 'user']),
            models.Index(fields=['user', 'tool_type']),
        ]

    def __str__(self):
        return f"{self.user} - {self.action_type} - {self.project_name} at {self.timestamp}"

    def get_project_url(self):
        if (
            self.action_type in ['project_created', 'project_completed']
            and self.tool_type
            and self.project
        ):
            share_token = getattr(self.project, 'share_token', None)
            if share_token:
                return f"/users/shared/{self.tool_type}/{share_token}/"
        return None

