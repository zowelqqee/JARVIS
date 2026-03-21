"""Confirmation gate interface for JARVIS MVP."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from types.confirmation_request import ConfirmationRequest, ConfirmationResult


def request_confirmation(boundary: ConfirmationRequest) -> ConfirmationResult:
    """Request explicit confirmation for a command-level or step-level boundary."""
    raise NotImplementedError("Confirmation handling is not implemented in MVP skeleton.")

