import type { NextConfig } from "next";

// The browser only ever talks to this Next.js server; /api/* is proxied to the FastAPI backend,
// so the backend URL (and any key it holds) is never exposed to frontend code.
const backend = process.env.BACKEND_URL ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  // Dev only: let a phone on the same Wi-Fi (private LAN addresses) load the dev server, e.g. http://192.168.1.9:3000
  allowedDevOrigins: ["192.168.*.*", "10.*.*.*", "172.*.*.*"],
  cacheComponents: false,
  partialPrefetching: false,
  async headers() {
    return [
      // Microphone (voice advisor) and camera (KYC photo) are allowed for this site only; location etc. stay off.
      { source: "/:path*", headers: [{ key: "Permissions-Policy", value: "microphone=(self), camera=(self), geolocation=(), payment=(self)" }] },
      // The service worker must always be re-fetched so an update reaches phones promptly.
      { source: "/sw.js", headers: [{ key: "Cache-Control", value: "no-cache, no-store, must-revalidate" }, { key: "Service-Worker-Allowed", value: "/" }] },
    ];
  },
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${backend}/api/:path*` }];
  },
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
