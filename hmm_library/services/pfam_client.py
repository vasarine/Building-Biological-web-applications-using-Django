import requests
import re
import gzip
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)


class PfamAPIClient:
    """
    Client for working with Pfam API (InterPro/EBI infrastructure).

    API documentation:
    https://www.ebi.ac.uk/interpro/api/
    """

    BASE_URL = "https://www.ebi.ac.uk/interpro/api"
    TIMEOUT = 30  

    @staticmethod
    def validate_pfam_id(pfam_id: str) -> bool:
        """
        Validate Pfam ID format.

        Possible formats:
        - PF00001 (Pfam-A accession)
        - PF12345
        """
        pattern = r'^PF\d{5}$'
        return bool(re.match(pattern, pfam_id.upper()))

    @classmethod
    def get_entry_metadata(cls, pfam_id: str) -> Optional[Dict[str, Any]]:
        """
        Get Pfam entry metadata.

        Returns:
            Dict with: name, description, version, type, etc.
            None if error or not found
        """
        if not cls.validate_pfam_id(pfam_id):
            logger.error(f"Invalid Pfam ID format: {pfam_id}")
            return None

        url = f"{cls.BASE_URL}/entry/pfam/{pfam_id.upper()}/"

        try:
            response = requests.get(url, timeout=cls.TIMEOUT)
            response.raise_for_status()

            data = response.json()

            metadata = {
                'accession': data.get('metadata', {}).get('accession'),
                'name': data.get('metadata', {}).get('name', {}).get('name', ''),
                'description': data.get('metadata', {}).get('name', {}).get('short', ''),
                'type': data.get('metadata', {}).get('type'),
                'member_databases': data.get('metadata', {}).get('member_databases'),
            }

            return metadata

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to fetch Pfam metadata for {pfam_id}: {e}")
            return None
        except (KeyError, ValueError) as e:
            logger.error(f"Failed to parse Pfam response for {pfam_id}: {e}")
            return None

    @classmethod
    def download_hmm(cls, pfam_id: str) -> Optional[bytes]:
        """
        Download HMM model from Pfam.

        Args:
            pfam_id: Pfam accession (e.g. PF00001)

        Returns:
            HMM file content as bytes
            None if error
        """
        if not cls.validate_pfam_id(pfam_id):
            logger.error(f"Invalid Pfam ID format: {pfam_id}")
            return None

        url = f"{cls.BASE_URL}/entry/pfam/{pfam_id.upper()}/?annotation=hmm"

        try:
            response = requests.get(url, timeout=cls.TIMEOUT)
            response.raise_for_status()

            content = response.content

            try:
                content = gzip.decompress(content)
                logger.info(f"Decompressed gzip content for {pfam_id}")
            except gzip.BadGzipFile:
                logger.info(f"Content not gzipped for {pfam_id}")
                pass

            if not content or not content.startswith(b'HMMER'):
                logger.error(f"Invalid HMM content received for {pfam_id}. First 100 bytes: {content[:100]}")
                return None

            logger.info(f"Successfully downloaded HMM for {pfam_id} ({len(content)} bytes)")
            return content

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to download HMM for {pfam_id}: {e}")
            return None

    @classmethod
    def search_by_name(cls, query: str, max_results: int = 10) -> list:
        """
        Search Pfam entries by name.

        Args:
            query: Search term
            max_results: Maximum number of results

        Returns:
            List of dicts with: accession, name, description
        """
        url = f"{cls.BASE_URL}/entry/pfam/"
        params = {
            'search': query,
            'page_size': max_results,
        }

        try:
            search_timeout = cls.TIMEOUT
            response = requests.get(url, params=params, timeout=search_timeout)
            response.raise_for_status()

            data = response.json()
            results = []

            for entry in data.get('results', [])[:max_results]:
                metadata = entry.get('metadata', {})
                results.append({
                    'accession': metadata.get('accession', ''),
                    'name': metadata.get('name', ''),
                    'description': metadata.get('name', ''),
                    'type': metadata.get('type', ''),
                })

            return results

        except requests.exceptions.Timeout:
            logger.warning(f"Pfam search timeout for '{query}' (> {search_timeout}s)")
            return []
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to search Pfam for '{query}': {e}")
            return []
        except (KeyError, ValueError) as e:
            logger.error(f"Failed to parse Pfam search results: {e}")
            return []

    @classmethod
    def get_hmm_info(cls, pfam_id: str) -> Optional[Dict[str, Any]]:
        """
        Return complete information about HMM (metadata + download URL).

        Convenience method to get everything at once.
        """
        metadata = cls.get_entry_metadata(pfam_id)
        if not metadata:
            return None

        metadata['download_url'] = f"{cls.BASE_URL}/entry/pfam/{pfam_id.upper()}/?annotation=hmm"
        return metadata
