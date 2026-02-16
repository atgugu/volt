"""
Selection Parser Utility

A shared utility for parsing user selection inputs across the application.
Supports numeric, ordinal, written numbers, roman numerals, and special patterns.
"""

import re
import logging
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)


class SelectionParser:
    """
    Enhanced selection parser with support for various natural language patterns.

    Supports:
    - Pure numbers: "1", "2", "3" (1-based input, returns 0-based)
    - Ordinals: "first", "second", "third", "1st", "2nd", "3rd"
    - Written numbers: "one", "two", "three"
    - Roman numerals: "i", "ii", "iii", "iv", "v"
    - Special patterns: "last one", "option 1", "choice 2"
    """

    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self._compile_patterns()

    def _compile_patterns(self):
        """Pre-compile all regex patterns for performance."""
        # Pure number pattern (1-10, avoiding negative numbers)
        self.number_pattern = re.compile(r"\b(\d+)\b")

        # Option/choice patterns
        self.option_pattern = re.compile(r"\b(?:option|choice)\s*(\d+)\b")

        # Ordinal patterns with numeric suffixes ONLY (removed ambiguous word versions)
        self.ordinal_patterns = [
            ("1st", 0),
            ("2nd", 1),
            ("3rd", 2),
            ("4th", 3),
            ("5th", 4),
            ("6th", 5),
            ("7th", 6),
            ("8th", 7),
            ("9th", 8),
            ("10th", 9),
        ]

        # Special patterns (keep these as they're explicit)
        self.last_pattern = re.compile(r"\b(?:last|final)(?:\s+one)?\b")

        # Strict Yes/No confirmation patterns (removed ambiguous variations)
        self.yes_pattern = re.compile(r"\byes\b")
        self.no_pattern = re.compile(r"\b(?:no|nope)\b")

        # Compile ordinal pattern regexes (only numeric versions now)
        self.ordinal_regexes = [
            (re.compile(r"\b" + pattern + r"\b"), index)
            for pattern, index in self.ordinal_patterns
        ]

        # Single-word patterns for unambiguous cases
        self.single_word_numbers = {
            "one": 0,
            "two": 1,
            "three": 2,
            "four": 3,
            "five": 4,
            "six": 5,
            "seven": 6,
            "eight": 7,
            "nine": 8,
            "ten": 9,
        }

        # Single-word confirmation patterns (for yes/approval)
        self.single_word_confirmations = [
            "sure",
            "okay",
            "ok",
            "yep",
            "yeah",
            "alright",
        ]

    def extract_selection_index_with_confidence(
        self, message: str, options_count: Optional[int] = None
    ) -> tuple[Optional[int], float]:
        """
        Extract numeric/ordinal selection index from user message with confidence score.

        Args:
            message: User message to parse
            options_count: Number of available options (for "last one" support)

        Returns:
            Tuple of (zero-based index or None, confidence score 0.0-1.0)
        """
        message_lower = message.lower().strip()

        if self.verbose:
            logger.info(
                f"Parsing selection from: '{message}' with {options_count} options"
            )

        # Handle "last one" pattern first (requires options_count)
        if options_count and options_count > 0:
            if self.last_pattern.search(message_lower):
                if self.verbose:
                    logger.info(
                        f"Found 'last one' pattern, returning index {options_count - 1}"
                    )
                return options_count - 1, 1.0  # High confidence for explicit "last" pattern

        # Handle single-word patterns first - these are 100% unambiguous
        words = message_lower.split()
        if len(words) == 1:
            single_word = words[0]

            # Check single-word numbers
            if single_word in self.single_word_numbers:
                index = self.single_word_numbers[single_word]
                validated_index = self._validate_index_bounds(index, options_count, self.verbose)
                if validated_index is not None:
                    if self.verbose:
                        logger.info(f"Found single-word number '{single_word}' -> index {validated_index}")
                    return validated_index, 1.0  # Maximum confidence for single-word numbers

            # Check single-word confirmations (for approval/yes responses)
            if single_word in self.single_word_confirmations:
                if self.verbose:
                    logger.info(f"Found single-word confirmation '{single_word}' -> approval")
                return 0, 1.0  # Single-word confirmations = first option (approval)

        # Handle strict yes/no confirmation patterns for binary choices
        if self.yes_pattern.search(message_lower):
            if self.verbose:
                logger.info("Found 'yes' confirmation pattern, returning index 0")
            # Only high confidence for standalone or very short messages
            word_count = len(message_lower.split())
            if word_count <= 2:
                return 0, 1.0  # Yes = first option (index 0), high confidence
            else:
                # Longer messages with "yes" - delegate to LLM
                return None, 0.0

        if self.no_pattern.search(message_lower):
            if self.verbose:
                logger.info("Found 'no' confirmation pattern, returning index 1")
            # Only return index 1 if there are at least 2 options
            if options_count is None or options_count >= 2:
                word_count = len(message_lower.split())
                if word_count <= 2:
                    return 1, 1.0  # No = second option (index 1), high confidence
                else:
                    # Longer messages with "no" - delegate to LLM
                    return None, 0.0
            else:
                # If only 1 option, "no" doesn't make sense as a selection
                if self.verbose:
                    logger.info(
                        "'No' pattern found but only 1 option available, rejecting"
                    )
                return None, 0.0

        # Check for multiple numbers first (to reject ambiguous cases like "1 2")
        all_numbers = self.number_pattern.findall(message_lower)
        if len(all_numbers) > 1:
            # Multiple numbers found - ambiguous, reject
            if self.verbose:
                logger.info(
                    f"Multiple numbers found: {all_numbers}, rejecting as ambiguous"
                )
            return None, 0.0

        # Handle pure numbers: "1", "2", "3" (but not negative numbers) - strict mode
        number_match = self.number_pattern.search(message_lower)
        if number_match:
            try:
                # Check that this isn't part of a negative number
                start_pos = number_match.start()
                if start_pos > 0 and message_lower[start_pos - 1] == "-":
                    # This is a negative number, skip it
                    pass
                else:
                    num = int(number_match.group(1))
                    if 1 <= num <= 10:  # Reasonable range
                        index = num - 1  # Convert to 0-based index
                        validated_index = self._validate_index_bounds(
                            index, options_count, self.verbose
                        )
                        if validated_index is not None:
                            word_count = len(message_lower.split())
                            if word_count <= 2:
                                # High confidence only for standalone or very short
                                if self.verbose:
                                    logger.info(
                                        f"Found standalone number pattern: {num} -> index {validated_index}"
                                    )
                                return validated_index, 1.0
                            else:
                                # Longer messages with numbers - delegate to LLM
                                if self.verbose:
                                    logger.info(
                                        f"Found number in longer message, delegating to LLM"
                                    )
                                return None, 0.0
            except ValueError:
                pass

        # Check for negation patterns first (these should be rejected)
        negation_patterns = [r"\bnot\s+", r"\bmaybe\s+", r"\bperhaps\s+", r"\bmight\s+"]
        for pattern in negation_patterns:
            if re.search(pattern, message_lower):
                if self.verbose:
                    logger.info(f"Found negation pattern '{pattern}', rejecting")
                return None, 0.0

        # Handle numeric ordinals (1st, 2nd, 3rd, etc.) - these are explicit and unambiguous
        for pattern_regex, index in self.ordinal_regexes:
            if pattern_regex.search(message_lower):
                validated_index = self._validate_index_bounds(
                    index, options_count, self.verbose
                )
                if validated_index is not None:
                    if self.verbose:
                        logger.info(f"Found numeric ordinal pattern -> index {validated_index}")
                    # High confidence for explicit numeric ordinals
                    return validated_index, 1.0

        # Handle "option X", "choice X" patterns - these are very explicit
        option_match = self.option_pattern.search(message_lower)
        if option_match:
            try:
                num = int(option_match.group(1))
                if 1 <= num <= 10:
                    index = num - 1  # Convert to 0-based index
                    validated_index = self._validate_index_bounds(
                        index, options_count, self.verbose
                    )
                    if validated_index is not None:
                        if self.verbose:
                            logger.info(
                                f"Found explicit option/choice pattern: {num} -> index {validated_index}"
                            )
                        # Maximum confidence for explicit option/choice patterns
                        return validated_index, 1.0
            except ValueError:
                pass

        if self.verbose:
            logger.info("No high-confidence selection pattern found, delegating to LLM")
        return None, 0.0

    def extract_selection_index(
        self, message: str, options_count: Optional[int] = None
    ) -> Optional[int]:
        """
        Extract numeric/ordinal selection index from user message.
        Maintained for backward compatibility.

        Args:
            message: User message to parse
            options_count: Number of available options (for "last one" support)

        Returns:
            Zero-based index (0, 1, 2...) or None if no valid selection found
        """
        index, confidence = self.extract_selection_index_with_confidence(message, options_count)
        return index

    def _validate_index_bounds(
        self, index: int, options_count: Optional[int], verbose: bool = False
    ) -> Optional[int]:
        """
        Validate that the extracted index is within valid bounds.

        Args:
            index: The extracted index (0-based)
            options_count: Number of available options
            verbose: Enable verbose logging

        Returns:
            The validated index or None if out of bounds
        """
        if options_count is not None and index >= options_count:
            if verbose:
                logger.info(
                    f"Index {index} is out of bounds for {options_count} options, rejecting"
                )
            return None
        return index

    def is_selection_message(self, message: str) -> bool:
        """
        Check if a message contains selection-like patterns.

        Args:
            message: User message to check

        Returns:
            True if message appears to be a selection attempt
        """
        message_lower = message.lower().strip()

        # Check for any of our selection patterns (with dummy options_count for last pattern)
        if self.extract_selection_index(message, options_count=10) is not None:
            return True

        # Check for special patterns that might not match extract_selection_index
        if self.last_pattern.search(message_lower):
            return True

        # Check for other selection-like words
        selection_words = [
            "select",
            "choose",
            "pick",
            "want",
            "take",
            "go with",
            "prefer",
            "like",
            "option",
            "choice",
            "number",
        ]

        return any(word in message_lower for word in selection_words)

    def get_supported_patterns(self) -> Dict[str, List[str]]:
        """
        Get documentation of supported selection patterns.
        Note: This parser now uses strict patterns only. Ambiguous responses
        are delegated to the LLM confirmation classifier.

        Returns:
            Dictionary mapping pattern types to example patterns
        """
        return {
            "numbers": ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10"],
            "numeric_ordinals": [
                "1st",
                "2nd",
                "3rd",
                "4th",
                "5th",
                "6th",
                "7th",
                "8th",
                "9th",
                "10th",
            ],
            "single_word_numbers": ["one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"],
            "explicit_options": ["option 1", "option 2", "choice 1", "choice 2"],
            "strict_confirmations": ["yes", "no", "nope"],
            "single_word_confirmations": ["sure", "okay", "ok", "yep", "yeah", "alright"],
            "special": ["last one", "final one", "last", "final"],
            "note": "Single-word patterns have 100% confidence. Multi-word patterns require ≤2 words for high confidence. Longer messages are delegated to LLM."
        }


# Global instance for easy reuse
_default_parser = None


def get_selection_parser(verbose: bool = False) -> SelectionParser:
    """
    Get a shared SelectionParser instance.

    Args:
        verbose: Enable verbose logging

    Returns:
        SelectionParser instance
    """
    global _default_parser
    if _default_parser is None or _default_parser.verbose != verbose:
        _default_parser = SelectionParser(verbose=verbose)
    return _default_parser


def extract_selection_index_with_confidence(
    message: str, options_count: Optional[int] = None, verbose: bool = False
) -> tuple[Optional[int], float]:
    """
    Convenience function to extract selection index with confidence score from a message.

    Args:
        message: User message to parse
        options_count: Number of available options (for "last one" support)
        verbose: Enable verbose logging

    Returns:
        Tuple of (zero-based index or None, confidence score 0.0-1.0)
    """
    parser = get_selection_parser(verbose=verbose)
    return parser.extract_selection_index_with_confidence(message, options_count)


def extract_selection_index(
    message: str, options_count: Optional[int] = None, verbose: bool = False
) -> Optional[int]:
    """
    Convenience function to extract selection index from a message.
    Maintained for backward compatibility.

    Args:
        message: User message to parse
        options_count: Number of available options (for "last one" support)
        verbose: Enable verbose logging

    Returns:
        Zero-based index or None if no valid selection found
    """
    parser = get_selection_parser(verbose=verbose)
    return parser.extract_selection_index(message, options_count)
