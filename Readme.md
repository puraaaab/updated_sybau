# AI Surveillance & Video Management System (VMS)

## Technical Implementation Specification (Prototype v1.0)

---

# Project Overview

## Objective

Build an AI-powered Video Management System (VMS) capable of:

* Connecting to multiple CCTV cameras (RTSP/ONVIF/HLS/RTMP/WebRTC)
* Performing real-time object detection and tracking
* Detecting behavioral events
* Recognizing faces and license plates
* Performing semantic search across video history
* Providing a modern surveillance dashboard
* Recording original video for forensic evidence
* Supporting future scalability

**Important:** This is intended to be a production-quality prototype suitable for a capstone project or hackathon—not an attempt to replicate the full feature set of enterprise VMS platforms such as Milestone, Genetec, or Verkada.

---

# High-Level Architecture

```text
                     Cameras
        (RTSP | ONVIF | HLS | DVR | Bodycam)

                         │
                         ▼
              MediaMTX / GStreamer
                         │
                         ▼
               Stream Manager (FastAPI)
                         │
      ┌──────────────────┼──────────────────┐
      │                  │                  │
      ▼                  ▼                  ▼
   YOLO26m          Face Pipeline     Vehicle Pipeline
      │                  │                  │
      └──────────────┬───┴──────────────────┘
                     ▼
           Multi Object Tracking
                 (ByteTrack)
                     │
                     ▼
        Behavior & Event Detection
                     │
                     ▼
       Florence-2 (Selected Frames Only)
                     │
                     ▼
        Embeddings + Vector Index
                     │
       PostgreSQL + Qdrant + MinIO
                     │
                     ▼
        React Surveillance Dashboard
```

---

# Core Design Principles

The implementation should follow these principles:

* Modular architecture
* Event-driven pipeline
* AI modules remain independent
* Record original video continuously
* Analyze sampled frames rather than every frame
* Store metadata separately from video
* GPU-optimized inference
* Easy deployment with Docker Compose
* Future Kubernetes compatibility

---

# Technology Stack

| Layer            | Technology                                                   |
| ---------------- | ------------------------------------------------------------ |
| Backend          | FastAPI                                                      |
| Frontend         | React + Material UI                                          |
| Streaming        | MediaMTX                                                     |
| Video Processing | FFmpeg + GStreamer                                           |
| Detection        | Ultralytics YOLO26m                                          |
| Tracking         | ByteTrack                                                    |
| Face Detection   | SCRFD                                                        |
| Face Recognition | InsightFace (buffalo_l or buffalo_sc)                        |
| Vehicle Re-ID    | FastReID or TorchReID                                        |
| OCR              | PaddleOCR                                                    |
| Scene Captioning | Florence-2 Base                                              |
| Embeddings       | SigLIP 2 (or another modern vision-language embedding model) |
| Database         | PostgreSQL                                                   |
| Vector Search    | Qdrant                                                       |
| Object Storage   | MinIO                                                        |
| Messaging        | Kafka                                                        |
| Deployment       | Docker Compose (prototype)                                   |

---

# Phase 1 — Video Ingestion

## Goal

Support multiple camera sources.

### Supported Protocols

* RTSP
* RTMP
* HLS
* WebRTC
* DVR/NVR streams
* ONVIF discovery

### Components

* MediaMTX
* FFmpeg
* GStreamer
* ONVIF Python SDK

### Responsibilities

* Camera discovery
* Stream health monitoring
* Automatic reconnect
* Camera registration
* Multi-camera support

---

# Phase 2 — Object Detection

## Model

Ultralytics YOLO26m

Detect at minimum:

* Person
* Bicycle
* Car
* Motorcycle
* Bus
* Truck
* Backpack
* Handbag
* Suitcase
* Umbrella

Output should include:

```text
Object ID

Class

Confidence

Bounding Box

Timestamp

Camera ID
```

---

# Phase 3 — Multi-Object Tracking

Use:

**ByteTrack**

Do **not** use DeepSORT unless there is a compelling research reason.

Every object receives a persistent tracking ID.

Example:

```text
Person #17

Frame 1

Frame 2

Frame 3

...
```

Track metadata should include:

* Track ID
* Camera ID
* First appearance
* Last appearance
* Path history
* Speed
* Direction

---

# Phase 4 — Face Detection

Use:

SCRFD

Responsibilities:

* Detect faces
* Return face bounding boxes
* Associate faces with tracked persons

Output:

```text
Face Bounding Box

Confidence

Track ID
```

---

# Phase 5 — Face Recognition

Use:

InsightFace

Recommended model:

```
buffalo_l
```

Fallback:

```
buffalo_sc
```

Generate:

512-dimensional face embeddings.

Store:

* Track ID
* Face embedding
* Timestamp
* Camera ID

This enables:

* Face search
* Person re-identification
* Watchlists (future)

---

# Phase 6 — Vehicle Recognition

Pipeline:

```text
YOLO

↓

Vehicle Crop

↓

Vehicle Re-ID

↓

Vehicle Identity
```

Recommended models:

* FastReID
* TorchReID

Capabilities:

* Cross-camera vehicle tracking
* Vehicle history reconstruction

Example:

```text
Blue Sedan

↓

Camera 2

↓

Camera 6

↓

Camera 11
```

---

# Phase 7 — License Plate Recognition

Pipeline

```text
YOLO

↓

Vehicle

↓

Plate Detection

↓

OCR

↓

License Plate Number
```

OCR:

* PaddleOCR (preferred)
* EasyOCR (fallback)

Store:

* Plate number
* Timestamp
* Camera
* Vehicle ID

---

# Phase 8 — Crowd Density

Use person detections.

Calculate:

```text
Density =
Persons / Area
```

Generate alerts when density exceeds configurable thresholds.

Example:

```
Area = 100 sqm

Persons = 120

Density = 1.2
```

---

# Phase 9 — Behavior Detection

Do **not** train custom action-recognition models.

Use rule-based analytics built on tracked objects.

Supported events:

## Loitering

```
Person remains inside a zone
for more than X minutes.
```

---

## Running

Estimate speed from tracking.

If:

```
Speed > Threshold
```

Generate alert.

---

## Abandoned Object

Logic:

```text
Bag detected

↓

Owner leaves

↓

Bag remains

↓

Alert
```

---

## Restricted Area

Polygon Zone

↓

Person enters

↓

Alert

---

## Wrong Direction

Track vector

↓

Compare against allowed direction

↓

Alert

---

## Vehicle in Pedestrian Zone

Vehicle enters restricted polygon.

↓

Alert

---

# Phase 10 — Florence-2 Scene Understanding

Do **not** process every frame.

Run Florence-2:

* Every 5 seconds
* When a new tracked object appears
* On user-requested forensic analysis

Example output:

```
Two children holding a red balloon.

Woman sitting on a bench.

Three bicycles parked nearby.
```

Store captions.

Generate embeddings.

---

# Phase 11 — Semantic Search

Use:

Qdrant

Store embeddings for:

* Captions
* Objects
* Faces
* Vehicles

Queries should support:

```
Red Backpack

Blue Umbrella

Yellow Jacket

Dog

Child Crying

Red Car

Person with suitcase
```

Return:

* Timestamp
* Camera
* Preview image
* Jump-to-video link

---

# Phase 12 — Database Design

Use PostgreSQL.

Suggested tables:

```
Users

Cameras

Frames

Objects

Tracks

Faces

Vehicles

Alerts

Events

Audit Logs

Search History
```

---

# Phase 13 — Object Storage

Use MinIO.

Store:

## Video

Continuous recordings.

## Images

Only when needed:

* Alerts
* Evidence
* Search thumbnails

Metadata remains inside PostgreSQL.

---

# Phase 14 — Event Messaging

Use Kafka.

Suggested event flow:

```text
Frame

↓

YOLO Detection

↓

Tracking

↓

Behavior Engine

↓

Florence

↓

Embedding

↓

Alerts

↓

Dashboard
```

Each service should publish and subscribe independently.

---

# Phase 15 — Dashboard

React + Material UI.

Pages:

## Live View

* Multi-camera grid
* Camera health
* FPS
* Status

---

## Alerts

Display:

* Loitering
* Restricted Area
* Crowd Density
* Person of Interest
* Vehicle Events
* License Plate Events

---

## Search

Natural language search.

Example:

```
Red Backpack
```

Returns:

```
Camera

Timestamp

Thumbnail

Jump to recording
```

---

## Timeline

Per-camera playback.

Features:

* Scrollable timeline
* Seek
* Event markers

---

## Heatmap

Display crowd activity over time.

---

## Face Search

Upload face image.

Return:

* Matches
* Cameras
* Timestamps

---

# Storage Strategy (Critical)

**Do NOT save screenshots continuously.**

Instead:

## Record original video continuously.

Run AI inference on sampled frames.

Recommended sampling:

* 2 FPS
* Adaptive sampling based on motion
* Event-triggered high-frequency inference

Store separately:

### Original Video

For evidence.

### AI Metadata

* Detections
* Tracks
* Captions
* OCR
* Embeddings
* Alerts

### Event Images

Only when required.

Example:

```
Search:

Red Backpack

↓

Result

Camera 7

14:23:11

↓

Jump directly to recorded video
```

This approach is significantly more storage-efficient and aligns with real-world surveillance systems.

---

# Suggested Repository Structure

```text
backend/
    api/
    auth/
    database/
    stream_manager/
    ai/
        detection/
        tracking/
        face/
        vehicle/
        ocr/
        behavior/
        embeddings/
    workers/
    messaging/

frontend/
    dashboard/

docker/
    postgres/
    qdrant/
    kafka/
    minio/
    mediamtx/

storage/

configs/

scripts/

docs/
```

---

# Development Roadmap

## Week 1

* MediaMTX integration
* Camera ingestion
* Live dashboard
* YOLO26m object detection

---

## Week 2

* ByteTrack
* PostgreSQL
* Alert engine
* Restricted zones
* Crowd counting
* Loitering detection

---

## Week 3

* SCRFD
* InsightFace
* PaddleOCR
* Searchable event history
* Vehicle tracking

---

## Week 4

* Florence-2 integration
* Embedding generation
* Qdrant semantic search
* Forensic export
* Dashboard polishing
* Performance optimization

---

# Future Enhancements (Not Required for Prototype)

* Multi-node deployment
* Kubernetes
* Distributed inference
* Active Directory authentication
* Watchlists
* Mobile application
* Push notifications
* Audio analytics
* Weapon detection
* Fire and smoke detection
* Cross-site federation
* Federated camera management
* Role-based access control (RBAC)
* Audit compliance reporting
* ONVIF PTZ camera control

---

# Final Goal

The completed prototype should demonstrate an end-to-end AI surveillance workflow:

1. Ingest live camera streams.
2. Record original video continuously.
3. Detect and track people, vehicles, and objects.
4. Recognize faces and license plates.
5. Detect configurable behavioral events.
6. Generate scene captions selectively using Florence-2.
7. Store structured metadata separately from video.
8. Enable semantic search across historical footage.
9. Provide a responsive React dashboard for live monitoring, playback, alerts, and forensic investigation.
10. Maintain a modular architecture that can be extended toward a production-grade surveillance platform.
