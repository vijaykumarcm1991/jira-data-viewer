import { useState } from "react";
import { Link, Route, Routes, useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Edit, Eraser, FilePlus, Loader2, Play, Sparkles, Square, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { ReportForm } from "@/components/ReportForm";
import { formatIst } from "@/lib/ist";
import type { Report, RunHistory } from "@/types/report";

export function AdminReports() {
  return (
    <Routes>
      <Route index element={<ReportsList />} />
      <Route path="new" element={<ReportForm mode="create" />} />
      <Route path=":id/edit" element={<EditWrapper />} />
    </Routes>
  );
}

function EditWrapper() {
  const { id } = useParams();
  return <ReportForm mode="edit" key={id} />;
}

function ReportsList() {
  const qc = useQueryClient();
  const { data, isLoading } = useQuery({
    queryKey: ["reports"],
    queryFn: () => api.get<Report[]>("/admin/reports").then((r) => r.data),
  });
  const { data: runs } = useQuery({
    queryKey: ["runs"],
    queryFn: () => api.get<RunHistory[]>("/admin/runs?limit=20").then((r) => r.data),
    refetchInterval: 2000,
  });
  const del = useMutation({
    mutationFn: (id: number) => api.delete(`/admin/reports/${id}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["reports"] });
      toast.success("Report deleted");
    },
    onError: (e: any) => toast.error(e?.response?.data?.detail || "Delete failed"),
  });
  const runNow = useMutation({
    mutationFn: (id: number) => api.post(`/admin/reports/${id}/run-now`),
    onSuccess: (_d, id) => {
      qc.invalidateQueries({ queryKey: ["runs"] });
      qc.invalidateQueries({ queryKey: ["reports"] });
      toast.success(`Sync queued for report #${id}`);
    },
    onError: (e: any) => toast.error(e?.response?.data?.detail || "Run failed"),
  });
  const truncate = useMutation({
    mutationFn: (id: number) => api.post(`/admin/reports/${id}/truncate`),
    onSuccess: (_d, id) => {
      qc.invalidateQueries({ queryKey: ["reports"] });
      qc.invalidateQueries({ queryKey: ["runs"] });
      toast.success(`Report #${id} table truncated — next sync starts from zero`);
    },
    onError: (e: any) => toast.error(e?.response?.data?.detail || "Truncate failed"),
  });
  const cleanup = useMutation({
    mutationFn: (id: number) => api.post(`/admin/reports/${id}/cleanup`),
    onSuccess: (r, id) => {
      qc.invalidateQueries({ queryKey: ["reports"] });
      toast.success(
        `Cleanup complete for report #${id}: removed ${r.data.rows_deleted} duplicate row(s)`
      );
    },
    onError: (e: any) => toast.error(e?.response?.data?.detail || "Cleanup failed"),
  });
  const cancelRun = useMutation({
    mutationFn: (runId: number) => api.post(`/admin/runs/${runId}/cancel`),
    onSuccess: (r, runId) => {
      qc.invalidateQueries({ queryKey: ["runs"] });
      const msg = r.data?.status === "interrupted"
        ? "Run was already stopped (stale entry cleared)"
        : "Stop requested — current page will finish, then the run ends";
      toast.success(msg);
    },
    onError: (e: any) => toast.error(e?.response?.data?.detail || "Cancel failed"),
  });

  return (
    <div className="container mx-auto px-4 py-8">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold">Reports</h1>
          <p className="text-sm text-muted-foreground">
            Each report has its own JQL, fields, schedule, and a dedicated DB table.
          </p>
        </div>
        <Button asChild>
          <Link to="/admin/reports/new">
            <FilePlus className="h-4 w-4 mr-2" /> New report
          </Link>
        </Button>
      </div>

      <Card className="mb-6">
        <CardHeader>
          <CardTitle className="text-base">Configured reports</CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <Skeleton className="h-32 w-full" />
          ) : (data?.length ?? 0) === 0 ? (
            <p className="text-sm text-muted-foreground py-8 text-center">No reports yet.</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Name</TableHead>
                  <TableHead>Instance</TableHead>
                  <TableHead>Schedule</TableHead>
                  <TableHead>Fields</TableHead>
                  <TableHead>Last run</TableHead>
                  <TableHead className="w-[180px]"></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data!.map((r) => (
                  <TableRow key={r.id}>
                    <TableCell className="font-medium">
                      <div className="flex items-center gap-2">
                        {r.name}
                        {!r.is_active && <Badge variant="warning">Paused</Badge>}
                      </div>
                    </TableCell>
                    <TableCell className="text-muted-foreground text-sm">{r.jira_instance_name}</TableCell>
                    <TableCell className="font-mono text-xs">{r.schedule_cron}</TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {r.selected_fields.length} fields
                      {r.history_retention_days > 0 && (
                        <span className="ml-2 text-xs px-1.5 py-0.5 rounded bg-secondary">
                          keep {r.history_retention_days}d
                        </span>
                      )}
                    </TableCell>
                    <TableCell>
                      {r.last_run_at ? (
                        <div className="text-sm">
                          <div>{formatIst(r.last_run_at)}</div>
                          <Badge
                            variant={
                              r.last_run_status === "success"
                                ? "success"
                                : r.last_run_status === "failed"
                                ? "destructive"
                                : "secondary"
                            }
                          >
                            {r.last_run_status || "—"}
                          </Badge>
                        </div>
                      ) : (
                        <span className="text-sm text-muted-foreground">Never</span>
                      )}
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-1">
                        <Button asChild size="sm" variant="ghost">
                          <Link to={`/r/${r.id}`}>
                            <Play className="h-4 w-4 mr-1" /> View
                          </Link>
                        </Button>
                        <Button asChild size="sm" variant="ghost">
                          <Link to={`/admin/reports/${r.id}/edit`}>
                            <Edit className="h-4 w-4" />
                          </Link>
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => runNow.mutate(r.id)}
                          disabled={runNow.isPending}
                          title="Trigger a sync for this report"
                        >
                          <Play className="h-4 w-4" />
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => {
                            if (
                              confirm(
                                `Truncate the data table for "${r.name}"? The schema stays, but all rows are deleted. The next sync will repopulate it from Jira.`
                              )
                            ) {
                              truncate.mutate(r.id);
                            }
                          }}
                          disabled={truncate.isPending}
                          title="Empty the data table (schema and view are kept)"
                        >
                          <Eraser className="h-4 w-4" />
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => {
                            const msg = r.history_retention_days > 0
                              ? `Remove duplicates and any non-latest rows older than ${r.history_retention_days} day(s) for "${r.name}"?`
                              : `Remove duplicate rows (keep only the latest per key) for "${r.name}"?`;
                            if (confirm(msg)) cleanup.mutate(r.id);
                          }}
                          disabled={cleanup.isPending}
                          title="Run history cleanup now (honors the report's retention setting)"
                        >
                          <Sparkles className="h-4 w-4" />
                        </Button>
                        <Button
                          size="icon"
                          variant="ghost"
                          onClick={() => {
                            if (confirm(`Delete report "${r.name}" and its table?`)) del.mutate(r.id);
                          }}
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Recent sync activity</CardTitle>
          <CardDescription>Auto-refreshes every 5 seconds.</CardDescription>
        </CardHeader>
        <CardContent>
          {(runs ?? []).length === 0 ? (
            <p className="text-sm text-muted-foreground py-4 text-center">No runs yet.</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Report</TableHead>
                  <TableHead>Started</TableHead>
                  <TableHead>Finished</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Rows</TableHead>
                  <TableHead>Pages</TableHead>
                  <TableHead className="w-[180px]">Progress</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {runs!.map((run) => {
                  const isRunning = run.status === "running";
                  return (
                    <TableRow key={run.id}>
                      <TableCell>#{run.report_id}</TableCell>
                      <TableCell className="text-sm">{formatIst(run.started_at)}</TableCell>
                      <TableCell className="text-sm">
                        {run.finished_at ? formatIst(run.finished_at) : "—"}
                      </TableCell>
                      <TableCell>
                        <Badge
                          variant={
                            run.status === "success"
                              ? "success"
                              : run.status === "failed"
                              ? "destructive"
                              : "secondary"
                          }
                        >
                          {isRunning && <Loader2 className="h-3 w-3 mr-1 animate-spin" />}
                          {run.status}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-sm tabular-nums">
                        {run.rows_inserted.toLocaleString("en-IN")}
                      </TableCell>
                      <TableCell className="text-sm tabular-nums">{run.pages_fetched}</TableCell>
                      <TableCell>
                        {isRunning ? (
                          <div className="space-y-1">
                            <div className="flex items-center gap-2">
                              <Button
                                size="sm"
                                variant="destructive"
                                onClick={() => {
                                  if (confirm(`Stop run #${run.id}? The current page will finish, then the sync will end. Committed rows are kept.`)) {
                                    cancelRun.mutate(run.id);
                                  }
                                }}
                                disabled={cancelRun.isPending}
                                title="Stop this sync (current page will finish, then the run ends)"
                              >
                                {cancelRun.isPending ? (
                                  <Loader2 className="h-3 w-3 mr-1 animate-spin" />
                                ) : (
                                  <Square className="h-3 w-3 mr-1" />
                                )}
                                Stop
                              </Button>
                              <div className="text-xs text-muted-foreground">
                                Fetching page {run.pages_fetched}…
                              </div>
                            </div>
                            <div className="h-1.5 w-32 bg-muted rounded-full overflow-hidden">
                              <div className="h-full w-1/3 bg-primary rounded-full animate-progress" />
                            </div>
                          </div>
                        ) : run.status === "failed" ? (
                          <span
                            className="text-xs text-destructive line-clamp-2 max-w-[200px]"
                            title={run.error_message || ""}
                          >
                            {run.error_message}
                          </span>
                        ) : run.status === "cancelled" ? (
                          <span className="text-xs text-amber-600">
                            Stopped at page {run.pages_fetched}
                          </span>
                        ) : (
                          <span className="text-xs text-muted-foreground">—</span>
                        )}
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
