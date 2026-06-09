import axiosInstance from "@/commons/utils/axiosInstance";

export type AdminCapabilityKey =
  | "can_access_admin_panel"
  | "can_view_audit"
  | "can_manage_users";

export type AuditEventItem = {
  id: number;
  organization_id: string | null;
  actor_id: number | null;
  actor_type: string;
  actor_role_snapshot: string | null;
  actor_name_snapshot: string | null;
  action: string;
  result: string;
  session_id: string | null;
  patient_id: number | null;
  encounter_id: number | null;
  document_id: number | null;
  resource_type: string | null;
  resource_id: string | null;
  service_name: string | null;
  service_account: string | null;
  error_code: string | null;
  trace_id: string | null;
  request_id: string | null;
  created_at: string;
};

export type AuditEventListResponse = {
  items: AuditEventItem[];
  total: number;
  limit: number;
  offset: number;
};

export type AuditEventFilters = {
  start_at?: string;
  end_at?: string;
  action?: string;
  result?: string;
  actor_id?: string;
  session_id?: string;
  patient_id?: string;
  encounter_id?: string;
  document_id?: string;
  limit?: number;
  offset?: number;
};

export type AdminUserListItem = {
  id: number;
  email: string;
  name: string;
  last_name: string;
  role: string;
  is_active: boolean;
  clinical_access_enabled: boolean;
  last_login: string | null;
  date_joined: string;
  active_session_count: number;
  last_session_started_at: string | null;
  login_success_24h: number;
  login_failure_24h: number;
};

export type AdminUserListResponse = {
  items: AdminUserListItem[];
  total: number;
  limit: number;
  offset: number;
};

export type AdminUserSession = {
  id: string;
  user_id: number | null;
  ip_hmac: string;
  network_prefix: string | null;
  user_agent_summary: string | null;
  started_at: string;
  last_seen_at: string;
  ended_at: string | null;
};

export type AdminUserDetailResponse = {
  user: AdminUserListItem;
  sessions: AdminUserSession[];
  recent_events: AuditEventItem[];
};

export type AdminUsersFilters = {
  q?: string;
  is_active?: string;
  clinical_access_enabled?: string;
  role?: string;
  limit?: number;
  offset?: number;
};

function cleanParams(
  params: Record<string, number | string | undefined>,
): Record<string, number | string> {
  return Object.fromEntries(
    Object.entries(params).filter(
      ([, value]) => value !== undefined && value !== "",
    ),
  ) as Record<string, number | string>;
}

export async function getInternalAuditEvents(
  params: AuditEventFilters,
): Promise<AuditEventListResponse> {
  const response = await axiosInstance.get<AuditEventListResponse>(
    "/api/v1/internal/audit-events",
    {
      params: cleanParams(params),
    },
  );
  return response.data;
}

export async function getInternalUsers(
  params: AdminUsersFilters,
): Promise<AdminUserListResponse> {
  const normalized: Record<string, string | number | undefined> = {
    q: params.q,
    role: params.role,
    limit: params.limit,
    offset: params.offset,
  };
  if (params.is_active === "true" || params.is_active === "false") {
    normalized.is_active = params.is_active;
  }
  if (
    params.clinical_access_enabled === "true" ||
    params.clinical_access_enabled === "false"
  ) {
    normalized.clinical_access_enabled = params.clinical_access_enabled;
  }
  const response = await axiosInstance.get<AdminUserListResponse>(
    "/api/v1/internal/users",
    {
      params: cleanParams(normalized),
    },
  );
  return response.data;
}

export async function getInternalUserDetail(
  userId: number,
): Promise<AdminUserDetailResponse> {
  const response = await axiosInstance.get<AdminUserDetailResponse>(
    `/api/v1/internal/users/${userId}`,
  );
  return response.data;
}

export type AdminUserStatusUpdate = {
  is_active?: boolean;
  clinical_access_enabled?: boolean;
};

export async function updateInternalUserStatus(
  userId: number,
  payload: AdminUserStatusUpdate,
): Promise<void> {
  await axiosInstance.patch(`/api/v1/internal/users/${userId}/status`, payload);
}
