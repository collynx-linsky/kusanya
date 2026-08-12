# Disaster Recovery

**Status: not yet implemented.** No backup automation, no tested restore
procedure, and no defined RTO/RPO exist for this project yet — this
document records the posture honestly rather than describing a plan that
hasn't been built or tested.

## What exists today

Local development data lives in a Docker-managed volume
(`kusanya_postgres_data`, see `docker-compose.yml`) with no automated
backup — expected, since Phase 1 has no production data and no tenant has
been onboarded outside test fixtures.

## What must exist before production

- **Automated PostgreSQL backups** (e.g. managed provider's point-in-time
  recovery, or `pg_dump`/WAL archiving on a schedule) with a defined
  retention period.
- **A tested restore procedure** — a backup that has never been restored
  is not a backup. This needs a documented, periodically-rehearsed
  runbook, not just "backups are configured."
- **Defined RTO (recovery time objective) and RPO (recovery point
  objective)** — how long can KUSANYA be down, and how much data can be
  lost, before it materially harms an institution that depends on it for
  collections. This is a product/business decision, not a purely
  technical one, and should be made before real institutions are
  onboarded (i.e., before a tenant leaves `PENDING` status in an
  environment with real money moving through it).
- **Redis persistence strategy** — Redis in this architecture is a
  cache/broker, not a system of record (all durable financial data lives
  in PostgreSQL), so Redis data loss should be recoverable without data
  loss, but this assumption should be explicitly verified once Celery
  carries real financial-notification workloads (Phase 5+).
- **Audit log export/off-box retention** — ties into
  [../ARCHITECTURE_DECISIONS.md](../ARCHITECTURE_DECISIONS.md) ADR-006:
  a disaster-recovery plan for the audit log specifically should include
  shipping it somewhere the primary database's own failure can't affect.

## Not this document's job

Choosing a specific cloud provider, backup tool, or managed database
tier — those are deployment decisions (see [DEPLOYMENT.md](DEPLOYMENT.md))
made when production infrastructure is actually selected.
