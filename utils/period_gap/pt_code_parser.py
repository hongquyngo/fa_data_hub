# utils/period_gap/pt_code_parser.py
"""
PT Code Parser for Period GAP Analysis
Handles parsing and validation of bulk PT code imports
"""

import re
from typing import List, Dict, Any, Set
import logging

logger = logging.getLogger(__name__)


class PTCodeParser:
    """Parser and validator for bulk PT code input"""
    
    @staticmethod
    def parse_pt_codes(input_text: str) -> List[str]:
        """
        Parse PT codes from text with multiple delimiter support
        Supports: comma, semicolon, space, newline, tab, pipe
        
        Args:
            input_text: Raw text input containing PT codes
            
        Returns:
            List of cleaned, unique PT codes
        """
        if not input_text or not input_text.strip():
            return []
        
        normalized = input_text.upper().strip()
        
        # Replace various delimiters with comma
        for delimiter in [';', '\n', '\r', '\t', '|']:
            normalized = normalized.replace(delimiter, ',')
        
        # Split by comma and/or spaces
        codes = re.split(r'[,\s]+', normalized)
        
        # Clean and filter
        cleaned_codes = []
        for code in codes:
            code = code.strip()
            if code and len(code) > 0:
                code = re.sub(r'["\']', '', code)
                if code:
                    cleaned_codes.append(code)
        
        # Remove duplicates while preserving order
        seen: Set[str] = set()
        unique_codes = []
        for code in cleaned_codes:
            if code not in seen:
                seen.add(code)
                unique_codes.append(code)
        
        return unique_codes
    
    @staticmethod
    def validate_codes_against_display_list(
        parsed_codes: List[str], 
        product_options: List[str]
    ) -> Dict[str, Any]:
        """
        Validate parsed codes against product display list
        Product options are in format: "PT_CODE | Product Name | Package (Brand)"
        
        Args:
            parsed_codes: List of PT codes to validate
            product_options: List of formatted product display strings
            
        Returns:
            Dict with matched options, matched codes, unmatched codes, and match rate
        """
        if not product_options:
            return {
                'matched_options': [],
                'matched_codes': [],
                'unmatched_codes': parsed_codes,
                'match_rate': 0
            }
        
        # Create mapping of PT codes to full display strings
        pt_code_map = {}
        for option in product_options:
            # Extract PT code (first part before |)
            parts = option.split('|')
            if parts:
                pt_code = parts[0].strip().upper()
                pt_code_map[pt_code] = option
        
        matched_options = []
        matched_codes = []
        unmatched_codes = []
        
        for code in parsed_codes:
            code_upper = code.upper().strip()
            if code_upper in pt_code_map:
                matched_options.append(pt_code_map[code_upper])
                matched_codes.append(code_upper)
            else:
                unmatched_codes.append(code)
        
        match_rate = (len(matched_codes) / len(parsed_codes) * 100) if parsed_codes else 0
        
        return {
            'matched_options': matched_options,
            'matched_codes': matched_codes,
            'unmatched_codes': unmatched_codes,
            'match_rate': match_rate
        }
    
    @staticmethod
    def get_pt_code_from_display(display_string: str) -> str:
        """
        Extract PT code from formatted display string
        Format: "PT_CODE | Product Name | Package (Brand)"
        
        Args:
            display_string: Formatted product display string
            
        Returns:
            PT code extracted from display string
        """
        parts = display_string.split('|')
        if parts:
            return parts[0].strip()
        return display_string