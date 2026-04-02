import os
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import StreamingResponse
import json
import io
import csv

from app.config import settings
from app.models import AuditResponse, AuditHitInfo
from app.utils.file_utils import is_supported_file
from app.services.document_processor import process_file
from app.services.audit_engine import audit_sections, get_available_categories

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
