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
        self.is_authenticated = False
        
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
            
            # Check if login successful by looking for user info in response
            if 'المستخدم' in login_response.text or 'تسجيل الخروج' in login_response.text:
                logger.info("✅ Successfully logged in to Kuwait Al-Yawm")
                self.is_authenticated = True
                return True
            else:
                logger.error("❌ Login failed - invalid credentials or session issue")
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
        if not self.is_authenticated:
            if not self.login():
                logger.error("❌ Cannot fetch tenders - not authenticated")
                return []
        
        try:
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
            response.raise_for_status()
            
            data = response.json()
            tenders = data.get('data', [])
            total = data.get('recordsTotal', 0)
            
            logger.info(f"✅ Found {len(tenders)} tenders (Total available: {total})")
            
            return tenders
            
        except Exception as e:
            logger.error(f"❌ Error fetching tenders: {e}")
            return []
    
    def download_pdf_page(self, edition_id: int, page_number: int) -> Optional[bytes]:
        """
        Download a specific PDF page from the gazette
        
        Args:
            edition_id: Gazette edition ID
            page_number: Page number in the edition
            
        Returns:
            PDF bytes if successful, None otherwise
        """
        try:
            # Kuwait Alyom uses a flip viewer - we need to get the actual PDF URL
            # This might require additional scraping of the flip viewer page
            logger.info(f"📄 Downloading PDF: Edition {edition_id}, Page {page_number}")
            
            # For now, return None - we'll implement PDF extraction in next step
            # The flip viewer URL is: /flip/index?id={edition_id}&no={page_number}
            # We need to extract the actual PDF URL from this page
            
            return None
            
        except Exception as e:
            logger.error(f"❌ Error downloading PDF: {e}")
            return None
    
    def parse_tender(self, tender_data: Dict) -> Dict:
        """
        Parse tender data from Kuwait Alyom API response
        
        Args:
            tender_data: Raw tender data from API
            
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
            
            # Generate content hash for deduplication
            content = f"KA-{tender_id}|{title}|{edition_no}"
            content_hash = hashlib.md5(content.encode()).hexdigest()
            
            return {
                "title": f"{title} - Edition {edition_no}",
                "tender_number": title,  # RFQ number or tender ID
                "url": url,
                "published_at": published_at,
                "ministry": None,  # Will be extracted from PDF via OCR
                "category": "tenders",  # Kuwait Alyom category
                "description": f"Gazette Edition {edition_no}, Page {page_number}",
                "language": "ar",  # Gazette is in Arabic
                "hash": content_hash,
                "source": "Kuwait Al-Yawm",
                "edition_no": edition_no,
                "edition_id": edition_id,
                "page_number": page_number,
                "hijri_date": hijri_date,
                "gazette_id": tender_id,
                "pdf_url": None,  # Will be populated when we extract PDF
            }
            
        except Exception as e:
            logger.error(f"❌ Error parsing tender: {e}")
            return None
    
    def scrape_all(
        self,
        category_id: str = "1",
        days_back: int = 90,
        limit: int = 100
    ) -> List[Dict]:
        """
        Scrape all tenders from Kuwait Alyom
        
        Args:
            category_id: Category to scrape (1=Tenders, 2=Auctions, 18=Practices)
            days_back: How many days back to scrape
            limit: Maximum number of tenders
            
        Returns:
            List of parsed tender dictionaries
        """
        logger.info(f"🚀 Starting Kuwait Al-Yawm scraper...")
        logger.info(f"   Category: {category_id}, Days back: {days_back}, Limit: {limit}")
        
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
        
        # Parse tenders
        parsed_tenders = []
        for raw_tender in raw_tenders:
            parsed = self.parse_tender(raw_tender)
            if parsed:
                parsed_tenders.append(parsed)
        
        logger.info(f"✅ Scraped {len(parsed_tenders)} tenders from Kuwait Al-Yawm")
        
        return parsed_tenders
