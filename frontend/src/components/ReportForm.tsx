import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Save, RefreshCw, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import { Skeleton } from "@/components/ui/skeleton";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { FieldSelector } from "@/components/FieldSelector";
import { CronInput } from "@/components/CronInput";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import type { FieldDef, InstanceField } from "@/types/jira";
import type { JiraInstance, Report } from "@/types/report";

interface Props {
  mode: "create" | "edit";
}

export function ReportForm({ mode }: Props) {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const qc = useQueryClient();

  const { data: instances } = useQuery({
    queryKey: ["instances"],
    queryFn: () => api.get<JiraInstance[]>("/admin/instances").then((r) => r.data),
  });
  const { data: existing, isLoading: loadingReport } = useQuery({
    queryKey: ["report", id],
    queryFn: () => api.get<Report>(`/admin/reports/${id}`).then((r) => r.data),
    enabled: mode === "edit" && Boolean(id),
  });

  const [name, setName] = useState("");
  const [jiraInstanceId, setJiraInstanceId] = useState<string>("");
  const [jql, setJql] = useState("issuetype = Incident AND updated >= startOfDay(-1) ORDER BY updated ASC");
  const [cron, setCron] = useState("0 2 * * *");
  const [selected, setSelected] = useState<string[]>([]);
  const [isActive, setIsActive] = useState(true);
  const [historyRetentionDays, setHistoryRetentionDays] = useState<number>(0);

  // For create mode the user picks the instance; for edit we lock it to the existing one.
  const instanceIdForFields = mode === "create" ? jiraInstanceId : String(existing?.jira_instance_id ?? "");

  const { data: instanceFields, isLoading: loadingFields, refetch: refetchFields } = useQuery({
    queryKey: ["instance-fields", instanceIdForFields],
    queryFn: () =>
      api
        .get<InstanceField[]>(`/admin/instances/${instanceIdForFields}/fields`)
        .then((r) => r.data),
    enabled: Boolean(instanceIdForFields),
  });

  useEffect(() => {
    if (mode === "edit" && existing) {
      setName(existing.name);
      setJiraInstanceId(String(existing.jira_instance_id));
      setJql(existing.jql_query);
      setCron(existing.schedule_cron);
      setSelected(existing.selected_fields || []);
      setIsActive(existing.is_active);
      setHistoryRetentionDays(existing.history_retention_days ?? 0);
    }
  }, [mode, existing]);

  const refreshFields = useMutation({
    mutationFn: () => api.post(`/admin/instances/${instanceIdForFields}/test`),
    onSuccess: (r) => {
      toast.success(`Refreshed: ${r.data.fields_cached} fields cached`);
      qc.invalidateQueries({ queryKey: ["instance-fields", instanceIdForFields] });
    },
    onError: (e: any) =>
      toast.error(e?.response?.data?.detail || "Refresh failed — check the token"),
  });

  const save = useMutation({
    mutationFn: async () => {
      if (mode === "create") {
        return api.post("/admin/reports", {
          name,
          jira_instance_id: Number(jiraInstanceId),
          jql_query: jql,
          schedule_cron: cron,
          selected_fields: selected,
          is_active: isActive,
        });
      }
      return api.patch(`/admin/reports/${id}`, {
        name,
        jql_query: jql,
        schedule_cron: cron,
        selected_fields: selected,
        is_active: isActive,
        history_retention_days: historyRetentionDays,
      });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["reports"] });
      qc.invalidateQueries({ queryKey: ["report", id] });
      toast.success(mode === "create" ? "Report created" : "Report updated");
      navigate("/admin/reports");
    },
    onError: (e: any) => toast.error(e?.response?.data?.detail || "Save failed"),
  });

  if (mode === "edit" && loadingReport) {
    return (
      <div className="container mx-auto px-4 py-8 space-y-4">
        <Skeleton className="h-10 w-1/3" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  // Build a FieldDef list the FieldSelector can consume.
  const fieldsForSelector: FieldDef[] = (instanceFields ?? []).map((f) => ({
    id: f.id,
    name: f.name,
    type: f.type,
    is_custom: f.is_custom,
    schema_type: f.schema_type,
  }));

  return (
    <div className="container mx-auto px-4 py-8 max-w-5xl">
      <Button variant="ghost" onClick={() => navigate("/admin/reports")} className="mb-4">
        <ArrowLeft className="h-4 w-4 mr-1" /> Back to reports
      </Button>
      <Card>
        <CardHeader>
          <CardTitle>{mode === "create" ? "New report" : "Edit report"}</CardTitle>
          <CardDescription>
            Pick a JQL, choose which fields to fetch and display, set a schedule. The
            system will create a dedicated table and view for this report.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              if (selected.length === 0) {
                toast.error("Select at least one field");
                return;
              }
              if (mode === "create" && !jiraInstanceId) {
                toast.error("Pick a Jira instance");
                return;
              }
              save.mutate();
            }}
            className="space-y-6"
          >
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="name">Report name</Label>
                <Input
                  id="name"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="Incidents — last 24h"
                  required
                />
              </div>
              {mode === "create" ? (
                <div className="space-y-2">
                  <Label>Jira instance</Label>
                  <Select value={jiraInstanceId} onValueChange={setJiraInstanceId}>
                    <SelectTrigger>
                      <SelectValue placeholder="Pick one…" />
                    </SelectTrigger>
                    <SelectContent>
                      {(instances ?? []).map((i) => (
                        <SelectItem key={i.id} value={String(i.id)}>
                          {i.name} ({i.domain})
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              ) : (
                <div className="space-y-2">
                  <Label>Jira instance</Label>
                  <Input value={existing?.jira_instance_name ?? ""} disabled />
                </div>
              )}
            </div>

            <div className="space-y-2">
              <Label htmlFor="jql">JQL</Label>
              <Textarea
                id="jql"
                value={jql}
                onChange={(e) => setJql(e.target.value)}
                rows={3}
                className="font-mono text-sm"
                required
              />
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <CronInput value={cron} onChange={setCron} />
              <div className="space-y-2">
                <Label>Status</Label>
                <div className="flex items-center gap-3 h-10">
                  <Switch checked={isActive} onCheckedChange={setIsActive} id="is_active" />
                  <Label htmlFor="is_active" className="cursor-pointer">
                    {isActive ? "Active (scheduler will run this report)" : "Paused"}
                  </Label>
                </div>
              </div>
            </div>

            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <Label>Fields</Label>
                {instanceIdForFields && (
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    onClick={() => refreshFields.mutate()}
                    disabled={refreshFields.isPending}
                  >
                    {refreshFields.isPending ? (
                      <Loader2 className="h-3.5 w-3.5 mr-1 animate-spin" />
                    ) : (
                      <RefreshCw className="h-3.5 w-3.5 mr-1" />
                    )}
                    Refresh fields
                  </Button>
                )}
              </div>

              {!instanceIdForFields ? (
                <Alert>
                  <AlertTitle>Pick a Jira instance first</AlertTitle>
                  <AlertDescription>
                    The available fields are pulled from the selected instance.
                  </AlertDescription>
                </Alert>
              ) : loadingFields ? (
                <Skeleton className="h-64 w-full" />
              ) : fieldsForSelector.length === 0 ? (
                <Alert>
                  <AlertTitle>No fields cached for this instance</AlertTitle>
                  <AlertDescription>
                    Go to <b>Instances</b>, click <b>Test</b> on this row, and the field list will
                    populate here.
                  </AlertDescription>
                </Alert>
              ) : (
                <>
                  <FieldSelector fields={fieldsForSelector} selected={selected} onChange={setSelected} />
                  <p className="text-xs text-muted-foreground mt-2">
                    {fieldsForSelector.length} fields available · {selected.length} selected.
                    Drag fields on the right to change the column order. Removing a field keeps
                    the data in the table (history) but drops it from the view.
                  </p>
                </>
              )}
            </div>

            <div className="flex justify-end">
              <Button type="submit" disabled={save.isPending}>
                <Save className="h-4 w-4 mr-2" />
                {save.isPending ? "Saving..." : mode === "create" ? "Create report" : "Save changes"}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
