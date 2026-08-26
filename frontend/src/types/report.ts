import type { FieldDef } from "./jira";

export interface JiraInstance {
  id: number;
  name: string;
  domain: string;
  email: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface Report {
  id: number;
  name: string;
  jira_instance_id: number;
  jira_instance_name?: string | null;
  jql_query: string;
  schedule_cron: string;
  selected_fields: string[];
  is_active: boolean;
  history_retention_days: number;
  last_run_at: string | null;
  last_run_status: string | null;
  last_error: string | null;
  created_at: string;
  updated_at: string;
}

export interface ReportSummary {
  id: number;
  name: string;
  selected_fields: string[];
  last_run_at: string | null;
  last_run_status: string | null;
}

export interface ReportDetail extends Omit<Report, "selected_fields"> {
  selected_fields: FieldDef[];
}

export interface RunHistory {
  id: number;
  report_id: number;
  started_at: string;
  finished_at: string | null;
  status: "running" | "success" | "failed" | "cancelled";
  rows_inserted: number;
  pages_fetched: number;
  error_message: string | null;
}
