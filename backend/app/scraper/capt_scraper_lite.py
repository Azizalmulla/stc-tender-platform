"""
Lightweight CAPT scraper using HTTP requests instead of Playwright
Much faster and uses less memory - ideal for Render free tier
Uses cloudscraper to bypass Cloudflare protection
"""
import cloudscraper
from bs4 import BeautifulSoup
from typing import List, Dict, Optional
import hashlib
from datetime import datetime
import pytz
from app.core.config import settings


class CAPTScraperLite:
    """Lightweight scraper for CAPT portal using HTTP requests"""
    
    def __init__(self):
        self.base_url = "https://capt.gov.kw"
        self.timezone = pytz.timezone(settings.TIMEZONE)
        
        # CAPT tender categories
        self.categories = {
            "opening": "/en/tenders/opening-tenders/",
            "closing": "/en/tenders/closing-tenders/",
            "pre_tenders": "/en/tenders/pre-tenders/",
            "winning": "/en/tenders/winning-bids/",
        }
        
        # HTTP headers to mimic browser
        self.headers = {
            'User-Agent': settings.SCRAPER_USER_AGENT,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
    
    def scrape_category(self, category_name: str, category_path: str) -> List[Dict]:
        """
        Scrape a single category page from CAPT
        
        Args:
            category_name: Category name (e.g., 'opening', 'closing')
            category_path: URL path for the category
            
        Returns:
            List of tender dictionaries
        """
        url = f"{self.base_url}{category_path}"
        
        try:
            print(f"  📄 Fetching {url}...")
            
            # Create cloudscraper session (bypasses Cloudflare)
            scraper = cloudscraper.create_scraper(
                browser={
                    'browser': 'chrome',
                    'platform': 'windows',
                    'mobile': False
                }
            )
            
            # Make HTTP request with cloudflare bypass
            response = scraper.get(url, timeout=30)
            response.raise_for_status()
            
            print(f"  ✅ Page loaded (status: {response.status_code})")
            
            # Parse HTML
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Find tender boxes
            tender_boxes = soup.find_all('div', class_=['content-box grey', 'content-box green'])
            # Also try without space (class as list)
            if not tender_boxes:
                tender_boxes = soup.find_all('div', class_='content-box')
            
            print(f"  📦 Found {len(tender_boxes)} tender boxes")
            
            tenders = []
            for box in tender_boxes:
                try:
                    tender_data = self._parse_tender_box(box, category_name)
                    if tender_data:
                        tenders.append(tender_data)
                except Exception as e:
                    print(f"  ⚠️  Error parsing tender box: {e}")
                    continue
            
            return tenders
            
        except Exception as e:
            print(f"  ❌ Error scraping category {category_name}: {e}")
            import traceback
            print(f"  Traceback: {traceback.format_exc()}")
            return []
    
    def _parse_tender_box(self, box, category: str) -> Optional[Dict]:
        """Parse a single tender box element"""
        try:
            # Skip search forms and detail boxes
            box_classes = ' '.join(box.get('class', []))
            if 'tender-search' in box_classes or 'tender-info' in box_classes:
                return None
            
            # Get tender number and date from <p class="tenderno">
            tender_no_elem = box.find('p', class_='tenderno')
            if not tender_no_elem:
                return None
            
            # Extract date from span first
            date_span = tender_no_elem.find('span')
            date_str = date_span.get_text().strip() if date_span else None
            
            # Remove span to get just tender number
            if date_span:
                date_span.extract()
            
            # Extract tender number (text after removing span)
            tender_no = tender_no_elem.get_text().strip()
            
            if not tender_no:
                return None
            
            # Get organization name from <p class="orgname">
            org_elem = box.find('p', class_='orgname')
            organization = org_elem.get_text().strip() if org_elem else "Unknown"
            
            # Get tender description (second <p> in tender-detail)
            detail_div = box.find('div', class_='tender-detail')
            if detail_div:
                desc_paragraphs = detail_div.find_all('p')
                description = desc_paragraphs[1].get_text().strip() if len(desc_paragraphs) > 1 else ""
            else:
                description = ""
            
            # Parse published date
            published_at = self._parse_date(date_str) if date_str else datetime.now(self.timezone)
            
            # Generate URL
            url = f"{self.base_url}/en/tenders/{category}/{tender_no}/"
            
            # Generate content hash for deduplication
            content = f"{tender_no}|{organization}|{description}"
            content_hash = hashlib.md5(content.encode()).hexdigest()
            
            # Detect language
            language = self._detect_language(description)
            
            # Try to find PDF link (often in tender boxes or detail pages)
            pdf_url = None
            pdf_link = box.find('a', href=lambda x: x and '.pdf' in x.lower())
            if pdf_link:
                pdf_url = pdf_link.get('href')
                if pdf_url and not pdf_url.startswith('http'):
                    pdf_url = f"{self.base_url}{pdf_url}"
            
            # Extract meeting info for pre-tender meetings
            meeting_date = None
            meeting_location = None
            if category == "pre_tenders":
                # Look for meeting date in description (common patterns)
                # This is basic - will improve when we see actual HTML structure
                desc_lower = description.lower()
                if 'meeting' in desc_lower or 'اجتماع' in description:
                    # Try to extract date/location from description
                    # For now, mark as having meeting but null date/location
                    # Will be populated from PDF extraction
                    pass
            
            return {
                "title": description[:200] if description else f"Tender {tender_no}",
                "tender_number": tender_no,
                "url": url,
                "published_at": published_at,
                "ministry": organization,
                "category": category,
                "description": description,
                "language": language,
                "hash": content_hash,
                "source": "CAPT",
                "pdf_url": pdf_url,
                "meeting_date": meeting_date,
                "meeting_location": meeting_location,
            }
            
        except Exception as e:
            print(f"    ⚠️  Error parsing tender: {e}")
            return None
    
    def _parse_date(self, date_str: str) -> datetime:
        """Parse date string to datetime"""
        try:
            # CAPT format: "Nov. 2, 2025"
            date_obj = datetime.strptime(date_str.strip(), "%b. %d, %Y")
            return self.timezone.localize(date_obj)
        except:
            # Fallback to current time
            return datetime.now(self.timezone)
    
    def _detect_language(self, text: str) -> str:
        """Detect if text is Arabic or English"""
        if not text:
            return "en"
        
        arabic_chars = sum(1 for c in text if '\u0600' <= c <= '\u06FF')
        total_chars = len([c for c in text if c.isalpha()])
        
        if total_chars > 0 and arabic_chars / total_chars > 0.3:
            return "ar"
        return "en"
    
    def scrape_all_categories(self) -> List[Dict]:
        """Scrape all CAPT categories"""
        all_tenders = []
        
        for category_name, category_path in self.categories.items():
            print(f"Scraping CAPT category: {category_name}")
            tenders = self.scrape_category(category_name, category_path)
            all_tenders.extend(tenders)
            print(f"  Found {len(tenders)} tenders")
        
        return all_tenders


def scrape_capt_lite() -> List[Dict]:
    """Main function to scrape CAPT tenders (lightweight version)"""
    scraper = CAPTScraperLite()
    tenders = scraper.scrape_all_categories()
    return tenders
