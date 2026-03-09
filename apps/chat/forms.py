from django import forms
from .models import ChatRoom
from django.utils.translation import gettext_lazy as _

class ChatRoomForm(forms.ModelForm):
    """Form for creating/editing chat rooms."""
    
    class Meta:
        model = ChatRoom
        fields = ['name', 'description', 'room_type', 'image', 'is_encrypted', 'max_members']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': _('Room name'),
                'maxlength': 100,
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'placeholder': _('Room description (optional)'),
                'rows': 3,
            }),
            'room_type': forms.Select(attrs={
                'class': 'form-select',
            }),
            'image': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': 'image/*',
            }),
            'is_encrypted': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
            }),
            'max_members': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 2,
                'max': 1000,
            }),
        }

    def clean_name(self):
        name = self.cleaned_data['name']
        if len(name) < 2:
            raise forms.ValidationError(_('Room name must be at least 2 characters.'))
        return name
