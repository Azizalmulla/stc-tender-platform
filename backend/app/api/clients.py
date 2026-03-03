"""
Client management API for multi-tenant sector allowlisting.
Each client (company) has a list of sectors they care about.
Tenders are filtered per-client based on their sector allowlist.
"""
from fastapi import APIRouter, Depends, HTTPException, Header, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, or_
from typing import List, Optional
from datetime import datetime, timezone
from pydantic import BaseModel
import secrets

from app.db.session import get_db
from app.models.tender import Client, Tender
from app.core.config import settings


router = APIRouter()


# --- Pydantic Models ---

class ClientCreate(BaseModel):
    name: str
    chat_id: Optional[str] = None
    sectors: List[str] = []

class ClientUpdate(BaseModel):
    name: Optional[str] = None
    chat_id: Optional[str] = None
    sectors: Optional[List[str]] = None
    is_active: Optional[bool] = None

class ClientResponse(BaseModel):
    id: int
    name: str
    chat_id: Optional[str]
    sectors: List[str]
    is_active: bool
    api_key: Optional[str]
    created_at: Optional[datetime]
    
    class Config:
        from_attributes = True

class ClientTenderResponse(BaseModel):
    id: int
    url: str
    title: Optional[str]
    summary_ar: Optional[str]
    summary_en: Optional[str]
    ministry: Optional[str]
    category: Optional[str]
    tender_number: Optional[str]
    deadline: Optional[datetime]
    published_at: Optional[datetime]
    ai_sectors: Optional[List[str]]
    expected_value: Optional[float]
    
    class Config:
        from_attributes = True


# --- Auth helper ---

VALID_SECTORS = [
    "telecom", "datacenter", "callcenter", "network", "smartcity",
    "software", "construction", "medical", "oil_gas", "education",
    "security", "transport", "finance", "food", "facilities",
    "environment", "energy", "legal",
]

def _require_admin(authorization: Optional[str] = Header(None)):
    """Require CRON_SECRET for admin operations"""
    cron_secret = settings.CRON_SECRET if hasattr(settings, 'CRON_SECRET') else None
    if not cron_secret or authorization != f"Bearer {cron_secret}":
        raise HTTPException(status_code=401, detail="Unauthorized")


# --- Client CRUD ---

@router.post("/", response_model=ClientResponse)
async def create_client(
    client_data: ClientCreate,
    db: Session = Depends(get_db),
    _auth = Depends(_require_admin),
):
    """Create a new client with sector allowlist"""
    # Validate sectors
    invalid = [s for s in client_data.sectors if s not in VALID_SECTORS]
    if invalid:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid sectors: {invalid}. Valid: {VALID_SECTORS}"
        )
    
    # Check for duplicate chat_id
    if client_data.chat_id:
        existing = db.query(Client).filter(Client.chat_id == client_data.chat_id).first()
        if existing:
            raise HTTPException(status_code=409, detail=f"Client with chat_id {client_data.chat_id} already exists")
    
    client = Client(
        name=client_data.name,
        chat_id=client_data.chat_id,
        sectors=client_data.sectors,
        api_key=secrets.token_hex(32),
    )
    db.add(client)
    db.commit()
    db.refresh(client)
    return client


@router.get("/", response_model=List[ClientResponse])
async def list_clients(
    db: Session = Depends(get_db),
    _auth = Depends(_require_admin),
):
    """List all clients"""
    return db.query(Client).order_by(Client.created_at.desc()).all()


@router.get("/{client_id}", response_model=ClientResponse)
async def get_client(
    client_id: int,
    db: Session = Depends(get_db),
    _auth = Depends(_require_admin),
):
    """Get a specific client"""
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    return client


@router.put("/{client_id}", response_model=ClientResponse)
async def update_client(
    client_id: int,
    updates: ClientUpdate,
    db: Session = Depends(get_db),
    _auth = Depends(_require_admin),
):
    """Update a client's sectors or info"""
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    
    if updates.sectors is not None:
        invalid = [s for s in updates.sectors if s not in VALID_SECTORS]
        if invalid:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid sectors: {invalid}. Valid: {VALID_SECTORS}"
            )
        client.sectors = updates.sectors
    
    if updates.name is not None:
        client.name = updates.name
    if updates.chat_id is not None:
        client.chat_id = updates.chat_id
    if updates.is_active is not None:
        client.is_active = updates.is_active
    
    db.commit()
    db.refresh(client)
    return client


@router.delete("/{client_id}")
async def delete_client(
    client_id: int,
    db: Session = Depends(get_db),
    _auth = Depends(_require_admin),
):
    """Delete a client"""
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    
    db.delete(client)
    db.commit()
    return {"status": "deleted", "client_id": client_id}


# --- Client-filtered tenders ---

@router.get("/{client_id}/tenders", response_model=List[ClientTenderResponse])
async def get_client_tenders(
    client_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    days_back: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    _auth = Depends(_require_admin),
):
    """Get tenders filtered by this client's sector allowlist"""
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    
    if not client.sectors:
        raise HTTPException(status_code=400, detail="Client has no sectors configured")
    
    # Filter tenders where ai_sectors overlaps with client's sector allowlist
    from datetime import timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)
    
    # Use PostgreSQL array overlap operator (&&) for efficient sector matching
    tenders = db.query(Tender).filter(
        Tender.published_at >= cutoff,
        Tender.ai_sectors.op('&&')(client.sectors),
    ).order_by(
        Tender.published_at.desc(),
        Tender.id.desc(),
    ).offset(skip).limit(limit).all()
    
    return tenders


@router.get("/by-chat/{chat_id}/tenders", response_model=List[ClientTenderResponse])
async def get_tenders_by_chat_id(
    chat_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    days_back: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
):
    """
    Get tenders for a client identified by their Telegram chat_id.
    This endpoint is used by the Telegram bot skill to serve per-client filtered tenders.
    No admin auth required — the chat_id itself acts as the identifier.
    """
    client = db.query(Client).filter(
        Client.chat_id == chat_id,
        Client.is_active == True,
    ).first()
    
    if not client:
        # Fallback: if no client config exists, return all tenders (backward compatible)
        from datetime import timedelta
        cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)
        tenders = db.query(Tender).filter(
            Tender.published_at >= cutoff,
        ).order_by(
            Tender.published_at.desc(),
            Tender.id.desc(),
        ).offset(skip).limit(limit).all()
        return tenders
    
    if not client.sectors:
        return []
    
    from datetime import timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)
    
    tenders = db.query(Tender).filter(
        Tender.published_at >= cutoff,
        Tender.ai_sectors.op('&&')(client.sectors),
    ).order_by(
        Tender.published_at.desc(),
        Tender.id.desc(),
    ).offset(skip).limit(limit).all()
    
    return tenders


@router.get("/sectors/available")
async def list_available_sectors():
    """List all available sector codes that can be used in client allowlists"""
    return {
        "sectors": VALID_SECTORS,
        "descriptions": {
            "telecom": "Telecommunications, fiber, 5G, mobile networks",
            "datacenter": "Data centers, cloud, servers, hosting",
            "callcenter": "Call centers, contact centers, IVR",
            "network": "Networking, firewalls, routers, cybersecurity",
            "smartcity": "Smart city, IoT, sensors, automation",
            "software": "Software, ERP, apps, digital transformation",
            "construction": "Building, roads, bridges, civil works",
            "medical": "Medical equipment, pharmaceuticals, hospitals",
            "oil_gas": "Petroleum, refining, drilling, pipelines",
            "education": "Schools, universities, training",
            "security": "CCTV, surveillance, access control, defense",
            "transport": "Vehicles, fleet, aviation, marine, shipping",
            "finance": "Banking, insurance, financial systems",
            "food": "Catering, food supply, agriculture",
            "facilities": "Cleaning, maintenance, furniture, printing",
            "environment": "Waste management, water treatment, recycling",
            "energy": "Electricity, solar, renewable energy",
            "legal": "Legal services, consulting, auditing",
        }
    }
