# main.py - FastAPI application entry point

from datetime import datetime
import io
import os

import pandas as pd
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from nemotron import generate_final_decision, generate_optimization_policy
from optimizer import optimize
from physics import calculate_pue

load_dotenv()


app = FastAPI(
    title="ThermaIQ API",
    description="LLM-guided constrained optimization digital twin for data centers",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class PredictInput(BaseModel):
    server_workload_pct: float = Field(..., ge=0, le=100)
    ambient_temp_c: float = Field(..., ge=-40, le=60)
    chiller_setpoint_c: float = Field(7, ge=4, le=20)
    fan_speed_pct: float = Field(65, ge=0, le=100)
    it_capacity_mw: float = Field(21, gt=0)


class TwinOptimizeInput(BaseModel):
    server_workload_pct: float = Field(..., ge=0, le=100)
    ambient_temp_c: float = Field(..., ge=-40, le=60)
    hour: int = Field(12, ge=0, le=23)
    month: int = Field(7, ge=1, le=12)
    it_capacity_mw: float = Field(21, gt=0)
    n_trials: int = Field(100, ge=10, le=250)


class BMSCommandInput(BaseModel):
    chiller_setpoint_c: float = Field(..., ge=6, le=16)
    fan_speed_pct: float = Field(..., ge=30, le=95)
    approval_token: str = "demo-approval"


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "ThermaIQ",
        "components": {
            "physics_engine": "ready",
            "optimizer": "ready",
            "nemotron": "ready" if os.getenv("NVIDIA_API_KEY") else "fallback_mode",
        },
    }


@app.post("/api/predict")
def predict(inp: PredictInput):
    """Single-scenario deterministic PUE calculation."""
    return calculate_pue(
        server_workload_pct=inp.server_workload_pct,
        ambient_temp_c=inp.ambient_temp_c,
        chiller_setpoint_c=inp.chiller_setpoint_c,
        fan_speed_pct=inp.fan_speed_pct,
        it_capacity_mw=inp.it_capacity_mw,
    )


@app.post("/api/twin-optimize")
def twin_optimize(inp: TwinOptimizeInput):
    """
    Full pipeline:
    1. Physics engine calculates current state.
    2. Nemotron produces an optimization policy.
    3. Optuna searches the physics twin with that policy.
    4. Nemotron returns final operations decision.
    """
    current = calculate_pue(
        server_workload_pct=inp.server_workload_pct,
        ambient_temp_c=inp.ambient_temp_c,
        chiller_setpoint_c=6,
        fan_speed_pct=90,
        it_capacity_mw=inp.it_capacity_mw,
    )

    policy = generate_optimization_policy(
        server_workload_pct=inp.server_workload_pct,
        ambient_temp_c=inp.ambient_temp_c,
        current_pue=current["pue"],
        current_inlet_temp=current["inlet_temp_c"],
        hour=inp.hour,
        month=inp.month,
    )

    optimization_result = optimize(
        server_workload_pct=inp.server_workload_pct,
        ambient_temp_c=inp.ambient_temp_c,
        policy=policy,
        hour=inp.hour,
        month=inp.month,
        it_capacity_mw=inp.it_capacity_mw,
        n_trials=inp.n_trials,
    )

    decision = generate_final_decision(
        current=optimization_result["current"],
        candidates=optimization_result["candidates"],
        policy=policy,
    )

    return {
        "current": optimization_result["current"],
        "policy": policy,
        "candidates": optimization_result["candidates"],
        "decision": decision,
        "meta": optimization_result["meta"],
        "timestamp": datetime.now().isoformat(),
    }


@app.get("/api/demo-scenarios")
def demo_scenarios():
    """Four offline demo scenarios."""
    scenarios = [
        {
            "name": "Yaz Ogle",
            "label_tr": "Yaz Öğle",
            "emoji": "sun",
            "server_workload_pct": 85,
            "ambient_temp_c": 35,
            "hour": 14,
            "month": 7,
        },
        {
            "name": "Kis Gece",
            "label_tr": "Kış Gece",
            "emoji": "snow",
            "server_workload_pct": 45,
            "ambient_temp_c": -2,
            "hour": 3,
            "month": 1,
        },
        {
            "name": "Bahar Normal",
            "label_tr": "Bahar Normal",
            "emoji": "spring",
            "server_workload_pct": 60,
            "ambient_temp_c": 18,
            "hour": 11,
            "month": 4,
        },
        {
            "name": "Asiri Yuk",
            "label_tr": "Aşırı Yük",
            "emoji": "peak",
            "server_workload_pct": 95,
            "ambient_temp_c": 28,
            "hour": 16,
            "month": 8,
        },
    ]

    results = []
    for scenario in scenarios:
        try:
            payload = {
                key: value
                for key, value in scenario.items()
                if key not in ("name", "label_tr", "emoji")
            }
            payload["n_trials"] = 60
            result = twin_optimize(TwinOptimizeInput(**payload))
            results.append({**scenario, "result": result})
        except Exception as exc:
            results.append({**scenario, "error": str(exc)})

    return results


@app.post("/api/bms/apply")
def bms_apply(inp: BMSCommandInput):
    """Mock BACnet/IP setpoint application."""
    if inp.approval_token != "demo-approval":
        raise HTTPException(status_code=403, detail="Onay token gerekli")

    return {
        "protocol": "BACnet/IP",
        "target": "Golbasi-HVAC-Controller-01",
        "commands": [
            {
                "object": "Chiller-01",
                "property": "chilled_water_setpoint",
                "value": inp.chiller_setpoint_c,
                "unit": "C",
            },
            {
                "object": "AHU-Bank-A",
                "property": "fan_speed",
                "value": inp.fan_speed_pct,
                "unit": "%",
            },
        ],
        "status": "APPLIED",
        "timestamp": datetime.now().isoformat(),
        "compliance": "TS EN 50600-aligned energy monitoring demo",
        "note": "Demo mode; real deployment requires a BACnet/IP stack and approval workflow.",
    }


@app.post("/api/adapt")
async def adapt(request: Request, company_name: str = Query("default")):
    """
    Customer CSV calibration preview.
    Accepts raw CSV body to avoid requiring python-multipart during the hackathon demo.
    """
    try:
        content = await request.body()
        if not content:
            raise ValueError("CSV body bos")

        df = pd.read_csv(io.BytesIO(content))
        stats = {
            "rows": len(df),
            "columns": df.columns.tolist(),
        }

        numeric_stats = {}
        for col in df.select_dtypes(include="number").columns:
            numeric_stats[col] = {
                "mean": round(float(df[col].mean()), 3),
                "min": round(float(df[col].min()), 3),
                "max": round(float(df[col].max()), 3),
            }

        return {
            "success": True,
            "company": company_name,
            "stats": stats,
            "numeric_stats": numeric_stats,
            "message": f"{company_name} icin dijital ikiz kalibrasyonu hazir.",
            "calibration_note": "Yeni veriler temel fizik motorunun katsayilarini ayarlamak icin kullanilir.",
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/")
def root():
    return {
        "service": "ThermaIQ",
        "tagline": "LLM-guided constrained optimization digital twin",
        "endpoints": [
            "GET /health",
            "POST /api/predict",
            "POST /api/twin-optimize",
            "GET /api/demo-scenarios",
            "POST /api/bms/apply",
            "POST /api/adapt",
        ],
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
