from django import forms
from django.core.validators import FileExtensionValidator
import re


class HMMEmitForm(forms.Form):
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

    hmm_source = forms.ChoiceField(
        label="HMM Source",
        choices=HMM_SOURCE_CHOICES,
        initial='upload',
        required=True,
        widget=forms.RadioSelect(attrs={
            "id": "hmm_source",
        }),
    )

    hmm_file = forms.FileField(
        label="Upload HMM file",
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
            "placeholder": "e.g., PF00001 or IPR000001",
            "class": "autocomplete-input",
        }),
    )

    num_seqs = forms.IntegerField(
        label="Number of sequences to generate",
        required=True,
        min_value=1,
        max_value=1000,
        initial=1,
        widget=forms.NumberInput(attrs={
            "id": "num_seqs",
            "min": 1,
            "max": 1000,
            "value": 1,
        }),
    )
    seed = forms.IntegerField(
        label="Random seed (optional)",
        required=False,
        widget=forms.NumberInput(attrs={
            "id": "seed",
            "placeholder": "e.g., 42",
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
                    'hmm_file': 'Please upload an HMM file or select a different source.'
                })

        elif hmm_source == 'library':
            if not external_hmm_id:
                raise forms.ValidationError({
                    'external_hmm_id': 'Please enter a Pfam or InterPro ID.'
                })

            external_hmm_id = external_hmm_id.upper().strip()
            cleaned_data['external_hmm_id'] = external_hmm_id

            if re.match(r'^PF\d{5}$', external_hmm_id):
                pass
            elif re.match(r'^IPR\d{6}$', external_hmm_id):
                pass
            else:
                raise forms.ValidationError({
                    'external_hmm_id': 'Invalid ID format. Use Pfam (e.g., PF00001) or InterPro (e.g., IPR000001) format.'
                })

        return cleaned_data
