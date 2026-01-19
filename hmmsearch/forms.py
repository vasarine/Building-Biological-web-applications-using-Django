from django import forms
from django.core.validators import FileExtensionValidator
import re


class HMMSearchForm(forms.Form):
    HMM_SOURCE_CHOICES = [
        ('upload', 'Upload file'),
        ('library', 'Use Pfam/InterPro library'),
    ]

    name = forms.CharField(
        label="Project Name",
        required=False,
        max_length=255,
        widget=forms.TextInput(attrs={
            "id": "name",
            "placeholder": "Enter project name",
        }),
    )
    fasta_file = forms.FileField(
        label="Upload FASTA sequence file",
        required=True,
        validators=[FileExtensionValidator(allowed_extensions=["fa", "fasta"])],
        widget=forms.ClearableFileInput(attrs={
            "id": "fasta_file",
            "accept": ".fa,.fasta",
        }),
    )

    hmm_source = forms.ChoiceField(
        label="HMM Source",
        choices=HMM_SOURCE_CHOICES,
        initial='upload',
        required=True,
        widget=forms.RadioSelect(attrs={
            "id": "hmm_source",
            "class": "hmm-source-radio",
        }),
    )

    hmm_file = forms.FileField(
        label="Upload HMM model file",
        required=False,
        validators=[FileExtensionValidator(allowed_extensions=["hmm"])],
        widget=forms.ClearableFileInput(attrs={
            "id": "hmm_file",
            "accept": ".hmm",
        }),
    )

    external_hmm_id = forms.CharField(
        label="Pfam/InterPro ID",
        required=False,
        max_length=50,
        widget=forms.TextInput(attrs={
            "id": "external_hmm_id",
            "placeholder": "Search... (e.g., PF00001, IPR000001, kinase)",
            "autocomplete": "off",
            "class": "hmm-autocomplete",
        }),
    )

    def clean(self):
        """Custom validation based on hmm_source selection"""
        cleaned_data = super().clean()
        hmm_source = cleaned_data.get('hmm_source')
        hmm_file = cleaned_data.get('hmm_file')
        external_hmm_id = cleaned_data.get('external_hmm_id')

        if hmm_source == 'upload':
            if not hmm_file:
                raise forms.ValidationError({
                    'hmm_file': 'Please upload an HMM file or select library.'
                })

        elif hmm_source == 'library':
            if not external_hmm_id:
                raise forms.ValidationError({
                    'external_hmm_id': 'Please enter a Pfam or InterPro ID.'
                })

            external_hmm_id = external_hmm_id.upper().strip()

            if re.match(r'^PF\d{5}$', external_hmm_id):
                pass
            elif re.match(r'^IPR\d{6}$', external_hmm_id):
                pass
            else:
                raise forms.ValidationError({
                    'external_hmm_id': 'Invalid format. Use Pfam (PF00001) or InterPro (IPR000001) ID.'
                })

        return cleaned_data
