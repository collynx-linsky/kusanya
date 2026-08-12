from django import forms
from django.contrib.auth.forms import AuthenticationForm


class EmailAuthenticationForm(AuthenticationForm):
    """Swaps the default `username` field label for `email` — the user
    model has no username field (see apps.users.models.User)."""

    username = forms.EmailField(
        label="Email",
        widget=forms.EmailInput(attrs={"autofocus": True, "class": "form-control"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["password"].widget.attrs.update({"class": "form-control"})
