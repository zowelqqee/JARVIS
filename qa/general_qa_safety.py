"""Policy helpers for broader open-domain question answering."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class GeneralQaSafetyPolicy:
    """Stable policy summary for one open-domain question."""

    policy_tags: tuple[str, ...] = ()
    response_mode: str = "answer"
    warning_hint: str | None = None
    guidance_lines: tuple[str, ...] = ()


def inspect_general_qa_safety(raw_input: str) -> GeneralQaSafetyPolicy:
    """Return the safety/uncertainty policy that should shape one answer."""
    lowered = str(raw_input or "").strip().lower()
    if not lowered:
        return GeneralQaSafetyPolicy()

    tags: list[str] = []
    guidance: list[str] = []
    response_mode = "answer"
    warning_hint: str | None = None

    if _looks_like_self_harm_request(lowered):
        tags.append("self_harm")
        guidance.append("Refuse self-harm facilitation and avoid providing instructions, methods, or optimization.")
        return GeneralQaSafetyPolicy(
            policy_tags=tuple(tags),
            response_mode="refusal",
            guidance_lines=tuple(guidance),
        )

    if _looks_like_illegal_or_dangerous_request(lowered):
        tags.append("illegal_or_dangerous")
        guidance.append("Refuse operational wrongdoing assistance and avoid step-by-step instructions or bypass details.")
        return GeneralQaSafetyPolicy(
            policy_tags=tuple(tags),
            response_mode="refusal",
            guidance_lines=tuple(guidance),
        )

    if _looks_like_medical_sensitive_request(lowered):
        tags.append("medical_sensitive")
        response_mode = "bounded_answer"
        warning_hint = "This is general information, not medical advice."
        guidance.append("Give only high-level general information, avoid diagnosis, prescriptions, dosing, or certainty.")

    if _looks_like_legal_sensitive_request(lowered):
        tags.append("legal_sensitive")
        response_mode = "bounded_answer"
        warning_hint = warning_hint or "This is general information, not legal advice."
        guidance.append("Give only general legal information, avoid definitive legal instructions or representation claims.")

    if _looks_like_financial_sensitive_request(lowered):
        tags.append("financial_sensitive")
        response_mode = "bounded_answer"
        warning_hint = warning_hint or "This is general information, not financial advice."
        guidance.append("Give only general financial information, avoid guarantees, allocations, or personalized investment directives.")

    if _looks_like_temporally_unstable_request(lowered):
        tags.append("temporally_unstable")
        if response_mode == "answer":
            response_mode = "bounded_answer"
        if warning_hint is None:
            warning_hint = "This answer may be out of date for changing public facts."
        guidance.append("Acknowledge that changing public facts may be stale without live web verification.")

    return GeneralQaSafetyPolicy(
        policy_tags=tuple(tags),
        response_mode=response_mode,
        warning_hint=warning_hint,
        guidance_lines=tuple(guidance),
    )


def policy_tags_text(policy: GeneralQaSafetyPolicy) -> str | None:
    """Return a stable comma-separated tag summary for metadata/debug output."""
    tags = [str(tag).strip() for tag in tuple(policy.policy_tags or ()) if str(tag).strip()]
    if not tags:
        return None
    return ",".join(tags)


def _looks_like_self_harm_request(text: str) -> bool:
    harm_terms = (
        "kill myself",
        "suicide",
        "end my life",
        "hurt myself",
        "cut myself",
        "overdose",
    )
    request_terms = (
        "how",
        "best way",
        "painless",
        "quickest",
        "should i",
        "tell me",
        "explain",
    )
    return any(term in text for term in harm_terms) and any(term in text for term in request_terms)


def _looks_like_illegal_or_dangerous_request(text: str) -> bool:
    dangerous_terms = (
        "hotwire",
        "build a bomb",
        "make a bomb",
        "explosive",
        "make meth",
        "phishing",
        "malware",
        "ransomware",
        "ddos",
        "steal a car",
        "break into",
        "bypass alarm",
        "poison someone",
    )
    request_terms = (
        "how",
        "tell me",
        "explain",
        "instructions",
        "step by step",
        "guide",
        "best way",
    )
    return any(term in text for term in dangerous_terms) and any(term in text for term in request_terms)


def _looks_like_medical_sensitive_request(text: str) -> bool:
    medical_terms = (
        "diagnose",
        "diagnosis",
        "prescribe",
        "prescription",
        "dosage",
        "dose",
        "medication",
        "symptoms",
        "chest pain",
        "should i take",
        "should i stop taking",
    )
    return any(term in text for term in medical_terms)


def _looks_like_legal_sensitive_request(text: str) -> bool:
    legal_terms = (
        "legal advice",
        "lawyer",
        "lawsuit",
        "sue",
        "contract",
        "liable",
        "criminal charge",
        "eviction",
        "divorce",
        "can i legally",
    )
    return any(term in text for term in legal_terms)


def _looks_like_financial_sensitive_request(text: str) -> bool:
    financial_terms = (
        "financial advice",
        "invest",
        "investment",
        "stock should i buy",
        "portfolio",
        "retirement",
        "tax advice",
        "should i buy shares",
        "guaranteed return",
        "loan default",
    )
    return any(term in text for term in financial_terms)


def _looks_like_temporally_unstable_request(text: str) -> bool:
    terms = (
        "current ",
        "currently ",
        "today",
        "now",
        "latest",
        "recent",
        "news",
        "president",
        "prime minister",
        "ceo",
        "stock price",
        "weather",
        "score",
        "won the election",
    )
    return any(term in text for term in terms)
