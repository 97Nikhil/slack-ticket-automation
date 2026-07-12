# ai/gemini_processor.py

import json
import re
import base64
from typing import Optional
from pathlib import Path

import google.generativeai as genai
from PIL import Image

from config import (
    GEMINI_API_KEY,
    GEMINI_MODEL,
    QUERY_TYPES,
    STATUS_OPTIONS,
    STATUS_KEYWORDS
)
from models.ticket import Ticket, TicketStatus


class GeminiProcessor:
    """
    Handles all Gemini AI processing for tickets.

    Responsibilities:
    - Configure Gemini API connection
    - Build a detailed prompt with full ticket context
    - Send message text + images to Gemini
    - Parse structured JSON response
    - Fill ticket fields from response
    - Fall back gracefully if API fails

    Usage:
        processor = GeminiProcessor()
        processor.process(ticket)   # fills query_type, status, remarks
    """

    def __init__(self):
        """
        Configures the Gemini API with your key.
        Initializes the model once — reused for all tickets.
        """
        genai.configure(api_key=GEMINI_API_KEY)
        self.model = genai.GenerativeModel(GEMINI_MODEL)
        print("✅ Gemini processor ready")


    def _keyword_status_check(self, ticket: Ticket) -> Optional[TicketStatus]:
        """
        Fast keyword matching on thread replies before
        calling Gemini. If a clear keyword match is found,
        we use it directly and save an API call for status.

        Gemini still runs for query_type and remarks regardless.

        Returns TicketStatus if keyword found, None otherwise.
        """
        all_reply_text = " ".join(ticket.thread_replies).lower()

        for keyword, status_value in STATUS_KEYWORDS.items():
            if keyword in all_reply_text:
                print(f"   🔑 Status keyword found: '{keyword}' → {status_value}")
                # Find matching TicketStatus enum value
                for status in TicketStatus:
                    if status.value == status_value:
                        return status

        return None


    def _build_prompt(self, ticket: Ticket) -> str:
        """
        Builds the instruction prompt sent to Gemini.

        A good prompt has 4 parts:
        1. Role — tell Gemini what it is
        2. Context — give it the ticket data
        3. Instructions — exactly what to do
        4. Output format — exactly how to respond

        The clearer the prompt, the better the output.
        """

        # Format thread replies as numbered list for clarity
        replies_text = ""
        if ticket.thread_replies:
            replies_text = "\n".join([
                f"Reply {i+1}: {reply}"
                for i, reply in enumerate(ticket.thread_replies)
            ])
        else:
            replies_text = "No replies in thread"

        # Format query types as numbered list for Gemini to choose from
        query_types_list = "\n".join([
            f"{i+1}. {qt}" for i, qt in enumerate(QUERY_TYPES)
        ])

        # Format status options as numbered list
        status_list = "\n".join([
            f"{i+1}. {s}" for i, s in enumerate(STATUS_OPTIONS)
        ])

        prompt = f"""
You are a customer support ticket analyst at ConvertWay, a Shopify marketing automation platform.

Your job is to analyze a support ticket from Slack and extract structured information.

═══════════════════════════════════════
TICKET INFORMATION
═══════════════════════════════════════

ORIGINAL MESSAGE:
{ticket.original_message}

STORE URL: {ticket.store_url or "Not detected"}

THREAD REPLIES:
{replies_text}

═══════════════════════════════════════
YOUR TASKS
═══════════════════════════════════════

TASK 1 — QUERY TYPE
Choose exactly ONE from this list that best describes the issue.
You must pick from this list only — do not invent new categories.

{query_types_list}

TASK 2 — STATUS SUGGESTION
Based on the thread replies, suggest the current ticket status.
Choose exactly ONE from this list only:

{status_list}

TASK 3 — DETAILED REMARKS
Write a full, professional, detailed description of this ticket for internal records.

The remarks must include:
- What the customer reported (the issue)
- Store URL and any identifiers mentioned (campaign name, flow name, order IDs, error messages)
- What investigation or action was taken (from thread replies)
- Current resolution status
- Any important technical details visible in screenshots

Write in third person. Be specific. Do not make up information not present in the message or replies.
Minimum 3 sentences. Maximum 8 sentences.

═══════════════════════════════════════
OUTPUT FORMAT
═══════════════════════════════════════

Respond ONLY with a valid JSON object. No explanation before or after.
No markdown. No code blocks. Just the raw JSON.

{{
    "query_type": "exact text from the query type list above",
    "status_suggestion": "exact text from the status list above",
    "remarks": "your detailed remarks here",
    "confidence": "high/medium/low",
    "extracted_identifiers": {{
        "campaign_name": "if found, else null",
        "flow_name": "if found, else null",
        "order_ids": "if found, else null",
        "error_message": "if found, else null"
    }}
}}
"""
        return prompt.strip()


    def _load_images(self, image_paths: list) -> list:
        """
        Loads images from local paths for sending to Gemini.

        Gemini accepts images as PIL Image objects.
        We load each saved screenshot and add to the request.

        Skips images that can't be loaded rather than crashing.
        """
        images = []

        for path in image_paths:
            try:
                if Path(path).exists():
                    img = Image.open(path)
                    images.append(img)
                    print(f"   🖼️  Image loaded: {path}")
                else:
                    print(f"   ⚠️  Image not found: {path}")
            except Exception as e:
                print(f"   ⚠️  Could not load image {path}: {e}")

        return images


    def _parse_response(self, response_text: str) -> Optional[dict]:
        """
        Parses Gemini's JSON response into a Python dictionary.

        Gemini sometimes adds extra text around the JSON even
        when told not to — we handle this by finding the JSON
        block inside the response using regex.

        Returns parsed dict or None if parsing failed.
        """
        try:
            # First try direct JSON parse (ideal case)
            return json.loads(response_text)

        except json.JSONDecodeError:
            # Gemini added text around JSON — extract just the JSON part
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)

            if json_match:
                try:
                    return json.loads(json_match.group())
                except json.JSONDecodeError:
                    pass

        print("   ⚠️  Could not parse Gemini response as JSON")
        print(f"   Raw response: {response_text[:200]}...")
        return None


    def _validate_query_type(self, query_type: str) -> Optional[str]:
        """
        Validates that Gemini's query type choice exactly matches
        one of our predefined options.

        Gemini might return slightly different text sometimes.
        We do a case-insensitive check to catch minor variations.
        """
        # Exact match first
        if query_type in QUERY_TYPES:
            return query_type

        # Case-insensitive match as fallback
        for qt in QUERY_TYPES:
            if qt.lower() == query_type.lower():
                return qt   # return the correctly-cased version

        print(f"   ⚠️  Gemini returned unknown query type: {query_type}")
        return None


    def _validate_status(self, status_text: str) -> Optional[TicketStatus]:
        """
        Validates Gemini's status suggestion against our
        TicketStatus enum values.

        Returns the matching TicketStatus enum or None.
        """
        for status in TicketStatus:
            if status.value.lower() == status_text.lower():
                return status

        print(f"   ⚠️  Gemini returned unknown status: {status_text}")
        return None


    def process(self, ticket: Ticket) -> Ticket:
        """
        Main method — processes one ticket with Gemini.

        Flow:
        1. Try keyword matching for status (fast, free)
        2. Build prompt with full ticket context
        3. Load images if any
        4. Send to Gemini
        5. Parse JSON response
        6. Validate and fill ticket fields
        7. Flag if anything couldn't be determined

        Always returns ticket whether successful or not.
        """
        print(f"\n   🤖 Processing with Gemini: {ticket.thread_ts}")

        # ── Step 1: Keyword check for status ──────────────
        keyword_status = self._keyword_status_check(ticket)
        if keyword_status:
            ticket.status        = keyword_status
            ticket.status_source = "keyword"

        # ── Step 2: Build prompt ───────────────────────────
        prompt = self._build_prompt(ticket)

        # ── Step 3: Load images ────────────────────────────
        images = self._load_images(ticket.image_paths)

        # ── Step 4: Send to Gemini ─────────────────────────
        try:
            # Build content list — prompt first, then images
            content = [prompt] + images

            response = self.model.generate_content(content)
            response_text = response.text
            print(f"   ✅ Gemini responded")

        except Exception as e:
            print(f"   ❌ Gemini API call failed: {e}")
            ticket.flag(f"Gemini API call failed: {e}")
            return ticket

        # ── Step 5: Parse response ─────────────────────────
        parsed = self._parse_response(response_text)

        if not parsed:
            ticket.flag("Gemini response could not be parsed")
            return ticket

        # ── Step 6: Fill ticket fields ─────────────────────

        # Query Type
        raw_query_type = parsed.get("query_type", "")
        valid_query_type = self._validate_query_type(raw_query_type)

        if valid_query_type:
            ticket.query_type = valid_query_type
        else:
            ticket.flag(f"Invalid query type from Gemini: {raw_query_type}")

        # Status — only use Gemini's if keyword didn't find it
        if ticket.status == TicketStatus.UNKNOWN:
            raw_status = parsed.get("status_suggestion", "")
            valid_status = self._validate_status(raw_status)

            if valid_status:
                ticket.status        = valid_status
                ticket.status_source = "gemini"
            else:
                ticket.flag("Status could not be determined")

        # Remarks
        remarks = parsed.get("remarks", "").strip()
        if remarks:
            ticket.remarks = remarks
        else:
            ticket.flag("Gemini did not generate remarks")

        # Confidence — if low confidence, flag for review
        confidence = parsed.get("confidence", "high")
        if confidence == "low":
            ticket.flag(f"Gemini low confidence — please review")

        # Store extracted identifiers in remarks as additional context
        identifiers = parsed.get("extracted_identifiers", {})
        if any(v for v in identifiers.values() if v):
            extras = []
            if identifiers.get("campaign_name"):
                extras.append(f"Campaign: {identifiers['campaign_name']}")
            if identifiers.get("flow_name"):
                extras.append(f"Flow: {identifiers['flow_name']}")
            if identifiers.get("order_ids"):
                extras.append(f"Order IDs: {identifiers['order_ids']}")
            if identifiers.get("error_message"):
                extras.append(f"Error: {identifiers['error_message']}")

            if extras and ticket.remarks:
                ticket.remarks += "\n\nIdentifiers: " + " | ".join(extras)

        print(f"   ✅ Query Type : {ticket.query_type}")
        print(f"   ✅ Status     : {ticket.status.value} (via {ticket.status_source})")
        print(f"   ✅ Remarks    : {ticket.remarks[:80]}...")

        return ticket