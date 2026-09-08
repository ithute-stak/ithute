from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import (
    Branch,
    CompanySetting,
    PasswordHistory,
    Permission,
    Role,
    RolePermission,
    Site,
    User,
    UserRoleAssignment,
    UserSession,
)

SESSION_COOKIE = "buildtrack_session"
PASSWORD_HASHER = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2, hash_len=32, salt_len=16)

DEFAULT_SECURITY_POLICY: dict[str, int | bool] = {
    "minimum_password_length": 12,
    "require_uppercase": True,
    "require_lowercase": True,
    "require_number": True,
    "require_special": True,
    "password_history": 5,
    "lockout_attempts": 5,
    "lockout_minutes": 15,
    "session_hours": 12,
    "idle_minutes": 60,
    "reset_token_minutes": 30,
    "max_active_sessions": 5,
}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(value: datetime) -> datetime:
    """Normalise database datetimes returned without timezone metadata (notably SQLite)."""
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_token() -> str:
    return secrets.token_urlsafe(48)


def normalize_username(value: str) -> str:
    return value.strip().lower()


def normalize_email(value: str) -> str:
    return value.strip().lower()


def security_policy(db: Session, company_id: int) -> dict[str, int | bool]:
    row = db.scalar(
        select(CompanySetting).where(
            CompanySetting.company_id == company_id,
            CompanySetting.key == "security_policy",
        )
    )
    policy = dict(DEFAULT_SECURITY_POLICY)
    if row and isinstance(row.value, dict):
        for key, default in DEFAULT_SECURITY_POLICY.items():
            if key in row.value and isinstance(row.value[key], type(default)):
                policy[key] = row.value[key]
    return policy


def validate_password(password: str, policy: dict[str, int | bool], *, identity: str | None = None) -> None:
    errors: list[str] = []
    minimum = int(policy["minimum_password_length"])
    if len(password) < minimum:
        errors.append(f"at least {minimum} characters")
    if policy["require_uppercase"] and not any(char.isupper() for char in password):
        errors.append("one uppercase letter")
    if policy["require_lowercase"] and not any(char.islower() for char in password):
        errors.append("one lowercase letter")
    if policy["require_number"] and not any(char.isdigit() for char in password):
        errors.append("one number")
    if policy["require_special"] and not any(not char.isalnum() for char in password):
        errors.append("one special character")
    if identity and len(identity) >= 3 and identity.lower() in password.lower():
        errors.append("must not contain the username or email")
    if errors:
        raise HTTPException(status_code=422, detail="Password must contain " + ", ".join(errors))


def hash_password(password: str) -> str:
    return PASSWORD_HASHER.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return PASSWORD_HASHER.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def enforce_password_history(db: Session, user: User, password: str, history_count: int) -> None:
    if verify_password(user.password_hash, password):
        raise HTTPException(status_code=422, detail="New password must be different from the current password")
    if history_count <= 0:
        return
    history = db.scalars(
        select(PasswordHistory)
        .where(PasswordHistory.user_id == user.id)
        .order_by(PasswordHistory.id.desc())
        .limit(history_count)
    ).all()
    if any(verify_password(item.password_hash, password) for item in history):
        raise HTTPException(status_code=422, detail=f"Password cannot reuse the last {history_count} passwords")


def replace_password(db: Session, user: User, password: str, *, must_change: bool = False) -> None:
    policy = security_policy(db, user.company_id)
    validate_password(password, policy, identity=user.username)
    enforce_password_history(db, user, password, int(policy["password_history"]))
    db.add(PasswordHistory(user_id=user.id, password_hash=user.password_hash))
    user.password_hash = hash_password(password)
    user.password_changed_at = utcnow()
    user.must_change_password = must_change
    keep = int(policy["password_history"]) + 2
    stale_ids = list(
        db.scalars(
            select(PasswordHistory.id)
            .where(PasswordHistory.user_id == user.id)
            .order_by(PasswordHistory.id.desc())
            .offset(keep)
        ).all()
    )
    if stale_ids:
        for item in db.scalars(select(PasswordHistory).where(PasswordHistory.id.in_(stale_ids))).all():
            db.delete(item)


def create_session(db: Session, user: User, request: Request) -> tuple[UserSession, str]:
    policy = security_policy(db, user.company_id)
    now = utcnow()
    active = db.scalars(
        select(UserSession)
        .where(
            UserSession.user_id == user.id,
            UserSession.revoked_at.is_(None),
            UserSession.expires_at > now,
        )
        .order_by(UserSession.created_at.asc())
    ).all()
    maximum = int(policy["max_active_sessions"])
    while len(active) >= maximum and active:
        oldest = active.pop(0)
        oldest.revoked_at = now
        oldest.revoked_by = "security-policy"
        oldest.revoke_reason = "Maximum active sessions exceeded"

    raw_token = new_token()
    row = UserSession(
        user_id=user.id,
        token_hash=token_hash(raw_token),
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent", "")[:500] or None,
        created_at=now,
        last_seen_at=now,
        expires_at=now + timedelta(hours=int(policy["session_hours"])),
    )
    db.add(row)
    db.flush()
    return row, raw_token


def revoke_user_sessions(db: Session, user_id: int, *, actor: str, reason: str, except_session_id: int | None = None) -> int:
    now = utcnow()
    statement = select(UserSession).where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
    if except_session_id is not None:
        statement = statement.where(UserSession.id != except_session_id)
    sessions = db.scalars(statement).all()
    for session in sessions:
        session.revoked_at = now
        session.revoked_by = actor
        session.revoke_reason = reason
    return len(sessions)


@dataclass(frozen=True)
class ScopeGrant:
    permission: str
    branch_id: int | None
    site_id: int | None


@dataclass
class Principal:
    user: User
    session: UserSession
    grants: list[ScopeGrant]

    @property
    def permission_codes(self) -> set[str]:
        return {grant.permission for grant in self.grants}

    def has_permission_anywhere(self, permission: str) -> bool:
        return any(grant.permission == permission for grant in self.grants)

    def has_company_permission(self, permission: str) -> bool:
        return any(grant.permission == permission and grant.branch_id is None and grant.site_id is None for grant in self.grants)

    def can(self, permission: str, *, branch_id: int | None = None, site_id: int | None = None) -> bool:
        relevant = [grant for grant in self.grants if grant.permission == permission]
        if any(grant.branch_id is None and grant.site_id is None for grant in relevant):
            return True
        if site_id is not None:
            return any(grant.site_id == site_id or (grant.site_id is None and grant.branch_id == branch_id) for grant in relevant)
        if branch_id is not None:
            return any(grant.branch_id == branch_id and grant.site_id is None for grant in relevant)
        return False

    def visible_branch_ids(self, permission: str) -> set[int] | None:
        relevant = [grant for grant in self.grants if grant.permission == permission]
        if any(grant.branch_id is None and grant.site_id is None for grant in relevant):
            return None
        return {grant.branch_id for grant in relevant if grant.branch_id is not None}

    def visible_site_ids(self, permission: str) -> set[int] | None:
        relevant = [grant for grant in self.grants if grant.permission == permission]
        if any(grant.branch_id is None and grant.site_id is None for grant in relevant):
            return None
        return {grant.site_id for grant in relevant if grant.site_id is not None}


def _raw_session_token(request: Request) -> str | None:
    cookie = request.cookies.get(SESSION_COOKIE)
    if cookie:
        return cookie
    authorization = request.headers.get("authorization", "")
    if authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return None


def _active_assignments(db: Session, user: User) -> list[UserRoleAssignment]:
    now = utcnow()
    return db.scalars(
        select(UserRoleAssignment)
        .join(Role, Role.id == UserRoleAssignment.role_id)
        .where(
            UserRoleAssignment.user_id == user.id,
            Role.company_id == user.company_id,
            Role.is_active.is_(True),
            or_(UserRoleAssignment.valid_from.is_(None), UserRoleAssignment.valid_from <= now),
            or_(UserRoleAssignment.valid_until.is_(None), UserRoleAssignment.valid_until >= now),
        )
        .order_by(UserRoleAssignment.id)
    ).all()


def build_principal(db: Session, user: User, session: UserSession) -> Principal:
    grants: list[ScopeGrant] = []
    assignments = _active_assignments(db, user)
    for assignment in assignments:
        role = db.get(Role, assignment.role_id)
        if not role:
            continue
        permission_codes = db.scalars(
            select(Permission.code)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .where(RolePermission.role_id == role.id)
        ).all()
        for permission in permission_codes:
            if role.scope_level == "company":
                grants.append(ScopeGrant(permission=permission, branch_id=None, site_id=None))
            elif role.scope_level == "branch" and assignment.branch_id is not None:
                grants.append(ScopeGrant(permission=permission, branch_id=assignment.branch_id, site_id=None))
            elif role.scope_level == "site" and assignment.site_id is not None:
                grants.append(ScopeGrant(permission=permission, branch_id=assignment.branch_id, site_id=assignment.site_id))
    return Principal(user=user, session=session, grants=grants)


def current_principal(request: Request, db: Session = Depends(get_db)) -> Principal:
    cached = getattr(request.state, "principal", None)
    if cached is not None:
        return cached
    raw_token = _raw_session_token(request)
    if not raw_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    now = utcnow()
    session = db.scalar(select(UserSession).where(UserSession.token_hash == token_hash(raw_token)))
    if not session or session.revoked_at is not None or as_utc(session.expires_at) <= now:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session has expired")
    user = db.get(User, session.user_id)
    if not user or not user.is_active or user.status not in {"active", "locked"}:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User account is not active")
    policy = security_policy(db, user.company_id)
    if as_utc(session.last_seen_at) + timedelta(minutes=int(policy["idle_minutes"])) <= now:
        session.revoked_at = now
        session.revoked_by = "security-policy"
        session.revoke_reason = "Idle timeout"
        db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired due to inactivity")
    if user.locked_until and as_utc(user.locked_until) > now:
        raise HTTPException(status_code=status.HTTP_423_LOCKED, detail="Account is temporarily locked")
    if user.locked_until and as_utc(user.locked_until) <= now:
        user.locked_until = None
        user.failed_login_attempts = 0
        user.status = "active"
    if (now - as_utc(session.last_seen_at)).total_seconds() >= 60:
        session.last_seen_at = now
        db.commit()
    principal = build_principal(db, user, session)
    request.state.principal = principal
    return principal


def require_permission(permission: str, *, company_scope: bool = False) -> Callable:
    def dependency(principal: Principal = Depends(current_principal)) -> Principal:
        allowed = principal.has_company_permission(permission) if company_scope else principal.has_permission_anywhere(permission)
        if not allowed:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Permission required: {permission}")
        return principal

    return dependency


def validate_role_assignment_scope(db: Session, user: User, role: Role, branch_id: int | None, site_id: int | None) -> None:
    if role.company_id != user.company_id:
        raise HTTPException(status_code=422, detail="Role does not belong to the user's company")
    if role.scope_level == "company":
        if branch_id is not None or site_id is not None:
            raise HTTPException(status_code=422, detail="Company-scoped roles cannot be restricted to a branch or site")
        return
    if role.scope_level == "branch":
        if branch_id is None or site_id is not None:
            raise HTTPException(status_code=422, detail="Branch-scoped roles require a branch and cannot specify a site")
        branch = db.get(Branch, branch_id)
        if not branch or branch.company_id != user.company_id:
            raise HTTPException(status_code=422, detail="Branch does not belong to the user's company")
        return
    if role.scope_level == "site":
        if site_id is None:
            raise HTTPException(status_code=422, detail="Site-scoped roles require a site")
        site = db.get(Site, site_id)
        if not site or site.company_id != user.company_id:
            raise HTTPException(status_code=422, detail="Site does not belong to the user's company")
        if branch_id is not None and site.branch_id != branch_id:
            raise HTTPException(status_code=422, detail="Site does not belong to the selected branch")
        return
    raise HTTPException(status_code=422, detail="Unsupported role scope")
