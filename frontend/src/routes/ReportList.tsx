import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { FileText, ChevronRight } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";
import { formatIst } from "@/lib/ist";
import type { ReportSummary } from "@/types/report";

export function ReportList() {
  const { data, isLoading } = useQuery({
    queryKey: ["public-reports"],
    queryFn: () => api.get<ReportSummary[]>("/reports").then((r) => r.data),
  });

  return (
    <div className="container mx-auto px-4 py-8">
      <div className="mb-8">
        <h1 className="text-3xl font-semibold tracking-tight">Reports</h1>
        <p className="text-muted-foreground mt-1">
          Pick a report to view its data. Filter by any field, set a date range, and export to CSV.
        </p>
      </div>

      {isLoading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          <Skeleton className="h-36" />
          <Skeleton className="h-36" />
          <Skeleton className="h-36" />
        </div>
      ) : (data?.length ?? 0) === 0 ? (
        <Card>
          <CardContent className="py-12 text-center">
            <FileText className="h-10 w-10 mx-auto text-muted-foreground/40" />
            <p className="mt-4 text-muted-foreground">No reports yet.</p>
            <p className="text-sm text-muted-foreground">
              An admin needs to configure a Jira instance and a report.
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {data!.map((r) => (
            <Link key={r.id} to={`/r/${r.id}`} className="group">
              <Card className="hover:border-primary/50 transition-colors h-full">
                <CardHeader>
                  <div className="flex items-start justify-between">
                    <FileText className="h-5 w-5 text-primary" />
                    <ChevronRight className="h-4 w-4 text-muted-foreground group-hover:text-primary transition-colors" />
                  </div>
                  <CardTitle className="text-lg mt-2">{r.name}</CardTitle>
                  <CardDescription>
                    {r.selected_fields.length} fields · last sync{" "}
                    {r.last_run_at ? formatIst(r.last_run_at) : "never"}
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  {r.last_run_status ? (
                    <Badge
                      variant={
                        r.last_run_status === "success"
                          ? "success"
                          : r.last_run_status === "failed"
                          ? "destructive"
                          : "secondary"
                      }
                    >
                      {r.last_run_status}
                    </Badge>
                  ) : (
                    <Badge variant="outline">No data</Badge>
                  )}
                </CardContent>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
