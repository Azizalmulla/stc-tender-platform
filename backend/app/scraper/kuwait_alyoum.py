import asyncio
from typing import List, Dict, Optional
from playwright.async_api import async_playwright, Page, Browser
from bs4 import BeautifulSoup
import hashlib
from datetime import datetime
import pytz
from app.core.config import settings


class KuwaitAlyoumScraper:
    """Scraper for Kuwait Alyoum government gazette"""
    
    def __init__(self):
        self.base_url = settings.BASE_URL
        self.categories = settings.TENDER_CATEGORIES
        self.timezone = pytz.timezone(settings.TIMEZONE)
        self.browser: Optional[Browser] = None
        
    async def __aenter__(self):
        """Async context manager entry"""
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=settings.SCRAPER_HEADLESS
        )
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self.browser:
            await self.browser.close()
        await self.playwright.stop()
    
    async def scrape_category(self, category_name: str, category_id: int) -> List[Dict]:
        """
        Scrape a single category page
        
        Args:
            category_name: Category name (e.g., 'tenders', 'auctions')
            category_id: Category ID from Kuwait Alyoum
            
        Returns:
            List of tender dictionaries
        """
        url = f"{self.base_url}/online/AdsCategory/{category_id}"
        
        page = await self.browser.new_page()
        page.set_default_timeout(settings.SCRAPER_TIMEOUT)
        
        try:
            # Navigate and wait for content
            await page.goto(url, wait_until="networkidle")
            await page.wait_for_selector("body", timeout=10000)
            
            # Get page content
            content = await page.content()
            soup = BeautifulSoup(content, 'html.parser')
            
            tenders = []
            
            # Look for tender listings (adapt selectors based on actual HTML)
            # This is a generic parser - will need refinement after inspecting actual page
            tender_items = soup.find_all(['article', 'div'], class_=lambda x: x and ('tender' in x.lower() or 'item' in x.lower() or 'card' in x.lower()))
            
            if not tender_items:
                # Fallback: find all links that might be tenders
                tender_items = soup.find_all('a', href=lambda x: x and '/online/' in x)
            
            for item in tender_items:
                tender_data = await self._parse_tender_item(item, category_name, page)
                if tender_data:
                    tenders.append(tender_data)
            
            return tenders
            
        finally:
            await page.close()
    
    async def _parse_tender_item(self, item, category: str, page: Page) -> Optional[Dict]:
        """
        Parse a single tender item from HTML
        
        Args:
            item: BeautifulSoup element
            category: Category name
            page: Playwright page for additional actions
            
        Returns:
            Tender dictionary or None
        """
        try:
            # Extract URL
            link = item.find('a', href=True)
            if not link:
                return None
                
            url = link['href']
            if not url.startswith('http'):
                url = f"{self.base_url}{url}"
            
            # Extract title
            title_elem = item.find(['h1', 'h2', 'h3', 'h4', 'div'], class_=lambda x: x and 'title' in x.lower()) or link
            title = title_elem.get_text(strip=True) if title_elem else ""
            
            # Extract body/description
            body_elem = item.find(['p', 'div'], class_=lambda x: x and ('desc' in str(x).lower() or 'content' in str(x).lower()))
            body = body_elem.get_text(strip=True) if body_elem else ""
            
            # Extract date if visible
            date_elem = item.find(['time', 'span'], class_=lambda x: x and 'date' in str(x).lower())
            published_at = None
            if date_elem:
                date_text = date_elem.get_text(strip=True)
                published_at = self._parse_date(date_text)
            
            # Generate hash for deduplication
            hash_content = f"{url}{title}{body}".encode('utf-8')
            content_hash = hashlib.sha256(hash_content).hexdigest()
            
            return {
                "url": url,
                "title": title,
                "body": body,
                "category": category,
                "published_at": published_at,
                "hash": content_hash,
                "ministry": None,  # Will be extracted during detailed parsing
                "tender_number": None,
                "deadline": None,
                "document_price_kd": None,
                "lang": self._detect_language(title + " " + body),
                "attachments": None
            }
            
        except Exception as e:
            print(f"Error parsing tender item: {e}")
            return None
    
    async def scrape_tender_details(self, url: str) -> Dict:
        """
        Scrape detailed information from a tender page
        
        Args:
            url: Full URL to tender detail page
            
        Returns:
            Detailed tender dictionary
        """
        page = await self.browser.new_page()
        
        try:
            await page.goto(url, wait_until="networkidle")
            content = await page.content()
            soup = BeautifulSoup(content, 'html.parser')
            
            # Extract main content
            main_content = soup.find(['article', 'main', 'div'], class_=lambda x: x and ('content' in str(x).lower() or 'detail' in str(x).lower()))
            
            if not main_content:
                main_content = soup.find('body')
            
            title = ""
            body = ""
            
            if main_content:
                title_elem = main_content.find(['h1', 'h2'])
                title = title_elem.get_text(strip=True) if title_elem else ""
                body = main_content.get_text(strip=True)
            
            # Look for PDF attachments
            attachments = []
            pdf_links = soup.find_all('a', href=lambda x: x and '.pdf' in x.lower())
            for link in pdf_links:
                attachments.append({
                    "url": link['href'] if link['href'].startswith('http') else f"{self.base_url}{link['href']}",
                    "name": link.get_text(strip=True) or "document.pdf"
                })
            
            # Detect language
            lang = self._detect_language(title + " " + body)
            
            return {
                "title": title,
                "body": body,
                "lang": lang,
                "attachments": attachments if attachments else None
            }
            
        finally:
            await page.close()
    
    async def scrape_all_categories(self) -> List[Dict]:
        """Scrape all configured tender categories"""
        all_tenders = []
        
        for category_name, category_id in self.categories.items():
            print(f"Scraping category: {category_name} (ID: {category_id})")
            tenders = await self.scrape_category(category_name, category_id)
            all_tenders.extend(tenders)
            
            # Be nice to the server
            await asyncio.sleep(2)
        
        return all_tenders
    
    def _detect_language(self, text: str) -> str:
        """Detect if text is primarily Arabic or English"""
        if not text:
            return "unknown"
        
        # Count Arabic characters
        arabic_chars = sum(1 for char in text if '\u0600' <= char <= '\u06FF')
        total_chars = len([c for c in text if c.isalpha()])
        
        if total_chars == 0:
            return "unknown"
        
        arabic_ratio = arabic_chars / total_chars
        
        if arabic_ratio > 0.3:
            return "ar"
        elif arabic_ratio < 0.1:
            return "en"
        else:
            return "ar"  # Default to Arabic for mixed content
    
    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """Parse date string to datetime with Kuwait timezone"""
        # This will need adjustment based on actual date formats
        # Common formats: "02/11/2025", "٢/١١/٢٠٢٥", etc.
        try:
            # Try various date formats
            for fmt in ["%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"]:
                try:
                    dt = datetime.strptime(date_str, fmt)
                    return self.timezone.localize(dt)
                except ValueError:
                    continue
            return None
        except Exception:
            return None


async def scrape_kuwait_alyoum() -> List[Dict]:
    """Main function to scrape Kuwait Alyoum tenders"""
    async with KuwaitAlyoumScraper() as scraper:
        return await scraper.scrape_all_categories()
