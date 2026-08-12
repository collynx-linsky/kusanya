from django import forms


class ApiCredentialForm(forms.Form):
    name = forms.CharField(max_length=150, label="Name", help_text='e.g. "School ERP integration"')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update({"class": "form-control"})
