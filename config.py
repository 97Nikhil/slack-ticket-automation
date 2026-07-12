# config.py
# ─────────────────────────────────────────────────────
# ALL personal credentials and settings live here.
# Never share this file. Never upload it to GitHub.
# ─────────────────────────────────────────────────────

# ── Slack ──────────────────────────────────────────
SLACK_TOKEN = ""

# Your 2 channel IDs (right-click channel in Slack browser → copy link → last part)
SLACK_CHANNEL_IDS = [
    "C06P9C7B1RN",   # replace with channel 1 ID
    "C06HVR8N4EQ",   # replace with channel 2 ID
]

# ── Gemini ─────────────────────────────────────────
GEMINI_API_KEY = ""
GEMINI_MODEL   = "gemini-1.5-flash"   # free tier model

# ── Admin Panel ────────────────────────────────────
ADMIN_PANEL_URL = "https://paste-your-admin-panel-url-here"

# ── Google Form ────────────────────────────────────
GOOGLE_FORM_URL = "https://docs.google.com/forms/d/YOUR_FORM_ID/viewform"

# Form field entry IDs — get these by inspecting your form (we'll do this together)
FORM_FIELDS = {
    "email":               "entry.000000001",
    "date":                "entry.000000002",
    "brand_name":          "entry.000000003",
    "store_url":           "entry.000000004",
    "order_count":         "entry.000000005",
    "average_consumption": "entry.000000006",
    "query_type":          "entry.000000007",
    "status":              "entry.000000008",
    "channel":             "entry.000000009",
    "priority":            "entry.000000010",
    "aging":               "entry.000000011",
    "remarks":             "entry.000000012",
}

# ── Hardcoded Values ───────────────────────────────
FIXED_CHANNEL   = "Slack"
FIXED_AGING     = "0-1"
FIXED_EMAIL     = "nikhil.01@convertway.in"

# ── Priority Rules (based on order count) ──────────
PRIORITY_RULES = {
    "unmanaged": {"max": 10,  "label": "Unmanaged (Very Small Customers, Very small issue)"},
    "p2":        {"max": 100, "label": "P2"},
    "p1":        {"min": 100, "label": "P1 (Irate Customers, High Value Customers)"},
}

# ── Query Type Options (exactly as in Google Form) ─
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

# ── Status Options (exactly as in Google Form) ─────
STATUS_OPTIONS = [
    "Pending from support",
    "Pending from tech team",
    "Pending customer response",
    "Ticket Open at third party (Meta, Kaleyra, Shopify etc)",
    "Resolved",
    "Pending from KAM",
]

# ── Keyword → Status Mapping ───────────────────────
# Keywords found in thread replies → mapped to exact form value
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
