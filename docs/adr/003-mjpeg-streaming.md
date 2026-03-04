# ADR-003: MJPEG over HTTP for Local Streaming

**Status:** Accepted  
**Date:** 2024-02-05  
**Deciders:** Perceptua  

---

## Context

The `StreamServer` needs to deliver live camera frames to a browser on the local network. Options evaluated:

1. **MJPEG over HTTP** (`multipart/x-mixed-replace`) — push-based, universally supported
2. **WebSocket + JPEG frames** — bidirectional, requires JS client
3. **HLS (HTTP Live Streaming)** — adaptive bitrate, requires segmenting and latency overhead
4. **WebRTC** — ultra-low latency, complex signalling infrastructure
5. **RTSP** — standard video protocol, not browser-native

## Decision

Use **MJPEG over HTTP** with Flask's streaming response (`multipart/x-mixed-replace`).

## Rationale

- **Zero client requirements** — works in any browser with a plain `<img>` tag; no JavaScript needed
- **No transcoding** — `Camera.get_jpeg_frame_generator()` already yields JPEG bytes; MJPEG is just boundary-wrapped JPEGs
- **Simple implementation** — Flask streaming response with a generator; two endpoints total
- **LAN-only use case** — latency and bandwidth are not production concerns
- **Sufficient for purpose** — this server is for local LAN verification, not the mobile app interface

## Trade-offs

- Higher bandwidth than H264/HLS — each frame is a full JPEG (no delta encoding)
- Not suitable for the mobile app (use the REST API + file download for stills, or add a direct streaming endpoint later)
- No built-in flow control — server pushes frames regardless of client consumption speed

## Future

If a low-latency video preview is needed in the mobile app, consider adding a WebSocket or WebRTC endpoint to `nomon.api` as a separate Phase deliverable.
