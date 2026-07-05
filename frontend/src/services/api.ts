/**
 * Centralized API client using Axios.
 *
 * In development (no Clerk keys), requests use the "dev-token" bypass.
 * In production, the Clerk auth token is injected via the useAuth hook.
 */

import axios from "axios";

// Strip any trailing /api from the base URL so that paths like /api/v1/...
// are not doubled (e.g. baseURL=".../api" + url="/api/v1/..." → ".../api/api/v1/...").
const _rawBase = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8001";
const _baseURL = _rawBase.replace(/\/api\/?$/, "");

export const apiClient = axios.create({
  baseURL: _baseURL,
  timeout: 30_000,
  // Required for Nginx Basic Auth — tells browser to include stored credentials
  // (Basic Auth headers) in programmatic XHR/fetch requests, not just page loads
  withCredentials: true,
  headers: {
    "Content-Type": "application/json",
  },
});

// A real Clerk key is base64-encoded after the prefix — always longer than 30 chars
const clerkKey = process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY ?? "";
const isDevMode =
  !clerkKey ||
  !((clerkKey.startsWith("pk_test_") || clerkKey.startsWith("pk_live_")) && clerkKey.length > 30);

// Request interceptor — inject auth token
apiClient.interceptors.request.use(async (config) => {
  if (isDevMode) {
    config.headers["Authorization"] = "Bearer dev-token";
    return config;
  }

  // Production: get token from Clerk session storage (set by useClerkToken hook)
  if (typeof window !== "undefined") {
    const token = window.sessionStorage.getItem("fitnessos_clerk_token");
    if (token) {
      config.headers["Authorization"] = `Bearer ${token}`;
    }
  }
  return config;
});

// Response interceptor — normalize errors
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    const message =
      error.response?.data?.detail ??
      error.response?.data?.message ??
      error.message ??
      "An unexpected error occurred";

    return Promise.reject(new Error(message));
  }
);

export function useApiClient() {
  return apiClient;
}
