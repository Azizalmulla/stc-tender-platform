"""
STC Template Excel Export Service
Generates Excel files matching STC's template structure with 5 sheets
"""
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from typing import List, Dict
from io import BytesIO
from sqlalchemy.orm import Session
from app.models.tender import Tender
from datetime import datetime


# Reference lists matching STC template
BIDDING_COMPANIES = ["STC", "SSTC", "ePortal", "CDN", "JMT", "AlDar", "H3"]

SECTORS = ["Government", "Oil & Gas", "Banking", "Private", "Telecom"]

TENDER_TYPES = [
    "CTC", "Semi-Tender", "Direct Tender", "RFP", "RFQ", "RFI",
    "Budgetary", "Writing RFP", "Pre-Qualification", "Auction"
]

ACCOUNT_MANAGERS = [
    "Ahmed El Henawy", "Ahmed Al Rahwan", "Amr El-Ragal", "Hany Ismail",
    "Mohamed Abuzarqa", "Mohsin Abdelrazig", "Rafik Hafez", "Syed Mohsin",
    "Issa Alsuwait", "Arpan Panigrahy", "Bharath Bilimaga", "Hursh Chandhok",
    "Mohamed Ibrahim", "Mohammad Hasan", "Noha Saranek", "Sachin Khan",
    "Samer Al Khatib"
]

JUSTIFICATIONS = [
    "Does Not Meet Qualifications",
    "Price Protected for Others",
    "Non-Compliance with Technical Specifications",
    "Outside Scope of Our Services",
    "Short Notice/Need More Time",
    "Over Budget"
]

ANNOUNCEMENT_TYPES = [
    "Awarding", "Complaint", "Opening Envelopes", "Cancellation",
    "Contract Extension", "Reconsideration", "Renew Bid Bond"
]


class STCTemplateExporter:
    """Generate Excel files matching STC template"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def generate_excel(self, tender_ids: List[int]) -> bytes:
        """
        Generate Excel file with 5 sheets matching STC template
        
        Args:
            tender_ids: List of tender IDs to export
            
        Returns:
            Excel file as bytes
        """
        # Fetch tenders
        tenders = self.db.query(Tender).filter(Tender.id.in_(tender_ids)).all()
        
        if not tenders:
            raise ValueError("No tenders found with provided IDs")
        
        # Create workbook
        wb = Workbook()
        # Remove default sheet
        wb.remove(wb.active)
        
        # Group tenders by status/sheet
        released_tenders = []
        future_tenders = []
        awarded_tenders = []
        
        for tender in tenders:
            status = (tender.status or "Released").lower()
            if status in ['future', 'upcoming', 'planned']:
                future_tenders.append(tender)
            elif status in ['awarded', 'opened', 'cancelled']:
                awarded_tenders.append(tender)
            else:  # default to released
                released_tenders.append(tender)
        
        # Create sheets in order
        self._create_released_tenders_sheet(wb, released_tenders)
        self._create_future_tenders_sheet(wb, future_tenders)
        self._create_awarded_opened_sheet(wb, awarded_tenders)
        self._create_color_coding_sheet(wb)
        self._create_list_sheet(wb)
        
        # Save to bytes
        output = BytesIO()
        wb.save(output)
        output.seek(0)
        return output.read()
    
    def _create_released_tenders_sheet(self, wb: Workbook, tenders: List[Tender]):
        """Create Released Tenders sheet"""
        ws = wb.create_sheet("Released Tenders", 0)
        
        # Header at row 5
        headers = [
            "", "No.", "Kuwait Alyoum NO.", "Kuwait Alyoum Date.",
            "Kuwait Alyoum Page No.", "Customer Name", "Bidding Company",
            "Sector", "Tender Type", "Tender No.", "Tender Title", "Tender Fee"
        ]
        
        for col_idx, header in enumerate(headers, 1):
            cell = ws.cell(5, col_idx, header)
            cell.font = Font(bold=True)
            cell.fill = PatternFill(start_color="D9E1F2", end_color="D9E1F2", fill_type="solid")
            cell.alignment = Alignment(horizontal="center", vertical="center")
        
        # Data rows starting from row 6
        for idx, tender in enumerate(tenders, 1):
            row = 5 + idx
            
            ws.cell(row, 1, "")  # Empty column A
            ws.cell(row, 2, idx)  # No.
            ws.cell(row, 3, self._get_gazette_number(tender))
            ws.cell(row, 4, self._format_date(tender.published_at))
            ws.cell(row, 5, self._get_page_number(tender))
            ws.cell(row, 6, tender.ministry or "")
            ws.cell(row, 7, tender.bidding_company or "")
            ws.cell(row, 8, tender.sector or "")
            ws.cell(row, 9, tender.tender_type or "")
            ws.cell(row, 10, tender.tender_number or "")
            ws.cell(row, 11, tender.title or "")
            ws.cell(row, 12, float(tender.tender_fee) if tender.tender_fee else "")
        
        # Auto-size columns
        for col in ws.columns:
            max_length = 0
            column = col[0].column_letter
            for cell in col:
                if cell.value:
                    max_length = max(max_length, len(str(cell.value)))
            adjusted_width = min(max_length + 2, 50)
            ws.column_dimensions[column].width = adjusted_width
    
    def _create_future_tenders_sheet(self, wb: Workbook, tenders: List[Tender]):
        """Create Future Tenders sheet"""
        ws = wb.create_sheet("Future Tenders", 1)
        
        # Header at row 5
        headers = [
            "No.", "Customer Name", "Bidding Company", "Sector", "Tender Type",
            "Tender No.", "Tender Title", "Release Date", "Expected Value",
            "Status", "Justification", "Type of Announcement"
        ]
        
        for col_idx, header in enumerate(headers, 1):
            cell = ws.cell(5, col_idx, header)
            cell.font = Font(bold=True)
            cell.fill = PatternFill(start_color="D9E1F2", end_color="D9E1F2", fill_type="solid")
            cell.alignment = Alignment(horizontal="center", vertical="center")
        
        # Data rows
        for idx, tender in enumerate(tenders, 1):
            row = 5 + idx
            
            ws.cell(row, 1, idx)
            ws.cell(row, 2, tender.ministry or "")
            ws.cell(row, 3, tender.bidding_company or "")
            ws.cell(row, 4, tender.sector or "")
            ws.cell(row, 5, tender.tender_type or "")
            ws.cell(row, 6, tender.tender_number or "")
            ws.cell(row, 7, tender.title or "")
            ws.cell(row, 8, self._format_date(tender.release_date))
            ws.cell(row, 9, float(tender.expected_value) if tender.expected_value else "")
            ws.cell(row, 10, tender.status or "")
            ws.cell(row, 11, tender.justification or "")
            ws.cell(row, 12, tender.announcement_type or "")
        
        # Auto-size columns
        for col in ws.columns:
            max_length = 0
            column = col[0].column_letter
            for cell in col:
                if cell.value:
                    max_length = max(max_length, len(str(cell.value)))
            adjusted_width = min(max_length + 2, 50)
            ws.column_dimensions[column].width = adjusted_width
    
    def _create_awarded_opened_sheet(self, wb: Workbook, tenders: List[Tender]):
        """Create Awarded-Opened Tenders sheet"""
        ws = wb.create_sheet("Awarded-Opened Tenders", 2)
        
        # Header at row 5
        headers = [
            "No.", "Customer Name", "Bidding Company", "Sector", "Tender Type",
            "Tender No.", "Tender Title", "Status", "Awarded Vendor",
            "Awarded Value", "Justification", "Type of Announcement"
        ]
        
        for col_idx, header in enumerate(headers, 1):
            cell = ws.cell(5, col_idx, header)
            cell.font = Font(bold=True)
            cell.fill = PatternFill(start_color="D9E1F2", end_color="D9E1F2", fill_type="solid")
            cell.alignment = Alignment(horizontal="center", vertical="center")
        
        # Data rows
        for idx, tender in enumerate(tenders, 1):
            row = 5 + idx
            
            ws.cell(row, 1, idx)
            ws.cell(row, 2, tender.ministry or "")
            ws.cell(row, 3, tender.bidding_company or "")
            ws.cell(row, 4, tender.sector or "")
            ws.cell(row, 5, tender.tender_type or "")
            ws.cell(row, 6, tender.tender_number or "")
            ws.cell(row, 7, tender.title or "")
            ws.cell(row, 8, tender.status or "")
            ws.cell(row, 9, tender.awarded_vendor or "")
            ws.cell(row, 10, float(tender.awarded_value) if tender.awarded_value else "")
            ws.cell(row, 11, tender.justification or "")
            ws.cell(row, 12, tender.announcement_type or "")
        
        # Auto-size columns
        for col in ws.columns:
            max_length = 0
            column = col[0].column_letter
            for cell in col:
                if cell.value:
                    max_length = max(max_length, len(str(cell.value)))
            adjusted_width = min(max_length + 2, 50)
            ws.column_dimensions[column].width = adjusted_width
    
    def _create_color_coding_sheet(self, wb: Workbook):
        """Create Color Coding legend sheet"""
        ws = wb.create_sheet("Color Coding", 3)
        
        ws.cell(1, 1, "Color Legend")
        ws.cell(1, 1).font = Font(bold=True, size=14)
        
        ws.cell(3, 1, "Released Tenders")
        ws.cell(3, 1).fill = PatternFill(start_color="D9E1F2", end_color="D9E1F2", fill_type="solid")
        
        ws.cell(4, 1, "Future Tenders")
        ws.cell(4, 1).fill = PatternFill(start_color="E2EFDA", end_color="E2EFDA", fill_type="solid")
        
        ws.cell(5, 1, "Awarded / Opened")
        ws.cell(5, 1).fill = PatternFill(start_color="FCE4D6", end_color="FCE4D6", fill_type="solid")
        
        ws.column_dimensions['A'].width = 30
    
    def _create_list_sheet(self, wb: Workbook):
        """Create reference lists sheet"""
        ws = wb.create_sheet("List", 4)
        
        # Bidding Company (Column B)
        ws.cell(1, 2, "Bidding Company")
        ws.cell(1, 2).font = Font(bold=True)
        for idx, company in enumerate(BIDDING_COMPANIES, 2):
            ws.cell(idx, 2, company)
        
        # Sector (Column D)
        ws.cell(1, 4, "Sector")
        ws.cell(1, 4).font = Font(bold=True)
        for idx, sector in enumerate(SECTORS, 2):
            ws.cell(idx, 4, sector)
        
        # Tender Type (Column F)
        ws.cell(1, 6, "Tender Type")
        ws.cell(1, 6).font = Font(bold=True)
        for idx, tender_type in enumerate(TENDER_TYPES, 2):
            ws.cell(idx, 6, tender_type)
        
        # Account Manager (Column H)
        ws.cell(1, 8, "Account Manager")
        ws.cell(1, 8).font = Font(bold=True)
        for idx, manager in enumerate(ACCOUNT_MANAGERS, 2):
            ws.cell(idx, 8, manager)
        
        # Justification (Column J)
        ws.cell(1, 10, "Justification")
        ws.cell(1, 10).font = Font(bold=True)
        for idx, justification in enumerate(JUSTIFICATIONS, 2):
            ws.cell(idx, 10, justification)
        
        # Type of Announcement (Column L)
        ws.cell(1, 12, "Type of Announcement")
        ws.cell(1, 12).font = Font(bold=True)
        for idx, announcement in enumerate(ANNOUNCEMENT_TYPES, 2):
            ws.cell(idx, 12, announcement)
        
        # Auto-size all columns
        for col in ['B', 'D', 'F', 'H', 'J', 'L']:
            ws.column_dimensions[col].width = 30
    
    def _get_gazette_number(self, tender: Tender) -> str:
        """Extract gazette number from tender"""
        # Try to get from gazette_id or edition_no attributes
        if hasattr(tender, 'gazette_id') and tender.gazette_id:
            return str(tender.gazette_id)
        if hasattr(tender, 'edition_no') and tender.edition_no:
            return str(tender.edition_no)
        return ""
    
    def _get_page_number(self, tender: Tender) -> str:
        """Extract page number from tender"""
        if hasattr(tender, 'page_number') and tender.page_number:
            return str(tender.page_number)
        return ""
    
    def _format_date(self, date_value) -> str:
        """Format date for Excel"""
        if not date_value:
            return ""
        if isinstance(date_value, datetime):
            return date_value.strftime("%Y-%m-%d")
        return str(date_value)
