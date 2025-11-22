"""
PDF metadata extraction and downloading
Text extraction is handled by Mistral OCR / Claude services
"""
import fitz  # PyMuPDF
import requests
from typing import Optional, Dict
import tempfile
import os


class PDFExtractor:
    """Download PDFs and extract metadata (page count, etc.). OCR is handled separately by Mistral/Claude."""
    
    def __init__(self):
        self.timeout = 60  # seconds
        self.max_size = 50 * 1024 * 1024  # 50MB max file size
    
    def download_pdf(self, url: str) -> Optional[bytes]:
        """
        Download PDF from URL
        
        Args:
            url: PDF URL
            
        Returns:
            PDF content as bytes or None if failed
        """
        try:
            print(f"  📥 Downloading PDF: {url}")
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            response = requests.get(
                url, 
                headers=headers, 
                timeout=self.timeout,
                stream=True
            )
            response.raise_for_status()
            
            # Check content type
            content_type = response.headers.get('content-type', '').lower()
            if 'pdf' not in content_type and 'application/octet-stream' not in content_type:
                print(f"  ⚠️  Not a PDF: {content_type}")
                return None
            
            # Check file size
            content_length = response.headers.get('content-length')
            if content_length and int(content_length) > self.max_size:
                print(f"  ⚠️  PDF too large: {int(content_length) / 1024 / 1024:.1f}MB")
                return None
            
            # Download content
            pdf_content = response.content
            
            print(f"  ✅ Downloaded {len(pdf_content) / 1024:.1f}KB")
            return pdf_content
            
        except requests.RequestException as e:
            print(f"  ❌ Download failed: {e}")
            return None
        except Exception as e:
            print(f"  ❌ Error downloading PDF: {e}")
            return None
    
    
    def get_pdf_metadata(self, pdf_bytes: bytes) -> Dict:
        """
        Extract metadata from PDF
        
        Args:
            pdf_bytes: PDF content as bytes
            
        Returns:
            Dictionary with metadata
        """
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
                tmp_file.write(pdf_bytes)
                tmp_path = tmp_file.name
            
            try:
                doc = fitz.open(tmp_path)
                
                metadata = {
                    'page_count': len(doc),
                    'title': doc.metadata.get('title', ''),
                    'author': doc.metadata.get('author', ''),
                    'subject': doc.metadata.get('subject', ''),
                    'creator': doc.metadata.get('creator', ''),
                    'producer': doc.metadata.get('producer', ''),
                    'creation_date': doc.metadata.get('creationDate', ''),
                    'modification_date': doc.metadata.get('modDate', ''),
                }
                
                doc.close()
                
                return metadata
                
            finally:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
                    
        except Exception as e:
            print(f"  ⚠️  Metadata extraction failed: {e}")
            return {}
