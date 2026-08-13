# Design System

P0 (Foundation) of the enterprise-UX rework — see ARCHITECTURE_DECISIONS
ADR-033 for why this stayed Django Templates + Bootstrap 5 + HTMX rather
than a SPA framework, and what tradeoff that constraint implies.

This document is both a reference for the pieces already built and an
honest map of what's migrated to the new patterns versus what still
renders under the old ones (correctly, just without the newer
conventions) — see "Migration status" at the end.

## Design tokens (`static/css/design-tokens.css`)

Every color, spacing, radius, shadow, and type-size value used anywhere
in custom CSS is a CSS custom property defined here — never a hardcoded
hex/px value in `kusanya.css` or inline styles. Two reasons:

1. **Dark mode is a token swap, not a parallel stylesheet.** `[data-bs-theme="dark"]`
   redefines the same token names to different values; every component
   that reads `var(--kz-text)` etc. is automatically dark-mode-correct
   with zero component-level changes, whenever a toggle exists (P3 item
   26 — not built yet; the token structure is ready for it).
2. **The tokens also feed Bootstrap's own `--bs-*` variables**
   (`--bs-primary`, `--bs-border-radius`, `--bs-body-font-family`, …) —
   so unmodified Bootstrap components (alerts, buttons, badges, form
   controls) automatically pick up the KUSANYA palette instead of stock
   Bootstrap blue, without needing Sass recompilation or a custom
   Bootstrap build.

Token categories: brand scale (`--kz-brand-50`…`900`), neutral gray
scale, semantic surface/text/border tokens, sidebar-specific tokens,
4px-based spacing scale, radius scale, two-tier shadow scale (enterprise
apps lean on borders over drop shadows — shadows here are deliberately
subtle), and a system-font type scale (no webfont download).

## Application shell (`templates/base.html`, `partials/sidebar.html`, `partials/topbar.html`)

Persistent left sidebar (grouped, icon-labeled nav — Collections /
Finance / Operations / Developer / Platform admin, matching the app's
actual domain structure) + sticky top bar (breadcrumb, tenant badge,
user menu) + a single content region. Every page template only ever
fills `{% block content %}` (and optionally `{% block breadcrumb %}`,
`{% block topbar_actions %}`) — the shell itself never changes per-page.

**`base.html` vs `base_auth.html`:** pages that require no
authentication (login, MFA verify, institution onboarding) extend
`base_auth.html` instead — a minimal centered layout with just the
brand bar, no sidebar. This is two separate template files, not one
template with an `{% if user.is_authenticated %}` branch containing two
copies of `{% block content %}` — **Django template blocks cannot
appear twice in the same file, even in mutually exclusive branches**;
this genuinely broke every page the first time (`TemplateSyntaxError:
'block' tag with name 'content' appears more than once`) before being
split into two files. If you need a third layout variant, use a third
file, not a bigger conditional in one.

**Responsive:** the sidebar becomes an off-canvas drawer below the `lg`
breakpoint (`kusanya.css`'s `@media (max-width: 991.98px)` block),
toggled by `static/js/kusanya.js` (`#kzSidebarToggle`) with a backdrop
click-to-close and auto-close on any HTMX navigation.

## Reusable components (`templates/components/`)

Django templates have no component/slot system — "reusable component"
here means one of two things:

- **CSS classes** for markup with arbitrary inner content (`.kz-card`,
  `.kz-card-body`, `.kz-card-header`, `.kz-table-wrap`, `.kz-form-card`)
  — write the markup directly in each template, styled consistently by
  class, same as any Bootstrap component.
- **`{% include %}` partials** for markup with fixed structure and a
  small number of parameters: `components/stat_card.html`,
  `components/empty_state.html`, `components/pagination.html`.

  **Gotcha that cost real debugging time:** a partial's "usage example"
  documented in a template comment must use `{% comment %}...{% endcomment %}`,
  never `{# ... #}`, if the example text itself contains `{% %}` syntax.
  A single-line `{# #}` comment does not reliably suppress a `{%
  include "self" %}`-shaped example written inside it — it was
  literally executed, and since the example was the component including
  *itself*, it recursed until `RecursionError`. Confirmed directly
  against `django.template.Template` before fixing: an `{% include %}`
  tag inside a `{# #}` block raised `TemplateDoesNotExist` instead of
  being ignored. `{% comment %}` blocks were verified safe with the
  same test and are what every component doc-comment uses now.

Status badges use a template filter, not a partial:
`{{ payment.status|status_badge_class }}` (`apps.core.templatetags.kusanya_ui`)
— a shared heuristic mapping common status vocabulary (active/pending/failed/…)
to Bootstrap semantic colors, since KUSANYA's various status fields
already share this vocabulary by convention. Falls back to neutral for
anything unrecognized; never raises.

## HTMX architecture

- **CSRF**: `hx-headers` on `<body>` injects `X-CSRFToken` for every
  HTMX request — no per-form wiring needed.
- **Global loading indicator**: a 2px top progress bar
  (`#kzProgressBar`), toggled by `htmx:beforeRequest`/`htmx:afterRequest`
  listeners in `kusanya.js`, for requests that don't have (or don't
  need) their own local `htmx-indicator`.
- **Toasts**: `#kz-toasts` is a fixed-position region. Two ways to show
  one — `window.kzShowToast(message, level)` client-side, or server-side
  via an `HX-Trigger: {"kzToast": {"message": "...", "level": "success"}}`
  response header (htmx dispatches it as a `kzToast` event, which
  bubbles to `document.body` and renders a Bootstrap `Toast`). A failed
  HTMX request with no such header still gets a generic "something went
  wrong" toast automatically (`htmx:responseError` listener) — an
  in-place action failing is never silently invisible.
- **Partial-swap convention**: a view that supports both a full page
  load and an HTMX-driven partial update checks
  `request.headers.get("HX-Request")` and `request.headers.get("HX-Target")`
  and renders a `_table.html`-style partial instead of the full page —
  see `apps.customers.views.customer_list` for the reference
  implementation (search-as-you-type re-fetches and swaps only
  `#kz-customer-table`, preserving the surrounding shell).
- **Deliberately not done**: global `hx-boost` on the whole shell (which
  would make every internal link an AJAX navigation, SPA-style, while
  keeping the sidebar/topbar persistent via `hx-select`). This is a
  legitimate future step, not ruled out — it was left out of P0
  specifically because verifying it doesn't desync the sidebar's
  active-link highlighting after a boosted navigation needs real browser
  testing this environment can't do, and shipping it unverified is worse
  than not shipping it. Apply it deliberately, page-section by
  page-section, with real browser verification each time.

## Forms

`django-crispy-forms` + `crispy-bootstrap5` (new dependency,
`ARCHITECTURE_DECISIONS` ADR-033) renders consistent, accessible
Bootstrap 5 form markup from a plain Django `Form`/`ModelForm` — no more
hand-writing `<label>`/`<input>`/error-list markup per field.

Pattern: mix `apps.core.forms.KusanyaFormHelperMixin` into a form class
(sets up a crispy `FormHelper` with `form_tag = False` so the `<form>`
tag — and any `hx-post`/`hx-target` attributes on it — stays in the
template, not generated by crispy), then in the template:

```
{% load crispy_forms_tags %}
<div class="kz-form-card">
    <form method="post">
        {% csrf_token %}
        {{ form|crispy }}
        <div class="kz-form-actions">
            <button type="submit" class="btn btn-primary">Save</button>
        </div>
    </form>
</div>
```

**Gotcha**: if a model field's type doesn't tell the whole validation
story (e.g. `Customer.email` is `EncryptedCharField`, not `EmailField`,
per ADR-032 — ciphertext can't be a Django `EmailField` at the DB
level), redeclare that one field explicitly on the form
(`email = forms.EmailField(...)`) rather than letting crispy/ModelForm
infer a plain text input from the model field class. `apps.customers.forms.CustomerForm`
is the reference example.

Reference implementation: `apps/customers/forms.py` +
`templates/customers/form.html`.

## Tables

Convention, not a single generic component (column sets vary too much
to genericize without a much heavier templating layer than this stack
uses): `.kz-table-wrap` > `.kz-table-toolbar` (search/filter controls) >
`.kz-table` (an ordinary `<table>`, styled by class) >
`{% include "components/pagination.html" %}`.

- **Search** is real Django ORM filtering, paginated with
  `django.core.paginator.Paginator` (25/page) — not client-side
  filtering of an already-rendered table.
- **Search on an encrypted field is exact-match only** — see
  ADR-032 for why, and `apps.customers.views.customer_list` for the
  concrete pattern (search a `Q()` of `lookup_hash` equality checks
  alongside a real `icontains` on any unencrypted field like
  `external_reference`). The empty state when a search matches nothing
  says so explicitly ("not a partial match"), instead of leaving a user
  to assume the record doesn't exist.
- **Sorting** only offers columns that are genuinely sortable — an
  encrypted column can't appear in an `order_by()` meaningfully (it
  would sort by ciphertext), so it simply isn't offered as a sort
  option, and `Customer.Meta.ordering`/`CustomerAccount.Meta.ordering`
  were changed to `-created_at`/`customer_id` for the same reason
  (ADR-032).
- **Pagination links preserve every other query param** (search text,
  sort) via `{% querystring_with page=N %}` — a page-2 link never
  silently drops an active search.

Reference implementation: `apps/customers/views.py::customer_list` +
`templates/customers/_table.html` (the HTMX-swappable partial) +
`templates/customers/list.html` (the full-page wrapper that includes
it).

## Migration status

**Fully migrated to every P0 pattern** (shell, search, pagination,
crispy forms, empty states): the Customers app (`list`, `detail`,
`form`) — the reference implementation everything above is described
against. The tenant dashboard uses the new `stat_card` component.
Login, MFA verify, and institution onboarding use the new
`base_auth.html` minimal layout.

**Gets the new shell/tokens automatically, not yet migrated to the
newer table/search/form patterns**: every other list/detail/form page
across billing, payments, control numbers, ledger, revenue,
reconciliation, settlement, webhooks, notifications, receipts, reports,
API credentials, and platform-admin views. These inherit the sidebar,
top bar, and design tokens simply by extending `base.html` (which every
page already did), and Bootstrap components on them already read the
new color/radius tokens — but their tables have no search/sort/pagination
yet, and their forms use hand-written markup instead of crispy-forms.
Extending the P0 patterns to each of these is real, bounded, mechanical
work (the customers app is the template to copy), not a design
question — a natural next increment, not attempted here to avoid
rushing ~15 templates without individual live verification the way
customers got.
