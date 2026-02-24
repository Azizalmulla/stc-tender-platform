"""
STC Template Export API

MASTER WORKBOOK APPROACH:
- Maintains ONE master Excel file that grows over time
- Each export APPENDS to the same file (not creates new)
- Tracks exported tenders to prevent duplicates
- Uses Redis locking for concurrent access safety
"""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Optional
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.export.stc_template_service import STCTemplateExporter
from app.models.export_file import ExportFile
from datetime import datetime
import io
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/export", tags=["export"])


class ExportRequest(BaseModel):
    """Request model for STC template export"""
    tender_ids: List[int]
    skip_duplicates: bool = True  # Skip already-exported tenders
    
    class Config:
        json_schema_extra = {
            "example": {
                "tender_ids": [1, 2, 3, 4, 5],
                "skip_duplicates": True
            }
        }


@router.post("/stc-template")
async def export_stc_template(
    request: ExportRequest,
    db: Session = Depends(get_db)
):
    """
    Export selected tenders to STC Master Excel file
    
    MASTER WORKBOOK APPROACH:
    - First export: Creates new master workbook
    - Subsequent exports: APPENDS to existing master
    - Same file grows over time with all exported tenders
    - Automatically skips already-exported tenders (unless skip_duplicates=False)
    
    The Excel file contains 5 sheets:
    1. Released Tenders
    2. Future Tenders  
    3. Awarded-Opened Tenders
    4. Color Coding (legend)
    5. List (reference values)
    
    Args:
        request: 
            - tender_ids: List of tender IDs to export
            - skip_duplicates: If True, skip already-exported tenders
        
    Returns:
        Updated master Excel file (.xlsx)
    """
    # Validate request
    if not request.tender_ids:
        raise HTTPException(
            status_code=400,
            detail="No tender IDs provided. Please select at least one tender to export."
        )
    
    if len(request.tender_ids) > 1000:
        raise HTTPException(
            status_code=400,
            detail="Too many tenders selected. Maximum is 1000 per export."
        )
    
    try:
        # Try to acquire Redis lock for concurrent access safety
        lock_acquired = False
        try:
            from app.core.redis_config import get_redis_connection
            redis = get_redis_connection()
            if redis:
                lock = redis.lock("stc_export_lock", timeout=120)
                lock_acquired = lock.acquire(blocking=True, blocking_timeout=10)
                if not lock_acquired:
                    raise HTTPException(
                        status_code=423,
                        detail="Another export is in progress. Please wait a moment and try again."
                    )
        except ImportError:
            logger.warning("Redis not available, proceeding without lock")
        except Exception as e:
            logger.warning(f"Redis lock failed, proceeding without lock: {e}")
        
        try:
            # Generate/update Excel file
            exporter = STCTemplateExporter(db)
            excel_bytes = exporter.generate_excel(
                request.tender_ids,
                skip_duplicates=request.skip_duplicates
            )
            
            # Always use the same filename - it's the MASTER file
            filename = "STC_Tenders_Master.xlsx"
            
            logger.info(f"✅ Export complete: {filename}")
            
            # Return as downloadable file
            return StreamingResponse(
                io.BytesIO(excel_bytes),
                media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                headers={
                    "Content-Disposition": f"attachment; filename={filename}",
                    "Access-Control-Expose-Headers": "Content-Disposition"
                }
            )
        finally:
            # Release lock if acquired
            if lock_acquired:
                try:
                    lock.release()
                except:
                    pass
        
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Export error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate Excel export: {str(e)}"
        )


@router.get("/stc-template/stats")
async def get_export_stats(db: Session = Depends(get_db)):
    """
    Get statistics about the STC master workbook
    
    Returns:
        - total_rows: Total tenders exported
        - file_size: Size of master file in bytes
        - last_updated: When the master was last updated
    """
    export_file = db.query(ExportFile).filter(
        ExportFile.name == "stc_master"
    ).first()
    
    if not export_file:
        return {
            "exists": False,
            "total_rows": 0,
            "file_size": 0,
            "last_updated": None
        }
    
    return {
        "exists": True,
        "total_rows": export_file.total_rows_exported,
        "file_size": export_file.file_size,
        "last_updated": export_file.updated_at.isoformat() if export_file.updated_at else None,
        "created_at": export_file.created_at.isoformat() if export_file.created_at else None
    }


@router.delete("/stc-template/reset")
async def reset_master_workbook(db: Session = Depends(get_db)):
    """
    Reset the STC master workbook (delete and start fresh)
    
    WARNING: This will delete all export history!
    
    Also resets the exported_to_stc_at flag on all tenders.
    """
    from app.models.tender import Tender
    
    # Delete the master file
    export_file = db.query(ExportFile).filter(
        ExportFile.name == "stc_master"
    ).first()
    
    if export_file:
        db.delete(export_file)
    
    # Reset all tender export flags
    db.query(Tender).filter(
        Tender.exported_to_stc_at.isnot(None)
    ).update({"exported_to_stc_at": None})
    
    db.commit()
    
    logger.info("✅ Master workbook reset complete")
    
    return {"status": "reset", "message": "Master workbook deleted and all tender export flags cleared"}


@router.get("/tenders")
async def export_tenders_generic(
    days_back: int = 7,
    category: str = None,
    sector: str = None,
    db: Session = Depends(get_db)
):
    """
    Export recent tech tenders to a clean generic Excel file.

    Args:
        days_back: How many days back to include (default 7)
        category: Optional filter (tenders/auctions/practices)
        sector: Optional filter by sector tag
    """
    from app.export.generic_export_service import GenericTenderExporter
    exporter = GenericTenderExporter(db)
    excel_bytes = exporter.generate_excel(days_back=days_back, category=category, sector=sector)
    from datetime import datetime
    filename = f"Kuwait_Tech_Tenders_{datetime.now().strftime('%Y-%m-%d')}.xlsx"
    return StreamingResponse(
        io.BytesIO(excel_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename={filename}",
            "Access-Control-Expose-Headers": "Content-Disposition"
        }
    )


@router.get("/reference-lists")
async def get_reference_lists():
    """
    Get reference lists for dropdown values
    
    Returns the controlled vocabularies used in STC template:
    - Bidding Companies
    - Sectors
    - Tender Types
    - Account Managers
    - Justifications
    - Announcement Types
    """
    from app.export.stc_template_service import (
        BIDDING_COMPANIES, SECTORS, TENDER_TYPES,
        ACCOUNT_MANAGERS, JUSTIFICATIONS, ANNOUNCEMENT_TYPES
    )
    
    return {
        "bidding_companies": BIDDING_COMPANIES,
        "sectors": SECTORS,
        "tender_types": TENDER_TYPES,
        "account_managers": ACCOUNT_MANAGERS,
        "justifications": JUSTIFICATIONS,
        "announcement_types": ANNOUNCEMENT_TYPES
    }
