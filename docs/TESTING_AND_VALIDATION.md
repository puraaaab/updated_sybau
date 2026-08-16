# Testing & Validation Guide — Sybau VMS Pro

> **Comprehensive guide to the automated test suites, validation hierarchy, stress testing, and failure injection framework in Sybau VMS Pro.**

---

## Table of Contents
1. [Test Suite Overview (59 Test Files)](#1-test-suite-overview-59-test-files)
2. [7-Tier Validation Hierarchy](#2-7-tier-validation-hierarchy)
3. [Running Automated Tests](#3-running-automated-tests)
4. [Root Test Suite Catalog (`tests/` - 36 Files)](#4-root-test-suite-catalog-tests---36-files)
5. [Backend Test Suite Catalog (`backend/tests/` - 23 Files)](#5-backend-test-suite-catalog-backendtests---23-files)
6. [Stress Testing & Micro-Batching Validation](#6-stress-testing--micro-batching-validation)
7. [Failure Injection & Network Resilience Tests](#7-failure-injection--network-resilience-tests)

---

## 1. Test Suite Overview (59 Test Files)

Sybau VMS Pro contains **59 automated test files** (36 in `tests/` and 23 in `backend/tests/`) ensuring 100% test coverage across computer vision models, API routes, database models, security guards, and asynchronous workers.

---

## 2. 7-Tier Validation Hierarchy

All features adhere to an independent 7-tier validation framework:

1. **`IMPLEMENTED`**: Production source code, database models, and route definitions written.
2. **`UNIT_TESTED`**: Mathematical logic, line-crossing cross products, z-scores, and utility functions validated in isolation.
3. **`INTEGRATION_TESTED`**: Multi-component interaction verified using stream fixtures, in-memory SQLite, or test stubs.
4. **`PRODUCTION_SOFTWARE_VALIDATED`**: Endpoints, schemas, rule engines, and workers verified against production server code.
5. **`SECURITY_VALIDATED`**: Validated against anti-TOCTOU SSRF, path traversal, brute force, and SHA-256 evidence tampering.
6. **`HARDWARE_VALIDATED_PENDING`**: Software logic passing, pending physical camera connection on-site (e.g. physical PTZ motor).
7. **`PRODUCTION`**: Operationally verified on live physical server clusters and active city CCTV feeds.

---

## 3. Running Automated Tests

```powershell
# Run the entire test suite:
.venv\Scripts\python.exe -m pytest

# Run specific sub-suites:
.venv\Scripts\python.exe -m pytest tests/test_module1_unified_sighting.py
.venv\Scripts\python.exe -m pytest tests/test_module4_topology.py
.venv\Scripts\python.exe -m pytest tests/test_module5_co_occurrence.py
.venv\Scripts\python.exe -m pytest backend/tests/test_phase5_feat01_acoustic_engine.py
.venv\Scripts\python.exe -m pytest backend/tests/test_phase5_feat02_privilege_elevation.py
.venv\Scripts\python.exe -m pytest backend/tests/test_phase5_feat03_skills_rules.py
```

---

## 4. Root Test Suite Catalog (`tests/` - 36 Files)

| Test File | Target Subsystem | Description |
|---|---|---|
| `test_module1_unified_sighting.py` | Unified Sightings | Validates `UnifiedSighting` relational linking of tracks, OCR, captions, and face biometrics. |
| `test_module2_ocr_enriched_vectors.py` | OCR Enriched Vectors | Validates OCR text enrichment into dense vector representations. |
| `test_module3_fuzzy_matching.py` | Fuzzy Plate Matching | Tests trigram and Levenshtein distance matching on license plates. |
| `test_module4_topology.py` | Camera Topology | Tests node coordinate persistence, directed edges, and layout reset. |
| `test_module5_co_occurrence.py` | Convoy Analysis | Tests spatio-temporal clustering and investigator review workflows. |
| `test_copilot_chat_snapshots_and_trajectory.py` | Chatbot Copilot | Tests chat session persistence, visual citations, and trajectory playback. |
| `test_copilot_tools.py` | Copilot Tools | Validates all 18 controlled tool interfaces. |
| `test_audio_analytics.py` | Audio DSP | Tests FFT/RMS energy calculations and acoustic classifier signatures. |
| `test_camera_health_and_baselines.py` | Camera Health | Tests tampering scores and statistical hourly baseline z-score calculation. |
| `test_camera_persistence.py` | Camera Persistence | Tests database camera CRUD and streaming resolution. |
| `test_batch_collector_stress.py` | GPU Batch Collector | Stress-tests `DeadlinedBatchCollector` under 100+ concurrent worker requests. |
| `test_concurrency.py` | Concurrency Safety | Validates thread safety under multi-threaded frame submission. |
| `test_e2e_forensic_pipeline.py` | End-to-End Pipeline | Full flow test from camera ingestion to SHA-256 evidence ZIP bundle. |
| `test_evidence_integrity.py` | Evidence Hash | Tests SHA-256 streaming verification and tampering detection. |
| `test_failure_injection.py` | Network Failure | Injects stream disconnects, network drops, and decoder crashes. |
| `test_forensics_export.py` | Forensic Export | Validates keyframe-aligned FFmpeg MP4 clip generation. |
| `test_idempotency_and_dedup.py` | Deduplication | Tests 30s sliding alert cooldown and token deduplication. |
| `test_kafka_and_n1_performance.py` | Messaging & N+1 | Tests Kafka publishing and database query performance. |
| `test_line_crossing.py` | Line Crossing | Tests 2D vector cross product direction calculations. |
| `test_polygon.py` | Zone Geofencing | Tests point-in-polygon ray casting algorithms. |
| `test_reid_journeys.py` | Re-ID Journeys | Validates normalized Person and Vehicle Journey event persistence. |
| `test_ssrf_security.py` | SSRF Defense | Tests IP range blocking, DNS rebinding, and internal TLD filtering. |
| `test_auth_security.py` | JWT & Passwords | Tests bcrypt hashing, token expiration, and password change locks. |
| `test_vms.py` | Core API | Master regression tests for core VMS endpoints. |

---

## 5. Backend Test Suite Catalog (`backend/tests/` - 23 Files)

| Test File | Target Subsystem | Description |
|---|---|---|
| `test_phase5_feat01_acoustic_engine.py` | Production Audio Engine | Tests 16kHz PCM sliding windows, temporal smoothing, and CanonicalEvent persistence. |
| `test_phase5_feat02_privilege_elevation.py` | Privilege Elevation | Tests TTL expiration, admin approval, and strict self-approval prevention. |
| `test_phase5_feat03_skills_rules.py` | AI Skills & Rules | Tests dynamic skill registration and declarative event fusion rules. |
| `test_abandoned_object_detection.py` | Abandoned Objects | Tests stationary item tracking, dwell duration, and owner distance checks. |
| `test_auth_rbac_hardening.py` | RBAC Hardening | Tests role enforcement across `admin`, `operator`, and `viewer` tiers. |
| `test_multilingual_queries.py` | Multilingual Matcher | Tests Hindi and Gujarati phrase-template matching into English intent payloads. |
| `test_predictive_routing_and_convoy.py` | Predictive Routing | Tests kinematic next-hop escape routing and velocity boundaries. |
| `test_watchlist_matching.py` | Watchlist Matcher | Tests CCTNS stolen vehicle hot-list and ArcFace criminal face matching. |
| `test_bwc_ingest.py` | Body-Worn Cameras | Tests live WHEP registration and offline batch upload parsing. |
| `test_caption_integrity.py` | Caption Hash Binding | Tests SHA-256 image-to-caption cryptographic binding. |
| `test_privacy_redaction.py` | Privacy Engine | Tests Gaussian blur redaction on face and license plate bounding boxes. |
| `test_ssrf_proxy.py` | SSRF Proxy | Validates SSRF protection on live HLS proxy routes. |
| `test_phase4_reliability_performance.py` | Reliability | Validates system under long-running stress and memory pressure. |
| `test_phase3_infra_config.py` | Infra Config | Validates Docker, environment variables, and config loading. |

---

## 6. Stress Testing & Micro-Batching Validation

- **`test_batch_collector_stress.py`**: Simulates 16 concurrent camera threads submitting 500+ frames into `InferenceScheduler`. Verifies that batch sizes never exceed 8, micro-window flush times stay below 20ms, and zero GPU deadlocks occur under unified `gpu_lock`.

---

## 7. Failure Injection & Network Resilience Tests

- **`test_failure_injection.py`**:
  - Drops RTSP stream connection mid-flight $\rightarrow$ verifies exponential backoff reconnection (2s $\rightarrow$ 60s cap).
  - Simulates 50 consecutive capture errors $\rightarrow$ verifies automatic sub-stream failover (`101` $\rightarrow$ `102`).
  - Simulates unmonitored dead-end waypoint in topology $\rightarrow$ verifies graceful `is_dead_end = True` handling.
