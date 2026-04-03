import os
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import StreamingResponse
import json
import io
import csv

from app.config import settings
from app.models import AuditResponse, AuditHitInfo, AuditByIdsRequest, MultiAuditResponse
from app.utils.file_utils import is_supported_file
from app.services.document_processor import process_file, DocumentSection
from app.services.audit_engine import audit_sections, get_available_categories
from app.services.document_store import get_document, get_sections_multi

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("/categories")
async def list_categories():
    """Return available audit categories for frontend configuration."""
    return get_available_categories()


@router.post("", response_model=AuditResponse)
async def audit_document(
    file: UploadFile = File(...),
    categories: str = Form(""),
):
    """Upload and audit a document.

    - **file**: The document file to audit.
    - **categories**: Comma-separated category keys to check (empty = all).
    """
    if not file.filename or not is_supported_file(file.filename):
        raise HTTPException(status_code=400, detail="Unsupported file type")

    cat_list = [c.strip() for c in categories.split(",") if c.strip()] or None

    tmp_id = uuid.uuid4().hex[:12]
    file_path = os.path.join(settings.upload_dir, f"audit_{tmp_id}_{file.filename}")

    try:
        content = await file.read()
        if len(content) > settings.max_file_size_mb * 1024 * 1024:
            raise HTTPException(status_code=400, detail="File too large")

        with open(file_path, "wb") as f:
            f.write(content)

        sections = process_file(file_path, file.filename)
        if not sections:
            raise HTTPException(status_code=400, detail="No text content extracted")

        result = audit_sections(sections, file.filename, cat_list)

        return AuditResponse(
            filename=result.filename,
            total_hits=result.total_hits,
            risk_level=result.risk_level,
            hits=[
                AuditHitInfo(
                    category=h.category,
                    category_label=h.category_label,
                    keyword=h.keyword,
                    description=h.description,
                    location=h.location,
                    context=h.context,
                    severity=h.severity,
                    suggestion=h.suggestion,
                )
                for h in result.hits
            ],
            category_summary=result.category_summary,
        )
    finally:
        if os.path.exists(file_path):
            os.unlink(file_path)


@router.post("/export")
async def export_report(
    file: UploadFile = File(...),
    categories: str = Form(""),
    format: str = Form("csv"),
):
    """Audit a document and return the report as a downloadable file."""
    if not file.filename or not is_supported_file(file.filename):
        raise HTTPException(status_code=400, detail="Unsupported file type")

    cat_list = [c.strip() for c in categories.split(",") if c.strip()] or None

    tmp_id = uuid.uuid4().hex[:12]
    file_path = os.path.join(settings.upload_dir, f"audit_{tmp_id}_{file.filename}")

    try:
        content = await file.read()
        if len(content) > settings.max_file_size_mb * 1024 * 1024:
            raise HTTPException(status_code=400, detail="File too large")

        with open(file_path, "wb") as f:
            f.write(content)

        sections = process_file(file_path, file.filename)
        if not sections:
            raise HTTPException(status_code=400, detail="No text content extracted")

        result = audit_sections(sections, file.filename, cat_list)

        if format == "json":
            return _export_json(result)
        return _export_csv(result)
    finally:
        if os.path.exists(file_path):
            os.unlink(file_path)


def _export_csv(result):
    buf = io.StringIO()
    buf.write("\ufeff")  # BOM for Excel CJK support
    writer = csv.writer(buf)
    writer.writerow([
        "文件名", "风险等级", "类别", "关键词",
        "说明", "位置", "上下文", "严重程度", "处理建议",
    ])
    for h in result.hits:
        writer.writerow([
            result.filename, result.risk_level,
            h.category_label, h.keyword, h.description,
            h.location, h.context, h.severity, h.suggestion,
        ])
    buf.seek(0)
    safe_name = result.filename.rsplit(".", 1)[0]
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename=audit_{safe_name}.csv"},
    )


def _export_json(result):
    data = {
        "filename": result.filename,
        "risk_level": result.risk_level,
        "total_hits": result.total_hits,
        "category_summary": result.category_summary,
        "hits": [
            {
                "category_label": h.category_label,
                "keyword": h.keyword,
                "description": h.description,
                "location": h.location,
                "context": h.context,
                "severity": h.severity,
                "suggestion": h.suggestion,
            }
            for h in result.hits
        ],
    }
    content = json.dumps(data, ensure_ascii=False, indent=2)
    safe_name = result.filename.rsplit(".", 1)[0]
    return StreamingResponse(
        iter([content]),
        media_type="application/json; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename=audit_{safe_name}.json"},
    )


# ---------------------------------------------------------------------------
# Library-based endpoints (audit by doc_ids from unified document library)
# ---------------------------------------------------------------------------

def _audit_docs_by_ids(doc_ids: list[str], categories: list[str] | None) -> list:
    """Shared logic: audit multiple documents by their library IDs."""
    sections_map = get_sections_multi(doc_ids)
    if not sections_map:
        raise HTTPException(status_code=404, detail="No documents found for given IDs")

    results = []
    for did, raw_sections in sections_map.items():
        doc = get_document(did)
        filename = doc.name if doc else did
        doc_sections = [
            DocumentSection(text=s["text"], metadata=s.get("metadata", {}))
            for s in raw_sections
        ]
        result = audit_sections(doc_sections, filename, categories)
        results.append(result)
    return results


def _to_response(result) -> AuditResponse:
    return AuditResponse(
        filename=result.filename,
        total_hits=result.total_hits,
        risk_level=result.risk_level,
        hits=[
            AuditHitInfo(
                category=h.category,
                category_label=h.category_label,
                keyword=h.keyword,
                description=h.description,
                location=h.location,
                context=h.context,
                severity=h.severity,
                suggestion=h.suggestion,
            )
            for h in result.hits
        ],
        category_summary=result.category_summary,
    )


def _overall_risk(results: list) -> str:
    levels = {"safe": 0, "low": 1, "medium": 2, "high": 3}
    max_level = max(levels.get(r.risk_level, 0) for r in results) if results else 0
    return {0: "safe", 1: "low", 2: "medium", 3: "high"}[max_level]


@router.post("/scan", response_model=MultiAuditResponse)
async def audit_by_ids(req: AuditByIdsRequest):
    """Audit documents from the unified library by their IDs."""
    if not req.doc_ids:
        raise HTTPException(status_code=400, detail="No document IDs provided")

    cat_list = req.categories or None
    results = _audit_docs_by_ids(req.doc_ids, cat_list)

    responses = [_to_response(r) for r in results]
    total = sum(r.total_hits for r in results)
    return MultiAuditResponse(
        results=responses,
        overall_risk_level=_overall_risk(results),
        overall_total_hits=total,
    )


@router.post("/export-by-ids")
async def export_by_ids(req: AuditByIdsRequest):
    """Audit documents from the library and export a combined CSV report."""
    if not req.doc_ids:
        raise HTTPException(status_code=400, detail="No document IDs provided")

    cat_list = req.categories or None
    results = _audit_docs_by_ids(req.doc_ids, cat_list)

    # Build combined CSV
    buf = io.StringIO()
    buf.write("\ufeff")
    writer = csv.writer(buf)
    writer.writerow([
        "文件名", "风险等级", "类别", "关键词",
        "说明", "位置", "上下文", "严重程度", "处理建议",
    ])
    for result in results:
        for h in result.hits:
            writer.writerow([
                result.filename, result.risk_level,
                h.category_label, h.keyword, h.description,
                h.location, h.context, h.severity, h.suggestion,
            ])
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=audit_report.csv"},
    )
