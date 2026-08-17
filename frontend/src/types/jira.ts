export type FieldType = "string" | "text" | "number" | "datetime";

export interface FieldDef {
  id: string;
  name: string;
  type: FieldType;
  is_custom?: boolean;
  schema_type?: string | null;
  position?: number;
}

export interface InstanceField extends FieldDef {
  schema_custom?: string | null;
  last_fetched_at: string | null;
}
