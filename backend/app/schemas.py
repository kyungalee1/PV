from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field


class CiomsFormData(BaseModel):
    """ICH E2B(R3) aligned CIOMS I fields (English for FDA submission)."""

    report_type: str = "Spontaneous"
    country_of_occurrence: str = ""
    date_of_report: str = ""
    reporter_type: str = "Health professional"
    reporter_name: str = ""
    reporter_organization: str = ""
    reporter_country: str = ""
    reporter_qualification: str = ""

    patient_initials: str = ""
    patient_date_of_birth: str = ""
    patient_age: str = ""
    patient_age_unit: str = "Year"
    patient_sex: str = ""
    patient_weight_kg: str = ""
    patient_height_cm: str = ""

    medical_history: str = ""
    concomitant_medications: str = ""

    suspect_drug_name: str = ""
    suspect_drug_active_substance: str = ""
    suspect_drug_dose: str = ""
    suspect_drug_route: str = ""
    suspect_drug_indication: str = ""
    suspect_drug_start_date: str = ""
    suspect_drug_stop_date: str = ""
    suspect_drug_batch_lot: str = ""
    therapy_duration: str = ""

    reaction_meddra_pt: str = ""
    reaction_verbatim: str = ""
    reaction_onset_date: str = ""
    reaction_onset_display: str = ""
    reaction_end_date: str = ""
    reaction_outcome: str = ""
    seriousness_death: bool = False
    seriousness_life_threatening: bool = False
    seriousness_hospitalization: bool = False
    seriousness_disability: bool = False
    seriousness_congenital_anomaly: bool = False
    seriousness_other_medically_important: bool = False

    dechallenge_abate: str = "NA"  # YES | NO | NA
    dechallenge_reappear: str = "NA"

    manufacturer_name_address: str = ""
    mfr_control_no: str = ""
    date_received_manufacturer: str = ""
    report_source_cioms: str = ""  # STUDY | LITERATURE | AUTHORITY | HEALTH PROFESSIONAL | OTHER
    cioms_report_type: str = "INITIAL"  # INITIAL | FOLLOWUP | FINAL

    narrative: str = ""
    causality_assessment: str = ""
    company_comment: str = ""


class CaseCreate(BaseModel):
    collection_date: date | None = None
    ae_name: str = ""
    is_sae: bool = False
    assignee: str = ""
    partner_reported: bool = False
    source: str = ""
    cioms: CiomsFormData | None = None


class CaseUpdate(BaseModel):
    collection_date: date | None = None
    ae_name: str | None = None
    is_sae: bool | None = None
    assignee: str | None = None
    partner_reported: bool | None = None
    source: str | None = None
    status: str | None = None
    cioms: CiomsFormData | None = None


class CaseResponse(BaseModel):
    id: int
    collection_date: date | None
    ae_name: str
    is_sae: bool
    assignee: str
    partner_reported: bool
    source: str
    source_file: str
    status: str
    cioms: dict[str, Any]
    has_pdf: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class LiteratureConvertResponse(BaseModel):
    filename: str
    ae_name: str
    cioms: dict[str, Any]
    html: str


class LiteratureHtmlRequest(BaseModel):
    cioms: dict[str, Any]
    filename: str = "CIOMS_report"


class DashboardStats(BaseModel):
    total_cases: int = 0
    sae_count: int = 0
    non_sae_count: int = 0
    partner_reported_count: int = 0
    completed_count: int = 0
    draft_count: int = 0
    by_source: list[dict[str, Any]] = Field(default_factory=list)
    by_assignee: list[dict[str, Any]] = Field(default_factory=list)
    monthly_trend: list[dict[str, Any]] = Field(default_factory=list)
    sae_ratio: float = 0.0
