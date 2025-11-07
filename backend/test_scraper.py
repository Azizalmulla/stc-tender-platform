from app.scraper.capt_scraper_lite import scrape_capt_lite
import json

print("Testing lightweight scraper...\n")
tenders = scrape_capt_lite()

print(f'\n🎉 SUCCESS! Found {len(tenders)} tenders\n')

if tenders:
    print('First tender:')
    print(json.dumps(tenders[0], indent=2, default=str))
    print(f'\nAll tender numbers: {[t["tender_number"] for t in tenders]}')
