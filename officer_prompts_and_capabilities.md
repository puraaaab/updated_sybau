# 🛡️ Copilot AI: Officer Prompts & Tactical Capabilities Guide

This document is the official field manual of **Natural Language Prompts** used by Police Officers, Control Room Dispatchers, and Forensic Investigators in the **Sybau VMS Pro (PS-11)** surveillance system.

It outlines:
1. **Prompts Working Right Now** (Live in current version)
2. **Next-Gen Capabilities** (Advanced capabilities ready to be activated)
3. **Under-the-Hood AI Pipeline** for each investigation

---

## 📑 Table of Contents
1. [🚨 Criminal Escape & Suspect Trajectory](#1--criminal-escape--suspect-trajectory)
2. [👶 Missing Person & Child Search](#2--missing-person--child-search)
3. [🚗 Vehicle, ANPR & Number Plate Tracking](#3--vehicle-anpr--number-plate-tracking)
4. [👥 Crowd Surge, Riots & Stampede Prevention](#4--crowd-surge-riots--stampede-prevention)
5. [🛑 Perimeter Breach & Night Patrol](#5--perimeter-breach--night-patrol)
6. [🏍️ Accomplice, Gang & Convoy Co-Occurrence](#6--accomplice-gang--convoy-co-occurrence)
7. [👮 Officer Field Safety & BWC (Body Worn Camera)](#7--officer-field-safety--bwc-body-worn-camera)
8. [⚖️ Evidence Export & Court-Admissible Audit Trail](#8--evidence-export--court-admissible-audit-trail)
9. [🔥 Fire, Smoke & Abandoned Object Detection](#9--fire-smoke--abandoned-object-detection) — **NEW**
10. [🕵️ Watchlist, OSINT & Cross-Agency Matching](#10--watchlist-osint--cross-agency-matching) — **NEW**
11. [🎙️ Audio Threat Detection](#11--audio-threat-detection) — **NEW**
12. [🌐 Multilingual Query & Reporting](#12--multilingual-query--reporting) — **NEW**
13. [🩺 Camera Network Health & Coverage](#13--camera-network-health--coverage) — **NEW**

---

# 1. 🚨 Criminal Escape & Suspect Trajectory

### Prompt 1.1: Physical Description + Multi-Camera Trajectory
```text
"Show me a suspect wearing a black hoodie and blue jeans spotted near Main Market between 2:00 PM and 3:30 PM"
```
* **Officer Goal**: Trace an escaped robbery suspect across public street cameras.
* **Status**: ✅ **Working Right Now**
* **System Action**:
  * Vector search parses `"black hoodie, blue jeans"` using 1024-D vision-language embeddings.
  * Filters camera feeds located in `Main Market` within `14:00` to `15:30`.
  * Generates chronological trajectory timeline cards with confidence score and snapshot previews.

---

### Prompt 1.2: Cross-Camera Multi-Hop Route Plotting
```text
"Trace the movement of the red motorcycle that crossed Traffic Signal 4 at 11:15 AM"
```
* **Officer Goal**: Identify which roads the suspect took after crossing a known checkpoint.
* **Status**: ✅ **Working Right Now**
* **System Action**:
  * Extracts vehicle trajectory track across downstream cameras.
  * Plots route on the **Suspect GIS Map & Camera Topology Canvas** with transit distance and travel time.

---

### Prompt 1.3: Predictive Next-Hop Escape Intersection
```text
"Predict the next 3 probable intersections this suspect will reach based on current speed and heading"
```
* **Officer Goal**: Dispatch PCR vans to intercept the suspect before they reach highway toll gates.
* **Status**: ⚡ **Next-Gen Capability (Ready to Enable)**
* **How We Make It Happen**:
  * Computes velocity vector from last two camera sightings $(\Delta \text{distance} / \Delta \text{time})$.
  * Queries Camera Topology Graph to find downstream connected nodes within a 5-minute travel radius.
  * Automatically highlights escape route choke-points in red on the Live Topology Map.

---

# 2. 👶 Missing Person & Child Search

### Prompt 2.1: Visual Clothing & Age Group Search
```text
"Find an 8-year-old child in a yellow t-shirt and blue shorts seen in the last 2 hours"
```
* **Officer Goal**: Locate a missing child reported in a crowded public festival or shopping complex.
* **Status**: ✅ **Working Right Now**
* **System Action**:
  * Natural language caption index scans all camera scene captions for `child`, `yellow shirt`, `blue shorts`.
  * Returns instantaneous thumbnail gallery sorted by newest detection.

---

### Prompt 2.2: Photo-Based Re-ID Face Matching
```text
[Officer uploads photograph] "Search all railway and bus station cameras for this missing person"
```
* **Officer Goal**: Find person from a parent's uploaded mobile photo across transit hubs.
* **Status**: ✅ **Working Right Now**
* **System Action**:
  * Extracts 512-D ArcFace biometric embedding from uploaded image.
  * Executes sub-50ms cosine similarity query in Qdrant `face_embeddings` collection.
  * Flags matching camera frames with bounding box and timestamp.

---

### Prompt 2.3: Reverse Direction & Last Seen Beacon
```text
"Where was this person last seen on camera before disappearing from the surveillance grid?"
```
* **Officer Goal**: Determine the exact blind spot or building entrance where the subject was last recorded.
* **Status**: ⚡ **Next-Gen Capability (Ready to Enable)**
* **How We Make It Happen**:
  * Filters all positive Re-ID matches and extracts the maximum timestamp $\max(t)$.
  * Automatically pulls high-resolution uncompressed 30-second video clip from NVR storage and displays camera coordinates on GIS map.

---

# 3. 🚗 Vehicle, ANPR & Number Plate Tracking

### Prompt 3.1: Partial Number Plate & Vehicle Class
```text
"Find all white SUVs with number plate ending in 8492 spotted today"
```
* **Officer Goal**: Locate hit-and-run vehicle with incomplete witness information.
* **Status**: ✅ **Working Right Now**
* **System Action**:
  * Combines EasyOCR / PaddleOCR text regex with YOLO vehicle class filter (`car`, `suv`, `truck`).
  * Returns exact license plate crops, plate string match, and camera location.

---

### Prompt 3.2: Fake / Tampered Plate Detection
```text
"Alert me if any vehicle with plate DL-01-AB-1234 is detected on a vehicle that is not a white sedan"
```
* **Officer Goal**: Detect stolen plates mounted on different vehicle models (plate cloning).
* **Status**: ⚡ **Next-Gen Capability (Ready to Enable)**
* **How We Make It Happen**:
  * Cross-references OCR plate string with vehicle body classification in PostgreSQL database.
  * If OCR plate is registered to a Sedan but YOLO detects a Truck, triggers **Critical Priority Stolen/Cloned Plate Alert**.

---

### Prompt 3.3: Time-Specific Vehicle Search
```text
"Can you get me where you have spotted buses after 10 AM?"
```
* **Officer Goal**: Audit public bus movements or restricted bus lane violations.
* **Status**: ✅ **Working Right Now**
* **System Action**:
  * Parses clock time (`time_start = 10:00:00 AM`) and target class (`bus`).
  * Returns chronological timeline cards of every bus detected across all 22 cameras.

---

### Prompt 3.4: Stolen Vehicle Database Cross-Check *(NEW)*
```text
"Flag any vehicle plate detected that matches today's stolen vehicle list"
```
* **Officer Goal**: Automatically catch a stolen vehicle the moment it passes any camera, without an officer having to search manually.
* **Status**: ⚡ **Next-Gen Capability (Ready to Enable)**
* **How We Make It Happen**:
  * Runs every OCR-extracted plate string against a synced stolen/blacklisted vehicle table (state CCTNS/e-Challan feed).
  * On match, fires a **Hot-List Vehicle Alert** with live camera feed pop-up and last-known-heading vector.

---

# 4. 👥 Crowd Surge, Riots & Stampede Prevention

### Prompt 4.1: Density & Crowd Overcrowding Alert
```text
"Which cameras are showing crowd count higher than 50 people right now?"
```
* **Officer Goal**: Prevent stampedes at railway platforms, temples, and rally grounds.
* **Status**: ✅ **Working Right Now**
* **System Action**:
  * Queries real-time YOLO head-count metadata from active camera streams.
  * Highlights overloaded camera cards in red with live count overlay.

---

### Prompt 4.2: Sudden Running / Stampede Dispersion
```text
"Show me cameras where sudden running or crowd dispersion happened in the last 15 minutes"
```
* **Officer Goal**: Detect riots, panic, or violent clashes before 112 emergency calls arrive.
* **Status**: ⚡ **Next-Gen Capability (Ready to Enable)**
* **How We Make It Happen**:
  * Measures optical flow vector divergence and average track velocity across bounding boxes.
  * If average velocity exceeds $3.5\text{ m/s}$ in divergent directions, fires **Crowd Panic Anomaly Alert**.

---

# 5. 🛑 Perimeter Breach & Night Patrol

### Prompt 5.1: Restricted Zone Intrusion
```text
"Show all unauthorized entries in the Server Room after 8:00 PM"
```
* **Officer Goal**: Audit security breaches in high-security government facilities.
* **Status**: ✅ **Working Right Now**
* **System Action**:
  * Checks polygon ROI (Region of Interest) geofencing rules and timestamp boundaries.
  * Displays thumbnail clips of intruders with timestamps.

---

### Prompt 5.2: Loitering & Suspicious Presence
```text
"Has anyone loitered near the ATM camera for more than 5 minutes?"
```
* **Officer Goal**: Prevent ATM skimming, robbery, or vandalism during night shifts.
* **Status**: ✅ **Working Right Now**
* **System Action**:
  * Tracks individual Person Re-ID track duration inside camera frame.
  * If $\text{dwell\_time} \ge 300\text{ seconds}$, generates a **Loitering Alert**.

---

### Prompt 5.3: Camera Tampering & Blind Spot Detection
```text
"Are any cameras currently obstructed, spray-painted, or defocused?"
```
* **Officer Goal**: Identify vandalized or disabled cameras instantly.
* **Status**: ⚡ **Next-Gen Capability (Ready to Enable)**
* **How We Make It Happen**:
  * Edge/Laplacian variance check on incoming decoded GPU frames.
  * If image variance drops below threshold or scene is solid color, fires **Camera Health Anomaly Alert**.

---

# 6. 🏍️ Accomplice, Gang & Convoy Co-Occurrence

### Prompt 6.1: Shadow Vehicle / Convoy Tracking
```text
"Identify any vehicle that followed suspect car HR-26-DK-9901 across at least 3 consecutive cameras"
```
* **Officer Goal**: Bust organized crime syndicates where getaway cars escort a target vehicle.
* **Status**: ⚡ **Next-Gen Capability (Ready to Enable)**
* **How We Make It Happen**:
  * Runs Spatio-Temporal Co-Occurrence query on `vehicle_journey_events`.
  * Finds vehicle pairs $(V_1, V_2)$ where $|t_1 - t_2| \le 30\text{ seconds}$ across $N \ge 3$ distinct cameras.
  * Outputs **Confirmed Convoy Candidate** card with synchronized side-by-side video clips.

---

### Prompt 6.2: Gang Convergence Detection
```text
"Did a group of more than 4 individuals gather together after arriving on separate two-wheelers?"
```
* **Officer Goal**: Preempt planned group violence or illicit street gatherings.
* **Status**: ⚡ **Next-Gen Capability (Ready to Enable)**
* **How We Make It Happen**:
  * Correlates two-wheeler dismount events with multi-person spatial clustering within a 10-meter radius.

---

# 7. 👮 Officer Field Safety & BWC (Body Worn Camera)

### Prompt 7.1: Fallen Officer / Man-Down Detection
```text
"Are there any officer-down or horizontal posture alerts from active BWC feeds?"
```
* **Officer Goal**: Immediate emergency backup dispatch when an on-duty officer is attacked or collapses.
* **Status**: ⚡ **Next-Gen Capability (Ready to Enable)**
* **How We Make It Happen**:
  * YOLOv8-Pose keypoint estimation detects horizontal torso axis $(\theta \ge 70^\circ)$ sustained for $>10\text{ seconds}$.
  * Triggers priority SOS alarm with GPS coordinates on the command console.

---

### Prompt 7.2: Gun / Weapon Brandishing in Stream
```text
"Show me any instances where a firearm or bladed weapon was detected in the last 1 hour"
```
* **Officer Goal**: Rapid armed-response unit dispatch.
* **Status**: ✅ **Working Right Now**
* **System Action**:
  * Scans YOLO weapon detection classes (`knife`, `gun`, `weapon`) with high confidence threshold $(c \ge 0.85)$.
  * Instantly pops up the live camera stream in full screen.

---

### Prompt 7.3: Officer Duress Word / Panic Trigger *(NEW)*
```text
"Alert the control room if Officer Patel's BWC picks up the duress code word 'Falcon'"
```
* **Officer Goal**: Let a plainclothes or undercover officer silently signal distress without reaching for a radio.
* **Status**: ⚡ **Next-Gen Capability (Ready to Enable)**
* **How We Make It Happen**:
  * Runs a lightweight on-device speech-to-text pass on the BWC audio stream, matched against a per-officer configurable keyword list.
  * On match, raises a **Silent Duress Alert** tagged with officer ID and last GPS fix — no visible/audible confirmation on the officer's device.

---

# 8. ⚖️ Evidence Export & Court-Admissible Audit Trail

### Prompt 8.1: Complete Evidence Dossier Export
```text
"Export a tamper-proof evidence package for Suspect-04 including video clips, trajectory map, and SHA-256 integrity hash"
```
* **Officer Goal**: Produce verifiable electronic evidence compliant with the Indian Evidence Act / Section 65B.
* **Status**: ✅ **Working Right Now**
* **System Action**:
  * Packages all positive video clips, trajectory timeline, and officer audit logs into a `.zip` dossier.
  * Signs package with cryptographic SHA-256 checksum and digital watermark.

---

### Prompt 8.2: Automated e-FIR / Challan Generation
```text
"Generate an official e-Challan report for red light violation by vehicle UP-16-Z-1002 with snapshot proof"
```
* **Officer Goal**: Automate administrative paperwork and traffic fine notices.
* **Status**: ✅ **Working Right Now**
* **System Action**:
  * Extracts violation timestamp, camera name, GPS location, and zoomed crop of number plate.
  * Formats into a court-ready PDF with unique Challan Reference ID.

---

### Prompt 8.3: Chain-of-Custody Access Log *(NEW)*
```text
"Show me everyone who viewed, downloaded, or exported footage related to Case-1042"
```
* **Officer Goal**: Prove evidence integrity in court by showing exactly who touched the footage and when.
* **Status**: ✅ **Working Right Now**
* **System Action**:
  * Queries the immutable `access_audit_log` table for every read/export event tagged with the case ID.
  * Returns officer name, badge ID, timestamp, and action type (`viewed`, `downloaded`, `exported`) as a signed PDF log.

---

# 9. 🔥 Fire, Smoke & Abandoned Object Detection *(NEW SECTION)*

### Prompt 9.1: Fire & Smoke Early Warning
```text
"Alert me immediately if smoke or open flame is detected on any camera"
```
* **Officer Goal**: Catch a fire in a crowded market or godown before it spreads, faster than a manual smoke detector network.
* **Status**: ⚡ **Next-Gen Capability (Ready to Enable)**
* **How We Make It Happen**:
  * Runs a lightweight fire/smoke classification head alongside the main YOLO pipeline on sampled frames.
  * On sustained positive detection ($\ge 3$ consecutive frames), fires a **Fire/Smoke Anomaly Alert** with camera location and fire-department dispatch shortcut.

---

### Prompt 9.2: Unattended Bag / Abandoned Object Alert
```text
"Flag any bag or package left unattended for more than 3 minutes at the station entrance"
```
* **Officer Goal**: Detect potential IEDs or theft-bait bags in high-footfall public transit areas.
* **Status**: ⚡ **Next-Gen Capability (Ready to Enable)**
* **How We Make It Happen**:
  * Tracks static object detections (`bag`, `backpack`, `box`) whose owner (nearest person track) has left the frame radius.
  * If object remains stationary beyond a configurable dwell threshold with no associated person nearby, raises an **Unattended Object Alert**.

---

# 10. 🕵️ Watchlist, OSINT & Cross-Agency Matching *(NEW SECTION)*

### Prompt 10.1: Wanted Persons Watchlist Match
```text
"Check if anyone on today's wanted list has appeared on any camera in the last 6 hours"
```
* **Officer Goal**: Passively catch known offenders without an officer having to manually search for each name.
* **Status**: ⚡ **Next-Gen Capability (Ready to Enable)**
* **How We Make It Happen**:
  * Continuously runs face embeddings from all live streams against a periodically synced watchlist collection in Qdrant.
  * On a high-confidence match ($\ge 0.9$ cosine similarity), raises a **Watchlist Hit Alert** requiring human verification before any action is logged.

---

### Prompt 10.2: Cross-Reference with State Crime Records
```text
"Has this suspect's face matched any record in the state crime database?"
```
* **Officer Goal**: Enrich a live camera hit with prior criminal history for situational awareness before approach.
* **Status**: ⚡ **Next-Gen Capability (Ready to Enable, pending inter-agency API access)**
* **How We Make It Happen**:
  * Sends the matched face embedding/ID to the state CCTNS record API over an authenticated, audit-logged channel.
  * Displays prior case references (if any) alongside the live camera hit — read-only, never auto-actioned.

---

# 11. 🎙️ Audio Threat Detection *(NEW SECTION)*

### Prompt 11.1: Gunshot / Scream Acoustic Alert
```text
"Alert me if a gunshot or scream is picked up by any camera microphone"
```
* **Officer Goal**: Catch violent incidents in blind spots or low-light areas where video alone misses the event.
* **Status**: ⚡ **Next-Gen Capability (Ready to Enable, requires mic-equipped cameras)**
* **How We Make It Happen**:
  * Runs a lightweight audio event classifier on microphone-enabled camera streams for `gunshot`, `scream`, `glass-break` classes.
  * On detection above confidence threshold, correlates with the nearest camera's video buffer and raises an **Acoustic Threat Alert**.

---

# 12. 🌐 Multilingual Query & Reporting *(NEW SECTION)*

### Prompt 12.1: Query in Gujarati or Hindi
```text
"પીળા શર્ટમાં એક છોકરો છેલ્લા 2 કલાકમાં ક્યાં દેખાયો?" (Gujarati: "Where was a boy in a yellow shirt seen in the last 2 hours?")
```
* **Officer Goal**: Let field officers and local station staff query the system in their working language instead of English-only prompts.
* **Status**: ⚡ **Next-Gen Capability (Ready to Enable)**
* **How We Make It Happen**:
  * Routes the query through a translation pre-processing step before the existing QueryIntentParser, preserving entity terms (colors, times, locations).
  * Renders alert cards and PDF reports bilingually (English + officer's chosen language) for local station use.

---

# 13. 🩺 Camera Network Health & Coverage *(NEW SECTION)*

### Prompt 13.1: Live Network Uptime Dashboard
```text
"Which cameras are currently offline or dropping frames?"
```
* **Officer Goal**: Give the control room a single glance at surveillance coverage gaps, distinct from tampering detection.
* **Status**: ✅ **Working Right Now**
* **System Action**:
  * Polls RTSP/MediaMTX stream heartbeat and frame-rate stability for every registered camera.
  * Returns a status grid (`online`, `degraded`, `offline`) with last-seen timestamp per camera.

---

## 🚀 Summary Matrix of Capabilities

| Operational Capability | Natural Language Prompt Example | Status | Underlying Technology |
| :--- | :--- | :---: | :--- |
| **Suspect Physical Search** | *"Red shirt, blue jeans near gate"* | ✅ Live | Qdrant Vector Search (1024-D) |
| **Clock-Time Filter** | *"Spotted buses after 10 AM"* | ✅ Live | QueryIntentParser + SQL Filter |
| **Face Re-ID Match** | *[Upload image] "Find this person"* | ✅ Live | ArcFace (512-D) + Cosine Distance |
| **ANPR / Vehicle OCR** | *"White SUV plate ending in 8492"* | ✅ Live | PaddleOCR + YOLO Vehicle Filter |
| **Route GIS Mapping** | *"Trace route of black motorbike"* | ✅ Live | Leaflet / Google GIS + Trajectory |
| **Evidence Dossier** | *"Export SHA-256 evidence for Suspect-04"* | ✅ Live | Forensic Evidence Ledger + Hash |
| **Chain-of-Custody Log** *(NEW)* | *"Who accessed footage for Case-1042?"* | ✅ Live | Immutable Access Audit Table |
| **Camera Network Health** *(NEW)* | *"Which cameras are offline?"* | ✅ Live | RTSP/MediaMTX Heartbeat Polling |
| **Predictive Escape Route** | *"Predict next 3 intersections"* | ⚡ Ready | Topology Graph Velocity Vector |
| **Convoy / Gang Co-Occurrence**| *"Vehicle following target car for 3 cams"*| ⚡ Ready | Spatio-Temporal Cluster Matching |
| **Plate Cloning Detection** | *"Plate on vehicle of wrong body type"* | ⚡ Ready | OCR vs Model Metadata Cross-Check |
| **Stolen Vehicle Cross-Check** *(NEW)* | *"Flag any plate matching today's stolen list"* | ⚡ Ready | OCR vs Hot-List DB Join |
| **Panic / Stampede Divergence**| *"Sudden running in last 15 min"* | ⚡ Ready | Optical Flow Dispersion Vector |
| **Officer-Down Detection** | *"Any man-down alerts from BWC?"* | ⚡ Ready | YOLOv8-Pose Keypoint Estimation |
| **Officer Duress Word** *(NEW)* | *"Alert on duress code word 'Falcon'"* | ⚡ Ready | On-Device Speech-to-Text Match |
| **Fire / Smoke Detection** *(NEW)* | *"Alert on smoke or open flame"* | ⚡ Ready | Fire/Smoke Classification Head |
| **Abandoned Object Detection** *(NEW)* | *"Flag unattended bag for 3+ min"* | ⚡ Ready | Static Object + Owner-Track Correlation |
| **Watchlist Face Match** *(NEW)* | *"Match today's wanted list to camera feeds"* | ⚡ Ready | Continuous Qdrant Face Match |
| **Cross-Agency Record Check** *(NEW)* | *"Match suspect to state crime database"* | ⚡ Ready | CCTNS API Cross-Reference |
| **Acoustic Threat Detection** *(NEW)* | *"Alert on gunshot or scream audio"* | ⚡ Ready | Audio Event Classifier |
| **Multilingual Query** *(NEW)* | *"Query in Gujarati / Hindi"* | ⚡ Ready | Translation Pre-Processor |

---

## 📝 Change Log
* **v2 (this version)**: Added Sections 9–13 (Fire/Smoke & Abandoned Object, Watchlist/OSINT/Cross-Agency, Audio Threat Detection, Multilingual Query, Camera Network Health), plus Prompts 3.4 (Stolen Vehicle Cross-Check), 7.3 (Officer Duress Word), and 8.3 (Chain-of-Custody Access Log). All additions follow the existing Officer Goal → Status → System Action format and are marked ⚡ Next-Gen unless noted otherwise.