from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded
import subprocess
import os
import logging
from users.history_utils import log_user_action

logger = logging.getLogger(__name__)

@shared_task(
    bind=True,
    autoretry_for=(subprocess.SubprocessError, OSError),
    retry_kwargs={'max_retries': 3, 'countdown': 5},
    soft_time_limit=300,
    time_limit=360
)
def run_hmmemit(self, project_id, hmm_path, out_path, num_seqs, seed=None):
    """
    Runs HMMER 'hmmemit' command in background.
    """
    from .models import HMMEmitProject

    try:
        self.update_state(state='STARTED', meta={'progress': 50, 'message': 'Generating sequences...'})

        project = HMMEmitProject.objects.get(id=project_id)
        project.task_status = 'STARTED'
        project.save(update_fields=['task_status'])

        command = ["hmmemit", "-N", str(num_seqs), "-o", out_path, hmm_path]
        if seed is not None:
            command.insert(1, "--seed")
            command.insert(2, str(seed))

        logger.info(f"Executing command: {' '.join(command)}")

        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=280,
            cwd=os.path.dirname(out_path)
        )

        if result.returncode == 0:
            with open(out_path, 'r', encoding='utf-8', errors='replace') as f:
                output_text = f.read()

            project.result_text = output_text
            project.task_status = 'SUCCESS'
            project.save(update_fields=['result_text', 'task_status'])

            log_user_action(
                user=project.user,
                action_type='project_completed',
                tool_type='hmmemit',
                project=project,
                project_name=project.name,
                description=f'HMMEMIT project completed successfully - generated {num_seqs} sequences'
            )

            self.update_state(state='SUCCESS', meta={'progress': 100, 'message': 'Sequences generated successfully'})

            return {
                'status': 'success',
                'stdout': result.stdout,
                'stderr': result.stderr,
                'output_text': output_text
            }
        else:
            error_msg = result.stderr or "Unknown error"
            logger.error(f"hmmemit error: {error_msg}")

            project.task_status = 'FAILURE'
            project.save(update_fields=['task_status'])

            log_user_action(
                user=project.user,
                action_type='project_failed',
                tool_type='hmmemit',
                project=project,
                project_name=project.name,
                description='HMMEMIT project failed',
                status='failure',
                error_message=error_msg
            )

            raise Exception(f"HMMEMIT error: {error_msg}")

    except SoftTimeLimitExceeded:
        logger.warning(f"hmmemit task {self.request.id} exceeded time limit")
        project = HMMEmitProject.objects.get(id=project_id)
        project.task_status = 'FAILURE'
        project.save(update_fields=['task_status'])
        raise

    except Exception as e:
        logger.error(f"hmmemit task error: {str(e)}")
        try:
            project = HMMEmitProject.objects.get(id=project_id)
            project.task_status = 'FAILURE'
            project.save(update_fields=['task_status'])
        except:
            pass
        raise
