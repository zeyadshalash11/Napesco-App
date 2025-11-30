# jobs/forms.py

from django import forms

class JobAttachmentForm(forms.Form):
    # This field is now very simple. The 'multiple' attribute will be in the HTML.
    file = forms.ImageField(required=True)
    
    caption = forms.CharField(max_length=200, required=False)