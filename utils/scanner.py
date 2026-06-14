import re
from rapidfuzz import fuzz

import config
from core.database import BLACK_LISTED_DOMAINS, BLACK_LISTED_SPAM_PHRASES

SPAM_REGEX_PATTERNS = [
    r"\+[0-9,]+\s?usdt",
    r"\$[0-9,]+\s?was success",
    r"discord\.gift/[a-zA-Z0-9]+",
    r"withdrawal of \$[0-9,]+",
]

_COMPILED_PATTERNS = [re.compile(p, re.IGNORECASE) for p in SPAM_REGEX_PATTERNS]

def normalize_text(text: str) -> str:
    """Normalize text by lowercasing, removing invisible chars, and stripping redundant spaces."""
    # Convert to lowercase
    text = text.lower()
    
    # Remove invisible zero-width characters (e.g. \u200B, \u200C, \u200D, \uFEFF)
    text = re.sub(r'[\u200B-\u200D\uFEFF]', '', text)
    
    # Keep alphanumeric, Thai characters, specific symbols, and spaces
    text = re.sub(r'[^a-z0-9ก-ฮ\.\$\+\s]', ' ', text)
    
    # Compress multiple spaces into one
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def analyze_text(text: str) -> tuple[bool, str]:
    """Analyze text for spam patterns, exact matches, and fuzzy matches."""
    # Check regex patterns on original text
    for pattern in _COMPILED_PATTERNS:
        if pattern.search(text):
            return True, f"Caught spam pattern: '{pattern.pattern}'"

    norm_text = normalize_text(text)
    # Text with no spaces to catch spaced-out words like 'f r e e'
    no_space_text = norm_text.replace(' ', '')
    
    fuzzy_threshold = getattr(config, 'FUZZY_THRESHOLD', 85)

    # Blacklist domains
    for domain in BLACK_LISTED_DOMAINS:
        norm_domain = normalize_text(domain)
        no_space_domain = norm_domain.replace(' ', '')
        
        if norm_domain in norm_text or no_space_domain in no_space_text:
            return True, f"Caught malicious link: '{domain}'"
            
        if len(norm_domain) > 5:
            score = fuzz.partial_ratio(norm_domain, norm_text)
            if score >= fuzzy_threshold:
                return True, f"Caught similar link: '{domain}' ({int(score)}%)"

    # Blacklist phrases
    for phrase in BLACK_LISTED_SPAM_PHRASES:
        norm_phrase = normalize_text(phrase)
        no_space_phrase = norm_phrase.replace(' ', '')
        
        # Check normal match and no-space match (if phrase is long enough)
        if norm_phrase in norm_text or (len(no_space_phrase) > 3 and no_space_phrase in no_space_text):
            return True, f"Caught spam phrase: '{phrase}'"
            
        if len(norm_phrase) > 5:
            score = fuzz.partial_ratio(norm_phrase, norm_text)
            if score >= fuzzy_threshold:
                return True, f"Caught similar phrase: '{phrase}' ({int(score)}%)"

    return False, ""
