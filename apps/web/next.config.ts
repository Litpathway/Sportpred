import type { NextConfig } from "next";

const config: NextConfig = {
  output: "standalone",
  // Optional local/CI limit for hosts with small commit-memory budgets.
  ...(Number.isInteger(Number(process.env.NEXT_BUILD_CPUS)) && Number(process.env.NEXT_BUILD_CPUS) > 0
    ? {experimental: {cpus: Number(process.env.NEXT_BUILD_CPUS)}} : {}),
  poweredByHeader: false,
  async rewrites() {
    // Vercel's root service router sends /api directly to FastAPI.
    if (process.env.VERCEL === "1") return [];
    return [{ source: "/api/:path*", destination: `${process.env.API_INTERNAL_URL || "http://127.0.0.1:8000"}/api/:path*` }];
  },
  async headers() {
    return [{ source: "/:path*", headers: [
      { key: "X-Content-Type-Options", value: "nosniff" },
      { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
      { key: "X-Frame-Options", value: "DENY" },
      { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
    ] }];
  },
};
export default config;
