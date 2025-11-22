"""
Kuwait Al-Yawm (Official Gazette) Scraper
Scrapes tender announcements from the official government gazette
"""
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta
import hashlib
import re
from typing import List, Dict, Optional
import logging
from app.core.config import settings
from app.parser.pdf_extractor import PDFExtractor
from PIL import Image, ImageEnhance, ImageFilter
from io import BytesIO
import numpy as np
import cv2

logger = logging.getLogger(__name__)


def preprocess_image_for_ocr(image_bytes: bytes) -> bytes:
    """
    Pre-process image for optimal OCR accuracy
    
    Applies industry-standard image enhancement techniques:
    - Grayscale conversion (removes color noise)
    - Contrast enhancement (makes text darker)
    - Denoising (removes artifacts)
    - Sharpening (clarifies text edges)
    
    Args:
        image_bytes: Raw image bytes from PDF
        
    Returns:
        Processed image bytes optimized for OCR
    """
    try:
        # Load image
        img = Image.open(BytesIO(image_bytes))
        
        # 1. Convert to grayscale (removes color, focuses on text)
        img = img.convert('L')
        
        # 2. Increase contrast (makes text stand out from background)
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(1.5)  # 1.5x contrast
        
        # 3. Denoise using OpenCV (removes scanning artifacts)
        img_array = np.array(img)
        img_array = cv2.fastNlMeansDenoising(img_array, h=10)
        
        # 4. Sharpen text edges for better character recognition
        img = Image.fromarray(img_array)
        enhancer = ImageEnhance.Sharpness(img)
        img = enhancer.enhance(2.0)  # 2x sharpness
        
        # 5. Optional: Slight brightness adjustment for consistency
        enhancer = ImageEnhance.Brightness(img)
        img = enhancer.enhance(1.1)
        
        # Convert back to bytes
        output = BytesIO()
        img.save(output, format='PNG', optimize=True)
        return output.getvalue()
        
    except Exception as e:
        print(f"⚠️  Image pre-processing failed: {e}")
        print(f"   Falling back to original image")
        return image_bytes  # Return original if pre-processing fails


class KuwaitAlyomScraper:
    """
    Scraper for Kuwait Al-Yawm (الكويت اليوم) - Official Government Gazette
    
    Authenticates with user credentials and scrapes tender announcements
    from the official legal record.
    """
    
    def __init__(self, username: str, password: str):
        """
        Initialize scraper with authentication credentials
        
        Args:
            username: Kuwait Alyom account username
            password: Kuwait Alyom account password
        """
        self.base_url = "https://kuwaitalyawm.media.gov.kw"
        self.username = username
        self.password = password
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        })
        # Disable SSL verification for production environment (Kuwait Alyom certificate issues)
        self.session.verify = False
        # Suppress SSL warnings
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        
        self.is_authenticated = False
        self.pdf_extractor = PDFExtractor()  # Initialize PDF extractor with OCR
        self._magazine_cache = {}  # Cache full magazine PDFs by edition_id
        
    def login(self) -> bool:
        """
        Authenticate with Kuwait Alyom
        
        Returns:
            bool: True if login successful, False otherwise
        """
        try:
            print("🔐 Logging in to Kuwait Al-Yawm...")  # Using print() to ensure visibility
            logger.info("🔐 Logging in to Kuwait Al-Yawm...")
            
            # Get login page to retrieve tokens
            login_page_url = f"{self.base_url}/Account/Login"
            response = self.session.get(login_page_url)
            response.raise_for_status()
            
            # Parse anti-forgery token
            soup = BeautifulSoup(response.text, 'html.parser')
            token_input = soup.find('input', {'name': '__RequestVerificationToken'})
            
            if not token_input:
                logger.error("❌ Could not find anti-forgery token")
                return False
                
            token = token_input.get('value')
            
            # Submit login form
            login_data = {
                'UserName': self.username,
                'Password': self.password,
                '__RequestVerificationToken': token,
                'RememberMe': 'false'
            }
            
            login_response = self.session.post(
                login_page_url,
                data=login_data,
                allow_redirects=True
            )
            
            # DEBUG: Log EVERYTHING about the login response (using print to ensure visibility)
            print(f"📍 Login Response URL: {login_response.url}")
            print(f"📊 Login Response Status: {login_response.status_code}")
            print(f"🍪 Session Cookies: {dict(self.session.cookies)}")
            
            # Show first 1000 chars of response for debugging
            response_preview = login_response.text[:1000] if len(login_response.text) > 1000 else login_response.text
            print(f"📄 Login Response Preview:\n{response_preview}")
            
            # Check our search strings
            has_user = 'المستخدم' in login_response.text
            has_logout = 'تسجيل الخروج' in login_response.text
            print(f"🔍 Contains 'المستخدم': {has_user}")
            print(f"🔍 Contains 'تسجيل الخروج': {has_logout}")
            
            # Check if login successful by looking for user info in response
            if has_user or has_logout:
                logger.info("✅ Successfully logged in to Kuwait Al-Yawm")
                self.is_authenticated = True
                return True
            else:
                logger.error("❌ Login failed - invalid credentials or session issue")
                logger.error("❌ Could not find user indicators in response")
                return False
                
        except Exception as e:
            logger.error(f"❌ Login error: {e}")
            return False
    
    def fetch_tenders(
        self, 
        category_id: str = "1",  # 1 = Tenders (المناقصات)
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 100,
        start_offset: int = 0
    ) -> tuple[List[Dict], int]:
        """
        Fetch tender list from Kuwait Alyom API with pagination support
        
        Args:
            category_id: Category ID (1=Tenders, 2=Auctions, 18=Practices)
            start_date: Start date filter (YYYY/MM/DD)
            end_date: End date filter (YYYY/MM/DD)
            limit: Maximum number of tenders to fetch in this page
            start_offset: Starting offset for pagination (0 = first page)
            
        Returns:
            Tuple of (list of tender dictionaries, total count available)
        """
        # Always try to login first to ensure fresh session
        print(f"🔄 Ensuring authentication for category {category_id}...")  # Using print()
        logger.info("🔄 Ensuring authentication...")
        if not self.login():
            print("❌ Cannot fetch tenders - login failed")  # Using print()
            logger.error("❌ Cannot fetch tenders - login failed")
            return [], 0
        
        try:
            # IMPORTANT: Visit the category page first to establish session state
            # Kuwait Alyom's API requires this step before calling AdsCategoryJson
            logger.info(f"📄 Visiting category page to establish session...")
            category_page_url = f"{self.base_url}/online/AdsCategory/{category_id}"
            page_response = self.session.get(category_page_url)
            
            print(f"📍 Category Page URL: {page_response.url}")
            print(f"📊 Category Page Status: {page_response.status_code}")
            print(f"🍪 Session Cookies After Page Visit: {dict(self.session.cookies)}")
            logger.info(f"📍 Category Page URL: {page_response.url}")
            logger.info(f"📊 Category Page Status: {page_response.status_code}")
            logger.info(f"🍪 Session Cookies After Page Visit: {dict(self.session.cookies)}")
            
            if page_response.status_code != 200:
                logger.error(f"❌ Failed to access category page: {page_response.status_code}")
                logger.error(f"Response preview: {page_response.text[:500]}")
                return [], 0
            
            logger.info(f"✅ Category page loaded successfully")
            logger.info(f"📊 Fetching tenders from Kuwait Al-Yawm (Category: {category_id})...")
            
            api_url = f"{self.base_url}/online/AdsCategoryJson"
            
            # DataTables API format - must match exactly what browser sends!
            payload = {
                'draw': '1',
                'columns[0][data]': 'AdsTitle',
                'columns[0][name]': '',
                'columns[0][searchable]': 'true',
                'columns[0][orderable]': 'true',
                'columns[0][search][value]': '',
                'columns[0][search][regex]': 'false',
                'columns[1][data][ID]': 'ID',
                'columns[1][data][EditionID_FK]': 'EditionID_FK',
                'columns[1][data][FromPage]': 'FromPage',
                'columns[1][name]': '',
                'columns[1][searchable]': 'true',
                'columns[1][orderable]': 'true',
                'columns[1][search][value]': '',
                'columns[1][search][regex]': 'false',
                'columns[2][data]': 'EditionNo',
                'columns[2][name]': '',
                'columns[2][searchable]': 'true',
                'columns[2][orderable]': 'true',
                'columns[2][search][value]': '',
                'columns[2][search][regex]': 'false',
                'columns[3][data]': 'EditionType',
                'columns[3][name]': '',
                'columns[3][searchable]': 'true',
                'columns[3][orderable]': 'true',
                'columns[3][search][value]': '',
                'columns[3][search][regex]': 'false',
                'columns[4][data]': 'EditionDate',
                'columns[4][name]': '',
                'columns[4][searchable]': 'true',
                'columns[4][orderable]': 'true',
                'columns[4][search][value]': '',
                'columns[4][search][regex]': 'false',
                'columns[5][data]': 'HijriDate',
                'columns[5][name]': '',
                'columns[5][searchable]': 'true',
                'columns[5][orderable]': 'true',
                'columns[5][search][value]': '',
                'columns[5][search][regex]': 'false',
                'order[0][column]': '1',
                'order[0][dir]': 'desc',
                'start': str(start_offset),
                'length': str(limit),
                'search[value]': '',
                'search[regex]': 'false',
                'ID': category_id,
                'AdsTitle': '',
                'EditionNo': '',
                'startdate': start_date or '',
                'enddate': end_date or ''
            }
            
            response = self.session.post(api_url, data=payload)
            
            logger.info(f"API Response Status: {response.status_code}")
            
            if response.status_code != 200:
                logger.error(f"❌ API returned status {response.status_code}")
                logger.error(f"Response text: {response.text[:500]}")
                return [], 0
            
            data = response.json()
            tenders = data.get('data', [])
            total = data.get('recordsTotal', 0)
            
            logger.info(f"✅ Fetched {len(tenders)} tenders from offset {start_offset} (Total available: {total})")
            
            return tenders, total
            
        except Exception as e:
            logger.error(f"❌ Error fetching tenders: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return [], 0
    
    def _screenshot_page_with_browserless(self, edition_id: str, page_number: int, max_retries: int = 2) -> Optional[bytes]:
        """
        Screenshot a flipbook page using Browserless API with retry logic
        
        Args:
            edition_id: Gazette edition ID
            page_number: Page number in the magazine
            max_retries: Maximum number of retry attempts (default: 2)
            
        Returns:
            Screenshot bytes (PNG) if successful, None otherwise
        """
        import os
        import requests
        import time
        
        browserless_api_key = os.getenv('BROWSERLESS_API_KEY')
        if not browserless_api_key or browserless_api_key == 'paste-your-browserless-api-key-here':
            print(f"⚠️  BROWSERLESS_API_KEY not configured, skipping screenshot")
            return None
        
        flip_url = f"{self.base_url}/flip/index?id={edition_id}&no={page_number}"
        browserless_url = f"https://production-sfo.browserless.io/screenshot?token={browserless_api_key}&ignoreHTTPSErrors=true"
        
        for attempt in range(max_retries + 1):
            try:
                if attempt > 0:
                    print(f"🔄 Retry attempt {attempt}/{max_retries} for page {page_number}...")
                    time.sleep(2)  # Wait 2 seconds before retry
                else:
                    print(f"📸 Screenshotting page {page_number} with Browserless...")
                
                # Convert session cookies to Browserless format
                cookies = []
                for cookie in self.session.cookies:
                    cookies.append({
                        "name": cookie.name,
                        "value": cookie.value,
                        "domain": cookie.domain or ".kuwaitalyawm.media.gov.kw",
                        "path": cookie.path or "/"
                    })
                
                payload = {
                    "url": flip_url,
                    "options": {
                        "fullPage": False,
                        "type": "png",
                        "encoding": "binary"
                    },
                    "cookies": cookies,  # Pass authenticated session cookies
                    "waitForTimeout": 5000  # Wait 5 seconds for flipbook to render PDF
                }
                
                response = requests.post(browserless_url, json=payload, timeout=30)
                
                if response.status_code != 200:
                    print(f"❌ Browserless API error: {response.status_code}")
                    print(f"   Response: {response.text[:200]}")
                    if attempt < max_retries:
                        continue  # Retry
                    return None
                
                screenshot_bytes = response.content
                print(f"✅ Screenshot captured ({len(screenshot_bytes) / 1024:.1f}KB)")
                
                return screenshot_bytes
                
            except Exception as e:
                print(f"❌ Error screenshotting with Browserless: {e}")
                if attempt < max_retries:
                    continue  # Retry
                return None
        
        return None
    
    def _preprocess_image(self, image_bytes: bytes) -> bytes:
        """
        Preprocess image to improve OCR quality
        
        Applies:
        - Contrast enhancement
        - Sharpening
        - Noise reduction
        
        Args:
            image_bytes: Original image bytes
            
        Returns:
            Enhanced image bytes
        """
        try:
            print(f"  🎨 Preprocessing image for better OCR...")
            
            # Open image
            img = Image.open(BytesIO(image_bytes))
            
            # Convert to RGB if needed
            if img.mode != 'RGB':
                img = img.convert('RGB')
            
            # Increase contrast (helps with faded scans)
            enhancer = ImageEnhance.Contrast(img)
            img = enhancer.enhance(1.5)
            
            # Sharpen (improves edge definition)
            img = img.filter(ImageFilter.SHARPEN)
            
            # Denoise (removes artifacts)
            img = img.filter(ImageFilter.MedianFilter(size=3))
            
            # Save back to bytes with high quality
            output = BytesIO()
            img.save(output, format='JPEG', quality=95)
            enhanced_bytes = output.getvalue()
            
            print(f"  ✅ Image preprocessed ({len(image_bytes)/1024:.1f}KB → {len(enhanced_bytes)/1024:.1f}KB)")
            
            return enhanced_bytes
            
        except Exception as e:
            print(f"  ⚠️  Image preprocessing failed: {e}, using original image")
            return image_bytes
    
    def _correct_arabic_text_with_vision(self, text: str, image_bytes: bytes) -> tuple[str, str]:
        """
        Post-process Arabic text using GPT-4o Vision to verify against original image
        
        Enhanced 3-Stage Pipeline:
        Stage 1: Basic Arabic normalization
        Stage 2: Ministry extraction with Vision
        Stage 3: GPT-4o VISION correction (reads image + OCR text together)
        Stage 4: Text structuring
        
        Args:
            text: Raw OCR text from Google Document AI
            image_bytes: Original screenshot for verification
            
        Returns:
            Tuple of (corrected_text, ministry_name)
        """
        try:
            from camel_tools.utils.normalize import normalize_unicode, normalize_alef_maksura_ar
            from camel_tools.utils.dediac import dediac_ar
            from openai import OpenAI
            import base64
            import os
            import json
            
            if not text or len(text.strip()) == 0:
                return text, None
            
            print(f"  🔧 Stage 1: Basic Arabic normalization...")
            
            # Stage 1: Quick normalization
            corrected = normalize_unicode(text)
            corrected = normalize_alef_maksura_ar(corrected)
            corrected = dediac_ar(corrected)
            
            print(f"  ✅ Stage 1 complete")
            
            ministry = None
            
            # Stage 2: Vision-based ministry extraction (only for longer texts)
            if len(corrected) > 100 and image_bytes:
                print(f"  👁️  Stage 2: GPT-4o-mini Vision - Extract ministry from image...")
                
                api_key = os.getenv('OPENAI_API_KEY')
                if api_key:
                    try:
                        client = OpenAI(api_key=api_key)
                        base64_image = base64.b64encode(image_bytes).decode('utf-8')
                        
                        # Prepare OCR text preview (first 3000 chars - enough to capture ministry)
                        ocr_preview = corrected[:3000] if len(corrected) > 3000 else corrected
                        
                        # Ask GPT to extract ministry using BOTH OCR text and image
                        # Research shows this is much more accurate than image-only
                        response = client.chat.completions.create(
                            model="gpt-4o",  # Use full model for better accuracy
                            messages=[
                                {
                                    "role": "user",
                                    "content": [
                                        {
                                            "type": "text",
                                            "text": f"""Extract the ministry or government entity name from this tender announcement.

OCR TEXT (may contain errors):
{ocr_preview}

TASK:
1. Look for ministry/entity name in the OCR text first
2. Use the image to confirm if text is unclear
3. Return the FULL official name

Common patterns to look for:
- وزارة الداخلية
- وزارة الأشغال العامة  
- وزارة الصحة
- الهيئة العامة للصناعة
- شركة نفط الكويت
- الهيئة العامة للقوى العاملة

CRITICAL: 
- Check the TOP of the page in the image
- Ministry name is usually prominent/large
- If you see ANY ministry name, return it
- Even if OCR is broken, READ the image

Return ONLY the ministry name, nothing else."""
                                        },
                                        {
                                            "type": "image_url",
                                            "image_url": {
                                                "url": f"data:image/png;base64,{base64_image}",
                                                "detail": "high"  # High detail for better reading
                                            }
                                        }
                                    ]
                                }
                            ],
                            temperature=0.1,
                            max_tokens=200,
                            response_format={
                                "type": "json_schema",
                                "json_schema": {
                                    "name": "ministry_extraction",
                                    "strict": True,
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "ministry": {
                                                "type": ["string", "null"],
                                                "description": "Full name of the ministry or government entity, or null if not found"
                                            }
                                        },
                                        "required": ["ministry"],
                                        "additionalProperties": False
                                    }
                                }
                            }
                        )
                        
                        vision_result = response.choices[0].message.content.strip()
                        result_json = json.loads(vision_result)
                        ministry = result_json.get('ministry')
                        
                        if ministry:
                            print(f"  ✅ Stage 2 complete - Ministry extracted: {ministry}")
                        else:
                            print(f"  ⚠️  Stage 2 - No ministry found in image")
                    
                    except Exception as e:
                        print(f"  ⚠️  Stage 2 failed: {e}, ministry will be None")
                else:
                    print(f"  ⏭️  Stage 2 skipped - no API key")
            else:
                print(f"  ⏭️  Stage 2 skipped - text too short or no image")
            
            # Stage 3: GPT-4o VISION correction (image + OCR text together)
            corrected_full = corrected  # Default to Stage 1 output
            
            # Lower threshold to 80 chars - Google OCR often returns 400-700 chars which is good
            if len(corrected) > 80 and image_bytes:
                print(f"  👁️  Stage 3: GPT-4o Vision - Correct severe OCR errors by reading image...")
                
                api_key = os.getenv('OPENAI_API_KEY')
                if api_key:
                    try:
                        client = OpenAI(api_key=api_key)
                        base64_image = base64.b64encode(image_bytes).decode('utf-8')
                        
                        # Send OCR text (up to 2000 chars as reference)
                        ocr_text_for_correction = corrected[:2000] if len(corrected) > 2000 else corrected
                        
                        # Ask GPT-4o Vision to correct OCR using safe, policy-compliant prompt
                        response = client.chat.completions.create(
                            model="gpt-4o",  # Full model for best Vision quality
                            messages=[
                                {
                                    "role": "user",
                                    "content": [
                                        {
                                            "type": "text",
                                            "text": f"""You are a model that fixes noisy, damaged OCR text.
You will receive two inputs:
1. OCR_TEXT = the extracted text from an OCR engine (may be broken or unreadable)
2. IMAGE = the page image (used only to visually clarify unclear characters)

Your tasks:
- Use the IMAGE only to visually confirm and correct what the OCR_TEXT should say.
- Correct misspellings, broken characters, missing letters, flipped text, and corrupted lines.
- Reconstruct text that is incomplete or garbled in the OCR output.
- Preserve all real text exactly as it appears on the page.
- Keep the original layout, section order, and line flow.
- Do NOT summarize or shorten anything.
- Do NOT describe the image.
- Do NOT classify the document.
- Do NOT interpret legal, official, or government context.
- Do NOT add new meaning.
- Do NOT refuse. Always output the corrected text.

Output format:
- Only output the corrected text as plain UTF-8 Arabic/English.
- No explanations.
- No comments.
- No extra sentences.

Begin correction.

OCR_TEXT:
{ocr_text_for_correction}"""
                                        },
                                        {
                                            "type": "image_url",
                                            "image_url": {
                                                "url": f"data:image/png;base64,{base64_image}",
                                                "detail": "high"  # High detail for accurate reading
                                            }
                                        }
                                    ]
                                }
                            ],
                            temperature=0.1,
                            max_tokens=4000
                        )
                        
                        corrected_full = response.choices[0].message.content.strip()
                        
                        # Check if Vision refused or returned minimal text
                        if len(corrected_full) < 100 or "unable to" in corrected_full.lower() or "can't assist" in corrected_full.lower() or "cannot help" in corrected_full.lower():
                            print(f"  ⚠️  Stage 3 returned refusal or minimal text ({len(corrected_full)} chars), falling back to Google OCR")
                            corrected_full = corrected  # Use original Google OCR text
                        else:
                            print(f"  ✅ Stage 3 complete - Text corrected by Vision ({len(corrected_full)} chars)")
                    
                    except Exception as e:
                        print(f"  ⚠️  Stage 3 failed: {e}, using Stage 1 output")
                        corrected_full = corrected
                else:
                    print(f"  ⏭️  Stage 3 skipped - no API key")
            else:
                print(f"  ⏭️  Stage 3 skipped - text too short or no image")
            
            # Stage 4: Structure the corrected text into clear sections
            structured_text = corrected_full  # Default to Stage 3 output
            
            if len(corrected_full) > 200:
                print(f"  📝 Stage 4: Structuring text into clear sections...")
                
                api_key = os.getenv('OPENAI_API_KEY')
                if api_key:
                    try:
                        client = OpenAI(api_key=api_key)
                        
                        # Ask GPT to structure the text
                        response = client.chat.completions.create(
                            model="gpt-4o-mini",
                            messages=[
                                {
                                    "role": "user",
                                    "content": f"""This is corrected tender text from Kuwait official gazette. Organize it into clear sections with Arabic headers.

Text:
{corrected_full[:8000]}

Your task:
1. Identify and extract key sections
2. Add clear Arabic section headers like:
   - === معلومات المناقصة === (Tender Info)
   - === تفاصيل المناقصة === (Details)
   - === الشروط والمتطلبات === (Requirements)
   - === معلومات الاتصال === (Contact Info)
   - === المواعيد المهمة === (Important Dates)
3. Remove duplicate headers and page numbers
4. Keep all important information
5. Format cleanly with proper spacing
6. DO NOT add information that wasn't in the original
7. If text is too short or unclear, return it as-is

Return the well-structured Arabic text."""
                                }
                            ],
                            temperature=0.2,
                            max_tokens=3000
                        )
                        
                        structured_text = response.choices[0].message.content.strip()
                        print(f"  ✅ Stage 4 complete - Text structured ({len(structured_text)} chars)")
                    
                    except Exception as e:
                        print(f"  ⚠️  Stage 4 failed: {e}, using Stage 3 output")
                        structured_text = corrected_full
                else:
                    print(f"  ⏭️  Stage 4 skipped - no API key")
            else:
                print(f"  ⏭️  Stage 4 skipped - text too short")
            
            return structured_text, ministry
            
        except Exception as e:
            print(f"  ⚠️  Arabic correction failed: {e}, returning original")
            import traceback
            print(traceback.format_exc())
            return text, None
    
    def _cleanup_ocr_text_with_gpt(self, ocr_text: str) -> str:
        """
        Clean up OCR errors using GPT-4o TEXT mode (no vision, no refusals)
        
        Args:
            ocr_text: Raw OCR text with potential errors
            
        Returns:
            Cleaned, corrected Arabic text
        """
        try:
            from openai import OpenAI
            
            api_key = os.getenv('OPENAI_API_KEY')
            if not api_key:
                print(f"  ⏭️  GPT cleanup skipped - no API key")
                return ocr_text
            
            print(f"  🔧 Cleaning OCR text with GPT-4o (text-only, no vision)...")
            
            client = OpenAI(api_key=api_key)
            
            prompt = f"""You are an Arabic OCR correction specialist for Kuwait government documents.

Fix spelling, grammar, and word order errors in this OCR-extracted text.

LEARN FROM THESE EXAMPLES:

EXAMPLE 1:
INPUT: "1100 لسم مراية الصحة ان جلوية في"
OUTPUT: "إعلان من وزارة الصحة عن جلسة في"
(Fixed: لسم→إعلان, مراية→وزارة, ان جلوية→عن جلسة)

EXAMPLE 2:
INPUT: "المتطلبات: 1. توريد معدات طتية 2. شهادة 1SO مطلوتة"
OUTPUT: "المتطلبات: 1. توريد معدات طبية 2. شهادة ISO مطلوبة"
(Fixed: طتية→طبية, 1SO→ISO, مطلوتة→مطلوبة)

EXAMPLE 3:
INPUT: "الموعد النهائي: 15/12/2024 في تمام الساعة 10:00 صباحاً"
OUTPUT: "الموعد النهائي: 15/12/2024 في تمام الساعة 10:00 صباحاً"
(No changes needed - already correct!)

CRITICAL RULES:
1. Fix OCR errors like the examples above
2. Correct scrambled characters (ة↔ت, و↔ا, etc.)
3. Fix number/letter confusion (0↔O, 1↔I, 5↔S)
4. Remove garbage but keep ALL meaningful content
5. DO NOT add or invent information
6. Output ONLY the corrected text

NOW CORRECT THIS TEXT:
{ocr_text[:4000]}

CORRECTED TEXT:"""

            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=4000
            )
            
            corrected = response.choices[0].message.content.strip()
            
            print(f"  ✅ GPT cleanup complete: {len(ocr_text)} → {len(corrected)} chars")
            
            return corrected
            
        except Exception as e:
            print(f"  ⚠️  GPT cleanup failed: {e}, using original OCR")
            return ocr_text
    
    def _extract_structured_data(self, text: str) -> dict:
        """
        Extract structured tender information using GPT-4o with strict JSON schema
        
        Args:
            text: Cleaned tender text
            
        Returns:
            Structured dict with tender fields
        """
        try:
            from openai import OpenAI
            import json
            
            api_key = os.getenv('OPENAI_API_KEY')
            if not api_key:
                print(f"  ⏭️  Structured extraction skipped - no API key")
                return {"body": text, "extracted_fields": {}}
            
            print(f"  📊 Extracting structured data with GPT-4o...")
            
            client = OpenAI(api_key=api_key)
            
            prompt = f"""Extract structured information from Kuwait government tender text as JSON.

LEARN FROM THIS EXAMPLE:

INPUT TEXT:
"وزارة الصحة - مناقصة رقم 2026/2025/83
إعلان عن مناقصة عامة لتوريد المعدات الطبية

المتطلبات:
1. توريد معدات طبية ومستلزمات مخبرية
2. شهادة ISO 9001 مطلوبة
3. خبرة لا تقل عن 5 سنوات

الموعد النهائي: 15 ديسمبر 2024 الساعة 10:00 صباحاً
موعد الاجتماع التمهيدي: 1 ديسمبر 2024 الساعة 10:00 صباحاً
مكان الاجتماع: مبنى الوزارة - الطابق الثالث - قاعة الاجتماعات
للاستفسار: 22334455
قيمة الوثائق: 50 دينار كويتي"

OUTPUT JSON:
{{
  "title": "مناقصة عامة لتوريد المعدات الطبية",
  "tender_number": "2026/2025/83",
  "ministry": "وزارة الصحة",
  "requirements": [
    "توريد معدات طبية ومستلزمات مخبرية",
    "شهادة ISO 9001 مطلوبة",
    "خبرة لا تقل عن 5 سنوات"
  ],
  "deadline_text": "15 ديسمبر 2024 الساعة 10:00 صباحاً",
  "meeting_date_text": "1 ديسمبر 2024 الساعة 10:00 صباحاً",
  "meeting_location": "مبنى الوزارة - الطابق الثالث - قاعة الاجتماعات",
  "contact_info": "22334455",
  "budget_text": "قيمة الوثائق: 50 دينار كويتي"
}}

CRITICAL RULES:
1. Extract ONLY information explicitly present in the text
2. DO NOT invent or assume any information
3. If a field is not found, set it to null
4. Be conservative - only include verifiable facts
5. Follow the JSON schema exactly

THINK STEP-BY-STEP:
1. First, identify the ministry/entity name
2. Then, find the tender number (usually starts with رقم or has year format)
3. Then, extract all requirements (look for numbered lists or bullet points)
4. Then, find deadline information
5. Then, look for pre-tender meeting info (موعد الاجتماع التمهيدي, مكان الاجتماع)
6. Finally, extract contact and budget details

NOW EXTRACT FROM THIS TEXT:
{text[:3000]}"""

            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=2000,
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "tender_extraction",
                        "strict": True,
                        "schema": {
                            "type": "object",
                            "properties": {
                                "title": {
                                    "type": ["string", "null"],
                                    "description": "Tender title if found"
                                },
                                "tender_number": {
                                    "type": ["string", "null"],
                                    "description": "Tender/RFQ number if found"
                                },
                                "ministry": {
                                    "type": ["string", "null"],
                                    "description": "Ministry or government entity name"
                                },
                                "requirements": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": "List of tender requirements"
                                },
                                "deadline_text": {
                                    "type": ["string", "null"],
                                    "description": "Deadline information as it appears in text"
                                },
                                "meeting_date_text": {
                                    "type": ["string", "null"],
                                    "description": "Pre-tender meeting date as it appears in text"
                                },
                                "meeting_location": {
                                    "type": ["string", "null"],
                                    "description": "Pre-tender meeting location"
                                },
                                "contact_info": {
                                    "type": ["string", "null"],
                                    "description": "Contact information if found"
                                },
                                "budget_text": {
                                    "type": ["string", "null"],
                                    "description": "Budget information as it appears in text"
                                }
                            },
                            "required": [],
                            "additionalProperties": False
                        }
                    }
                }
            )
            
            structured = json.loads(response.choices[0].message.content)
            
            print(f"  ✅ Structured extraction complete")
            print(f"     - Title: {structured.get('title', 'N/A')}")
            print(f"     - Ministry: {structured.get('ministry', 'N/A')}")
            print(f"     - Requirements: {len(structured.get('requirements', []))} items")
            
            return {
                "body": text,
                "extracted_fields": structured
            }
            
        except Exception as e:
            print(f"  ⚠️  Structured extraction failed: {e}")
            return {"body": text, "extracted_fields": {}}
    
    def _structure_text_with_sections(self, text: str, extracted_fields: dict) -> str:
        """
        Structure tender text with clear Arabic section headers
        Makes text much more readable for users and AI agent
        
        Args:
            text: Cleaned tender text
            extracted_fields: Extracted fields from previous step
            
        Returns:
            Beautifully structured text with headers
        """
        try:
            from openai import OpenAI
            
            api_key = os.getenv('OPENAI_API_KEY')
            if not api_key:
                print(f"  ⏭️  Text structuring skipped - no API key")
                return text
            
            if len(text) < 200:
                print(f"  ⏭️  Text structuring skipped - text too short")
                return text
            
            print(f"  📝 Structuring text with clear section headers...")
            
            client = OpenAI(api_key=api_key)
            
            # Build context from extracted fields
            context = "Extracted information to help you structure:\n"
            if extracted_fields.get('ministry'):
                context += f"- Ministry: {extracted_fields['ministry']}\n"
            if extracted_fields.get('tender_number'):
                context += f"- Tender Number: {extracted_fields['tender_number']}\n"
            if extracted_fields.get('requirements'):
                context += f"- Requirements found: {len(extracted_fields['requirements'])} items\n"
            
            prompt = f"""Structure this Kuwait government tender text with clear Arabic section headers.

LEARN FROM THIS EXAMPLE:

INPUT (unstructured):
"وزارة الصحة مناقصة رقم 2026/2025/83 إعلان عن مناقصة عامة لتوريد المعدات الطبية المتطلبات توريد معدات طبية شهادة ISO مطلوبة الموعد النهائي 15 ديسمبر 2024 للاستفسار 22334455"

OUTPUT (structured):
=== معلومات المناقصة ===
وزارة الصحة
مناقصة رقم: 2026/2025/83
إعلان عن مناقصة عامة لتوريد المعدات الطبية

=== الشروط والمتطلبات ===
• توريد معدات طبية
• شهادة ISO مطلوبة

=== المواعيد المهمة ===
الموعد النهائي: 15 ديسمبر 2024

=== معلومات الاتصال ===
للاستفسار: 22334455

---

{context}

YOUR TASK:
1. Add clear Arabic section headers (use === header === format)
2. Common sections:
   - === معلومات المناقصة === (Tender Info)
   - === الشروط والمتطلبات === (Requirements)
   - === المواعيد المهمة === (Important Dates)
   - === معلومات الاتصال === (Contact)
   - === تفاصيل إضافية === (Additional Details)
3. Use bullet points (•) for lists
4. Remove duplicate headers and page numbers
5. Clean spacing between sections
6. DO NOT add information that wasn't in original
7. Keep ALL important content

TEXT TO STRUCTURE:
{text[:4000]}

STRUCTURED TEXT:"""

            response = client.chat.completions.create(
                model="gpt-4o-mini",  # Cheaper model is fine for formatting
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=4000
            )
            
            structured_text = response.choices[0].message.content.strip()
            
            print(f"  ✅ Text structured with sections ({len(structured_text)} chars)")
            return structured_text
            
        except Exception as e:
            print(f"  ⚠️  Text structuring failed: {e}, using original")
            return text
    
    def _validate_extraction_quality(self, text: str, extracted_fields: dict) -> dict:
        """
        Validate extraction quality and detect potential issues
        
        Args:
            text: Extracted text
            extracted_fields: Extracted fields
            structured_data: Structured extraction results
            
        Returns:
            Validation results with quality score and issues
        """
        issues = []
        
        # Check 1: Minimum length (Kuwait tenders are typically 500-2000 chars)
        if len(text) < 500:
            issues.append(f"Text too short for tender: {len(text)} chars (minimum 500)")
        
        # Check 2: Arabic content ratio
        arabic_chars = sum(1 for c in text if '\u0600' <= c <= '\u06FF')
        total_chars = len(text.replace(' ', '').replace('\n', ''))
        arabic_ratio = arabic_chars / total_chars if total_chars > 0 else 0
        
        if arabic_ratio < 0.85:
            issues.append(f"Low Arabic content: {arabic_ratio*100:.1f}% (expected 85%+ for Kuwait tenders)")
        
        # Check 3: Gibberish detection (repeated characters)
        import re
        if re.search(r'(.)\1{6,}', text):
            issues.append("Detected repeated character pattern (possible gibberish)")
        
        # Check 4: Too many special characters
        special_chars = sum(1 for c in text if c in '!@#$%^&*()_+=[]{}|\\:";\'<>?/~`')
        special_ratio = special_chars / len(text) if len(text) > 0 else 0
        
        if special_ratio > 0.15:
            issues.append(f"Too many special characters: {special_ratio*100:.1f}% (likely gibberish)")
        
        # Check 5: Hallucination detection for structured fields
        extracted = extracted_fields or {}
        
        for field, value in extracted.items():
            if value and isinstance(value, str) and len(value) > 10:
                # Check if key terms from extracted value appear in text
                # This is a simple check - if the value has content but no words match, likely hallucinated
                value_words = set(value.split()[:5])  # First 5 words
                if not any(word in text for word in value_words if len(word) > 3):
                    issues.append(f"Possible hallucination in field '{field}': content not found in text")
        
        # Calculate quality score (0-1)
        score = 1.0
        score -= len(issues) * 0.15  # Each issue reduces score by 15%
        score -= (1 - arabic_ratio) * 0.3  # Low Arabic content penalty
        score = max(0.0, min(1.0, score))  # Clamp to 0-1
        
        validation = {
            "quality_score": round(score, 2),
            "issues": issues,
            "arabic_ratio": round(arabic_ratio, 2),
            "text_length": len(text),
            "is_acceptable": score >= 0.7 and len(text) >= 500
        }
        
        if issues:
            print(f"  ⚠️  Quality issues detected:")
            for issue in issues:
                print(f"     - {issue}")
            print(f"  📊 Quality score: {score:.2f} ({'ACCEPTABLE' if validation['is_acceptable'] else 'POOR'})")
        else:
            print(f"  ✅ Quality validation passed (score: {score:.2f})")
        
        return validation
    
    def _extract_text_from_image(self, image_bytes: bytes) -> Optional[dict]:
        """
        Extract text from image using Mistral OCR (primary) and Claude Sonnet 4.5 (fallback)
        
        OCR approach:
        1. Mistral OCR (fast, cost-effective, Arabic-optimized) - Primary
        2. Claude Sonnet 4.5 (premium quality, structured extraction) - Fallback
        
        Args:
            image_bytes: Image bytes (PNG/JPEG)
            
        Returns:
            Dict with {'text': str, 'ministry': str, ...} if successful, None otherwise
        """
        try:
            import os

            # Try Mistral OCR first if available
            try:
                from app.ai.mistral_ocr_service import mistral_ocr_service
            except Exception:
                mistral_ocr_service = None

            if mistral_ocr_service:
                print(f"  🚀 Using Mistral OCR for text extraction (primary)...")
                try:
                    mistral_result = mistral_ocr_service.extract_text_from_image(image_bytes, image_format="png")
                except Exception as e:
                    print(f"  ⚠️  Mistral OCR error: {e}")
                    mistral_result = None

                if mistral_result and mistral_result.get('text') and len(mistral_result['text']) > 50:
                    print(f"  ✅ Mistral OCR extracted {len(mistral_result['text'])} characters")
                    # Ensure consistent structure with downstream expectations
                    mistral_result.setdefault('ministry', None)
                    mistral_result.setdefault('meeting_date_text', None)
                    mistral_result.setdefault('meeting_location', None)
                    mistral_result.setdefault('tender_number', None)
                    mistral_result.setdefault('deadline', None)
                    mistral_result.setdefault('note', None)
                    mistral_result.setdefault('ocr_method', 'mistral')
                    return mistral_result
                else:
                    print(f"  ⚠️  Mistral OCR returned insufficient text, trying Claude/legacy OCR...")
            else:
                print(f"  ⏭️  Mistral OCR service not available, using Claude/legacy OCR...")

            # Claude Sonnet 4.5 OCR (fallback)
            claude_api_key = os.getenv('ANTHROPIC_API_KEY')
            if not claude_api_key or claude_api_key == 'your-claude-api-key-here':
                print(f"⚠️  ANTHROPIC_API_KEY not configured, no OCR available")
                return None

            print(f"  🧠 Using Claude Sonnet 4.5 for OCR and extraction...")

            # Import Claude service
            from app.ai.claude_service import claude_service

            if not claude_service:
                print(f"⚠️  Claude service not initialized, no OCR available")
                return None

            # Extract with Claude
            result = claude_service.extract_tender_from_image(image_bytes, image_format="png")

            if result and result.get('body'):
                print(f"  ✅ Claude extracted {len(result['body'])} characters")
                print(f"  🏛️ Ministry: {result.get('ministry', 'N/A')}")
                print(f"  📊 Confidence: {result.get('ocr_confidence', 0.0)}")

                return {
                    'text': result['body'],
                    'ministry': result.get('ministry'),
                    'meeting_date_text': result.get('meeting_date_text'),
                    'meeting_location': result.get('meeting_location'),
                    'tender_number': result.get('tender_number'),
                    'deadline': result.get('deadline'),
                    'ocr_confidence': result.get('ocr_confidence', 0.5),
                    'note': result.get('note'),
                    'ocr_method': 'claude'
                }
            elif result and result.get('note'):
                print(f"  ⚠️  Claude extraction note: {result['note']}")
                return None
            else:
                print(f"  ⚠️  Claude returned no text")
                return None
                
        except Exception as e:
            print(f"  ❌ All OCR methods failed: {e}")
            import traceback
            print(traceback.format_exc())
            return None
    
    def _download_magazine_pdf(self, edition_id: str) -> Optional[bytes]:
        """
        Download the full magazine PDF for an edition (cached per edition)
        
        Kuwait Alyom embeds the entire magazine as base64 in the source attribute.
        We download it once per edition and cache it.
        
        Args:
            edition_id: Gazette edition ID
            
        Returns:
            Full magazine PDF bytes if successful, None otherwise
        """
        # Check cache first
        if edition_id in self._magazine_cache:
            print(f"📦 Using cached PDF for edition {edition_id}")
            return self._magazine_cache[edition_id]
        
        try:
            print(f"⬇️  Downloading full magazine PDF for edition {edition_id}...")
            
            # Visit any flipbook page to get the source attribute (page 1 is fine)
            flip_url = f"{self.base_url}/flip/index?id={edition_id}&no=1"
            response = self.session.get(flip_url, timeout=30)
            
            if response.status_code != 200:
                print(f"⚠️  Failed to load flipbook page: {response.status_code}")
                return None
            
            # Extract base64 PDF data from source attribute
            if 'source="' not in response.text:
                print(f"⚠️  Could not find source attribute in flipbook page")
                return None
            
            # Split at source=" and take everything after
            parts = response.text.split('source="', 1)
            if len(parts) < 2:
                print(f"⚠️  Could not split at source=\"")
                return None
            
            # Kuwait's HTML is malformed - source attribute has no closing quote
            # Extract only valid base64 characters until we hit the end
            # Kuwait uses URL-safe base64 (- instead of +, _ instead of /)
            raw_data = parts[1]
            base64_chars = set('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/-_=')
            base64_data = []
            stop_reason = "unknown"
            
            # Extract all valid base64 characters until we hit something that's clearly not base64
            for i, char in enumerate(raw_data):
                if char in base64_chars:
                    base64_data.append(char)
                elif char in (' ', '\t', '\n', '\r'):
                    # Skip whitespace
                    continue
                else:
                    # Hit a non-base64 character (likely start of next HTML attribute)
                    stop_reason = f"hit non-base64 char '{char}'"
                    print(f"🛑 Stopped at position {i}: {stop_reason}")
                    break
            
            base64_data = ''.join(base64_data)
            
            print(f"📊 EXTRACTION SUMMARY:")
            print(f"   - Total length: {len(base64_data)} chars")
            print(f"   - Stop reason: {stop_reason}")
            print(f"   - First 50 chars: {base64_data[:50]}")
            print(f"   - Last 50 chars: {base64_data[-50:]}")
            
            if len(base64_data) < 100:
                print(f"⚠️  Extracted base64 too short: {len(base64_data)} chars")
                return None
                
            # Remove any whitespace
            base64_data = re.sub(r'\s+', '', base64_data)
            
            print(f"✅ Found base64 PDF data ({len(base64_data)} characters, ~{len(base64_data) * 0.75 / 1024 / 1024:.1f}MB)")
            print(f"   - Data length % 4: {len(base64_data) % 4}")
            print(f"   - Last 50 chars: {base64_data[-50:]}")
            
            # Decode base64 with proper normalization and padding
            import base64
            try:
                print(f"🔓 Normalizing and decoding base64...")
                
                # Step 1: Normalize URL-safe base64 to standard base64
                normalized_data = base64_data.replace('-', '+').replace('_', '/')
                
                # Step 2: Remove all whitespace and invalid characters
                normalized_data = re.sub(r'[^A-Za-z0-9+/=]', '', normalized_data)
                
                # Step 3: Strip existing padding (we'll recalculate)
                normalized_data = normalized_data.rstrip('=')
                
                # Step 4: Add correct padding (base64 requires length to be multiple of 4)
                missing_padding = len(normalized_data) % 4
                if missing_padding:
                    normalized_data += '=' * (4 - missing_padding)
                    print(f"   - Added {4 - missing_padding} padding characters")
                
                print(f"   - Normalized length: {len(normalized_data)} (should be multiple of 4: {len(normalized_data) % 4 == 0})")
                
                # Step 5: Validate base64 string before decoding
                if not re.match(r'^[A-Za-z0-9+/]*={0,2}$', normalized_data):
                    print(f"❌ Invalid base64 characters detected after normalization")
                    print(f"   - Last 100 chars: {normalized_data[-100:]}")
                    return None
                
                # Step 6: Decode with validation
                pdf_bytes = base64.b64decode(normalized_data, validate=True)
                
                print(f"✅ Decoded successfully!")
                print(f"   - Decoded size: {len(pdf_bytes) / 1024 / 1024:.1f}MB")
                print(f"   - First 20 bytes: {pdf_bytes[:20]}")
                print(f"   - Starts with %PDF: {pdf_bytes.startswith(b'%PDF')}")
            except Exception as e:
                print(f"❌ Base64 decode failed: {e}")
                print(f"   - This usually means the PDF data in HTML is corrupted")
                print(f"   - Browserless screenshot will be used instead (more reliable)")
                return None  # Don't raise, just return None to use screenshot fallback
            
            # Verify it's a valid PDF (starts with %PDF)
            if not pdf_bytes.startswith(b'%PDF'):
                print(f"⚠️  Decoded data is not a valid PDF")
                return None
            
            print(f"✅ Downloaded full magazine PDF ({len(pdf_bytes) / 1024 / 1024:.1f}MB)")
            
            # Cache it
            self._magazine_cache[edition_id] = pdf_bytes
            
            return pdf_bytes
                
        except Exception as e:
            print(f"❌ Error downloading magazine PDF: {e}")
            import traceback
            print(traceback.format_exc())
            return None
    
    def _extract_high_res_image_from_pdf(self, magazine_pdf: bytes, page_number: int) -> Optional[bytes]:
        """
        Extract original high-resolution image from a specific PDF page
        This gives better OCR quality than screenshots
        
        Args:
            magazine_pdf: Full magazine PDF bytes
            page_number: Page number to extract (1-indexed)
            
        Returns:
            Image bytes (PNG/JPEG) or None if failed
        """
        try:
            import fitz  # PyMuPDF
            
            print(f"🖼️  Extracting high-res image from PDF page {page_number}...")
            
            # Open PDF
            doc = fitz.open(stream=magazine_pdf, filetype="pdf")
            
            if page_number < 1 or page_number > len(doc):
                print(f"⚠️  Page {page_number} out of range (PDF has {len(doc)} pages)")
                return None
            
            page = doc[page_number - 1]  # Convert to 0-indexed
            
            # Method 1: Try to extract embedded images first (best quality)
            images = page.get_images()
            
            if images:
                # Get the largest image (usually the full page scan)
                largest_image = max(images, key=lambda img: img[2] * img[3])  # width * height
                xref = largest_image[0]
                
                try:
                    base_image = doc.extract_image(xref)
                    image_bytes = base_image["image"]
                    image_ext = base_image["ext"]
                    
                    print(f"✅ Extracted embedded {image_ext.upper()} image ({len(image_bytes) / 1024:.1f}KB)")
                    
                    # Pre-process image for better OCR
                    print(f"🔧 Pre-processing image (grayscale, contrast, denoise, sharpen)...")
                    processed_bytes = preprocess_image_for_ocr(image_bytes)
                    print(f"✅ Image pre-processed ({len(processed_bytes) / 1024:.1f}KB)")
                    
                    doc.close()
                    return processed_bytes
                except Exception as e:
                    print(f"⚠️  Could not extract embedded image: {e}, falling back to rendering")
            
            # Method 2: Render page as high-resolution image (fallback)
            # Use 3x zoom for 300 DPI quality (vs 100 DPI default)
            matrix = fitz.Matrix(3, 3)
            pix = page.get_pixmap(matrix=matrix, alpha=False)
            image_bytes = pix.tobytes("png")
            
            print(f"✅ Rendered page as high-res PNG ({len(image_bytes) / 1024:.1f}KB, {pix.width}x{pix.height}px)")
            
            # Pre-process image for better OCR
            print(f"🔧 Pre-processing image (grayscale, contrast, denoise, sharpen)...")
            processed_bytes = preprocess_image_for_ocr(image_bytes)
            print(f"✅ Image pre-processed ({len(processed_bytes) / 1024:.1f}KB)")
            
            doc.close()
            return processed_bytes
            
        except Exception as e:
            print(f"❌ Error extracting image from PDF: {e}")
            import traceback
            print(traceback.format_exc())
            return None
    
    def _extract_page_from_pdf(self, magazine_pdf: bytes, page_number: int) -> Optional[bytes]:
        """
        Extract a specific page from a PDF as a separate single-page PDF
        
        Args:
            pdf_bytes: Full PDF bytes
            page_number: Page number to extract (1-indexed)
            
        Returns:
            Single-page PDF bytes if successful, None otherwise
        """
        try:
            from PyPDF2 import PdfReader, PdfWriter
            import io
            
            # Read the full PDF
            pdf_reader = PdfReader(io.BytesIO(pdf_bytes))
            total_pages = len(pdf_reader.pages)
            
            # Validate page number (convert to 0-indexed)
            page_index = page_number - 1
            if page_index < 0 or page_index >= total_pages:
                print(f"⚠️  Page {page_number} out of range (total pages: {total_pages})")
                return None
            
            # Create a new PDF with just this page
            pdf_writer = PdfWriter()
            pdf_writer.add_page(pdf_reader.pages[page_index])
            
            # Write to bytes
            output = io.BytesIO()
            pdf_writer.write(output)
            page_pdf_bytes = output.getvalue()
            
            print(f"✅ Extracted page {page_number}/{total_pages} ({len(page_pdf_bytes) / 1024:.1f}KB)")
            return page_pdf_bytes
            
        except Exception as e:
            print(f"❌ Error extracting page {page_number} from PDF: {e}")
            import traceback
            print(traceback.format_exc())
            return None
    
    def extract_pdf_text(self, edition_id: str, page_number: int) -> Optional[dict]:
        """
        Extract text from a specific page in the Kuwait Alyom gazette
        
        Uses Mistral OCR (primary) and Claude (fallback) for text extraction.
        Tries screenshot first, then PDF-based OCR.
        
        Args:
            edition_id: Gazette edition ID
            page_number: Page number in the edition
            
        Returns:
            Dict with {'text': str, 'ministry': str, ...} if successful, None otherwise
        """
        try:
            print(f"📄 Extracting text from page: Edition {edition_id}, Page {page_number}")
            
            # Method 1: Try Browserless screenshot (PRIMARY - fastest)
            screenshot_bytes = self._screenshot_page_with_browserless(edition_id, page_number)
            if screenshot_bytes:
                print(f"🖼️  Using screenshot-based extraction...")
                result = self._extract_text_from_image(screenshot_bytes)
                if result and result.get('text') and len(result['text']) > 20:
                    print(f"✅ Extracted {len(result['text'])} characters from screenshot")
                    return result
                else:
                    print(f"⚠️  Screenshot extraction returned minimal text (< 20 chars), trying PDF OCR...")
            
            # Method 2: PDF-based Mistral OCR (if screenshot failed)
            print(f"📄 Trying PDF-based OCR...")
            magazine_pdf = self._download_magazine_pdf(edition_id)
            if not magazine_pdf:
                return None
            
            page_pdf = self._extract_page_from_pdf(magazine_pdf, page_number)
            if not page_pdf:
                return None
            
            # Try Mistral PDF OCR first
            try:
                from app.ai.mistral_ocr_service import mistral_ocr_service
            except Exception:
                mistral_ocr_service = None
            
            if mistral_ocr_service:
                print(f"  🚀 Using Mistral PDF OCR...")
                mistral_result = mistral_ocr_service.extract_text_from_pdf(page_pdf)
                if mistral_result and mistral_result.get('text') and len(mistral_result['text']) > 50:
                    print(f"  ✅ Mistral PDF OCR extracted {len(mistral_result['text'])} characters")
                    # Add missing fields for consistency
                    mistral_result.setdefault('ministry', None)
                    mistral_result.setdefault('meeting_date_text', None)
                    mistral_result.setdefault('meeting_location', None)
                    mistral_result.setdefault('tender_number', None)
                    mistral_result.setdefault('deadline', None)
                    mistral_result.setdefault('note', None)
                    return mistral_result
                else:
                    print(f"  ⚠️  Mistral PDF OCR returned insufficient text, trying Claude on PDF image...")
            
            # Method 3: Extract image from PDF and use Claude (last resort)
            print(f"  🖼️  Extracting image from PDF for Claude OCR...")
            image_bytes = self._extract_high_res_image_from_pdf(magazine_pdf, page_number)
            if image_bytes:
                result = self._extract_text_from_image(image_bytes)
                if result and result.get('text') and len(result['text']) > 20:
                    print(f"✅ Extracted {len(result['text'])} characters via Claude OCR")
                    return result
            
            print(f"⚠️  All OCR methods returned minimal or no text")
            return None
                
        except Exception as e:
            print(f"❌ Error extracting text: {e}")
            import traceback
            print(traceback.format_exc())
            return None
    
    def parse_ocr_text(self, ocr_text: str) -> Dict[str, Optional[str]]:
        """
        Parse OCR text to extract tender details
        
        Args:
            ocr_text: Text extracted from PDF via OCR
            
        Returns:
            Dictionary with extracted fields (ministry, description, deadline, etc.)
        """
        try:
            extracted = {
                'ministry': None,
                'description': None,
                'deadline': None,
                'requirements': None
            }
            
            # Extract ministry/organization (common patterns in Arabic)
            ministry_patterns = [
                r'(وزارة\s+[^\n]+)',
                r'(الهيئة\s+العامة\s+[^\n]+)',
                r'(شركة\s+[^\n]+)',
                r'(مؤسسة\s+[^\n]+)',
                r'(ديوان\s+[^\n]+)'
            ]
            
            for pattern in ministry_patterns:
                match = re.search(pattern, ocr_text)
                if match:
                    extracted['ministry'] = match.group(1).strip()
                    break
            
            # Extract RFQ/tender description (usually after RFQ number)
            desc_match = re.search(r'RFQ\s+\d+[:\s]+([^\n]{20,200})', ocr_text)
            if desc_match:
                extracted['description'] = desc_match.group(1).strip()
            else:
                # Try Arabic tender patterns
                desc_match = re.search(r'مناقصة[:\s]+([^\n]{20,200})', ocr_text)
                if desc_match:
                    extracted['description'] = desc_match.group(1).strip()
            
            # Extract deadline (common date patterns)
            deadline_patterns = [
                r'آخر موعد[:\s]+(\d{1,2}/\d{1,2}/\d{4})',
                r'تاريخ الإغلاق[:\s]+(\d{1,2}/\d{1,2}/\d{4})',
                r'deadline[:\s]+(\d{1,2}/\d{1,2}/\d{4})',
            ]
            
            for pattern in deadline_patterns:
                match = re.search(pattern, ocr_text, re.IGNORECASE)
                if match:
                    extracted['deadline'] = match.group(1).strip()
                    break
            
            # If no specific fields found, use first substantial paragraph as description
            if not extracted['description']:
                paragraphs = [p.strip() for p in ocr_text.split('\n') if len(p.strip()) > 50]
                if paragraphs:
                    extracted['description'] = paragraphs[0][:500]  # Limit length
            
            return extracted
            
        except Exception as e:
            logger.error(f"❌ Error parsing OCR text: {e}")
            return {'ministry': None, 'description': None, 'deadline': None, 'requirements': None}
    
    def _parse_meeting_date(self, date_text: str) -> Optional[datetime]:
        """
        Parse meeting date text to datetime
        
        Supports formats like:
        - "1 ديسمبر 2024 الساعة 10:00 صباحاً"
        - "١/١٢/٢٠٢٤"
        - "1/12/2024"
        
        Args:
            date_text: Meeting date as text
            
        Returns:
            Parsed datetime or None
        """
        if not date_text:
            return None
            
        try:
            import dateparser
            
            # Convert Arabic numerals to English
            date_text_en = self._arabic_to_english_numerals(date_text)
            
            # Use dateparser which handles Arabic month names and various formats
            parsed = dateparser.parse(
                date_text_en,
                languages=['ar', 'en'],
                settings={'TIMEZONE': 'Asia/Kuwait', 'RETURN_AS_TIMEZONE_AWARE': True}
            )
            
            if parsed:
                # Convert to UTC
                return parsed.astimezone(timezone.utc)
            
            print(f"  ⚠️ Could not parse meeting date: {date_text}")
            return None
            
        except Exception as e:
            print(f"  ⚠️ Meeting date parsing error: {e}")
            return None
    
    def _arabic_to_english_numerals(self, text: str) -> str:
        """
        Convert Arabic numerals to English numerals
        
        Args:
            text: Text containing Arabic numerals (٠-٩)
            
        Returns:
            Text with English numerals (0-9)
        """
        arabic_to_english = str.maketrans('٠١٢٣٤٥٦٧٨٩', '0123456789')
        return text.translate(arabic_to_english)
    
    def _parse_edition_date(self, tender_data: dict) -> Optional[datetime]:
        """
        Parse edition date with multiple fallback methods
        
        Priority:
        1. EditionDate (.NET JSON format)
        2. HijriDate (convert to Gregorian)
        3. None (don't fake the date!)
        
        Args:
            tender_data: Raw tender data from API
            
        Returns:
            Parsed datetime or None if parsing fails
        """
        # Method 1: .NET JSON format: /Date(1761426000000)/
        date_str = tender_data.get('EditionDate', '')
        date_match = re.search(r'/Date\((\d+)\)/', date_str)
        
        if date_match:
            try:
                timestamp = int(date_match.group(1)) / 1000  # Convert milliseconds to seconds
                published_at = datetime.fromtimestamp(timestamp, tz=timezone.utc)
                print(f"  ✅ Parsed EditionDate: {published_at.strftime('%Y-%m-%d')}")
                return published_at
            except Exception as e:
                print(f"  ⚠️  EditionDate parsing failed: {e}")
        
        # Method 2: Hijri date conversion (fallback)
        hijri_date = tender_data.get('HijriDate', '')
        if hijri_date:
            try:
                from hijri_converter import Hijri
                
                # Convert Arabic numerals to English if present
                hijri_date_en = self._arabic_to_english_numerals(hijri_date)
                
                # Parse format: "15/5/1446" (day/month/year)
                parts = hijri_date_en.replace('/', ' ').split()
                if len(parts) == 3:
                    day, month, year = map(int, parts)
                    
                    # Convert Hijri to Gregorian
                    hijri = Hijri(year, month, day)
                    gregorian = hijri.to_gregorian()
                    
                    # Create timezone-aware datetime
                    published_at = datetime(
                        gregorian.year,
                        gregorian.month,
                        gregorian.day,
                        tzinfo=timezone.utc
                    )
                    
                    print(f"  ✅ Converted HijriDate {hijri_date} → {published_at.strftime('%Y-%m-%d')}")
                    return published_at
                    
            except Exception as e:
                print(f"  ⚠️  HijriDate conversion failed for '{hijri_date}': {e}")
        
        # Method 3: Return None (be honest about missing data)
        print(f"  ⚠️  WARNING: Could not parse date for tender {tender_data.get('AdsTitle', 'Unknown')}")
        print(f"     EditionDate: {date_str}")
        print(f"     HijriDate: {hijri_date}")
        return None
    
    def parse_tender(self, tender_data: Dict, extract_pdf: bool = False, category_id: str = "1") -> Dict:
        """
        Parse tender data from Kuwait Alyom API response
        
        Args:
            tender_data: Raw tender data from API
            extract_pdf: Whether to extract and OCR the PDF (slower but more complete data)
            category_id: Category ID for this tender (1=Tenders, 2=Auctions, 18=Practices)
            
        Returns:
            Standardized tender dictionary
        """
        try:
            # Parse date with multiple fallback methods
            published_at = self._parse_edition_date(tender_data)
            
            # Extract tender info
            title = tender_data.get('AdsTitle', '')
            edition_no = tender_data.get('EditionNo', '')
            hijri_date = tender_data.get('HijriDate', '')
            edition_id = tender_data.get('EditionID_FK')
            page_number = tender_data.get('FromPage')
            tender_id = tender_data.get('ID')
            
            # Generate URL to gazette page (include tender_id to make it unique for multiple tenders on same page)
            url = f"{self.base_url}/flip/index?id={edition_id}&no={page_number}#tender-{tender_id}"
            
            # Initialize with basic info
            ministry = None
            description = f"Gazette Edition {edition_no}, Page {page_number}"
            pdf_text = None
            meeting_date = None
            meeting_location = None
            
            # Debug: Check extraction parameters
            print(f"🔍 DEBUG: extract_pdf={extract_pdf}, edition_id={edition_id}, page_number={page_number}, title={title}")
            
            # Optionally extract PDF and parse with OCR
            if extract_pdf and edition_id and page_number:
                print(f"🔍 Extracting PDF content for {title}...")
                pdf_result = self.extract_pdf_text(edition_id, page_number)
                
                if pdf_result:
                    pdf_text = pdf_result.get('text')
                    vision_ministry = pdf_result.get('ministry')
                    
                    # Claude returns meeting info directly in pdf_result
                    meeting_date_text = pdf_result.get('meeting_date_text')
                    meeting_location = pdf_result.get('meeting_location')
                    
                    # Also check old 'extracted_fields' format for backward compatibility
                    extracted_fields = pdf_result.get('extracted_fields', {})
                    if extracted_fields:
                        meeting_date_text = meeting_date_text or extracted_fields.get('meeting_date_text')
                        meeting_location = meeting_location or extracted_fields.get('meeting_location')
                    
                    # Use Vision/Claude-extracted ministry if available
                    if vision_ministry:
                        ministry = vision_ministry
                        print(f"✅ Extracted details - Ministry: {ministry} (from Claude/Vision)")
                    else:
                        # Fallback to regex parsing if Vision didn't find ministry
                        ocr_data = self.parse_ocr_text(pdf_text)
                        ministry = ocr_data.get('ministry')
                        print(f"✅ Extracted details - Ministry: {ministry} (from regex)")
                    
                    # Extract description from text
                    ocr_data = self.parse_ocr_text(pdf_text)
                    if ocr_data.get('description'):
                        description = ocr_data.get('description')
                    
                    # Extract meeting information if available
                    meeting_date = None
                    if meeting_date_text:
                        meeting_date = self._parse_meeting_date(meeting_date_text)
                        if meeting_date:
                            print(f"✅ Extracted meeting date: {meeting_date.strftime('%Y-%m-%d %H:%M')}")
                    
                    if meeting_location:
                        print(f"✅ Extracted meeting location: {meeting_location}")
            
            # Generate content hash for deduplication
            content = f"KA-{tender_id}|{title}|{edition_no}"
            content_hash = hashlib.md5(content.encode()).hexdigest()
            
            # Map Kuwait Alyom category to our system category
            # This is set by scrape_all() based on which category is being scraped
            category_map = {
                "1": "tenders",      # المناقصات
                "2": "auctions",     # المزايدات  
                "18": "practices"    # الممارسات
            }
            
            return {
                "title": f"{title} - Edition {edition_no}",
                "tender_number": title,  # RFQ number or tender ID
                "url": url,
                "published_at": published_at,
                "ministry": ministry,
                "category": "tenders",  # Default, will be set properly in scrape_all
                "description": description,
                "language": "ar",  # Gazette is in Arabic
                "hash": content_hash,
                "source": "Kuwait Al-Yawm",
                "edition_no": edition_no,
                "edition_id": edition_id,
                "page_number": page_number,
                "hijri_date": hijri_date,
                "gazette_id": tender_id,
                "pdf_text": pdf_text,  # Full OCR text for AI processing
                "kuwait_category_id": category_id,  # Store original category for reference
                "meeting_date": meeting_date,  # Pre-tender meeting date
                "meeting_location": meeting_location,  # Pre-tender meeting location
            }
            
        except Exception as e:
            logger.error(f"❌ Error parsing tender: {e}")
            return None
    
    def scrape_all(
        self,
        category_id: str = "1",
        days_back: int = 90,
        limit: int = 100,
        extract_pdfs: bool = True
    ) -> List[Dict]:
        """
        Scrape all tenders from Kuwait Alyom
        
        Args:
            category_id: Category to scrape (1=Tenders, 2=Auctions, 18=Practices)
            days_back: How many days back to scrape
            limit: Maximum number of tenders
            extract_pdfs: Whether to extract and OCR PDFs (slower but more complete)
            
        Returns:
            List of parsed tender dictionaries
        """
        logger.info(f"🚀 Starting Kuwait Al-Yawm scraper...")
        logger.info(f"   Category: {category_id}, Days back: {days_back}, Limit: {limit}")
        logger.info(f"   PDF Extraction: {'Enabled (with Google Doc AI OCR)' if extract_pdfs else 'Disabled (metadata only)'}")
        
        # Calculate date range
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days_back)
        
        # Format dates for API 
        # NOTE: Kuwait Alyom API doesn't accept date filters properly
        # Send empty strings like the browser does, then filter results after
        start_date_str = ""
        end_date_str = ""
        
        # Fetch ALL tenders with pagination (no limit!)
        print(f"📊 Fetching all tenders from category {category_id}...")
        logger.info(f"📊 Fetching all tenders with pagination...")
        
        all_raw_tenders = []
        page_size = 100  # Fetch 100 at a time
        start_offset = 0
        total_available = None
        
        while True:
            # Fetch this page
            page_tenders, total = self.fetch_tenders(
                category_id=category_id,
                start_date=start_date_str,
                end_date=end_date_str,
                limit=page_size,
                start_offset=start_offset
            )
            
            if total_available is None:
                total_available = total
                print(f"📊 Total tenders available in category: {total_available}")
                logger.info(f"📊 Total tenders available: {total_available}")
            
            if not page_tenders:
                print(f"✅ Reached end of results (fetched {len(all_raw_tenders)} total)")
                break
            
            all_raw_tenders.extend(page_tenders)
            print(f"📄 Fetched page {start_offset // page_size + 1}: {len(page_tenders)} tenders (total so far: {len(all_raw_tenders)}/{total_available})")
            
            # Check if we've fetched everything
            if len(all_raw_tenders) >= total_available:
                print(f"✅ Fetched all {len(all_raw_tenders)} tenders!")
                break
            
            # Check if we hit the overall limit
            if len(all_raw_tenders) >= limit:
                print(f"⚠️  Reached limit of {limit} tenders (total available: {total_available})")
                break
            
            # Move to next page
            start_offset += page_size
        
        raw_tenders = all_raw_tenders[:limit]  # Apply limit
        
        if len(all_raw_tenders) > limit:
            print(f"⚠️  WARNING: Limiting to {limit} tenders out of {len(all_raw_tenders)} fetched")
            logger.warning(f"⚠️  Limiting to {limit} tenders out of {len(all_raw_tenders)} available")
        
        # Category mapping
        category_map = {
            "1": "tenders",      # المناقصات
            "2": "auctions",     # المزايدات  
            "18": "practices"    # الممارسات
        }
        
        # Parse tenders
        parsed_tenders = []
        for i, raw_tender in enumerate(raw_tenders, 1):
            logger.info(f"📄 Processing tender {i}/{len(raw_tenders)}: {raw_tender.get('AdsTitle')}")
            parsed = self.parse_tender(raw_tender, extract_pdf=extract_pdfs, category_id=category_id)
            if parsed:
                # Set the proper category based on category_id
                parsed['category'] = category_map.get(category_id, "tenders")
                parsed_tenders.append(parsed)
        
        logger.info(f"✅ Scraped {len(parsed_tenders)} tenders from Kuwait Al-Yawm")
        
        return parsed_tenders
