import type { NextConfig } from "next";
import path from "path";

const isProd = process.env.NODE_ENV === "production";

const nextConfig: NextConfig = {
  // Standalone output bundles everything needed to run without node_modules
  // Required for systemd-based deployment on DigitalOcean
  output: isProd ? "standalone" : undefined,

  // Pin the tracing root to this project directory so standalone/ is flat
  outputFileTracingRoot: __dirname,

  images: {
    remotePatterns: [
      {
        protocol: "https",
        hostname: "*.supabase.co",
      },
      {
        protocol: "https",
        hostname: "img.clerk.com",
      },
    ],
  },

  // Disable type-route checking in prod builds for speed
  typescript: {
    ignoreBuildErrors: isProd,
  },
  eslint: {
    ignoreDuringBuilds: isProd,
  },
};

export default nextConfig;
