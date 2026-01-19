from django.shortcuts import render, redirect
from django.conf import settings
from django.http import FileResponse, Http404, JsonResponse
from .models import HMMEmitProject
from .forms import HMMEmitForm
from .tasks import run_hmmemit
from celery.result import AsyncResult
from hmm_library.services import HMMCacheManager
from users.history_utils import log_user_action
import os
import uuid
import logging

logger = logging.getLogger(__name__)

def hmmemit_form(request):
    """
    Generates sequences from uploaded HMM file using hmmemit and displays result.
    """
    context = {}

    if request.method == "POST":
        form = HMMEmitForm(request.POST, request.FILES)
        form.fields["name"].required = request.user.is_authenticated

        if not form.is_valid():
            return render(request, "hmmemit_form.html", {"form": form})

        hmm_source = form.cleaned_data["hmm_source"]
        user_input_name = form.cleaned_data.get("name") or "Untitled project"
        num_seqs = form.cleaned_data["num_seqs"]
        seed = form.cleaned_data.get("seed")

        unique_id = uuid.uuid4().hex[:8]
        file_prefix = f"hmmemit_{unique_id}"

        emit_dir = os.path.join(settings.MEDIA_ROOT, "hmmemit")
        os.makedirs(emit_dir, exist_ok=True)

        out_filename = f"{file_prefix}.fa"
        out_path = os.path.join(emit_dir, out_filename)

        external_hmm_id = None
        external_hmm_name = None

        if hmm_source == 'upload':
            hmm_file = form.cleaned_data["hmm_file"]
            hmm_filename = f"{file_prefix}.hmm"
            hmm_path = os.path.join(emit_dir, hmm_filename)

            try:
                with open(hmm_path, "wb+") as dest:
                    for chunk in hmm_file.chunks():
                        dest.write(chunk)
            except OSError as e:
                form.add_error(None, f"Failed to save uploaded file: {e}")
                return render(request, "hmmemit_form.html", {"form": form})

        elif hmm_source == 'library':
            external_hmm_id = form.cleaned_data["external_hmm_id"].upper().strip()

            import re
            if re.match(r'^PF\d{5}$', external_hmm_id):
                detected_source = 'pfam'
            elif re.match(r'^IPR\d{6}$', external_hmm_id):
                detected_source = 'interpro'
            else:
                form.add_error('external_hmm_id', 'Unrecognized ID format.')
                return render(request, "hmmemit_form.html", {"form": form})

            try:
                logger.info(f"Attempting to get HMM from {detected_source}: {external_hmm_id}")

                hmm_path = HMMCacheManager.get_or_download(detected_source, external_hmm_id)

                logger.info(f"HMM path result: {hmm_path}")

                if not hmm_path:
                    error_msg = f'Could not download HMM for {external_hmm_id}. '
                    if detected_source == 'interpro':
                        error_msg += 'This InterPro entry may not have an associated Pfam HMM model. Try using a Pfam ID (PF00001) instead, or search for entries that have HMM models.'
                    else:
                        error_msg += 'Please check the ID format or try again later.'

                    form.add_error('external_hmm_id', error_msg)
                    return render(request, "hmmemit_form.html", {"form": form})

                from hmm_library.models import ExternalHMMModel
                ext_model = ExternalHMMModel.objects.filter(
                    source=detected_source,
                    external_id=external_hmm_id
                ).first()
                if ext_model:
                    external_hmm_name = ext_model.name
                    logger.info(f"Found HMM name: {external_hmm_name}")

                hmm_source = detected_source

            except Exception as e:
                import traceback
                logger.error(f"Error getting HMM: {str(e)}")
                logger.error(traceback.format_exc())
                form.add_error('external_hmm_id',
                               f'Error: {str(e)}. Please check your internet connection and try again later.')
                return render(request, "hmmemit_form.html", {"form": form})

            hmm_filename = f"{external_hmm_id}.hmm"

        project = HMMEmitProject.objects.create(
            user=request.user if request.user.is_authenticated else None,
            name=user_input_name,
            hmm_file=f"hmmemit/{hmm_filename}" if hmm_source == 'upload' else None,
            hmm_source=hmm_source,
            external_hmm_id=external_hmm_id,
            external_hmm_name=external_hmm_name,
            output_file=f"hmmemit/{out_filename}",
            task_status='PENDING'
        )

        task = run_hmmemit.delay(project.id, hmm_path, out_path, num_seqs, seed)
        project.task_id = task.id
        project.save(update_fields=['task_id'])

        description = f'Created HMMEMIT project'
        if hmm_source == 'upload':
            description += f' with uploaded HMM file'
        else:
            description += f' using {hmm_source.upper()} library: {external_hmm_id}'

        log_user_action(
            user=request.user if request.user.is_authenticated else None,
            action_type='project_created',
            tool_type='hmmemit',
            project=project,
            project_name=user_input_name,
            description=description,
            metadata={
                'hmm_source': hmm_source,
                'external_hmm_id': external_hmm_id,
                'num_seqs': num_seqs
            }
        )

        return redirect('hmmemit_status', project_id=project.id)

    form = HMMEmitForm()
    form.fields["name"].required = request.user.is_authenticated
    return render(request, "hmmemit_form.html", {"form": form})


def hmmemit_status(request, project_id):
    """
    Shows task status and progress.
    """
    try:
        project = HMMEmitProject.objects.get(id=project_id)
        if request.user.is_authenticated and project.user and project.user != request.user:
            raise Http404("Project not found")
    except HMMEmitProject.DoesNotExist:
        raise Http404("Project not found")

    context = {
        'project': project,
        'form': HMMEmitForm()
    }

    if project.task_status == 'SUCCESS' and project.result_text:
        output_filename = os.path.basename(project.output_file.name) if project.output_file else None
        context.update({
            'output_text': project.result_text,
            'output_filename': output_filename,
        })

    return render(request, 'hmmemit_status.html', context)


def hmmemit_task_status(request, task_id):
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
        response_data['message'] = task.info.get('message', 'Generating sequences...')
        response_data['progress'] = task.info.get('progress', 50)
    elif task.state == 'SUCCESS':
        response_data['message'] = 'Sequences generated successfully'
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


def download_emit(request, file_name):
    """
    Provides MEDIA/hmmemit directory file for download.
    """
    file_path = os.path.join(settings.MEDIA_ROOT, "hmmemit", file_name)
    if os.path.exists(file_path):
        return FileResponse(open(file_path, "rb"), as_attachment=True)
    raise Http404("File not found")
