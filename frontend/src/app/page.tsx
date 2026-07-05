import { redirect } from "next/navigation";

const clerkKey = process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY ?? "";
const hasClerk =
  (clerkKey.startsWith("pk_test_") || clerkKey.startsWith("pk_live_")) &&
  clerkKey.length > 30;

export default async function HomePage() {
  if (!hasClerk) {
    // Dev mode: go straight to dashboard
    redirect("/dashboard");
  }

  // With real Clerk keys, check auth
  const { auth } = await import("@clerk/nextjs/server");
  const { userId } = await auth();

  if (userId) {
    redirect("/dashboard");
  } else {
    redirect("/auth/sign-in");
  }
}
