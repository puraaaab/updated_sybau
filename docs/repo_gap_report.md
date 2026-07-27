# SYBAU VMS Repository Gap Report

This report captures the main bugs fixed in the `purab` branch and the larger product/engineering gaps that should be planned as follow-up work.

## Bugs fixed now

- Fixed the React Rules of Hooks violation in `LiveGrid.jsx` by moving heatmap hooks before the offline early return.
- Removed unused/dead LiveGrid code that caused lint failures or warnings, including an unused icon import, unused setter, and an unreachable Push-to-Talk state path.
- Made the OpenCV concurrency test skip cleanly when host OpenCV runtime libraries are unavailable, instead of failing the whole suite during import collection.
- Replaced a developer-specific Windows absolute Qdrant migration path with a repository-relative script path.
- Locked the public registration route behind admin authentication so anonymous users cannot self-register privileged accounts.
- Unified startup-seeded default passwords with the default login credentials used elsewhere in the app.

## Important follow-up gaps

### Security and access control

- Replace demo default accounts with an explicit first-run bootstrap flow before production use.
- Add password complexity, account lockout, and rate limiting to authentication endpoints.
- Add audit logs for login, logout, registration, camera mutation, zone mutation, watchlist mutation, export, and evidence download events.
- Add row-level or tenant-level authorization if multiple agencies/departments share the platform.
- Ensure production deployments set `APP_ENV=production`, `VMS_SECRET_KEY`, and strict `CORS_ALLOWED_ORIGINS`.

### Deployment and operations

- Add backend and frontend services to Docker Compose or provide production container images.
- Add Alembic migrations instead of relying only on `Base.metadata.create_all`.
- Add healthcheck definitions for Docker services and app-level readiness endpoints.
- Add environment-specific config examples such as `.env.example`.
- Add CI that installs OpenCV system runtime libraries and runs backend/frontend checks.

### AI pipeline and data quality

- Add deterministic test doubles for YOLO, OCR, face recognition, and captioning so CI does not require GPU/model downloads.
- Define model artifact management: where model files live, checksums, versions, and download scripts.
- Track detection confidence, model version, and frame timestamp in all AI-generated records.
- Add duplicate-alert suppression and alert cooldown windows per camera/zone/event type.
- Add explicit handling for camera clock skew and timezone normalization.

### Video and evidence handling

- Store clip hashes and snapshot hashes at write time, not only during export.
- Add tamper-evident chain-of-custody records for every evidence export.
- Validate `camera_id`, snapshot IDs, and clip names before serving files to reduce path traversal risk.
- Define retention policy UI and per-camera retention overrides.
- Move large/generated artifacts such as local DBs, recordings, snapshots, and model weights out of git.

### Frontend UX and maintainability

- Add a real login page instead of depending on demo quick-switch credentials.
- Address remaining lint warnings around exhaustive hook dependencies and unused symbols.
- Split the large production JS chunk with route/component-level dynamic imports.
- Add user-facing error states for backend unavailable, token expired, and stream unavailable.
- Add accessibility review for keyboard navigation, color contrast, and screen-reader labels.

### Testing

- Add backend API tests for auth/RBAC, camera CRUD, zones, alerts, playback, and export endpoints.
- Add frontend component tests for auth state, route visibility by role, and live grid states.
- Add integration tests that run against disposable PostgreSQL and Qdrant containers.
- Add security tests for unauthenticated access to admin-only endpoints.

## Suggested implementation order

1. Finish security hardening: auth bootstrap, login page, rate limiting, audit logs.
2. Add migrations and containerized app services.
3. Build stable CI with mocked AI dependencies.
4. Improve evidence integrity and retention controls.
5. Expand AI behavior quality and duplicate-alert suppression.
