# Firmware specification

Status: **no firmware exists.** This records requirements for Milestone 2. Hardware facts live in `firmware/elecrow_esp32p4/hardware-profile.yaml`, where each value is marked `documented`, `measured` or `unknown`. **Nothing has been measured on a board.** The board was not connected to the development PC, and ESP-IDF is not installed.

## Hardware verification gate

Before writing board-specific code, read the PCB revision from the physical board. LVGL version and pin mapping depend on it (LVGL 9.1 on V1.2, 8.3 on V1.0 and V1.1, according to the vendor). Fill every `unknown` field, and resolve these conflicts in the documentation using the schematic:

- IO40 appears both in the DSI pin list and as touch RESET.
- A LoRa snippet still lists pins that V1.2 is said to have swapped.
- The display controller is not named.
- The microphone is described as both single and an array.
- A speaker is named but missing from the package list.

## Scope of the first firmware

- ESP-IDF 5.4.2 or later, C/C++, the vendor's example code as a starting point once its licence is confirmed, and the LVGL version matched to the revision.
- A writing page with local ink rendering that never waits for the network.
- Touch capture producing Digital Ink v1 operations that pass the shared fixtures. A C core must add its own conformance run; browser and Python results do not cover it.
- An early spike for the memory cost of folding a journal, the entropy source for IDs, and rounding. The P4's floating-point support is believed to be single-precision only; verify this, since it affects the coordinate transform.

Device behaviour in general: the device never runs Django or recognition models, gets only device-scoped credentials, validates TLS certificates, and never embeds shared secrets. Secure OTA is required before any distribution beyond controlled development use.

## Palm rejection experiment

A capacitive panel may be unable to tell a passive stylus from a finger or a palm, and software cannot recover information the sensor does not report. The state machine is `IDLE`, `CONTACT_CANDIDATE`, `STROKE_ACTIVE`, `AMBIGUOUS_MULTITOUCH`, `GESTURE_CANDIDATE`, `CANCELLED`. The first touch must not be assumed to be the stylus. Palm-first and stylus-first contact are both tested.

Measure, with timestamped diagnostics from the device: false accepted palm strokes, false rejected stylus strokes, stroke interruptions, tracking-ID stability, several stylus types, both orientations.

## Writing performance

Collect: touch sampling rate, touch-to-visible-ink latency (p50, p95, p99; initial target under 30 ms at p95), stroke continuity, coordinate jitter, render performance, RAM and PSRAM use, recovery time, long-session stability, and real power draw. The measurement method must be documented, and camera-based latency measurement is the likely choice since software timestamps miss the panel's delay.

## Decision gate

If palm rejection, precision or comfort is unacceptable, document it and evaluate other styluses, other touchscreens and active digitizers. A hardware change must not affect the backend or the ink protocol.

Physical test status: **BLOCKED** until a board is available.
