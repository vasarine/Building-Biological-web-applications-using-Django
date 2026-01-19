from django.db import models
from biologine_aplikacija.models import BaseHMMProject


class HMMEmitProject(BaseHMMProject):
    """
    HMMEMIT project model - inherits shared functionality from BaseHMMProject.
    Only tool-specific fields are defined here.
    """
    hmm_file = models.FileField(upload_to="hmmemit/", null=True, blank=True)
    output_file = models.FileField(upload_to="hmmemit/", null=True, blank=True)

    hmm_source = models.CharField(max_length=20, default='upload', null=True, blank=True)
    external_hmm_id = models.CharField(max_length=50, null=True, blank=True)
    external_hmm_name = models.CharField(max_length=255, null=True, blank=True)
