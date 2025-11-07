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
        
    def login(self) -> bool:
        """
        Authenticate with Kuwait Alyom
        
        Returns:
            bool: True if login successful, False otherwise
        """
        try:
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
            
            # DEBUG: Log EVERYTHING about the login response
            logger.info(f"📍 Login Response URL: {login_response.url}")
            logger.info(f"📊 Login Response Status: {login_response.status_code}")
            logger.info(f"🍪 Session Cookies: {dict(self.session.cookies)}")
            
            # Show first 1000 chars of response for debugging
            response_preview = login_response.text[:1000] if len(login_response.text) > 1000 else login_response.text
            logger.info(f"📄 Login Response Preview:\n{response_preview}")
            
            # Check our search strings
            has_user = 'المستخدم' in login_response.text
            has_logout = 'تسجيل الخروج' in login_response.text
            logger.info(f"🔍 Contains 'المستخدم': {has_user}")
            logger.info(f"🔍 Contains 'تسجيل الخروج': {has_logout}")
            
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
        logger.info("🔄 Ensuring authentication...")
        if not self.login():
            logger.error("❌ Cannot fetch tenders - login failed")
            return []
        
        try:
            # IMPORTANT: Visit the category page first to establish session state
            # Kuwait Alyom's API requires this step before calling AdsCategoryJson
            logger.info(f"📄 Visiting category page to establish session...")
            category_page_url = f"{self.base_url}/online/AdsCategory/{category_id}"
            page_response = self.session.get(category_page_url)
            
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
            
            # DataTables API format
            payload = {
                'draw': '1',
                'start': '0',
                'length': str(limit),
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
            logger.error(f"Traceback: {traceback.format_exc()}")
            return []
    
    def extract_pdf_text(self, edition_id: int, page_number: int) -> Optional[str]:
        """
        Extract text from a specific PDF page from the gazette using OCR
        
        Args:
            edition_id: Gazette edition ID
            page_number: Page number in the edition
            
        Returns:
            Extracted text if successful, None otherwise
        """
        try:
            logger.info(f"📄 Extracting text from PDF: Edition {edition_id}, Page {page_number}")
            
            # Kuwait Alyom uses a flip viewer - try to access the PDF directly
            # The flip viewer loads PDFs from a predictable URL pattern
            # We'll try common patterns used by flip book viewers
            
            possible_pdf_urls = [
                f"{self.base_url}/flip/pdf/{edition_id}/{page_number}.pdf",
                f"{self.base_url}/flip/pages/{edition_id}/page{page_number}.pdf",
                f"{self.base_url}/EditionsPDF/{edition_id}/page_{page_number}.pdf",
            ]
            
            pdf_bytes = None
            
            # Try each possible URL
            for pdf_url in possible_pdf_urls:
                try:
                    response = self.session.get(pdf_url, timeout=30)
                    if response.status_code == 200 and response.content[:4] == b'%PDF':
                        pdf_bytes = response.content
                        logger.info(f"✅ Found PDF at: {pdf_url}")
                        break
                except:
                    continue
            
            # If direct PDF access fails, try to scrape the flip viewer page
            if not pdf_bytes:
                flip_url = f"{self.base_url}/flip/index?id={edition_id}&no={page_number}"
                response = self.session.get(flip_url)
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Look for PDF URL in JavaScript or iframe
                scripts = soup.find_all('script')
                for script in scripts:
                    if script.string and 'pdf' in script.string.lower():
                        # Try to extract PDF URL from JavaScript
                        pdf_match = re.search(r'["\']([^"\']*\.pdf[^"\']*)["\']', script.string)
                        if pdf_match:
                            pdf_url = pdf_match.group(1)
                            if not pdf_url.startswith('http'):
                                pdf_url = f"{self.base_url}{pdf_url}"
                            
                            response = self.session.get(pdf_url)
                            if response.status_code == 200:
                                pdf_bytes = response.content
                                logger.info(f"✅ Extracted PDF from flip viewer")
                                break
            
            if not pdf_bytes:
                logger.warning(f"⚠️  Could not download PDF for Edition {edition_id}, Page {page_number}")
                return None
            
            # Use PDF extractor (with Google Doc AI OCR) to extract text
            text = self.pdf_extractor.extract_text_from_bytes(pdf_bytes)
            
            if text and len(text) > 50:  # Ensure we got meaningful content
                logger.info(f"✅ Extracted {len(text)} characters from PDF")
                return text
            else:
                logger.warning(f"⚠️  PDF extraction returned minimal text")
                return None
                
        except Exception as e:
            logger.error(f"❌ Error extracting PDF text: {e}")
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
    
    def parse_tender(self, tender_data: Dict, extract_pdf: bool = False) -> Dict:
        """
        Parse tender data from Kuwait Alyom API response
        
        Args:
            tender_data: Raw tender data from API
            extract_pdf: Whether to extract and OCR the PDF (slower but more complete data)
            
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
            
            # Generate URL to gazette page
            url = f"{self.base_url}/flip/index?id={edition_id}&no={page_number}"
            
            # Initialize with basic info
            ministry = None
            description = f"Gazette Edition {edition_no}, Page {page_number}"
            pdf_text = None
            
            # Optionally extract PDF and parse with OCR
            if extract_pdf and edition_id and page_number:
                logger.info(f"🔍 Extracting PDF content for {title}...")
                pdf_text = self.extract_pdf_text(edition_id, page_number)
                
                if pdf_text:
                    # Parse OCR text to extract details
                    ocr_data = self.parse_ocr_text(pdf_text)
                    ministry = ocr_data.get('ministry')
                    if ocr_data.get('description'):
                        description = ocr_data.get('description')
                    
                    logger.info(f"✅ Extracted details - Ministry: {ministry}")
            
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
        
        start_date_str = start_date.strftime("%Y/%m/%d")
        end_date_str = end_date.strftime("%Y/%m/%d")
        
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
            parsed = self.parse_tender(raw_tender, extract_pdf=extract_pdfs)
            if parsed:
                # Set the proper category based on category_id
                parsed['category'] = category_map.get(category_id, "tenders")
                parsed_tenders.append(parsed)
        
        logger.info(f"✅ Scraped {len(parsed_tenders)} tenders from Kuwait Al-Yawm")
        
        return parsed_tenders
