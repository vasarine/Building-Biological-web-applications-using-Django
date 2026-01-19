from django.db import models
from django.conf import settings
from django.utils import timezone
from datetime import timedelta
import uuid


class BaseHMMProject(models.Model):
    """
    Abstract base class for all HMM project models.
    Eliminates code duplication across HMMBuildProject, HMMEmitProject, and HMMSearchProject.
    """
    VISIBILITY_CHOICES = [
        ('private', 'Private'),
        ('link', 'Link'),
        ('public', 'Public'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True)
    name = models.CharField(max_length=255)
    result_text = models.TextField(null=True, blank=True)

    task_id = models.CharField(max_length=255, null=True, blank=True, db_index=True)
    task_status = models.CharField(max_length=50, default='PENDING', null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    is_temporary = models.BooleanField(default=True, db_index=True)
    expires_at = models.DateTimeField(null=True, blank=True, db_index=True)

    visibility = models.CharField(max_length=10, choices=VISIBILITY_CHOICES, default='private', db_index=True)
    shared_with = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name='shared_%(class)s_projects',
        blank=True
    )
    share_token = models.UUIDField(default=uuid.uuid4, editable=False, db_index=True)

    class Meta:
        abstract = True
        indexes = [
            models.Index(fields=['user', 'task_status', '-created_at']),
            models.Index(fields=['user', 'expires_at']),
            models.Index(fields=['visibility', 'expires_at']),
        ]

    def save(self, *args, **kwargs):
        """Set expiration based on user authentication status"""
        if not self.pk and self.expires_at is None:
            if self.user is None:
                self.is_temporary = True
                self.expires_at = timezone.now() + timedelta(days=7)
            else:
                self.is_temporary = False
                self.expires_at = None
        super().save(*args, **kwargs)

    def can_view(self, user):
        """Check if user can view the project"""
        if self.user == user:
            return True
        if self.visibility == 'public':
            return True
        if self.visibility == 'link':
            return True
        if user.is_authenticated and self.shared_with.filter(id=user.id).exists():
            return True
        return False

    def can_edit(self, user):
        """Check if user can edit the project"""
        return self.user == user

    def __str__(self):
        username = self.user.username if self.user else "Anonymous"
        return f"{self.name} ({username})"
