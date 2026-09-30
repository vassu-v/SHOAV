import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Set NEXT_DIST_DIR to build/dev into a separate folder without touching a served .next
  allowedDevOrigins: ["127.0.0.1"],
  distDir: process.env.NEXT_DIST_DIR || ".next",
};

export default nextConfig;
