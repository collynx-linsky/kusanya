# Reporting

**Status: implemented (Phase 5), scoped as focused report views rather
than a generic report-builder engine.** Code: `apps/reports/`. Not one
of the documents explicitly listed in the build spec's docs/ structure
(section 35), but section 27 clearly wants first-class reporting, so it
gets its own document — same reasoning as
[WEBHOOK_ARCHITECTURE.md](WEBHOOK_ARCHITECTURE.md) in Phase 3.

## What build spec section 27 asks for, and where each report actually lives

| Section 27 report | Where it lives |
|---|---|
| Bills | `apps.reports.views.bills_report` — filters: status, date range |
| Control numbers | `apps.control_numbers.views.control_number_list` (Phase 2) |
| Payments / failed / successful | `apps.reports.views.payments_report` — filters: status, date range |
| Outstanding balances | `apps.reports.views.outstanding_balances_report` |
| Collections | `apps.reports.views.collections_report` — gross + platform revenue for a period |
| Reconciliation | `apps.reconciliation.views` (Phase 4) — already a report in its own right |
| Settlements | `apps.settlement.views` (Phase 4) — already a report in its own right |
| Platform revenue | `apps.revenue.views.tenant_revenue_summary` / `platform_revenue_dashboard` (Phase 4) |
| Provider fees | Included as a column in the settlement batch detail view (Phase 4) — always 0 today since the mock provider charges nothing |
| Institution revenue | `apps.reports.views.collections_report`'s gross-collected figure |
| Notifications | `apps.notifications.views.notification_list` (Phase 5) |
| Audit events | `apps.reports.views.audit_report` |

## Why focused views, not a generic report-builder

Building a fully generic "pick any model, any filter, any grouping"
reporting engine is a different, much larger project than what four
phases' worth of domain models actually need reported on today. Each
report view queries the specific model(s) it's about, with the specific
filters build spec section 27 names for that report (date, status,
customer, revenue source, channel/provider where applicable) — adding a
new filter to an existing report, or a new report entirely, is a
same-shaped, small, reviewable change, not a configuration-language
feature. See [../ARCHITECTURE_DECISIONS.md](../ARCHITECTURE_DECISIONS.md)
ADR-022.

## Filters — implemented per report, matching what's meaningful for it

Date range on every report that has a natural date field. Status filter
on bills and payments (dropdown populated from the model's own
`TextChoices`, so it can never drift out of sync with the real status
vocabulary). Free-text action filter on the audit report. Not every
filter build spec section 27 lists applies to every report — a "revenue
source" filter on the notifications report wouldn't mean anything, for
instance — each report only exposes the filters that are meaningful for
what it's reporting on.

## CSV export

`apps.reports.csv_export.render_csv()` — a single shared helper, added to
a report view by checking `?format=csv` and calling it instead of
rendering the HTML template. Implemented on the bills, payments, and
outstanding-balances reports; trivial to add to any other report the same
way.

## Tenant isolation

Every report view filters by `request.tenant`, following the same
explicit-filter pattern as every other portal view since Phase 2 (see
[MULTI_TENANCY.md](MULTI_TENANCY.md)) — a tenant only ever sees their own
bills, payments, audit events, and so on.

## What's not built

Scheduled/emailed reports (a tenant asking "send me the collections
report every Monday"), saved report definitions, and any cross-tenant
report beyond the two that already exist for platform staff (platform
revenue, platform settlement list) — none of these have a concrete
requirement driving them yet.
