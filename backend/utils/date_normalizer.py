"""
Date expression normalizer for diary-specific queries.

This module handles complex temporal expressions commonly used in diary contexts,
including relative dates, event-based references, and cultural time concepts.
"""

import re
from datetime import datetime, timedelta, date
from typing import Dict, List, Optional, Tuple
from calendar import monthrange
import logging

logger = logging.getLogger(__name__)


class DateNormalizer:
    """
    Normalizes various date expressions into concrete dates.
    
    Handles:
    - Relative expressions (next day, yesterday, last month)
    - Event-based references (around Halloween, New Year period)
    - Cultural concepts (year-end, beginning of year)
    - Calendar-specific terms (end of month, beginning of week)
    """
    
    def __init__(self, reference_date: Optional[date] = None):
        """
        Initialize the normalizer.
        
        Args:
            reference_date: Base date for relative calculations. Defaults to today.
        """
        self.reference_date = reference_date or date.today()
        
        # Japanese temporal expressions
        self.japanese_expressions = {
            'basic_relative': {
                '次の日': 1, '翌日': 1, '明日': 1,
                'その次の日': 1, 'その翌日': 1,
                '前の日': -1, '昨日': -1,
                'その前の日': -1,
                '次の週': 7, '来週': 7, '翌週': 7,
                '前の週': -7, '先週': -7,
                '次の月': 30, '来月': 30, '翌月': 30,
                '前の月': -30, '先月': -30,
                '次の年': 365, '来年': 365, '翌年': 365,
                '前の年': -365, '去年': -365, '昨年': -365
            },
            'month_specific': {
                '先月末': -1, '今月末': 0, '来月末': 1,
                '月初': 0, '月末': 0, '月中旬': 15
            },
            'event_based': {
                'ハロウィンの頃': (10, 31), 'ハロウィン': (10, 31),
                'クリスマス頃': (12, 25), 'クリスマス': (12, 25),
                'お正月': (1, 1), '正月': (1, 1),
                '年末': (12, 31), '年越し': (12, 31)
            },
            'cultural': {
                '年明け': (1, 1), '新年': (1, 1),
                '年度始め': (4, 1), '年度末': (3, 31),
                '学期始め': self._get_semester_start,
                '学期末': self._get_semester_end
            }
        }
        
        # English temporal expressions
        self.english_expressions = {
            'basic_relative': {
                'next day': 1, 'tomorrow': 1, 'following day': 1,
                'previous day': -1, 'yesterday': -1,
                'next week': 7, 'following week': 7,
                'last week': -7, 'previous week': -7,
                'next month': 30, 'following month': 30,
                'last month': -30, 'previous month': -30,
                'next year': 365, 'following year': 365,
                'last year': -365, 'previous year': -365
            },
            'month_specific': {
                'end of last month': -1, 'end of this month': 0, 'end of next month': 1,
                'beginning of month': 0, 'middle of month': 15
            },
            'event_based': {
                'around halloween': (10, 31), 'halloween': (10, 31),
                'around christmas': (12, 25), 'christmas': (12, 25),
                'new year': (1, 1), 'new years': (1, 1),
                'year end': (12, 31), 'year end': (12, 31)
            },
            'cultural': {
                'new year period': (1, 1), 'beginning of year': (1, 1),
                'fiscal year start': (4, 1), 'fiscal year end': (3, 31)
            }
        }
    
    def normalize_query(self, query: str, context_history: Optional[List[str]] = None) -> str:
        """
        Normalize temporal expressions in a query.
        
        Args:
            query: Original query with temporal expressions
            context_history: Previous queries for context understanding
            
        Returns:
            Query with temporal expressions normalized to concrete dates
        """
        # Detect language
        is_japanese = self._detect_japanese(query)
        expressions = self.japanese_expressions if is_japanese else self.english_expressions
        
        # Extract reference date from context if available
        if context_history:
            self.reference_date = self._extract_reference_date_from_context(context_history)
        
        normalized_query = query
        
        # Process different types of expressions
        normalized_query = self._normalize_basic_relative(normalized_query, expressions['basic_relative'])
        normalized_query = self._normalize_month_specific(normalized_query, expressions['month_specific'])
        normalized_query = self._normalize_event_based(normalized_query, expressions['event_based'])
        normalized_query = self._normalize_cultural(normalized_query, expressions['cultural'])
        
        logger.debug(f"Normalized query: '{query}' -> '{normalized_query}'")
        return normalized_query
    
    def _detect_japanese(self, text: str) -> bool:
        """Detect if text is primarily Japanese."""
        japanese_chars = re.findall(r'[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF]', text)
        return len(japanese_chars) > len(text) * 0.3
    
    def _normalize_basic_relative(self, query: str, expressions: Dict[str, int]) -> str:
        """Normalize basic relative expressions."""
        normalized = query
        
        # Sort expressions by length (longer first) to avoid partial matches
        sorted_expressions = sorted(expressions.items(), key=lambda x: len(x[0]), reverse=True)
        
        for expr, days in sorted_expressions:
            if expr in normalized:
                target_date = self.reference_date + timedelta(days=days)
                date_str = target_date.strftime('%Y-%m-%d')
                normalized = normalized.replace(expr, date_str)
                logger.info(f"Replaced '{expr}' with '{date_str}'")
        
        return normalized
    
    def _normalize_month_specific(self, query: str, expressions: Dict[str, int]) -> str:
        """Normalize month-specific expressions."""
        normalized = query
        
        for expr, month_offset in expressions.items():
            if expr in normalized:
                target_date = self._get_month_date(self.reference_date, month_offset)
                date_str = target_date.strftime('%Y-%m-%d')
                normalized = normalized.replace(expr, date_str)
                logger.debug(f"Replaced '{expr}' with '{date_str}'")
        
        return normalized
    
    def _normalize_event_based(self, query: str, expressions: Dict[str, Tuple]) -> str:
        """Normalize event-based expressions."""
        normalized = query
        
        for expr, (month, day) in expressions.items():
            if expr in normalized:
                # Use current year or most recent occurrence
                current_year = self.reference_date.year
                target_date = date(current_year, month, day)
                
                # If the date hasn't occurred yet this year, use last year
                if target_date > self.reference_date:
                    target_date = date(current_year - 1, month, day)
                
                date_str = target_date.strftime('%Y-%m-%d')
                normalized = normalized.replace(expr, date_str)
                logger.debug(f"Replaced '{expr}' with '{date_str}'")
        
        return normalized
    
    def _normalize_cultural(self, query: str, expressions: Dict[str, Tuple]) -> str:
        """Normalize cultural time concepts."""
        normalized = query
        
        for expr, date_info in expressions.items():
            if expr in normalized:
                if callable(date_info):
                    # Dynamic calculation (e.g., semester dates)
                    target_date = date_info(self.reference_date.year)
                else:
                    # Fixed date
                    month, day = date_info
                    target_date = date(self.reference_date.year, month, day)
                
                date_str = target_date.strftime('%Y-%m-%d')
                normalized = normalized.replace(expr, date_str)
                logger.debug(f"Replaced '{expr}' with '{date_str}'")
        
        return normalized
    
    def _get_month_date(self, reference: date, month_offset: int) -> date:
        """Get specific date within a month."""
        if month_offset == 0:
            # Current month
            if '末' in str(month_offset) or 'end' in str(month_offset):
                # End of month
                last_day = monthrange(reference.year, reference.month)[1]
                return date(reference.year, reference.month, last_day)
            elif '初' in str(month_offset) or 'beginning' in str(month_offset):
                # Beginning of month
                return date(reference.year, reference.month, 1)
            else:
                return reference
        else:
            # Offset month
            target_month = reference.month + month_offset
            target_year = reference.year
            
            # Handle year overflow
            while target_month > 12:
                target_month -= 12
                target_year += 1
            while target_month < 1:
                target_month += 12
                target_year -= 1
            
            if '末' in str(month_offset) or 'end' in str(month_offset):
                last_day = monthrange(target_year, target_month)[1]
                return date(target_year, target_month, last_day)
            else:
                return date(target_year, target_month, 1)
    
    def _get_semester_start(self, year: int) -> date:
        """Get semester start date (Japanese academic calendar)."""
        return date(year, 4, 1)
    
    def _get_semester_end(self, year: int) -> date:
        """Get semester end date (Japanese academic calendar)."""
        return date(year + 1, 3, 31)
    
    def _extract_reference_date_from_context(self, history: List[str]) -> date:
        """Extract reference date from conversation history."""
        # Look for date patterns in recent messages
        date_pattern = re.compile(r'(\d{4})-(\d{2})-(\d{2})')
        month_day_pattern = re.compile(r'(\d{1,2})/(\d{1,2})')
        
        for message in reversed(history[-5:]):  # Check last 5 messages
            # Try YYYY-MM-DD pattern first
            matches = date_pattern.findall(message)
            if matches:
                year, month, day = map(int, matches[0])
                return date(year, month, day)
            
            # Try M/D pattern
            matches = month_day_pattern.findall(message)
            if matches:
                month, day = map(int, matches[0])
                # Assume current year for M/D pattern
                return date(self.reference_date.year, month, day)
        
        return self.reference_date


# Example usage and testing
if __name__ == "__main__":
    normalizer = DateNormalizer(date(2026, 4, 10))
    
    test_queries = [
        "次の日は何をした？",
        "先月末の出来事を教えて",
        "ハロウィンの頃の予定は？",
        "昨年の今日は何をしてた？",
        "年明けの目標は？",
        "What did I do tomorrow?",
        "What happened around Halloween?",
        "What were my new year resolutions?"
    ]
    
    for query in test_queries:
        normalized = normalizer.normalize_query(query)
        print(f"Original: {query}")
        print(f"Normalized: {normalized}")
        print("-" * 50)
