// Display helpers for Jira-returned IST strings. No timezone conversion — the
// backend already stores the IST wall-clock as a naive datetime and returns it
// as a string, so the frontend just parses and renders.

import { format, parseISO } from "date-fns";

const DEFAULT_PATTERN = "yyyy-MM-dd HH:mm";

export function formatIst(
  value: string | Date | null | undefined,
  pattern: string = DEFAULT_PATTERN
): string {
  if (!value) return "—";
  const d = typeof value === "string" ? parseISO(value.replace(" ", "T")) : value;
  if (Number.isNaN(d.getTime())) return String(value);
  // The string is the IST wall-clock Jira gave us. The Date we built from it
  // is "anchored" in the browser's local zone, but since we only care about the
  // wall-clock digits, a plain `format` gives the right output.
  return format(d, pattern);
}

export function formatIstDate(value: string | Date | null | undefined): string {
  return formatIst(value, "yyyy-MM-dd");
}

export function formatIstTime(value: string | Date | null | undefined): string {
  return formatIst(value, "HH:mm");
}
