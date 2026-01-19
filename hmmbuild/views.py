from .forms import HMMBuildForm
from django.http import FileResponse, Http404, JsonResponse
from .models import HMMBuildProject
import os
from django.conf import settings
from django.shortcuts import render, redirect
import uuid
from .tasks import run_hmmbuild
from celery.result import AsyncResult
from users.history_utils import log_user_action

def hmmbuild_form(request):
    """
    Creates HMM from uploaded MSA file and displays result.
    """
    context = {}

    if request.method == "POST":
        form = HMMBuildForm(request.POST, request.FILES)
        form.fields["name"].required = request.user.is_authenticated

        if not form.is_valid():
            return render(request, "hmmbuild_form.html", {"form": form})

        msa_file = form.cleaned_data["msa_file"]
        user_input_name = form.cleaned_data.get("name") or "Untitled project"

        # Unique file prefix
        unique_id = uuid.uuid4().hex[:8]
        file_prefix = f"hmmbuild_{unique_id}"

        hmmbuild_dir = os.path.join(settings.MEDIA_ROOT, "hmmbuild")
        os.makedirs(hmmbuild_dir, exist_ok=True)

        # File paths
        original_ext = os.path.splitext(msa_file.name)[1].lower() or ".sto"
        msa_filename = f"{file_prefix}{original_ext}"
        hmm_filename = f"{file_prefix}.hmm"

        msa_path = os.path.join(hmmbuild_dir, msa_filename)
        hmm_path = os.path.join(hmmbuild_dir, hmm_filename)

        # Write uploaded file
        try:
            with open(msa_path, "wb+") as dest:
                for chunk in msa_file.chunks():
                    dest.write(chunk)
        except OSError as e:
            form.add_error(None, f"Failed to save uploaded file: {e}")
            return render(request, "hmmbuild_form.html", {"form": form})

        # Create project in DB
        project = HMMBuildProject.objects.create(
            user=request.user if request.user.is_authenticated else None,
            name=user_input_name,
            msa_file=f"hmmbuild/{msa_filename}",
            hmm_file=f"hmmbuild/{hmm_filename}",
            task_status='PENDING'
        )

        # Start Celery task
        task = run_hmmbuild.delay(project.id, msa_path, hmm_path)
        project.task_id = task.id
        project.save(update_fields=['task_id'])

        # Log project creation
        log_user_action(
            user=request.user if request.user.is_authenticated else None,
            action_type='project_created',
            tool_type='hmmbuild',
            project=project,
            project_name=user_input_name,
            description=f'Created HMMBUILD project with MSA file: {msa_file.name}',
            metadata={'msa_filename': msa_file.name}
        )

        return redirect('hmmbuild_status', project_id=project.id)

    form = HMMBuildForm()
    return render(request, "hmmbuild_form.html", {"form": form})


def hmmbuild_status(request, project_id):
    """
    Shows task status and progress.
    """
    try:
        project = HMMBuildProject.objects.get(id=project_id)
        # Check if user has permission to view project
        if request.user.is_authenticated and project.user and project.user != request.user:
            raise Http404("Project not found")
    except HMMBuildProject.DoesNotExist:
        raise Http404("Project not found")

    context = {
        'project': project,
        'form': HMMBuildForm()
    }

    # Add results if task is successful
    if project.task_status == 'SUCCESS' and project.result_text:
        hmm_filename = os.path.basename(project.hmm_file.name) if project.hmm_file else None
        context.update({
            'hmm_model_text': project.result_text,
            'hmm_model_name': hmm_filename,
        })

    return render(request, 'hmmbuild_status.html', context)


def hmmbuild_task_status(request, task_id):
    """
    API endpoint for status checking (AJAX).
    """
    task = AsyncResult(task_id)

    response_data = {
        'task_id': task_id,
        'status': task.state,
        'result': None
    }

    if task.state == 'PENDING':
        response_data['message'] = 'Task queued...'
        response_data['progress'] = 0
    elif task.state == 'STARTED':
        response_data['message'] = task.info.get('message', 'Building HMM profile...')
        response_data['progress'] = task.info.get('progress', 50)
    elif task.state == 'SUCCESS':
        response_data['message'] = 'HMM build completed successfully'
        response_data['progress'] = 100
        response_data['result'] = task.result
    elif task.state == 'FAILURE':
        response_data['message'] = 'Task failed'
        response_data['progress'] = 100
        response_data['error'] = str(task.info)
    else:
        response_data['message'] = str(task.state)
        response_data['progress'] = 50

    return JsonResponse(response_data)


def download_model(request, file_name):
    """
    Provides MEDIA/hmmbuild directory .hmm file for download.
    """
    file_path = os.path.join(settings.MEDIA_ROOT, 'hmmbuild', file_name)
    if os.path.exists(file_path):
        return FileResponse(open(file_path, 'rb'), as_attachment=True)
    raise Http404("File not found")
