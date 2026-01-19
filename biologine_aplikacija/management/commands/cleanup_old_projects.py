import os
import logging
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.conf import settings
from hmmbuild.models import HMMBuildProject
from hmmsearch.models import HMMSearchProject
from hmmemit.models import HMMEmitProject

logger = logging.getLogger(__name__)

MODEL_CLASSES = [
    (HMMBuildProject, 'HMMBuild'),
    (HMMSearchProject, 'HMMSearch'),
    (HMMEmitProject, 'HMMEmit')
]


class Command(BaseCommand):
    help = 'Cleans up old temporary projects and their files'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Shows what would be deleted without actually deleting',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        now = timezone.now()

        total_deleted = 0
        total_files_deleted = 0
        total_space_freed = 0
        total_orphaned = 0
        total_failed = 0

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - nothing will be deleted'))

        for model_class, model_name in MODEL_CLASSES:
            deleted, files_deleted, space_freed = self._cleanup_model(
                model_class, model_name, now, dry_run
            )
            total_deleted += deleted
            total_files_deleted += files_deleted
            total_space_freed += space_freed

        one_hour_ago = now - timedelta(hours=1)

        for model_class, model_name in MODEL_CLASSES:
            failed = self._cleanup_failed_projects(
                model_class, model_name, one_hour_ago, dry_run
            )
            total_failed += failed

        for model_class, model_name in MODEL_CLASSES:
            orphaned = self._cleanup_orphaned_projects(
                model_class, model_name, dry_run
            )
            total_orphaned += orphaned

        self.stdout.write(self.style.SUCCESS(f'\n=== CLEANUP RESULTS ==='))
        self.stdout.write(f'Expired projects deleted: {total_deleted}')
        self.stdout.write(f'Failed projects deleted: {total_failed}')
        self.stdout.write(f'Projects without files deleted: {total_orphaned}')
        self.stdout.write(f'Files deleted: {total_files_deleted}')
        self.stdout.write(f'Space freed: {self._format_bytes(total_space_freed)}')

        if dry_run:
            self.stdout.write(self.style.WARNING('\nThis was a DRY RUN - nothing was deleted!'))

    def _cleanup_model(self, model_class, model_name, now, dry_run):
        """Cleans up projects for a specific model"""

        expired_projects = model_class.objects.filter(
            is_temporary=True,
            expires_at__lt=now
        )

        count = expired_projects.count()

        if count == 0:
            self.stdout.write(f'{model_name}: No expired projects found')
            return 0, 0, 0

        self.stdout.write(f'\n{model_name}: Found {count} expired projects')

        files_deleted = 0
        space_freed = 0

        for project in expired_projects:
            file_fields = []

            if model_name == 'HMMBuild':
                file_fields = ['msa_file', 'hmm_file']
            elif model_name == 'HMMSearch':
                file_fields = ['fasta_file', 'hmm_file', 'out_file', 'tblout_file', 'domtbl_file']
            elif model_name == 'HMMEmit':
                file_fields = ['hmm_file', 'output_file']

            for field_name in file_fields:
                file_field = getattr(project, field_name, None)
                if file_field:
                    try:
                        file_path = file_field.path
                        if os.path.exists(file_path):
                            file_size = os.path.getsize(file_path)

                            if not dry_run:
                                os.remove(file_path)
                                self.stdout.write(f'  Deleted: {file_path}')
                            else:
                                self.stdout.write(f'  [DRY RUN] Would delete: {file_path}')

                            files_deleted += 1
                            space_freed += file_size
                    except Exception as e:
                        logger.error(f'Error deleting file {field_name}: {e}')
                        self.stdout.write(self.style.ERROR(f'  ✗ Error: {e}'))

        if not dry_run:
            expired_projects.delete()
            self.stdout.write(self.style.SUCCESS(f'{model_name}: Deleted {count} projects'))
        else:
            self.stdout.write(self.style.WARNING(f'{model_name}: [DRY RUN] Would delete {count} projects'))

        return count, files_deleted, space_freed

    def _cleanup_failed_projects(self, model_class, model_name, cutoff_time, dry_run):
        """Deletes failed projects (FAILURE/PENDING) older than 1 hour"""

        failed_projects = model_class.objects.filter(
            task_status__in=['FAILURE', 'PENDING'],
            created_at__lt=cutoff_time
        )

        count = failed_projects.count()

        if count == 0:
            return 0

        self.stdout.write(f'\n{model_name}: Found {count} failed/stuck projects')

        if model_name == 'HMMBuild':
            file_fields = ['msa_file', 'hmm_file']
        elif model_name == 'HMMSearch':
            file_fields = ['fasta_file', 'hmm_file', 'out_file', 'tblout_file', 'domtbl_file']
        elif model_name == 'HMMEmit':
            file_fields = ['hmm_file', 'output_file']
        else:
            return 0

        for project in failed_projects:
            for field_name in file_fields:
                file_field = getattr(project, field_name, None)
                if file_field:
                    try:
                        file_path = file_field.path
                        if os.path.exists(file_path):
                            if not dry_run:
                                os.remove(file_path)
                                self.stdout.write(f'  Deleted: {file_path}')
                            else:
                                self.stdout.write(f'  [DRY RUN] Would delete: {file_path}')
                    except Exception as e:
                        logger.error(f'Error deleting file {field_name}: {e}')

            if not dry_run:
                self.stdout.write(f'  Deleted project: {project.name} (Status: {project.task_status})')
                project.delete()

        if not dry_run:
            self.stdout.write(self.style.SUCCESS(f'{model_name}: Deleted {count} failed projects'))
        else:
            self.stdout.write(self.style.WARNING(f'{model_name}: [DRY RUN] Would delete {count} projects'))

        return count

    def _cleanup_orphaned_projects(self, model_class, model_name, dry_run):
        """Deletes projects whose files don't exist"""

        if model_name == 'HMMBuild':
            file_fields = ['msa_file', 'hmm_file']
        elif model_name == 'HMMSearch':
            file_fields = ['fasta_file', 'hmm_file', 'out_file', 'tblout_file', 'domtbl_file']
        elif model_name == 'HMMEmit':
            file_fields = ['hmm_file', 'output_file']
        else:
            return 0

        all_projects = model_class.objects.all()
        orphaned_projects = []

        for project in all_projects:
            has_any_file = False

            for field_name in file_fields:
                file_field = getattr(project, field_name, None)
                if file_field and file_field.name:
                    try:
                        if os.path.exists(file_field.path):
                            has_any_file = True
                            break
                    except:
                        pass

            if not has_any_file:
                orphaned_projects.append(project)

        count = len(orphaned_projects)

        if count == 0:
            return 0

        self.stdout.write(f'\n{model_name}: Found {count} projects without files')

        if not dry_run:
            for project in orphaned_projects:
                project.delete()
                self.stdout.write(f'  Deleted DB record: {project.name} (ID={project.id})')
            self.stdout.write(self.style.SUCCESS(f'{model_name}: Deleted {count} orphaned projects'))
        else:
            for project in orphaned_projects:
                self.stdout.write(f'  [DRY RUN] Would delete: {project.name} (ID={project.id})')

        return count

    def _format_bytes(self, bytes_size):
        """Formats byte count into readable format"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if bytes_size < 1024.0:
                return f"{bytes_size:.2f} {unit}"
            bytes_size /= 1024.0
        return f"{bytes_size:.2f} TB"
