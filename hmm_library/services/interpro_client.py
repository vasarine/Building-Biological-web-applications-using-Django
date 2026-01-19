import requests
import re
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)


class InterProAPIClient:
    """
    Client for working with InterPro API.

    API documentation:
    https://www.ebi.ac.uk/interpro/api/
    """

    BASE_URL = "https://www.ebi.ac.uk/interpro/api"
    TIMEOUT = 30

    @staticmethod
    def validate_interpro_id(interpro_id: str) -> bool:
        """
        Validate InterPro ID format.

        Possible formats:
        - IPR000001 (InterPro accession)
        - IPR012345
        """
        pattern = r'^IPR\d{6}$'
        return bool(re.match(pattern, interpro_id.upper()))

    @classmethod
    def get_entry_metadata(cls, interpro_id: str) -> Optional[Dict[str, Any]]:
        """
        Get InterPro entry metadata.

        Returns:
            Dict with: name, description, type, member_databases, etc.
            None if error or not found
        """
        if not cls.validate_interpro_id(interpro_id):
            logger.error(f"Invalid InterPro ID format: {interpro_id}")
            return None

        url = f"{cls.BASE_URL}/entry/interpro/{interpro_id.upper()}/"

        try:
            response = requests.get(url, timeout=cls.TIMEOUT)
            response.raise_for_status()

            data = response.json()

            meta = data.get('metadata', {})

            name_field = meta.get('name', '')
            if isinstance(name_field, dict):
                name = name_field.get('name', '')
                description = name_field.get('short', '')
            else:
                name = name_field
                description = name_field

            metadata = {
                'accession': meta.get('accession'),
                'name': name,
                'description': description,
                'type': meta.get('type'),
                'member_databases': meta.get('member_databases', {}),
            }

            return metadata

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to fetch InterPro metadata for {interpro_id}: {e}")
            return None
        except (KeyError, ValueError) as e:
            logger.error(f"Failed to parse InterPro response for {interpro_id}: {e}")
            return None

    @classmethod
    def get_pfam_members(cls, interpro_id: str) -> list:
        """
        Get Pfam members belonging to InterPro entry.

        InterPro entry can be an aggregation of multiple Pfam models.

        Returns:
            List of Pfam accessions (e.g. ['PF00001', 'PF00002'])
        """
        metadata = cls.get_entry_metadata(interpro_id)
        if not metadata:
            return []

        member_databases = metadata.get('member_databases', {})
        pfam_members = member_databases.get('pfam', [])

        pfam_ids = []

        if isinstance(pfam_members, dict):
            pfam_ids = list(pfam_members.keys())
        elif isinstance(pfam_members, list):
            for member in pfam_members:
                if isinstance(member, dict):
                    accession = member.get('accession')
                    if accession:
                        pfam_ids.append(accession)

        return pfam_ids

    @classmethod
    def download_hmm(cls, interpro_id: str) -> Optional[bytes]:
        """
        Download HMM model from InterPro.

        Note: InterPro entry can have multiple Pfam models.
        This method downloads the first found Pfam model.

        Args:
            interpro_id: InterPro accession (e.g. IPR000001)

        Returns:
            HMM file content as bytes
            None if error or no Pfam model
        """
        if not cls.validate_interpro_id(interpro_id):
            logger.error(f"Invalid InterPro ID format: {interpro_id}")
            return None

        pfam_members = cls.get_pfam_members(interpro_id)

        if not pfam_members:
            logger.warning(f"No Pfam members found for InterPro {interpro_id}")
            return None

        pfam_id = pfam_members[0]
        logger.info(f"Downloading HMM for InterPro {interpro_id} via Pfam {pfam_id}")

        from .pfam_client import PfamAPIClient

        return PfamAPIClient.download_hmm(pfam_id)

    @classmethod
    def search_by_name(cls, query: str, max_results: int = 10) -> list:
        """
        Search InterPro entries by name.

        Args:
            query: Search term
            max_results: Maximum number of results

        Returns:
            List of dicts with: accession, name, description, type
        """
        url = f"{cls.BASE_URL}/entry/interpro/"
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

                name_field = metadata.get('name', '')
                if isinstance(name_field, dict):
                    name = name_field.get('name', '')
                    description = name_field.get('short', '')
                else:
                    name = name_field
                    description = name_field

                member_databases = metadata.get('member_databases', {})
                pfam_members = member_databases.get('pfam', [])

                pfam_ids = []
                if isinstance(pfam_members, dict):
                    pfam_ids = list(pfam_members.keys())
                elif isinstance(pfam_members, list):
                    for member in pfam_members:
                        if isinstance(member, dict):
                            accession = member.get('accession')
                            if accession:
                                pfam_ids.append(accession)

                results.append({
                    'accession': metadata.get('accession'),
                    'name': name,
                    'description': description,
                    'type': metadata.get('type'),
                    'pfam_members': pfam_ids,
                    'has_pfam_model': len(pfam_ids) > 0,
                })

            return results

        except requests.exceptions.Timeout:
            logger.warning(f"InterPro search timeout for '{query}' (> {search_timeout}s)")
            return []
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to search InterPro for '{query}': {e}")
            return []
        except (KeyError, ValueError) as e:
            logger.error(f"Failed to parse InterPro search results: {e}")
            return []

    @classmethod
    def get_hmm_info(cls, interpro_id: str) -> Optional[Dict[str, Any]]:
        """
        Return complete information about HMM (metadata + Pfam members).

        Convenience method to get everything at once.
        """
        metadata = cls.get_entry_metadata(interpro_id)
        if not metadata:
            return None

        metadata['pfam_members'] = cls.get_pfam_members(interpro_id)
        return metadata
