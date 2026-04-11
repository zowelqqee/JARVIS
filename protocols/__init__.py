"""Protocol support for named JARVIS command scenarios."""

from protocols.registry import get_protocol_by_id, match_protocol_trigger, resolve_protocol_reference

__all__ = [
    "get_protocol_by_id",
    "match_protocol_trigger",
    "resolve_protocol_reference",
]
