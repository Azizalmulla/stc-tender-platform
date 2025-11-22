import os
import time
from typing import Optional, Dict, Any, List

import requests
from mistralai import Mistral

from app.core.config import settings


class MistralOCRService:
    """Thin wrapper around Mistral OCR for images/PDF pages.

    This service uploads a file to Mistral, then calls the /v1/ocr endpoint
    with that file_id and aggregates page markdown into a single text string.
    """

    def __init__(self) -> None:
        api_key = settings.MISTRAL_API_KEY or os.getenv("MISTRAL_API_KEY")
        if not api_key or api_key == "paste-your-mistral-api-key-here":
            raise ValueError("MISTRAL_API_KEY not configured")

        self.api_key = api_key
        # Use official SDK for file upload, raw HTTP for /v1/ocr (not yet in SDK)
        self.client = Mistral(api_key=api_key)
        self.ocr_model = "mistral-ocr-latest"
        self.api_url = os.getenv("MISTRAL_API_URL", "https://api.mistral.ai").rstrip("/")

    def _upload_file(
        self,
        content: bytes,
        file_name: str,
        content_type: str,
    ) -> Optional[str]:
        """Upload a file to Mistral Files API and return file_id."""
        try:
            file_obj = {
                "file_name": file_name,
                "content": content,
                "content_type": content_type,
            }
            uploaded = self.client.files.upload(file=file_obj)
            if uploaded and getattr(uploaded, "id", None):
                return uploaded.id
            print("  ⚠️  Mistral file upload returned no id")
            return None
        except Exception as e:
            print(f"  ❌ Mistral file upload failed: {e}")
            return None

    def _call_ocr(self, file_id: str) -> Optional[Dict[str, Any]]:
        """Call Mistral /v1/ocr for a previously uploaded file."""
        try:
            url = f"{self.api_url}/v1/ocr"
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": self.ocr_model,
                "document": {"file_id": file_id},
            }
            resp = requests.post(url, headers=headers, json=payload, timeout=60)
            if resp.status_code != 200:
                print(f"  ❌ Mistral OCR HTTP {resp.status_code}: {resp.text[:200]}")
                return None
            return resp.json()
        except Exception as e:
            print(f"  ❌ Mistral OCR request failed: {e}")
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
        content_type = f"image/{image_format}"
        
        # Retry logic for transient failures
        last_error = None
        for attempt in range(max_retries):
            try:
                file_id = self._upload_file(image_bytes, f"page.{image_format}", content_type)
                if not file_id:
                    if attempt < max_retries - 1:
                        wait_time = 2 ** attempt  # 1s, 2s, 4s
                        print(f"  ⚠️  Mistral file upload failed, retrying in {wait_time}s... (attempt {attempt + 1}/{max_retries})")
                        time.sleep(wait_time)
                        continue
                    return None

                ocr_result = self._call_ocr(file_id)
                if not ocr_result:
                    if attempt < max_retries - 1:
                        wait_time = 2 ** attempt
                        print(f"  ⚠️  Mistral OCR call failed, retrying in {wait_time}s... (attempt {attempt + 1}/{max_retries})")
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

                # Success!
                return {
                    "text": text,
                    "ocr_method": "mistral",
                    "ocr_confidence": 0.85,
                }
                
            except (requests.exceptions.RequestException, requests.exceptions.Timeout) as e:
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
        content_type = "application/pdf"
        
        # Retry logic for transient failures
        last_error = None
        for attempt in range(max_retries):
            try:
                file_id = self._upload_file(pdf_bytes, "document.pdf", content_type)
                if not file_id:
                    if attempt < max_retries - 1:
                        wait_time = 2 ** attempt
                        print(f"  ⚠️  Mistral PDF upload failed, retrying in {wait_time}s... (attempt {attempt + 1}/{max_retries})")
                        time.sleep(wait_time)
                        continue
                    return None

                ocr_result = self._call_ocr(file_id)
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
                
            except (requests.exceptions.RequestException, requests.exceptions.Timeout) as e:
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
