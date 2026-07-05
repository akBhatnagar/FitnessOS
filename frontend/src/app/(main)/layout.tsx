import { AppShell } from "@/components/layout/AppShell";

const clerkKey = process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY ?? "";
const hasClerk =
  (clerkKey.startsWith("pk_test_") || clerkKey.startsWith("pk_live_")) &&
  clerkKey.length > 30;

export default async function MainLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  if (hasClerk) {
    const { auth } = await import("@clerk/nextjs/server");
    const { userId } = await auth();
    if (!userId) {
      const { redirect } = await import("next/navigation");
      redirect("/auth/sign-in");
    }
  }

  return <AppShell>{children}</AppShell>;
}
