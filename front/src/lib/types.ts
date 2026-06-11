export interface User {
  id: number;
  email: string;
  name: string;
  org_id: number;
  role: "admin" | "dev" | "user";
  is_admin: boolean;
  is_dev: boolean;
}

export interface AdminUser {
  id: number;
  email: string;
  name: string;
  role: "admin" | "dev" | "user";
  is_active: boolean;
}

export interface TemplateInfo {
  key: string;
  name: string;
  description: string;
}

export interface Project {
  id: number;
  name: string;
  subdomain: string;
  description: string;
  status: "draft" | "live";
  folder_id: number | null;
  output_folder_name: string;
  access_mode: "whitelist" | "domain";
  allowed_domain: string;
  wizard_state: WizardState;
  wizard_dirty: boolean;
  created_at: string;
  updated_at: string;
}

export type TriggerKind = "manual" | "schedule" | "webhook";
export type InputKind = "file" | "fields" | "none";
export type OutputKind = "download" | "summary";

export interface WizardField {
  label: string;
  type: "text" | "number" | "date" | "select";
}

export interface WizardState {
  step?: number;
  trigger?: { kind: TriggerKind; every?: number; unit?: "hours" | "days" };
  input?: { kind: InputKind; fields?: WizardField[]; sample_file?: string };
  process?: { description: string };
  output?: { kind: OutputKind };
}

export interface Folder {
  id: number;
  name: string;
}

export type StageType = "form" | "script" | "job" | "hook" | "agent";

export interface Stage {
  id: number;
  type: StageType;
  name: string;
  key: string;
  config: any;
  entry_file: string;
  timeout_seconds: number;
  pos_x: number;
  pos_y: number;
}

export interface Edge {
  id: number;
  source_stage_id: number;
  target_stage_id: number;
  variable_label: string;
}

export interface SourceFile {
  id: number;
  path: string;
  content: string;
  is_dir: boolean;
}

export interface Execution {
  id: string;
  project_id: number;
  stage_id: number;
  build_id: number | null;
  stage_name: string;
  stage_type: string;
  status: "queued" | "running" | "success" | "error";
  stdout: string;
  stderr: string;
  input_data: any;
  output_data: any;
  started_at: string;
  finished_at: string | null;
}

export interface Build {
  id: number;
  hash: string;
  framework_version: string;
  status: "live" | "inactive" | "failed";
  created_at: string;
}

export interface PendingAction {
  id: number;
  kind: string;
  title: string;
  payload: any;
  status: string;
  created_at: string;
}

export interface ChatMessage {
  id: number;
  role: "user" | "assistant";
  content: string;
  meta: any;
  tokens: number;
  created_at: string;
}

export interface EnvVar {
  id: number;
  key: string;
  value: string;
  secret: boolean;
}

export interface Role {
  id: number;
  name: string;
  description: string;
}

export interface Member {
  id: number;
  email: string;
  roles: string[];
}
