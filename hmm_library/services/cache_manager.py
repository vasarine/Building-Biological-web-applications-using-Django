import os
import hashlib
from datetime import timedelta
from typing import Optional, Tuple
from django.core.files.base import ContentFile
from django.utils import timezone
from django.conf import settings
from django.core.cache import cache
import logging

from ..models import ExternalHMMModel, HMMDownloadLog
from .pfam_client import PfamAPIClient
from .interpro_client import InterProAPIClient

logger = logging.getLogger(__name__)


class HMMCacheManager:
    """
    Cache system for HMM models.

    Functionality:
    - Check local cache
    - Download from API if needed
    - Validate and update cache
    - Auto-cleanup of expired models
    """

    DEFAULT_TTL_DAYS = 90

    @classmethod
    def get_or_download(cls, source: str, external_id: str) -> Optional[str]:
        """
        Main function - get HMM file (from cache or download).

        Args:
            source: 'pfam' or 'interpro'
            external_id: Pfam/InterPro ID (e.g. PF00001, IPR000001)

        Returns:
            Full path to HMM file
            None if failed to get
        """
        if not cls._validate_id(source, external_id):
            logger.error(f"Invalid {source} ID: {external_id}")
            return None

        cached_model = cls._get_from_cache(source, external_id)

        if cached_model:
            logger.info(f"Cache HIT for {source}:{external_id}")
            return cached_model.hmm_file.path

        logger.info(f"Cache MISS for {source}:{external_id} - downloading...")
        downloaded_model = cls._download_and_cache(source, external_id)

        if downloaded_model:
            return downloaded_model.hmm_file.path

        return None

    @classmethod
    def _validate_id(cls, source: str, external_id: str) -> bool:
        """Validate ID format based on source"""
        if source == 'pfam':
            return PfamAPIClient.validate_pfam_id(external_id)
        elif source == 'interpro':
            return InterProAPIClient.validate_interpro_id(external_id)
        else:
            logger.error(f"Unknown source: {source}")
            return False

    @classmethod
    def _get_from_cache(cls, source: str, external_id: str) -> Optional[ExternalHMMModel]:
        """
        Search cache and check if not expired.

        Returns:
            ExternalHMMModel if found and valid
            None if not found or expired
        """
        try:
            model = ExternalHMMModel.objects.get(
                source=source,
                external_id=external_id.upper()
            )

            if model.is_expired(days=cls.DEFAULT_TTL_DAYS):
                logger.info(f"Cached model {source}:{external_id} expired - will re-download")
                model.delete()
                return None

            if not os.path.exists(model.hmm_file.path):
                logger.warning(f"Cached file missing for {source}:{external_id} - will re-download")
                model.delete()
                return None

            return model

        except ExternalHMMModel.DoesNotExist:
            return None

    @classmethod
    def _download_and_cache(cls, source: str, external_id: str) -> Optional[ExternalHMMModel]:
        """
        Download HMM from API and save to cache.

        Returns:
            ExternalHMMModel if successful
            None if failed
        """
        log = HMMDownloadLog.objects.create(
            source=source,
            external_id=external_id.upper(),
            status='downloading'
        )

        try:
            hmm_content, metadata = cls._fetch_from_api(source, external_id)

            if not hmm_content:
                log.status = 'failed'
                log.error_message = "Failed to download HMM content from API"
                log.completed_at = timezone.now()
                log.save()
                return None

            model = cls._save_to_cache(
                source=source,
                external_id=external_id.upper(),
                hmm_content=hmm_content,
                metadata=metadata
            )

            log.status = 'success'
            log.completed_at = timezone.now()
            log.hmm_model = model
            log.save()

            logger.info(f"Successfully cached {source}:{external_id}")
            return model

        except Exception as e:
            logger.error(f"Failed to download and cache {source}:{external_id}: {e}")
            log.status = 'failed'
            log.error_message = str(e)
            log.completed_at = timezone.now()
            log.save()
            return None

    @classmethod
    def _fetch_from_api(cls, source: str, external_id: str) -> Tuple[Optional[bytes], dict]:
        """
        Download HMM and metadata from API.

        Returns:
            (hmm_content_bytes, metadata_dict)
        """
        if source == 'pfam':
            hmm_content = PfamAPIClient.download_hmm(external_id)
            metadata = PfamAPIClient.get_entry_metadata(external_id) or {}

        elif source == 'interpro':
            hmm_content = InterProAPIClient.download_hmm(external_id)
            metadata = InterProAPIClient.get_entry_metadata(external_id) or {}

        else:
            return None, {}

        return hmm_content, metadata

    @classmethod
    def _save_to_cache(cls, source: str, external_id: str, hmm_content: bytes, metadata: dict) -> ExternalHMMModel:
        """
        Save HMM file and metadata to cache.
        """
        filename = f"{external_id.upper()}.hmm"
        file_content = ContentFile(hmm_content)

        checksum = hashlib.sha256(hmm_content).hexdigest()

        has_pfam_model = True
        pfam_members = []
        if source == 'interpro':
            pfam_members = InterProAPIClient.get_pfam_members(external_id)
            has_pfam_model = len(pfam_members) > 0

        model = ExternalHMMModel.objects.create(
            source=source,
            external_id=external_id.upper(),
            name=metadata.get('name', ''),
            description=metadata.get('description', ''),
            version=metadata.get('version', ''),
            file_size=len(hmm_content),
            checksum=checksum,
            expires_at=timezone.now() + timedelta(days=cls.DEFAULT_TTL_DAYS),
            api_url=metadata.get('download_url', ''),
            has_pfam_model=has_pfam_model,
            pfam_members=pfam_members,
        )

        model.hmm_file.save(filename, file_content, save=True)

        return model

    @classmethod
    def cleanup_expired(cls) -> int:
        """
        Delete expired cache entries.

        Returns:
            Number of deleted entries
        """
        expired_models = ExternalHMMModel.objects.filter(
            expires_at__lt=timezone.now()
        )

        count = expired_models.count()

        expired_models.delete()

        logger.info(f"Cleaned up {count} expired HMM cache entries")
        return count

    @classmethod
    def cleanup_old(cls, days: int = 180) -> int:
        """
        Delete very old models (downloaded long time ago).

        Args:
            days: Number of days since download

        Returns:
            Number of deleted entries
        """
        threshold = timezone.now() - timedelta(days=days)

        old_models = ExternalHMMModel.objects.filter(
            downloaded_at__lt=threshold
        )

        count = old_models.count()
        old_models.delete()

        logger.info(f"Cleaned up {count} old HMM cache entries (downloaded >{days} days ago)")
        return count

    @classmethod
    def get_cache_stats(cls) -> dict:
        """
        Return cache statistics.
        """
        total_models = ExternalHMMModel.objects.count()
        total_size = sum(m.file_size for m in ExternalHMMModel.objects.all())

        pfam_count = ExternalHMMModel.objects.filter(source='pfam').count()
        interpro_count = ExternalHMMModel.objects.filter(source='interpro').count()

        return {
            'total_models': total_models,
            'total_size_mb': round(total_size / (1024 * 1024), 2),
            'pfam_count': pfam_count,
            'interpro_count': interpro_count,
        }

    @classmethod
    def search_hmm(cls, source: str, query: str, max_results: int = 10) -> list:
        """
        Search for HMM models directly from API.
        Returns latest results based on query.
        """
       
        api_limit = max_results * 3 if source == 'interpro' else max_results

        if source == 'pfam':
            api_results = PfamAPIClient.search_by_name(query, api_limit)
        elif source == 'interpro':
            api_results = InterProAPIClient.search_by_name(query, api_limit)
        else:
            return []

        filtered_results = []
        for result in api_results:
            if source == 'interpro':
                has_pfam = result.get('has_pfam_model', False)
                if not has_pfam:
                    continue

            filtered_results.append(result)

            if len(filtered_results) >= max_results:
                break

        return filtered_results
