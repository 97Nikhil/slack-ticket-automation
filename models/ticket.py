# models/ticket.py

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from enum import Enum


# ── Enums ──────────────────────────────────────────────────────────────────
# Enums are a clean way to define a fixed set of allowed values.
# Instead of using raw strings like "Resolved" everywhere in your code
# (which can have typos), you use TicketStatus.RESOLVED.
# Python will catch typos at runtime immediately.

class TicketStatus(Enum):
    PENDING_SUPPORT   = "Pending from support"
    PENDING_TECH      = "Pending from tech team"
    PENDING_CUSTOMER  = "Pending customer response"
    THIRD_PARTY       = "Ticket Open at third party (Meta, Kaleyra, Shopify etc)"
    RESOLVED          = "Resolved"
    PENDING_KAM       = "Pending from KAM"
    UNKNOWN           = "Unknown"          # when neither keyword nor Gemini could detect


class TicketPriority(Enum):
    P0          = "Leadership - P0"
    P1          = "P1 (Irate Customers, High Value Customers)"
    P2          = "P2"
    UNMANAGED   = "Unmanaged (Very Small Customers, Very small issue)"
    UNKNOWN     = "Unknown"                # when order count couldn't be fetched


class TicketChannel(Enum):
    SLACK       = "Slack"
    CRISP       = "Crisp"
    WHATSAPP    = "Whatsapp/Periskope"
    EMAIL       = "Email"


class TicketAging(Enum):
    ZERO_TO_ONE = "0-1"
    TWO_TO_THREE = "2-3"
    FOUR_TO_FIVE = "4-5"
    FIVE_PLUS    = "5+"


# ── Ticket Dataclass ───────────────────────────────────────────────────────
# A dataclass is a special Python class designed to hold data.
# @dataclass automatically creates __init__, __repr__, and __eq__ for you.
# You don't need to write def __init__(self, ...) manually.
# 
# Optional[str] means the field can be a string OR None (not filled yet).
# field(default=None) means the default value is None.

@dataclass
class Ticket:

    # ── Slack Identity ─────────────────────────────
    # These fields identify WHERE this ticket came from in Slack.
    # thread_ts is Slack's unique ID for a message — we use it
    # to check if this ticket was already processed (SQLite check).

    thread_ts:      str                         # Slack message timestamp — unique ID
    channel_id:     str                         # Which Slack channel
    slack_url:      Optional[str] = None        # Direct link to the Slack thread


    # ── Raw Content ────────────────────────────────
    # Exactly what came from Slack, untouched.
    # We store raw content so we never lose original data.
    # Gemini will read these to generate structured output.

    original_message:   Optional[str] = None    # The parent Slack message text
    thread_replies:     list = field(default_factory=list)   # All reply texts in thread
    image_paths:        list = field(default_factory=list)   # Local paths to downloaded screenshots


    # ── Extracted Fields ───────────────────────────
    # These are pulled from the Slack message directly
    # by our extractor — no AI needed for these.

    store_url:      Optional[str] = None        # Regex extracted from message
    date:           Optional[str] = None        # Today's date when script runs


    # ── Admin Panel Fields ─────────────────────────
    # These come from Selenium scraping your admin panel.

    brand_name:         Optional[str] = None    # Scraped from store page
    order_count:        Optional[int] = None    # From admin panel
    install_date:       Optional[str] = None    # From admin panel (to calc avg consumption)
    used_amount:        Optional[float] = None  # From admin panel (wallet used)
    average_consumption: Optional[float] = None # Calculated: used_amount / months_installed


    # ── AI Generated Fields ────────────────────────
    # These are filled by Gemini after reading the full thread.

    query_type:     Optional[str] = None        # One of the 15 query types
    remarks:        Optional[str] = None        # Full structured remark written by Gemini


    # ── Status ─────────────────────────────────────
    # Filled by keyword matching first, Gemini as fallback.
    # Default is UNKNOWN until detected.

    status:         TicketStatus = TicketStatus.UNKNOWN
    status_source:  Optional[str] = None        # "keyword" or "gemini" or "manual"


    # ── Form Fields ────────────────────────────────
    # These are either hardcoded or calculated from other fields.

    channel:        TicketChannel = TicketChannel.SLACK   # always Slack
    aging:          TicketAging   = TicketAging.ZERO_TO_ONE  # always 0-1
    priority:       TicketPriority = TicketPriority.UNKNOWN  # calculated from order_count


    # ── Processing Metadata ────────────────────────
    # Tracks the state of this ticket through the pipeline.
    # Useful for knowing what step failed if something goes wrong.

    created_at:         str = field(default_factory=lambda: datetime.now().isoformat())
    is_submitted:       bool = False            # True after form is submitted
    needs_manual_review: bool = False           # True if flagged for your attention
    flag_reason:        Optional[str] = None    # Why it was flagged


    # ── Methods ────────────────────────────────────
    # Methods are functions that belong to the Ticket class.
    # They can read and modify the ticket's own data using self.

    def calculate_priority(self) -> TicketPriority:
        """
        Calculates priority based on order count.
        Called after order_count is filled from admin panel.

        Returns the priority and also sets self.priority so the
        ticket updates itself.
        """
        if self.order_count is None:
            self.priority = TicketPriority.UNKNOWN
        elif self.order_count < 10:
            self.priority = TicketPriority.UNMANAGED
        elif self.order_count <= 100:
            self.priority = TicketPriority.P2
        else:
            self.priority = TicketPriority.P1

        return self.priority


    def calculate_average_consumption(self) -> Optional[float]:
        """
        Calculates average monthly consumption.
        Formula: used_amount / months since install_date

        Called after admin panel scraping fills
        used_amount and install_date.
        """
        if not self.used_amount or not self.install_date:
            return None

        try:
            install = datetime.strptime(self.install_date, "%Y-%m-%d")
            now     = datetime.now()

            # Calculate months between install date and today
            months = (now.year - install.year) * 12 + (now.month - install.month)

            # Avoid division by zero for brand new installs
            if months == 0:
                months = 1

            self.average_consumption = round(self.used_amount / months, 2)
            return self.average_consumption

        except ValueError:
            # Date parsing failed — flag for manual review
            self.flag("Could not parse install date for avg consumption calculation")
            return None


    def flag(self, reason: str):
        """
        Marks this ticket for manual review.
        Called whenever something couldn't be auto-detected.

        Example:
            ticket.flag("No status keyword found in thread")
            ticket.flag("Store URL not found in message")
        """
        self.needs_manual_review = True
        self.flag_reason = reason


    def is_ready_for_submission(self) -> bool:
        """
        Checks if all required fields are filled before
        opening the Google Form.

        Returns True if ready, False if something is missing.
        Missing fields are printed so you know what to fix.
        """
        required_fields = {
            "store_url":    self.store_url,
            "brand_name":   self.brand_name,
            "order_count":  self.order_count,
            "query_type":   self.query_type,
            "remarks":      self.remarks,
        }

        missing = [k for k, v in required_fields.items() if not v]

        if missing:
            print(f"  ⚠️  Ticket {self.thread_ts} missing fields: {missing}")
            return False

        if self.status == TicketStatus.UNKNOWN:
            print(f"  ⚠️  Ticket {self.thread_ts} has unknown status — needs review")
            return False

        return True


    def to_form_data(self) -> dict:
        """
        Converts the Ticket object into a flat dictionary
        ready to be passed to the form filler.

        The form filler doesn't need to know about Enums or
        internal fields — it just needs key:value pairs.
        """
        return {
            "email":                self.get_email(),
            "date":                 self.date,
            "brand_name":           self.brand_name,
            "store_url":            self.store_url,
            "order_count":          str(self.order_count) if self.order_count else "",
            "average_consumption":  str(self.average_consumption) if self.average_consumption else "",
            "query_type":           self.query_type,
            "status":               self.status.value,   # .value gets the string from Enum
            "channel":              self.channel.value,
            "priority":             self.priority.value,
            "aging":                self.aging.value,
            "remarks":              self.remarks,
        }


    def get_email(self) -> str:
        """Returns the fixed email — imported here to avoid circular imports."""
        from config import FIXED_EMAIL
        return FIXED_EMAIL


    def __repr__(self) -> str:
        """
        Controls what prints when you do print(ticket).
        Useful for debugging — gives you a clean summary.
        """
        return (
            f"\nTicket("
            f"\n  thread_ts   = {self.thread_ts}"
            f"\n  store_url   = {self.store_url}"
            f"\n  brand_name  = {self.brand_name}"
            f"\n  query_type  = {self.query_type}"
            f"\n  status      = {self.status.value}"
            f"\n  priority    = {self.priority.value}"
            f"\n  flagged     = {self.needs_manual_review}"
            f"\n  flag_reason = {self.flag_reason}"
            f"\n  submitted   = {self.is_submitted}"
            f"\n)"
        )