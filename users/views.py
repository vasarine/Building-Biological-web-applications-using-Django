from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from .forms import RegisterForm, ProjectSharingForm
from django.db import transaction
from django.urls import reverse
from django.utils import timezone
from django.contrib import messages
from django.http import HttpResponseForbidden, JsonResponse
from django.core.paginator import Paginator
from django.db.models import Q
from hmmsearch.models import HMMSearchProject
from hmmbuild.models import HMMBuildProject
from hmmemit.models import HMMEmitProject
from .models import UserActionHistory
from .history_utils import log_user_action
import os

from biologine_aplikacija.utils import delete_project_files


MODEL_FIELDS = {
    "hmmbuild": (HMMBuildProject, ("msa_file", "hmm_file")),
    "hmmemit": (HMMEmitProject, ("hmm_file", "output_file")),
    "hmmsearch": (HMMSearchProject, ("fasta_file", "hmm_file", "out_file", "tblout_file", "domtbl_file")),
}


def has_files(project, file_fields):
    """Check if at least one project file exists"""
    for field_name in file_fields:
        file_field = getattr(project, field_name, None)
        if file_field and file_field.name:
            try:
                if os.path.exists(file_field.path):
                    return True
            except:
                pass
    return False


def register(request):
    if request.method == "POST":
        form = RegisterForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect("home")
    else:
        form = RegisterForm()
    return render(request, "registration/register.html", {"form": form})

@login_required
def my_projects(request):
    """
    Display user projects, filtered by selected tool (hmmbuild/hmmsearch/hmmemit).
    Does not show expired projects and projects with deleted files.
    Also shows projects that are shared with me.
    """
    user = request.user
    active_tool = request.GET.get('tool')
    now = timezone.now()

    context = {'active_tool': active_tool}

    def get_active_projects(Model, file_fields):
        """Return active successful projects (mine and shared)"""
        my_projects = Model.objects.filter(user=user).select_related('user').filter(
            Q(expires_at__isnull=True) | Q(expires_at__gt=now)
        ).filter(task_status='SUCCESS')

        shared_projects = Model.objects.filter(shared_with=user).select_related('user').filter(
            Q(expires_at__isnull=True) | Q(expires_at__gt=now)
        ).filter(task_status='SUCCESS')

        all_projects = (my_projects | shared_projects).distinct().order_by('-created_at')

        valid_projects = []
        for p in all_projects:
            if has_files(p, file_fields):
                p.is_mine = (p.user == user)
                valid_projects.append(p)

        return valid_projects

    projects = []
    if active_tool == 'hmmbuild':
        projects = get_active_projects(HMMBuildProject, ('msa_file', 'hmm_file'))
        for p in projects:
            p.tool_type = 'hmmbuild'
    elif active_tool == 'hmmsearch':
        projects = get_active_projects(HMMSearchProject, ('fasta_file', 'hmm_file', 'out_file', 'tblout_file', 'domtbl_file'))
        for p in projects:
            p.tool_type = 'hmmsearch'
    elif active_tool == 'hmmemit':
        projects = get_active_projects(HMMEmitProject, ('hmm_file', 'output_file'))
        for p in projects:
            p.tool_type = 'hmmemit'
    else:
        hmmbuild_projects = get_active_projects(HMMBuildProject, ('msa_file', 'hmm_file'))
        hmmsearch_projects = get_active_projects(HMMSearchProject, ('fasta_file', 'hmm_file', 'out_file', 'tblout_file', 'domtbl_file'))
        hmmemit_projects = get_active_projects(HMMEmitProject, ('hmm_file', 'output_file'))

        for p in hmmbuild_projects:
            p.tool_type = 'hmmbuild'
        for p in hmmsearch_projects:
            p.tool_type = 'hmmsearch'
        for p in hmmemit_projects:
            p.tool_type = 'hmmemit'

        projects = hmmbuild_projects + hmmsearch_projects + hmmemit_projects
        projects.sort(key=lambda x: x.created_at, reverse=True)

    paginator = Paginator(projects, 10)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    context['projects'] = page_obj.object_list
    context['page_obj'] = page_obj

    return render(request, 'users/my_projects.html', context)

@login_required
def delete_project(request, pk):
    """
    Delete a specific project (and its associated files) based on active tool.
    """
    if request.method != "POST":
        return redirect("my-projects")

    tool = request.GET.get("tool", "")
    if tool not in MODEL_FIELDS:
        return redirect("my-projects")

    Model, fields = MODEL_FIELDS[tool]
    project = get_object_or_404(Model, pk=pk, user=request.user)

    project_name = project.name
    project_id = project.id

    original_tool_param = request.POST.get("from_tool", "")

    with transaction.atomic():
        from django.contrib.contenttypes.models import ContentType
        content_type = ContentType.objects.get_for_model(project)
        UserActionHistory.objects.filter(
            content_type=content_type,
            object_id=project.id
        ).update(object_id=None)

        log_user_action(
            user=request.user,
            action_type='project_deleted',
            tool_type=tool,
            project=project,
            project_name=project_name,
            description=f'Deleted {tool.upper()} project'
        )
        delete_project_files(project, fields)

    if original_tool_param:
        return redirect(f"{reverse('my-projects')}?tool={original_tool_param}")
    else:
        return redirect("my-projects")


@login_required
def delete_selected_projects(request):
    """
    Bulk delete: delete multiple selected projects at once.
    """
    if request.method != "POST":
        return redirect("my-projects")

    import json

    projects_by_tool_list = request.POST.getlist("projects_by_tool")

    with transaction.atomic():
        for json_str in projects_by_tool_list:
            data = json.loads(json_str)
            tool = data['tool']
            ids = data['ids']

            if tool not in MODEL_FIELDS:
                continue

            Model, fields = MODEL_FIELDS[tool]
            ids = [int(id_val) for id_val in ids]

            for project in Model.objects.filter(id__in=ids, user=request.user):
                delete_project_files(project, fields)

    return redirect("my-projects")


@login_required
def share_project(request, tool, pk):
    """
    Project sharing settings
    """
    if tool not in MODEL_FIELDS:
        return redirect('my-projects')

    Model, _ = MODEL_FIELDS[tool]
    project = get_object_or_404(Model, pk=pk, user=request.user)

    if request.method == 'POST':
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            email = request.POST.get('email')
            action = request.POST.get('action')

            if action == 'add' and email:
                try:
                    user_to_share = User.objects.filter(email=email).exclude(id=request.user.id).first()

                    if not user_to_share:
                        return JsonResponse({'success': False, 'error': 'User not found with this email address'})

                    if project.shared_with.filter(id=user_to_share.id).exists():
                        return JsonResponse({'success': False, 'error': 'Already shared with this user'})

                    project.shared_with.add(user_to_share)

                    log_user_action(
                        user=request.user,
                        action_type='project_shared',
                        tool_type=tool,
                        project=project,
                        project_name=project.name,
                        description=f'Shared project with: {user_to_share.username}',
                        metadata={'shared_with': user_to_share.username}
                    )

                    return JsonResponse({
                        'success': True,
                        'user': {
                            'id': user_to_share.id,
                            'email': user_to_share.email,
                            'username': user_to_share.username
                        }
                    })
                except Exception as e:
                    import traceback
                    traceback.print_exc()
                    return JsonResponse({'success': False, 'error': f'Error: {str(e)}'})

            elif action == 'remove':
                user_id = request.POST.get('user_id')
                try:
                    user_to_remove = User.objects.get(id=user_id)
                    project.shared_with.remove(user_to_remove)

                    log_user_action(
                        user=request.user,
                        action_type='project_unshared',
                        tool_type=tool,
                        project=project,
                        project_name=project.name,
                        description=f'Removed sharing with: {user_to_remove.username}',
                        metadata={'removed_user': user_to_remove.username}
                    )

                    return JsonResponse({'success': True})
                except User.DoesNotExist:
                    return JsonResponse({'success': False, 'error': 'User not found'})

        form = ProjectSharingForm(request.POST)
        if form.is_valid():
            visibility_changed = project.visibility != form.cleaned_data['visibility']

            if visibility_changed:
                old_visibility = project.visibility
                project.visibility = form.cleaned_data['visibility']
                project.save()

                log_user_action(
                    user=request.user,
                    action_type='project_visibility_changed',
                    tool_type=tool,
                    project=project,
                    project_name=project.name,
                    description=f'Changed visibility from {old_visibility} to {project.visibility}',
                    metadata={'old_visibility': old_visibility, 'new_visibility': project.visibility}
                )

            return redirect(f"{reverse('my-projects')}?tool={tool}")
    else:
        form = ProjectSharingForm(
            initial={
                'visibility': project.visibility,
            }
        )

    share_link = request.build_absolute_uri(
        reverse('shared-project', args=[tool, project.share_token])
    )

    context = {
        'project': project,
        'form': form,
        'tool': tool,
        'share_link': share_link,
        'shared_users': project.shared_with.all(),
    }

    return render(request, 'users/share_project.html', context)


def shared_project_view(request, tool, token):
    """
    Public project view via share_token (link or public)
    """
    if tool not in MODEL_FIELDS:
        return redirect('home')

    Model, _ = MODEL_FIELDS[tool]

    try:
        project = Model.objects.select_related('user').get(share_token=token)
    except Model.DoesNotExist:
        messages.error(request, 'Project not found or link is no longer valid.')
        return redirect('home')

    if not project.can_view(request.user):
        return HttpResponseForbidden("You don't have permission to view this project.")

    can_edit = project.can_edit(request.user)

    context = {
        'project': project,
        'tool': tool,
        'can_edit': can_edit,
        'is_owner': (project.user == request.user),
    }

    return render(request, 'users/shared_project_view.html', context)


@login_required
def remove_shared_project(request, tool, pk):
    """
    Remove shared project from user's list (does not delete the project).
    """
    if request.method != "POST":
        return redirect("my-projects")

    if tool not in MODEL_FIELDS:
        return redirect("my-projects")

    Model, _ = MODEL_FIELDS[tool]
    project = get_object_or_404(Model, pk=pk)

    if request.user in project.shared_with.all():
        project.shared_with.remove(request.user)

    return redirect(f"{reverse('my-projects')}?tool={tool}")


def public_projects(request):
    """
    Display all public projects (visibility='public')
    """
    active_tool = request.GET.get('tool')
    now = timezone.now()

    context = {'active_tool': active_tool}

    def get_public_projects(Model, file_fields):
        """Return public active successful projects"""
        all_projects = Model.objects.filter(
            visibility='public'
        ).filter(
            Q(expires_at__isnull=True) | Q(expires_at__gt=now)
        ).filter(task_status='SUCCESS').select_related('user').order_by('-created_at')

        valid_projects = [p for p in all_projects if has_files(p, file_fields)]
        return valid_projects

    projects = []
    if active_tool == 'hmmbuild':
        projects = get_public_projects(HMMBuildProject, ('msa_file', 'hmm_file'))
        for p in projects:
            p.tool_type = 'hmmbuild'
    elif active_tool == 'hmmsearch':
        projects = get_public_projects(HMMSearchProject, ('fasta_file', 'hmm_file', 'out_file', 'tblout_file', 'domtbl_file'))
        for p in projects:
            p.tool_type = 'hmmsearch'
    elif active_tool == 'hmmemit':
        projects = get_public_projects(HMMEmitProject, ('hmm_file', 'output_file'))
        for p in projects:
            p.tool_type = 'hmmemit'
    else:
        hmmbuild_projects = get_public_projects(HMMBuildProject, ('msa_file', 'hmm_file'))
        hmmsearch_projects = get_public_projects(HMMSearchProject, ('fasta_file', 'hmm_file', 'out_file', 'tblout_file', 'domtbl_file'))
        hmmemit_projects = get_public_projects(HMMEmitProject, ('hmm_file', 'output_file'))

        for p in hmmbuild_projects:
            p.tool_type = 'hmmbuild'
        for p in hmmsearch_projects:
            p.tool_type = 'hmmsearch'
        for p in hmmemit_projects:
            p.tool_type = 'hmmemit'

        projects = hmmbuild_projects + hmmsearch_projects + hmmemit_projects
        projects.sort(key=lambda x: x.created_at, reverse=True)

    paginator = Paginator(projects, 10)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    context['projects'] = page_obj.object_list
    context['page_obj'] = page_obj

    return render(request, 'users/public_projects.html', context)


@login_required
def get_user_history(request):
    """
    API endpoint to fetch user's recent action history
    Returns JSON data for the history panel
    """
    limit = int(request.GET.get('limit', 20))

    history_items = UserActionHistory.objects.filter(
        user=request.user
    ).select_related('user', 'content_type')[:limit]

    data = []
    for item in history_items:
        data.append({
            'id': item.id,
            'action_type': item.get_action_type_display(),
            'action_type_code': item.action_type,
            'tool_type': item.tool_type.upper(),
            'project_name': item.project_name,
            'timestamp': item.timestamp.isoformat(),
            'status': item.status,
            'description': item.description,
            'url': item.get_project_url(),
        })

    return JsonResponse({'history': data})


@login_required
def clear_user_history(request):
    """
    API endpoint to clear all user's history
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)

    try:
        deleted_count, _ = UserActionHistory.objects.filter(user=request.user).delete()
        return JsonResponse({'success': True, 'deleted_count': deleted_count})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)
