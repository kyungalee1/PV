/** Resolve API base URL for local dev, Vercel, and mobile browsers. */

/** Production Render API — direct calls avoid Vercel proxy timeouts on PDF convert. */
const PRODUCTION_RENDER_API = "https://pv-qce5.onrender.com/api";

function normalizeApiBase(base: string): string {
  const trimmed = base.trim().replace(/\/$/, "");
  if (!trimmed) return trimmed;
  if (trimmed.endsWith("/api")) return trimmed;
  return `${trimmed}/api`;
}

export function resolveApiBase(): string {
  const envBase = (import.meta.env.VITE_API_BASE as string | undefined)?.trim();
  const host =
    typeof window !== "undefined" ? window.location.hostname.toLowerCase() : "";
  const isLocalHost =
    host === "localhost" || host === "127.0.0.1" || host === "[::1]";
  const isVercelHost =
    host.endsWith(".vercel.app") || host.endsWith(".vercel.dev");

  const pointsToLocal =
    !!envBase &&
    (envBase.includes("127.0.0.1") || envBase.includes("localhost"));

  // Deployed app: call Render directly (Vercel /api proxy times out on long PDF parses)
  if (isVercelHost || (import.meta.env.PROD && !isLocalHost)) {
    if (envBase && !pointsToLocal) {
      return normalizeApiBase(envBase);
    }
    return PRODUCTION_RENDER_API;
  }

  if (envBase && !pointsToLocal) {
    return normalizeApiBase(envBase);
  }

  // Local dev on same machine — Vite proxies /api → localhost:8000
  if (envBase && pointsToLocal && isLocalHost) {
    return normalizeApiBase(envBase);
  }

  return "/api";
}

export function isDeployedApp(): boolean {
  if (typeof window === "undefined") return import.meta.env.PROD;
  const host = window.location.hostname.toLowerCase();
  return (
    import.meta.env.PROD ||
    host.endsWith(".vercel.app") ||
    host.endsWith(".vercel.dev")
  );
}

export function apiBaseLabel(): string {
  const base = resolveApiBase();
  if (base === "/api") return "local proxy → backend";
  if (base.includes("onrender.com")) return "Render API (direct)";
  return base;
}
