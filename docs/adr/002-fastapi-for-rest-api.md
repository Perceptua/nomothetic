# ADR-002: FastAPI for REST API (over Flask)

**Status:** Accepted  
**Date:** 2024-02-17  
**Deciders:** Perceptua  

---

## Context

The nomon REST API needs an HTTP framework. The project already uses Flask for `StreamServer`. Options evaluated:

1. **FastAPI** — modern async framework, Pydantic models, automatic OpenAPI docs
2. **Flask** — already in the project, synchronous, no built-in schema generation
3. **aiohttp** — async, lower-level, no built-in validation
4. **Standard library `http.server`** — no dependencies, but very low-level

## Decision

Use **FastAPI** for the REST API (`nomon.api`), while retaining Flask for the MJPEG stream server.

## Rationale

- **Automatic OpenAPI docs** at `/docs` and `/redoc` with zero extra code — essential for mobile client development
- **Pydantic request/response models** provide built-in validation and serialization
- **Async-native** — uvicorn ASGI server handles concurrent requests efficiently
- **Native SSL/TLS** via uvicorn — no additional middleware or reverse proxy needed
- **Type hints throughout** — aligns with project conventions; FastAPI leverages them for validation
- Flask remains appropriate for `StreamServer` (streaming response, two endpoints, synchronous generator)

## Trade-offs

- Two HTTP frameworks in the project (`fastapi` + `flask`) — acceptable because they serve different purposes and are in separate optional dependency groups
- FastAPI's dependency injection model is more complex than Flask's for new contributors
- Additional dependencies: `fastapi`, `uvicorn`, `python-multipart` in `[api]` group

## Consequences

- The `[api]` optional dependency group is required to use `APIServer`
- The `[web]` optional dependency group is required to use `StreamServer`
- A Pi running both must install both groups
