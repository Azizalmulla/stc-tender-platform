import fitz  # PyMuPDF
from google.cloud import documentai_v1 as documentai
from google.oauth2 import service_account
from typing import Optional, Dict
import os
import base64
import json
import tempfile
from app.core.config import settings


class PDFParser:
    """Parse PDF files with OCR fallback"""
    
    def __init__(self):
        self.documentai_client = None
        self.processor_name = None
        
        # Try base64 encoded credentials first (for cloud deployment)
        base64_creds = os.getenv('GOOGLE_CLOUD_DOCUMENTAI_CREDENTIALS_BASE64')
        if base64_creds:
            try:
                creds_json = base64.b64decode(base64_creds).decode('utf-8')
                creds_dict = json.loads(creds_json)
                credentials = service_account.Credentials.from_service_account_info(creds_dict)
                self.documentai_client = documentai.DocumentProcessorServiceClient(
                    credentials=credentials
                )
                self.processor_name = settings.DOCUMENTAI_PROCESSOR_NAME
            except Exception as e:
                print(f"Error loading base64 credentials: {e}")
        # Fall back to file-based credentials (for local development)
        elif settings.GOOGLE_CLOUD_DOCUMENTAI_CREDENTIALS:
            credentials = service_account.Credentials.from_service_account_file(
                settings.GOOGLE_CLOUD_DOCUMENTAI_CREDENTIALS
            )
            self.documentai_client = documentai.DocumentProcessorServiceClient(
                credentials=credentials
            )
            self.processor_name = settings.DOCUMENTAI_PROCESSOR_NAME
    
    def extract_text(self, pdf_path: str) -> Dict[str, any]:
        """
        Extract text from PDF using native extraction or OCR
        
        Args:
            pdf_path: Path to PDF file
            
        Returns:
            Dict with extracted text and metadata
        """
        # Step 1: Try native text extraction
        text = self._extract_native_text(pdf_path)
        
        if self._is_valid_text(text):
            return {
                "text": text,
                "method": "native",
                "confidence": 1.0,
                "page_count": self._get_page_count(pdf_path)
            }
        
        # Step 2: Try Google Cloud Document AI
        if self.documentai_client and self.processor_name:
            text, confidence = self._extract_with_document_ai(pdf_path)
            if text and confidence > 0.7:
                return {
                    "text": text,
                    "method": "document_ai",
                    "confidence": confidence,
                    "page_count": self._get_page_count(pdf_path)
                }
        
        # Step 3: Fallback (return native text even if it's poor quality)
        return {
            "text": text or "",
            "method": "fallback",
            "confidence": 0.5,
            "page_count": self._get_page_count(pdf_path)
        }
    
    def _extract_native_text(self, pdf_path: str) -> str:
        """Extract text using PyMuPDF (native text layer)"""
        try:
            doc = fitz.open(pdf_path)
            text = ""
            
            for page_num in range(len(doc)):
                page = doc[page_num]
                text += page.get_text()
            
            doc.close()
            return text.strip()
            
        except Exception as e:
            print(f"Native text extraction failed: {e}")
            return ""
    
    def _extract_with_document_ai(self, pdf_path: str) -> tuple[str, float]:
        """
        Extract text using Google Cloud Document AI
        
        Returns:
            Tuple of (text, confidence_score)
        """
        try:
            # Read the PDF file
            with open(pdf_path, "rb") as f:
                pdf_content = f.read()
            
            # Configure the process request
            raw_document = documentai.RawDocument(
                content=pdf_content,
                mime_type="application/pdf"
            )
            
            request = documentai.ProcessRequest(
                name=self.processor_name,
                raw_document=raw_document
            )
            
            # Process the document
            result = self.documentai_client.process_document(request=request)
            document = result.document
            
            # Extract text and confidence
            text = document.text
            
            # Calculate average confidence from entities
            confidences = [entity.confidence for entity in document.entities if entity.confidence]
            avg_confidence = sum(confidences) / len(confidences) if confidences else 0.9
            
            return text, avg_confidence
            
        except Exception as e:
            print(f"Document AI OCR failed: {e}")
            return "", 0.0
    
    def _is_valid_text(self, text: str) -> bool:
        """Check if extracted text is valid and meaningful"""
        if not text or len(text.strip()) < 50:
            return False
        
        # Check for Arabic or English characters
        alpha_chars = sum(1 for c in text if c.isalpha())
        if alpha_chars < 20:
            return False
        
        return True
    
    def _get_page_count(self, pdf_path: str) -> int:
        """Get number of pages in PDF"""
        try:
            doc = fitz.open(pdf_path)
            count = len(doc)
            doc.close()
            return count
        except:
            return 0


class TextNormalizer:
    """Normalize Arabic text for better processing"""
    
    @staticmethod
    def normalize_arabic(text: str) -> str:
        """
        Normalize Arabic text:
        - Remove diacritics
        - Unify Alef variations
        - Unify Ya/Alef Maqsura
        - Convert Eastern Arabic numerals to Western
        """
        if not text:
            return ""
        
        # Remove diacritics (Tashkeel)
        diacritics = [
            '\u064B', '\u064C', '\u064D', '\u064E', '\u064F',
            '\u0650', '\u0651', '\u0652', '\u0653', '\u0654',
            '\u0655', '\u0656', '\u0657', '\u0658', '\u0670'
        ]
        for diacritic in diacritics:
            text = text.replace(diacritic, '')
        
        # Unify Alef variations
        alef_variations = ['آ', 'أ', 'إ', 'ا']
        for alef in alef_variations:
            text = text.replace(alef, 'ا')
        
        # Unify Ya and Alef Maqsura
        text = text.replace('ى', 'ي')
        
        # Convert Eastern Arabic numerals to Western
        eastern_to_western = str.maketrans('٠١٢٣٤٥٦٧٨٩', '0123456789')
        text = text.translate(eastern_to_western)
        
        return text.strip()
    
    @staticmethod
    def extract_keywords(text: str) -> list[str]:
        """Extract potential keywords from Arabic/English text"""
        # Simple keyword extraction (can be enhanced with NER)
        words = text.split()
        
        # Filter meaningful words (length > 3, not numbers)
        keywords = [
            word.strip('.,،:؛') 
            for word in words 
            if len(word) > 3 and not word.isdigit()
        ]
        
        return list(set(keywords))[:50]  # Return unique keywords, max 50
