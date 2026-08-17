import { Link, NavLink, Route, Routes, useLocation } from "react-router-dom";
import { LayoutDashboard, FileText, LogOut, Database } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ReportList } from "@/routes/ReportList";
import { ReportView } from "@/routes/ReportView";
import { AdminLogin } from "@/routes/AdminLogin";
import { AdminInstances } from "@/routes/AdminInstances";
import { AdminReports } from "@/routes/AdminReports";
import { api } from "@/lib/api";
import { useQuery } from "@tanstack/react-query";
import { cn } from "@/lib/utils";

function App() {
  const location = useLocation();
  const { data: me } = useQuery({
    queryKey: ["me"],
    queryFn: () => api.get("/auth/me").then((r) => r.data).catch(() => null),
    retry: false,
  });

  const onLogout = async () => {
    await api.post("/auth/logout");
    window.location.href = "/";
  };

  const isAdminArea = location.pathname.startsWith("/admin") && location.pathname !== "/admin/login";

  return (
    <div className="min-h-screen flex flex-col">
      <header className="border-b bg-card">
        <div className="container mx-auto px-4 h-14 flex items-center justify-between">
          <div className="flex items-center gap-6">
            <Link to="/" className="font-semibold text-lg flex items-center gap-2">
              <FileText className="h-5 w-5 text-primary" />
              Jira Data Viewer
            </Link>
            <nav className="flex items-center gap-1">
              <NavLink
                to="/"
                end
                className={({ isActive }) =>
                  `px-3 py-1.5 rounded-md text-sm font-medium ${
                    isActive
                      ? "bg-secondary text-secondary-foreground"
                      : "text-muted-foreground hover:text-foreground"
                  }`
                }
              >
                Reports
              </NavLink>
              {me && (
                <NavLink
                  to="/admin/reports"
                  className={({ isActive }) =>
                    `px-3 py-1.5 rounded-md text-sm font-medium ${
                      isActive || isAdminArea
                        ? "bg-secondary text-secondary-foreground"
                        : "text-muted-foreground hover:text-foreground"
                    }`
                  }
                >
                  <LayoutDashboard className="inline h-4 w-4 mr-1" />
                  Admin
                </NavLink>
              )}
            </nav>
          </div>
          <div className="flex items-center gap-2">
            {me ? (
              <>
                <span className="text-sm text-muted-foreground">
                  Signed in as <span className="font-medium text-foreground">{me.username}</span>
                </span>
                <Button variant="ghost" size="sm" onClick={onLogout}>
                  <LogOut className="h-4 w-4 mr-1" /> Logout
                </Button>
              </>
            ) : (
              <Button asChild variant="ghost" size="sm">
                <Link to="/admin/login">Admin login</Link>
              </Button>
            )}
          </div>
        </div>

        {me && isAdminArea && (
          <div className="border-t bg-muted/30">
            <div className="container mx-auto px-4 h-10 flex items-center gap-1">
              <NavLink
                to="/admin/reports"
                end
                className={({ isActive }) =>
                  cn(
                    "px-3 py-1.5 rounded-md text-sm font-medium",
                    isActive
                      ? "bg-background text-foreground shadow-sm"
                      : "text-muted-foreground hover:text-foreground"
                  )
                }
              >
                <FileText className="inline h-3.5 w-3.5 mr-1" />
                Reports
              </NavLink>
              <NavLink
                to="/admin/instances"
                className={({ isActive }) =>
                  cn(
                    "px-3 py-1.5 rounded-md text-sm font-medium",
                    isActive
                      ? "bg-background text-foreground shadow-sm"
                      : "text-muted-foreground hover:text-foreground"
                  )
                }
              >
                <Database className="inline h-3.5 w-3.5 mr-1" />
                Instances
              </NavLink>
            </div>
          </div>
        )}
      </header>

      <main className="flex-1">
        <Routes>
          <Route path="/" element={<ReportList />} />
          <Route path="/r/:id" element={<ReportView />} />
          <Route path="/admin/login" element={<AdminLogin />} />
          <Route path="/admin/reports/*" element={<AdminReports />} />
          <Route path="/admin/instances" element={<AdminInstances />} />
        </Routes>
      </main>
    </div>
  );
}

export default App;
