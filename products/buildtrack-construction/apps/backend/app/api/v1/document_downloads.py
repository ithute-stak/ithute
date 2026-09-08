from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.models import Company, Document, DocumentVersion

router = APIRouter(prefix="/foundation", tags=["Phase 1 - Document Control"])
settings = get_settings()


def current_company(db: Session) -> Company:
    company = db.scalar(select(Company).order_by(Company.id).limit(1))
    if not company:
        raise HTTPException(status_code=409, detail="BuildTrack has not been bootstrapped")
    return company


@router.get("/documents/{document_id}/versions/{version_id}/download")
def download_document_version(document_id: int, version_id: int, db: Session = Depends(get_db)) -> FileResponse:
    company = current_company(db)
    document = db.get(Document, document_id)
    if not document or document.company_id != company.id:
        raise HTTPException(status_code=404, detail="Document not found")
    version = db.get(DocumentVersion, version_id)
    if not version or version.document_id != document.id:
        raise HTTPException(status_code=404, detail="Document version not found")

    media_root = Path(settings.media_root).resolve()
    path = (media_root / version.stored_path).resolve()
    try:
        path.relative_to(media_root)
    except ValueError as error:
        raise HTTPException(status_code=400, detail="Invalid document storage path") from error
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Stored document file is missing")

    return FileResponse(
        path,
        media_type=version.content_type or "application/octet-stream",
        filename=version.original_filename,
    )
