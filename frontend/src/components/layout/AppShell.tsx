import { AppSidebar } from "@/components/layout/AppSidebar";
import { TopBar } from "@/components/layout/TopBar";

interface AppShellProps {
  children: React.ReactNode;
  /** Use overflow-hidden on main for full-height pages like chat */
  mainClassName?: string;
}

export function AppShell({ children, mainClassName }: AppShellProps) {
  return (
    <div className="flex h-screen bg-background overflow-hidden">
      <AppSidebar />
      <div className="flex flex-col flex-1 overflow-hidden min-w-0">
        <TopBar />
        <main
          className={
            mainClassName ?? "flex-1 overflow-y-auto p-6"
          }
        >
          {children}
        </main>
      </div>
    </div>
  );
}
