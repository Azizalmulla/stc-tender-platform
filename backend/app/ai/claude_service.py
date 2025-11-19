"""
Claude Sonnet 4.5 Service for OCR and Document Extraction
Replaces Google Document AI + GPT pipeline with single Claude call
"""
import base64
import json
from typing import Optional, Dict, Any
from anthropic import Anthropic
from app.core.config import settings


class ClaudeOCRService:
    """Claude Sonnet 4.5 for OCR, extraction, and structuring"""
    
    def __init__(self):
        if not settings.ANTHROPIC_API_KEY:
            raise ValueError("ANTHROPIC_API_KEY not configured")
        self.client = Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        self.model = settings.CLAUDE_MODEL
    
    def extract_tender_from_image(
        self,
        image_bytes: bytes,
        image_format: str = "png"
    ) -> Dict[str, Any]:
        """
        Extract all tender information from screenshot using Claude Sonnet 4.5
        
        Args:
            image_bytes: Screenshot image bytes
            image_format: Image format (png, jpeg, etc.)
        
        Returns:
            Dict containing extracted tender data:
            {
                "ministry": str,
                "tender_number": str | None,
                "deadline": str | None (YYYY-MM-DD),
                "meeting_date": str | None,
                "meeting_location": str | None,
                "body": str | None (clean Arabic text),
                "ocr_confidence": float,
                "note": str | None (if text unclear)
            }
        """
        try:
            # Encode image to base64
            image_base64 = base64.b64encode(image_bytes).decode('utf-8')
            
            # Construct prompt for Claude
            prompt = self._construct_extraction_prompt()
            
            # Call Claude Vision API
            print(f"🧠 Claude Sonnet 4.5: Analyzing tender document...")
            
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": f"image/{image_format}",
                                    "data": image_base64
                                }
                            },
                            {
                                "type": "text",
                                "text": prompt
                            }
                        ]
                    }
                ]
            )
            
            # Extract response text
            response_text = response.content[0].text
            
            # Parse JSON response
            result = self._parse_response(response_text)
            
            print(f"✅ Claude extraction complete")
            print(f"   Ministry: {result.get('ministry', 'N/A')}")
            print(f"   Body length: {len(result.get('body', '') or '')} chars")
            print(f"   Confidence: {result.get('ocr_confidence', 0)}")
            
            return result
            
        except Exception as e:
            print(f"❌ Claude extraction error: {e}")
            return {
                "ministry": None,
                "tender_number": None,
                "deadline": None,
                "meeting_date": None,
                "meeting_location": None,
                "body": None,
                "ocr_confidence": 0.0,
                "note": f"Extraction failed: {str(e)}"
            }
    
    def _construct_extraction_prompt(self) -> str:
        """Construct the extraction prompt for Claude"""
        return """أنت خبير في استخراج المعلومات من مناقصات الكويت الرسمية.

قم بتحليل هذه الصورة واستخراج جميع المعلومات التالية:

1. **اسم الوزارة أو الجهة** (Ministry name in Arabic)
2. **رقم المناقصة/المزايدة/الممارسة** (Tender number)
3. **الموعد النهائي لتقديم العروض** (Deadline date)
4. **معلومات اجتماع المقاولين** إن وجدت (Pre-tender meeting info):
   - تاريخ الاجتماع
   - مكان الاجتماع
5. **النص الكامل** للمناقصة بالعربية (Full tender text in clean Arabic)

**تعليمات مهمة:**
- إذا كان النص غير واضح أو غير قابل للقراءة، ضع `null` في حقل `body` واشرح السبب في حقل `note`
- لا تختلق نصوصًا غير موجودة
- تأكد من دقة استخراج التواريخ بصيغة YYYY-MM-DD
- نظف النص من الأخطاء الإملائية الواضحة
- احتفظ بتنسيق واضح مع عناوين الأقسام

**أمثلة على معلومات الاجتماع:**
- "يُعقد اجتماع لشرح المناقصة يوم الأحد الموافق ١٥ ديسمبر ٢٠٢٤ في مبنى الوزارة"
- "موعد الاجتماع: ١٥-١٢-٢٠٢٤، المكان: قاعة الاجتماعات بالوزارة"

**أرجع النتيجة بصيغة JSON:**
```json
{
  "ministry": "string (اسم الوزارة بالعربية)",
  "tender_number": "string or null",
  "deadline": "YYYY-MM-DD or null",
  "meeting_date_text": "string or null (النص الأصلي للتاريخ بالعربية)",
  "meeting_location": "string or null",
  "body": "string or null (النص الكامل المنظم)",
  "ocr_confidence": 0.0-1.0 (ثقتك في جودة استخراج النص),
  "note": "string or null (ملاحظات إضافية إن وجدت)"
}
```

قم بالتحليل الآن:"""
    
    def _parse_response(self, response_text: str) -> Dict[str, Any]:
        """Parse Claude's JSON response"""
        try:
            # Try to find JSON in response
            start_idx = response_text.find('{')
            end_idx = response_text.rfind('}') + 1
            
            if start_idx == -1 or end_idx == 0:
                raise ValueError("No JSON found in response")
            
            json_str = response_text[start_idx:end_idx]
            data = json.loads(json_str)
            
            # Ensure all required fields exist
            result = {
                "ministry": data.get("ministry"),
                "tender_number": data.get("tender_number"),
                "deadline": data.get("deadline"),
                "meeting_date_text": data.get("meeting_date_text"),
                "meeting_location": data.get("meeting_location"),
                "body": data.get("body"),
                "ocr_confidence": float(data.get("ocr_confidence", 0.5)),
                "note": data.get("note")
            }
            
            return result
            
        except Exception as e:
            print(f"⚠️  Failed to parse Claude response as JSON: {e}")
            print(f"Raw response: {response_text[:500]}...")
            
            # Return fallback
            return {
                "ministry": None,
                "tender_number": None,
                "deadline": None,
                "meeting_date_text": None,
                "meeting_location": None,
                "body": response_text if response_text else None,
                "ocr_confidence": 0.3,
                "note": "Failed to parse as JSON, returning raw text"
            }


# Singleton instance
claude_service = ClaudeOCRService() if settings.ANTHROPIC_API_KEY else None
