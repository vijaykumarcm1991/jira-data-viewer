import { useEffect, useState } from "react";
import { Calendar as CalendarIcon, X } from "lucide-react";
import { format } from "date-fns";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

export interface DateRange {
  from: string | null; // YYYY-MM-DD
  to: string | null;
}

interface DateRangeSlicerProps {
  value: DateRange;
  onChange: (v: DateRange) => void;
  label?: string;
}

const PRESETS: { label: string; days: number | null }[] = [
  { label: "All time", days: null },
  { label: "Last 7 days", days: 7 },
  { label: "Last 30 days", days: 30 },
  { label: "Last 90 days", days: 90 },
];

export function DateRangeSlicer({ value, onChange, label = "Created date" }: DateRangeSlicerProps) {
  const [open, setOpen] = useState(false);
  const hasValue = Boolean(value.from || value.to);

  useEffect(() => {
    if (!hasValue) return;
    if (value.from && !value.to) {
      onChange({ from: value.from, to: format(new Date(), "yyyy-MM-dd") });
    }
  }, [hasValue, value.from, value.to, onChange]);

  const summary = hasValue
    ? `${value.from ?? "…"} → ${value.to ?? format(new Date(), "yyyy-MM-dd")}`
    : "All time";

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          className={cn(
            "min-w-[240px] justify-start text-left font-normal",
            hasValue && "border-primary/50"
          )}
        >
          <CalendarIcon className="mr-2 h-4 w-4" />
          <span className="text-sm">
            {label}: <span className="font-medium">{summary}</span>
          </span>
          {hasValue && (
            <X
              className="ml-auto h-4 w-4 text-muted-foreground hover:text-foreground"
              onClick={(e) => {
                e.stopPropagation();
                onChange({ from: null, to: null });
              }}
            />
          )}
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-80" align="start">
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-2">
            <div className="space-y-1">
              <Label className="text-xs">From</Label>
              <Input
                type="date"
                value={value.from ?? ""}
                onChange={(e) => onChange({ ...value, from: e.target.value || null })}
              />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">To</Label>
              <Input
                type="date"
                value={value.to ?? ""}
                onChange={(e) => onChange({ ...value, to: e.target.value || null })}
              />
            </div>
          </div>
          <div className="flex flex-wrap gap-1">
            {PRESETS.map((p) => (
              <button
                key={p.label}
                type="button"
                className="text-xs px-2 py-1 rounded border bg-card hover:bg-accent"
                onClick={() => {
                  if (p.days === null) onChange({ from: null, to: null });
                  else {
                    const to = new Date();
                    const from = new Date();
                    from.setDate(from.getDate() - p.days);
                    onChange({
                      from: format(from, "yyyy-MM-dd"),
                      to: format(to, "yyyy-MM-dd"),
                    });
                  }
                  setOpen(false);
                }}
              >
                {p.label}
              </button>
            ))}
          </div>
        </div>
      </PopoverContent>
    </Popover>
  );
}
