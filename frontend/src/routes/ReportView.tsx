import { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import {
  flexRender,
  getCoreRowModel,
  useReactTable,
  type ColumnDef,
  type VisibilityState,
} from "@tanstack/react-table";
import { useQuery } from "@tanstack/react-query";
import { ArrowDown, ArrowUp, ArrowUpDown, ChevronLeft, ChevronRight, Eye, Loader2, X } from "lucide-react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { FilterPanel } from "@/components/FilterPanel";
import { DateRangeSlicer, type DateRange } from "@/components/DateRangeSlicer";
import { ExportButton } from "@/components/ExportButton";
import { storage } from "@/lib/persist";
import { buildFilterQueryString, type FilterValue } from "@/lib/filters";
import { formatIst } from "@/lib/ist";
import { cn } from "@/lib/utils";
import type { FieldDef } from "@/types/jira";
import type { ReportDetail } from "@/types/report";

const PAGE_SIZE_KEY = (id: number) => `report:${id}:page_size`;

export function ReportView() {
  const { id } = useParams<{ id: string }>();
  const reportId = Number(id);

  const { data: report, isLoading: loadingReport } = useQuery({
    queryKey: ["public-report", reportId],
    queryFn: () => api.get<ReportDetail>(`/reports/${reportId}`).then((r) => r.data),
  });

  const [filters, setFilters] = useState<Record<string, FilterValue>>({});
  const [dateRange, setDateRange] = useState<DateRange>({ from: null, to: null });
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState<number>(() => storage.get<number>(PAGE_SIZE_KEY(reportId), 50));
  const [columnVisibility, setColumnVisibility] = useState<VisibilityState>(() =>
    storage.get<VisibilityState>(`report:${reportId}:columns`, {})
  );
  const [sort, setSort] = useState<{ field: string; dir: "asc" | "desc" } | null>(() =>
    storage.get<{ field: string; dir: "asc" | "desc" } | null>(`report:${reportId}:sort`, null)
  );

  // Persist UI state
  useEffect(() => {
    storage.set(PAGE_SIZE_KEY(reportId), pageSize);
  }, [reportId, pageSize]);
  useEffect(() => {
    storage.set(`report:${reportId}:columns`, columnVisibility);
  }, [reportId, columnVisibility]);
  useEffect(() => {
    storage.set(`report:${reportId}:sort`, sort);
  }, [reportId, sort]);

  const onHeaderSort = (fieldId: string) => {
    setPage(1);
    setSort((prev) => {
      if (prev?.field === fieldId) {
        return { field: fieldId, dir: prev.dir === "asc" ? "desc" : "asc" };
      }
      return { field: fieldId, dir: "asc" };
    });
  };

  const fieldDefs: FieldDef[] = useMemo(
    () => (report?.selected_fields ?? []).filter((f) => f && f.id),
    [report]
  );
  // Always include the system spine columns the UI needs.
  const allColumns: FieldDef[] = useMemo(() => {
    const seen = new Set<string>();
    const out: FieldDef[] = [];
    const spine: FieldDef = {
      id: "issue_key",
      name: "Issue Key",
      type: "string",
    };
    if (!seen.has(spine.id)) {
      seen.add(spine.id);
      out.push(spine);
    }
    for (const f of fieldDefs) {
      if (seen.has(f.id)) continue;
      seen.add(f.id);
      out.push(f);
    }
    // Only add the "jira_created" fallback column if the user did NOT select
    // "created" themselves (in which case the row already has a `created` key).
    if (!seen.has("created")) {
      const createdCol: FieldDef = {
        id: "jira_created",
        name: "Created (IST)",
        type: "datetime",
      };
      out.push(createdCol);
    }
    return out;
  }, [fieldDefs]);

  // Reset filters when report changes
  useEffect(() => {
    const empty: Record<string, FilterValue> = {};
    for (const f of fieldDefs) empty[f.id] = null;
    setFilters(empty);
    setPage(1);
  }, [reportId, fieldDefs.length]);

  const filterQuery = useMemo(() => buildFilterQueryString(filters), [filters]);

  const { data, isFetching, isLoading } = useQuery({
    queryKey: ["issues", reportId, page, pageSize, filterQuery, dateRange, sort],
    queryFn: () => {
      const params = new URLSearchParams();
      params.set("page", String(page));
      params.set("page_size", String(pageSize));
      if (dateRange.from) params.set("created_from", dateRange.from);
      if (dateRange.to) params.set("created_to", dateRange.to);
      if (sort) {
        params.set("sort_field", sort.field);
        params.set("sort_dir", sort.dir);
      }
      const extra = filterQuery.replace(/^\?/, "");
      const qs = [params.toString(), extra].filter(Boolean).join("&");
      return api
        .get<{ data: Record<string, any>[]; total: number; page: number; page_size: number }>(
          `/reports/${reportId}/issues?${qs}`
        )
        .then((r) => r.data);
    },
    enabled: Boolean(reportId) && Boolean(report),
    placeholderData: (prev) => prev,
  });

  // Distinct values for filter dropdowns (string fields only).
  const stringFieldIds = fieldDefs.filter((f) => f.type === "string").map((f) => f.id);
  const { data: distinctData, isFetching: loadingDistinct } = useQuery({
    queryKey: ["distinct", reportId, stringFieldIds.join(",")],
    queryFn: async () => {
      const out: Record<string, string[]> = {};
      // Backend doesn't expose this directly; derive from the first page of data
      // for small datasets. For large datasets, we'd need a dedicated endpoint.
      const params = new URLSearchParams();
      params.set("page", "1");
      params.set("page_size", "500");
      const r = await api.get<{ data: Record<string, any>[] }>(
        `/reports/${reportId}/issues?${params.toString()}`
      );
      for (const f of stringFieldIds) {
        const set = new Set<string>();
        for (const row of r.data.data) {
          const v = row[f];
          if (v != null && v !== "") set.add(String(v));
        }
        out[f] = Array.from(set).sort().slice(0, 200);
      }
      return out;
    },
    enabled: stringFieldIds.length > 0 && Boolean(report),
  });

  const columns: ColumnDef<Record<string, any>>[] = useMemo(
    () =>
      allColumns.map((f) => ({
        id: f.id,
        accessorFn: (row) => row[f.id],
        header: () => {
          const isSorted = sort?.field === f.id;
          const isAsc = isSorted && sort.dir === "asc";
          return (
            <button
              type="button"
              onClick={() => onHeaderSort(f.id)}
              className={cn(
                "inline-flex items-center gap-1 -mx-2 px-2 py-1 rounded hover:bg-muted/60 transition-colors",
                isSorted && "text-foreground"
              )}
              title={`Sort by ${f.name}`}
            >
              <span>{f.name}</span>
              {isSorted ? (
                isAsc ? (
                  <ArrowUp className="h-3 w-3" />
                ) : (
                  <ArrowDown className="h-3 w-3" />
                )
              ) : (
                <ArrowUpDown className="h-3 w-3 text-muted-foreground/50" />
              )}
            </button>
          );
        },
        cell: ({ getValue }) => {
          const v = getValue();
          if (v == null || v === "") return <span className="text-muted-foreground/60">—</span>;
          if (f.type === "datetime" && typeof v === "string") {
            return <span className="whitespace-nowrap text-sm">{formatIst(v)}</span>;
          }
          if (f.id === "issue_key") {
            return <span className="font-mono text-xs">{String(v)}</span>;
          }
          return <span className="text-sm">{String(v)}</span>;
        },
        enableHiding: true,
      })),
    [allColumns, sort]
  );

  const table = useReactTable({
    data: data?.data ?? [],
    columns,
    state: { columnVisibility },
    onColumnVisibilityChange: setColumnVisibility,
    getCoreRowModel: getCoreRowModel(),
    manualPagination: true,
    manualFiltering: true,
  });

  if (loadingReport) {
    return (
      <div className="container mx-auto px-4 py-8 space-y-3">
        <Skeleton className="h-8 w-1/3" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (!report) {
    return (
      <div className="container mx-auto px-4 py-8">
        <Card className="p-8 text-center">
          <p className="text-muted-foreground">Report not found.</p>
        </Card>
      </div>
    );
  }

  const total = data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  return (
    <div className="container mx-auto px-4 py-6 space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">{report.name}</h1>
          <p className="text-sm text-muted-foreground">
            {total.toLocaleString("en-IN")} {total === 1 ? "issue" : "issues"}
            {report.last_run_at && (
              <> · last sync {formatIst(report.last_run_at)}</>
            )}
          </p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <DateRangeSlicer value={dateRange} onChange={setDateRange} />
          <FilterPanel
            fields={fieldDefs}
            values={filters}
            onChange={setFilters}
            distinctValues={distinctData ?? {}}
            loadingDistinct={loadingDistinct}
          />
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="outline">
                <Eye className="mr-2 h-4 w-4" /> Columns
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-56 max-h-80 overflow-y-auto">
              <DropdownMenuLabel>Toggle columns</DropdownMenuLabel>
              <DropdownMenuSeparator />
              {table
                .getAllColumns()
                .filter((c) => c.getCanHide())
                .map((c) => (
                  <DropdownMenuCheckboxItem
                    key={c.id}
                    checked={c.getIsVisible()}
                    onCheckedChange={(v) => c.toggleVisibility(Boolean(v))}
                    className="capitalize"
                  >
                    {(allColumns.find((f) => f.id === c.id)?.name) || c.id}
                  </DropdownMenuCheckboxItem>
                ))}
            </DropdownMenuContent>
          </DropdownMenu>
          <ExportButton
            reportId={reportId}
            filterQuery={filterQuery}
            createdFrom={dateRange.from}
            createdTo={dateRange.to}
            sortField={sort?.field}
            sortDir={sort?.dir}
            filename={`${report.name.replace(/\s+/g, "_")}.csv`}
          />
          {sort && (
            <Button
              variant="ghost"
              onClick={() => {
                setSort(null);
                setPage(1);
              }}
              title="Clear sort"
            >
              <X className="mr-1 h-4 w-4" /> Clear sort
            </Button>
          )}
        </div>
      </div>

      <Card className="overflow-hidden">
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              {table.getHeaderGroups().map((hg) => (
                <TableRow key={hg.id}>
                  {hg.headers.map((h) => (
                    <TableHead key={h.id}>
                      {h.isPlaceholder ? null : flexRender(h.column.columnDef.header, h.getContext())}
                    </TableHead>
                  ))}
                </TableRow>
              ))}
            </TableHeader>
            <TableBody>
              {isLoading ? (
                Array.from({ length: 8 }).map((_, i) => (
                  <TableRow key={i}>
                    {table.getVisibleLeafColumns().map((c) => (
                      <TableCell key={c.id}>
                        <Skeleton className="h-4 w-full" />
                      </TableCell>
                    ))}
                  </TableRow>
                ))
              ) : (data?.data ?? []).length === 0 ? (
                <TableRow>
                  <TableCell colSpan={table.getVisibleLeafColumns().length} className="text-center py-12">
                    <p className="text-muted-foreground">No issues match the current filters.</p>
                  </TableCell>
                </TableRow>
              ) : (
                table.getRowModel().rows.map((row) => (
                  <TableRow key={row.id}>
                    {row.getVisibleCells().map((cell) => (
                      <TableCell key={cell.id}>{flexRender(cell.column.columnDef.cell, cell.getContext())}</TableCell>
                    ))}
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </div>

        <div className="flex items-center justify-between p-3 border-t bg-muted/30 text-sm">
          <div className="text-muted-foreground">
            Page {page} of {totalPages} · {total.toLocaleString("en-IN")} rows
          </div>
          <div className="flex items-center gap-2">
            <span className="text-muted-foreground">Rows per page</span>
            <select
              value={pageSize}
              onChange={(e) => {
                setPageSize(Number(e.target.value));
                setPage(1);
              }}
              className="h-8 rounded border bg-background px-2 text-sm"
            >
              {[25, 50, 100, 200].map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
            <Button
              size="sm"
              variant="outline"
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page <= 1 || isFetching}
            >
              <ChevronLeft className="h-4 w-4" />
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              disabled={page >= totalPages || isFetching}
            >
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </Card>

      {isFetching && !isLoading && (
        <div className="fixed bottom-4 right-4 bg-card border rounded-lg shadow-lg px-3 py-2 text-sm flex items-center gap-2">
          <Loader2 className="h-4 w-4 animate-spin" /> Refreshing…
        </div>
      )}
    </div>
  );
}
