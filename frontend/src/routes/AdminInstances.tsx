import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Loader2, Play, Plus, RefreshCw, Trash2 } from "lucide-react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { formatIst } from "@/lib/ist";
import type { JiraInstance } from "@/types/report";

export function AdminInstances() {
  const qc = useQueryClient();
  const { data, isLoading } = useQuery({
    queryKey: ["instances"],
    queryFn: () => api.get<JiraInstance[]>("/admin/instances").then((r) => r.data),
  });
  const del = useMutation({
    mutationFn: (id: number) => api.delete(`/admin/instances/${id}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["instances"] });
      toast.success("Instance deleted");
    },
    onError: (e: any) => toast.error(e?.response?.data?.detail || "Delete failed"),
  });

  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ name: "", domain: "", email: "", api_token: "", is_active: true });
  const create = useMutation({
    mutationFn: () => api.post("/admin/instances", form),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["instances"] });
      toast.success("Instance added — now click 'Test' to verify and fetch its fields");
      setOpen(false);
      setForm({ name: "", domain: "", email: "", api_token: "", is_active: true });
    },
    onError: (e: any) => toast.error(e?.response?.data?.detail || "Create failed"),
  });

  const test = useMutation({
    mutationFn: (id: number) => api.post(`/admin/instances/${id}/test`),
    onSuccess: (r, id) => {
      const d = r.data;
      toast.success(
        `Connected as ${d.display_name || d.email}. ${d.fields_cached} fields cached.`
      );
      qc.invalidateQueries({ queryKey: ["instances"] });
    },
    onError: (e: any) => toast.error(e?.response?.data?.detail || "Connection failed"),
  });

  const runAll = useMutation({
    mutationFn: (id: number) => api.post(`/admin/instances/${id}/run-all`),
    onSuccess: (r) => {
      const d = r.data;
      toast.success(`Queued ${d.reports_queued} report${d.reports_queued === 1 ? "" : "s"} for sync`);
      qc.invalidateQueries({ queryKey: ["runs"] });
      qc.invalidateQueries({ queryKey: ["reports"] });
    },
    onError: (e: any) => toast.error(e?.response?.data?.detail || "Could not queue syncs"),
  });

  return (
    <div className="container mx-auto px-4 py-8">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold">Jira instances</h1>
          <p className="text-sm text-muted-foreground">
            Each instance is one Jira Cloud connection. Click <b>Test</b> to verify the
            token and pull the full list of available fields.
          </p>
        </div>
        <Dialog open={open} onOpenChange={setOpen}>
          <DialogTrigger asChild>
            <Button>
              <Plus className="h-4 w-4 mr-2" /> New instance
            </Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Add Jira instance</DialogTitle>
              <DialogDescription>
                Token is encrypted at rest with Fernet. After saving, click <b>Test</b> on the
                instance row to verify the connection and fetch the field catalog.
              </DialogDescription>
            </DialogHeader>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                create.mutate();
              }}
              className="space-y-4"
            >
              <div className="space-y-2">
                <Label htmlFor="name">Name</Label>
                <Input id="name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Production Jira" required />
              </div>
              <div className="space-y-2">
                <Label htmlFor="domain">Domain</Label>
                <Input id="domain" value={form.domain} onChange={(e) => setForm({ ...form, domain: e.target.value })} placeholder="your-org.atlassian.net" required />
              </div>
              <div className="space-y-2">
                <Label htmlFor="email">Email</Label>
                <Input id="email" type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} placeholder="user@your-org.com" required />
              </div>
              <div className="space-y-2">
                <Label htmlFor="token">API token</Label>
                <Input
                  id="token"
                  type="password"
                  value={form.api_token}
                  onChange={(e) => setForm({ ...form, api_token: e.target.value })}
                  placeholder="ATATT..."
                  required
                />
                <p className="text-xs text-muted-foreground">
                  Generate at id.atlassian.com → Security → API tokens.
                </p>
              </div>
              <div className="flex items-center gap-2">
                <Switch id="active" checked={form.is_active} onCheckedChange={(v) => setForm({ ...form, is_active: v })} />
                <Label htmlFor="active">Active</Label>
              </div>
              <DialogFooter>
                <Button type="button" variant="outline" onClick={() => setOpen(false)}>
                  Cancel
                </Button>
                <Button type="submit" disabled={create.isPending}>
                  {create.isPending ? "Adding..." : "Add"}
                </Button>
              </DialogFooter>
            </form>
          </DialogContent>
        </Dialog>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Configured instances</CardTitle>
          <CardDescription>Tokens are encrypted at rest with Fernet (ENCRYPTION_KEY).</CardDescription>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="space-y-2">
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-10 w-full" />
            </div>
          ) : (data?.length ?? 0) === 0 ? (
            <p className="text-sm text-muted-foreground py-8 text-center">No instances yet — add your first one.</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Name</TableHead>
                  <TableHead>Domain</TableHead>
                  <TableHead>Email</TableHead>
                  <TableHead>Active</TableHead>
                  <TableHead>Updated</TableHead>
                  <TableHead className="w-[220px]"></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data!.map((i) => (
                  <TableRow key={i.id}>
                    <TableCell className="font-medium">{i.name}</TableCell>
                    <TableCell>{i.domain}</TableCell>
                    <TableCell>{i.email}</TableCell>
                    <TableCell>{i.is_active ? "Yes" : "No"}</TableCell>
                    <TableCell>{formatIst(i.updated_at)}</TableCell>
                    <TableCell>
                      <div className="flex items-center gap-1">
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => test.mutate(i.id)}
                          disabled={test.isPending}
                          title="Verify Jira credentials and refresh the field cache"
                        >
                          {test.isPending ? (
                            <Loader2 className="h-3.5 w-3.5 mr-1 animate-spin" />
                          ) : (
                            <RefreshCw className="h-3.5 w-3.5 mr-1" />
                          )}
                          Test
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => runAll.mutate(i.id)}
                          disabled={runAll.isPending}
                          title="Manually trigger a sync for every active report on this instance"
                        >
                          {runAll.isPending ? (
                            <Loader2 className="h-3.5 w-3.5 mr-1 animate-spin" />
                          ) : (
                            <Play className="h-3.5 w-3.5 mr-1" />
                          )}
                          Run
                        </Button>
                        <Button
                          size="icon"
                          variant="ghost"
                          onClick={() => {
                            if (confirm(`Delete instance "${i.name}"?`)) del.mutate(i.id);
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
    </div>
  );
}
