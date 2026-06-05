import type { CiomsFormData } from "../types";

export type FieldDef = {
  key: keyof CiomsFormData;
  label: string;
  multiline?: boolean;
  checkbox?: boolean;
  yn?: boolean;
};

export type CiomsSection = {
  title: string;
  fields: FieldDef[];
};

/** CIOMS Form I — 26 fillable items in 4 sections */
export const CIOMS_SECTIONS: CiomsSection[] = [
  {
    title: "I. Reaction Information",
    fields: [
      { key: "patient_initials", label: "1. Patient Initials (first, last)" },
      { key: "country_of_occurrence", label: "1a. Country" },
      { key: "patient_date_of_birth", label: "2. Date of Birth" },
      { key: "patient_age", label: "2a. Age (years)" },
      { key: "patient_sex", label: "3. Sex" },
      { key: "reaction_meddra_pt", label: "4–6. Reaction (term)" },
      { key: "reaction_onset_date", label: "4–6. Reaction Onset (date)" },
      { key: "narrative", label: "7 + 13. Describe Reaction(s)", multiline: true },
      { key: "seriousness_death", label: "8. Patient Died", checkbox: true },
      { key: "seriousness_life_threatening", label: "9. Life Threatening", checkbox: true },
      { key: "seriousness_hospitalization", label: "10. Hospitalization", checkbox: true },
      { key: "seriousness_disability", label: "11. Disability/Incapacity", checkbox: true },
      { key: "seriousness_congenital_anomaly", label: "12a. Congenital Anomaly", checkbox: true },
      {
        key: "seriousness_other_medically_important",
        label: "12b. Other Medically Important",
        checkbox: true,
      },
    ],
  },
  {
    title: "II. Suspect Drug(s) Information",
    fields: [
      { key: "suspect_drug_name", label: "14. Suspect Drug(s)" },
      { key: "suspect_drug_active_substance", label: "14. Active Substance" },
      { key: "suspect_drug_dose", label: "15. Daily Dose(s)" },
      { key: "suspect_drug_route", label: "16. Route(s) of Administration" },
      { key: "suspect_drug_indication", label: "17. Indication(s) for Use" },
      { key: "suspect_drug_start_date", label: "18. Therapy Dates (from)" },
      { key: "suspect_drug_stop_date", label: "18. Therapy Dates (to)" },
      { key: "therapy_duration", label: "19. Therapy Duration" },
      { key: "dechallenge_abate", label: "20. Abate after stopping? (YES/NO/NA)", yn: true },
      { key: "dechallenge_reappear", label: "21. Reappear after reintro? (YES/NO/NA)", yn: true },
    ],
  },
  {
    title: "III. Concomitant Drug(s) and History",
    fields: [
      { key: "concomitant_medications", label: "22. Concomitant Drug(s)", multiline: true },
      { key: "medical_history", label: "23. Other Relevant History", multiline: true },
    ],
  },
  {
    title: "IV. Manufacturer Information",
    fields: [
      { key: "manufacturer_name_address", label: "24a. Manufacturer Name & Address", multiline: true },
      { key: "mfr_control_no", label: "24b. MFR Control No." },
      { key: "date_received_manufacturer", label: "24c. Date Received by Manufacturer" },
      { key: "report_source_cioms", label: "24d. Report Source" },
      { key: "cioms_report_type", label: "25a. Report Type (INITIAL/FOLLOWUP/FINAL)" },
      { key: "reporter_name", label: "25b. Reporter Name" },
      { key: "reporter_organization", label: "25b. Reporter Organization" },
      { key: "reporter_country", label: "25b. Reporter Country" },
      { key: "date_of_report", label: "Date of This Report" },
      { key: "company_comment", label: "26. Remarks", multiline: true },
    ],
  },
];
