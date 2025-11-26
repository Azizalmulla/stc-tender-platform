"""
Export File Storage Model
Stores master Excel files in database for persistent storage
"""
from sqlalchemy import Column, Integer, String, LargeBinary, DateTime, Text
from sqlalchemy.sql import func
from app.db.session import Base


class ExportFile(Base):
    """Store master export files in database"""
    __tablename__ = "export_files"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # File identifier (e.g., "stc_master" for STC's master workbook)
    name = Column(String(100), unique=True, nullable=False, index=True)
    
    # The actual Excel file bytes
    file_data = Column(LargeBinary, nullable=False)
    
    # Metadata
    description = Column(Text)
    file_size = Column(Integer)  # Size in bytes
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Track how many rows have been added
    total_rows_exported = Column(Integer, default=0)
