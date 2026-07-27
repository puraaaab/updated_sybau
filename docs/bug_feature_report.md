# SYBAU VMS Bug and Feature Report

## Scope

This report is based on a static review of the current repository plus local lint/test/build checks. It focuses on bugs, risks, and practical features that can be added in the next implementation pass.

## Current check results

- `npm run lint` exits successfully, but still reports warnings for unused imports/parameters and hook dependency issues across multiple frontend components.
- `python -m pytest tests -q` previously passes with one environment-dependent OpenCV skip.
- `python -m pytest backend/tests -q` previously skips Qdrant integration tests when Qdrant/migration prerequisites are unavailable.
- `npm run build` previously succeeds, but reports a large frontend JavaScript chunk.

## High-priority bugs to fix next

### 1. Playback file serving allows unsafe path construction

**Where:** `backend/main.py` playback routes and `backend/services/forensics.py` export download route.

**Problem:** `camera_id`, `clip_name`, `snap_id`, and export `filename` are joined directly into filesystem paths. Even with `abspath`, the code does not verify that the final path remains inside the intended storage directory.

**Impact:** A malicious or malformed path value may allow path traversal attempts or unexpected file exposure.

**Recommended fix now:** Add a small safe-path helper using `Path.resolve()` and reject any resolved path outside the expected base directory. Also constrain route parameters with regex patterns for UUID-like snapshot IDs, camera IDs, MP4 filenames, and ZIP filenames.

### 2. YouTube/HLS proxy is an open SSRF-style proxy

**Where:** `/api/v1/proxy/m3u8` and `/api/v1/proxy/ts` in `backend/main.py`.

**Problem:** Both endpoints accept arbitrary URLs and fetch them server-side without authentication or host allowlisting.

**Impact:** The backend could be abused to fetch internal/private network URLs, cloud metadata endpoints, or arbitrary third-party content.

**Recommended fix now:** Require viewer authentication, restrict schemes to HTTPS, allow only known video CDN domains when possible, block private/link-local IP ranges, and add response size/time limits.

### 3. Face search uses random embeddings

**Where:** `backend/main.py` face search endpoint.

**Problem:** Uploaded face search currently ignores the uploaded image content and searches using a random 384-dimensional vector.

**Impact:** Results are non-deterministic and misleading for a forensic search workflow.

**Recommended fix now:** Either wire the upload into the face embedding pipeline or return `501 Not Implemented` unless a real embedding can be generated. Avoid returning fake investigative results.

### 4. Soft-delete/status fields are not persisted

**Where:** `backend/admin/router.py` and `backend/database/models.py`.

**Problem:** Admin routes use `getattr/hasattr` for `status`, `must_change_password`, and `deleted_at`, but the `User` SQLAlchemy model does not define these columns.

**Impact:** Soft-delete and status updates appear to work from the API response, but they do not persist in the database.

**Recommended fix now:** Add real columns to `User` and introduce migrations. Until then, remove UI/actions that imply persisted account status.

### 5. Audit logs do not cover important actions

**Where:** Auth, camera, zone, alert acknowledge, playback export, settings, and watchlist routes.

**Problem:** Only some admin/forensic actions write audit logs.

**Impact:** For a police/evidence VMS, missing audit records reduce accountability and chain-of-custody value.

**Recommended fix now:** Add a shared `write_audit_log()` helper and call it from login, camera CRUD, zone save, alert acknowledge, settings updates, exports/downloads, and watchlist mutations.

### 6. Frontend still depends on hardcoded demo credentials

**Where:** `frontend/src/App.jsx` role switching and auto-login flow.

**Problem:** The UI auto-logs in as admin and has a quick role-switch map with static passwords.

**Impact:** This is useful for demos but unsafe and confusing outside demo mode.

**Recommended fix now:** Add a real login screen and put demo auto-login/role switching behind `VITE_DEMO_MODE=true`.

### 7. Frontend lint warnings remain

**Where:** `frontend/src/App.jsx`, `AdminConsole.jsx`, `SettingsConsole.jsx`, `ForensicsManager.jsx`, `ArchivePlayback.jsx`, `WatchlistManager.jsx`, `TrajectoryMap.jsx`, `InvestigationSearch.jsx`, `CameraManagement.jsx`, and `LiveGrid.jsx`.

**Problem:** The current lint command exits successfully, but reports many warnings for missing hook dependencies and unused symbols.

**Impact:** Hook dependency warnings can become stale-data bugs; unused symbols increase maintenance noise.

**Recommended fix now:** Clean unused imports/parameters and wrap loader functions in `useCallback` where they are dependencies of `useEffect`.

### 8. Qdrant tests are skip-friendly but not actually validating in normal local runs

**Where:** `backend/tests/test_qdrant_collection_vehicle_dim.py`.

**Problem:** Tests skip when Qdrant or the migration cannot run.

**Impact:** CI may pass without ever checking vector collection dimensions.

**Recommended fix now:** Add a Docker-backed integration test job for Qdrant and mark it separately from fast unit tests.

### 9. Heatmap endpoint returns demo random data when no tracks exist

**Where:** `backend/main.py` analytics heatmap route.

**Problem:** When the database has no recent tracks, the endpoint returns random demo hotspots.

**Impact:** Operators may confuse simulated hotspots with real activity.

**Recommended fix now:** Return an empty result unless an explicit `demo_mode` config flag is enabled.

### 10. Production deployment is incomplete

**Where:** `docker-compose.yml`, setup docs, and app startup flow.

**Problem:** Docker Compose starts infrastructure only; backend/frontend are not containerized as services.

**Impact:** New developers/operators must manually run backend/frontend, and production deployment is inconsistent.

**Recommended fix now:** Add backend and frontend services or a `compose.dev.yml` plus `compose.prod.yml` split.

## Features that can be added now

### Quick wins, low risk

1. **Real login page**
   - Replace auto-login with username/password form.
   - Keep demo quick-switch only behind demo mode.

2. **Evidence-safe file serving**
   - Add safe path validation helper.
   - Add unit tests for path traversal rejection.

3. **Audit log coverage**
   - Add helper and log all privileged state-changing operations.

4. **Frontend lint cleanup**
   - Remove unused imports and parameters.
   - Stabilize fetch callbacks with `useCallback`.

5. **`.env.example`**
   - Document `APP_ENV`, `DATABASE_URL`, `VMS_SECRET_KEY`, `CORS_ALLOWED_ORIGINS`, `KAFKA_BOOTSTRAP_SERVERS`, Qdrant URL, and frontend demo flags.

6. **Demo mode badge and guards**
   - Show an obvious banner when using demo credentials/data.
   - Disable random/demo data when demo mode is false.

### Medium effort, high value

1. **Alembic migrations**
   - Add user status fields, schema evolution, and migration history.

2. **Real face image search**
   - Extract uploaded image embedding using the existing face pipeline.
   - Return 422/501 if no face is detected or model is unavailable.

3. **Alert cooldown/deduplication**
   - Prevent repeated alerts for the same object/zone within a cooldown window.

4. **Camera credential vaulting**
   - Avoid storing RTSP/ONVIF credentials in plain text URLs.

5. **Backend integration test profile**
   - Add Docker-based PostgreSQL/Qdrant/Kafka test jobs.

6. **Evidence chain-of-custody**
   - Store hashes at capture/export time and log every download.

### Larger features to schedule later

1. **Map-based camera topology and route reconstruction**
   - Use real camera coordinates, adjacency graphs, and time windows.

2. **Multi-tenant agency/department support**
   - Partition cameras, users, logs, and exports by organization.

3. **Model observability dashboard**
   - Show per-model latency, failure rate, queue depth, and GPU memory.

4. **Incident workflow**
   - Convert alerts into cases with assignments, comments, evidence, and closure states.

5. **Object/person re-identification review queue**
   - Human-in-the-loop review for uncertain identity matches.

## Recommended next sprint plan

1. Secure file-serving and proxy endpoints.
2. Replace fake face search with real implementation or explicit `501`.
3. Add persisted user status fields and migrations.
4. Remove hardcoded frontend demo login from normal mode.
5. Clean lint warnings and add tests for the fixed security paths.
