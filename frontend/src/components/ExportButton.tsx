import { useState } from "react";
import { Download, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { toast } from "sonner";

interface ExportButtonProps {
  reportId: number;
  filterQuery: string;
  createdFrom: string | null;
  createdTo: string | null;
  sortField?: string;
  sortDir?: "asc" | "desc";
  filename?: string;
}

export function ExportButton({
  reportId,
  filterQuery,
  createdFrom,
  createdTo,
  sortField,
  sortDir,
  filename,
}: ExportButtonProps) {
  const [loading, setLoading] = useState(false);

  const onClick = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (createdFrom) params.set("created_from", createdFrom);
      if (createdTo) params.set("created_to", createdTo);
      if (sortField) params.set("sort_field", sortField);
      if (sortDir) params.set("sort_dir", sortDir);
      // filterQuery already contains "&f_..." — strip the leading "?" if present and append.
      const extra = filterQuery.replace(/^\?/, "");
      const qs = [params.toString(), extra].filter(Boolean).join("&");

      const r = await api.get(`/reports/${reportId}/export${qs ? `?${qs}` : ""}`, {
        responseType: "blob",
      });
      const url = URL.createObjectURL(new Blob([r.data]));
      const a = document.createElement("a");
      a.href = url;
      a.download = filename || `report_${reportId}.csv`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      toast.success("Export downloaded");
    } catch (e: any) {
      toast.error("Export failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Button variant="outline" onClick={onClick} disabled={loading}>
      {loading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Download className="mr-2 h-4 w-4" />}
      Export CSV
    </Button>
  );
}
