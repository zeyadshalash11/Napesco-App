# jobs/forms.py

from django import forms
from .models import Job
from django.core.validators import FileExtensionValidator

class JobAttachmentForm(forms.Form):
    file = forms.FileField(
        required=True,
        validators=[FileExtensionValidator(allowed_extensions=['jpg', 'jpeg', 'png', 'pdf', 'txt', 'xlsx', 'xls'])]
    )
    
    caption = forms.CharField(max_length=200, required=False)


class JobForm(forms.ModelForm):
    class Meta:
        model = Job
        fields = [
            'job_type', 
            'customer', 
            'date', 
            'status', 
            'rig', 
            'well', 
            'location', 
            'trans', 
            'description'
        ]
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
            'description': forms.Textarea(attrs={'rows': 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Add Bootstrap's form-control class to all fields
        for field_name, field in self.fields.items():
            field.widget.attrs['class'] = 'form-control'
        
        # Make the customer field searchable with Tom Select
        self.fields['customer'].widget.attrs.update({'id': 'customer-select'})    