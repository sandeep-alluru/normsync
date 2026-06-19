"""FastAPI REST wrapper for normsync.

Start:   uvicorn normsync.api:app --reload
Install: pip install "normsync[api]"
Docs:    http://localhost:8000/docs
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

try:
    from fastapi import FastAPI
    from pydantic import BaseModel
except ImportError as exc:
    raise ImportError("API server requires: pip install 'normsync[api]'") from exc

import time

from normsync.monitor import NormMonitor
from normsync.norm import AgentAction, WorldNorm
from normsync.store import NormStore

_store = NormStore()
_monitor = NormMonitor()


@asynccontextmanager
async def _lifespan(app: FastAPI) -> Any:
    for norm in _store.get_norms():
        if norm.active:
            _monitor.add_norm(norm)
    yield


app = FastAPI(
    title="normsync API",
    description="World constitution engine for norm-governed multi-agent games",
    version="0.1.0",
    lifespan=_lifespan,
)


class HealthResponse(BaseModel):
    status: str
    version: str


class NormRequest(BaseModel):
    name: str
    description: str
    condition: str
    prohibited: str
    scope: str = "global"
    priority: int = 0


class NormResponse(BaseModel):
    id: str
    name: str
    description: str
    condition: str
    prohibited: str
    scope: str
    active: bool
    priority: int


class CheckRequest(BaseModel):
    agent_id: str
    action: str
    location: str = ""
    target: str = ""
    faction: str = ""


class ViolationResponse(BaseModel):
    id: str
    norm_id: str
    norm_name: str
    action_id: str
    agent_id: str
    description: str
    severity: str
    timestamp: float


@app.get("/health", response_model=HealthResponse)
async def health() -> dict[str, Any]:
    """Liveness probe."""
    from normsync import __version__

    return {"status": "ok", "version": __version__}


@app.post("/norm", response_model=NormResponse)
async def add_norm(req: NormRequest) -> dict[str, Any]:
    """Add a new norm to the constitution."""
    norm = WorldNorm(
        name=req.name,
        description=req.description,
        condition=req.condition,
        prohibited=req.prohibited,
        scope=req.scope,
        priority=req.priority,
    )
    _store.save_norm(norm)
    _monitor.add_norm(norm)
    return norm.to_dict()


@app.get("/norms")
async def list_norms() -> list[dict[str, Any]]:
    """List all norms."""
    return [n.to_dict() for n in _store.get_norms()]


@app.post("/check")
async def check_action(req: CheckRequest) -> dict[str, Any]:
    """Check an action against active norms."""
    act = AgentAction(
        agent_id=req.agent_id,
        action=req.action,
        location=req.location,
        target=req.target,
        faction=req.faction,
        timestamp=time.time(),
    )
    violations = _monitor.check(act)
    for v in violations:
        _store.save_violation(v)
    return {
        "violation_count": len(violations),
        "has_violations": len(violations) > 0,
        "violations": [v.to_dict() for v in violations],
    }


@app.get("/violations")
async def list_violations() -> list[dict[str, Any]]:
    """List all recorded violations."""
    return [v.to_dict() for v in _store.get_violations()]
