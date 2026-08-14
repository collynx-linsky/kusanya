# Design System

P0 (Foundation), P1 (Enterprise UX), P2 (Advanced Features), and P3
(Quality) of the enterprise-UX rework — see ARCHITECTURE_DECISIONS
ADR-033 (P0), ADR-034 (P1), ADR-036 (P2, plus ADR-035 for a real
integrity bug P2's work surfaced), and ADR-037/038/039/040 (P3) for why
this stayed Django Templates + Bootstrap 5 + HTMX rather than a SPA
framework, and what tradeoff that constraint implies.

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

  **Gotcha that cost real debugging time (twice — see the correction
  below):** Django's `{# ... #}` comment tag **cannot span multiple
  lines, at all, regardless of content** — this is documented Django
  behavior, not a bug in this codebase, but easy to miss. A `{# #}`
  comment written across several lines simply fails to be recognized as
  a comment: the raw text, `{#`/`#}` markers included, renders as
  literal output. First discovered when a component's multi-line usage
  example (`{% include "components/empty_state.html" with ... %}`,
  written as a "comment" describing the component's own usage) turned
  out to still be *executed* — since the example was the component
  including itself, it recursed until `RecursionError`. That was
  initially (and incompletely) diagnosed as "only breaks if the comment
  contains `{% %}` syntax," which was wrong — P2 found three more
  multi-line `{# #}` comments with no embedded tags at all, silently
  leaking their literal text into rendered pages. Confirmed both the bug
  and the fix directly against `django.template.Template` before
  trusting it. The rule: **any comment spanning more than one line must
  use `{% comment %}...{% endcomment %}`**, which does support
  multi-line — never `{# #}`, even for a "safe-looking" multi-line note
  with no tag syntax in it.

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
it). Extended to a second reference case in P1:
`apps/billing/views.py::bill_list` (adds a status filter dropdown
alongside search — see "Filtering" below).

## Dashboard

The tenant dashboard combines the P0 stat cards with a **real recent
payments feed** (`apps.tenants.views.dashboard`'s `recent_payments`,
last 5 by `initiated_at`, real ORM query — never a fabricated activity
list). The platform (staff-only) dashboard got the same stat-card
treatment. Both had a stale "not yet implemented" notice corrected
while already being edited — see ADR-034.

## Filtering

A status filter (`<select>`) sits alongside search in the same toolbar
form, both triggering the same HTMX partial-swap (`apps/billing/views.py::bill_list`
is the reference — status is validated against `BillStatus.values`
before hitting the query, so an invalid/tampered value is silently
ignored rather than raising). The pattern generalizes to any model with
a `TextChoices` status field: pass `status_choices` in context, render
the `<select>`, filter with `.filter(status=status)` guarded by the
same "is this actually a valid choice" check.

## Modals / drawers

Two patterns, used for different reasons — pick based on whether the
modal's content depends on fresh server data:

- **Static Bootstrap modal, no HTMX** — for a confirmation whose text
  doesn't need a server round-trip (e.g. "cancel this bill?"). The
  modal markup is already in the page; `data-bs-toggle="modal"` opens
  it, a plain `<form method="post">` inside submits normally. Reference:
  the cancel-bill confirmation on `templates/billing/detail.html`, and
  the deactivate-customer confirmation on `templates/customers/detail.html`.
- **HTMX-loaded modal** — for content that needs current server state
  (a full create/edit form, in particular). A trigger element sets
  `hx-get="..." hx-target="#kzModalBody"` alongside
  `data-bs-toggle="modal" data-bs-target="#kzModal"` (the shared modal
  shell lives once in `templates/base.html`) — clicking it fetches the
  form fragment and swaps it into the modal body, showing a skeleton
  placeholder (`components/skeleton_form.html`) while in flight. On
  successful POST, the view sets an `HX-Redirect` response header
  (`response["HX-Redirect"] = response.url`) rather than relying on the
  default 302 handling — htmx would otherwise AJAX-fetch the redirect
  target and swap *that* into the modal, which is never what "the form
  succeeded, now show me the updated page" means. On a validation
  error, the view re-renders just the form fragment (with errors) back
  into the same target — the modal never closes on a failed submit.
  Reference implementation: `apps.customers.views.account_create` (GET
  returns `customers/_account_form_modal.html` for an HTMX request, a
  full page otherwise — the same URL works both ways, so the feature
  degrades gracefully with HTMX/JS unavailable) +
  `templates/customers/detail.html`'s "New account" button.

## Notifications (topbar alerts)

The bell in the top bar is backed by `apps.core.context_processors.topbar_alerts`
— a context processor computed on every authenticated request from
**genuinely real, already-existing state**: open reconciliation
exceptions (tenant-scoped) and pending institution approvals
(platform-staff-scoped). This is deliberately *not* a stored/historical
notification inbox with read/unread state — building one with no real
backing data model, or faking entries, would violate this project's own
"no fake functionality" rule. It answers "does anything need my
attention right now," recomputed fresh each time, not "what happened
recently." A persistent, markable-as-read inbox is a legitimate future
feature (P2/P3 territory) but needs its own model and its own design
pass, not a retrofit of this.

## Loading states

- **Global**: the P0 top progress bar covers any HTMX request.
- **Search**: a spinner inside the search input's `input-group`
  (`htmx-indicator`), scoped to just that control.
- **HTMX-loaded modal content**: `components/skeleton_form.html` — a
  generic pulsing-placeholder block (`.kz-skeleton`, defined in
  `kusanya.css`) shown in `#kzModalBody` before any request has been
  made, replaced by the real fragment once one loads. Generic
  on purpose (not shaped to any specific form's field count) — it's a
  loading placeholder, not a preview of the content about to arrive.

## Empty / error states

`components/empty_state.html` (P0) is now also what `403.html`/`404.html`
render — access-denied and not-found are just empty states with a
different icon/copy, not a special case. **`500.html` is deliberately
the one page that does NOT extend `base.html`** and has no dependency on
static files, context processors, or the database — Django renders it
with a bare `Context()` (no request) in production, and it may be the
page shown during an actual outage of the infrastructure (static
files, DB-backed context, …) everything else here depends on. Confirmed
directly: `render_to_string("500.html")` with zero context renders
correctly standalone.

## CRUD experience

Customers went from Create+Read only (no way to edit a customer, or
remove one from active use, from the portal at all) to full CRUD:

- **Update**: `apps.customers.views.customer_edit`, reusing `CustomerForm`
  with `instance=customer` — same form, same template, same validation
  as create.
- **Delete → deactivate**: `apps.customers.views.customer_deactivate`/`customer_activate`
  toggle `Customer.is_active` rather than deleting the row. A hard
  delete of a customer with bills/payments attached would corrupt
  financial history — the same "never delete, only mark/compensate"
  principle already applied to every other domain model here
  (immutable financial records, ADR-006) extends naturally to Customer
  even though it isn't itself a financial-event model. Both actions are
  confirmed via a modal (see "Modals" above) before anything happens.

## Command palette

Ctrl/Cmd+K (or clicking the "Search…" button in the top bar) opens a
modal with a single search input, hitting `apps.core.views.command_palette_search`
on every keystroke (150ms debounce) via HTMX. Results are two kinds,
both real:

- **Navigation shortcuts** — a static list mirroring the sidebar's real
  links (`apps.core.views._NAV_SHORTCUTS`), filtered by substring match
  on the label. Not a separate source of truth from the sidebar; if a
  sidebar link changes, update the same list.
- **Entity search** — `apps.core.search.search_customers`/`search_bills`,
  reusing the exact-match-on-encrypted-fields constraint already
  established (ADR-032) rather than inventing a separate, laxer search
  behavior just for the palette.

Empty query shows a prompt, not an empty list; no matches shows a real
"no matches" message. Arrow keys move a `.active` class between result
rows (`static/js/kusanya.js`), Enter activates the highlighted (or
first) result, Esc closes (native `<dialog>`/Bootstrap modal
behavior).

## Keyboard shortcuts

- **Ctrl/Cmd+K** — opens the command palette, from anywhere, including
  while focus is inside a text input (this one intentionally overrides
  "don't act on shortcuts while typing").
- **/** — focuses the current page's search/filter input, if it has one
  (`input[type="search"]`) — skipped while already typing in a field.
- **?** — opens a real shortcuts-help dialog (`#kzShortcutsModal` in
  `base.html`) listing exactly these shortcuts, not a placeholder.
- **Esc** — closes whatever Bootstrap modal is open (native Bootstrap
  behavior, no custom code needed).

`isTypingInField()` in `kusanya.js` is the guard that stops `/` and `?`
from firing while a user is typing a real `/` or `?` character into a
form field — only Ctrl/Cmd+K is exempt, since a global "quick open"
shortcut is expected to work anywhere.

## Bulk operations

Checkbox-select on the Customers list (`kz-bulk-checkbox` per row,
`kz-bulk-select-all` in the header) shows a bulk-actions bar
(`apps.customers.views.customer_bulk_deactivate`) once at least one row
is selected. Deliberately a real `<form>` POST — every selected
customer is individually validated (tenant-scoped, so another tenant's
ID slipped into the request is silently ignored, not acted on) and
individually audited (`metadata={"bulk": True}` distinguishes a bulk
action from a one-at-a-time deactivate in the activity timeline, but
both produce the same real `customer.deactivated` event). The
confirmation is a native `confirm()`, not another Bootstrap modal —
deliberately, since the confirmation text depends on a dynamically
changing selection count and a native dialog is genuinely simpler for
that specific shape than wiring a modal's body to update on every
checkbox change.

## Background jobs

`apps.core.views.background_jobs` aggregates real state from tables
this system already writes to as a side effect of normal operation —
not a generic Celery task browser (that's a real, separate
infrastructure decision, needing something like Flower or
django-celery-results, for later): `WebhookDelivery` and `Notification`
status counts (tenant-scoped), plus — platform-staff only —
`django_celery_beat.PeriodicTask.last_run_at`/`total_run_count` for
scheduled tasks like the health monitor (ADR-031). If a count reads
zero, it's because nothing has happened yet, not because the query is
broken — confirmed by checking the real counts against real webhook/
notification fixtures in tests, not just that the page returns 200.

## Activity timelines

`apps.audit.services.get_activity_for(target)` returns every `AuditLog`
event recorded against a specific object (via its existing
`GenericForeignKey`), newest first — `components/activity_timeline.html`
renders that queryset as a vertical timeline with an expandable
before/after diff per entry. Applied to the Customer detail page as the
reference (real events: `customer.created`, `customer.updated` — added
in P2 specifically so the timeline wouldn't be dishonestly incomplete
for edits made through the new CRUD UI — `customer.deactivated`,
`customer.reactivated`). Nothing here is synthesized for display; an
empty timeline shows a real empty state, not placeholder rows.

## Audit visualization

The audit report (`apps.reports.views.audit_report`, rendering
`reports/audit.html` and `reports/_audit_table.html`) gained pagination
(50/page — it was silently capped at `[:500]` with no way to see
further back), CSV
export (`?format=csv`, using the pre-existing `apps.reports.csv_export.render_csv`
helper already used by every other report), and HTMX partial-swap
search/filter on top of the date-range filters that already existed.

Separately, a real **"Verify audit chain integrity"** action was added
to the platform dashboard (`apps.audit.views.verify_chain`, POST-only,
platform-staff-gated) that calls the pre-existing
`AuditLog.verify_chain()` classmethod and reports the real result. This
is deliberately platform-staff-only rather than exposed on the
per-tenant audit report — the hash chain is one global sequence across
every tenant, not one chain per tenant, so verifying a tenant-filtered
subset would misinterpret "this tenant's first record isn't preceded by
GENESIS_HASH" as tampering. Building this genuinely useful feature is
also what surfaced a real bug in the hash chain itself — see
ARCHITECTURE_DECISIONS ADR-035 for the full story (a false-positive
"tampering" report caused by deleting a user after they performed an
audited action, and the fix).

## Accessibility

Contrast, keyboard, and screen-reader basics across the shell, not a
one-page audit. `--kz-sidebar-text-muted` (`static/css/design-tokens.css`)
was changed from `--kz-gray-500` (3.75:1 against the sidebar background
— fails WCAG AA's 4.5:1 for normal text) to `--kz-gray-400` (6.96:1) —
see ARCHITECTURE_DECISIONS ADR-037 for how this was found (computing
real relative-luminance contrast ratios for every text/background token
pairing in use, not eyeballing it). `.kz-skip-link` (`base.html` and
`base_auth.html`, both) is a real skip-to-content link targeting
`#kz-content-region`, visible on keyboard focus. `:focus-visible`
outlines were added for `.kz-nav-link`, `.kz-palette-item`,
`.kz-stat-card`, and `.kz-avatar` — interactive elements that previously
fell back to the browser default (or nothing, where a default outline
had been suppressed elsewhere in `kusanya.css`). Every active nav link
in `partials/sidebar.html` now carries `aria-current="page"` via a new
`{% aria_current_ns %}` template tag (`apps.core.templatetags.kusanya_ui`)
alongside the pre-existing `{% is_active_ns %}`/`{% is_active_view %}`
tags that drive the same link's active *styling* — kept as separate
tags rather than merged, since a link can need the CSS class without
being the page-level "current page" (e.g. a filter chip). User-facing
strings in the shell (sidebar, topbar, both base templates) are wrapped
in `{% trans %}` — see "Internationalization" below, which doubles as
an accessibility win since screen readers announce content in whatever
language `lang="{{ LANGUAGE_CODE }}"` (set on `<html>`) declares.

## Dark mode

`[data-bs-theme]` on `<html>`, resolved from a three-way preference —
`light` / `dark` / `system` — stored in `localStorage` under `kzTheme`.
The resolve has to happen *before* first paint or the page flashes the
wrong theme; `partials/theme_init.html` is a small synchronous
`<script>` included first inside `<head>` on both `base.html` and
`base_auth.html` (before any stylesheet) that reads `localStorage`,
falls back to `matchMedia("(prefers-color-scheme: dark)")`, and sets
`data-bs-theme` directly — no framework, no flash. The visible toggle
(topbar's theme dropdown, three `.kz-theme-option` buttons) is wired in
`static/js/kusanya.js`, which calls the *same* resolution logic via
`window.KZLogic.resolveTheme` (`static/js/kusanya-logic.js` — see
"Automated frontend testing" below for why this got split out) so the
no-flash script and the live toggle can never disagree about what
"system" currently resolves to. Choosing "system" after page load also
attaches a `matchMedia` change listener, so the theme updates live if
the OS preference changes without a reload. Design tokens
(`design-tokens.css`) already fed Bootstrap's own `--bs-*` variables
from P0, so no component needed dark-mode-specific overrides beyond
what `[data-bs-theme="dark"]` already gives Bootstrap out of the box.

## Mobile optimization

An audit of every component added in P0–P2 against the existing
`lg` breakpoint (the sidebar's own off-canvas threshold, unchanged from
P0). The one real fix: `.kz-breadcrumb` was overflowing/wrapping badly
on narrow viewports, so it's hidden below `767.98px`
(`@media (max-width: 767.98px) { .kz-breadcrumb { display: none; } }`)
— the page title in `<h1>`/`{% block title %}` already conveys location
on mobile, so hiding the breadcrumb trail there loses no information,
only chrome that didn't fit. `.kz-topbar-actions { flex-shrink: 0; }`
stops the topbar's action buttons (theme toggle, language switcher,
notification bell) from being crushed when the topbar is narrow. No
other P0–P2 component needed a mobile-specific rule — the design
system's grid/spacing tokens and Bootstrap's own responsive utilities
already covered the rest.

## Internationalization

Django's standard i18n framework: `LocaleMiddleware` (`config/settings/base.py`,
positioned after `SessionMiddleware`/before `CommonMiddleware`, per
Django's documented ordering requirement), the `i18n` context processor,
and `{% trans %}`/`{% blocktrans %}` throughout the shell templates
(`base.html`, `base_auth.html`, `sidebar.html`, `topbar.html`) and every
page that extends `base_auth.html` (`accounts/login.html`,
`accounts/mfa_verify.html`, `tenants/onboarding.html`). `LANGUAGES =
[("en", "English"), ("sw", "Kiswahili")]`; `partials/language_switcher.html`
is a shared dropdown (included in both base templates' topbar) that
POSTs to Django's built-in `set_language` view
(`path("i18n/", include("django.conf.urls.i18n"))` in `config/urls.py`)
and shows a checkmark against `{% get_current_language %}`.

Kiswahili's `locale/sw/LC_MESSAGES/django.po` is hand-authored (57
reviewed translations covering the shell chrome and every pre-login
page) and compiled with `pybabel compile` rather than GNU gettext's
`msgfmt` — see ARCHITECTURE_DECISIONS ADR-038 for why (no admin rights
to install system gettext in this environment; `babel`, a pure-Python
package, is a real substitute for *compiling* `.po` → `.mo`, just not
for `makemessages`' auto-extraction, which is manual for now). This is
scoped honestly to what's actually translated — the shell and the
pre-login pages, not yet every authenticated-area page body, model-
generated string, or Python-side form field label — rather than
claiming broader coverage than it has. Live-verifying the language
switcher's actual HTTP round-trip (not just that the `.mo` compiled)
caught one real bug this way: `login.html` and `onboarding.html` each
override `base_auth.html`'s `{% block topbar_actions %}` with their own
markup, so the parent's already-translated "Sign in"/"Register
institution" text never reached those two pages — the override's own
copy needed `{% trans %}` independently. See ADR-038 for the full
story.

## Performance

Three real N+1 query fixes (`apps.customers.views.customer_list`/`customer_detail`,
`apps.billing.views.bill_detail`) — see ARCHITECTURE_DECISIONS ADR-039
for the mechanism (`QuerySet.count()` always issues its own query, even
inside a `prefetch_related`'d loop, so a per-row `{{ x.count }}` in a
template was one extra query per row rendered; fixed via
`.annotate(Count(...))` and, for `bill_detail`, extending the existing
`prefetch_related` to cover `payment_allocations__payment` and
collapsing a separate `.exists()` + `.all()` into one `{% with %}`).
Both base templates gained `<link rel="preconnect">` hints for the CDN
origins (`cdn.jsdelivr.net`, `unpkg.com`) already in use for
Bootstrap/HTMX, shortening the connection-setup time for those requests
without changing what's loaded. No bundler/build-step was introduced
(ADR-033 still holds) — these are the two performance levers available
without one: fewer queries per request, and faster setup for the fixed,
small set of external requests every page already makes.

## Print/PDF optimization

A global `@media print` block in `kusanya.css` hides shell chrome —
sidebar, topbar, the progress bar, the toast region, and every modal
(`#kzPaletteModal`, `#kzShortcutsModal`, `#kzModal`) — on *every* page,
not just designated "printable" ones, plus `.kz-breadcrumb` (redundant
once the page has a printed title) and the `.kz-main` margin the
sidebar otherwise reserves. Cards/tables lose their shadow and get a
plain `1px solid` border instead — screen-only elevation cues that
don't mean anything on paper. `templates/receipts/detail.html` was
rewritten onto the current `.kz-card` component (it had been left on
the pre-P0 `.card`/`.card-body` markup) and its print action relabeled
"Print / Save as PDF" — `window.print()` already lets the browser's own
print dialog save to PDF, so no separate PDF-generation library was
needed for what is, in every browser this app needs to support, the
same underlying capability.

## Security UX

Two additions, both reusing infrastructure this project already had
rather than building something parallel. A password-visibility toggle
(`static/js/kusanya.js`) is applied automatically to every
`input[type="password"].form-control` on the page — wraps it in
`.kz-password-wrap`, adds a show/hide button with `aria-pressed`
tracking its state — reducing mistyped-password lockouts against this
app's own login throttle (`apps.accounts.throttle`, 5 failed attempts)
without weakening anything: the value never leaves the input, only how
the browser renders it changes. And an MFA-not-enabled nudge was added
to `apps.core.context_processors.topbar_alerts` (the same real,
live-computed alerts mechanism from ADR-034 — open reconciliation
exceptions, pending tenant approvals) rather than a second notification
path: if `MFADevice.objects.filter(user=request.user, confirmed=True)`
is empty, an alert linking to `accounts:mfa-status` appears in the
topbar bell.

## Automated frontend testing

`static/js/kusanya.js` stayed a single unbundled `<script>` (ADR-033:
no build step), so rather than introduce a bundler purely to make it
importable, its two DOM-independent pure functions — `resolveTheme`
(dark mode's light/dark/system resolution) and `isTypingInField` (the
keyboard-shortcut guard that ignores `/` and `?` while the user is
typing in a field) — were split into `static/js/kusanya-logic.js`, a
small UMD-style module: a plain `window.KZLogic` global in the browser
(loaded via its own `<script>` tag immediately before `kusanya.js` in
both base templates — no behavior change), `module.exports` under
Node/Vitest. `static/js/kusanya-logic.test.js` unit-tests that module
directly (8 tests). `static/js/kusanya.dom.test.js` uses Vitest's
`jsdom` environment to `import()` the *actual* production `kusanya.js`
against a hand-built DOM fragment and assert on real mutations — the
password-toggle and bulk-selection-bar behaviors (5 tests) — rather
than reimplementing their logic under test. Command palette, toasts,
and modal wiring depend on the Bootstrap JS bundle loaded from a CDN in
the real page; faking `bootstrap.Toast`/`Modal` in jsdom to cover those
would test the fake, not the app, so they're left to manual live
verification instead. `npm test` (via `package.json`/`vitest.config.js`
at the repo root, dev-tooling only — no `dependencies`, only
`devDependencies: {vitest, jsdom}`) runs all 13 tests. See
ARCHITECTURE_DECISIONS ADR-040 for the full reasoning.

## Migration status

**Fully migrated to every P0+P1 pattern** (shell, search, filtering,
pagination, crispy forms, empty states, CRUD, modals): the Customers
app (`list`, `detail`, `form`, edit, deactivate/activate, the HTMX
account-creation modal) — the reference implementation everything above
is described against.

**Migrated to search/filter/pagination, not yet to full CRUD or
modals**: Bills (`billing/list.html` + `_table.html` — search, status
filter, pagination; `billing/detail.html` — modal-confirmed cancel, the
design-system card/table styling, `status_badge_class`). Bills has no
Update/Delete UI yet (bills are largely immutable once issued by
design — cancel is the closest analog and already exists).

**Migrated in P2**: the audit report (`reports/audit.html` — search,
pagination, CSV export) and the receipts list (reframed as "Documents,"
see "Command palette"/"Document management" reasoning in ADR-036).
Customer detail additionally gained a real activity timeline.

**Global/cross-cutting, so every page already has these regardless of
migration status**: the command palette (Ctrl/Cmd+K), keyboard
shortcuts, the topbar notification bell (P1), and the background-jobs
page (linked from the sidebar) — none of these depend on a page having
been individually migrated, since they live in `base.html`/the shell or
are their own new page.

**Gets the new shell/tokens/notification-bell/command-palette
automatically, not yet migrated to the newer table/search/form/CRUD
patterns**: payments, control numbers, ledger, revenue, reconciliation,
settlement, webhooks, notifications, reports (bills/payments/collections/
outstanding-balances specifically — these already had real
filtering *and* CSV export before P0 even started, see
`apps/reports/csv_export.py`; what they're missing is visual migration
and pagination, not functionality), API credentials, and platform-admin
views. These inherit the sidebar, top bar, design tokens, and the real
topbar-alerts bell simply by extending `base.html` (which every page
already did) — but their tables have no search/sort/pagination yet, and
their forms use hand-written markup instead of crispy-forms. Extending
the pattern to each of these is real, bounded, mechanical work (Bills
and the audit report are now worked examples alongside Customers,
covering the "search + filter, no CRUD" shape most of these will need),
not a design question — a natural next increment, not attempted here to
avoid rushing the remaining templates without individual live
verification.
