"""Machine-readable error kinds for the HTTP API (`webview_server.py` adds them as a `code` field).

Imports nothing from the pipeline, so the modules that produce refusals can use it without a cycle.
"""

from __future__ import annotations

from enum import StrEnum


class ErrorCode(StrEnum):
    NOT_FOUND = "NOT_FOUND"
    BAD_REQUEST = "BAD_REQUEST"
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    CONFLICT = "CONFLICT"
    STALE_BUILD = "STALE_BUILD"
    BIBLE_UNLOCKED = "BIBLE_UNLOCKED"
    PENDING_CORRECTIONS = "PENDING_CORRECTIONS"
    GPU_BUSY = "GPU_BUSY"
    RESOURCE_REFUSED = "RESOURCE_REFUSED"
    LICENCE_REFUSED = "LICENCE_REFUSED"
    PROJECT_BUSY = "PROJECT_BUSY"
    APPLIED_CORRECTION = "APPLIED_CORRECTION"
    JOB_NOT_CANCELLABLE = "JOB_NOT_CANCELLABLE"
    PAYLOAD_TOO_LARGE = "PAYLOAD_TOO_LARGE"
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"
    INTERNAL = "INTERNAL"


class Refusal(str):
    """A refusal message that remembers its kind.

    It is a `str` with the exact wording the refusal functions always returned, so the CLI and every caller that
    prints or compares it are unchanged; the server reads `.code` instead of guessing the kind from the text.
    """

    code: ErrorCode

    def __new__(cls, message: str, code: ErrorCode) -> Refusal:
        obj = super().__new__(cls, message)
        obj.code = code
        return obj
