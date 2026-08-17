import { useState } from "react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

interface CronInputProps {
  value: string;
  onChange: (v: string) => void;
  id?: string;
}

const PRESETS: { label: string; value: string }[] = [
  { label: "Every 5 minutes", value: "*/5 * * * *" },
  { label: "Every 15 minutes", value: "*/15 * * * *" },
  { label: "Every hour", value: "0 * * * *" },
  { label: "Daily 02:00 IST", value: "0 2 * * *" },
  { label: "Weekdays 09:00 IST", value: "0 9 * * 1-5" },
];

export function CronInput({ value, onChange, id }: CronInputProps) {
  const [touched, setTouched] = useState(false);
  const valid = isValidCron(value);
  return (
    <div className="space-y-2">
      <Label htmlFor={id}>Schedule (cron, IST)</Label>
      <Input
        id={id}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onBlur={() => setTouched(true)}
        placeholder="0 2 * * *"
        className="font-mono"
        aria-invalid={touched && !valid}
      />
      <div className="flex flex-wrap gap-1">
        {PRESETS.map((p) => (
          <button
            key={p.value}
            type="button"
            className="text-xs px-2 py-1 rounded border bg-card hover:bg-accent"
            onClick={() => onChange(p.value)}
          >
            {p.label}
          </button>
        ))}
      </div>
      {touched && !valid && (
        <p className="text-xs text-destructive">
          Not a valid 5-field cron expression (m h dom mon dow).
        </p>
      )}
    </div>
  );
}

function isValidCron(s: string): boolean {
  const parts = s.trim().split(/\s+/);
  if (parts.length !== 5) return false;
  return parts.every((p) => /^[0-9*/,\-]+$/.test(p));
}
