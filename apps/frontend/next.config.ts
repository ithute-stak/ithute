import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  env: {
    // Keep every browser route on Ithute's same-origin API unless a build
    // explicitly supplies another public endpoint. This centrally neutralizes
    // historical localhost fallbacks in legacy pages and prevents a production
    // build from ever trying to call a visitor's localhost.
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL || "/api/v1",
  },
};

export default nextConfig;
