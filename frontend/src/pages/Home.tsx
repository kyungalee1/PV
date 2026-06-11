import { useEffect, useRef, useState } from "react";
import {
  Download,
  FileText,
  Loader2,
  RefreshCw,
  Upload,
  Eye,
  List,
} from "lucide-react";
import { CIOMS_SECTIONS } from "../config/ciomsFields";
import { api, downloadHtml, emptyCioms, getApiBase } from "../api";
import { isDeployedApp } from "../config/apiBase";
import type { CiomsFormData } from "../types";

type Tab = "preview" | "fields";

export default function Home() {
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [serverOk, setServerOk] = useState<boolean | null>(null);
  const [backendVersion, setBackendVersion] = useState("");
  const [needsReconvert, setNeedsReconvert] = useState(false);
  const prevBackendVersion = useRef("");
  const [tab, setTab] = useState<Tab>("preview");
  const [filename, setFilename] = useState("");
  const [aeName, setAeName] = useState("");
  const [cioms, setCioms] = useState<CiomsFormData | null>(null);
  const [html, setHtml] = useState("");
  const [refreshing, setRefreshing] = useState(false);

  useEffect(() => {
    const check = () =>
      api
        .health()
        .then((h) => {
          setServerOk(true);
          const ver = h.extractor_version ?? "";
          if (
            prevBackendVersion.current &&
            ver &&
            prevBackendVersion.current !== ver
          ) {
            setNeedsReconvert(true);
          }
          prevBackendVersion.current = ver;
          setBackendVersion(ver);
        })
        .catch(() => {
          setServerOk(false);
          setBackendVersion("");
        });

    check();
    const timer = window.setInterval(check, 5000);
    const onFocus = () => check();
    window.addEventListener("focus", onFocus);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener("focus", onFocus);
    };
  }, []);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file) {
      setError("논문 PDF 파일을 선택해 주세요.");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const result = await api.convertLiterature(file);
      setFilename(result.filename);
      setAeName(result.ae_name);
      setCioms({ ...emptyCioms(), ...result.cioms });
      setHtml(result.html);
      setTab("preview");
    } catch (err) {
      setError(err instanceof Error ? err.message : "변환에 실패했습니다.");
    } finally {
      setLoading(false);
    }
  };

  const refreshHtml = async () => {
    if (!cioms) return;
    setRefreshing(true);
    try {
      const { html: next } = await api.renderHtml(cioms);
      setHtml(next);
      setTab("preview");
    } catch (err) {
      setError(err instanceof Error ? err.message : "HTML 생성 실패");
    } finally {
      setRefreshing(false);
    }
  };

  const reset = () => {
    setFile(null);
    setCioms(null);
    setHtml("");
    setFilename("");
    setAeName("");
    setError("");
    setTab("preview");
  };

  const hasResult = Boolean(cioms && html);

  return (
    <div className="min-h-screen">
      {/* App header */}
      <header className="sticky top-0 z-10 border-b border-white/60 bg-white/70 backdrop-blur-md">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-5 py-4">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-toss-blue text-white shadow-toss">
              <FileText size={20} />
            </div>
            <div>
              <h1 className="text-base font-bold text-toss-gray-900">CIOMS Converter</h1>
              <p className="text-xs text-toss-gray-500">논문 PDF → CIOMS HTML</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            {serverOk && backendVersion && (
              <span
                className="hidden rounded-full bg-emerald-50 px-2.5 py-1 text-xs font-medium text-emerald-700 sm:inline"
                title={getApiBase()}
              >
                API {backendVersion}
              </span>
            )}
            {hasResult && (
              <button
                type="button"
                onClick={reset}
                className="text-sm font-medium text-toss-gray-500 hover:text-toss-blue"
              >
                새 변환
              </button>
            )}
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-5 py-8">
        {serverOk === false && (
          <p className="mb-6 rounded-2xl bg-red-50 px-4 py-3 text-sm text-toss-red">
            {isDeployedApp() ? (
              <>
                API 서버에 연결되지 않습니다. Vercel → Settings → Environment Variables에{" "}
                <code className="text-xs">API_PROXY_TARGET</code> = Render 백엔드 URL
                (예: https://xxx.onrender.com)을 넣고 <strong>Redeploy</strong>하세요.
                Render 무료 플랜은 첫 요청에 1분 정도 걸릴 수 있습니다.
              </>
            ) : (
              <>
                서버에 연결되지 않습니다.{" "}
                <code className="text-xs">.\dev.ps1</code> 실행 후 새로고침하세요.
              </>
            )}
          </p>
        )}

        {needsReconvert && (
          <p className="mb-6 rounded-2xl bg-amber-50 px-4 py-3 text-sm text-amber-900">
            백엔드가 업데이트되었습니다 ({backendVersion}). 변경 내용을 보려면{" "}
            <strong>PDF를 다시 업로드</strong>해 주세요. (기존 화면 HTML은 이전
            추출 결과입니다.)
          </p>
        )}

        {!hasResult ? (
          <section className="mx-auto max-w-lg">
            <div className="mb-8 text-center">
              <h2 className="text-2xl font-bold text-toss-gray-900">논문을 CIOMS 양식으로</h2>
              <p className="mt-2 text-sm text-toss-gray-500">
                Case report PDF를 업로드하면 26개 항목을 추출하고 HTML을 바로 받을 수 있습니다.
              </p>
            </div>

            <form
              onSubmit={onSubmit}
              className="rounded-3xl border border-white/80 bg-white/90 p-8 shadow-toss backdrop-blur-sm"
            >
              <label
                className={`flex cursor-pointer flex-col items-center justify-center rounded-2xl border-2 border-dashed px-6 py-14 transition ${
                  file
                    ? "border-toss-blue bg-blue-50/50"
                    : "border-toss-gray-200 hover:border-toss-blue"
                }`}
              >
                <input
                  type="file"
                  accept=".pdf,application/pdf"
                  className="hidden"
                  onChange={(e) => setFile(e.target.files?.[0] || null)}
                />
                <Upload className="mb-3 text-toss-blue" size={40} />
                <p className="text-sm font-semibold text-toss-gray-800">
                  {file ? file.name : "논문 PDF를 선택하세요"}
                </p>
              </label>

              {error && (
                <p className="mt-4 rounded-xl bg-red-50 px-4 py-3 text-sm text-toss-red">{error}</p>
              )}

              <button
                type="submit"
                disabled={loading || !file}
                className="mt-6 flex w-full items-center justify-center gap-2 rounded-2xl bg-toss-blue py-4 text-sm font-bold text-white hover:bg-toss-blue-dark disabled:opacity-50"
              >
                {loading ? <Loader2 className="animate-spin" size={18} /> : null}
                {loading ? "분석 중…" : "CIOMS HTML 생성"}
              </button>
            </form>
          </section>
        ) : (
          <section className="space-y-4">
            <div className="rounded-2xl border border-white/80 bg-white/90 px-5 py-4 shadow-toss backdrop-blur-sm">
              <p className="text-sm font-semibold text-toss-gray-800">{filename}</p>
              <p className="mt-0.5 text-xs text-toss-gray-500">AE: {aeName}</p>
            </div>

            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => setTab("preview")}
                className={`flex items-center gap-2 rounded-xl px-4 py-2.5 text-sm font-semibold ${
                  tab === "preview"
                    ? "bg-toss-blue text-white"
                    : "bg-white/90 text-toss-gray-600"
                }`}
              >
                <Eye size={16} />
                HTML 미리보기
              </button>
              <button
                type="button"
                onClick={() => setTab("fields")}
                className={`flex items-center gap-2 rounded-xl px-4 py-2.5 text-sm font-semibold ${
                  tab === "fields"
                    ? "bg-toss-blue text-white"
                    : "bg-white/90 text-toss-gray-600"
                }`}
              >
                <List size={16} />
                26개 항목
              </button>
              <button
                type="button"
                onClick={() => downloadHtml(html, filename)}
                className="ml-auto flex items-center gap-2 rounded-xl bg-toss-blue px-4 py-2.5 text-sm font-bold text-white"
              >
                <Download size={16} />
                HTML 다운로드
              </button>
            </div>

            {tab === "preview" ? (
              <div className="rounded-2xl border border-white/80 bg-white shadow-toss">
                <p className="border-b border-toss-gray-100 px-4 py-2 text-xs text-toss-gray-500 md:hidden">
                  양식이 넓어요. 아래 미리보기 안에서 좌우로 스크롤해 주세요.
                </p>
                <iframe
                  title="CIOMS Preview"
                  srcDoc={html}
                  className="block h-[min(75vh,900px)] w-full max-w-full bg-white"
                  sandbox="allow-same-origin"
                />
              </div>
            ) : (
              <div className="space-y-4">
                <div className="flex justify-end">
                  <button
                    type="button"
                    onClick={refreshHtml}
                    disabled={refreshing}
                    className="flex items-center gap-2 rounded-xl border border-toss-gray-200 bg-white px-4 py-2 text-sm font-semibold"
                  >
                    {refreshing ? (
                      <Loader2 className="animate-spin" size={16} />
                    ) : (
                      <RefreshCw size={16} />
                    )}
                    수정 반영 → HTML 갱신
                  </button>
                </div>
                {CIOMS_SECTIONS.map((section) => (
                  <div
                    key={section.title}
                    className="rounded-2xl border border-white/80 bg-white/90 p-5 shadow-toss"
                  >
                    <h3 className="mb-3 text-sm font-bold text-toss-blue">{section.title}</h3>
                    <div className="grid gap-3 sm:grid-cols-2">
                      {section.fields.map((f) => (
                        <label
                          key={f.key}
                          className={`block text-sm ${f.multiline ? "sm:col-span-2" : ""}`}
                        >
                          <span className="mb-1 block text-xs font-medium text-toss-gray-500">
                            {f.label}
                          </span>
                          {f.checkbox ? (
                            <input
                              type="checkbox"
                              checked={Boolean(cioms![f.key])}
                              onChange={(e) =>
                                setCioms((c) => c && { ...c, [f.key]: e.target.checked })
                              }
                              className="h-4 w-4 rounded text-toss-blue"
                            />
                          ) : f.yn ? (
                            <select
                              value={String(cioms![f.key] ?? "NA")}
                              onChange={(e) =>
                                setCioms((c) => c && { ...c, [f.key]: e.target.value })
                              }
                              className="w-full rounded-xl border border-toss-gray-200 px-3 py-2 text-sm"
                            >
                              <option value="YES">YES</option>
                              <option value="NO">NO</option>
                              <option value="NA">NA</option>
                            </select>
                          ) : f.multiline ? (
                            <textarea
                              rows={3}
                              value={String(cioms![f.key] ?? "")}
                              onChange={(e) =>
                                setCioms((c) => c && { ...c, [f.key]: e.target.value })
                              }
                              className="w-full rounded-xl border border-toss-gray-200 px-3 py-2 text-sm"
                            />
                          ) : (
                            <input
                              type="text"
                              value={String(cioms![f.key] ?? "")}
                              onChange={(e) =>
                                setCioms((c) => c && { ...c, [f.key]: e.target.value })
                              }
                              className="w-full rounded-xl border border-toss-gray-200 px-3 py-2 text-sm"
                            />
                          )}
                        </label>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </section>
        )}
      </main>
    </div>
  );
}
