// Force dynamic rendering — Clerk requires runtime auth context
export const dynamic = "force-dynamic";

import type { Metadata, Viewport } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import { ThemeProvider } from "next-themes";
import { Toaster } from "sonner";
import { QueryProvider } from "@/components/shared/QueryProvider";
import "./globals.css";

const fontSans = Inter({
  subsets: ["latin"],
  variable: "--font-sans",
  display: "swap",
});

const fontMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: {
    default: "FitnessOS — Your AI Personal Trainer",
    template: "%s | FitnessOS",
  },
  description:
    "A multi-agent AI operating system that remembers everything, learns continuously, and becomes your elite personal trainer.",
  keywords: ["fitness", "AI trainer", "personal training", "nutrition", "swimming", "weight loss"],
  authors: [{ name: "FitnessOS" }],
  openGraph: {
    type: "website",
    locale: "en_IN",
    url: "https://fitnessos.app",
    title: "FitnessOS — Your AI Personal Trainer",
    description: "Your AI personal trainer that never forgets and keeps getting smarter.",
    siteName: "FitnessOS",
  },
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#ffffff" },
    { media: "(prefers-color-scheme: dark)", color: "#09090b" },
  ],
};

const clerkKey = process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY ?? "";
const hasClerk =
  (clerkKey.startsWith("pk_test_") || clerkKey.startsWith("pk_live_")) &&
  clerkKey.length > 30; // real keys are much longer than placeholders

async function ClerkWrapper({ children }: { children: React.ReactNode }) {
  if (!hasClerk) return <>{children}</>;
  const { ClerkProvider } = await import("@clerk/nextjs");
  return <ClerkProvider>{children}</ClerkProvider>;
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <ClerkWrapper>
      <html lang="en" suppressHydrationWarning>
        <body className={`${fontSans.variable} ${fontMono.variable} font-sans antialiased`}>
          <ThemeProvider
            attribute="class"
            defaultTheme="dark"
            enableSystem
            disableTransitionOnChange
          >
            <QueryProvider>
              {children}
              <Toaster
                position="top-right"
                richColors
                closeButton
                duration={4000}
              />
            </QueryProvider>
          </ThemeProvider>
        </body>
      </html>
    </ClerkWrapper>
  );
}
