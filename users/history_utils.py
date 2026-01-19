from django.contrib.contenttypes.models import ContentType
from .models import UserActionHistory


def log_user_action(user, action_type, tool_type, project, project_name, description='', status='success', error_message='', metadata=None):
    if metadata is None:
        metadata = {}

    if not user or not user.is_authenticated:
        return None

    content_type = ContentType.objects.get_for_model(project)

    history = UserActionHistory.objects.create(
        user=user,
        action_type=action_type,
        tool_type=tool_type,
        content_type=content_type,
        object_id=project.id,
        project_name=project_name,
        description=description,
        status=status,
        error_message=error_message,
        metadata=metadata
    )

    return history
