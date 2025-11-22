import fitz  # PyMuPDF
from typing import Optional, Dict
import os


class PDFParser:
    """Parse PDF files using PyMuPDF for native text extraction. OCR is handled by Mistral/Claude services."""
    
    def __init__(self):
        pass
    
    def extract_text(self, pdf_path: str) -> Dict[str, any]:
        """
        Extract text from PDF using native extraction (PyMuPDF)
        
        Note: This only works for PDFs with text layers. For scanned PDFs/images,
        use Mistral OCR or Claude services instead.
        
        Args:
            pdf_path: Path to PDF file
            
        Returns:
            Dict with extracted text and metadata
        """
        # Try native text extraction
        text = self._extract_native_text(pdf_path)
        
        if self._is_valid_text(text):
            return {
                "text": text,
                "method": "pymupdf_native",
                "confidence": 1.0,
                "page_count": self._get_page_count(pdf_path)
            }
        
        # If no valid text found, return empty (caller should use OCR)
        return {
            "text": text or "",
            "method": "pymupdf_native",
            "confidence": 0.0,
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
        
        # Unify Ta Marbuta and Ha (for search flexibility)
        # This allows matching regardless of which one is used
        text = text.replace('ة', 'ه')
        
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
