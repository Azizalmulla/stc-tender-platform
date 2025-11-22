"""
Claude Sonnet 4.5 Service for OCR and Document Extraction
Replaces Google Document AI + GPT pipeline with single Claude call
"""
import base64
import json
from typing import Optional, Dict, Any, List
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
            
            # Construct prompt for Claude with enhanced date extraction
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

### 📅 **الموعد النهائي (CRITICAL - دقة 100% مطلوبة):**
**ابحث عن هذه العبارات:**
- "آخر موعد لتقديم العروض"
- "الموعد النهائي"
- "آخر موعد للتقديم"
- "ينتهي استلام العروض"
- "Last date for submission"

**استخرج التاريخ بصيغة YYYY-MM-DD:**
- تحقق من وجود التاريخ الميلادي أو الهجري
- إذا وجدت "6/11/2025" فهذا يعني 6 نوفمبر 2025 → "2025-11-06"
- إذا وجدت "16/11/2025" فهذا يعني 16 نوفمبر 2025 → "2025-11-16"
- إذا وجدت "26/11/2025" فهذا يعني 26 نوفمبر 2025 → "2025-11-26"
- انتبه: لا تخلط بين "6" و"16" و"26"

**قواعد التحقق:**
- التاريخ النهائي يجب أن يكون في المستقبل (بعد تاريخ النشر)
- إذا كان التاريخ في الماضي، ضع ملاحظة في حقل "note"
- إذا لم تجد التاريخ بوضوح، اترك الحقل null ولا تخمن

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
    
    def summarize_tender(self, title: str, body: str, lang: str = "ar") -> Dict:
        """
        Generate bilingual summary and key facts for a tender using Claude
        
        Args:
            title: Tender title
            body: Tender body text
            lang: Primary language ('ar' or 'en')
            
        Returns:
            Dict with summary_ar, summary_en, facts_ar, facts_en
        """
        # Use .format() instead of f-string to avoid issues with curly braces in body text
        prompt = """You are an Arabic tender extraction assistant analyzing Kuwait Al-Yawm government tenders.

**CRITICAL: Extract information ONLY from the provided text. NEVER fabricate or hallucinate information.**

Title: {title_text}
Body: {body_text}

Generate a JSON response with:
1. **summary_ar**: Arabic summary in 2 lines (max 200 characters)
2. **summary_en**: English summary in 2 lines (max 200 characters)  
3. **facts_ar**: 3-5 key facts in Arabic as bullet points
4. **facts_en**: 3-5 key facts in English as bullet points

**Rules:**
- Extract ONLY information that is explicitly stated in the text
- For ministry: Use EXACT name from the tender document
- For deadlines: Use exact dates mentioned (format: YYYY-MM-DD if possible)
- For tender numbers: Use exact numbers from document
- If information is NOT in the text, do NOT invent it - say "غير محدد" or "Not specified"
- Focus on: ministry/issuing entity, tender number, deadline, requirements, budget, meeting info

**Return JSON with COMPLETE key facts (include ALL available information):**
```json
{{
  "summary_ar": "موجز بالعربية (سطران فقط)",
  "summary_en": "English summary (2 lines only)",
  "facts_ar": [
    "الجهة المعلنة: [EXACT name from document]",
    "رقم المناقصة: [number]",
    "الموعد النهائي: [YYYY-MM-DD]",
    "موعد الاجتماع التمهيدي: [date if mentioned, otherwise OMIT this line]",
    "مكان الاجتماع: [location if mentioned, otherwise OMIT this line]",
    "قيمة الوثائق: [price if mentioned]",
    "مدة العقد: [duration if mentioned]"
  ],
  "facts_en": [
    "Issuing Entity: [EXACT name]",
    "Tender Number: [number]",
    "Deadline: [YYYY-MM-DD]",
    "Pre-tender Meeting: [date if mentioned, otherwise OMIT this line]",
    "Meeting Location: [location if mentioned, otherwise OMIT this line]",
    "Document Price: [price if mentioned]",
    "Contract Duration: [duration if mentioned]"
  ]
}}
```

**CRITICAL:**
- NEVER say "غير مذكور" or "Not specified" if the information EXISTS in the text
- If information is truly missing, OMIT that fact line completely
- For meetings: Only include if explicitly mentioned in tender
- For entity: Use EXACT Arabic name from document (don't translate or change it)

Generate the JSON now:""".format(
    title_text=title.replace('{', '{{').replace('}', '}}'),
    body_text=body[:3000].replace('{', '{{').replace('}', '}}')
)
        
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1500,
                temperature=0.1,
                messages=[{
                    "role": "user",
                    "content": prompt
                }]
            )
            
            response_text = response.content[0].text
            
            # Parse JSON from response
            start_idx = response_text.find('{')
            end_idx = response_text.rfind('}') + 1
            
            if start_idx == -1 or end_idx == 0:
                raise ValueError("No JSON found in Claude response")
            
            json_str = response_text[start_idx:end_idx]
            result = json.loads(json_str)
            
            return {
                "summary_ar": result.get("summary_ar", "")[:300],
                "summary_en": result.get("summary_en", "")[:300],
                "facts_ar": result.get("facts_ar", [])[:5],
                "facts_en": result.get("facts_en", [])[:5]
            }
            
        except Exception as e:
            print(f"❌ Claude summarization error: {e}")
            return {
                "summary_ar": title[:200] if lang == "ar" else "",
                "summary_en": title[:200] if lang == "en" else "",
                "facts_ar": [],
                "facts_en": []
            }
    
    def extract_structured_data(self, text: str) -> Dict:
        """
        Extract structured fields from tender text using Claude
        
        Args:
            text: Full tender text
            
        Returns:
            Dict with ministry, tender_number, deadline, document_price_kd, category
        """
        prompt = """Extract structured fields from this Kuwait tender text.

**CRITICAL: Extract ONLY information explicitly stated in the text. Do NOT guess or fabricate.**

Text:
{text_content}

Extract these fields and return JSON:
```json
{{
  "ministry": "Exact issuing organization name from document",
  "tender_number": "Exact tender/RFP/RFQ number",
  "deadline": "YYYY-MM-DD format",
  "document_price_kd": numeric value in KD,
  "category": "IT|Construction|Services|Healthcare|Infrastructure|Other"
}}
```

**Rules:**
- Use null for fields NOT found in the text
- For ministry: Extract the EXACT Arabic name of the issuing organization (ministry, company, authority, agency, or any entity)
  * Examples: "وزارة الصحة", "شركة نفط الكويت", "الهيئة العامة للإسكان", "بنك الكويت الوطني"
  * ALWAYS extract the entity name - it's RARE for this to be missing
  * Only use null if absolutely NO organization name is mentioned
- For deadline: Parse from Arabic or English dates
- For category: Classify based on keywords in text
- For document_price_kd: Extract numeric value only

**Return JSON now:**""".format(text_content=text[:2500].replace('{', '{{').replace('}', '}}'))
        
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=500,
                temperature=0.1,
                messages=[{
                    "role": "user",
                    "content": prompt
                }]
            )
            
            response_text = response.content[0].text
            
            # Parse JSON
            start_idx = response_text.find('{')
            end_idx = response_text.rfind('}') + 1
            
            if start_idx == -1 or end_idx == 0:
                raise ValueError("No JSON found in Claude response")
            
            json_str = response_text[start_idx:end_idx]
            return json.loads(json_str)
            
        except Exception as e:
            print(f"❌ Claude structured extraction error: {e}")
            return {
                "ministry": None,
                "tender_number": None,
                "deadline": None,
                "document_price_kd": None,
                "category": None
            }
    
    def analyze_query(self, question: str) -> Dict:
        """
        Analyze user query to extract intent and filters for accurate database queries
        
        Args:
            question: User's natural language question
            
        Returns:
            Dict with query_type, entity_filters, search_terms
        """
        prompt = """You are an expert query analyzer for Kuwait government tenders. Extract ALL conditions from the user's question with 100% accuracy.

**CRITICAL: Extract EVERY filter mentioned. Do not miss any conditions.**

Question: """ + question + """

Return ONLY a JSON object with these fields:
{
  "query_type": "count" | "search" | "specific",
  "intent": "Brief description of what user wants",
  "ministry_keywords": ["keyword1", "keyword2"],
  "category_keywords": ["keyword1", "keyword2"],
  "deadline_filter": "upcoming" | "expired" | "all" | null,
  "sql_conditions": [
    {"field": "ministry", "operator": "ILIKE", "value": "%keyword%"},
    {"field": "deadline", "operator": ">", "value": "2025-11-22"}
  ]
}

**Instructions:**
- query_type: "count" if asking "how many", "total"; "specific" if asking about exact tender; "search" otherwise
- ministry_keywords: Extract ministry-related terms in Arabic AND English
- category_keywords: IT, construction, services, healthcare, etc.
- deadline_filter: Detect time-sensitive queries ("closing soon", "expired", "active")
- sql_conditions: Build SQL WHERE clause conditions dynamically

**Examples:**

Q: "how many electricity tenders"
→ {
  "query_type": "count",
  "intent": "Count tenders from electricity ministry",
  "ministry_keywords": ["electricity", "كهرباء", "الكهرباء والماء"],
  "category_keywords": [],
  "deadline_filter": null,
  "sql_conditions": [
    {"field": "ministry", "operator": "ILIKE", "value": "%كهرباء%"}
  ]
}

Q: "show me finance tenders closing this week"
→ {
  "query_type": "search",
  "intent": "Find finance tenders with upcoming deadlines",
  "ministry_keywords": ["finance", "مالية", "المالية"],
  "category_keywords": [],
  "deadline_filter": "upcoming",
  "sql_conditions": [
    {"field": "ministry", "operator": "ILIKE", "value": "%مالية%"},
    {"field": "deadline", "operator": ">=", "value": "TODAY"},
    {"field": "deadline", "operator": "<=", "value": "TODAY+7"}
  ]
}

Q: "finance tenders over 100K closing next week"
→ {
  "query_type": "search",
  "intent": "Find high-value finance tenders with upcoming deadlines",
  "ministry_keywords": ["finance", "مالية"],
  "category_keywords": [],
  "deadline_filter": "upcoming",
  "sql_conditions": [
    {"field": "ministry", "operator": "ILIKE", "value": "%مالية%"},
    {"field": "document_price_kd", "operator": ">", "value": 100000},
    {"field": "deadline", "operator": ">=", "value": "TODAY"},
    {"field": "deadline", "operator": "<=", "value": "TODAY+7"}
  ]
}

Q: "IT tenders from MOF with meetings scheduled"
→ {
  "query_type": "search",
  "intent": "Find IT tenders from Ministry of Finance that have pre-tender meetings",
  "ministry_keywords": ["MOF", "finance", "مالية"],
  "category_keywords": ["IT", "information technology"],
  "deadline_filter": null,
  "sql_conditions": [
    {"field": "ministry", "operator": "ILIKE", "value": "%مالية%"},
    {"field": "category", "operator": "ILIKE", "value": "%IT%"},
    {"field": "meeting_date", "operator": "IS NOT", "value": "NULL"}
  ]
}

**IMPORTANT:**
- Extract ALL conditions (ministry, price, deadline, category, meeting, etc.)
- For prices: 100K = 100000, 1M = 1000000
- For deadlines: "next week" = TODAY to TODAY+7, "this month" = TODAY to TODAY+30
- For categories: IT, construction, healthcare, services, etc.
- Always include Arabic equivalents for ministry names

Return ONLY the JSON, no explanation."""
        
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=800,
                temperature=0.1,
                messages=[{
                    "role": "user",
                    "content": prompt
                }]
            )
            
            response_text = response.content[0].text
            
            # Parse JSON
            start_idx = response_text.find('{')
            end_idx = response_text.rfind('}') + 1
            
            if start_idx == -1 or end_idx == 0:
                # Default fallback
                return {
                    "query_type": "search",
                    "intent": question,
                    "ministry_keywords": [],
                    "category_keywords": [],
                    "deadline_filter": None,
                    "sql_conditions": []
                }
            
            json_str = response_text[start_idx:end_idx]
            result = json.loads(json_str)
            
            print(f"🧠 Query Analysis: {result['query_type']} - {result['intent']}")
            return result
            
        except Exception as e:
            print(f"❌ Query analysis error: {e}")
            # Fallback to simple search
            return {
                "query_type": "search",
                "intent": question,
                "ministry_keywords": [],
                "category_keywords": [],
                "deadline_filter": None,
                "sql_conditions": []
            }
    
    def answer_question(
        self, 
        question: str, 
        context_docs: List[Dict], 
        conversation_history: List[Dict] = None,
        metadata: Dict = None
    ) -> Dict:
        """
        Answer questions about tenders using Claude Sonnet 4.5 with RAG
        
        Args:
            question: User question in Arabic or English
            context_docs: List of relevant tender documents
            conversation_history: Previous conversation messages (optional)
            metadata: Optional metadata like total_count for accurate aggregations
            
        Returns:
            Dict with answer_ar, answer_en, citations, confidence
        """
        # Add metadata context if provided (e.g., accurate counts)
        metadata_context = ""
        if metadata and metadata.get('total_count'):
            total_count = metadata['total_count']
            sample_count = len(context_docs)
            metadata_context = f"\n\n**DATABASE STATISTICS:**\n"
            metadata_context += f"- Total matching tenders in database: {total_count}\n"
            metadata_context += f"- Sample tenders shown below: {sample_count}\n"
            metadata_context += f"- Use the TOTAL COUNT ({total_count}) when answering 'how many' questions\n\n"
        
        # Build context from documents
        context = "\n\n---\n\n".join([
            f"رقم المناقصة / Tender Number: {doc.get('tender_number', 'N/A')}\n"
            f"العنوان / Title: {doc['title']}\n"
            f"الجهة / Ministry: {doc.get('ministry', 'N/A')}\n"
            f"التصنيف / Category: {doc.get('category', 'N/A')}\n"
            f"تاريخ النشر / Published: {doc.get('published_at', 'N/A')}\n"
            f"الموعد النهائي / Deadline: {doc.get('deadline', 'N/A')}\n"
            f"سعر الوثائق / Document Price: {doc.get('document_price_kd', 'N/A')} KD\n"
            f"موعد الاجتماع / Meeting Date: {doc.get('meeting_date', 'N/A')}\n"
            f"مكان الاجتماع / Meeting Location: {doc.get('meeting_location', 'N/A')}\n"
            f"مؤجل / Postponed: {'نعم / Yes' if doc.get('is_postponed') else 'لا / No'}\n"
            f"الموعد الأصلي / Original Deadline: {doc.get('original_deadline', 'N/A')}\n"
            f"سبب التأجيل / Postponement Reason: {doc.get('postponement_reason', 'N/A')}\n"
            f"الملخص العربي / Arabic Summary: {doc.get('summary_ar', 'N/A')[:500]}\n"
            f"الملخص الإنجليزي / English Summary: {doc.get('summary_en', 'N/A')[:500]}\n"
            f"الحقائق الرئيسية / Key Facts: {', '.join(doc.get('facts_ar', [])[:5]) if doc.get('facts_ar') else 'N/A'}\n"
            f"النص الكامل / Full Text: {(doc.get('body', '') or 'N/A')[:3000]}\n"
            f"الرابط / URL: {doc['url']}"
            for doc in context_docs[:10]
        ])
        
        # Build conversation context
        conversation_context = ""
        if conversation_history:
            conversation_context = "\n\n**المحادثة السابقة / Previous Conversation:**\n" + "\n".join([
                f"{msg['role'].capitalize()}: {msg['content']}"
                for msg in conversation_history[-6:]
            ])
        
        # Get today's date for temporal context
        from datetime import datetime
        today = datetime.now().strftime("%Y-%m-%d")
        today_readable = datetime.now().strftime("%B %d, %Y")
        
        prompt = f"""You are an expert assistant for Kuwait government tenders from Kuwait Al-Yawm Official Gazette.
أنت مساعد خبير في مناقصات الحكومة الكويتية من جريدة كويت اليوم الرسمية.

Today's date is {today_readable} ({today}). Use this to determine if tenders are active or expired.

**INSTRUCTIONS:**
- Answer ONLY using the provided documents - never fabricate information
- Use conversation history for context on follow-up questions  
- Always cite sources with [Source] links
- If multiple tenders match, list them clearly
- Be concise but comprehensive
- Respond in BOTH Arabic and English based on question language

**OUTPUT FORMAT - Conversational & Clean:**

For single tender:
I found [1 tender / مناقصة واحدة] from [Ministry].

📋 **Tender #[Number]**  
⏰ Deadline: [Date]

[Brief 1-2 sentence description of what it's for]

Key requirements:
• [Requirement 1]
• [Requirement 2]
• [Requirement 3]

[View Full Details →]([url])

⚠️ [Any important notes if applicable]

For multiple tenders (3-5):
I found [N tenders] matching your query. Here are the top results:

**1. Tender #[Number]** - [Ministry]  
⏰ Closes: [Date]  
[One line description]  
[View →]([url])

**2. Tender #[Number]** - [Ministry]  
⏰ Closes: [Date]  
[One line description]  
[View →]([url])

**3. [Same format]**

For many tenders (10+):
I found [N tenders] in total. Here are the 5 most relevant:

1. **[Ministry] - Tender #[Number]**  
   Closes [Date] • [One line] • [View →]([url])

2. **[Ministry] - Tender #[Number]**  
   Closes [Date] • [One line] • [View →]([url])

**IMPORTANT:**
- Be conversational, not robotic
- Use emojis sparingly (📋 ⏰ ⚠️ ✓ only)
- Keep it clean and scannable
- No heavy markdown boxing (---)
- Mobile-friendly format

{metadata_context}**الوثائق / Context Documents:**
{context}
{conversation_context}

**قواعد الجودة / QUALITY RULES:**
- إذا كان السياق غير كافٍ: قل "لم أجد تفاصيل كافية" / "I need more details"
- إذا لم تتطابق المناقصات: اشرح السبب واقترح بدائل
  If no tenders match: explain why and suggest alternatives
- درجة الثقة / Confidence: 0.9+ للتطابق التام، 0.7-0.9 للتطابق الجيد، 0.5-0.7 للتطابق الضعيف
  0.9+ for exact matches, 0.7-0.9 for good matches, 0.5-0.7 for weak matches

**BILINGUAL RESPONSE:**
- Respond primarily in the question's language
- Keep the same conversational, friendly tone in both languages
- Use natural phrasing, not robotic translations
- English: "I found 3 tenders..." not "There are 3 tenders..."
- Arabic: "وجدت 3 مناقصات..." not "يوجد 3 مناقصات..."

**السؤال / Question:**
{question}

أرجع JSON بهذا التنسيق / Return JSON in this format:
{{
  "answer_ar": "إجابة مفصلة بالعربية مع ذكر التفاصيل المهمة والروابط",
  "answer_en": "Detailed English answer with important details and links",
  "citations": [{{"url": "...", "title": "...", "published_at": "..."}}],
  "confidence": 0.85
}}
"""
        
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=2000,
                temperature=0.3,
                messages=[{
                    "role": "user",
                    "content": prompt
                }]
            )
            
            response_text = response.content[0].text
            
            # Parse JSON from response
            import json
            start_idx = response_text.find('{')
            end_idx = response_text.rfind('}') + 1
            
            if start_idx == -1 or end_idx == 0:
                raise ValueError("No JSON found in Claude response")
            
            json_str = response_text[start_idx:end_idx]
            result = json.loads(json_str)
            
            return {
                "answer_ar": result.get("answer_ar", "لم أجد إجابة"),
                "answer_en": result.get("answer_en", "No answer found"),
                "citations": result.get("citations", []),
                "confidence": result.get("confidence", 0.5)
            }
            
        except json.JSONDecodeError as e:
            print(f"❌ JSON parsing error in Claude Q&A: {e}")
            print(f"Claude response: {response_text[:500]}")
            return {
                "answer_ar": "عذراً، حدث خطأ في معالجة البيانات.",
                "answer_en": "Sorry, a data processing error occurred.",
                "citations": [],
                "confidence": 0.3
            }
        except Exception as e:
            print(f"❌ Claude Q&A error: {e}")
            return {
                "answer_ar": "عذراً، حدث خطأ أثناء معالجة سؤالك. يرجى المحاولة مرة أخرى.",
                "answer_en": "Sorry, an error occurred while processing your question. Please try again.",
                "citations": [],
                "confidence": 0.0
            }


# Singleton instance
claude_service = ClaudeOCRService() if settings.ANTHROPIC_API_KEY else None
