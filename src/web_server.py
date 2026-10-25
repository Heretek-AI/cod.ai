#!/usr/bin/env python3
"""
FastAPI Web GUI & Local Policy Proxy Server (`/src/web_server.py`).
Serves the Claude Web Opus 5.5 GUI at `http://127.0.0.1:8642` (matching the Proxmox VE port 8642 spec)
and exposes REST endpoints for live custom endpoint configuration, 3-Layer Cache assembly,
and `/skill doctor` telemetry inspection.
"""
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from src.context.cache_assembler import ThreeLayerCacheAssembler
from src.security.classifier import TwoStageSecurityClassifier
from src.security.proxy_sandbox import CredentialVaultProxy
from src.security.telemetry import SkillDoctorTelemetryEngine

app = FastAPI(title="cod.ai Claude Web Opus 5.5 Studio & Proxy Server", version="0.2.0")

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
WEB_INDEX_PATH = WORKSPACE_ROOT / "web" / "index.html"

vault_proxy = CredentialVaultProxy()
classifier = TwoStageSecurityClassifier()
telemetry_engine = SkillDoctorTelemetryEngine()


class EndpointConfigPayload(BaseModel):
    base_url: str
    wire_protocol: str = "anthropic-messages"
    model: str = "claude-opus-5-5"
    api_key: str = ""
    proxy_url: str = "http://127.0.0.1:3128"


class ChatTurnPayload(BaseModel):
    prompt: str
    model: str = "claude-opus-5-5"
    effort: str = "medium"
    thinking_display: str = "summarized"
    polarity_mode: str = "MODE_A_ARCHITECT"
    specialist_slug: str = "holistic-web-architect"


@app.get("/", response_class=HTMLResponse)
def serve_claude_web_gui() -> HTMLResponse:
    if WEB_INDEX_PATH.exists():
        return HTMLResponse(WEB_INDEX_PATH.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>cod.ai Web GUI not found</h1>", status_code=404)


@app.post("/api/endpoint/configure")
def configure_custom_endpoint(cfg: EndpointConfigPayload) -> JSONResponse:
    if cfg.api_key:
        vault_proxy.register_secret("CUSTOM_ENDPOINT_API_KEY", cfg.api_key)
    # Add target host to allowlist
    host = cfg.base_url.split("//")[-1].split("/")[0].split(":")[0].lower()
    if host:
        vault_proxy.allowlisted_hosts.add(host)
    check = vault_proxy.inspect_and_inject_outbound_request(cfg.base_url)
    return JSONResponse({
        "status": "ok",
        "allowlisted": check.allowed,
        "target_url": cfg.base_url,
        "wire_protocol": cfg.wire_protocol,
        "model": cfg.model,
        "vault_sealed": bool(cfg.api_key),
    })


@app.post("/api/chat/assemble")
def assemble_three_layer_turn(turn: ChatTurnPayload) -> JSONResponse:
    assembler = ThreeLayerCacheAssembler(
        model=turn.model,
        system_prompt=f"You are cod.ai operating in {turn.polarity_mode}.",
        layer2_project_context="# CLAUDE.md\nPreserve 3-layer prefix cache.",
    )
    assembler.append_user_message(
        turn.prompt,
        system_reminders=[f"Active Specialist: {turn.specialist_slug} | Effort: {turn.effort}"],
    )
    req = assembler.assemble_request()
    return JSONResponse({
        "model": req.model,
        "layer1_hash": req.layer1_hash,
        "layer2_hash": req.layer2_hash,
        "layer1_tokens": req.layer1_tokens,
        "layer2_tokens": req.layer2_tokens,
        "layer3_tokens": req.layer3_tokens,
        "breakpoint_count": req.breakpoint_count,
        "output_config": {"effort": turn.effort},
        "thinking": {"type": "adaptive", "display": turn.thinking_display},
    })


@app.get("/api/telemetry")
def get_live_telemetry() -> dict[str, Any]:
    snap = telemetry_engine.run_skill_doctor(
        session_id="sess_web_opus_5_5",
        model="claude-opus-5-5",
        active_tokens=185_000,
        context_window=1_000_000,
        cache_read_tokens=480_000,
        cache_write_tokens=45_000,
        cache_rebilled_usd=0.0,
        tokens_before_compact=760_000,
        tokens_after_compact=190_000,
        retrieved_items=["cache_assembler.py", "ttl_scheduler.py"],
        relevant_items={"cache_assembler.py", "ttl_scheduler.py"},
    )
    return {
        "session_id": snap.session_id,
        "model": snap.model,
        "context_utilization_pct": snap.context_utilization_pct,
        "cache_hit_rate_pct": snap.cache_hit_rate_pct,
        "cache_rebilled_usd": snap.cache_rebilled_usd,
        "compression_ratio": snap.compression_ratio,
        "retrieval_precision_pct": snap.retrieval_precision_pct,
    }
