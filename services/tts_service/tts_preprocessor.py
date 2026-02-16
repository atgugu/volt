"""
TTS Preprocessor Module

Preprocesses text before sending to TTS to improve speech quality and remove
formatting artifacts that would be spoken literally.
"""

import re
import logging

logger = logging.getLogger(__name__)


class TTSPreprocessor:
    """
    Preprocesses text for TTS to improve speech naturalness and remove formatting.
    """

    def __init__(self):
        # Compile regex patterns for performance
        self.bold_pattern = re.compile(r'\*\*([^*]+)\*\*')
        self.emphasis_pattern = re.compile(r'\*([^*]+)\*')
        self.time_pattern = re.compile(r'\b(\d{1,2}):00\s*(AM|PM|am|pm)\b')
        # Pattern to match phone numbers after "Phone:" or similar identifiers
        self.phone_pattern = re.compile(r'\b(Phone|Tel|Telephone|Cell|Mobile|Fax):\s*(\d{5,})\b', re.IGNORECASE)
        # Pattern to match general phone number formats (with or without identifiers)
        # Matches: (555) 556-6777, 555-556-6777, 555.556.6777, 5555566777, etc.
        # Uses lookbehind to ensure we don't match numbers in the middle of words
        self.general_phone_pattern = re.compile(
            r'(?:^|(?<=\s))'  # Start of string or preceded by whitespace
            r'(?:\+?1[-.\s]?)?'  # Optional country code
            r'(?:\()?'  # Optional opening parenthesis
            r'(\d{3})'  # Area code
            r'(?:\))?'  # Optional closing parenthesis
            r'[-.\s]?'  # Optional separator
            r'(\d{3})'  # First 3 digits
            r'[-.\s]?'  # Optional separator
            r'(\d{4})'  # Last 4 digits
            r'(?=\s|$|[.,!?])'  # Followed by whitespace, end of string, or punctuation
        )
        # Pattern to match "e.g." abbreviation
        self.eg_pattern = re.compile(r'\be\.g\.\s*', re.IGNORECASE)

        # Emoji pattern - matches most common emoji ranges in Unicode
        # This covers emoticons, symbols, pictographs, transport symbols, flags, etc.
        self.emoji_pattern = re.compile(
            "["
            "\U0001F600-\U0001F64F"  # Emoticons
            "\U0001F300-\U0001F5FF"  # Symbols & pictographs
            "\U0001F680-\U0001F6FF"  # Transport & map symbols
            "\U0001F700-\U0001F77F"  # Alchemical symbols
            "\U0001F780-\U0001F7FF"  # Geometric shapes
            "\U0001F800-\U0001F8FF"  # Supplemental arrows
            "\U0001F900-\U0001F9FF"  # Supplemental symbols
            "\U0001FA00-\U0001FA6F"  # Chess symbols
            "\U0001FA70-\U0001FAFF"  # Symbols and pictographs extended
            "\U00002702-\U000027B0"  # Dingbats
            "\U000024C2-\U0001F251"  # Enclosed characters
            "\U0001F1E0-\U0001F1FF"  # Flags (iOS)
            "\u2600-\u26FF"          # Miscellaneous symbols
            "\u2700-\u27BF"          # Dingbats
            "\uFE00-\uFE0F"          # Variation selectors
            "\u200d"                 # Zero-width joiner
            "\u2640-\u2642"          # Gender symbols
            "]+",
            flags=re.UNICODE
        )

        self.state_abbreviations = {
            'TN': 'Tennessee',
            'AL': 'Alabama',
            'AK': 'Alaska',
            'AZ': 'Arizona',
            'AR': 'Arkansas',
            'CA': 'California',
            'CO': 'Colorado',
            'CT': 'Connecticut',
            'DE': 'Delaware',
            'FL': 'Florida',
            'GA': 'Georgia',
            'HI': 'Hawaii',
            'ID': 'Idaho',
            'IL': 'Illinois',
            'IN': 'Indiana',
            'IA': 'Iowa',
            'KS': 'Kansas',
            'KY': 'Kentucky',
            'LA': 'Louisiana',
            'ME': 'Maine',
            'MD': 'Maryland',
            'MA': 'Massachusetts',
            'MI': 'Michigan',
            'MN': 'Minnesota',
            'MS': 'Mississippi',
            'MO': 'Missouri',
            'MT': 'Montana',
            'NE': 'Nebraska',
            'NV': 'Nevada',
            'NH': 'New Hampshire',
            'NJ': 'New Jersey',
            'NM': 'New Mexico',
            'NY': 'New York',
            'NC': 'North Carolina',
            'ND': 'North Dakota',
            'OH': 'Ohio',
            'OK': 'Oklahoma',
            'OR': 'Oregon',
            'PA': 'Pennsylvania',
            'RI': 'Rhode Island',
            'SC': 'South Carolina',
            'SD': 'South Dakota',
            'TX': 'Texas',
            'UT': 'Utah',
            'VT': 'Vermont',
            'VA': 'Virginia',
            'WA': 'Washington',
            'WV': 'West Virginia',
            'WI': 'Wisconsin',
            'WY': 'Wyoming'
        }

        # Create regex pattern for state abbreviations
        # Match state abbreviations with word boundaries and optional comma/period
        self.state_pattern = re.compile(
            r'\b(' + '|'.join(self.state_abbreviations.keys()) + r')\b(?=[,.\s]|$)'
        )

    def remove_markdown_formatting(self, text: str) -> str:
        """
        Remove markdown formatting like **bold** and *emphasis*.

        Args:
            text: Input text with potential markdown

        Returns:
            Text with markdown removed
        """
        # Remove bold markdown (** **)
        text = self.bold_pattern.sub(r'\1', text)

        # Remove emphasis markdown (* *)
        text = self.emphasis_pattern.sub(r'\1', text)

        return text

    def expand_abbreviations(self, text: str) -> str:
        """
        Expand common abbreviations to their full form.
        Currently handles US state abbreviations.

        Args:
            text: Input text with potential abbreviations

        Returns:
            Text with abbreviations expanded
        """
        def replace_state(match):
            abbreviation = match.group(1)
            return self.state_abbreviations.get(abbreviation, abbreviation)

        text = self.state_pattern.sub(replace_state, text)

        return text

    def simplify_times(self, text: str) -> str:
        """
        Simplify time expressions by removing :00 minutes.
        Transforms "5:00 PM" to "5 PM".

        Args:
            text: Input text with time expressions

        Returns:
            Text with simplified times
        """
        # Replace times like "5:00 PM" with "5 PM"
        text = self.time_pattern.sub(r'\1 \2', text)

        return text

    def space_phone_digits(self, text: str) -> str:
        """
        Add spaces between phone number digits so TTS reads each digit individually.
        Handles both labeled phone numbers (e.g., "Phone: 5757575757") and
        general phone formats (e.g., "(555) 556-6777").

        Args:
            text: Input text with phone numbers

        Returns:
            Text with spaced phone number digits
        """
        # First, handle labeled phone numbers (Phone:, Tel:, etc.)
        def replace_labeled_phone(match):
            identifier = match.group(1)  # e.g., "Phone"
            digits = match.group(2)      # e.g., "5757575757"
            # Add spaces between each digit
            spaced_digits = ' '.join(digits)
            return f"{identifier}: {spaced_digits}"

        text = self.phone_pattern.sub(replace_labeled_phone, text)

        # Then, handle general phone number formats
        def replace_general_phone(match):
            # Extract only the captured digit groups (ignore non-capturing groups)
            area = match.group(1)   # e.g., "555"
            prefix = match.group(2) # e.g., "556"
            line = match.group(3)   # e.g., "6777"

            # Combine all digits and space them
            all_digits = area + prefix + line
            spaced_digits = ' '.join(all_digits)

            # Return only the spaced digits (no parentheses, dashes, etc.)
            return spaced_digits

        text = self.general_phone_pattern.sub(replace_general_phone, text)

        return text

    def remove_emojis(self, text: str) -> str:
        """
        Remove all emojis from text to prevent TTS from reading them.

        Args:
            text: Input text with potential emojis

        Returns:
            Text with emojis removed
        """
        # Remove emojis
        text = self.emoji_pattern.sub('', text)

        # Clean up any double spaces that might have been created, but preserve newlines
        # First, clean up spaces on each line separately
        lines = text.split('\n')
        cleaned_lines = []
        for line in lines:
            # Remove multiple spaces within a line
            line = re.sub(r' +', ' ', line)
            # Strip leading/trailing spaces from each line
            line = line.strip()
            cleaned_lines.append(line)

        text = '\n'.join(cleaned_lines)

        return text

    def expand_eg_abbreviation(self, text: str) -> str:
        """
        Replace "e.g." with "for example" for more natural TTS.

        Args:
            text: Input text with potential "e.g." abbreviations

        Returns:
            Text with "e.g." replaced with "for example"
        """
        text = self.eg_pattern.sub('for example ', text)
        return text

    def preprocess_text(self, text: str) -> str:
        """
        Apply all preprocessing transformations to the input text.

        Args:
            text: Raw input text

        Returns:
            Preprocessed text ready for TTS
        """
        if not text:
            return text

        original_text = text

        # Apply transformations in sequence
        # Remove emojis first to avoid them interfering with other patterns
        text = self.remove_emojis(text)
        text = self.remove_markdown_formatting(text)
        text = self.expand_abbreviations(text)
        text = self.expand_eg_abbreviation(text)
        text = self.simplify_times(text)
        text = self.space_phone_digits(text)

        # Log preprocessing if text changed
        if text != original_text:
            logger.debug(f"TTS preprocessing: '{original_text[:50]}...' -> '{text[:50]}...'")

        return text


# Create a global instance for convenience
tts_preprocessor = TTSPreprocessor()


def preprocess_for_tts(text: str) -> str:
    """
    Convenience function to preprocess text for TTS.

    Args:
        text: Raw input text

    Returns:
        Preprocessed text ready for TTS
    """
    return tts_preprocessor.preprocess_text(text)
