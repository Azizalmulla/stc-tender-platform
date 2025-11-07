import asyncio
from typing import List, Dict, Optional
from playwright.async_api import async_playwright, Page, Browser
import hashlib
from datetime import datetime
import pytz
from app.core.config import settings


class CAPTScraper:
    """Scraper for CAPT (Central Agency for Public Tenders) portal"""
    
    def __init__(self):
        self.base_url = "https://capt.gov.kw"
        self.timezone = pytz.timezone(settings.TIMEZONE)
        self.browser: Optional[Browser] = None
        
        # CAPT tender categories
        self.categories = {
            "opening": "/en/tenders/opening-tenders/",
            "closing": "/en/tenders/closing-tenders/",
            "pre_tenders": "/en/tenders/pre-tenders/",
            "winning": "/en/tenders/winning-bids/",
        }
        
    async def __aenter__(self):
        """Async context manager entry"""
        try:
            print("🌐 Starting Playwright...")
            self.playwright = await async_playwright().start()
            print("🚀 Launching browser...")
            self.browser = await self.playwright.chromium.launch(
                headless=settings.SCRAPER_HEADLESS,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--no-sandbox',
                    '--disable-dev-shm-usage',  # Fix for Docker/Render
                ]
            )
            print("✅ Browser launched successfully")
            return self
        except Exception as e:
            print(f"❌ BROWSER LAUNCH FAILED: {e}")
            print(f"Error type: {type(e).__name__}")
            import traceback
            print(f"Traceback: {traceback.format_exc()}")
            raise
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self.browser:
            await self.browser.close()
        await self.playwright.stop()
    
    async def scrape_category(self, category_name: str, category_path: str) -> List[Dict]:
        """
        Scrape a single category page from CAPT
        
        Args:
            category_name: Category name (e.g., 'opening', 'closing')
            category_path: URL path for the category
            
        Returns:
            List of tender dictionaries
        """
        url = f"{self.base_url}{category_path}"
        
        # Create context with realistic settings
        context = await self.browser.new_context(
            user_agent=settings.SCRAPER_USER_AGENT,
            viewport={'width': 1920, 'height': 1080},
            locale='en-US',
            timezone_id='Asia/Kuwait',
        )
        
        # Mask webdriver properties
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        """)
        
        page = await context.new_page()
        page.set_default_timeout(settings.SCRAPER_TIMEOUT)
        
        try:
            print(f"  📄 Loading {url}...")
            await page.goto(url, wait_until='networkidle', timeout=60000)
            print(f"  ⏱️  Waiting for content...")
            await page.wait_for_timeout(5000)  # Wait longer for Cloudflare
            
            tenders = []
            
            # Find tender boxes (.content-box.grey or .content-box.green)
            print(f"  🔍 Searching for tender boxes...")
            tender_boxes = await page.query_selector_all('.content-box.grey, .content-box.green')
            print(f"  📦 Found {len(tender_boxes)} tender boxes")
            
            for box in tender_boxes:
                try:
                    tender_data = await self._parse_tender_box(box, category_name)
                    if tender_data:
                        tenders.append(tender_data)
                except Exception as e:
                    print(f"  ⚠️  Error parsing tender box: {e}")
                    continue
            
            return tenders
            
        except Exception as e:
            print(f"  ❌ Error scraping category {category_name}: {e}")
            print(f"  Error type: {type(e).__name__}")
            import traceback
            print(f"  Traceback: {traceback.format_exc()}")
            return []
        finally:
            await page.close()
            await context.close()
    
    async def _parse_tender_box(self, box, category: str) -> Optional[Dict]:
        """Parse a single tender box element"""
        try:
            # Get tender number and date
            tender_no_elem = await box.query_selector('.tenderno')
            if not tender_no_elem:
                return None
                
            tender_info = await tender_no_elem.inner_text()
            lines = [line.strip() for line in tender_info.strip().split('\n') if line.strip()]
            
            tender_no = lines[0] if lines else None
            date_str = lines[1] if len(lines) > 1 else None
            
            if not tender_no:
                return None
            
            # Get organization name
            org_elem = await box.query_selector('.orgname')
            organization = await org_elem.inner_text() if org_elem else "Unknown"
            organization = organization.strip()
            
            # Get description (Arabic text)
            detail_elem = await box.query_selector('.tender-detail p:not(.orgname)')
            description = await detail_elem.inner_text() if detail_elem else ""
            description = description.strip()
            
            # Parse date
            published_at = self._parse_date(date_str) if date_str else datetime.now(self.timezone)
            
            # Generate URL (construct detail page URL)
            url = f"{self.base_url}/en/tenders/{category}/{tender_no}/"
            
            # Generate hash for deduplication
            hash_str = f"{tender_no}{organization}{description}"
            content_hash = hashlib.md5(hash_str.encode()).hexdigest()
            
            # Detect language
            language = self._detect_language(description)
            
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
            }
            
        except Exception as e:
            print(f"Error parsing tender box: {e}")
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
    
    async def scrape_all_categories(self) -> List[Dict]:
        """Scrape all CAPT categories"""
        all_tenders = []
        
        for category_name, category_path in self.categories.items():
            print(f"Scraping CAPT category: {category_name}")
            tenders = await self.scrape_category(category_name, category_path)
            all_tenders.extend(tenders)
            print(f"  Found {len(tenders)} tenders")
            
            # Be respectful - wait between requests
            await asyncio.sleep(2)
        
        return all_tenders


async def scrape_capt() -> List[Dict]:
    """Main function to scrape CAPT tenders"""
    async with CAPTScraper() as scraper:
        tenders = await scraper.scrape_all_categories()
    return tenders
