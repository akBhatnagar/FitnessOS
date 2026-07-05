import { NextResponse, type NextRequest } from "next/server";

// A real Clerk publishable key is base64-encoded after the prefix and is long (>30 chars)
// Placeholder keys like pk_test_placeholder are rejected by Clerk's SDK even at runtime
const clerkKey = process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY ?? "";
const hasValidClerkKey =
  clerkKey.startsWith("pk_test_") || clerkKey.startsWith("pk_live_")
    ? clerkKey.length > 30 // real keys are base64 encoded, much longer than placeholder
    : false;

// When real Clerk keys are present we use clerkMiddleware; otherwise a simple
// passthrough that lets all routes through so dev works without an account.
let middlewareHandler: (req: NextRequest) => Promise<NextResponse> | NextResponse;

if (hasValidClerkKey) {
  // Dynamic require so the module isn't even parsed when keys are missing.
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const { clerkMiddleware, createRouteMatcher } = require("@clerk/nextjs/server");
  const isPublicRoute = createRouteMatcher(["/auth/(.*)", "/api/health"]);
  middlewareHandler = clerkMiddleware(async (auth: { protect: () => Promise<void> }, request: NextRequest) => {
    if (!isPublicRoute(request)) {
      await auth.protect();
    }
  });
} else {
  middlewareHandler = (_req: NextRequest) => NextResponse.next();
}

export default middlewareHandler;

export const config = {
  matcher: [
    "/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)",
    "/(api|trpc)(.*)",
  ],
};
