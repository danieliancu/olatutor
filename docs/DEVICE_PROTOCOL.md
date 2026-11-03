# Device protocol

Status: **draft, not implemented.** `contracts/device_api/v1/openapi.draft.yaml` records the intended shape. None of these endpoints exist. The current `/api/ink/v1/` routes are an unauthenticated prototype, disabled outside development, and must not be used by a device.

## Intent

A device is an optional terminal that speaks the same Digital Ink v1 operations as the browser (`DIGITAL_INK_SPEC.md`, section 10), so the backend stays independent of any one vendor.

## To be designed in Milestones 2 and 5

- **Pairing:** a short-lived parent-issued code exchanged for a device-scoped credential.
- **Credentials:** rotatable and revocable, with no family administration access. Secure ownership reset and reassignment.
- **Records:** hardware model and revision, firmware version, protocol version, last sync, last connection, error state.
- **Transport:** HTTPS with certificate validation. JSON first; a 20,000-point stroke is about 430 KB of JSON, so compact binary is considered if measurements on the device justify it.
- **Offline:** bounded local storage if the device's storage permits it; otherwise clear connection status. No silent loss.
- **Retry:** bounded backoff with idempotent operations.
