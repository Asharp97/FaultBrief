import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  distDir: process.env.FAULTBRIEF_SMOKE === "1" ? ".next-smoke" : ".next",
  agentRules: false,
  poweredByHeader: false,
  reactStrictMode: true,
};

export default nextConfig;
