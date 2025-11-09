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

logger = logging.getLogger(__name__)


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
        limit: int = 100
    ) -> List[Dict]:
        """
        Fetch tender list from Kuwait Alyom API
        
        Args:
            category_id: Category ID (1=Tenders, 2=Auctions, 18=Practices)
            start_date: Start date filter (YYYY/MM/DD)
            end_date: End date filter (YYYY/MM/DD)
            limit: Maximum number of tenders to fetch
            
        Returns:
            List of tender dictionaries
        """
        # Always try to login first to ensure fresh session
        print(f"🔄 Ensuring authentication for category {category_id}...")  # Using print()
        logger.info("🔄 Ensuring authentication...")
        if not self.login():
            print("❌ Cannot fetch tenders - login failed")  # Using print()
            logger.error("❌ Cannot fetch tenders - login failed")
            return []
        
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
                return []
            
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
                'start': '0',
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
                return []
            
            data = response.json()
            tenders = data.get('data', [])
            total = data.get('recordsTotal', 0)
            
            logger.info(f"✅ Found {len(tenders)} tenders (Total available: {total})")
            
            return tenders
            
        except Exception as e:
            logger.error(f"❌ Error fetching tenders: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return []
    
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
            # Extract only valid base64 characters until we hit the end of the first base64 string
            # Kuwait uses URL-safe base64 (- instead of +, _ instead of /)
            # The HTML has TWO base64 strings concatenated (PDF data, then next attribute)
            # We stop at the first '=' padding character (marks end of PDF data)
            raw_data = parts[1]
            base64_chars = set('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/-_')
            base64_data = []
            found_padding = False
            stop_reason = "unknown"
            
            for i, char in enumerate(raw_data):
                # Once we hit '=', we're in the padding zone
                if char == '=':
                    if not found_padding:
                        found_padding = True
                        base64_data.append(char)
                        print(f"🔍 Found first '=' at position {i}")
                    else:
                        # Additional '=' padding
                        base64_data.append(char)
                elif found_padding:
                    # After padding, if we hit a non-'=' base64 char, that's the NEXT attribute
                    # Stop here!
                    if char in base64_chars:
                        stop_reason = f"hit base64 char '{char}' after padding (next attribute)"
                        print(f"🛑 Stopped at position {i}: {stop_reason}")
                        break
                    elif char not in (' ', '\t', '\n', '\r'):
                        # Hit invalid char after padding
                        stop_reason = f"hit invalid char '{char}' after padding"
                        print(f"🛑 Stopped at position {i}: {stop_reason}")
                        break
                elif char in base64_chars:
                    base64_data.append(char)
                elif char in (' ', '\t', '\n', '\r'):
                    # Skip whitespace
                    continue
                else:
                    # Hit invalid char before any padding
                    stop_reason = f"hit invalid char '{char}'"
                    print(f"🛑 Stopped at position {i}: {stop_reason}")
                    break
            
            base64_data = ''.join(base64_data)
            
            print(f"📊 EXTRACTION SUMMARY:")
            print(f"   - Total length: {len(base64_data)} chars")
            print(f"   - Stop reason: {stop_reason}")
            print(f"   - Has padding: {found_padding}")
            print(f"   - First 50 chars: {base64_data[:50]}")
            print(f"   - Last 50 chars: {base64_data[-50:]}")
            
            if len(base64_data) < 100:
                print(f"⚠️  Extracted base64 too short: {len(base64_data)} chars")
                return None
                
            # Remove any whitespace
            base64_data = re.sub(r'\s+', '', base64_data)
            print(f"✅ Found base64 PDF data ({len(base64_data)} characters, ~{len(base64_data) * 0.75 / 1024 / 1024:.1f}MB)")
            
            # Decode using URL-safe base64 decoder (handles - and _ automatically, adds padding)
            import base64
            try:
                print(f"🔓 Attempting urlsafe_b64decode...")
                pdf_bytes = base64.urlsafe_b64decode(base64_data)
                print(f"✅ Decoded successfully!")
                print(f"   - Decoded size: {len(pdf_bytes) / 1024 / 1024:.1f}MB")
                print(f"   - First 20 bytes: {pdf_bytes[:20]}")
                print(f"   - Starts with %PDF: {pdf_bytes.startswith(b'%PDF')}")
            except Exception as e:
                print(f"❌ urlsafe_b64decode failed: {e}")
                print(f"   - Data length % 4: {len(base64_data) % 4}")
                print(f"   - Trying manual padding...")
                # Add padding if needed
                padding_needed = len(base64_data) % 4
                if padding_needed:
                    base64_data += '=' * (4 - padding_needed)
                    print(f"🔧 Added {4 - padding_needed} padding characters")
                try:
                    pdf_bytes = base64.urlsafe_b64decode(base64_data)
                    print(f"✅ Decoded with manual padding!")
                except Exception as e2:
                    print(f"❌ Still failed after padding: {e2}")
                    raise
            
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
    
    def _extract_page_from_pdf(self, pdf_bytes: bytes, page_number: int) -> Optional[bytes]:
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
    
    def extract_pdf_text(self, edition_id: str, page_number: int) -> Optional[str]:
        """
        Extract text from a specific page in the Kuwait Alyom gazette
        
        Downloads the full magazine PDF once per edition (cached), extracts the
        specific page, and sends it to Google Doc AI for OCR.
        
        Args:
            edition_id: Gazette edition ID
            page_number: Page number in the edition
            
        Returns:
            Extracted text if successful, None otherwise
        """
        try:
            print(f"📄 Extracting text from PDF: Edition {edition_id}, Page {page_number}")
            
            # Step 1: Download full magazine PDF (or get from cache)
            magazine_pdf = self._download_magazine_pdf(edition_id)
            if not magazine_pdf:
                return None
            
            # Step 2: Extract the specific page as a separate PDF
            page_pdf = self._extract_page_from_pdf(magazine_pdf, page_number)
            if not page_pdf:
                return None
            
            # Step 3: Use PDF extractor (with Google Doc AI OCR) to extract text from this single page
            text = self.pdf_extractor.extract_text_from_bytes(page_pdf)
            
            if text and len(text) > 50:  # Ensure we got meaningful content
                print(f"✅ Extracted {len(text)} characters from page {page_number}")
                return text
            else:
                print(f"⚠️  PDF extraction returned minimal text")
                return None
                
        except Exception as e:
            print(f"❌ Error extracting PDF text: {e}")
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
            # Parse date from .NET JSON format: /Date(1761426000000)/
            date_str = tender_data.get('EditionDate', '')
            date_match = re.search(r'/Date\((\d+)\)/', date_str)
            
            if date_match:
                timestamp = int(date_match.group(1)) / 1000  # Convert to seconds
                published_at = datetime.fromtimestamp(timestamp, tz=timezone.utc)
            else:
                published_at = datetime.now(timezone.utc)
            
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
            
            # Debug: Check extraction parameters
            print(f"🔍 DEBUG: extract_pdf={extract_pdf}, edition_id={edition_id}, page_number={page_number}, title={title}")
            
            # Optionally extract PDF and parse with OCR
            if extract_pdf and edition_id and page_number:
                print(f"🔍 Extracting PDF content for {title}...")
                pdf_text = self.extract_pdf_text(edition_id, page_number)
                
                if pdf_text:
                    # Parse OCR text to extract details
                    ocr_data = self.parse_ocr_text(pdf_text)
                    ministry = ocr_data.get('ministry')
                    if ocr_data.get('description'):
                        description = ocr_data.get('description')
                    
                    print(f"✅ Extracted details - Ministry: {ministry}")
            
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
        
        # Fetch tenders
        raw_tenders = self.fetch_tenders(
            category_id=category_id,
            start_date=start_date_str,
            end_date=end_date_str,
            limit=limit
        )
        
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
