/**
 * Vercel serverless proxy: /api/* → Render (or other) backend.
 * Set on Vercel: API_PROXY_TARGET=https://your-service.onrender.com
 */
export const config = {
  api: { bodyParser: false },
};

function readBody(req) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    req.on("data", (chunk) => chunks.push(chunk));
    req.on("end", () => resolve(Buffer.concat(chunks)));
    req.on("error", reject);
  });
}

export default async function handler(req, res) {
  const backend = (process.env.API_PROXY_TARGET || "")
    .trim()
    .replace(/\/$/, "");

  if (!backend) {
    res.status(503).json({
      detail:
        "Set API_PROXY_TARGET on Vercel (e.g. https://your-app.onrender.com) and redeploy.",
    });
    return;
  }

  const parts = req.query.path;
  const subpath = Array.isArray(parts) ? parts.join("/") : parts || "";
  const query =
    req.url && req.url.includes("?") ? req.url.slice(req.url.indexOf("?")) : "";
  const target = `${backend}/api/${subpath}${query}`;

  const headers = {};
  for (const [key, value] of Object.entries(req.headers)) {
    if (!value) continue;
    const lower = key.toLowerCase();
    if (lower === "host" || lower === "connection") continue;
    headers[key] = Array.isArray(value) ? value.join(", ") : value;
  }

  let body;
  if (req.method !== "GET" && req.method !== "HEAD") {
    body = await readBody(req);
  }

  try {
    const upstream = await fetch(target, {
      method: req.method,
      headers,
      body: body && body.length ? body : undefined,
    });

    res.status(upstream.status);
    upstream.headers.forEach((value, key) => {
      const lower = key.toLowerCase();
      if (lower === "transfer-encoding" || lower === "connection") return;
      res.setHeader(key, value);
    });

    const buf = Buffer.from(await upstream.arrayBuffer());
    res.send(buf);
  } catch (err) {
    res.status(502).json({
      detail: err?.message || "Backend unreachable. Is Render service running?",
    });
  }
}
