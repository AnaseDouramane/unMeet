"""PostgreSQL implementation of :class:`app.tenancy.store.TenancyStore`."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.billing.plans import plan_for
from app.database.models import (
    ApiKeyModel,
    MembershipModel,
    UserModel,
    WorkspaceModel,
)
from app.database.session import SessionLocal
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


class TenancyRepository:
    def __init__(self, session_factory: Callable[[], Session] = SessionLocal) -> None:
        self._session_factory = session_factory

    # -- workspaces -------------------------------------------------------------------------

    def create_workspace(
        self, name: str, owner_email: str, owner_external_id: str | None = None
    ) -> Workspace:
        if not name.strip() or len(name.strip()) > 120:
            raise ValueError("workspace name must be 1-120 characters")
        with self._session_factory() as session:
            owner = self._get_or_create_user(session, owner_email, owner_external_id)
            model = WorkspaceModel(
                name=name.strip(), slug=self._unique_slug(session, name), plan="free"
            )
            session.add(model)
            session.flush()
            session.add(
                MembershipModel(workspace_id=model.id, user_id=owner.id, role=Role.OWNER.value)
            )
            session.commit()
            session.refresh(model)
            return _workspace(model)

    def ensure_default_workspace(self) -> Workspace:
        with self._session_factory() as session:
            model = session.scalar(select(WorkspaceModel).where(WorkspaceModel.slug == "default"))
            if model is None:
                model = WorkspaceModel(name="Default", slug="default", plan="free")
                session.add(model)
                try:
                    session.commit()
                except IntegrityError:  # created concurrently
                    session.rollback()
                    model = session.scalar(
                        select(WorkspaceModel).where(WorkspaceModel.slug == "default")
                    )
                else:
                    session.refresh(model)
            assert model is not None
            return _workspace(model)

    def get_workspace(self, workspace_id: int) -> Workspace | None:
        with self._session_factory() as session:
            model = session.get(WorkspaceModel, workspace_id)
            return None if model is None else _workspace(model)

    def set_plan(self, workspace_id: int, plan: str) -> Workspace:
        plan_for(plan)
        with self._session_factory() as session:
            model = session.get(WorkspaceModel, workspace_id)
            if model is None:
                raise NotFoundError(f"workspace {workspace_id} does not exist")
            model.plan = plan
            session.commit()
            session.refresh(model)
            return _workspace(model)

    @staticmethod
    def _unique_slug(session: Session, name: str) -> str:
        base = slugify(name)
        slug, counter = base, 2
        while session.scalar(select(WorkspaceModel.id).where(WorkspaceModel.slug == slug)):
            slug, counter = f"{base}-{counter}", counter + 1
        return slug

    # -- users and members ------------------------------------------------------------------

    def get_or_create_user(self, email: str, external_id: str | None = None) -> User:
        with self._session_factory() as session:
            user = self._get_or_create_user(session, email, external_id)
            session.commit()
            return user

    @staticmethod
    def _get_or_create_user(session: Session, email: str, external_id: str | None) -> User:
        normalized = normalize_email(email)
        condition = UserModel.email == normalized
        if external_id:
            condition = condition | (UserModel.external_id == external_id)
        model = session.scalar(select(UserModel).where(condition))
        if model is None:
            model = UserModel(email=normalized, external_id=external_id or None)
            session.add(model)
            session.flush()
        elif external_id and model.external_id is None:
            model.external_id = external_id
        return User(model.id, model.email, model.external_id)

    def workspaces_for_user(self, user_id: int) -> tuple[tuple[Workspace, Role], ...]:
        statement = (
            select(WorkspaceModel, MembershipModel.role)
            .join(MembershipModel, MembershipModel.workspace_id == WorkspaceModel.id)
            .where(MembershipModel.user_id == user_id)
            .order_by(WorkspaceModel.id)
        )
        with self._session_factory() as session:
            return tuple((_workspace(w), Role(role)) for w, role in session.execute(statement))

    def role_of(self, workspace_id: int, user_id: int) -> Role | None:
        with self._session_factory() as session:
            role = session.scalar(
                select(MembershipModel.role).where(
                    MembershipModel.workspace_id == workspace_id,
                    MembershipModel.user_id == user_id,
                )
            )
            return None if role is None else Role(role)

    def list_members(self, workspace_id: int) -> tuple[Member, ...]:
        with self._session_factory() as session:
            if session.get(WorkspaceModel, workspace_id) is None:
                raise NotFoundError(f"workspace {workspace_id} does not exist")
            statement = (
                select(UserModel.id, UserModel.email, MembershipModel.role)
                .join(MembershipModel, MembershipModel.user_id == UserModel.id)
                .where(MembershipModel.workspace_id == workspace_id)
                .order_by(UserModel.id)
            )
            return tuple(
                Member(uid, email, Role(role)) for uid, email, role in session.execute(statement)
            )

    def add_member(self, workspace_id: int, email: str, role: Role) -> Member:
        with self._session_factory() as session:
            if session.get(WorkspaceModel, workspace_id) is None:
                raise NotFoundError(f"workspace {workspace_id} does not exist")
            user = self._get_or_create_user(session, email, None)
            session.add(
                MembershipModel(workspace_id=workspace_id, user_id=user.id, role=role.value)
            )
            try:
                session.commit()
            except IntegrityError as error:
                session.rollback()
                raise ConflictError(f"{user.email} is already a member") from error
            return Member(user.id, user.email, role)

    def remove_member(self, workspace_id: int, user_id: int) -> None:
        with self._session_factory() as session:
            membership = session.get(MembershipModel, (workspace_id, user_id))
            if membership is None:
                raise NotFoundError("that user is not a member")
            if membership.role == Role.OWNER.value:
                owners = session.scalar(
                    select(func.count())
                    .select_from(MembershipModel)
                    .where(
                        MembershipModel.workspace_id == workspace_id,
                        MembershipModel.role == Role.OWNER.value,
                    )
                )
                if owners == 1:
                    raise ConflictError("a workspace needs at least one owner")
            session.delete(membership)
            session.commit()

    # -- API keys ---------------------------------------------------------------------------

    def create_api_key(self, workspace_id: int, name: str) -> tuple[ApiKeyInfo, str]:
        if not name.strip() or len(name.strip()) > 120:
            raise ValueError("key name must be 1-120 characters")
        with self._session_factory() as session:
            if session.get(WorkspaceModel, workspace_id) is None:
                raise NotFoundError(f"workspace {workspace_id} does not exist")
            prefix, plaintext, digest = generate_api_key()
            model = ApiKeyModel(
                workspace_id=workspace_id, name=name.strip(), prefix=prefix, key_hash=digest
            )
            session.add(model)
            session.commit()
            session.refresh(model)
            return _key(model), plaintext

    def authenticate_api_key(self, plaintext: str) -> ApiKeyInfo | None:
        prefix = parse_api_key_prefix(plaintext)
        if prefix is None:
            return None
        with self._session_factory() as session:
            model = session.scalar(
                select(ApiKeyModel).where(
                    ApiKeyModel.prefix == prefix,
                    ApiKeyModel.key_hash == hash_api_key(plaintext),
                    ApiKeyModel.revoked_at.is_(None),
                )
            )
            if model is None:
                return None
            session.execute(
                update(ApiKeyModel)
                .where(ApiKeyModel.id == model.id)
                .values(last_used_at=datetime.now(UTC))
            )
            session.commit()
            session.refresh(model)
            return _key(model)

    def list_api_keys(self, workspace_id: int) -> tuple[ApiKeyInfo, ...]:
        with self._session_factory() as session:
            models = session.scalars(
                select(ApiKeyModel)
                .where(ApiKeyModel.workspace_id == workspace_id)
                .order_by(ApiKeyModel.id)
            )
            return tuple(_key(model) for model in models)

    def revoke_api_key(self, workspace_id: int, key_id: int) -> None:
        with self._session_factory() as session:
            model = session.get(ApiKeyModel, key_id)
            if model is None or model.workspace_id != workspace_id:
                raise NotFoundError(f"api key {key_id} does not exist")
            if model.revoked_at is None:
                model.revoked_at = datetime.now(UTC)
                session.commit()


def _workspace(model: WorkspaceModel) -> Workspace:
    return Workspace(model.id, model.name, model.slug, model.plan, model.created_at)


def _key(model: ApiKeyModel) -> ApiKeyInfo:
    return ApiKeyInfo(
        model.id,
        model.workspace_id,
        model.name,
        model.prefix,
        model.created_at,
        model.last_used_at,
        model.revoked_at,
    )
