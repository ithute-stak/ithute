from __future__ import annotations

import secrets
import string
from datetime import datetime, timedelta
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.models import (
    AuditLog,
    Branch,
    Company,
    CompanySetting,
    PasswordResetToken,
    Permission,
    Role,
    RolePermission,
    SecurityEvent,
    Site,
    User,
    UserRoleAssignment,
    UserSession,
)
from app.security.access import (
    DEFAULT_SECURITY_POLICY,
    SESSION_COOKIE,
    Principal,
    create_session,
    current_principal,
    hash_password,
    new_token,
    normalize_email,
    normalize_username,
    replace_password,
    require_permission,
    revoke_user_sessions,
    security_policy,
    token_hash,
    utcnow,
    validate_password,
    validate_role_assignment_scope,
    verify_password,
)

router = APIRouter(prefix="/access", tags=["Phase 2 - User Access & Security"])
settings = get_settings()

PHASE2_PERMISSIONS = {
    "users.view": ("users", "view", "View user accounts and assignments"),
    "users.manage": ("users", "manage", "Create and administer user accounts and assignments"),
    "security.view": ("security", "view", "View security policy and events"),
    "security.manage": ("security", "manage", "Manage security policy, locks and password recovery"),
    "sessions.view": ("sessions", "view", "View active user sessions"),
    "sessions.manage": ("sessions", "manage", "Revoke user sessions"),
}


class AssignmentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role_id: int
    branch_id: int | None = None
    site_id: int | None = None
    is_primary: bool = False
    valid_from: datetime | None = None
    valid_until: datetime | None = None


class BootstrapAdminInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(default="admin", min_length=3, max_length=80)
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=255)
    password: str = Field(min_length=12, max_length=256)
    phone: str | None = Field(default=None, max_length=64)


class LoginInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=256)


class UserCreateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=3, max_length=80)
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=255)
    phone: str | None = Field(default=None, max_length=64)
    employee_number: str | None = Field(default=None, max_length=64)
    job_title: str | None = Field(default=None, max_length=160)
    temporary_password: str | None = Field(default=None, min_length=12, max_length=256)
    assignments: list[AssignmentInput] = Field(min_length=1)
    must_change_password: bool = True


class UserUpdateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr | None = None
    full_name: str | None = Field(default=None, min_length=2, max_length=255)
    phone: str | None = Field(default=None, max_length=64)
    employee_number: str | None = Field(default=None, max_length=64)
    job_title: str | None = Field(default=None, max_length=160)
    status: Literal["active", "suspended"] | None = None
    is_active: bool | None = None


class AssignmentReplaceInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    assignments: list[AssignmentInput] = Field(min_length=1)


class ChangePasswordInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=12, max_length=256)


class ResetConsumeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str = Field(min_length=20, max_length=500)
    new_password: str = Field(min_length=12, max_length=256)


class SecurityPolicyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    minimum_password_length: int = Field(ge=12, le=128)
    require_uppercase: bool = True
    require_lowercase: bool = True
    require_number: bool = True
    require_special: bool = True
    password_history: int = Field(ge=0, le=24)
    lockout_attempts: int = Field(ge=3, le=20)
    lockout_minutes: int = Field(ge=1, le=1440)
    session_hours: int = Field(ge=1, le=168)
    idle_minutes: int = Field(ge=5, le=1440)
    reset_token_minutes: int = Field(ge=5, le=1440)
    max_active_sessions: int = Field(ge=1, le=20)


def current_company(db: Session) -> Company:
    company = db.scalar(select(Company).order_by(Company.id).limit(1))
    if not company:
        raise HTTPException(status_code=409, detail="Complete company setup before Phase 2 access setup")
    return company


def commit(db: Session, message: str = "The requested access-control change conflicts with existing data") -> None:
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status_code=409, detail=message) from error


def client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",", 1)[0].strip()[:80]
    return request.client.host[:80] if request.client else None


def security_event(db: Session, request: Request, event_type: str, *, company_id: int | None = None, user_id: int | None = None, username: str | None = None, detail: dict[str, Any] | None = None) -> None:
    db.add(
        SecurityEvent(
            company_id=company_id,
            user_id=user_id,
            event_type=event_type,
            username_attempted=username,
            ip_address=client_ip(request),
            user_agent=request.headers.get("user-agent", "")[:500] or None,
            detail=detail or {},
        )
    )


def audit(db: Session, principal_name: str, action: str, entity_type: str, entity_id: int | str | None, *, company_id: int, detail: dict[str, Any] | None = None) -> None:
    db.add(AuditLog(company_id=company_id, actor=principal_name, action=action, entity_type=entity_type, entity_id=str(entity_id) if entity_id is not None else None, detail=detail or {}))


def set_session_cookie(response: Response, token: str, hours: int) -> None:
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        max_age=hours * 3600,
        httponly=True,
        secure=settings.environment.lower() == "production",
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/", httponly=True, samesite="lax", secure=settings.environment.lower() == "production")


def ensure_phase2_access_catalog(db: Session, company: Company) -> dict[str, Role]:
    permissions: dict[str, Permission] = {}
    for code, (module, action, description) in PHASE2_PERMISSIONS.items():
        permission = db.scalar(select(Permission).where(Permission.code == code))
        if not permission:
            permission = Permission(code=code, module=module, action=action, description=description)
            db.add(permission)
            db.flush()
        permissions[code] = permission

    roles = {role.code: role for role in db.scalars(select(Role).where(Role.company_id == company.id)).all()}
    if "ACCESS_ADMIN" not in roles:
        role = Role(company_id=company.id, code="ACCESS_ADMIN", name="Access Administrator", description="User, session and security administration", scope_level="company", is_system=True, is_active=True)
        db.add(role)
        db.flush()
        roles[role.code] = role

    grants: dict[str, set[str]] = {
        "SYSTEM_ADMIN": set(PHASE2_PERMISSIONS),
        "ACCESS_ADMIN": set(PHASE2_PERMISSIONS),
        "HQ_EXECUTIVE": {"users.view", "security.view", "sessions.view"},
    }
    for role_code, permission_codes in grants.items():
        role = roles.get(role_code)
        if not role:
            continue
        existing = set(db.scalars(select(RolePermission.permission_id).where(RolePermission.role_id == role.id)).all())
        for code in permission_codes:
            permission = permissions[code]
            if permission.id not in existing:
                db.add(RolePermission(role_id=role.id, permission_id=permission.id))
    return roles


def generated_temporary_password() -> str:
    alphabet = string.ascii_letters + string.digits + "!@#$%*-_"
    while True:
        value = "BT!" + "".join(secrets.choice(alphabet) for _ in range(15)) + "9aA"
        if any(c.isupper() for c in value) and any(c.islower() for c in value) and any(c.isdigit() for c in value):
            return value


def assignment_dict(db: Session, item: UserRoleAssignment) -> dict[str, Any]:
    role = db.get(Role, item.role_id)
    branch = db.get(Branch, item.branch_id) if item.branch_id else None
    site = db.get(Site, item.site_id) if item.site_id else None
    return {
        "id": item.id,
        "role_id": item.role_id,
        "role_code": role.code if role else None,
        "role_name": role.name if role else None,
        "scope_level": role.scope_level if role else None,
        "branch_id": item.branch_id,
        "branch_name": branch.name if branch else None,
        "site_id": item.site_id,
        "site_name": site.name if site else None,
        "is_primary": item.is_primary,
        "valid_from": item.valid_from,
        "valid_until": item.valid_until,
    }


def user_dict(db: Session, user: User) -> dict[str, Any]:
    assignments = db.scalars(select(UserRoleAssignment).where(UserRoleAssignment.user_id == user.id).order_by(UserRoleAssignment.id)).all()
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "full_name": user.full_name,
        "phone": user.phone,
        "employee_number": user.employee_number,
        "job_title": user.job_title,
        "status": user.status,
        "is_active": user.is_active,
        "must_change_password": user.must_change_password,
        "failed_login_attempts": user.failed_login_attempts,
        "locked_until": user.locked_until,
        "last_login_at": user.last_login_at,
        "last_login_ip": user.last_login_ip,
        "created_by": user.created_by,
        "created_at": user.created_at,
        "assignments": [assignment_dict(db, item) for item in assignments],
    }


def replace_assignments(db: Session, user: User, assignments: list[AssignmentInput], actor: str) -> None:
    if not assignments:
        raise HTTPException(status_code=422, detail="Every active user needs at least one role assignment")
    for old in db.scalars(select(UserRoleAssignment).where(UserRoleAssignment.user_id == user.id)).all():
        db.delete(old)
    primary_count = sum(1 for item in assignments if item.is_primary)
    if primary_count > 1:
        raise HTTPException(status_code=422, detail="Only one role assignment can be primary")
    for index, item in enumerate(assignments):
        role = db.get(Role, item.role_id)
        if not role or not role.is_active:
            raise HTTPException(status_code=422, detail="Role is invalid or inactive")
        branch_id = item.branch_id
        site_id = item.site_id
        if role.scope_level == "site" and site_id is not None and branch_id is None:
            site = db.get(Site, site_id)
            branch_id = site.branch_id if site else None
        validate_role_assignment_scope(db, user, role, branch_id, site_id)
        if item.valid_from and item.valid_until and item.valid_until <= item.valid_from:
            raise HTTPException(status_code=422, detail="Assignment valid_until must be after valid_from")
        db.add(
            UserRoleAssignment(
                user_id=user.id,
                role_id=role.id,
                branch_id=branch_id,
                site_id=site_id,
                is_primary=item.is_primary or (primary_count == 0 and index == 0),
                valid_from=item.valid_from,
                valid_until=item.valid_until,
                created_by=actor,
            )
        )


@router.get("/setup-status")
def setup_status(db: Session = Depends(get_db)) -> dict[str, Any]:
    company = db.scalar(select(Company).order_by(Company.id).limit(1))
    return {
        "company_bootstrapped": company is not None,
        "admin_bootstrapped": bool(db.scalar(select(func.count()).select_from(User))) if company else False,
        "company_name": company.name if company else None,
        "phase": 2,
    }


@router.post("/bootstrap-admin", status_code=201)
def bootstrap_admin(payload: BootstrapAdminInput, request: Request, response: Response, db: Session = Depends(get_db)) -> dict[str, Any]:
    company = current_company(db)
    if db.scalar(select(func.count()).select_from(User)):
        raise HTTPException(status_code=409, detail="The first administrator has already been created")
    roles = ensure_phase2_access_catalog(db, company)
    admin_role = roles.get("SYSTEM_ADMIN")
    if not admin_role:
        raise HTTPException(status_code=409, detail="Phase 1 System Administrator role is missing")
    policy = security_policy(db, company.id)
    validate_password(payload.password, policy, identity=payload.username)
    user = User(
        company_id=company.id,
        username=normalize_username(payload.username),
        email=normalize_email(str(payload.email)),
        full_name=payload.full_name.strip(),
        phone=payload.phone,
        password_hash=hash_password(payload.password),
        must_change_password=False,
        status="active",
        is_active=True,
        created_by="Phase 2 bootstrap",
    )
    db.add(user)
    db.flush()
    db.add(UserRoleAssignment(user_id=user.id, role_id=admin_role.id, is_primary=True, created_by="Phase 2 bootstrap"))
    if not db.scalar(select(CompanySetting).where(CompanySetting.company_id == company.id, CompanySetting.key == "security_policy")):
        db.add(CompanySetting(company_id=company.id, key="security_policy", value=dict(DEFAULT_SECURITY_POLICY), description="Phase 2 authentication and session security policy"))
    session, raw_token = create_session(db, user, request)
    security_event(db, request, "admin_bootstrap", company_id=company.id, user_id=user.id)
    audit(db, user.full_name, "access.admin_bootstrap", "user", user.id, company_id=company.id)
    commit(db)
    set_session_cookie(response, raw_token, int(policy["session_hours"]))
    return {"user": user_dict(db, user), "session_id": session.id, "message": "Phase 2 administrator created"}


@router.post("/login")
def login(payload: LoginInput, request: Request, response: Response, db: Session = Depends(get_db)) -> dict[str, Any]:
    company = current_company(db)
    identity = normalize_username(payload.username)
    user = db.scalar(select(User).where(User.company_id == company.id, or_(User.username == identity, User.email == normalize_email(payload.username))))
    policy = security_policy(db, company.id)
    now = utcnow()
    if not user:
        security_event(db, request, "login_failed_unknown_user", company_id=company.id, username=payload.username)
        db.commit()
        raise HTTPException(status_code=401, detail="Invalid username or password")
    if not user.is_active or user.status == "suspended":
        security_event(db, request, "login_blocked_inactive", company_id=company.id, user_id=user.id, username=user.username)
        db.commit()
        raise HTTPException(status_code=403, detail="Account is suspended or inactive")
    if user.locked_until and user.locked_until > now:
        security_event(db, request, "login_blocked_locked", company_id=company.id, user_id=user.id, username=user.username, detail={"locked_until": user.locked_until.isoformat()})
        db.commit()
        raise HTTPException(status_code=423, detail="Account is temporarily locked")
    if not verify_password(user.password_hash, payload.password):
        user.failed_login_attempts += 1
        locked = user.failed_login_attempts >= int(policy["lockout_attempts"])
        if locked:
            user.locked_until = now + timedelta(minutes=int(policy["lockout_minutes"]))
            user.status = "locked"
        security_event(db, request, "login_failed", company_id=company.id, user_id=user.id, username=user.username, detail={"attempt": user.failed_login_attempts, "locked": locked})
        db.commit()
        raise HTTPException(status_code=423 if locked else 401, detail="Account is temporarily locked" if locked else "Invalid username or password")

    user.failed_login_attempts = 0
    user.locked_until = None
    user.status = "active"
    user.last_login_at = now
    user.last_login_ip = client_ip(request)
    session, raw_token = create_session(db, user, request)
    security_event(db, request, "login_success", company_id=company.id, user_id=user.id, username=user.username, detail={"session_id": session.id})
    db.commit()
    set_session_cookie(response, raw_token, int(policy["session_hours"]))
    return {"user": user_dict(db, user), "session_id": session.id, "must_change_password": user.must_change_password}


@router.post("/logout", status_code=204)
def logout(response: Response, request: Request, principal: Principal = Depends(current_principal), db: Session = Depends(get_db)) -> Response:
    principal.session.revoked_at = utcnow()
    principal.session.revoked_by = principal.user.full_name
    principal.session.revoke_reason = "User logout"
    security_event(db, request, "logout", company_id=principal.user.company_id, user_id=principal.user.id, detail={"session_id": principal.session.id})
    db.commit()
    clear_session_cookie(response)
    response.status_code = 204
    return response


@router.get("/me")
def me(principal: Principal = Depends(current_principal), db: Session = Depends(get_db)) -> dict[str, Any]:
    return {"user": user_dict(db, principal.user), "permissions": sorted(principal.permission_codes), "session_id": principal.session.id}


@router.get("/context")
def access_context(principal: Principal = Depends(current_principal), db: Session = Depends(get_db)) -> dict[str, Any]:
    assignments = db.scalars(select(UserRoleAssignment).where(UserRoleAssignment.user_id == principal.user.id).order_by(UserRoleAssignment.id)).all()
    company_wide = any(item["scope_level"] == "company" for item in (assignment_dict(db, assignment) for assignment in assignments))
    branch_ids = sorted({assignment.branch_id for assignment in assignments if assignment.branch_id is not None})
    site_ids = sorted({assignment.site_id for assignment in assignments if assignment.site_id is not None})
    branches = db.scalars(select(Branch).where(Branch.company_id == principal.user.company_id, Branch.id.in_(branch_ids))).all() if branch_ids else []
    sites = db.scalars(select(Site).where(Site.company_id == principal.user.company_id, Site.id.in_(site_ids))).all() if site_ids else []
    return {
        "user": user_dict(db, principal.user),
        "permissions": sorted(principal.permission_codes),
        "company_wide": company_wide,
        "branches": [{"id": row.id, "code": row.code, "name": row.name, "district": row.district} for row in branches],
        "sites": [{"id": row.id, "branch_id": row.branch_id, "code": row.code, "name": row.name} for row in sites],
    }


@router.post("/change-password")
def change_password(payload: ChangePasswordInput, request: Request, principal: Principal = Depends(current_principal), db: Session = Depends(get_db)) -> dict[str, Any]:
    if not verify_password(principal.user.password_hash, payload.current_password):
        security_event(db, request, "password_change_failed", company_id=principal.user.company_id, user_id=principal.user.id)
        db.commit()
        raise HTTPException(status_code=422, detail="Current password is incorrect")
    replace_password(db, principal.user, payload.new_password)
    revoked = revoke_user_sessions(db, principal.user.id, actor=principal.user.full_name, reason="Password changed", except_session_id=principal.session.id)
    security_event(db, request, "password_changed", company_id=principal.user.company_id, user_id=principal.user.id, detail={"revoked_other_sessions": revoked})
    audit(db, principal.user.full_name, "access.password_change", "user", principal.user.id, company_id=principal.user.company_id)
    db.commit()
    return {"message": "Password changed", "revoked_other_sessions": revoked}


@router.get("/users")
def list_users(_: Principal = Depends(require_permission("users.view", company_scope=True)), db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    company = current_company(db)
    return [user_dict(db, user) for user in db.scalars(select(User).where(User.company_id == company.id).order_by(User.full_name)).all()]


@router.post("/users", status_code=201)
def create_user(payload: UserCreateInput, request: Request, principal: Principal = Depends(require_permission("users.manage", company_scope=True)), db: Session = Depends(get_db)) -> dict[str, Any]:
    company = current_company(db)
    temporary_password = payload.temporary_password or generated_temporary_password()
    policy = security_policy(db, company.id)
    validate_password(temporary_password, policy, identity=payload.username)
    user = User(
        company_id=company.id,
        username=normalize_username(payload.username),
        email=normalize_email(str(payload.email)),
        full_name=payload.full_name.strip(),
        phone=payload.phone,
        employee_number=payload.employee_number,
        job_title=payload.job_title,
        password_hash=hash_password(temporary_password),
        must_change_password=payload.must_change_password,
        status="active",
        is_active=True,
        created_by=principal.user.full_name,
    )
    db.add(user)
    db.flush()
    replace_assignments(db, user, payload.assignments, principal.user.full_name)
    security_event(db, request, "user_created", company_id=company.id, user_id=user.id, detail={"created_by": principal.user.id})
    audit(db, principal.user.full_name, "access.user_create", "user", user.id, company_id=company.id, detail={"username": user.username})
    commit(db, "Username or email already exists")
    return {"user": user_dict(db, user), "temporary_password": temporary_password if payload.temporary_password is None else None}


@router.patch("/users/{user_id}")
def update_user(user_id: int, payload: UserUpdateInput, request: Request, principal: Principal = Depends(require_permission("users.manage", company_scope=True)), db: Session = Depends(get_db)) -> dict[str, Any]:
    user = db.get(User, user_id)
    if not user or user.company_id != principal.user.company_id:
        raise HTTPException(status_code=404, detail="User not found")
    changes = payload.model_dump(exclude_unset=True)
    if "email" in changes and changes["email"] is not None:
        changes["email"] = normalize_email(str(changes["email"]))
    for key, value in changes.items():
        setattr(user, key, value)
    if not user.is_active or user.status == "suspended":
        revoke_user_sessions(db, user.id, actor=principal.user.full_name, reason="Account suspended or deactivated")
    security_event(db, request, "user_updated", company_id=user.company_id, user_id=user.id, detail={"fields": sorted(changes)})
    audit(db, principal.user.full_name, "access.user_update", "user", user.id, company_id=user.company_id, detail={"fields": sorted(changes)})
    commit(db, "Email already belongs to another user")
    return user_dict(db, user)


@router.put("/users/{user_id}/assignments")
def update_assignments(user_id: int, payload: AssignmentReplaceInput, request: Request, principal: Principal = Depends(require_permission("users.manage", company_scope=True)), db: Session = Depends(get_db)) -> dict[str, Any]:
    user = db.get(User, user_id)
    if not user or user.company_id != principal.user.company_id:
        raise HTTPException(status_code=404, detail="User not found")
    replace_assignments(db, user, payload.assignments, principal.user.full_name)
    security_event(db, request, "role_assignments_changed", company_id=user.company_id, user_id=user.id, detail={"assignment_count": len(payload.assignments)})
    audit(db, principal.user.full_name, "access.assignments_update", "user", user.id, company_id=user.company_id)
    commit(db)
    return user_dict(db, user)


@router.post("/users/{user_id}/unlock")
def unlock_user(user_id: int, request: Request, principal: Principal = Depends(require_permission("security.manage", company_scope=True)), db: Session = Depends(get_db)) -> dict[str, Any]:
    user = db.get(User, user_id)
    if not user or user.company_id != principal.user.company_id:
        raise HTTPException(status_code=404, detail="User not found")
    user.failed_login_attempts = 0
    user.locked_until = None
    user.status = "active"
    security_event(db, request, "account_unlocked", company_id=user.company_id, user_id=user.id, detail={"actor": principal.user.id})
    audit(db, principal.user.full_name, "access.user_unlock", "user", user.id, company_id=user.company_id)
    db.commit()
    return user_dict(db, user)


@router.post("/users/{user_id}/reset-token")
def issue_reset_token(user_id: int, request: Request, principal: Principal = Depends(require_permission("security.manage", company_scope=True)), db: Session = Depends(get_db)) -> dict[str, Any]:
    user = db.get(User, user_id)
    if not user or user.company_id != principal.user.company_id:
        raise HTTPException(status_code=404, detail="User not found")
    policy = security_policy(db, user.company_id)
    now = utcnow()
    for old in db.scalars(select(PasswordResetToken).where(PasswordResetToken.user_id == user.id, PasswordResetToken.used_at.is_(None))).all():
        old.used_at = now
    raw_token = new_token()
    expires_at = now + timedelta(minutes=int(policy["reset_token_minutes"]))
    db.add(PasswordResetToken(user_id=user.id, token_hash=token_hash(raw_token), created_by=principal.user.full_name, created_at=now, expires_at=expires_at))
    security_event(db, request, "password_reset_issued", company_id=user.company_id, user_id=user.id, detail={"actor": principal.user.id})
    audit(db, principal.user.full_name, "access.password_reset_issue", "user", user.id, company_id=user.company_id)
    db.commit()
    return {"reset_token": raw_token, "expires_at": expires_at, "user": {"id": user.id, "username": user.username, "full_name": user.full_name}}


@router.post("/reset-password")
def consume_reset_token(payload: ResetConsumeInput, request: Request, db: Session = Depends(get_db)) -> dict[str, Any]:
    now = utcnow()
    reset = db.scalar(select(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash(payload.token)))
    if not reset or reset.used_at is not None or reset.expires_at <= now:
        raise HTTPException(status_code=422, detail="Reset token is invalid or expired")
    user = db.get(User, reset.user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=422, detail="Reset token cannot be used for this account")
    replace_password(db, user, payload.new_password)
    user.failed_login_attempts = 0
    user.locked_until = None
    user.status = "active"
    reset.used_at = now
    revoked = revoke_user_sessions(db, user.id, actor="password-reset", reason="Password reset")
    security_event(db, request, "password_reset_completed", company_id=user.company_id, user_id=user.id, detail={"revoked_sessions": revoked})
    audit(db, user.full_name, "access.password_reset_complete", "user", user.id, company_id=user.company_id)
    db.commit()
    return {"message": "Password reset. Sign in with the new password."}


@router.get("/sessions")
def my_sessions(principal: Principal = Depends(current_principal), db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    rows = db.scalars(select(UserSession).where(UserSession.user_id == principal.user.id).order_by(UserSession.id.desc()).limit(50)).all()
    return [{"id": row.id, "ip_address": row.ip_address, "user_agent": row.user_agent, "created_at": row.created_at, "last_seen_at": row.last_seen_at, "expires_at": row.expires_at, "revoked_at": row.revoked_at, "revoke_reason": row.revoke_reason, "current": row.id == principal.session.id} for row in rows]


@router.delete("/sessions/{session_id}", status_code=204)
def revoke_my_session(session_id: int, principal: Principal = Depends(current_principal), db: Session = Depends(get_db)) -> Response:
    row = db.get(UserSession, session_id)
    if not row or row.user_id != principal.user.id:
        raise HTTPException(status_code=404, detail="Session not found")
    if row.revoked_at is None:
        row.revoked_at = utcnow()
        row.revoked_by = principal.user.full_name
        row.revoke_reason = "Revoked by user"
        db.commit()
    return Response(status_code=204)


@router.get("/users/{user_id}/sessions")
def user_sessions(user_id: int, principal: Principal = Depends(require_permission("sessions.view", company_scope=True)), db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    user = db.get(User, user_id)
    if not user or user.company_id != principal.user.company_id:
        raise HTTPException(status_code=404, detail="User not found")
    rows = db.scalars(select(UserSession).where(UserSession.user_id == user.id).order_by(UserSession.id.desc()).limit(100)).all()
    return [{"id": row.id, "ip_address": row.ip_address, "user_agent": row.user_agent, "created_at": row.created_at, "last_seen_at": row.last_seen_at, "expires_at": row.expires_at, "revoked_at": row.revoked_at, "revoke_reason": row.revoke_reason} for row in rows]


@router.post("/users/{user_id}/sessions/revoke-all")
def revoke_all_user_sessions(user_id: int, request: Request, principal: Principal = Depends(require_permission("sessions.manage", company_scope=True)), db: Session = Depends(get_db)) -> dict[str, Any]:
    user = db.get(User, user_id)
    if not user or user.company_id != principal.user.company_id:
        raise HTTPException(status_code=404, detail="User not found")
    count = revoke_user_sessions(db, user.id, actor=principal.user.full_name, reason="Administrator revoked all sessions")
    security_event(db, request, "sessions_revoked", company_id=user.company_id, user_id=user.id, detail={"count": count, "actor": principal.user.id})
    audit(db, principal.user.full_name, "access.sessions_revoke_all", "user", user.id, company_id=user.company_id, detail={"count": count})
    db.commit()
    return {"revoked_sessions": count}


@router.get("/security-policy")
def get_policy(principal: Principal = Depends(require_permission("security.view", company_scope=True)), db: Session = Depends(get_db)) -> dict[str, int | bool]:
    return security_policy(db, principal.user.company_id)


@router.put("/security-policy")
def update_policy(payload: SecurityPolicyInput, request: Request, principal: Principal = Depends(require_permission("security.manage", company_scope=True)), db: Session = Depends(get_db)) -> dict[str, Any]:
    row = db.scalar(select(CompanySetting).where(CompanySetting.company_id == principal.user.company_id, CompanySetting.key == "security_policy"))
    if not row:
        row = CompanySetting(company_id=principal.user.company_id, key="security_policy", value=payload.model_dump(), description="Phase 2 authentication and session security policy")
        db.add(row)
    else:
        row.value = payload.model_dump()
    security_event(db, request, "security_policy_changed", company_id=principal.user.company_id, user_id=principal.user.id)
    audit(db, principal.user.full_name, "access.security_policy_update", "company_setting", row.id, company_id=principal.user.company_id)
    db.commit()
    return {"policy": security_policy(db, principal.user.company_id), "message": "Security policy updated"}


@router.get("/security-events")
def list_security_events(limit: int = 250, event_type: str | None = None, principal: Principal = Depends(require_permission("security.view", company_scope=True)), db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    limit = max(1, min(limit, 1000))
    statement = select(SecurityEvent).where(SecurityEvent.company_id == principal.user.company_id)
    if event_type:
        statement = statement.where(SecurityEvent.event_type == event_type)
    rows = db.scalars(statement.order_by(SecurityEvent.id.desc()).limit(limit)).all()
    return [{"id": row.id, "user_id": row.user_id, "event_type": row.event_type, "username_attempted": row.username_attempted, "ip_address": row.ip_address, "user_agent": row.user_agent, "detail": row.detail, "occurred_at": row.occurred_at} for row in rows]
