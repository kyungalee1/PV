import json
import logging
import os
import shutil
from datetime import date, datetime
from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, Response
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import PDF_DIR, UPLOAD_DIR
from app.database import Base, engine, get_db
from app.models import CaseRecord
from app.schemas import (
    CaseCreate,
    CaseResponse,
    CaseUpdate,
    CiomsFormData,
    DashboardStats,
    LiteratureConvertResponse,
    LiteratureHtmlRequest,
)
from app.services.parser import parse_uploaded_file
from app.services.html_generator import generate_cioms_html
from app.services.pdf_generator import generate_cioms_pdf

logger = logging.getLogger(__name__)

app = FastAPI(title="CIOMS Literature Converter", version="2.0.0")

_default_origins = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://127.0.0.1:5174"
_cors_origins = [
    o.strip()
    for o in os.getenv("CORS_ORIGINS", _default_origins).split(",")
    if o.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

Base.metadata.create_all(bind=engine)


def _to_response(record: CaseRecord) -> CaseResponse:
    return CaseResponse(
        id=record.id,
        collection_date=record.collection_date,
        ae_name=record.ae_name,
        is_sae=record.is_sae,
        assignee=record.assignee,
        partner_reported=record.partner_reported,
        source=record.source,
        source_file=record.source_file,
        status=record.status,
        cioms=record.cioms_data(),
        has_pdf=bool(record.pdf_path and Path(record.pdf_path).exists()),
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/dashboard/stats", response_model=DashboardStats)
def dashboard_stats(db: Session = Depends(get_db)):
    cases = db.query(CaseRecord).all()
    total = len(cases)
    sae_count = sum(1 for c in cases if c.is_sae)
    partner = sum(1 for c in cases if c.partner_reported)
    completed = sum(1 for c in cases if c.status == "completed")
    draft = sum(1 for c in cases if c.status == "draft")

    by_source: dict[str, int] = {}
    by_assignee: dict[str, int] = {}
    monthly: dict[str, int] = {}
    for c in cases:
        by_source[c.source or "unknown"] = by_source.get(c.source or "unknown", 0) + 1
        key = c.assignee or "Unassigned"
        by_assignee[key] = by_assignee.get(key, 0) + 1
        if c.collection_date:
            mk = c.collection_date.strftime("%Y-%m")
            monthly[mk] = monthly.get(mk, 0) + 1

    return DashboardStats(
        total_cases=total,
        sae_count=sae_count,
        non_sae_count=total - sae_count,
        partner_reported_count=partner,
        completed_count=completed,
        draft_count=draft,
        by_source=[{"name": k, "value": v} for k, v in sorted(by_source.items())],
        by_assignee=[{"name": k, "value": v} for k, v in sorted(by_assignee.items())],
        monthly_trend=sorted(
            [{"month": k, "count": v} for k, v in monthly.items()],
            key=lambda x: x["month"],
        ),
        sae_ratio=round(sae_count / total * 100, 1) if total else 0.0,
    )


@app.get("/api/cases", response_model=list[CaseResponse])
def list_cases(
    sae: bool | None = None,
    assignee: str | None = None,
    source: str | None = None,
    db: Session = Depends(get_db),
):
    q = db.query(CaseRecord).order_by(CaseRecord.created_at.desc())
    if sae is not None:
        q = q.filter(CaseRecord.is_sae == sae)
    if assignee:
        q = q.filter(CaseRecord.assignee == assignee)
    if source:
        q = q.filter(CaseRecord.source == source)
    return [_to_response(r) for r in q.all()]


@app.get("/api/cases/{case_id}", response_model=CaseResponse)
def get_case(case_id: int, db: Session = Depends(get_db)):
    record = db.get(CaseRecord, case_id)
    if not record:
        raise HTTPException(404, "Case not found")
    return _to_response(record)


@app.post("/api/cases", response_model=CaseResponse)
def create_case(payload: CaseCreate, db: Session = Depends(get_db)):
    cioms = payload.cioms.model_dump() if payload.cioms else {}
    record = CaseRecord(
        collection_date=payload.collection_date or date.today(),
        ae_name=payload.ae_name,
        is_sae=payload.is_sae,
        assignee=payload.assignee,
        partner_reported=payload.partner_reported,
        source=payload.source,
        cioms_json=json.dumps(cioms, ensure_ascii=False),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return _to_response(record)


@app.patch("/api/cases/{case_id}", response_model=CaseResponse)
def update_case(case_id: int, payload: CaseUpdate, db: Session = Depends(get_db)):
    record = db.get(CaseRecord, case_id)
    if not record:
        raise HTTPException(404, "Case not found")

    for field in ("collection_date", "ae_name", "is_sae", "assignee", "partner_reported", "source", "status"):
        val = getattr(payload, field)
        if val is not None:
            setattr(record, field, val)

    if payload.cioms:
        record.cioms_json = json.dumps(payload.cioms.model_dump(), ensure_ascii=False)
        if payload.cioms.reaction_meddra_pt and not payload.ae_name:
            record.ae_name = payload.cioms.reaction_meddra_pt[:500]

    record.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(record)
    return _to_response(record)


@app.delete("/api/cases/{case_id}")
def delete_case(case_id: int, db: Session = Depends(get_db)):
    record = db.get(CaseRecord, case_id)
    if not record:
        raise HTTPException(404, "Case not found")
    if record.pdf_path and Path(record.pdf_path).exists():
        Path(record.pdf_path).unlink(missing_ok=True)
    db.delete(record)
    db.commit()
    return {"ok": True}


@app.post("/api/literature/convert", response_model=LiteratureConvertResponse)
async def convert_literature(file: UploadFile = File(...)):
    """Stateless: PDF → CIOMS fields + HTML (no database)."""
    if not file.filename:
        raise HTTPException(400, "Filename required")
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Only PDF files are supported")

    safe_name = Path(file.filename).name
    dest = UPLOAD_DIR / f"tmp_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{safe_name}"
    try:
        with dest.open("wb") as f:
            shutil.copyfileobj(file.file, f)
        parsed = await run_in_threadpool(parse_uploaded_file, dest)
        cioms = parsed.get("cioms", {})
        if not cioms.get("date_of_report"):
            cioms["date_of_report"] = date.today().isoformat()
        html = generate_cioms_html(cioms, case_id=0)
        return LiteratureConvertResponse(
            filename=safe_name,
            ae_name=parsed.get("ae_name", "Unknown AE"),
            cioms=cioms,
            html=html,
        )
    except Exception as e:
        logger.exception("Literature convert failed for %s", safe_name)
        raise HTTPException(422, f"Parse failed: {e}") from e
    finally:
        dest.unlink(missing_ok=True)


@app.post("/api/literature/html")
def render_literature_html(payload: LiteratureHtmlRequest):
    """Regenerate HTML from edited CIOMS fields (no database)."""
    cioms = dict(payload.cioms)
    if not cioms.get("date_of_report"):
        cioms["date_of_report"] = date.today().isoformat()
    return {"html": generate_cioms_html(cioms, case_id=0)}


@app.post("/api/literature/upload", response_model=CaseResponse)
async def upload_literature(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Upload literature case-report PDF → extract CIOMS 26 fields."""
    if not file.filename:
        raise HTTPException(400, "Filename required")
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Only PDF files are supported")

    safe_name = Path(file.filename).name
    dest = UPLOAD_DIR / f"{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{safe_name}"
    try:
        with dest.open("wb") as f:
            shutil.copyfileobj(file.file, f)
        parsed = await run_in_threadpool(parse_uploaded_file, dest)
    except Exception as e:
        dest.unlink(missing_ok=True)
        logger.exception("Literature parse failed for %s", safe_name)
        raise HTTPException(422, f"Parse failed: {e}") from e

    record = CaseRecord(
        collection_date=date.today(),
        ae_name=parsed.get("ae_name", "Unknown AE"),
        is_sae=parsed.get("is_sae", False),
        source="literature",
        source_file=file.filename,
        status="completed",
        cioms_json=json.dumps(parsed.get("cioms", {}), ensure_ascii=False),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return _to_response(record)


@app.post("/api/cases/upload", response_model=CaseResponse)
async def upload_and_parse(
    file: UploadFile = File(...),
    assignee: str = "",
    partner_reported: bool = False,
    db: Session = Depends(get_db),
):
    if not file.filename:
        raise HTTPException(400, "Filename required")

    suffix = Path(file.filename).suffix.lower()
    if suffix not in (".pdf", ".xlsx", ".xls", ".txt", ".csv"):
        raise HTTPException(400, "Supported: PDF, Excel, TXT, CSV")

    safe_name = Path(file.filename).name
    dest = UPLOAD_DIR / f"{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{safe_name}"
    try:
        with dest.open("wb") as f:
            shutil.copyfileobj(file.file, f)
        logger.info("Uploaded file saved: %s (%s bytes)", dest.name, dest.stat().st_size)
        parsed = await run_in_threadpool(parse_uploaded_file, dest)
    except HTTPException:
        dest.unlink(missing_ok=True)
        raise
    except Exception as e:
        dest.unlink(missing_ok=True)
        logger.exception("Parse failed for %s", safe_name)
        raise HTTPException(422, f"Parse failed: {e}") from e

    coll = parsed.get("collection_date")
    coll_date = date.fromisoformat(coll) if isinstance(coll, str) and coll else date.today()

    record = CaseRecord(
        collection_date=coll_date,
        ae_name=parsed.get("ae_name", "Unknown AE"),
        is_sae=parsed.get("is_sae", False),
        assignee=assignee,
        partner_reported=partner_reported,
        source=parsed.get("source", "other"),
        source_file=file.filename,
        status="draft",
        cioms_json=json.dumps(parsed.get("cioms", {}), ensure_ascii=False),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return _to_response(record)


@app.post("/api/cases/{case_id}/generate-pdf", response_model=CaseResponse)
def generate_pdf(case_id: int, db: Session = Depends(get_db)):
    record = db.get(CaseRecord, case_id)
    if not record:
        raise HTTPException(404, "Case not found")

    cioms = record.cioms_data()
    if not cioms:
        raise HTTPException(400, "CIOMS data is empty")

    if not cioms.get("mfr_control_no"):
        cioms["mfr_control_no"] = f"CASE-{case_id}"
    if not cioms.get("date_of_report"):
        cioms["date_of_report"] = date.today().isoformat()

    out = PDF_DIR / f"cioms_case_{case_id}.pdf"
    generate_cioms_pdf(cioms, case_id, out)
    record.pdf_path = str(out)
    record.status = "completed"
    record.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(record)
    return _to_response(record)


def _cioms_for_html(record: CaseRecord, case_id: int) -> dict:
    cioms = record.cioms_data()
    if not cioms:
        raise HTTPException(400, "CIOMS data is empty")
    if not cioms.get("mfr_control_no"):
        cioms["mfr_control_no"] = f"CASE-{case_id}"
    if not cioms.get("date_of_report"):
        cioms["date_of_report"] = date.today().isoformat()
    return cioms


@app.get("/api/cases/{case_id}/html")
def download_html(case_id: int, db: Session = Depends(get_db)):
    record = db.get(CaseRecord, case_id)
    if not record:
        raise HTTPException(404, "Case not found")
    cioms = _cioms_for_html(record, case_id)
    return HTMLResponse(
        content=generate_cioms_html(cioms, case_id),
        media_type="text/html; charset=utf-8",
    )


@app.get("/api/cases/{case_id}/html/download")
def download_html_file(case_id: int, db: Session = Depends(get_db)):
    record = db.get(CaseRecord, case_id)
    if not record:
        raise HTTPException(404, "Case not found")
    cioms = _cioms_for_html(record, case_id)
    html = generate_cioms_html(cioms, case_id)
    filename = f"CIOMS_{Path(record.source_file or 'case').stem}.html"
    return Response(
        content=html.encode("utf-8"),
        media_type="text/html; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/cases/{case_id}/pdf")
def download_pdf(case_id: int, db: Session = Depends(get_db)):
    record = db.get(CaseRecord, case_id)
    if not record or not record.pdf_path:
        raise HTTPException(404, "PDF not generated")
    path = Path(record.pdf_path)
    if not path.exists():
        raise HTTPException(404, "PDF file missing")
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=f"CIOMS_Case_{case_id}.pdf",
    )


@app.post("/api/cases/seed-demo")
def seed_demo(db: Session = Depends(get_db)):
    """Load sample cases for dashboard demo."""
    if db.query(func.count(CaseRecord.id)).scalar():
        return {"message": "Database already has cases"}

    samples = [
        {
            "ae_name": "Hepatotoxicity",
            "is_sae": True,
            "assignee": "Kim PV",
            "partner_reported": True,
            "source": "clinical_data",
            "cioms": CiomsFormData(
                reaction_meddra_pt="Hepatotoxicity",
                suspect_drug_name="DrugX 100mg",
                narrative="Elevated ALT/AST during phase III trial.",
                seriousness_hospitalization=True,
            ),
        },
        {
            "ae_name": "Nausea",
            "is_sae": False,
            "assignee": "Lee PV",
            "partner_reported": False,
            "source": "literature",
            "cioms": CiomsFormData(
                reaction_meddra_pt="Nausea",
                suspect_drug_name="DrugY",
                narrative="Mild nausea reported in published case series.",
            ),
        },
        {
            "ae_name": "Anaphylactic reaction",
            "is_sae": True,
            "assignee": "Kim PV",
            "partner_reported": False,
            "source": "sae_form",
            "cioms": CiomsFormData(
                reaction_meddra_pt="Anaphylactic reaction",
                suspect_drug_name="DrugZ infusion",
                seriousness_life_threatening=True,
                narrative="SAE form received from affiliate site.",
            ),
        },
    ]
    for i, s in enumerate(samples):
        record = CaseRecord(
            collection_date=date.today(),
            ae_name=s["ae_name"],
            is_sae=s["is_sae"],
            assignee=s["assignee"],
            partner_reported=s["partner_reported"],
            source=s["source"],
            status="draft",
            cioms_json=json.dumps(s["cioms"].model_dump(), ensure_ascii=False),
        )
        db.add(record)
    db.commit()
    return {"message": f"Created {len(samples)} demo cases"}
