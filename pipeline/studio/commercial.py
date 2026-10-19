"""Commercial controls for the local studio and a hosted deployment path.

The local account is intentionally single-user. Stripe and external auth are opt-in through
environment variables; no payment or invitation is sent by merely opening Channel Studio.
"""
from pathlib import Path
from uuid import uuid4
import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from pipeline.core.config import settings
from pipeline.models.entities import CreditLedger, WorkspaceAccount, WorkspaceMember, WorkspaceSubscription
from pipeline.storage.db import get_db
from pipeline.providers.registry import voice_provider

router = APIRouter(prefix="/commercial", tags=["Commercial controls"])


def ensure_workspace(db: Session) -> WorkspaceAccount:
    account = db.scalars(select(WorkspaceAccount).order_by(WorkspaceAccount.created_at)).first()
    if account:
        return account
    account = WorkspaceAccount(name="Local Studio", owner_email="editor@aivatar.local")
    db.add(account)
    db.flush()
    db.add(WorkspaceMember(workspace_id=account.id, email=account.owner_email, role="owner"))
    db.add(CreditLedger(workspace_id=account.id, delta=settings.aivatar_default_credits,
                        reason="local development allowance", provider="local"))
    db.add(WorkspaceSubscription(workspace_id=account.id, plan="free", status="inactive"))
    db.commit()
    db.refresh(account)
    return account


def commercial_status(db: Session) -> dict:
    account = ensure_workspace(db)
    members = db.scalars(select(WorkspaceMember).where(WorkspaceMember.workspace_id == account.id)
                         .order_by(WorkspaceMember.created_at)).all()
    subscription = db.scalars(select(WorkspaceSubscription).where(WorkspaceSubscription.workspace_id == account.id)).first()
    credits = db.scalar(select(func.coalesce(func.sum(CreditLedger.delta), 0.0))
                         .where(CreditLedger.workspace_id == account.id)) or 0.0
    return {
        "workspace": {"id": account.id, "name": account.name, "owner_email": account.owner_email},
        "members": [{"id": m.id, "email": m.email, "role": m.role} for m in members],
        "credits": round(float(credits), 3),
        "subscription": {"plan": subscription.plan, "status": subscription.status} if subscription else None,
        "features": {
            "voice_preview": True,
            "automatic_music": True,
            "transitions": ["cut", "crossfade", "fade", "wipeleft", "slideright"],
            "scene_direction": True,
            "team_roles": settings.aivatar_auth_mode != "local",
            "stripe_subscriptions": bool(settings.stripe_secret_key and settings.stripe_price_id),
            "stripe_prepaid_credits": bool(settings.stripe_secret_key and settings.stripe_credit_price_id),
        },
        "deployment": {"auth_mode": settings.aivatar_auth_mode, "public_base_url": settings.aivatar_public_base_url,
                       "stripe_configured": bool(settings.stripe_secret_key),
                       "note": "Local mode is single-user. Configure auth and Stripe before inviting real customers."},
    }


@router.get("/status")
def status(db: Session = Depends(get_db)):
    return commercial_status(db)


class PreviewRequest(BaseModel):
    text: str = Field(min_length=2, max_length=1200)
    provider: str = "ai33"
    voice_id: str | None = None


@router.post("/voice-preview")
def voice_preview(payload: PreviewRequest):
    """Render a short preview through the configured voice provider; never falls back silently."""
    if payload.provider == "mock_voice":
        raise HTTPException(422, "Choose a configured voice provider for a commercial preview")
    output_dir = settings.aivatar_workspace / "previews" / str(uuid4())
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        result = voice_provider(payload.provider).generate(payload.text, min(12.0, max(1.0, len(payload.text.split()) / 2.2)),
                                                           output_dir, voice_id=payload.voice_id)
    except (ValueError, RuntimeError, OSError) as exc:
        raise HTTPException(409, "Voice preview failed. Check the configured provider and voice ID.") from exc
    return {"preview_url": f"/studio/commercial/previews/{output_dir.name}/{result.path.name}",
            "provider": result.provider, "duration": result.duration, "reported_cost_usd": result.actual_cost_usd}


@router.get("/previews/{preview_id}/{filename}")
def preview_file(preview_id: str, filename: str):
    path = (settings.aivatar_workspace / "previews" / preview_id / filename).resolve()
    base = (settings.aivatar_workspace / "previews").resolve()
    if base not in path.parents or not path.is_file():
        raise HTTPException(404, "Preview not found")
    return FileResponse(path, media_type="audio/wav" if path.suffix == ".wav" else "audio/mpeg")


class DirectionRequest(BaseModel):
    script: str = Field(min_length=1, max_length=100000)
    visual_style: str = Field(default="cinematic documentary", max_length=1000)
    scene_seconds: int = Field(default=12, ge=5, le=15)


@router.post("/scene-direction")
def scene_direction(payload: DirectionRequest):
    """Create an inspectable first-pass scene direction without sending script data to a vendor."""
    words = payload.script.split()
    count = max(1, min(24, (len(words) + 39) // 40))
    scenes = []
    for i in range(count):
        chunk = words[i * len(words) // count:(i + 1) * len(words) // count]
        narration = " ".join(chunk)
        focus = "presenter close-up" if i == 0 or i == count - 1 else "supporting b-roll with gentle motion"
        scenes.append({"ordinal": i + 1, "narration": narration, "direction": f"{focus}; {payload.visual_style}; clean composition; no generated text"})
    return {"mode": "assisted", "scenes": scenes, "note": "Review the suggestions before generating; the script is unchanged."}


@router.get("/music/recommend")
def recommend_music(mood: str = "calm documentary"):
    catalog = settings.aivatar_music_catalog_dir
    candidates = sorted(p for p in catalog.glob("*") if p.suffix.lower() in {".mp3", ".wav", ".m4a"})
    if not candidates:
        return {"selected": None, "mood": mood, "note": "Add licensed tracks to the local music catalog to enable automatic selection."}
    # Deterministic selection keeps previews reproducible and avoids random spend.
    selected = candidates[abs(hash(mood)) % len(candidates)]
    return {"selected": str(selected.resolve()), "mood": mood, "note": "Selected from the licensed local catalog."}


class InviteRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    role: str = Field(default="editor", pattern="^(admin|editor|viewer)$")


@router.post("/members")
def invite_member(payload: InviteRequest, db: Session = Depends(get_db)):
    if settings.aivatar_auth_mode == "local":
        raise HTTPException(409, "Team invitations require a hosted auth mode")
    account = ensure_workspace(db)
    member = WorkspaceMember(workspace_id=account.id, email=payload.email.strip().lower(), role=payload.role)
    db.add(member); db.commit(); db.refresh(member)
    return {"id": member.id, "email": member.email, "role": member.role, "status": "invited"}


class CheckoutRequest(BaseModel):
    kind: str = Field(pattern="^(subscription|credits)$")
    success_url: str | None = None
    cancel_url: str | None = None


@router.post("/checkout")
def checkout(payload: CheckoutRequest, db: Session = Depends(get_db)):
    price_id = settings.stripe_price_id if payload.kind == "subscription" else settings.stripe_credit_price_id
    if not settings.stripe_secret_key or not price_id:
        raise HTTPException(409, "Stripe is not configured. Add STRIPE_SECRET_KEY and the matching price ID on the server.")
    account = ensure_workspace(db)
    data = {"mode": "subscription" if payload.kind == "subscription" else "payment",
            "line_items[0][price]": price_id, "line_items[0][quantity]": "1",
            "success_url": payload.success_url or f"{settings.aivatar_public_base_url}/channel-studio?checkout=success",
            "cancel_url": payload.cancel_url or f"{settings.aivatar_public_base_url}/channel-studio?checkout=cancel",
            "client_reference_id": account.id}
    try:
        with httpx.Client(timeout=20) as client:
            response = client.post("https://api.stripe.com/v1/checkout/sessions", data=data,
                                   auth=(settings.stripe_secret_key, ""))
            response.raise_for_status()
            session = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(502, "Stripe checkout could not be created") from exc
    return {"checkout_url": session.get("url"), "session_id": session.get("id"), "kind": payload.kind}
