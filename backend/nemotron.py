# nemotron.py - NVIDIA Nemotron digital twin controller

import json
import os
import re
from typing import Optional

import urllib3
import requests
from dotenv import load_dotenv

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

load_dotenv()

NVIDIA_API = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "nvidia/nemotron-3-nano-30b-a3b:free"


POLICY_SYSTEM_PROMPT = """Sen Türksat Gölbaşı Veri Merkezi'nin Dijital İkiz Kontrolcüsüsün.
21 MW IT kapasiteli, ASHRAE 90.4 ve TS EN 50600 uyumlu bir tesissin.

Görevin: Mevcut tesis durumuna bakıp optimizasyon stratejisi belirlemek.
Stratejiler:
- safety_first: Yüksek yük veya yüksek sıcaklıkta termal risk öncelikli
- aggressive_savings: Düşük yük veya soğuk havada agresif tasarruf
- balanced: Normal koşullarda dengeli yaklaşım
- free_cooling: Dış sıcaklık 8°C altında, free cooling maksimize edilir
- peak_load: Yük %90+ veya tepe saatlerde stabilite öncelikli

Çıktı SADECE şu JSON formatında olsun, başka hiçbir şey yazma:
{
  "strategy": "safety_first|aggressive_savings|balanced|free_cooling|peak_load",
  "objective_weights": {
    "pue": 0.0-1.0,
    "thermal_risk": 0.0-1.0,
    "setpoint_change": 0.0-1.0
  },
  "search_space": {
    "chiller_setpoint_c": [min, max],
    "fan_speed_pct": [min, max]
  },
  "risk_policy": {
    "max_inlet_temp_c": <=27,
    "preferred_inlet_temp_c": 20-26.5
  },
  "reason_tr": "Türkçe gerekçe, 1-2 cümle"
}

Sınırlar:
- chiller_setpoint_c global: 6-16°C
- fan_speed_pct global: 30-95
- objective_weights toplamı 1.0 olmalı
- max_inlet_temp_c maksimum 27"""


DECISION_SYSTEM_PROMPT = """Sen Türksat Gölbaşı Veri Merkezi'nin Operasyon Karar Vericisisin.
Sana mevcut durum ve Optuna'nın bulduğu top 3 aday sunulacak.
Görevin: En iyi adayı seçmek ve operasyonel kararı vermek.

Karar kriterleri:
- En düşük PUE her zaman en iyi değildir
- Termal risk (inlet temp) ile tasarruf arasında denge
- ASHRAE-Recommended bandı tercih edilir, Allowable kabul edilebilir, VIOLATION asla
- Setpoint değişimi büyükse risk artar

Çıktı SADECE şu JSON formatında olsun:
{
  "decision": "APPROVE|REVIEW|REJECT",
  "selected_candidate_rank": 1|2|3,
  "risk_level": "low|medium|high",
  "standards_check": {
    "ashrae": "PASS|WARNING|FAIL",
    "pue": "IMPROVED|NEUTRAL|DEGRADED",
    "bms": "HUMAN_APPROVAL_REQUIRED|AUTO_APPLY_OK"
  },
  "operator_message_tr": "Türkçe operasyonel rapor, 3-4 cümle, sayısal değerlerle",
  "approval_question_tr": "Tesis müdürüne sorulacak Türkçe onay sorusu",
  "fallback_action": "Eğer öneri uygulandıktan sonra inlet sıcaklığı yükselirse yapılacak Türkçe aksiyon"
}"""


def _extract_json(content: str) -> dict:
    """Parse JSON from plain content, fenced blocks, or text containing one JSON object."""
    text = content.strip()
    if "```" in text:
        blocks = text.split("```")
        for block in blocks:
            cleaned = block.strip()
            if cleaned.startswith("json"):
                cleaned = cleaned[4:].strip()
            if cleaned.startswith("{"):
                text = cleaned
                break

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))


def _call_nemotron(system_prompt: str, user_message: str, max_tokens: int = 400) -> dict:
    """Call NVIDIA Nemotron and parse a JSON object response."""
    api_key = os.getenv("NVIDIA_API_KEY")
    if not api_key:
        raise ValueError("NVIDIA_API_KEY bulunamadı")

    response = requests.post(
        NVIDIA_API,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost:8000",
            "X-Title": "ThermaIQ Data Center Twin",
        },
        json={
            "model": MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "max_tokens": max_tokens,
            "temperature": 0.2,
        },
        timeout=30,
        verify=False,
    )
    response.raise_for_status()
    message = response.json()["choices"][0]["message"]

    content = message.get("content") or ""
    # Reasoning models (nemotron-nano) may put output in the reasoning field
    # when max_tokens is exhausted before the final answer block.
    if not content.strip():
        reasoning = message.get("reasoning") or ""
        content = reasoning

    return _extract_json(content.strip())


def _fallback_policy(server_workload_pct: float, ambient_temp_c: float) -> dict:
    """Rule-based fallback if API key is missing or the API fails."""
    if ambient_temp_c < 8:
        return {
            "strategy": "free_cooling",
            "objective_weights": {"pue": 0.65, "thermal_risk": 0.20, "setpoint_change": 0.15},
            "search_space": {"chiller_setpoint_c": [10, 16], "fan_speed_pct": [30, 60]},
            "risk_policy": {"max_inlet_temp_c": 27, "preferred_inlet_temp_c": 24},
            "reason_tr": "Dış sıcaklık düşük. Free cooling maksimize edilebilir.",
            "source": "fallback",
        }
    if server_workload_pct >= 90:
        return {
            "strategy": "peak_load",
            "objective_weights": {"pue": 0.35, "thermal_risk": 0.55, "setpoint_change": 0.10},
            "search_space": {"chiller_setpoint_c": [6, 10], "fan_speed_pct": [75, 95]},
            "risk_policy": {"max_inlet_temp_c": 27, "preferred_inlet_temp_c": 23},
            "reason_tr": "Yük tepe seviyede. Termal stabilite ve fan kapasitesi önceliklendirildi.",
            "source": "fallback",
        }
    if server_workload_pct > 85 or ambient_temp_c > 30:
        return {
            "strategy": "safety_first",
            "objective_weights": {"pue": 0.40, "thermal_risk": 0.50, "setpoint_change": 0.10},
            "search_space": {"chiller_setpoint_c": [6, 11], "fan_speed_pct": [65, 90]},
            "risk_policy": {"max_inlet_temp_c": 27, "preferred_inlet_temp_c": 23},
            "reason_tr": "Yük veya dış sıcaklık yüksek. Güvenlik öncelikli optimizasyon seçildi.",
            "source": "fallback",
        }
    if server_workload_pct < 40 and ambient_temp_c < 18:
        return {
            "strategy": "aggressive_savings",
            "objective_weights": {"pue": 0.70, "thermal_risk": 0.20, "setpoint_change": 0.10},
            "search_space": {"chiller_setpoint_c": [9, 14], "fan_speed_pct": [35, 65]},
            "risk_policy": {"max_inlet_temp_c": 27, "preferred_inlet_temp_c": 25},
            "reason_tr": "Düşük yük ve serin hava nedeniyle agresif tasarruf modu güvenli görünüyor.",
            "source": "fallback",
        }
    return {
        "strategy": "balanced",
        "objective_weights": {"pue": 0.55, "thermal_risk": 0.30, "setpoint_change": 0.15},
        "search_space": {"chiller_setpoint_c": [7, 13], "fan_speed_pct": [60, 90]},
        "risk_policy": {"max_inlet_temp_c": 27, "preferred_inlet_temp_c": 25.5},
        "reason_tr": "Koşullar normal aralıkta. Tasarruf ve termal güvenlik dengelendi.",
        "source": "fallback",
    }


def _fallback_decision(candidates: list) -> dict:
    """Rule-based final decision if Nemotron is unavailable."""
    if not candidates:
        return {
            "decision": "REJECT",
            "selected_candidate_rank": None,
            "risk_level": "high",
            "standards_check": {
                "ashrae": "FAIL",
                "pue": "DEGRADED",
                "bms": "HUMAN_APPROVAL_REQUIRED",
            },
            "operator_message_tr": "Geçerli aday bulunamadı. Mevcut ayarlar korunmalı ve manuel inceleme başlatılmalı.",
            "approval_question_tr": "Manuel kontrol için operasyon ekibi çağırılsın mı?",
            "fallback_action": "Mevcut ayarlar korunur.",
            "source": "fallback",
        }

    valid = [c for c in candidates if c.get("ashrae_status") != "VIOLATION"]
    if not valid:
        return _fallback_decision([])

    risk_rank = {"low": 0, "medium": 1, "high": 2}
    best = sorted(
        valid,
        key=lambda c: (
            risk_rank.get(c.get("risk_level", "high"), 2),
            c.get("pue", 9),
        ),
    )[0]
    rank = best["rank"]
    decision = "APPROVE" if best.get("risk_level") in ("low", "medium") else "REVIEW"
    ashrae = "PASS" if best.get("risk_level") != "high" else "WARNING"

    return {
        "decision": decision,
        "selected_candidate_rank": rank,
        "risk_level": best.get("risk_level", "medium"),
        "standards_check": {
            "ashrae": ashrae,
            "pue": "IMPROVED",
            "bms": "HUMAN_APPROVAL_REQUIRED",
        },
        "operator_message_tr": (
            f"Rank {rank} adayı önerildi. PUE {best['pue']} seviyesine düşerken "
            f"inlet sıcaklığı {best['inlet_temp_c']}°C ve ASHRAE durumu {best['ashrae_status']}. "
            f"Beklenen aylık tasarruf {best['monthly_savings_tl']:,.0f} TL. "
            "Komut insan onayı sonrası BACnet/IP payload olarak uygulanmalıdır."
        ),
        "approval_question_tr": (
            f"CHILLER-01 için {best['chiller_setpoint_c']}°C setpoint ve "
            f"%{best['fan_speed_pct']} fan hızını BACnet/IP üzerinden uygulamak istiyor musunuz?"
        ),
        "fallback_action": (
            f"Inlet 26.5°C üzerine çıkarsa fan hızı %{min(95, best['fan_speed_pct'] + 10):.0f} "
            "seviyesine alınır ve chiller setpoint 1°C düşürülür."
        ),
        "source": "fallback",
    }


def _validate_policy_shape(policy: dict, fallback: dict) -> dict:
    """Keep Nemotron output structurally compatible with optimizer.py."""
    if not isinstance(policy, dict):
        return fallback

    required = ("strategy", "objective_weights", "search_space", "risk_policy")
    if not all(key in policy for key in required):
        return fallback

    policy.setdefault("reason_tr", fallback.get("reason_tr", ""))
    policy["source"] = "nemotron"
    return policy


def _validate_decision_shape(decision: dict, candidates: list, fallback: dict) -> dict:
    if not isinstance(decision, dict):
        return fallback

    ranks = {c.get("rank") for c in candidates}
    selected_rank = decision.get("selected_candidate_rank")
    if selected_rank not in ranks:
        return fallback
    if decision.get("decision") not in ("APPROVE", "REVIEW", "REJECT"):
        return fallback

    decision.setdefault("source", "nemotron")
    return decision


def generate_optimization_policy(
    server_workload_pct: float,
    ambient_temp_c: float,
    current_pue: float,
    current_inlet_temp: float,
    hour: int = 12,
    month: int = 7,
) -> dict:
    """Nemotron Call #1: strategy planner."""
    fallback = _fallback_policy(server_workload_pct, ambient_temp_c)
    user_msg = f"""Mevcut tesis durumu:
- Sunucu yükü: %{server_workload_pct}
- Dış sıcaklık: {ambient_temp_c}°C
- Mevcut PUE: {current_pue}
- Inlet sıcaklık: {current_inlet_temp}°C
- Saat: {hour}:00, Ay: {month}

Bu duruma uygun optimizasyon politikasını JSON olarak üret."""

    try:
        policy = _call_nemotron(POLICY_SYSTEM_PROMPT, user_msg, max_tokens=1200)
        return _validate_policy_shape(policy, fallback)
    except Exception as exc:
        print(f"[Nemotron policy fallback] {exc}")
        return fallback


def generate_final_decision(current: dict, candidates: list, policy: dict) -> dict:
    """Nemotron Call #2: operations controller."""
    fallback = _fallback_decision(candidates)
    candidates_summary = []
    for candidate in candidates:
        candidates_summary.append(
            {
                "rank": candidate["rank"],
                "pue": candidate["pue"],
                "chiller_setpoint_c": candidate["chiller_setpoint_c"],
                "fan_speed_pct": candidate["fan_speed_pct"],
                "inlet_temp_c": candidate["inlet_temp_c"],
                "ashrae_status": candidate["ashrae_status"],
                "risk_level": candidate["risk_level"],
                "monthly_savings_tl": candidate["monthly_savings_tl"],
            }
        )

    user_msg = f"""Mevcut durum:
PUE: {current['pue']}, Inlet: {current['inlet_temp_c']}°C, ASHRAE: {current['ashrae_status']}

Optimizasyon stratejisi: {policy.get('strategy', 'balanced')}
Strateji gerekçesi: {policy.get('reason_tr', '')}

Top 3 aday:
{json.dumps(candidates_summary, ensure_ascii=False, indent=2)}

En uygun adayı seç ve operasyon kararını JSON olarak ver."""

    try:
        decision = _call_nemotron(DECISION_SYSTEM_PROMPT, user_msg, max_tokens=1500)
        return _validate_decision_shape(decision, candidates, fallback)
    except Exception as exc:
        print(f"[Nemotron decision fallback] {exc}")
        return fallback


if __name__ == "__main__":
    print("=== POLICY TEST: Yaz Ogle ===")
    p1 = generate_optimization_policy(85, 35, 1.42, 25.3, hour=14, month=7)
    print(json.dumps(p1, indent=2, ensure_ascii=False))

    print("\n=== POLICY TEST: Kis Gece ===")
    p2 = generate_optimization_policy(45, -2, 1.15, 18.5, hour=3, month=1)
    print(json.dumps(p2, indent=2, ensure_ascii=False))

    print("\n=== DECISION TEST ===")
    mock_current = {"pue": 1.42, "inlet_temp_c": 25.3, "ashrae_status": "ASHRAE-Allowable"}
    mock_candidates = [
        {
            "rank": 1,
            "pue": 1.31,
            "chiller_setpoint_c": 11.5,
            "fan_speed_pct": 70,
            "inlet_temp_c": 25.8,
            "ashrae_status": "ASHRAE-Allowable",
            "risk_level": "medium",
            "monthly_savings_tl": 1500000,
        },
        {
            "rank": 2,
            "pue": 1.33,
            "chiller_setpoint_c": 10.2,
            "fan_speed_pct": 75,
            "inlet_temp_c": 24.9,
            "ashrae_status": "ASHRAE-Allowable",
            "risk_level": "low",
            "monthly_savings_tl": 1380000,
        },
        {
            "rank": 3,
            "pue": 1.35,
            "chiller_setpoint_c": 9.0,
            "fan_speed_pct": 80,
            "inlet_temp_c": 24.1,
            "ashrae_status": "ASHRAE-Recommended",
            "risk_level": "low",
            "monthly_savings_tl": 1250000,
        },
    ]
    d = generate_final_decision(mock_current, mock_candidates, p1)
    print(json.dumps(d, indent=2, ensure_ascii=False))
