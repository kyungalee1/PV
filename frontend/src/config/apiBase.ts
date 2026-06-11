/** Resolve API base URL for local dev, Vercel, and mobile browsers. */

export function resolveApiBase(): string {
  const envBase = (import.meta.env.VITE_API_BASE as string | undefined)
    ?.trim()
    .replace(/\/$/, "");
  const host =
    typeof window !== "undefined" ? window.location.hostname.toLowerCase() : "";
  const isLocalHost =
    host === "localhost" || host === "127.0.0.1" || host === "[::1]";

  const pointsToLocal =
    !!envBase &&
    (envBase.includes("127.0.0.1") || envBase.includes("localhost"));

  // Production/public URL: never call 127.0.0.1 (breaks mobile & Vercel)
  if (envBase && !pointsToLocal) {
    return envBase;
  }

  // Local dev on same machine
  if (envBase && pointsToLocal && isLocalHost) {
    return envBase;
  }

  // Vercel serverless proxy at /api/* (see frontend/api/[...path].js)
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
  if (base === "/api") return "Vercel proxy → Render";
  return base;
}
