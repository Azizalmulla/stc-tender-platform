"""
Mistral AI Service - Complete tender processing pipeline
Uses Mistral for OCR, summarization, and structured extraction
"""
import base64
import json
from typing import Optional, Dict, Any
from mistralai import Mistral
from app.core.config import settings


class MistralAIService:
    """Mistral AI for complete tender processing (OCR + Understanding + Extraction)"""
    
    def __init__(self):
        if not settings.MISTRAL_API_KEY or settings.MISTRAL_API_KEY == 'paste-your-mistral-api-key-here':
            raise ValueError("MISTRAL_API_KEY not configured")
        self.client = Mistral(api_key=settings.MISTRAL_API_KEY)
        self.ocr_model = "mistral-ocr-latest"  # For OCR
        self.reasoning_model = "mistral-large-latest"  # For understanding & extraction
    
    def extract_text_from_image(
        self,
        image_bytes: bytes,
        image_format: str = "png"
    ) -> Dict[str, Any]:
        """
        Extract text from image using Mistral OCR
        
        Args:
            image_bytes: Screenshot image bytes
            image_format: Image format (png, jpeg, etc.)
        
        Returns:
            Dict containing extracted text:
            {
                "body": str (extracted text in markdown format),
                "ministry": str | None (extracted if visible in header),
                "ocr_confidence": float,
                "success": bool
            }
        """
        try:
            # Encode image to base64
            image_base64 = base64.b64encode(image_bytes).decode('utf-8')
            
            # Call Mistral OCR API (correct endpoint)
            response = self.client.ocr.process(
                model=self.ocr_model,
                document={
                    "type": "image_base64",
                    "image_base64": image_base64
                },
                include_image_base64=False  # We don't need it back
            )
            
            # Extract text from response
            # Response structure: response.pages[0].markdown
            if response.pages and len(response.pages) > 0:
                extracted_text = response.pages[0].markdown
                
                # Try to extract ministry from the beginning of text
                ministry = None
                lines = extracted_text.split('\n')
                if lines:
                    # First few lines often contain ministry name
                    first_line = lines[0].strip().replace('#', '').strip()
                    if len(first_line) > 5 and len(first_line) < 150:  # Reasonable ministry name length
                        ministry = first_line
                
                return {
                    "body": extracted_text,
                    "ministry": ministry,
                    "ocr_confidence": 0.85,  # Mistral OCR is quite good
                    "success": True
                }
            else:
                raise ValueError("No pages found in OCR response")
        
        except Exception as e:
            print(f"❌ Mistral OCR error: {e}")
            return {
                "body": "",
                "ministry": None,
                "ocr_confidence": 0.0,
                "success": False,
                "error": str(e)
            }
    
    def summarize_tender(
        self,
        tender_text: str,
        tender_number: Optional[str] = None,
        entity: Optional[str] = None,
        deadline: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generate bilingual summary and key facts using Mistral Large
        
        Args:
            tender_text: The full tender text
            tender_number: Tender number if available
            entity: Ministry/entity name if available
            deadline: Deadline if available
        
        Returns:
            Dict with summary_ar, summary_en, and key_facts
        """
        try:
            # Construct prompt for Mistral Large
            prompt = f"""أنت مساعد متخصص في تحليل مناقصات الكويت الحكومية من الجريدة الرسمية (كويت اليوم).

## معلومات المناقصة المتوفرة:
{f"رقم المناقصة: {tender_number}" if tender_number else ""}
{f"الجهة: {entity}" if entity else ""}
{f"الموعد النهائي: {deadline}" if deadline else ""}

## نص المناقصة:
{tender_text[:3000]}

## المهمة:
قم بإنشاء ملخص ثنائي اللغة واستخراج الحقائق الرئيسية.

### قواعد حاسمة:
1. **استخرج المعلومات فقط من النص المقدم** - لا تخترع أو تفترض معلومات
2. **الدقة 100%** - استخدم الأسماء والأرقام والتواريخ بالضبط كما وردت
3. **إذا كانت المعلومات مفقودة** - ضع null ولا تخمن
4. **التواريخ** - تحقق من الصيغة YYYY-MM-DD وانتبه لعدم الخلط بين "6" و "16"
5. **الجهة** - استخدم الاسم العربي الكامل بالضبط من المستند

### صيغة الإخراج (JSON فقط):
{{
    "summary_ar": "ملخص مختصر بالعربية (2-3 جمل، أقل من 200 حرف)",
    "summary_en": "Brief English summary (2-3 sentences, under 200 chars)",
    "key_facts": [
        "الجهة المعلنة: [الاسم الدقيق من المستند]",
        "رقم المناقصة: [الرقم]",
        "الموعد النهائي: [YYYY-MM-DD]",
        "موعد الاجتماع: [التاريخ إن ذُكر]",
        "مكان الاجتماع: [المكان إن ذُكر]"
    ],
    "entity": "اسم الجهة الحكومية بالعربية" أو null,
    "tender_number": "رقم المناقصة" أو null,
    "deadline": "YYYY-MM-DD" أو null,
    "meeting_date": "تاريخ الاجتماع بالعربية كما ورد" أو null,
    "meeting_location": "مكان الاجتماع" أو null
}}

**مهم:** أرجع JSON صالح فقط، بدون نص إضافي. لا تضع معلومات غير موجودة في النص."""

            # Call Mistral Large
            response = self.client.chat.complete(
                model=self.reasoning_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=1000,
                response_format={"type": "json_object"}
            )
            
            # Parse JSON response
            result = json.loads(response.choices[0].message.content)
            
            # Handle case where Mistral returns a list instead of dict
            if isinstance(result, list):
                if len(result) > 0:
                    result = result[0]  # Take first item
                else:
                    raise ValueError("Mistral returned empty list")
            
            # Ensure result is a dict
            if not isinstance(result, dict):
                raise ValueError(f"Mistral returned unexpected type: {type(result)}")
            
            return {
                "summary_ar": result.get("summary_ar", ""),
                "summary_en": result.get("summary_en", ""),
                "key_facts": result.get("key_facts", []),
                "entity": result.get("entity"),
                "tender_number": result.get("tender_number"),
                "deadline": result.get("deadline"),
                "meeting_date": result.get("meeting_date"),
                "meeting_location": result.get("meeting_location"),
                "success": True
            }
        
        except Exception as e:
            print(f"❌ Mistral summarization error: {e}")
            return {
                "summary_ar": "",
                "summary_en": "",
                "key_facts": [],
                "success": False,
                "error": str(e)
            }
    
    def extract_structured_data(
        self,
        tender_text: str
    ) -> Dict[str, Any]:
        """
        Extract structured data from tender text using Mistral Large
        
        Args:
            tender_text: The full tender text
        
        Returns:
            Dict with ministry, tender_number, deadline, category, etc.
        """
        try:
            prompt = f"""أنت خبير في استخراج البيانات المهيكلة من مناقصات الكويت الحكومية.

## نص المناقصة:
{tender_text[:3000]}

## المهمة:
استخرج الحقول التالية بدقة 100%.

### قواعد الاستخراج الحاسمة:
1. **استخرج فقط المعلومات الموجودة صراحةً في النص** - لا تخمن أو تفترض
2. **الدقة الكاملة** - استخدم الأسماء والأرقام بالضبط كما وردت
3. **للحقول المفقودة** - ضع null ولا تخترع معلومات
4. **التواريخ** - صيغة YYYY-MM-DD فقط، وانتبه لعدم الخلط بين الأرقام
5. **الجهة** - الاسم العربي الكامل بالضبط من المستند

### 📅 استخراج التاريخ النهائي (حاسم):
**ابحث عن هذه العبارات:**
- "آخر موعد لتقديم العروض"
- "الموعد النهائي"
- "آخر موعد للتقديم"
- "ينتهي استلام العروض"

**تنسيق التاريخ:**
- 6/11/2025 → "2025-11-06"
- 16/11/2025 → "2025-11-16"
- 26/11/2025 → "2025-11-26"
- **مهم:** لا تخلط بين "6" و "16" و "26"

### 🏷️ التصنيفات المتاحة:
- **"خدمات"**: Services (خدمات، صيانة، تشغيل، نظافة)
- **"توريدات"**: Supplies (توريد، شراء، مواد، معدات)
- **"إنشاءات"**: Construction (إنشاء، بناء، تطوير، ترميم)
- **"استشارات"**: Consulting (استشارات، دراسات، تصاميم)
- **"تقنية"**: IT (أنظمة، برمجيات، حاسب آلي)
- **"أخرى"**: Other

### صيغة الإخراج (JSON فقط):
{{
    "ministry": "اسم الوزارة أو الجهة الكامل بالعربية" أو null,
    "tender_number": "رقم المناقصة الدقيق" أو null,
    "deadline": "YYYY-MM-DD" أو null,
    "document_price": "سعر وثائق المناقصة (رقم فقط)" أو null,
    "category": "أحد التصنيفات أعلاه" أو null,
    "meeting_date": "تاريخ اجتماع الموردين (النص العربي الأصلي)" أو null,
    "meeting_location": "مكان الاجتماع" أو null
}}

**مهم جداً:** 
- أرجع JSON صالح فقط
- استخدم null للحقول غير الموجودة (لا تخمن)
- احرص على دقة التواريخ والأرقام"""

            # Call Mistral Large
            response = self.client.chat.complete(
                model=self.reasoning_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,  # Deterministic for extraction
                max_tokens=500,
                response_format={"type": "json_object"}
            )
            
            # Parse JSON response
            result = json.loads(response.choices[0].message.content)
            
            # Handle case where Mistral returns a list instead of dict
            if isinstance(result, list):
                if len(result) > 0:
                    result = result[0]  # Take first item
                else:
                    raise ValueError("Mistral returned empty list")
            
            # Ensure result is a dict
            if not isinstance(result, dict):
                raise ValueError(f"Mistral returned unexpected type: {type(result)}")
            
            return {
                "ministry": result.get("ministry"),
                "tender_number": result.get("tender_number"),
                "deadline": result.get("deadline"),
                "document_price": result.get("document_price"),
                "category": result.get("category"),
                "meeting_date": result.get("meeting_date"),
                "meeting_location": result.get("meeting_location"),
                "success": True
            }
        
        except Exception as e:
            print(f"❌ Mistral extraction error: {e}")
            return {
                "ministry": None,
                "tender_number": None,
                "deadline": None,
                "document_price": None,
                "category": None,
                "meeting_date": None,
                "meeting_location": None,
                "success": False,
                "error": str(e)
            }


# Singleton instance - safe initialization
try:
    mistral_service = MistralAIService()
    print("✅ Mistral AI Service initialized successfully")
except ValueError as e:
    print(f"⚠️  Mistral AI Service not initialized: {e}")
    mistral_service = None
