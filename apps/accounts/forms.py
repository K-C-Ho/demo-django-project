from datetime import date
from django import forms
from allauth.account.forms import SignupForm
from django.utils.translation import gettext_lazy as _
from .models import User

class UserSignupForm(SignupForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        self.fields['username'] = forms.CharField(
            max_length=150,
            required=True,
            label=_("Username"),
            widget=forms.TextInput(attrs={
                'autocomplete': 'username',
                'placeholder': _("Choose a username"),
                'autofocus': 'autofocus',
                'class': 'form-control form-control-lg',
            })
        )

        self.fields['email'] = forms.EmailField(
            required=False,
            label=_("Email address (optional)"),
            widget=forms.EmailInput(attrs={
                'autocomplete': 'email',
                'placeholder': _("your.email@example.com"),
                'class': 'form-control form-control-lg',
            })
        )

        self.fields['password1'] = forms.CharField(
            label=_("Password"),
            widget=forms.PasswordInput(attrs={
                'autocomplete': 'new-password',
                'placeholder': _("Create a password"),
                'class': 'form-control form-control-lg',
            })
        )

        self.fields['password2'] = forms.CharField(
            label=_("Password"),
            widget=forms.PasswordInput(attrs={
                'autocomplete': 'new-password',
                'placeholder': _("Confirm your password"),
                'class': 'form-control form-control-lg',
            })
        )

        self.fields['first_name'] = forms.CharField(
            max_length=150,
            required=False,
            label=_("First name (optional)"),
            widget=forms.TextInput(attrs={
                'autocomplete': 'given-name',
                'placeholder': _("First name"),
                'class': 'form-control form-control-lg',
            })
        )

        self.fields['last_name'] = forms.CharField(
            max_length=150,
            required=False,
            label=_("Last name (optional)"),
            widget=forms.TextInput(attrs={
                'autocomplete': 'family-name',
                'placeholder': _("Last name"),
                'class': 'form-control form-control-lg',
            })
        )

        self.fields['phone'] = forms.CharField(
            max_length=20,
            required=False,
            label=_("Phone number (optional)"),
            widget=forms.TextInput(attrs={
                'autocomplete': 'tel',
                'placeholder': _("Phone number"),
                'class': 'form-control form-control-lg',
            })
        )

        self.fields['date_of_birth'] = forms.DateField(
            required=False,
            label=_("Date of birth (optional)"),
            widget=forms.DateInput(attrs={
                'autocomplete': 'bday',
                'type': 'date',
                'class': 'form-control form-control-lg',
            })
        )
    
    def clean_phone(self):
        phone = self.cleaned_data.get('phone')
        if phone and not phone.isdigit():
            raise forms.ValidationError(
                _("Phone number must contain only digits."),
                code='invalid_phone'
            )
        return phone

    def clean_date_of_birth(self):
        dob = self.cleaned_data.get('date_of_birth')
        if dob:
            age = (date.today() - dob).days // 365
            if age < 13:
                raise forms.ValidationError(
                    _("You must be at least 13 years old."),
                    code='too_young'
                )
        return dob 
    
    def save(self, request):
        # Let allauth create and save the base user (username, email, password)
        user = super().save(request)

        # Now populate extra fields
        user.first_name = self.cleaned_data.get('first_name', '')
        user.last_name = self.cleaned_data.get('last_name', '')
        user.phone = self.cleaned_data.get('phone', '')
        user.date_of_birth = self.cleaned_data.get('date_of_birth', '')
        user.save()

        return user

class UserProfileForm(forms.ModelForm):
    """Form for editing user profile."""
    
    class Meta:
        model = User
        fields = ['username', 'email', 'first_name', 'last_name', 'phone', 'date_of_birth',
                  'avatar', 'bio', 'email_notifications', 'push_notifications']
        widgets = {
            'username': forms.TextInput(attrs={
                'autocomplete': 'username',
                'class': 'form-control',
                'placeholder': _('Username')
            }),
            'email': forms.EmailInput(attrs={
                'autocomplete': 'email',
                'class': 'form-control',
                'placeholder': _('Email')
            }),
            'first_name': forms.TextInput(attrs={
                'autocomplete': 'given-name',
                'class': 'form-control',
                'placeholder': _('First Name')
            }),
            'last_name': forms.TextInput(attrs={
                'autocomplete': 'family-name',
                'class': 'form-control',
                'placeholder': _('Last Name')
            }),
            'phone': forms.TextInput(attrs={
                'autocomplete': 'tel',
                'class': 'form-control',
                'placeholder': _('Phone number')
            }),
            'date_of_birth': forms.DateInput(attrs={
                'autocomplete': 'bday',
                'class': 'form-control',
                'placeholder': _('Date of birth'),
                'type': 'date'
            }),
            'avatar': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': 'image/*'
            }),
            'bio': forms.Textarea(attrs={
                'class': 'form-control',
                'placeholder': _('Tell us about yourself...'),
                'rows': 4
            }),
            'email_notifications': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
            'push_notifications': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
        }