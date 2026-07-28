"""Opaque storage identifier generation (Requirements 10.13, 10.19, 10.20).

The primary generator and the fallback generator use independent randomness
sources so a failure specific to one mechanism does not also break the
other; neither is derived from client-controlled input (filename or any
other client-supplied path content), and neither reveals a predictable
sequence.
"""

from __future__ import annotations

import secrets
import uuid
from collections.abc import Callable

from app.domains.images.errors import OpaqueKeyGenerationError

_KEY_BYTE_LENGTH = 16


def generate_primary_opaque_key() -> str:
    """Primary generator: a cryptographically random hex token."""
    return secrets.token_hex(_KEY_BYTE_LENGTH)


def generate_fallback_opaque_key() -> str:
    """Fallback generator: an independent randomness source (uuid4) so a
    defect in the primary generator's source does not also affect this one."""
    return uuid.uuid4().hex


def generate_opaque_key(
    *,
    primary_generator: Callable[[], str] = generate_primary_opaque_key,
    fallback_generator: Callable[[], str] = generate_fallback_opaque_key,
) -> str:
    """Generate an opaque key via `primary_generator`, falling back to
    `fallback_generator` if the primary raises, and rejecting the upload
    (raising `OpaqueKeyGenerationError`) if both fail.

    The generator parameters default to the two independent production
    generators; tests substitute a failing callable to exercise the
    fallback and reject-if-both-fail paths without special-casing
    production behavior.
    """
    try:
        return primary_generator()
    except Exception:
        try:
            return fallback_generator()
        except Exception as fallback_exc:
            raise OpaqueKeyGenerationError() from fallback_exc
