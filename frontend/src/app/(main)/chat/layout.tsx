export default function ChatLayout({ children }: { children: React.ReactNode }) {
  return <div className="h-full flex flex-col overflow-hidden">{children}</div>;
}
