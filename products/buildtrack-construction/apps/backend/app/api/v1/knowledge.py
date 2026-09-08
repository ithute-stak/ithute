from __future__ import annotations

from datetime import date, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.procurement import allow_self_approval, commit, ensure_document, issue_reference, row_dict, utcnow
from app.db.session import get_db
from app.models import (
    Branch,
    ChangeRequest,
    Document,
    KnowledgeAcknowledgement,
    KnowledgeArticle,
    KnowledgeAuditEvent,
    NumberSequence,
    Permission,
    Role,
    RolePermission,
    Site,
    SupportTicket,
)
from app.security.access import Principal, current_principal


router = APIRouter(prefix="/knowledge", tags=["Phase 27 - Operational Knowledge & SOP Control"])

P = {
    "knowledge.view": ("knowledge", "view", "View controlled operational knowledge"),
    "knowledge.manage": ("knowledge", "manage", "Prepare operational knowledge and SOP articles"),
    "knowledge.approve": ("knowledge", "approve", "Independently publish controlled operational knowledge"),
    "knowledge.acknowledge": ("knowledge", "acknowledge", "Acknowledge published operational knowledge"),
}


def any_permission(principal: Principal, code: str) -> None:
    if not principal.has_permission_anywhere(code):
        raise HTTPException(status_code=403, detail=f"Permission required: {code}")


def scope(principal: Principal, code: str, branch_id: int, site_id: int | None) -> None:
    if not principal.can(code, branch_id=branch_id, site_id=site_id):
        raise HTTPException(status_code=403, detail=f"Permission required in this branch/site: {code}")


def audit(db: Session, principal: Principal, action: str, article: KnowledgeArticle, detail: dict | None = None) -> None:
    db.add(KnowledgeAuditEvent(
        company_id=principal.user.company_id,
        branch_id=article.branch_id,
        site_id=article.site_id,
        actor=principal.user.full_name,
        action=action,
        entity_type=article.__tablename__,
        entity_id=str(article.id),
        detail=detail or {},
    ))


def get_article(db: Session, principal: Principal, article_id: int, permission: str) -> KnowledgeArticle:
    article = db.get(KnowledgeArticle, article_id)
    if not article or article.company_id != principal.user.company_id:
        raise HTTPException(status_code=404, detail="Knowledge article not found")
    scope(principal, permission, article.branch_id, article.site_id)
    return article


def scoped_rows(db: Session, principal: Principal, permission: str) -> list[KnowledgeArticle]:
    return [
        article for article in db.scalars(
            select(KnowledgeArticle)
            .where(KnowledgeArticle.company_id == principal.user.company_id)
            .order_by(KnowledgeArticle.created_at.desc())
        ).all()
        if principal.can(permission, branch_id=article.branch_id, site_id=article.site_id)
    ]


def bootstrap_module(db: Session, company_id: int) -> None:
    permissions: dict[str, Permission] = {}
    for code, (module, action, description) in P.items():
        permission = db.scalar(select(Permission).where(Permission.code == code))
        if not permission:
            permission = Permission(code=code, module=module, action=action, description=description)
            db.add(permission)
            db.flush()
        permissions[code] = permission

    roles = {role.code: role for role in db.scalars(select(Role).where(Role.company_id == company_id)).all()}
    for code, name, level in (
        ("KNOWLEDGE_MANAGER", "Knowledge Manager", "company"),
        ("KNOWLEDGE_AUTHOR", "Knowledge Author", "branch"),
        ("KNOWLEDGE_REVIEWER", "Knowledge Reviewer", "company"),
    ):
        if code not in roles:
            roles[code] = Role(company_id=company_id, code=code, name=name, scope_level=level, description=f"Phase 27 {name}", is_system=True, is_active=True)
            db.add(roles[code])
            db.flush()

    grants = {
        "SYSTEM_ADMIN": set(P), "HQ_EXECUTIVE": set(P), "BRANCH_MANAGER": set(P),
        "AUDITOR": {"knowledge.view"}, "SUPPORT_MANAGER": {"knowledge.view", "knowledge.manage", "knowledge.acknowledge"},
        "CHANGE_MANAGER": {"knowledge.view", "knowledge.manage", "knowledge.acknowledge"},
        "KNOWLEDGE_MANAGER": set(P), "KNOWLEDGE_AUTHOR": {"knowledge.view", "knowledge.manage", "knowledge.acknowledge"},
        "KNOWLEDGE_REVIEWER": {"knowledge.view", "knowledge.approve", "knowledge.acknowledge"},
    }
    for role_code, codes in grants.items():
        role = roles.get(role_code)
        if not role:
            continue
        current = set(db.scalars(select(RolePermission.permission_id).where(RolePermission.role_id == role.id)).all())
        for code in codes:
            if permissions[code].id not in current:
                db.add(RolePermission(role_id=role.id, permission_id=permissions[code].id))
                current.add(permissions[code].id)
    if not db.scalar(select(NumberSequence).where(NumberSequence.company_id == company_id, NumberSequence.code == "KNOWLEDGE_ARTICLE")):
        db.add(NumberSequence(company_id=company_id, code="KNOWLEDGE_ARTICLE", name="Knowledge Article", prefix="KNO", next_number=1, padding=5, reset_period="yearly"))


class ArticleIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    branch_id: int
    site_id: int | None = None
    title: str = Field(min_length=2, max_length=300)
    category: Literal["procedure", "system", "process", "troubleshooting", "safety", "commercial", "other"]
    audience: Literal["all_staff", "head_office", "branch_staff", "site_staff", "managers"] = "all_staff"
    summary: str = Field(min_length=10, max_length=2000)
    body: str = Field(min_length=30, max_length=15000)
    review_due_date: date | None = None
    evidence_document_id: int | None = None
    source_ticket_id: int | None = None
    source_change_id: int | None = None


@router.post("/bootstrap")
def bootstrap(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict:
    if not principal.has_company_permission("company.manage") and not principal.has_company_permission("knowledge.manage"):
        raise HTTPException(status_code=403, detail="Company administration is required")
    bootstrap_module(db, principal.user.company_id)
    commit(db)
    return {"phase": 27, "status": "ready"}


@router.get("/catalog")
def catalog(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict:
    any_permission(principal, "knowledge.view")
    all_sites = db.scalars(select(Site).where(Site.company_id == principal.user.company_id)).all()
    sites = [site for site in all_sites if principal.can("knowledge.view", branch_id=site.branch_id, site_id=site.id)]
    site_branch_ids = {site.branch_id for site in sites}
    branches = [branch for branch in db.scalars(select(Branch).where(Branch.company_id == principal.user.company_id)).all() if principal.can("knowledge.view", branch_id=branch.id, site_id=None) or branch.id in site_branch_ids]
    documents = [
        document for document in db.scalars(select(Document).where(Document.company_id == principal.user.company_id).order_by(Document.created_at.desc())).all()
        if principal.can("knowledge.view", branch_id=document.branch_id, site_id=document.site_id)
    ]
    return {"branches": [row_dict(row) for row in branches], "sites": [row_dict(row) for row in sites], "documents": [row_dict(row) for row in documents]}


@router.get("/articles")
def articles(published_only: bool = False, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> list[dict]:
    any_permission(principal, "knowledge.view")
    rows = scoped_rows(db, principal, "knowledge.view")
    return [row_dict(article) for article in rows if not published_only or article.status == "published"]


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict:
    any_permission(principal, "knowledge.view")
    rows = scoped_rows(db, principal, "knowledge.view")
    review_window = date.today() + timedelta(days=30)
    published_ids = [row.id for row in rows if row.status == "published"]
    acknowledgement_count = 0
    if published_ids:
        acknowledgement_count = len(db.scalars(select(KnowledgeAcknowledgement).where(KnowledgeAcknowledgement.article_id.in_(published_ids))).all())
    return {
        "articles": len(rows),
        "published": sum(row.status == "published" for row in rows),
        "awaiting_publication": sum(row.status == "submitted" for row in rows),
        "review_due": sum(row.status == "published" and row.review_due_date and row.review_due_date <= review_window for row in rows),
        "acknowledgements": acknowledgement_count,
    }


@router.post("/articles", status_code=201)
def create_article(payload: ArticleIn, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict:
    scope(principal, "knowledge.manage", payload.branch_id, payload.site_id)
    branch = db.get(Branch, payload.branch_id)
    site = db.get(Site, payload.site_id) if payload.site_id else None
    if not branch or branch.company_id != principal.user.company_id or site and (site.company_id != principal.user.company_id or site.branch_id != branch.id):
        raise HTTPException(status_code=422, detail="Knowledge article branch/site scope is invalid")
    ensure_document(db, principal.user.company_id, payload.evidence_document_id)
    if payload.source_ticket_id:
        ticket = db.get(SupportTicket, payload.source_ticket_id)
        if not ticket or ticket.company_id != principal.user.company_id or ticket.status != "closed" or ticket.branch_id != payload.branch_id or ticket.site_id != payload.site_id:
            raise HTTPException(status_code=422, detail="Knowledge source ticket must be a closed ticket in the same branch/site scope")
    if payload.source_change_id:
        change = db.get(ChangeRequest, payload.source_change_id)
        if not change or change.company_id != principal.user.company_id or change.status != "released" or change.branch_id != payload.branch_id or change.site_id != payload.site_id:
            raise HTTPException(status_code=422, detail="Knowledge source change must be a released change in the same branch/site scope")
    article = KnowledgeArticle(
        company_id=principal.user.company_id, branch_id=payload.branch_id, site_id=payload.site_id,
        article_number=issue_reference(db, principal.user.company_id, "KNOWLEDGE_ARTICLE", "KNO"),
        title=payload.title.strip(), category=payload.category, audience=payload.audience,
        summary=payload.summary.strip(), body=payload.body.strip(), review_due_date=payload.review_due_date,
        evidence_document_id=payload.evidence_document_id, source_ticket_id=payload.source_ticket_id,
        source_change_id=payload.source_change_id, prepared_by=principal.user.full_name,
    )
    db.add(article)
    db.flush()
    audit(db, principal, "knowledge.article.created", article)
    commit(db)
    return row_dict(article)


@router.post("/articles/{article_id:int}/submit")
def submit_article(article_id: int, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict:
    article = get_article(db, principal, article_id, "knowledge.manage")
    if article.status not in {"draft", "rejected"} or not article.evidence_document_id or not article.review_due_date:
        raise HTTPException(status_code=409, detail="Controlled evidence and a review due date are required before knowledge submission")
    article.status, article.submitted_at = "submitted", utcnow()
    audit(db, principal, "knowledge.article.submitted", article)
    commit(db)
    return row_dict(article)


@router.post("/articles/{article_id:int}/publish")
def publish_article(article_id: int, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict:
    article = get_article(db, principal, article_id, "knowledge.approve")
    if article.status != "submitted":
        raise HTTPException(status_code=409, detail="Knowledge article is not awaiting publication")
    if article.prepared_by == principal.user.full_name and not allow_self_approval(db, article.company_id):
        raise HTTPException(status_code=422, detail="Self-publication is disabled by company policy")
    article.status, article.published_by, article.published_at = "published", principal.user.full_name, utcnow()
    audit(db, principal, "knowledge.article.published", article)
    commit(db)
    return row_dict(article)


@router.post("/articles/{article_id:int}/retire")
def retire_article(article_id: int, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict:
    article = get_article(db, principal, article_id, "knowledge.manage")
    if article.status != "published":
        raise HTTPException(status_code=409, detail="Only published knowledge articles can be retired")
    article.status, article.retired_by, article.retired_at = "retired", principal.user.full_name, utcnow()
    audit(db, principal, "knowledge.article.retired", article)
    commit(db)
    return row_dict(article)


@router.post("/articles/{article_id:int}/acknowledge")
def acknowledge_article(article_id: int, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict:
    article = get_article(db, principal, article_id, "knowledge.acknowledge")
    if article.status != "published":
        raise HTTPException(status_code=409, detail="Only published knowledge articles can be acknowledged")
    acknowledgement = db.scalar(select(KnowledgeAcknowledgement).where(KnowledgeAcknowledgement.article_id == article.id, KnowledgeAcknowledgement.user_id == principal.user.id))
    if acknowledgement:
        return row_dict(acknowledgement)
    acknowledgement = KnowledgeAcknowledgement(article_id=article.id, user_id=principal.user.id, acknowledged_by=principal.user.full_name)
    db.add(acknowledgement)
    audit(db, principal, "knowledge.article.acknowledged", article, {"user_id": principal.user.id})
    commit(db)
    return row_dict(acknowledgement)


@router.get("/articles/{article_id:int}/acknowledgements")
def acknowledgements(article_id: int, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> list[dict]:
    article = get_article(db, principal, article_id, "knowledge.view")
    return [row_dict(row) for row in db.scalars(select(KnowledgeAcknowledgement).where(KnowledgeAcknowledgement.article_id == article.id).order_by(KnowledgeAcknowledgement.acknowledged_at.desc())).all()]
