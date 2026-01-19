import os
import uuid
import logging
from django.shortcuts import render, redirect
from django.conf import settings
from django.http import FileResponse, Http404, JsonResponse
from .models import HMMSearchProject
from .forms import HMMSearchForm
from .tasks import run_hmmsearch
from celery.result import AsyncResult
from hmm_library.services import HMMCacheManager
from users.history_utils import log_user_action

logger = logging.getLogger(__name__)

def hmmsearch_form(request):
    """
    Runs hmmsearch from uploaded HMM + FASTA and displays results.
    """
    context = {}

    if request.method == "POST":
        form = HMMSearchForm(request.POST, request.FILES)
        form.fields["name"].required = request.user.is_authenticated

        if not form.is_valid():
            return render(request, "hmmsearch_form.html", {"form": form})

        fasta_file = form.cleaned_data["fasta_file"]
        hmm_source = form.cleaned_data["hmm_source"]
        user_input_name = form.cleaned_data.get("name") or "Untitled project"

        unique_id = uuid.uuid4().hex[:8]
        prefix = f"hmmsearch_{unique_id}"

        search_dir = os.path.join(settings.MEDIA_ROOT, "hmmsearch")
        os.makedirs(search_dir, exist_ok=True)

        fasta_ext       = os.path.splitext(fasta_file.name)[1].lower() or ".fa"
        fasta_filename  = f"{prefix}{fasta_ext}"
        out_filename    = f"{prefix}.out"
        tblout_filename = f"{prefix}.tblout"
        domtbl_filename = f"{prefix}.domtbl"

        fasta_path  = os.path.join(search_dir, fasta_filename)
        out_path    = os.path.join(search_dir, out_filename)
        tblout_path = os.path.join(search_dir, tblout_filename)
        domtbl_path = os.path.join(search_dir, domtbl_filename)

        try:
            with open(fasta_path, "wb+") as d:
                for ch in fasta_file.chunks():
                    d.write(ch)
        except OSError as e:
            form.add_error(None, f"Failed to save FASTA file: {e}")
            return render(request, "hmmsearch_form.html", {"form": form})

        external_hmm_id = None
        external_hmm_name = None

        if hmm_source == 'upload':
            hmm_file = form.cleaned_data["hmm_file"]
            hmm_filename = f"{prefix}.hmm"
            hmm_path = os.path.join(search_dir, hmm_filename)

            try:
                with open(hmm_path, "wb+") as d:
                    for ch in hmm_file.chunks():
                        d.write(ch)
            except OSError as e:
                form.add_error(None, f"Failed to save HMM file: {e}")
                return render(request, "hmmsearch_form.html", {"form": form})

        elif hmm_source == 'library':
            external_hmm_id = form.cleaned_data["external_hmm_id"].upper().strip()

            import re
            if re.match(r'^PF\d{5}$', external_hmm_id):
                detected_source = 'pfam'
            elif re.match(r'^IPR\d{6}$', external_hmm_id):
                detected_source = 'interpro'
            else:
                form.add_error('external_hmm_id', 'Unrecognized ID format.')
                return render(request, "hmmsearch_form.html", {"form": form})

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
                    return render(request, "hmmsearch_form.html", {"form": form})

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
                return render(request, "hmmsearch_form.html", {"form": form})

            hmm_filename = f"{external_hmm_id}.hmm"

        project = HMMSearchProject.objects.create(
            user=request.user if request.user.is_authenticated else None,
            name=user_input_name,
            fasta_file=f"hmmsearch/{fasta_filename}",
            hmm_file=f"hmmsearch/{hmm_filename}" if hmm_source == 'upload' else None,
            hmm_source=hmm_source,
            external_hmm_id=external_hmm_id,
            external_hmm_name=external_hmm_name,
            out_file=f"hmmsearch/{out_filename}",
            tblout_file=f"hmmsearch/{tblout_filename}",
            domtbl_file=f"hmmsearch/{domtbl_filename}",
            task_status='PENDING'
        )

        task = run_hmmsearch.delay(project.id, hmm_path, fasta_path, out_path, tblout_path, domtbl_path)
        project.task_id = task.id
        project.save(update_fields=['task_id'])

        description = f'Created HMMSEARCH project with FASTA file: {fasta_file.name}'
        if hmm_source == 'upload':
            description += f' and uploaded HMM file'
        else:
            description += f' using {hmm_source.upper()} library: {external_hmm_id}'

        log_user_action(
            user=request.user if request.user.is_authenticated else None,
            action_type='project_created',
            tool_type='hmmsearch',
            project=project,
            project_name=user_input_name,
            description=description,
            metadata={
                'hmm_source': hmm_source,
                'external_hmm_id': external_hmm_id,
                'fasta_filename': fasta_file.name
            }
        )

        return redirect('hmmsearch_status', project_id=project.id)

    form = HMMSearchForm()
    form.fields["name"].required = request.user.is_authenticated
    return render(request, "hmmsearch_form.html", {"form": form})


def hmmsearch_status(request, project_id):
    """
    Shows task status and progress.
    """
    try:
        project = HMMSearchProject.objects.get(id=project_id)
        if request.user.is_authenticated and project.user and project.user != request.user:
            raise Http404("Project not found")
    except HMMSearchProject.DoesNotExist:
        raise Http404("Project not found")

    context = {
        'project': project,
        'form': HMMSearchForm()
    }

    if project.task_status == 'SUCCESS' and project.result_text:
        out_filename = os.path.basename(project.out_file.name) if project.out_file else None
        tblout_filename = os.path.basename(project.tblout_file.name) if project.tblout_file else None
        domtbl_filename = os.path.basename(project.domtbl_file.name) if project.domtbl_file else None
        context.update({
            'result_text': project.result_text,
            'tblout_text': project.tblout_text,
            'domtbl_text': project.domtbl_text,
            'out_filename': out_filename,
            'tblout_filename': tblout_filename,
            'domtbl_filename': domtbl_filename,
        })

    return render(request, 'hmmsearch_status.html', context)


def hmmsearch_task_status(request, task_id):
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
        response_data['message'] = task.info.get('message', 'Running HMM search...')
        response_data['progress'] = task.info.get('progress', 50)
    elif task.state == 'SUCCESS':
        response_data['message'] = 'Search completed successfully'
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


def download_search_file(request, file_name):
    """
    Provides MEDIA/hmmsearch directory file for download.
    """
    file_path = os.path.join(settings.MEDIA_ROOT, "hmmsearch", file_name)
    if os.path.exists(file_path):
        return FileResponse(open(file_path, "rb"), as_attachment=True)
    raise Http404("File not found")
