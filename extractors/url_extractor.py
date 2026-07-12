# extractors/url_extractor.py

import re
from typing import Optional
from models.ticket import Ticket


class URLExtractor:
    """
    Extracts and cleans store URLs from Slack message text.

    Handles all URL formats seen in real Slack messages:
    - Clean URL: myadira.myshopify.com
    - With prefix: store url: myadira.myshopify.com
    - With https: https://myadira.myshopify.com
    - With trailing slash: myadira.myshopify.com/

    Usage:
        extractor = URLExtractor()
        extractor.process(ticket)   # fills ticket.store_url
    """

    # Regex patterns ordered by priority
    # We try each pattern one by one until one matches
    # The first match wins
    PATTERNS = [

        # Pattern 1 — Full URL with http/https
        # Matches: https://myadira.myshopify.com
        #          http://myadira.myshopify.com
        r'https?://([a-zA-Z0-9\-]+\.myshopify\.com)',

        # Pattern 2 — After "store url:" keyword (case insensitive)
        # Matches: store url: myadira.myshopify.com
        #          Store URL: myadira.myshopify.com
        #          store url - myadira.myshopify.com
        r'store\s*url\s*[:\-]\s*([a-zA-Z0-9\-]+\.myshopify\.com)',

        # Pattern 3 — After "store:" keyword
        # Matches: store: myadira.myshopify.com
        r'store\s*[:\-]\s*([a-zA-Z0-9\-]+\.myshopify\.com)',

        # Pattern 4 — Bare domain anywhere in text (most permissive)
        # Matches: myadira.myshopify.com
        # This is last because it's the most broad
        r'([a-zA-Z0-9\-]+\.myshopify\.com)',
    ]


    def _clean_url(self, raw_url: str) -> str:
        """
        Cleans a raw URL into a consistent format.

        We always store URLs as:
        https://storename.myshopify.com
        (with https, without trailing slash)

        This way the admin panel scraper always
        gets a consistent URL to work with.
        """
        # Remove trailing slash
        url = raw_url.rstrip("/")

        # Remove https:// or http:// if present
        # We'll add https:// back in a controlled way
        url = re.sub(r'^https?://', '', url)

        # Add https:// prefix
        url = f"https://{url}"

        return url.lower()   # lowercase for consistency


    def _extract_from_text(self, text: str) -> Optional[str]:
        """
        Tries each regex pattern against the message text.
        Returns the first match found, or None if nothing matches.

        re.IGNORECASE means pattern works regardless of
        upper/lowercase — "Store URL" and "store url" both match.
        """
        for pattern in self.PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                # match.group(1) is the captured group (inside parentheses)
                # This gives us just the domain, not the full match
                return match.group(1)

        return None


    def process(self, ticket: Ticket) -> Ticket:
        """
        Main method — extracts store URL from ticket's message
        and fills ticket.store_url.

        Also checks thread replies in case the URL was
        posted in a reply instead of the main message.

        Always returns the ticket (modified or not) so it can
        be chained in the pipeline.
        """
        # Try main message first
        raw_url = self._extract_from_text(ticket.original_message or "")

        # If not found in main message, check thread replies
        if not raw_url:
            print("   🔍 URL not in main message, checking replies...")
            for reply in ticket.thread_replies:
                raw_url = self._extract_from_text(reply)
                if raw_url:
                    print("   ✅ URL found in thread reply")
                    break

        if raw_url:
            ticket.store_url = self._clean_url(raw_url)
            print(f"   ✅ Store URL extracted: {ticket.store_url}")
        else:
            # No URL found anywhere — flag for manual review
            ticket.flag("Store URL not found in message or thread replies")
            print(f"   ⚠️  No store URL found — ticket flagged")

        return ticket