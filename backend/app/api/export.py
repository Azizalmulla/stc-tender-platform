"""
STC Template Export API
Endpoint for exporting tenders to Excel matching STC template
"""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.export.stc_template_service import STCTemplateExporter
from datetime import datetime
import io


router = APIRouter(prefix="/export", tags=["export"])


class ExportRequest(BaseModel):
    """Request model for STC template export"""
    tender_ids: List[int]
    
    class Config:
        json_schema_extra = {
            "example": {
                "tender_ids": [1, 2, 3, 4, 5]
            }
        }


@router.post("/stc-template")
async def export_stc_template(
    request: ExportRequest,
    db: Session = Depends(get_db)
):
    """
    Export selected tenders to Excel file matching STC template
    
    The Excel file contains 5 sheets:
    1. Released Tenders
    2. Future Tenders  
    3. Awarded-Opened Tenders
    4. Color Coding (legend)
    5. List (reference values)
    
    Tenders are automatically routed to the correct sheet based on their status.
    
    Args:
        request: List of tender IDs to export
        db: Database session
        
    Returns:
        Excel file (.xlsx) ready for download
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
        # Generate Excel file
        exporter = STCTemplateExporter(db)
        excel_bytes = exporter.generate_excel(request.tender_ids)
        
        # Generate filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"STC_Tenders_Export_{timestamp}.xlsx"
        
        # Return as downloadable file
        return StreamingResponse(
            io.BytesIO(excel_bytes),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f"attachment; filename={filename}",
                "Access-Control-Expose-Headers": "Content-Disposition"
            }
        )
        
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        print(f"❌ Export error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate Excel export: {str(e)}"
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
