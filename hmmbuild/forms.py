from django import forms
from django.core.validators import FileExtensionValidator

class HMMBuildForm(forms.Form):
    name = forms.CharField(
        label="Project Name",
        required=False,
        max_length=255,
        widget=forms.TextInput(attrs={
            "id": "name",
            "placeholder": "Enter project name",
        }),
    )
    msa_file = forms.FileField(
        label="Upload alignment (MSA) file",
        required=True,
        validators=[FileExtensionValidator(allowed_extensions=["sto", "aln", "phy", "fa", "fasta"])],
        widget=forms.ClearableFileInput(attrs={
            "id": "msa_file",
            "accept": ".sto,.aln,.phy,.fa,.fasta",
        }),
    )
