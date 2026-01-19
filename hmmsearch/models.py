from django.db import models
from biologine_aplikacija.models import BaseHMMProject


class HMMSearchProject(BaseHMMProject):
    """
    HMMSEARCH project model - inherits shared functionality from BaseHMMProject.
    Only tool-specific fields are defined here.
    """
    fasta_file = models.FileField(upload_to="hmmsearch/")
    hmm_file = models.FileField(upload_to="hmmsearch/", null=True, blank=True)
    out_file = models.FileField(upload_to="hmmsearch/", null=True, blank=True)
    tblout_file = models.FileField(upload_to="hmmsearch/", null=True, blank=True)
    domtbl_file = models.FileField(upload_to="hmmsearch/", null=True, blank=True)

    tblout_text = models.TextField(null=True, blank=True)
    domtbl_text = models.TextField(null=True, blank=True)

    hmm_source = models.CharField(max_length=20, default='upload', null=True, blank=True)
    external_hmm_id = models.CharField(max_length=50, null=True, blank=True) 
    external_hmm_name = models.CharField(max_length=255, null=True, blank=True) 
