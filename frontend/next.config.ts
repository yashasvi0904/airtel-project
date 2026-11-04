import type { NextConfig } from "next";

// The browser only ever talks to this Next.js server; /api/* is proxied to the FastAPI backend,
// so the backend URL (and any key it holds) is never exposed to frontend code.
const backend = process.env.BACKEND_URL ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  cacheComponents: false,
  partialPrefetching: false,
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
