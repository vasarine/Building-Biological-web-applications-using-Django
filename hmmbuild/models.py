from django.db import models
from biologine_aplikacija.models import BaseHMMProject


class HMMBuildProject(BaseHMMProject):
    """
    HMMBUILD project model - inherits shared functionality from BaseHMMProject.
    Only tool-specific fields are defined here.
    """
    msa_file = models.FileField(upload_to="hmmbuild/")
    hmm_file = models.FileField(upload_to="hmmbuild/", null=True, blank=True)
