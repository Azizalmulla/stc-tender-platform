import os
import time
import base64
from typing import Optional, Dict, Any, List

from mistralai import Mistral

from app.core.config import settings


class MistralOCRService:
    """Wrapper around Mistral OCR using client.ocr.process() with base64 data URLs.
    Supports images and PDFs.
    """

    def __init__(self) -> None:
        api_key = settings.MISTRAL_API_KEY or os.getenv("MISTRAL_API_KEY")
        if not api_key or api_key == "paste-your-mistral-api-key-here":
            raise ValueError("MISTRAL_API_KEY not configured")

        self.api_key = api_key
        self.client = Mistral(api_key=api_key)
        self.ocr_model = "mistral-ocr-latest"

    def _encode_to_data_url(self, content: bytes, mime_type: str) -> str:
        """Encode bytes to base64 data URL."""
        base64_content = base64.b64encode(content).decode('utf-8')
        return f"data:{mime_type};base64,{base64_content}"

    def _process_ocr(self, data_url: str) -> Optional[Dict[str, Any]]:
        """Process OCR using client.ocr.process() with data URL."""
        try:
            response = self.client.ocr.process(
                model=self.ocr_model,
                document={
                    "type": "image_url",
                    "image_url": data_url,
                }
            )
            
            # Extract pages from response
            if not response or not hasattr(response, 'pages'):
                print("  ⚠️  Mistral OCR returned no pages")
                return None
            
            return {"pages": [{
                "markdown": page.markdown
            } for page in response.pages]}
            
        except Exception as e:
            print(f"  ❌ Mistral OCR failed: {e}")
            return None

    def extract_text_from_image(
        self,
        image_bytes: bytes,
        image_format: str = "png",
        max_retries: int = 3,
    ) -> Optional[Dict[str, Any]]:
        """Run OCR on an image and return aggregated markdown text.

        Args:
            image_bytes: Image bytes (PNG, JPEG, etc.)
            image_format: Image format
            max_retries: Number of retry attempts for transient failures

        Returns dict with at least:
        {
          "text": str,
          "ocr_method": "mistral",
          "ocr_confidence": float,
        }
        or None on failure.
        """
        # Determine MIME type
        mime_type = f"image/{image_format}" if image_format != "jpg" else "image/jpeg"
        
        # Retry logic for transient failures
        last_error = None
        for attempt in range(max_retries):
            try:
                # Encode to data URL
                data_url = self._encode_to_data_url(image_bytes, mime_type)
                
                # Call OCR
                ocr_result = self._process_ocr(data_url)
                if not ocr_result:
                    if attempt < max_retries - 1:
                        wait_time = 2 ** attempt
                        print(f"  ⚠️  Mistral OCR failed, retrying in {wait_time}s... (attempt {attempt + 1}/{max_retries})")
                        time.sleep(wait_time)
                        continue
                    return None

                pages: List[Dict[str, Any]] = ocr_result.get("pages", []) or []
                markdown_parts: List[str] = []
                for page in pages:
                    md = page.get("markdown")
                    if md:
                        markdown_parts.append(md)

                text = "\n\n".join(markdown_parts).strip()
                if not text:
                    print("  ⚠️  Mistral OCR returned no markdown text")
                    return None

                # DEBUG: Show what Mistral actually returned
                arabic_count = sum(1 for c in text if '\u0600' <= c <= '\u06FF')
                english_count = sum(1 for c in text if c.isalpha() and c.isascii())
                print(f"  🔍 Mistral OCR DEBUG:")
                print(f"     - Text length: {len(text)} chars")
                print(f"     - First 200 chars: {text[:200]}")
                print(f"     - Arabic chars: {arabic_count}")
                print(f"     - English chars: {english_count}")
                
                # Success!
                return {
                    "text": text,
                    "ocr_method": "mistral",
                    "ocr_confidence": 0.85,
                }
                
            except Exception as e:
                last_error = e
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    print(f"  ⚠️  Mistral API error ({type(e).__name__}), retrying in {wait_time}s... (attempt {attempt + 1}/{max_retries})")
                    time.sleep(wait_time)
                else:
                    print(f"  ❌ Mistral API failed after {max_retries} attempts: {last_error}")
                    
        return None
    
    def extract_text_from_pdf(
        self,
        pdf_bytes: bytes,
        max_retries: int = 3,
    ) -> Optional[Dict[str, Any]]:
        """Run OCR on PDF bytes directly (more efficient than image extraction).

        Args:
            pdf_bytes: PDF file bytes
            max_retries: Number of retry attempts for transient failures

        Returns dict with at least:
        {
          "text": str,
          "ocr_method": "mistral",
          "ocr_confidence": float,
          "page_count": int,
        }
        or None on failure.
        """
        # Retry logic for transient failures
        last_error = None
        for attempt in range(max_retries):
            try:
                # Encode PDF to data URL
                data_url = self._encode_to_data_url(pdf_bytes, "application/pdf")
                
                # Call OCR
                ocr_result = self._process_ocr(data_url)
                if not ocr_result:
                    if attempt < max_retries - 1:
                        wait_time = 2 ** attempt
                        print(f"  ⚠️  Mistral PDF OCR failed, retrying in {wait_time}s... (attempt {attempt + 1}/{max_retries})")
                        time.sleep(wait_time)
                        continue
                    return None

                pages: List[Dict[str, Any]] = ocr_result.get("pages", []) or []
                markdown_parts: List[str] = []
                for page in pages:
                    md = page.get("markdown")
                    if md:
                        markdown_parts.append(md)

                text = "\n\n".join(markdown_parts).strip()
                if not text:
                    print("  ⚠️  Mistral PDF OCR returned no markdown text")
                    return None

                # Success!
                return {
                    "text": text,
                    "ocr_method": "mistral",
                    "ocr_confidence": 0.85,
                    "page_count": len(pages),
                }
                
            except Exception as e:
                last_error = e
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    print(f"  ⚠️  Mistral PDF API error ({type(e).__name__}), retrying in {wait_time}s... (attempt {attempt + 1}/{max_retries})")
                    time.sleep(wait_time)
                else:
                    print(f"  ❌ Mistral PDF API failed after {max_retries} attempts: {last_error}")
                    
        return None


# Singleton instance (mirrors claude_service pattern)
try:
    mistral_ocr_service: Optional[MistralOCRService] = MistralOCRService()
    print("✅ Mistral OCR service initialized successfully")
except Exception as _e:
    print(f"⚠️  Mistral OCR service not initialized: {_e}")
    mistral_ocr_service = None
