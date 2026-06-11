import type { CiomsFormData } from "./types";
import { isDeployedApp, resolveApiBase } from "./config/apiBase";

export function getApiBase(): string {
  return resolveApiBase();
}

function formatDetail(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((d) =>
        typeof d === "object" && d && "msg" in d
          ? String((d as { msg: string }).msg)
          : String(d),
      )
      .join("; ");
  }
  return "Request failed";
}

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const isUpload = options?.body instanceof FormData;
  const controller = new AbortController();
  const timeoutMs = isUpload ? 300_000 : isDeployedApp() ? 90_000 : 60_000;
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const res = await fetch(`${getApiBase()}${url}`, {
      ...options,
      signal: controller.signal,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(formatDetail(err.detail) || res.statusText);
    }
    return res.json();
  } catch (e) {
    if (e instanceof Error) {
      if (e.name === "AbortError") {
        throw new Error("요청 시간이 초과되었습니다. 잠시 후 다시 시도해 주세요.");
      }
      if (e.message === "Failed to fetch" || e instanceof TypeError) {
        if (isDeployedApp()) {
          throw new Error(
            "API 서버에 연결할 수 없습니다. Vercel에 API_PROXY_TARGET(Render URL)을 설정했는지, Render 백엔드가 실행 중인지 확인해 주세요.",
          );
        }
        throw new Error(
          "서버에 연결할 수 없습니다. 백엔드가 실행 중인지 확인해 주세요.",
        );
      }
    }
    throw e;
  } finally {
    clearTimeout(timer);
  }
}

export type ConvertResult = {
  filename: string;
  ae_name: string;
  cioms: CiomsFormData;
  html: string;
};

export const api = {
  health: () =>
    request<{ status: string; extractor_version?: string }>("/health"),

  convertLiterature: async (file: File): Promise<ConvertResult> => {
    const fd = new FormData();
    fd.append("file", file);
    return request<ConvertResult>("/literature/convert", { method: "POST", body: fd });
  },

  renderHtml: (cioms: CiomsFormData) =>
    request<{ html: string }>("/literature/html", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ cioms, filename: "CIOMS_report" }),
    }),
};

export const emptyCioms = (): CiomsFormData => ({
  report_type: "Literature",
  country_of_occurrence: "",
  date_of_report: new Date().toISOString().slice(0, 10),
  reporter_type: "Health professional",
  reporter_name: "",
  reporter_organization: "",
  reporter_country: "",
  reporter_qualification: "",
  patient_initials: "",
  patient_date_of_birth: "",
  patient_age: "",
  patient_age_unit: "Year",
  patient_sex: "",
  patient_weight_kg: "",
  patient_height_cm: "",
  medical_history: "",
  concomitant_medications: "",
  suspect_drug_name: "",
  suspect_drug_active_substance: "",
  suspect_drug_dose: "",
  suspect_drug_route: "",
  suspect_drug_indication: "",
  suspect_drug_start_date: "",
  suspect_drug_stop_date: "",
  suspect_drug_batch_lot: "",
  therapy_duration: "",
  reaction_meddra_pt: "",
  reaction_verbatim: "",
  reaction_onset_date: "",
  reaction_onset_display: "",
  reaction_end_date: "",
  reaction_outcome: "",
  seriousness_death: false,
  seriousness_life_threatening: false,
  seriousness_hospitalization: false,
  seriousness_disability: false,
  seriousness_congenital_anomaly: false,
  seriousness_other_medically_important: false,
  dechallenge_abate: "NA",
  dechallenge_reappear: "NA",
  manufacturer_name_address: "",
  mfr_control_no: "",
  date_received_manufacturer: "",
  report_source_cioms: "LITERATURE",
  cioms_report_type: "INITIAL",
  narrative: "",
  causality_assessment: "",
  company_comment: "",
});

export function downloadHtml(html: string, filename: string) {
  const blob = new Blob([html], { type: "text/html;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename.replace(/\.pdf$/i, "") + "_CIOMS.html";
  a.click();
  URL.revokeObjectURL(url);
}
