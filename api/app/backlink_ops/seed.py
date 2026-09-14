"""Backlink Ops — domain reference data.

These are the fixed rules of the game: what a link type is worth, what each
difficulty level demands, and the seed keyword clusters each site works
through. They are code, not user data, so they version with the repo and are
reviewable in a diff. Anything an operator should be able to change at runtime
(current level, team roster) lives in bo_config instead.
"""

PROJECTS = {
    "agenticai": {
        "id": "agenticai",
        "name": "AgenticAiAutomation.co",
        "short": "AgenticAI",
        "hue": "#00998C",
        "initial": "A",
        "niche": ("AI and RPA automation for hospitals, insurance, banking, back-office, "
                  "CA firms and CS firms — plus AI appointment systems and WhatsApp automation."),
        "pages": ["/whatsapp-automation", "/rpa-migration", "/ai-agents", "/healthcare-automation",
                  "/bfsi-automation", "/ca-firm-automation", "/appointment-automation",
                  "/back-office-automation", "/contact"],
    },
    "diymart": {
        "id": "diymart",
        "name": "DIYMart.in",
        "short": "DIYMart",
        "hue": "#B85520",
        "initial": "D",
        "niche": ("Online DIY, home-improvement and gifting retail in India — head-to-head with "
                  "Mr. DIY on store, tools, decor, craft, party and gifting keywords."),
        "pages": ["/store", "/gifting", "/home-decor", "/tools-hardware", "/craft-kits",
                  "/party-supplies", "/organizers", "/diy-ideas", "/corporate-gifting"],
    },
}

SEED_KEYWORDS = {
    "agenticai": [
        "whatsapp automation for hospitals", "hospital appointment automation software india",
        "rpa for insurance claims processing", "insurance policy issuance automation",
        "banking back office automation services", "bank reconciliation automation software",
        "automation for ca firms india", "gst return filing automation software",
        "company secretary compliance automation", "back office process automation services",
        "ai agent for appointment booking", "whatsapp chatbot for clinics",
        "uipath alternative for indian smes", "rpa migration services",
        "n8n automation agency india", "ai automation agency india",
        "invoice processing automation india", "kyc automation for banks",
        "claims settlement automation software", "patient intake automation software",
        "roc filing automation", "tally automation for accountants",
        "whatsapp api for appointment reminders", "insurance underwriting automation",
        "loan processing automation india",
    ],
    "diymart": [
        "mr diy india", "diy store online india", "home improvement products online india",
        "gift items online india", "birthday gift ideas under 500", "diy craft kit online india",
        "home decor items online cheap", "party decoration items online",
        "return gifts for birthday", "diy room decor ideas", "tools and hardware online india",
        "storage organizer online india", "diy gift ideas for boyfriend",
        "craft supplies online india", "festive decoration items online",
        "kitchen organizer online india", "car accessories online india",
        "diy painting kit for adults", "corporate gifting india online",
        "anniversary gift ideas india", "wall hanging decor online",
        "stationery combo set online", "diy furniture ideas india", "rakhi gift ideas online",
        "cheap household items online india",
    ],
}

# base points, and whether the placement counts as "high value" for level gates
LINK_TYPES = [
    {"v": "guest_post",       "l": "Guest post",               "p": 15, "tier": "high"},
    {"v": "resource_page",    "l": "Resource / listicle page", "p": 12, "tier": "high"},
    {"v": "niche_edit",       "l": "Niche edit / link insert", "p": 11, "tier": "high"},
    {"v": "pr",               "l": "PR / news placement",      "p": 10, "tier": "high"},
    {"v": "podcast",          "l": "Podcast / interview",      "p":  9, "tier": "high"},
    {"v": "infographic",      "l": "Infographic / image",      "p":  8, "tier": "mid"},
    {"v": "qa",               "l": "Q&A (Quora / Reddit)",     "p":  6, "tier": "mid"},
    {"v": "forum",            "l": "Forum / community",        "p":  5, "tier": "mid"},
    {"v": "web2",             "l": "Web 2.0 property",         "p":  5, "tier": "mid"},
    {"v": "business_listing", "l": "Business listing",         "p":  4, "tier": "low"},
    {"v": "directory",        "l": "Directory submission",     "p":  3, "tier": "low"},
    {"v": "profile",          "l": "Profile creation",         "p":  3, "tier": "low"},
    {"v": "social_bookmark",  "l": "Social bookmark",          "p":  3, "tier": "low"},
    {"v": "comment",          "l": "Blog comment",             "p":  2, "tier": "low"},
]
TYPE_MAP = {t["v"]: t for t in LINK_TYPES}

# Difficulty ladder. Start at 1; raise only when both associates clear five
# consecutive days (see docs/RUNBOOK.md, "Raising the level").
LEVELS = [
    {"n": 1, "name": "Warm-up", "target":  60, "queries": 3, "min_avg_da": 20,
     "high_value": 0, "max_exact": 0.40, "index_rate": 0.00},
    {"n": 2, "name": "Steady",  "target":  75, "queries": 4, "min_avg_da": 25,
     "high_value": 1, "max_exact": 0.35, "index_rate": 0.00},
    {"n": 3, "name": "Push",    "target":  90, "queries": 5, "min_avg_da": 30,
     "high_value": 2, "max_exact": 0.30, "index_rate": 0.40},
    {"n": 4, "name": "Pro",     "target": 110, "queries": 6, "min_avg_da": 35,
     "high_value": 3, "max_exact": 0.25, "index_rate": 0.55},
    {"n": 5, "name": "Elite",   "target": 130, "queries": 7, "min_avg_da": 40,
     "high_value": 4, "max_exact": 0.20, "index_rate": 0.70},
]

DEFAULT_ROSTER = [
    {"name": "Jai",              "project": "agenticai", "owner": True},
    {"name": "SEO Associate 1",  "project": "agenticai", "owner": False},
    {"name": "SEO Associate 2",  "project": "diymart",   "owner": False},
]

DEFAULT_CONFIG = {"level": 1, "roster": DEFAULT_ROSTER}


def level(n):
    idx = max(0, min(int(n or 1) - 1, len(LEVELS) - 1))
    return LEVELS[idx]
