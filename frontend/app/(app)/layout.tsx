import AppSidebar from "@/components/AppSidebar";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="app-shell">
      <AppSidebar />
      <div className="app-content">
        <main className="app-main">{children}</main>
      </div>
    </div>
  );
}
