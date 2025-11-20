"""
Date Validation and Conversion Utilities for STC Tender Platform
Provides extreme accuracy for date extraction and validation
"""
from datetime import datetime, timedelta
from typing import Optional, Dict, Tuple
import re


class DateValidator:
    """Comprehensive date validation for tender deadlines"""
    
    @staticmethod
    def validate_deadline(
        deadline: Optional[datetime],
        published_date: Optional[datetime],
        tolerance_days: int = 0
    ) -> Dict:
        """
        Validate deadline against publication date
        
        Args:
            deadline: Extracted deadline
            published_date: Tender publication date
            tolerance_days: Allow deadlines this many days before publication (default: 0)
            
        Returns:
            Dict with validation result and suggestions
        """
        if not deadline or not published_date:
            return {
                "valid": None,
                "issue": None,
                "confidence": 1.0,
                "suggestion": None
            }
        
        # Ensure timezone-aware
        from datetime import timezone
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=timezone.utc)
        if published_date.tzinfo is None:
            published_date = published_date.replace(tzinfo=timezone.utc)
        
        days_diff = (deadline - published_date).days
        
        # Check if deadline is before publication
        if days_diff < -tolerance_days:
            issue_type = "deadline_before_publication"
            abs_diff = abs(days_diff)
            
            # Detect common OCR errors
            suggestions = []
            
            # Check for YEAR OCR errors (e.g., 2013 instead of 2025, 2024 instead of 2025)
            year_diff = published_date.year - deadline.year
            if year_diff > 0 and year_diff <= 12:  # Years are reasonably close
                # Try correcting the year to match publication year
                try:
                    corrected_deadline = deadline.replace(year=published_date.year)
                    corrected_diff = (corrected_deadline - published_date).days
                    
                    # If corrected date makes sense (0-90 days after publication)
                    if 0 <= corrected_diff <= 90:
                        confidence = 0.95 if year_diff >= 2 else 0.85  # Higher confidence for bigger year gaps
                        suggestions.append({
                            "type": "year_ocr_error",
                            "original": deadline.strftime("%Y-%m-%d"),
                            "suggested": corrected_deadline.strftime("%Y-%m-%d"),
                            "reason": f"OCR read year as '{deadline.year}' instead of '{published_date.year}'",
                            "confidence": confidence
                        })
                except ValueError:
                    pass  # Invalid date (e.g., Feb 29 in non-leap year)
            
            # Check for single digit confusion (6 vs 16 vs 26) - only if year is same
            if deadline.year == published_date.year:
                if abs_diff == 10:
                    # Could be 6 vs 16
                    corrected_deadline = deadline + timedelta(days=10)
                    suggestions.append({
                        "type": "digit_confusion",
                        "original": deadline.strftime("%Y-%m-%d"),
                        "suggested": corrected_deadline.strftime("%Y-%m-%d"),
                        "reason": "Possible OCR confusion: '6' vs '16' in date",
                        "confidence": 0.8
                    })
                elif abs_diff == 20:
                    # Could be 6 vs 26
                    corrected_deadline = deadline + timedelta(days=20)
                    suggestions.append({
                        "type": "digit_confusion",
                        "original": deadline.strftime("%Y-%m-%d"),
                        "suggested": corrected_deadline.strftime("%Y-%m-%d"),
                        "reason": "Possible OCR confusion: '6' vs '26' in date",
                        "confidence": 0.7
                    })
            
            # Check for expired tender (deadline > 30 days in past) - if no year error detected
            if abs_diff > 30 and not any(s.get('type') == 'year_ocr_error' for s in suggestions):
                suggestions.append({
                    "type": "expired_tender",
                    "reason": f"Deadline is {abs_diff} days before publication - likely expired/reposted tender",
                    "confidence": 0.9
                })
            
            return {
                "valid": False,
                "issue": issue_type,
                "days_diff": days_diff,
                "message": f"Deadline ({deadline.date()}) is {abs_diff} days BEFORE publication ({published_date.date()})",
                "suggestions": suggestions,
                "confidence": 0.3  # Low confidence in this date
            }
        
        # Check if deadline is too far in future (> 2 years)
        if days_diff > 730:
            return {
                "valid": False,
                "issue": "deadline_too_far_future",
                "days_diff": days_diff,
                "message": f"Deadline is {days_diff} days ({days_diff // 365} years) in future - likely incorrect",
                "confidence": 0.2
            }
        
        # Check if deadline is very soon (< 3 days)
        if 0 < days_diff < 3:
            return {
                "valid": True,
                "issue": "urgent_deadline",
                "days_diff": days_diff,
                "message": f"Urgent: Deadline is only {days_diff} days away",
                "confidence": 0.9
            }
        
        # Valid deadline
        return {
            "valid": True,
            "issue": None,
            "days_diff": days_diff,
            "message": f"Valid deadline: {days_diff} days after publication",
            "confidence": 1.0
        }
    
    @staticmethod
    def parse_arabic_date(date_text: str) -> Optional[datetime]:
        """
        Parse Arabic date text to datetime
        Handles various Arabic date formats
        
        Args:
            date_text: Arabic date string
            
        Returns:
            datetime object or None
        """
        if not date_text:
            return None
        
        # Normalize Arabic numbers to English
        arabic_to_english = {
            '٠': '0', '١': '1', '٢': '2', '٣': '3', '٤': '4',
            '٥': '5', '٦': '6', '٧': '7', '٨': '8', '٩': '9'
        }
        
        normalized = date_text
        for ar, en in arabic_to_english.items():
            normalized = normalized.replace(ar, en)
        
        # Try various date patterns
        patterns = [
            r'(\d{1,2})[/-](\d{1,2})[/-](\d{4})',  # DD/MM/YYYY or DD-MM-YYYY
            r'(\d{4})[/-](\d{1,2})[/-](\d{1,2})',  # YYYY-MM-DD
            r'(\d{1,2})\s+(\w+)\s+(\d{4})',         # DD Month YYYY
        ]
        
        arabic_months = {
            'يناير': 1, 'فبراير': 2, 'مارس': 3, 'أبريل': 4,
            'مايو': 5, 'يونيو': 6, 'يوليو': 7, 'أغسطس': 8,
            'سبتمبر': 9, 'أكتوبر': 10, 'نوفمبر': 11, 'ديسمبر': 12
        }
        
        for pattern in patterns:
            match = re.search(pattern, normalized)
            if match:
                try:
                    groups = match.groups()
                    if len(groups) == 3:
                        # Check if middle group is month name
                        if groups[1] in arabic_months:
                            day = int(groups[0])
                            month = arabic_months[groups[1]]
                            year = int(groups[2])
                        elif '/' in date_text or '-' in date_text:
                            # DD/MM/YYYY format
                            day, month, year = int(groups[0]), int(groups[1]), int(groups[2])
                            # Handle if year is first
                            if year < 100:  # YYYY/MM/DD
                                year, month, day = int(groups[0]), int(groups[1]), int(groups[2])
                        
                        return datetime(year, month, day)
                except (ValueError, KeyError):
                    continue
        
        return None
    
    @staticmethod
    def convert_hijri_to_gregorian(hijri_date_str: str) -> Optional[datetime]:
        """
        Convert Hijri date to Gregorian
        Requires hijri-converter package
        
        Args:
            hijri_date_str: Hijri date string (e.g., "25 جمادى الأول 1447")
            
        Returns:
            Gregorian datetime or None
        """
        try:
            from hijri_converter import Hijri, Gregorian
            
            # This is a placeholder - actual implementation would parse Hijri date
            # and convert using hijri-converter library
            # For now, return None to avoid errors if package not installed
            return None
        except ImportError:
            print("⚠️  hijri-converter not installed, skipping Hijri date conversion")
            return None


# Singleton instance
date_validator = DateValidator()
