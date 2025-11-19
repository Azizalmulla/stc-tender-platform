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
        return """أنت خبير متخصص في استخراج المعلومات من مناقصات الكويت الرسمية (الجريدة الرسمية - كويت اليوم).

## المهمة:
قم بقراءة هذه الصورة بعناية واستخراج جميع المعلومات التالية:

### 1. معلومات أساسية:
- **الوزارة/الجهة**: اسم الوزارة أو المؤسسة بالعربية (مثال: وزارة الأشغال العامة، شركة نفط الكويت، الهيئة العامة للصناعة)
- **رقم المناقصة**: رقم المناقصة/المزايدة/الممارسة إن وجد
- **الموعد النهائي**: تاريخ انتهاء تقديم العروض (بصيغة YYYY-MM-DD)

### 2. معلومات اجتماع المقاولين (إن وجدت):
- **تاريخ الاجتماع**: النص الأصلي بالعربية كما هو (مثال: "يوم الأحد الموافق ١٥ ديسمبر ٢٠٢٤")
- **مكان الاجتماع**: مكان عقد الاجتماع (مثال: "مبنى الوزارة - الدور الثالث")

**أمثلة على عبارات الاجتماع:**
- "يُعقد اجتماع لشرح المناقصة يوم الأحد الموافق ١٥ ديسمبر ٢٠٢٤ الساعة ١٠ صباحاً في مبنى الوزارة"
- "موعد الاجتماع: الأحد ١٥/١٢/٢٠٢٤ - المكان: قاعة الاجتماعات"
- "لمزيد من التفاصيل، يُرجى حضور الاجتماع يوم ١-١٢-٢٠٢٤ بمقر الشركة"

### 3. النص الكامل:
قم باستخراج النص الكامل للمناقصة وتنظيمه بعناوين عربية واضحة. استخدم هذا الهيكل:

```
=== معلومات المناقصة ===
[المعلومات الأساسية: الوزارة، رقم المناقصة، الموضوع]

=== تفاصيل المناقصة ===
[تفاصيل العمل المطلوب، النطاق، الوصف]

=== الشروط والمتطلبات ===
[الشروط الفنية، المواصفات، متطلبات التأهيل]

=== معلومات الاتصال ===
[معلومات التواصل، مكان تقديم العروض، الاستفسارات]

=== المواعيد المهمة ===
[الموعد النهائي، موعد الاجتماع إن وجد، مواعيد أخرى]
```

## تعليمات حاسمة:

### ✅ افعل:
- اقرأ النص بعناية واستخرجه كما هو
- نظف الأخطاء الإملائية الواضحة (مثل: "dekمبر" → "ديسمبر")
- حافظ على الأرقام والتواريخ والأسماء كما هي
- نظم النص بعناوين واضحة بالعربية
- إذا كان النص واضحاً ومقروءاً، ضع ocr_confidence بين 0.8-1.0

### ❌ لا تفعل:
- لا تختلق نصوصاً أو معلومات غير موجودة
- لا تحاول قراءة نص غير واضح أو مطموس
- إذا كان النص غير قابل للقراءة، ضع `null` في حقل `body`
- إذا كانت جودة الصورة سيئة، ضع ocr_confidence أقل من 0.5

### مثال على نص منظم:
```
=== معلومات المناقصة ===
وزارة الأشغال العامة
مناقصة رقم: 2024/123
الموضوع: توريد وتركيب معدات طبية

=== تفاصيل المناقصة ===
تعلن وزارة الصحة عن طرح مناقصة عامة لتوريد وتركيب معدات طبية للمستشفيات التالية:
- مستشفى الجهراء
- مستشفى الفروانية
- مستشفى الأحمدي

=== الشروط والمتطلبات ===
- شهادة ISO 9001 سارية المفعول
- خبرة لا تقل عن 5 سنوات في مجال التوريد الطبي
- ضمان مصنع لمدة سنتين

=== معلومات الاتصال ===
للاستفسار: إدارة المشتريات - وزارة الصحة
هاتف: 22345678
البريد الإلكتروني: procurement@moh.gov.kw

=== المواعيد المهمة ===
آخر موعد لتقديم العروض: 15 ديسمبر 2024
موعد الاجتماع: 1 ديسمبر 2024، الساعة 10 صباحاً، مبنى الوزارة
```

## صيغة الإخراج (JSON فقط):
```json
{
  "ministry": "وزارة الأشغال العامة",
  "tender_number": "2024/123",
  "deadline": "2024-12-15",
  "meeting_date_text": "يوم الأحد الموافق ١ ديسمبر ٢٠٢٤",
  "meeting_location": "مبنى الوزارة - الدور الثالث",
  "body": "=== معلومات المناقصة ===\nوزارة الأشغال العامة\n...",
  "ocr_confidence": 0.9,
  "note": null
}
```

**إذا كان النص غير واضح:**
```json
{
  "ministry": "وزارة الصحة",
  "tender_number": null,
  "deadline": null,
  "meeting_date_text": null,
  "meeting_location": null,
  "body": null,
  "ocr_confidence": 0.2,
  "note": "جودة الصورة منخفضة جداً - النص غير قابل للقراءة بدقة"
}
```

**قم بالتحليل الآن وأرجع JSON فقط:**"""
    
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
