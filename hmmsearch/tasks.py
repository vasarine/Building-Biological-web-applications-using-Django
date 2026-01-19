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
    soft_time_limit=600,
    time_limit=720
)
def run_hmmsearch(self, project_id, hmm_path, fasta_path, out_path, tblout_path, domtbl_path):
    """
    Runs HMMER 'hmmsearch' command in background.
    """
    from .models import HMMSearchProject

    try:
        self.update_state(state='STARTED', meta={'progress': 50, 'message': 'Running HMM search...'})

        project = HMMSearchProject.objects.get(id=project_id)
        project.task_status = 'STARTED'
        project.save(update_fields=['task_status'])

        command = [
            "hmmsearch",
            "-o", out_path,
            "--domtblout", domtbl_path,
            "--tblout", tblout_path,
            hmm_path, fasta_path
        ]
        logger.info(f"Executing command: {' '.join(command)}")

        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=580,
            cwd=os.path.dirname(fasta_path)
        )

        if result.returncode == 0:
            with open(out_path, 'r') as f:
                result_text = f.read()
            with open(tblout_path, 'r') as f:
                tblout_text = f.read()
            with open(domtbl_path, 'r') as f:
                domtbl_text = f.read()

            project.result_text = result_text
            project.tblout_text = tblout_text
            project.domtbl_text = domtbl_text
            project.task_status = 'SUCCESS'
            project.save(update_fields=['result_text', 'tblout_text', 'domtbl_text', 'task_status'])

            log_user_action(
                user=project.user,
                action_type='project_completed',
                tool_type='hmmsearch',
                project=project,
                project_name=project.name,
                description='HMMSEARCH project completed successfully'
            )

            self.update_state(state='SUCCESS', meta={'progress': 100, 'message': 'Search completed successfully'})

            return {
                'status': 'success',
                'stdout': result.stdout,
                'stderr': result.stderr
            }
        else:
            error_msg = result.stderr or "Unknown error"
            logger.error(f"hmmsearch error: {error_msg}")

            project.task_status = 'FAILURE'
            project.save(update_fields=['task_status'])

            log_user_action(
                user=project.user,
                action_type='project_failed',
                tool_type='hmmsearch',
                project=project,
                project_name=project.name,
                description='HMMSEARCH project failed',
                status='failure',
                error_message=error_msg
            )

            raise Exception(f"HMMSEARCH error: {error_msg}")

    except SoftTimeLimitExceeded:
        logger.warning(f"hmmsearch task {self.request.id} exceeded time limit")
        project = HMMSearchProject.objects.get(id=project_id)
        project.task_status = 'FAILURE'
        project.save(update_fields=['task_status'])
        raise

    except Exception as e:
        logger.error(f"hmmsearch task error: {str(e)}")
        try:
            project = HMMSearchProject.objects.get(id=project_id)
            project.task_status = 'FAILURE'
            project.save(update_fields=['task_status'])
        except:
            pass
        raise
