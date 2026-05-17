# ThermaIQ Frontend

This folder contains the static demo interface for the ThermaIQ prototype. Its role is to make backend outputs visible, understandable, and usable during the hackathon demo.

## Responsibilities

The frontend owns:

- Showing dashboard metrics
- Sending simulator scenarios to the backend optimization endpoint
- Rendering calendar/event layers
- Showing backend optimization and report output
- Displaying structured JSON payloads for demo transparency
- Letting the user select and test different operating conditions

The frontend does not own:

- Physics-model correctness
- Optuna trial logic
- NVIDIA/OpenRouter API key management
- Production data persistence
- Direct integration with facility control systems

## Run

The frontend is a static HTML app.

```bash
cd frontend
python -m http.server 3000
```

Open:

```text
http://127.0.0.1:3000
```

The backend is expected at:

```text
http://127.0.0.1:8001
```

## Data Layers

The calendar and simulator screens can use these sample data layers:

- `Important dates`: holidays, exams, events, campaigns, or public-service traffic peaks
- `Weather data`: date-based historical or forecast ambient temperature
- `Traffic/load data`: date-based server workload or traffic estimate
- `Operations/sensor data`: facility measurements used for demo context

Temperature and traffic values are not calendar events by themselves; they are operational context layers.

## Demo Flow

The main demo flow uses the real backend:

- `/api/twin-optimize` for physics + Optuna optimization
- `/api/report` for live LLM-backed operational reporting when an API key is available
- local fallback reporting only when the external LLM provider is unavailable

Fallback output is kept as a resilience mechanism, not as the primary demo mode.
