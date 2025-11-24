"""
STC Tender Relevance Scoring Service
Uses Claude AI to analyze tender relevance to STC's business areas
"""
from typing import Dict, List, Optional
import json
from app.ai.claude_service import claude_service


class RelevanceScorer:
    """Score tender relevance to STC's business using AI"""
    
    # STC's core business areas (matching Email 1 requirements)
    STC_SECTORS = {
        "Telecom infrastructure": ["fiber", "ftth", "5g", "4g", "lte", "network", "telecommunications", "tower", "antenna", "base station", "optical", "cable"],
        "Data center & cloud": ["data center", "cloud", "server", "storage", "virtualization", "hosting", "colocation", "iaas", "paas", "saas", "datacenter"],
        "Contact center / call center": ["contact center", "call center", "customer service", "ivr", "crm", "helpdesk", "support center", "voice", "telephony"],
        "Networking & security": ["network", "router", "switch", "firewall", "vpn", "security", "cybersecurity", "wan", "lan", "mpls", "sd-wan", "cisco", "juniper"],
        "Smart city / IoT": ["smart city", "iot", "internet of things", "sensors", "smart", "automation", "surveillance", "traffic management", "monitoring"]
    }
    
    # STC Business Units
    STC_TEAMS = [
        "STC Enterprise – Government",
        "STC Enterprise – Corporate", 
        "STC Consumer",
        "STC Solutions (ICT)",
        "STC Channels & Sales"
    ]
    
    def __init__(self):
        self.claude = claude_service
    
    def score_tender_relevance(self, tender_title: str, tender_body: str, ministry: Optional[str] = None) -> Dict:
        """
        Analyze tender and return relevance score + insights
        
        Returns:
        {
            "relevance_score": "very_high" | "high" | "medium" | "low",
            "confidence": 0.95,
            "keywords": ["Fiber", "MPLS", "Managed Service"],
            "sectors": ["telecom_infrastructure", "networking_security"],
            "recommended_team": "STC Enterprise – Government",
            "reasoning": "This tender involves fiber optic network infrastructure..."
        }
        """
        try:
            # Prepare prompt for Claude
            prompt = f"""Analyze this government tender from Kuwait for STC (Kuwait Telecommunications Company) relevance.

**Tender Details:**
Title: {tender_title}
Ministry/Entity: {ministry or "Unknown"}
Description: {tender_body[:2000]}  # First 2000 chars

**STC's Business Areas (use these exact names):**
1. Telecom infrastructure
2. Data center & cloud
3. Contact center / call center
4. Networking & security
5. Smart city / IoT

**STC Business Units:**
- STC Enterprise – Government (public sector)
- STC Enterprise – Corporate (private companies)
- STC Consumer (B2C)
- STC Solutions (ICT projects)
- STC Channels & Sales

**Task:** Analyze and provide:
1. Relevance score (very_high, high, medium, low)
2. Confidence (0-1)
3. Key technical keywords found (max 5)
4. Matching STC sectors
5. Recommended team to handle this
6. Brief reasoning (1-2 sentences)

Return JSON only:
{{
  "relevance_score": "very_high",
  "confidence": 0.95,
  "keywords": ["Fiber Optic", "MPLS", "Managed Service"],
  "sectors": ["telecom_infrastructure", "networking_security"],
  "recommended_team": "STC Enterprise – Government",
  "reasoning": "Tender requires fiber optic network infrastructure with MPLS and managed services - core STC Enterprise capabilities for government sector."
}}"""

            # Call Claude with STRUCTURED OUTPUTS (guaranteed valid JSON)
            response = self.claude.client.messages.create(
                model=self.claude.model,
                max_tokens=1024,
                timeout=30.0,  # Explicit timeout
                messages=[{"role": "user", "content": prompt}],
                tools=[{
                    "name": "score_tender_relevance",
                    "description": "Analyze tender relevance to STC's business",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "relevance_score": {
                                "type": "string",
                                "enum": ["very_high", "high", "medium", "low"],
                                "description": "Overall relevance level"
                            },
                            "confidence": {
                                "type": "number",
                                "minimum": 0,
                                "maximum": 1,
                                "description": "Confidence score 0-1"
                            },
                            "keywords": {
                                "type": "array",
                                "items": {"type": "string"},
                                "maxItems": 5,
                                "description": "Key technical terms found"
                            },
                            "sectors": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Matching STC business sectors"
                            },
                            "recommended_team": {
                                "type": "string",
                                "description": "Which STC team should handle this"
                            },
                            "reasoning": {
                                "type": "string",
                                "description": "Brief explanation (1-2 sentences)"
                            }
                        },
                        "required": ["relevance_score", "confidence", "keywords", "reasoning"]
                    }
                }],
                tool_choice={"type": "tool", "name": "score_tender_relevance"}
            )
            
            # Extract structured result (guaranteed valid!)
            tool_use = next((block for block in response.content if block.type == "tool_use"), None)
            if tool_use:
                result = tool_use.input  # Already a dict, no JSON parsing needed!
            else:
                # Fallback to text parsing (shouldn't happen with tool_choice)
                response_text = response.content[0].text.strip()
                if "```json" in response_text:
                    json_start = response_text.find("```json") + 7
                    json_end = response_text.find("```", json_start)
                    response_text = response_text[json_start:json_end].strip()
                result = json.loads(response_text)
            
            print(f"✅ Relevance scored: {result.get('relevance_score')} ({result.get('confidence', 0):.0%} confidence)")
            return result
            
        except Exception as e:
            print(f"❌ Relevance scoring error: {e}")
            # Fallback to keyword matching
            return self._fallback_scoring(tender_title, tender_body, ministry)
    
    def _fallback_scoring(self, title: str, body: str, ministry: Optional[str]) -> Dict:
        """Simple keyword-based fallback if AI fails"""
        text = f"{title} {body}".lower()
        
        # Count keyword matches
        matches = []
        matched_sectors = []
        
        for sector, keywords in self.STC_SECTORS.items():
            for keyword in keywords:
                if keyword.lower() in text:
                    matches.append(keyword.title())
                    if sector not in matched_sectors:
                        matched_sectors.append(sector)
        
        # Score based on matches
        match_count = len(set(matches))
        if match_count >= 3:
            relevance = "very_high"
            confidence = 0.85
        elif match_count >= 2:
            relevance = "high"
            confidence = 0.70
        elif match_count >= 1:
            relevance = "medium"
            confidence = 0.55
        else:
            relevance = "low"
            confidence = 0.40
        
        # Determine team
        is_government = ministry and any(x in ministry.lower() for x in ["وزارة", "ministry", "هيئة", "authority"])
        team = "STC Enterprise – Government" if is_government else "STC Enterprise – Corporate"
        
        return {
            "relevance_score": relevance,
            "confidence": confidence,
            "keywords": list(set(matches))[:5],
            "sectors": matched_sectors,
            "recommended_team": team,
            "reasoning": f"Found {match_count} relevant keywords in tender description."
        }
    
    def calculate_urgency(self, deadline) -> Dict:
        """Calculate urgency based on deadline"""
        from datetime import datetime, timezone
        
        if not deadline:
            return {"urgency": "unknown", "days_left": None, "label": "No deadline"}
        
        now = datetime.now(timezone.utc)
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=timezone.utc)
        
        delta = deadline - now
        days_left = delta.days
        
        if days_left < 0:
            urgency = "expired"
            label = "Expired"
        elif days_left <= 3:
            urgency = "critical"
            label = f"{days_left} days left"
        elif days_left <= 7:
            urgency = "high"
            label = f"{days_left} days left"
        elif days_left <= 14:
            urgency = "medium"
            label = f"{days_left} days left"
        else:
            urgency = "low"
            label = f"{days_left} days left"
        
        return {
            "urgency": urgency,
            "days_left": days_left,
            "label": label
        }


# Singleton instance
relevance_scorer = RelevanceScorer()
