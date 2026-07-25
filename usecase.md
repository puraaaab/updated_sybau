Think of PS_11 as **"Google Maps + AI + CCTV"** for police. Instead of humans constantly watching hundreds of camera feeds, the AI watches everything and only alerts the operator when something important happens.

Here are detailed real-life scenarios where it would be used.

---

# Use Case 1: A Criminal Escapes After Robbery

### Situation

A jewellery shop is robbed at **2:15 PM**.

The suspect is wearing

* Black jacket
* Blue jeans
* Black helmet

He escapes on a bike.

---

### Current Method

Police have to

* Visit nearby shops
* Collect CCTV footage
* Copy videos to pen drives
* Watch every video manually
* Try to identify where the suspect went

This can take **6–12 hours**.

---

### With PS-11

All nearby cameras are already connected.

Officer simply types:

> "Black jacket, blue jeans, black helmet"

AI immediately searches all cameras.

Results:

```
2:15 PM
Jewellery Shop

↓

2:17 PM
Main Road Camera

↓

2:20 PM
Traffic Signal

↓

2:24 PM
Highway Exit
```

The software also draws the suspect's route on a map.

Police know exactly where the suspect went.

---

# Use Case 2: Missing Child

Parents report

> My son is 8 years old.
> Wearing yellow T-shirt.
> Blue shorts.

---

Instead of asking every shopkeeper...

Officer enters

```
Yellow T-shirt
Blue shorts
Age around 8
```

AI searches

* Mall cameras
* Society cameras
* Traffic cameras
* Railway station cameras

Within seconds it finds

```
Camera 31

4:42 PM

Walking near Bus Stand
```

Police immediately send a nearby patrol.

The child is found quickly.

---

# Use Case 3: Terrorist or Wanted Criminal

Police already have

* Photo
* Vehicle Number

They add it to the watchlist.

Now AI keeps checking every incoming camera feed.

Suppose at 11:12 AM

One traffic camera detects

```
MH04AB1234
```

Immediately

```
ALERT

Wanted Vehicle Found

Location:
Ring Road

Camera ID:
TRF-102
```

Nearby police are informed instantly.

No one had to watch that camera manually.

---

# Use Case 4: Large Crowd Formation

Suppose during a festival

Suddenly

500 people gather.

Current system

Someone has to notice.

Sometimes nobody notices until it's too late.

---

With AI

Camera detects

```
Crowd Size

50

↓

120

↓

300

↓

700
```

System alerts

```
Possible overcrowding

High Risk
```

Police send more officers.

Crowd can be managed before panic starts.

---

# Use Case 5: Fight Detection

Imagine outside a club.

People start fighting.

AI notices

* Running
* Punching
* People falling
* Sudden gathering

Alert

```
Possible Physical Violence

Camera 19

Live Now
```

Police reach immediately.

---

# Use Case 6: Abandoned Bag

Airport

Railway Station

Mall

Someone leaves a backpack.

Current system

Operator may never notice.

---

AI detects

```
Bag appears

↓

Owner walks away

↓

Bag remains

5 minutes

↓

Alert
```

Police inspect it immediately.

---

# Use Case 7: Hit and Run

Someone reports

```
White Creta

Hit pedestrian

Escaped
```

Police search

```
White Creta
```

AI searches every road camera.

Finds

```
Camera 5

↓

Camera 17

↓

Camera 26

↓

Camera 42
```

Shows

* Direction
* Speed
* Route

Police intercept.

---

# Use Case 8: Society Security

Housing society has

50 cameras.

One guard.

Guard cannot watch all cameras.

---

AI monitors everything.

At 2 AM

Someone climbs the compound wall.

Immediately

```
Intrusion Detected

Block B

North Wall

Snapshot Attached
```

Guard reaches before theft happens.

---

# Use Case 9: Retail Shoplifting

Mall has

200 cameras.

Shopkeeper reports

Someone stole an iPhone.

Police search

```
Red Shirt
Black Backpack
```

AI finds

```
Entered

↓

Stole phone

↓

Exited Gate 4

↓

Entered Parking
```

No manual searching.

---

# Use Case 10: Vehicle Tracking Across City

Police know

```
Car Number

GJ05XX1234
```

AI tracks

```
8:20 AM

Traffic Signal A

↓

8:28 AM

Mall Road

↓

8:34 AM

Airport Circle

↓

8:45 AM

Highway Toll
```

Complete journey is reconstructed automatically.

---

# Use Case 11: Police Body Camera

A police officer is wearing a body camera.

He enters a dangerous area.

The live feed also comes into the system.

Command center can

* watch him live
* record everything
* analyze events
* store evidence

If he encounters a wanted suspect, AI can assist by flagging that the person matches a watchlist (subject to deployment policies and legal permissions).

---

# Use Case 12: Fire Detection

A shop catches fire.

AI sees

* Smoke
* Flames

Immediately

```
Fire Detected

Camera 102

Market Area

Priority High
```

Fire brigade is informed.

---

# Use Case 13: Illegal Parking

AI watches roads.

Vehicle parked in

```
No Parking Zone
```

for

15 minutes.

Alert generated.

Traffic police take action.

---

# Use Case 14: Accident Detection

Road camera notices

```
Vehicle collision

↓

Vehicle stopped

↓

People lying on road
```

Alert

```
Possible Accident

Live Feed Available
```

Ambulance dispatched immediately.

---

# Use Case 15: Stolen Vehicle Re-Identification (No Plate Visible)

### Situation
A car is stolen. Thieves swap or cover the plate within minutes.

### Current Method
Once the plate is changed, plate-based ANPR systems lose the vehicle entirely. Manual review of hours of footage across multiple junctions is the only option.

### With PS-11
AI re-identifies the vehicle by **make, model, color, and visual damage/features** (dent, sticker, roof rack) rather than plate alone.

```
8:00 AM — Stolen (Plate GJ05AB1234)
↓
8:12 AM — Plate now unreadable/changed
↓
8:12 AM — Vehicle re-identified by appearance vector
↓
8:20 AM — Location: Ring Road, no plate match needed
```

*Why this matters: plate-swapping is the single most common way suspects defeat ANPR-only systems. Visual re-ID closes that gap.*

---

# Use Case 16: Cross-Camera, Cross-Agency Handoff

### Situation
A suspect's route crosses from municipal traffic cameras into a private mall's CCTV, then into a housing society's system — three different vendors, three different formats.

### With PS-11
Unified feed aggregation means the suspect's track continues seamlessly across ownership boundaries, with each camera's owning agency/entity logged against the segment of footage used (for legal chain-of-custody).

```
Municipal Camera (Ring Road) → Mall CCTV (Entrance Gate) → Society Camera (Block C)
Each handoff logged with: operator ID, camera owner, legal basis for access
```

*This is the actual core value proposition of "unified aggregation" — worth being an explicit, named use case rather than implied.*

---

# Use Case 17: Chain of Custody & Evidence Integrity for Court

### Situation
Footage is pulled for a case. Six months later, defense counsel challenges whether the clip was tampered with.

### With PS-11
Every exported clip carries:
- Cryptographic hash (SHA256) at time of export
- Timestamp, camera ID, operator ID who pulled it
- Export reason/case number logged
- Immutable audit trail (append-only log, not editable by any operator including admins)

```
Export Record:
Case #: FIR-2026-0417
Clip Hash: a3f9e1...
Exported by: Officer Badge #4521
Reason: "Suspect ID confirmation"
Timestamp: 2026-07-15 14:32:07
```

*Without this, footage is inadmissible or easily challenged in court. This should be a hard requirement, not an afterthought — flagging that your current known bug ("forensic export reads from live stream not MediaMTX archive") directly undermines this use case, since live-stream re-encoding breaks hash integrity back to the original recording.*

---

# Use Case 18: Weapon Detection in Crowds

### Situation
A public event, market, or protest — someone is carrying a visible firearm or blade.

### With PS-11
AI flags visible weapons in frame independent of any other trigger (not just during an active fight).

```
Weapon Detected (Knife)
Camera 44 — Market Entrance
Confidence: High
Live Feed Attached
```

*Your class list already includes `weapon` — this should be surfaced as its own standing alert type, not folded only into fight-detection logic.*

---

# Use Case 19: Number Plate Recognition in Degraded Conditions

### Situation
Rain, night, motion blur, or a partially obscured plate (mud, damage, deliberate tampering).

### With PS-11
Super-resolution / plate-reconstruction pass runs specifically on low-confidence plate detections before discarding them, rather than a single-pass OCR that fails silently.

```
Raw detection confidence: 32% → below threshold
↓
Enhancement pass (deblur + super-res)
↓
Re-run OCR: 81% confidence → GJ05**34
```

*Real-world plates are rarely read cleanly on the first pass at night or in monsoon — this is a common gap in demo-stage ANPR systems.*

---

# Use Case 20: Loitering / Suspicious Dwell-Time Detection

### Situation
Someone repeatedly circles a bank ATM or parked vehicle without a clear purpose — a common pre-crime indicator (recon before robbery/theft).

### With PS-11
```
Person detected near ATM
↓
Same person re-appears 3x in 20 min, no transaction
↓
Alert: Possible Recon / Loitering
```

---

# Use Case 21: Wrong-Side Driving / Traffic Violation Beyond Parking

### Situation
Current use cases cover illegal parking but not moving violations.

### With PS-11
```
Vehicle detected traveling against marked lane direction
↓
Alert: Wrong-Side Driving
Camera: Junction 12
Plate: (auto-captured)
```

Also covers: signal jumping, no-helmet detection (helmet class already exists in your dataset), triple-riding on two-wheelers.

---

# Use Case 22: Domestic/Public Distress Signals (Non-Violent)

### Situation
A person is being followed, cornered, or shows visible distress (not yet a fight) — e.g., a woman being harassed at night.

### With PS-11
Behavioral cues (rapid distancing, repeated glancing back, group surrounding an individual) trigger a lower-severity "possible harassment" alert distinct from full fight-detection, so operators can intervene earlier rather than waiting for physical violence.

*This is a real and frequently requested feature for women's safety-focused deployments in India specifically — worth considering given this is aimed at Surat Police.*

---

# Use Case 23: Multi-Suspect Coordinated Crime

### Situation
Robbery involves 3 people — one enters, one waits on a bike, one watches the street. Investigators need to link them as a group, not three separate unrelated detections.

### With PS-11
```
Person A enters shop (2:15 PM)
Person B waits on bike, same location, same time window
Person C stands at street corner, same time window
↓
System flags spatial-temporal co-occurrence
↓
Suggests: "These 3 individuals may be linked (same incident window)"
```

*This is a genuinely harder ML problem (graph-based co-occurrence linking, not just single-target search) — flag it as a stretch feature, not core scope, unless your team has bandwidth.*

---

# Use Case 24: False Alarm / Alert Feedback Loop

### Situation
Operators get an alert, check it, and it's a false positive (e.g., a mannequin flagged as a person with a weapon).

### With PS-11
Operator marks alert as "false positive" or "confirmed" in one click. This feedback becomes training data for your **Active Learning / Hard Example Mining** module (already in your plan) — closing the loop between deployment and model improvement.

*This is the actual real-world source of the FP/TP labels your `active_learning.py` script needs — worth making explicit that this operator feedback UI is the missing upstream piece, not just the log file.*

---

# Use Case 25: Night-Time / Low-Light Operation

### Situation
A large share of crime (robbery, break-ins, hit-and-run) happens at night, where RGB-only detection accuracy drops sharply.

### With PS-11
System should flag/adjust confidence thresholds per camera based on IR/low-light mode, and surface a "low visibility — reduced confidence" tag on alerts from those feeds rather than presenting night detections with the same false confidence as daytime ones.

---

# Use Case 26: Bandwidth/Camera Outage Resilience

### Situation
A camera goes offline (cut cable, power failure, tampering) — which is itself sometimes a precursor to a planned crime.

### With PS-11
```
Camera 19 — No signal for 90 seconds
↓
Alert: Camera Offline (Possible Tampering)
Last Known Frame: attached
```

*Operationally important and easy to implement (you already have MediaMTX health-checking territory) but currently missing from your use cases entirely.*

---

# Use Case 27: Search by Natural Language Description (Beyond Fixed Attributes)

### Situation
A witness describes a suspect in free-form language: "tall guy, limping, red bag, was arguing with someone."

### With PS-11
Given you already have CLIP embeddings in your stack, this is a natural fit: free-text query embedded and matched against frame embeddings rather than requiring rigid dropdown attribute selection.

```
Query: "man limping, red bag"
↓
CLIP similarity search across archived + live embeddings
↓
Ranked candidate frames returned
```

*This is likely your single highest-impact differentiator for the demo — it directly matches how a real officer describes a suspect, not how a database schema wants attributes entered.*

---

# What Else Real Investigations Typically Need (Gaps Worth Naming Explicitly)

A few categories a real police team would ask about that aren't yet represented anywhere in the document:

1. **Multi-jurisdiction data-sharing agreements** — legal/DPDP framing for when footage crosses private property (mall, society) vs. public infrastructure. You've already flagged DPDP compliance once in your OWL-ViT review; it deserves a standing section, not a one-off note.
2. **Officer safety / access control** — who can query the watchlist, and audit logging of *searches* (not just alerts), since misuse of a "search by appearance" tool is a real surveillance-abuse risk that reviewers/mentors will likely ask about directly.
3. **Report generation for FIR filing** — a one-click "export this incident as a formatted report" (timeline, snapshots, camera IDs) that a constable can attach to a First Information Report, rather than only raw clip export.
4. **Degraded network / offline-first edge case** — what happens to alerting when the RTSP relay (MediaMTX) itself goes down; is there a local buffering/failover story worth one slide even if not fully implemented.
5. **Watchlist expiry/legal review** — wanted-person entries should have a review/expiry date rather than persisting indefinitely, since a resolved case that isn't removed from the watchlist becomes a real liability.

These last five are worth at least a slide of acknowledgment even if not built for the hackathon deadline — judges evaluating a *police-facing* system will almost certainly ask about misuse-prevention and legal compliance, and having a considered answer (even "out of scope for MVP, here's our plan") is stronger than silence.

---

---

# How This Helps Police

Without this system:

* Officers manually watch hundreds of hours of footage.
* Different organizations use different CCTV software.
* Finding one person can take an entire day.
* Important events may be missed because no one is watching the right camera.

With PS-11:

* **One dashboard** connects feeds from different camera systems into a single place.
* **AI continuously monitors** every connected stream 24×7.
* **Events are detected automatically** instead of relying on human attention.
* **Investigators can search by person, vehicle, clothing, or time** instead of reviewing footage manually.
* **Real-time alerts** allow faster response to incidents.
* **Recorded clips can be exported with timestamps, camera IDs, and integrity information**, making them easier to use as evidence. 

In simple terms, **the software becomes a digital police operator that never gets tired, never looks away, and can monitor hundreds of cameras simultaneously while surfacing only the events that actually matter.**