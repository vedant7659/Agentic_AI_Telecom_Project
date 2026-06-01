"""
Output Guardrail — Layer 2 Defence.

Scrubs the final agent response before it is shown to the user.
Catches any schema/data leakage that slipped through the input filter.

Usage:
    from guardrails.output_guard import scrub_output

    safe_text = scrub_output(raw_agent_response)
"""
import re
import logging

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Patterns to redact from output
# ---------------------------------------------------------------------------
_REDACT_RULES = [
    # Raw SQL statements
    (re.compile(
        r"(SELECT|INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE)\s+.{10,200}?(FROM|TABLE|INTO|WHERE)[^;.\n]{0,150}",
        re.IGNORECASE | re.DOTALL),
     "[SQL REDACTED]"),

    # Internal hostnames and ports
    (re.compile(r"(https?://)?(localhost|127\.0\.0\.1|0\.0\.0\.0)(:\d+)?(/\S*)?", re.IGNORECASE),
     "[INTERNAL URL REDACTED]"),

    # Stack traces / Python tracebacks
    (re.compile(r"Traceback \(most recent call last\).*?(Error|Exception)[^\n]*", re.DOTALL | re.IGNORECASE),
     "[ERROR DETAILS REDACTED]"),

    # File system paths (Windows & Unix style)
    (re.compile(r"[A-Za-z]:\\(?:[^\\\n\"'<>]+\\){1,}[^\\\n\"'<>]*", re.IGNORECASE),
     "[PATH REDACTED]"),
    (re.compile(r"/(?:home|usr|var|etc|tmp|app|code|workspace)/[\w./\-]+", re.IGNORECASE),
     "[PATH REDACTED]"),

    # Database file references
    (re.compile(r"\b\w+\.db\b", re.IGNORECASE),
     "[DB FILE REDACTED]"),

    # PRAGMA / SQLite introspection outputs
    (re.compile(r"\bPRAGMA\b.{0,100}", re.IGNORECASE),
     "[PRAGMA REDACTED]"),
]

# Minimum safe response to return if the entire output is scrubbed away
_FALLBACK_RESPONSE = (
    "I'm unable to provide that information. Please contact our support team "
    "if you need further assistance."
)


def scrub_output(text: str) -> str:
    """
    Apply all redaction rules to the agent output text.
    Returns the scrubbed text. If most content is removed, returns a fallback message.
    """
    if not text or not text.strip():
        return _FALLBACK_RESPONSE

    original_length = len(text)
    scrubbed = text

    for pattern, replacement in _REDACT_RULES:
        new_text = pattern.sub(replacement, scrubbed)
        if new_text != scrubbed:
            logger.warning(
                "Guardrail [OUTPUT] redacted pattern matching: %s",
                pattern.pattern[:60]
            )
        scrubbed = new_text

    # If over 60% of content was redacted, return the fallback
    if len(scrubbed.replace("[SQL REDACTED]", "").replace("[INTERNAL URL REDACTED]", "")
                   .replace("[PATH REDACTED]", "").replace("[DB FILE REDACTED]", "")
                   .replace("[PRAGMA REDACTED]", "").replace("[ERROR DETAILS REDACTED]", "")
                   .strip()) < (original_length * 0.4):
        logger.warning("Guardrail [OUTPUT] too much content redacted — returning fallback.")
        return _FALLBACK_RESPONSE

    return scrubbed
