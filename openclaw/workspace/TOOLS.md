# Tools & Skills

## kuwait-tenders skill
Location: skills/kuwait-tenders/SKILL.md
Purpose: Query live Kuwait government tender database

API Base URL: http://76.13.63.68:8000
Environment variable: TENDER_API_URL=http://76.13.63.68:8000

### Quick Reference
- List tenders: GET /api/tenders?limit=5
- Search: GET /api/search/keyword?q=QUERY
- By sector: GET /api/tenders?sector=telecom
- By urgency: GET /api/tenders?urgency=3_days
- By ministry: GET /api/tenders?ministry=NAME
- Details: GET /api/tenders/ID
- Notifications: GET /api/notifications/
- Analytics: GET /api/analytics/summary
- Urgency stats: GET /api/analytics/urgency
- AI chat: POST /api/chat/ask
