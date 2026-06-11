export interface CiomsFormData {
  report_type: string;
  country_of_occurrence: string;
  date_of_report: string;
  reporter_type: string;
  reporter_name: string;
  reporter_organization: string;
  reporter_country: string;
  reporter_qualification: string;
  patient_initials: string;
  patient_date_of_birth: string;
  patient_age: string;
  patient_age_unit: string;
  patient_sex: string;
  patient_weight_kg: string;
  patient_height_cm: string;
  medical_history: string;
  concomitant_medications: string;
  suspect_drug_name: string;
  suspect_drug_active_substance: string;
  suspect_drug_dose: string;
  suspect_drug_route: string;
  suspect_drug_indication: string;
  suspect_drug_start_date: string;
  suspect_drug_stop_date: string;
  suspect_drug_batch_lot: string;
  therapy_duration: string;
  reaction_meddra_pt: string;
  reaction_verbatim: string;
  reaction_onset_date: string;
  reaction_onset_display: string;
  reaction_end_date: string;
  reaction_outcome: string;
  seriousness_death: boolean;
  seriousness_life_threatening: boolean;
  seriousness_hospitalization: boolean;
  seriousness_disability: boolean;
  seriousness_congenital_anomaly: boolean;
  seriousness_other_medically_important: boolean;
  dechallenge_abate: string;
  dechallenge_reappear: string;
  manufacturer_name_address: string;
  mfr_control_no: string;
  date_received_manufacturer: string;
  report_source_cioms: string;
  cioms_report_type: string;
  narrative: string;
  causality_assessment: string;
  company_comment: string;
}

export interface CaseRecord {
  id: number;
  collection_date: string | null;
  ae_name: string;
  is_sae: boolean;
  assignee: string;
  partner_reported: boolean;
  source: string;
  source_file: string;
  status: string;
  cioms: CiomsFormData;
  has_pdf: boolean;
  created_at: string;
  updated_at: string;
}

export interface DashboardStats {
  total_cases: number;
  sae_count: number;
  non_sae_count: number;
  partner_reported_count: number;
  completed_count: number;
  draft_count: number;
  by_source: { name: string; value: number }[];
  by_assignee: { name: string; value: number }[];
  monthly_trend: { month: string; count: number }[];
  sae_ratio: number;
}
