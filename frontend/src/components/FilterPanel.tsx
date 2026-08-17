import { useEffect, useState } from "react";
import { Check, Filter, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Checkbox } from "@/components/ui/checkbox";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { FieldDef } from "@/types/jira";
import type { FilterValue } from "@/lib/filters";
import { groupFieldsByType } from "@/lib/filters";

interface FilterPanelProps {
  fields: FieldDef[];
  values: Record<string, FilterValue>;
  onChange: (v: Record<string, FilterValue>) => void;
  distinctValues: Record<string, string[]>;
  loadingDistinct: boolean;
}

export function FilterPanel({
  fields,
  values,
  onChange,
  distinctValues,
  loadingDistinct,
}: FilterPanelProps) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const groups = groupFieldsByType(fields);
  const activeCount = Object.values(values).filter((v) => {
    if (Array.isArray(v)) return v.length > 0;
    return Boolean(v);
  }).length;

  const setField = (id: string, v: FilterValue) => onChange({ ...values, [id]: v });

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button variant="outline" className={cn(activeCount > 0 && "border-primary/50")}>
          <Filter className="mr-2 h-4 w-4" />
          Filters
          {activeCount > 0 && (
            <Badge variant="default" className="ml-2 h-5 px-1.5">
              {activeCount}
            </Badge>
          )}
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-[420px] p-0" align="start">
        <div className="p-3 border-b">
          <Input
            placeholder="Search fields…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="h-9"
          />
        </div>
        <ScrollArea className="h-[480px]">
          <div className="p-3 space-y-5">
            {(["string", "text", "number", "datetime"] as const).map((type) => {
              const list = (groups[type] || []).filter((f) =>
                f.name.toLowerCase().includes(search.toLowerCase())
              );
              if (list.length === 0) return null;
              return (
                <div key={type}>
                  <div className="text-xs font-semibold text-muted-foreground uppercase mb-2">
                    {type === "string"
                      ? "Single-value fields"
                      : type === "text"
                      ? "Free text"
                      : type === "number"
                      ? "Numbers"
                      : "Dates"}
                  </div>
                  <div className="space-y-3">
                    {list.map((f) => (
                      <FieldFilter
                        key={f.id}
                        field={f}
                        value={values[f.id]}
                        onChange={(v) => setField(f.id, v)}
                        options={distinctValues[f.id]}
                        loading={loadingDistinct}
                      />
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        </ScrollArea>
        {activeCount > 0 && (
          <div className="border-t p-2 flex justify-end">
            <Button
              size="sm"
              variant="ghost"
              onClick={() => {
                const empty: Record<string, FilterValue> = {};
                for (const f of fields) empty[f.id] = null;
                onChange(empty);
              }}
            >
              <X className="h-4 w-4 mr-1" /> Clear all
            </Button>
          </div>
        )}
      </PopoverContent>
    </Popover>
  );
}

function FieldFilter({
  field,
  value,
  onChange,
  options,
  loading,
}: {
  field: FieldDef;
  value: FilterValue;
  onChange: (v: FilterValue) => void;
  options?: string[];
  loading: boolean;
}) {
  if (field.type === "string") {
    const arr = Array.isArray(value) ? value : value ? [String(value)] : [];
    return (
      <div className="space-y-1">
        <div className="flex items-center justify-between">
          <span className="text-sm font-medium">{field.name}</span>
          {arr.length > 0 && (
            <button
              type="button"
              className="text-xs text-muted-foreground hover:text-foreground"
              onClick={() => onChange(null)}
            >
              Clear
            </button>
          )}
        </div>
        <Popover>
          <PopoverTrigger asChild>
            <Button variant="outline" size="sm" className="w-full justify-start text-left font-normal h-8">
              {arr.length === 0 ? (
                <span className="text-muted-foreground">Any</span>
              ) : (
                <span className="truncate">{arr.join(", ")}</span>
              )}
            </Button>
          </PopoverTrigger>
          <PopoverContent className="w-64 p-0" align="start">
            <div className="p-2 border-b">
              <Input
                placeholder="Filter options…"
                className="h-8"
                onChange={(e) => {
                  const term = e.target.value.toLowerCase();
                  document
                    .querySelectorAll<HTMLElement>(`[data-options-for="${field.id}"] [data-option]`)
                    .forEach((el) => {
                      el.style.display = el.dataset.option?.toLowerCase().includes(term) ? "" : "none";
                    });
                }}
              />
            </div>
            <ScrollArea className="h-64">
              <div className="p-1" data-options-for={field.id}>
                {loading && <div className="text-xs text-muted-foreground p-2">Loading…</div>}
                {(options ?? []).map((opt) => {
                  const checked = arr.includes(opt);
                  return (
                    <label
                      key={opt}
                      data-option={opt}
                      className="flex items-center gap-2 px-2 py-1.5 text-sm hover:bg-accent rounded cursor-pointer"
                    >
                      <Checkbox
                        checked={checked}
                        onCheckedChange={(c) => {
                          if (c) onChange([...arr, opt]);
                          else onChange(arr.filter((x) => x !== opt));
                        }}
                      />
                      <span className="truncate">{opt}</span>
                      {checked && <Check className="ml-auto h-3 w-3 text-primary" />}
                    </label>
                  );
                })}
                {!loading && (options ?? []).length === 0 && (
                  <div className="text-xs text-muted-foreground p-2">No values</div>
                )}
              </div>
            </ScrollArea>
          </PopoverContent>
        </Popover>
      </div>
    );
  }
  if (field.type === "text") {
    return (
      <div className="space-y-1">
        <div className="flex items-center justify-between">
          <span className="text-sm font-medium">{field.name}</span>
          {value && (
            <button
              type="button"
              className="text-xs text-muted-foreground hover:text-foreground"
              onClick={() => onChange(null)}
            >
              Clear
            </button>
          )}
        </div>
        <Input
          value={typeof value === "string" ? value : ""}
          onChange={(e) => onChange(e.target.value || null)}
          placeholder="contains…"
          className="h-8"
        />
      </div>
    );
  }
  if (field.type === "number") {
    return (
      <div className="space-y-1">
        <div className="flex items-center justify-between">
          <span className="text-sm font-medium">{field.name}</span>
          {value && (
            <button
              type="button"
              className="text-xs text-muted-foreground hover:text-foreground"
              onClick={() => onChange(null)}
            >
              Clear
            </button>
          )}
        </div>
        <Input
          type="number"
          value={typeof value === "string" ? value : ""}
          onChange={(e) => onChange(e.target.value || null)}
          placeholder="equals…"
          className="h-8"
        />
      </div>
    );
  }
  return null;
}
