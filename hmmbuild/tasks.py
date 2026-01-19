from celery import shared_task, states
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
def run_hmmbuild(self, project_id, input_fasta_path, output_hmm_path):
    """
    Runs HMMER 'hmmbuild' command in background.
    """
    from .models import HMMBuildProject

    try:
        self.update_state(state='STARTED', meta={'progress': 50, 'message': 'Building HMM profile...'})

        project = HMMBuildProject.objects.get(id=project_id)
        project.task_status = 'STARTED'
        project.save(update_fields=['task_status'])

        command = ["hmmbuild", output_hmm_path, input_fasta_path]
        logger.info(f"Executing command: {' '.join(command)}")

        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=280,
            cwd=os.path.dirname(input_fasta_path)
        )

        if result.returncode == 0:
            with open(output_hmm_path, 'r') as f:
                hmm_content = f.read()

            project.result_text = hmm_content
            project.task_status = 'SUCCESS'
            project.save(update_fields=['result_text', 'task_status'])

            log_user_action(
                user=project.user,
                action_type='project_completed',
                tool_type='hmmbuild',
                project=project,
                project_name=project.name,
                description='HMMBUILD project completed successfully'
            )

            self.update_state(state='SUCCESS', meta={'progress': 100, 'message': 'HMM build completed successfully'})

            return {
                'status': 'success',
                'stdout': result.stdout,
                'stderr': result.stderr,
                'hmm_content': hmm_content
            }
        else:
            error_msg = result.stderr or "Unknown error"
            logger.error(f"hmmbuild error: {error_msg}")

            project.task_status = 'FAILURE'
            project.save(update_fields=['task_status'])

            log_user_action(
                user=project.user,
                action_type='project_failed',
                tool_type='hmmbuild',
                project=project,
                project_name=project.name,
                description='HMMBUILD project failed',
                status='failure',
                error_message=error_msg
            )

            raise Exception(f"HMMBUILD error: {error_msg}")

    except SoftTimeLimitExceeded:
        logger.warning(f"hmmbuild task {self.request.id} exceeded time limit")
        project = HMMBuildProject.objects.get(id=project_id)
        project.task_status = 'FAILURE'
        project.save(update_fields=['task_status'])
        raise

    except Exception as e:
        logger.error(f"hmmbuild task error: {str(e)}")
        try:
            project = HMMBuildProject.objects.get(id=project_id)
            project.task_status = 'FAILURE'
            project.save(update_fields=['task_status'])
        except:
            pass
        raise
