# SentinelForge Operations Runbook

This runbook defines the repository-side operational contract. Actual infrastructure provisioning and credentials are environment-specific.

## Production startup

1. Provision PostgreSQL/TimescaleDB and Redis.
2. Create a persistent application secret, Fernet key, and ingest key.
3. Set SENTINELFORGE_ENV=production.
4. Set explicit CORS_ORIGINS.
5. Configure database and Redis endpoints.
6. Configure TLS at the ingress/reverse proxy.
7. Start the Compose stack.
8. Verify /live, /ready, /health, and /metrics.
9. Confirm Celery worker and beat are consuming/dispatching tasks.
10. Run a controlled camera smoke test.

## Required production secrets

- SECRET_KEY: persistent JWT signing secret, at least 32 characters.
- FERNET_KEY: persistent encryption key where application-level Fernet encryption is used.
- BOOTSTRAP_ADMIN_TOKEN: deployment-time first-admin bootstrap credential.
- INGEST_API_KEY: machine-to-machine camera ingestion credential.
- POSTGRES_PASSWORD: database credential.

Never commit real values.

## Database backup contract

The infrastructure layer must provide:

- Scheduled PostgreSQL backups.
- Off-host backup storage.
- Encryption at rest.
- Retention policy.
- Restore testing.
- Point-in-time recovery where required.
- Documented RPO and RTO.

A backup that has never been restored is not a verified backup.

## Restore procedure

1. Stop application writers.
2. Restore PostgreSQL to a clean target.
3. Validate database connectivity.
4. Run Alembic migration state verification.
5. Start API.
6. Verify /ready and /health.
7. Start Celery worker and beat.
8. Validate representative dashboard queries.
9. Resume camera ingestion.
10. Record the restore result and elapsed time.

## Camera failure handling

A production deployment should monitor:

- stream connectivity
- frame rate
- frame age
- reconnect count
- decode failures
- inference latency
- dropped frames
- camera authentication failures

The application should not silently treat a dead camera as an operationally healthy camera.

## Security operations

Monitor:

- failed logins
- administrator changes
- camera configuration changes
- person creation/deletion
- privacy deletion requests
- export requests
- incident state transitions
- unusual API error rates
- ingest authentication failures

Audit logs should be shipped to durable infrastructure and retained according to approved policy.

## Scaling

Scale independently:

- API replicas for request throughput.
- Celery workers for background analytics.
- GPU inference workers for CV workloads.
- PostgreSQL for durable state.
- Redis for queues/caching.
- Object storage for footage and generated reports.

Do not scale camera count by simply increasing API worker count; video inference is a separate resource domain.

## Production acceptance criteria

A deployment is accepted only after:

- all CI checks are green;
- migrations apply cleanly;
- health/readiness checks are green;
- authentication and RBAC are verified;
- audit logging is verified;
- privacy deletion is verified;
- backups and restores are tested;
- representative camera streams are stable;
- end-to-end alert latency is measured;
- camera failure/reconnect behavior is tested;
- resource consumption is benchmarked;
- security review is complete;
- legal/compliance approval is complete where required.
