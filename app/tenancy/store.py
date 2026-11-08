"""Workspace, member and API key storage: the contract plus an in-memory implementation."""

from __future__ import annotations

import threading
from dataclasses import replace
from datetime import UTC, datetime
from typing import Protocol

from app.tenancy.schemas import (
    ApiKeyInfo,
    ConflictError,
    Member,
    NotFoundError,
    Role,
    User,
    Workspace,
    generate_api_key,
    hash_api_key,
    normalize_email,
    parse_api_key_prefix,
    slugify,
)


class TenancyStore(Protocol):
    def create_workspace(
        self, name: str, owner_email: str, owner_external_id: str | None = None
    ) -> Workspace: ...

    def ensure_default_workspace(self) -> Workspace: ...

    def get_workspace(self, workspace_id: int) -> Workspace | None: ...

    def set_plan(self, workspace_id: int, plan: str) -> Workspace: ...

    def get_or_create_user(self, email: str, external_id: str | None = None) -> User: ...

    def workspaces_for_user(self, user_id: int) -> tuple[tuple[Workspace, Role], ...]: ...

    def role_of(self, workspace_id: int, user_id: int) -> Role | None: ...

    def list_members(self, workspace_id: int) -> tuple[Member, ...]: ...

    def add_member(self, workspace_id: int, email: str, role: Role) -> Member: ...

    def remove_member(self, workspace_id: int, user_id: int) -> None: ...

    def create_api_key(self, workspace_id: int, name: str) -> tuple[ApiKeyInfo, str]: ...

    def authenticate_api_key(self, plaintext: str) -> ApiKeyInfo | None: ...

    def list_api_keys(self, workspace_id: int) -> tuple[ApiKeyInfo, ...]: ...

    def revoke_api_key(self, workspace_id: int, key_id: int) -> None: ...


class InMemoryTenancyStore:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._workspaces: dict[int, Workspace] = {}
        self._users: dict[int, User] = {}
        self._members: dict[tuple[int, int], Role] = {}
        self._keys: dict[int, tuple[ApiKeyInfo, str]] = {}
        self._ids = {"workspace": 0, "user": 0, "key": 0}

    def _next(self, kind: str) -> int:
        self._ids[kind] += 1
        return self._ids[kind]

    def _unique_slug(self, name: str) -> str:
        base = slugify(name)
        taken = {w.slug for w in self._workspaces.values()}
        slug, counter = base, 2
        while slug in taken:
            slug, counter = f"{base}-{counter}", counter + 1
        return slug

    def create_workspace(
        self, name: str, owner_email: str, owner_external_id: str | None = None
    ) -> Workspace:
        if not name.strip() or len(name.strip()) > 120:
            raise ValueError("workspace name must be 1-120 characters")
        with self._lock:
            owner = self.get_or_create_user(owner_email, owner_external_id)
            workspace = Workspace(
                self._next("workspace"),
                name.strip(),
                self._unique_slug(name),
                "free",
                datetime.now(UTC),
            )
            self._workspaces[workspace.id] = workspace
            self._members[(workspace.id, owner.id)] = Role.OWNER
            return workspace

    def ensure_default_workspace(self) -> Workspace:
        with self._lock:
            for workspace in self._workspaces.values():
                if workspace.slug == "default":
                    return workspace
            workspace = Workspace(
                self._next("workspace"), "Default", "default", "free", datetime.now(UTC)
            )
            self._workspaces[workspace.id] = workspace
            return workspace

    def get_workspace(self, workspace_id: int) -> Workspace | None:
        return self._workspaces.get(workspace_id)

    def set_plan(self, workspace_id: int, plan: str) -> Workspace:
        from app.billing.plans import plan_for

        plan_for(plan)
        with self._lock:
            workspace = self._require_workspace(workspace_id)
            updated = replace(workspace, plan=plan)
            self._workspaces[workspace_id] = updated
            return updated

    def _require_workspace(self, workspace_id: int) -> Workspace:
        workspace = self._workspaces.get(workspace_id)
        if workspace is None:
            raise NotFoundError(f"workspace {workspace_id} does not exist")
        return workspace

    def get_or_create_user(self, email: str, external_id: str | None = None) -> User:
        normalized = normalize_email(email)
        with self._lock:
            for user in self._users.values():
                if user.email == normalized or (external_id and user.external_id == external_id):
                    if external_id and user.external_id is None:
                        user = replace(user, external_id=external_id)
                        self._users[user.id] = user
                    return user
            user = User(self._next("user"), normalized, external_id)
            self._users[user.id] = user
            return user

    def workspaces_for_user(self, user_id: int) -> tuple[tuple[Workspace, Role], ...]:
        with self._lock:
            return tuple(
                (self._workspaces[wid], role)
                for (wid, uid), role in sorted(self._members.items())
                if uid == user_id
            )

    def role_of(self, workspace_id: int, user_id: int) -> Role | None:
        return self._members.get((workspace_id, user_id))

    def list_members(self, workspace_id: int) -> tuple[Member, ...]:
        with self._lock:
            self._require_workspace(workspace_id)
            return tuple(
                Member(uid, self._users[uid].email, role)
                for (wid, uid), role in sorted(self._members.items())
                if wid == workspace_id
            )

    def add_member(self, workspace_id: int, email: str, role: Role) -> Member:
        with self._lock:
            self._require_workspace(workspace_id)
            user = self.get_or_create_user(email)
            if (workspace_id, user.id) in self._members:
                raise ConflictError(f"{user.email} is already a member")
            self._members[(workspace_id, user.id)] = role
            return Member(user.id, user.email, role)

    def remove_member(self, workspace_id: int, user_id: int) -> None:
        with self._lock:
            role = self._members.get((workspace_id, user_id))
            if role is None:
                raise NotFoundError("that user is not a member")
            owners = [
                k for k, r in self._members.items() if k[0] == workspace_id and r is Role.OWNER
            ]
            if role is Role.OWNER and len(owners) == 1:
                raise ConflictError("a workspace needs at least one owner")
            del self._members[(workspace_id, user_id)]

    def create_api_key(self, workspace_id: int, name: str) -> tuple[ApiKeyInfo, str]:
        if not name.strip() or len(name.strip()) > 120:
            raise ValueError("key name must be 1-120 characters")
        with self._lock:
            self._require_workspace(workspace_id)
            prefix, plaintext, digest = generate_api_key()
            info = ApiKeyInfo(
                self._next("key"), workspace_id, name.strip(), prefix, datetime.now(UTC)
            )
            self._keys[info.id] = (info, digest)
            return info, plaintext

    def authenticate_api_key(self, plaintext: str) -> ApiKeyInfo | None:
        prefix = parse_api_key_prefix(plaintext)
        if prefix is None:
            return None
        digest = hash_api_key(plaintext)
        with self._lock:
            for key_id, (info, stored) in self._keys.items():
                if info.prefix == prefix and stored == digest and info.revoked_at is None:
                    updated = replace(info, last_used_at=datetime.now(UTC))
                    self._keys[key_id] = (updated, stored)
                    return updated
        return None

    def list_api_keys(self, workspace_id: int) -> tuple[ApiKeyInfo, ...]:
        with self._lock:
            return tuple(
                info for info, _ in self._keys.values() if info.workspace_id == workspace_id
            )

    def revoke_api_key(self, workspace_id: int, key_id: int) -> None:
        with self._lock:
            entry = self._keys.get(key_id)
            if entry is None or entry[0].workspace_id != workspace_id:
                raise NotFoundError(f"api key {key_id} does not exist")
            info, digest = entry
            if info.revoked_at is None:
                self._keys[key_id] = (replace(info, revoked_at=datetime.now(UTC)), digest)
