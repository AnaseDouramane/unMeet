from __future__ import annotations

import re
import secrets
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from hashlib import sha256

API_KEY_PREFIX = "um"


class Role(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"

    @property
    def can_manage(self) -> bool:
        """Owners and admins manage members, keys, billing and topics; members use the inbox."""
        return self in (Role.OWNER, Role.ADMIN)


@dataclass(frozen=True)
class Workspace:
    id: int
    name: str
    slug: str
    plan: str
    created_at: datetime | None = None
    website_url: str | None = None
    product_summary: str | None = None


@dataclass(frozen=True)
class User:
    id: int
    email: str
    external_id: str | None = None


@dataclass(frozen=True)
class Member:
    user_id: int
    email: str
    role: Role


@dataclass(frozen=True)
class ApiKeyInfo:
    id: int
    workspace_id: int
    name: str
    prefix: str
    created_at: datetime | None = None
    last_used_at: datetime | None = None
    revoked_at: datetime | None = None


@dataclass(frozen=True)
class Principal:
    """Who is calling and for which workspace. ``via`` says how they authenticated."""

    workspace_id: int
    role: Role
    via: str  # "api_key" | "jwt" | "dev"
    user_id: int | None = None


class TenancyError(Exception):
    pass


class NotFoundError(TenancyError):
    pass


class ConflictError(TenancyError):
    pass


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug[:60] or "workspace"


def normalize_email(email: str) -> str:
    cleaned = email.strip().lower()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", cleaned) or len(cleaned) > 320:
        raise ValueError("a valid email address is required")
    return cleaned


def generate_api_key() -> tuple[str, str, str]:
    """Return (prefix, plaintext key, sha256 hex). The plaintext is never stored."""
    prefix = secrets.token_hex(4)
    plaintext = f"{API_KEY_PREFIX}_{prefix}_{secrets.token_urlsafe(32)}"
    return prefix, plaintext, hash_api_key(plaintext)


def hash_api_key(plaintext: str) -> str:
    # API keys are 256-bit random values, so a plain SHA-256 is enough (no password stretching).
    return sha256(plaintext.encode()).hexdigest()


def parse_api_key_prefix(plaintext: str) -> str | None:
    parts = plaintext.split("_", 2)
    if len(parts) == 3 and parts[0] == API_KEY_PREFIX and parts[1]:
        return parts[1]
    return None
