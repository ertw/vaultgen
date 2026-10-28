"""Single-piece key, constructed from native gear and handle geometry."""

from dataclasses import dataclass


@dataclass(frozen=True)
class KeySpec:
    @property
    def slug(self):
        # Retain the catalog identity used by saved builds and complete sets.
        return "snap_key"

    @property
    def name(self):
        return "Key"


def build_key():
    from .key_geometry import build_key_blank
    key = build_key_blank()
    key.label = 'key'
    return key


def build_key_parts():
    """One connected printable key with its gear bottom on Z=0."""
    return {'key': build_key()}
