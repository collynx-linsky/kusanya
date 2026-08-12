"""Shared CSV rendering — every report view supports `?format=csv` using
this, so adding CSV export to a new report is one line, not a
copy-pasted response-building block per view."""

import csv

from django.http import HttpResponse


def render_csv(filename: str, header: list[str], rows) -> HttpResponse:
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    writer = csv.writer(response)
    writer.writerow(header)
    for row in rows:
        writer.writerow(row)
    return response
