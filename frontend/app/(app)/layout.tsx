import AppSidebar from "@/components/AppSidebar";
import TopNav from "@/components/TopNav";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="app-shell">
      <AppSidebar />
      <div className="app-content">
        <TopNav />
        <main className="app-main">{children}</main>
      </div>
    </div>
  );
}
