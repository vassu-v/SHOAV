"""Thresholds for the deterministic filter core.

Every number here is a heuristic parameter, not a measured constant — the
literature review (research/08-synthesis/OPEN_QUESTIONS.md, question 2) is
explicit that no false-positive rate has been measured for rules like these.
Keep them here, in one place, so they can be tuned from real test results
instead of being buried inline.
"""

# --- Ingress: hidden/invisible text (Target 1, DETECTION_TARGETS.md) ---
# opacity/off-screen thresholds per DETERMINISTIC_TARGETS.md Target 1.
INGRESS_OPACITY_THRESHOLD = 0.05
INGRESS_MIN_FONT_SIZE_PX = 0.0
INGRESS_OFFSCREEN_LEFT_PX = -500.0

# Class/attribute substrings treated as legitimate reasons for hidden-but-
# textful content, so Target 1 does not flag ordinary accessibility/UI
# patterns as injections. Not exhaustive — a documented, not a solved, gap.
INGRESS_BENIGN_HIDDEN_MARKERS = (
    "sr-only",
    "visually-hidden",
    "visuallyhidden",
    "screen-reader",
    "a11y-hidden",
)

# Deterministic keyword heuristic for HTML-comment / hidden-text injection
# attempts. This is pattern matching, not language understanding — it will
# miss paraphrased injections and can over-fire on legitimate dev comments
# that happen to use these words. Documented limitation, not a solved gap.
INGRESS_INJECTION_KEYWORDS = (
    "ignore previous",
    "ignore all previous",
    "disregard",
    "system prompt",
    "you are now",
    "new instructions",
    "act as",
    "assistant:",
)

ZERO_WIDTH_CHARS = ("​", "‌", "‍", "﻿")

# --- Ingress: context overloading / node budget (Target 4) ---
# Trigger and target both from DETERMINISTIC_TARGETS.md Target 4 /
# PLAN_AND_ROUGH_SKETCH.md 3.1 step 1.
INGRESS_NODE_BUDGET_TRIGGER = 150
INGRESS_NODE_BUDGET_TARGET = 50
INGRESS_TOKEN_BUDGET_TRIGGER = 4000
# ~4 chars/token, the usual rough English-text estimate; good enough for a
# budget trigger, not meant to match any specific tokenizer exactly.
INGRESS_CHARS_PER_TOKEN_ESTIMATE = 4

# Interactive tag/role priority when compacting — kept over dropped when a
# budget cut has to choose. Earlier entries are kept first.
INGRESS_NODE_PRIORITY = ("button", "a", "input", "select", "textarea")

# --- Ingress: pre-checked / default-on form state (Target 3) ---
# Only these control types are eligible — never radio/select, since those
# usually *require* some default and flagging them over-fires constantly
# (a shipping-method radio, a country <select>).
INGRESS_FLAGGABLE_TOGGLE_TYPES = ("checkbox", "toggle", "switch")

# Keyword heuristic for which pre-checked toggles are worth flagging.
# Same honest limitation as INGRESS_INJECTION_KEYWORDS: a toggle with
# unrelated wording for the same effect will not be caught.
INGRESS_CONSENT_KEYWORDS = (
    "market",
    "newsletter",
    "share",
    "data",
    "optin",
    "opt-in",
    "subscribe",
    "addon",
    "add-on",
    "warranty",
    "insurance",
    "autorenew",
    "auto-renew",
    "consent",
    "tracking",
    "promo",
)

# Rapid background mutation flooding ("dummy DOM diffs"), the second half of
# Target 4 — distinct from the static node/token budget above. Needs a live
# MutationObserver count from the connector layer; this is just the cutoff.
INGRESS_MUTATION_RATE_THRESHOLD = 50.0  # mutations/sec

# Raw DOM flood signals (Target 4, F-E): evaluated BEFORE any caps, from a
# lightweight element-count plus text-length probe. These complement the
# interactables-budget check in the engine: a page can flood with plain
# non-interactive nodes or raw text without adding interactables.
# Thresholds are heuristic floors chosen so synthetic fixtures separate
# cleanly: fixtures/flood.html ships ~720 filler elements and must BLOCK,
# while benign pages (wiki, login, cookie banner, ~tens of elements and a
# few hundred chars) stay ALLOW. Tune from real data when available.
INGRESS_RAW_ELEMENT_COUNT_THRESHOLD = 500
INGRESS_RAW_TEXT_CHARS_THRESHOLD = INGRESS_TOKEN_BUDGET_TRIGGER * INGRESS_CHARS_PER_TOKEN_ESTIMATE

# --- Egress: overlay / hit-target mismatch (Target 2) ---
EGRESS_OVERLAY_OPACITY_THRESHOLD = 0.1
EGRESS_OVERLAY_ZINDEX_THRESHOLD = 9000

# Z-index above this is treated as absurd even for an opaque top element,
# so it stays BLOCK rather than dropping to ESCALATE as a plausible modal.
# Rationale: ordinary modal, dialog, and cookie-banner stacks live well
# below this (typically tens to low thousands; the 9000 decoy threshold
# above already covers aggressive ones). A top element past 100000 with a
# mismatched ref looks engineered to sit above everything, not like page UI.
# Opaque top elements at or below this ceiling with opacity >= 0.1 are
# plausible modals and get ESCALATE, not BLOCK. Near-zero-opacity top
# elements (opacity < 0.1 with pointer events enabled) are always BLOCK.
EGRESS_ABSURD_ZINDEX_THRESHOLD = 100000

# --- Egress: cart / checkout sneaking (Target 5) ---
# No threshold needed — this is exact-set arithmetic, not a heuristic.
