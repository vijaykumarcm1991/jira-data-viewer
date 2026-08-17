// Build query-string filter params for /api/reports/<id>/issues.
// Keys: f_<fieldId>=<value> for single, or comma-joined for multiple.

import type { FieldDef } from "@/types/jira";

export type FilterValue = string[] | string | null | undefined;

export function buildFilterQueryString(filters: Record<string, FilterValue>): string {
  const parts: string[] = [];
  for (const [k, v] of Object.entries(filters)) {
    if (v == null) continue;
    if (Array.isArray(v)) {
      if (v.length === 0) continue;
      parts.push(`f_${encodeURIComponent(k)}=${encodeURIComponent(v.join(","))}`);
    } else if (typeof v === "string" && v.trim() !== "") {
      parts.push(`f_${encodeURIComponent(k)}=${encodeURIComponent(v)}`);
    }
  }
  return parts.join("&");
}

export function groupFieldsByType(fields: FieldDef[]) {
  const groups: Record<string, FieldDef[]> = { string: [], text: [], number: [], datetime: [] };
  for (const f of fields) {
    groups[f.type]?.push(f);
  }
  return groups;
}
