# ThermaIQ

## Project Overview

ThermaIQ is a hackathon prototype for AI-assisted data center cooling optimization. It combines a deterministic physics model, constrained Optuna search, and an LLM decision/report layer to help operators evaluate cooling setpoints, PUE impact, thermal risk, savings potential, and carbon impact before taking action.

The default flow uses the real backend, `physics.py`, `optimizer.py`, and live NVIDIA Nemotron/OpenRouter integration when a valid API key is configured. If the external LLM service is unavailable, the system can produce a local fallback report for demo continuity and fault tolerance.

## Hackathon Theme Codes

- **A2 — Sustainability**
- **B4 — Data Center**
- **C1 — Text generation and chat**
- **C7 — Agent and tool use**

ThermaIQ also performs time-contextual operation analysis and physics-based safety/risk checks, but these are implementation details rather than separate theme-code claims.

## Problem

Data center cooling decisions affect energy cost, PUE, carbon output, and hardware safety at the same time. Operators often need to balance competing goals:

- reducing cooling energy,
- keeping inlet temperature within safe limits,
- avoiding risky setpoint changes during peak load,
- explaining recommendations in language facility teams can act on.

Manual setpoint decisions can be conservative, hard to compare across scenarios, and difficult to translate into a clear operational action plan.

## Solution

ThermaIQ evaluates a facility scenario through a physics-based digital twin and searches for safer, more efficient chiller setpoint and fan-speed candidates. The system then converts the result into an operator-facing report and a structured action output.

The prototype answers:

- What is the current PUE estimate?
- Which setpoint/fan candidate improves PUE without violating thermal limits?
- What is the expected annualized savings and carbon impact in representative demo scenarios?
- What should the operator review or approve?

## Architecture

```text
Frontend
  |
  |  scenario values, sample files, operator actions
  v
FastAPI backend
  |
  |-- physics.py
  |     deterministic PUE, COP, inlet temperature, safety checks
  |
  |-- optimizer.py
  |     Optuna-based constrained search for chiller setpoint and fan speed
  |
  |-- nemotron.py
  |     NVIDIA Nemotron / OpenRouter policy, decision, report layer
  |     local fallback reporting if external LLM access fails
  |
  `-- calendar_parser.py
        time-contextual event parsing for operational planning
```

## Project Structure

```text
thermaiq/
|-- backend/
|   |-- main.py                    # FastAPI application and endpoints
|   |-- physics.py                 # Deterministic PUE, COP, inlet temperature calculations
|   |-- optimizer.py               # Optuna-based safe setpoint/fan search
|   |-- nemotron.py                # Live/fallback LLM decision and report layer
|   |-- calendar_parser.py         # Calendar/event file parser
|   |-- adaptation.py              # Customer data upload/adaptation preview helpers
|   |-- generate_data.py           # Synthetic/sample data utility
|   |-- evaluate_optimization.py   # Scenario evaluation helper
|   `-- requirements.txt           # Backend dependencies
|-- frontend/
|   |-- index.html                 # Static dashboard and simulator UI
|   |-- API_CONTRACTS.md           # Frontend/backend API notes
|   |-- README.md                  # Frontend-specific notes
|   |-- calendar-events-sample.csv
|   |-- calendar-events-sample.txt
|   `-- sample-data/
|       |-- important-dates.csv
|       |-- operations-sensor-sample.csv
|       |-- traffic-forecast.csv
|       `-- weather-forecast.csv
|-- data/
|-- models/
|-- run_demo.bat
|-- .env.example
`-- README.md
```

## Tech Stack

- **Backend:** FastAPI, Uvicorn
- **Optimization:** Optuna
- **Physics/data processing:** Python, NumPy, pandas
- **LLM layer:** NVIDIA Nemotron or OpenRouter-compatible chat completion endpoint
- **Frontend:** Static HTML/CSS/JavaScript

## Installation

```bash
git clone https://github.com/seymaerdogan0/thermaiq.git
cd thermaiq
python -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
cp .env.example .env
```

On Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
Copy-Item .env.example .env
```

Set one live LLM provider key in `.env`:

```env
NVIDIA_API_KEY=nvapi-xxx
OPENROUTER_API_KEY=sk-or-v1-xxx
```

## Backend Setup

```bash
cd backend
uvicorn main:app --host 127.0.0.1 --port 8001 --reload
```

API documentation:

```text
http://127.0.0.1:8001/docs
```

## Frontend Setup

```bash
cd frontend
python -m http.server 3000
```

Open:

```text
http://127.0.0.1:3000
```

## API Endpoints

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Service and component status |
| `POST` | `/api/predict` | Single-scenario deterministic PUE calculation |
| `POST` | `/api/twin-optimize` | Physics model + LLM policy + Optuna optimization |
| `POST` | `/api/report` | Operator-facing report generation |
| `GET` | `/api/report/sample` | Local fallback report sample |
| `GET` | `/api/demo-scenarios` | Offline demo scenarios |
| `POST` | `/api/bms/apply` | Structured command payload endpoint for prototype review |
| `POST` | `/api/calendar/parse` | Calendar/event file parsing |
| `GET` | `/api/calendar/sample` | Sample calendar events |
| `POST` | `/api/adaptation/upload` | Customer CSV preview |
| `POST` | `/api/adaptation/run` | Customer CSV adaptation preview |

Example optimization call:

```bash
curl -X POST http://127.0.0.1:8001/api/twin-optimize \
  -H "Content-Type: application/json" \
  -d '{
    "server_workload_pct": 85,
    "ambient_temp_c": 35,
    "hour": 14,
    "month": 7,
    "it_capacity_mw": 21,
    "n_trials": 60
  }'
```

## Live AI Mode Explanation

With a valid API key, ThermaIQ makes live LLM calls for policy, final decision, and report generation. The LLM does not invent the savings calculation; it receives physics/optimization outputs and turns them into an operational explanation.

If the LLM provider is unavailable, the backend can fall back to deterministic local report generation. This fallback is a technical resilience mechanism, not the primary final-demo claim.

## Standard Facility Management / Cooling System Output Explanation

ThermaIQ is currently a decision-support prototype that does not directly intervene in standard facility management or cooling systems. It produces a readable operator report and can optionally emit structured JSON action output that existing systems can parse.

In a production phase, this structured output could be integrated with existing control systems while preserving institutional safety limits, approval workflows, and human oversight.

## Savings and Carbon Impact Disclaimer

In four representative operation scenarios, the physics-based PUE model calculated an annualized savings potential of approximately **3.2 million TL/year**. This is not a guaranteed field result; it is the annualized engineering output of hackathon prototype demo scenarios.

The same representative scenarios produced an annualized carbon reduction potential of approximately **456 tons CO2/year**.

ThermaIQ does not guarantee LEED Gold certification or any sustainability certification outcome. It supports such goals by making energy, PUE, and carbon metrics more measurable at the operational decision level.

## Future Work

- Validate the physics model with larger real facility datasets.
- Add scenario weighting based on real annual operating-hour distributions.
- Add role-based approval workflows for facility teams.
- Integrate structured outputs with existing control systems after safety review.
- Add audit logging for recommendations, approvals, and applied actions.

## Team

ThermaIQ was built as a hackathon prototype by the project team for AI-assisted sustainable data center operations.
