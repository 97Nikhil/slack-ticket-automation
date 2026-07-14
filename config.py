# config.py
import os
from dotenv import load_dotenv

# Load .env file into environment
load_dotenv()

# ── Slack ──────────────────────────────────────────
SLACK_TOKEN = os.getenv("SLACK_TOKEN")
SLACK_CHANNEL_IDS = [
    os.getenv("SLACK_CHANNEL_ID_1"),
    os.getenv("SLACK_CHANNEL_ID_2"),
]

# ── Gemini ─────────────────────────────────────────
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = "gemini-2.0-flash"

# ── Admin Panel ────────────────────────────────────
ADMIN_PANEL_URL = os.getenv("ADMIN_PANEL_URL")

# ── Google Form ────────────────────────────────────
GOOGLE_FORM_URL = os.getenv("GOOGLE_FORM_URL")

FORM_FIELDS = {
    "email":               "emailAddress",       # special field — not entry.xxx
    "date":                "entry.2008450749",   # date field (splits into _year _month _day)
    "brand_name":          "entry.504235780",
    "store_url":           "entry.779455465",
    "order_count":         "entry.1450916064",
    "average_consumption": "entry.1807040935",
    "query_type":          "entry.1053956291",
    "status":              "entry.298503497",
    "channel":             "entry.1262316531",
    "priority":            "entry.1023708205",
    "aging":               "entry.662103023",
    "remarks":             "entry.1863345591",
}

# ── Hardcoded Values ───────────────────────────────
FIXED_CHANNEL = "Slack"
FIXED_AGING   = "0-1"
FIXED_EMAIL   = "nikhil.01@convertway.in"

# ── Priority Rules ─────────────────────────────────
PRIORITY_RULES = {
    "unmanaged": {"max": 10,  "label": "Unmanaged (Very Small Customers, Very small issue)"},
    "p2":        {"max": 100, "label": "P2"},
    "p1":        {"min": 100, "label": "P1 (Irate Customers, High Value Customers)"},
}

# ── Query Type Options ─────────────────────────────
QUERY_TYPES = [
    "SMS/RCS",
    "Campagin/Template Related",
    "Noitifications/Flows related",
    "Widget/POP-UP",
    "Meta related/WABA/OBA/Kaleya",
    "Report/Data update",
    "Billing",
    "Chat Bot/Catalogue/Instagram/email/Agent-base",
    "Converstation panel",
    "AI Agent related",
    "Plan Upgrade",
    "New Requirement",
    "Demo",
    "Spam/Fraud",
    "Store Related",
]

# ── Status Options ─────────────────────────────────
STATUS_OPTIONS = [
    "Pending from support",
    "Pending from tech team",
    "Pending customer response",
    "Ticket Open at third party (Meta, Kaleyra, Shopify etc)",
    "Resolved",
    "Pending from KAM",
]

# ── Keyword → Status Mapping ───────────────────────
STATUS_KEYWORDS = {
    "resolved":          "Resolved",
    "resolve":           "Resolved",
    "raised with tech":  "Pending from tech team",
    "raised with meta":  "Ticket Open at third party (Meta, Kaleyra, Shopify etc)",
    "pending customer":  "Pending customer response",
    "waiting for store": "Pending customer response",
    "pending from kam":  "Pending from KAM",
}

# ── Database ───────────────────────────────────────
DB_PATH = "database/tickets.db"

# ── Validation — warns you if any key is missing ──
def validate_config():
    required = {
        "SLACK_TOKEN": SLACK_TOKEN,
        "GEMINI_API_KEY": GEMINI_API_KEY,
        "ADMIN_PANEL_URL": ADMIN_PANEL_URL,
        "GOOGLE_FORM_URL": GOOGLE_FORM_URL,
    }
    missing = [k for k, v in required.items() if not v]
    if missing:
        raise ValueError(f"Missing required config values: {missing}\nCheck your .env file.")