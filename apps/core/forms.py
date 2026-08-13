"""Shared form base classes backing the design system's form conventions
(docs/DESIGN_SYSTEM.md, ARCHITECTURE_DECISIONS ADR-033).

`KusanyaFormHelperMixin` wires a crispy-forms FormHelper with
`form_tag = False` — the `<form>` tag itself stays in the template (so a
view/template can freely add `hx-post`, `hx-target`, etc. without
crispy needing to know about HTMX), crispy only renders the fields.
"""

from crispy_forms.helper import FormHelper


class KusanyaFormHelperMixin:
    """Mix into any Form/ModelForm to get consistent Bootstrap 5 field
    rendering via crispy-forms — `{% load crispy_forms_tags %}{{ form|crispy }}`
    in the template, no manual widget-class wiring per field."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.helper.form_tag = False
        self.helper.disable_csrf = True  # the wrapping <form> handles its own {% csrf_token %}
