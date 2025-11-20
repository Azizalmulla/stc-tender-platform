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
            
            # Construct message for Mistral OCR
            messages = [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": """Extract ALL text from this Arabic tender document image.

**INSTRUCTIONS:**
1. Extract ALL visible Arabic text accurately
2. Preserve the original structure and layout
3. If you see the ministry/entity name at the top, note it
4. Output the text in clean, readable format
5. Do NOT summarize - extract the complete text as-is

**OUTPUT FORMAT:**
Return a JSON with:
- body: The complete extracted text
- ministry: The ministry/entity name if visible (or null)
- confidence: Your confidence level (0.0 to 1.0)"""
                        },
                        {
                            "type": "image_url",
                            "image_url": f"data:image/{image_format};base64,{image_base64}"
                        }
                    ]
                }
            ]
            
            # Call Mistral OCR
            response = self.client.chat.complete(
                model=self.ocr_model,
                messages=messages,
                temperature=0.0,  # Deterministic for OCR
                max_tokens=4000
            )
            
            # Parse response
            response_text = response.choices[0].message.content.strip()
            
            # Try to parse as JSON first
            try:
                result = json.loads(response_text)
                return {
                    "body": result.get("body", ""),
                    "ministry": result.get("ministry"),
                    "ocr_confidence": float(result.get("confidence", 0.8)),
                    "success": True
                }
            except json.JSONDecodeError:
                # If not JSON, treat entire response as extracted text
                return {
                    "body": response_text,
                    "ministry": None,
                    "ocr_confidence": 0.75,  # Default confidence
                    "success": True
                }
        
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
            prompt = f"""You are analyzing a Kuwait government tender document in Arabic.

**TENDER INFORMATION:**
{f"Tender Number: {tender_number}" if tender_number else ""}
{f"Entity: {entity}" if entity else ""}
{f"Deadline: {deadline}" if deadline else ""}

**TENDER TEXT:**
{tender_text[:3000]}  # Limit to prevent token overflow

**YOUR TASK:**
Generate a bilingual summary and extract key facts.

**CRITICAL RULES:**
1. Extract information ONLY from the provided text
2. DO NOT hallucinate or invent information
3. If information is missing, set it to null
4. Be accurate and concise

**OUTPUT FORMAT (JSON):**
{{
    "summary_ar": "ملخص مختصر باللغة العربية (2-3 جمل)",
    "summary_en": "Brief English summary (2-3 sentences)",
    "key_facts": [
        "Fact 1 in Arabic or English",
        "Fact 2...",
        "Fact 3..."
    ],
    "entity": "الجهة الحكومية" or null,
    "tender_number": "رقم المناقصة" or null,
    "deadline": "YYYY-MM-DD" or null,
    "meeting_date": "تاريخ الاجتماع" or null,
    "meeting_location": "مكان الاجتماع" or null
}}

Return ONLY valid JSON, no additional text."""

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
            prompt = f"""Extract structured information from this Kuwait government tender in Arabic.

**TENDER TEXT:**
{tender_text[:3000]}

**EXTRACTION RULES:**
1. Extract ONLY information explicitly stated in the text
2. DO NOT guess or hallucinate
3. Return null for missing fields
4. Be precise with dates (format: YYYY-MM-DD)

**CATEGORIES:**
- "خدمات": Services (خدمات، صيانة، تشغيل)
- "توريدات": Supplies (توريد، شراء، مواد)
- "إنشاءات": Construction (إنشاء، بناء، تطوير)
- "استشارات": Consulting (استشارات، دراسات)
- "أخرى": Other

**OUTPUT FORMAT (JSON):**
{{
    "ministry": "اسم الوزارة أو الجهة" or null,
    "tender_number": "رقم المناقصة" or null,
    "deadline": "YYYY-MM-DD" or null,
    "document_price": "سعر وثائق المناقصة" or null,
    "category": "one of the categories above" or null,
    "meeting_date": "تاريخ اجتماع الموردين" or null,
    "meeting_location": "مكان الاجتماع" or null
}}

Return ONLY valid JSON."""

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
