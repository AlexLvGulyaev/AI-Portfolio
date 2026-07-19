const API_BASE_URL = import.meta.env.VITE_ADMIN_API_URL || '/api/admin';

function getToken(): string | null {
  return localStorage.getItem('ai_portfolio_admin_token');
}

interface RequestOptions extends RequestInit {
  requireAuth?: boolean;
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { requireAuth = true, headers, ...rest } = options;

  const requestHeaders = new Headers({
    'Content-Type': 'application/json',
    Accept: 'application/json',
  });

  if (headers) {
    const initHeaders = new Headers(headers);
    initHeaders.forEach((value, key) => {
      requestHeaders.set(key, value);
    });
  }

  if (requireAuth) {
    const token = getToken();
    if (!token) {
      throw new Error('Authentication required');
    }
    requestHeaders.set('Authorization', `Bearer ${token}`);
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...rest,
    headers: requestHeaders,
  });

  if (response.status === 403) {
    throw new Error('Access denied: invalid or missing admin token');
  }

  if (!response.ok) {
    const text = await response.text().catch(() => '');
    throw new Error(`API error: ${response.status} ${response.statusText}${text ? ` - ${text}` : ''}`);
  }

  return response.json() as Promise<T>;
}

export const apiClient = {
  get: <T,>(path: string, options?: RequestOptions) =>
    request<T>(path, { ...options, method: 'GET' }),
  post: <T,>(path: string, body?: unknown, options?: RequestOptions) =>
    request<T>(path, {
      ...options,
      method: 'POST',
      body: body ? JSON.stringify(body) : undefined,
    }),
  patch: <T,>(path: string, body?: unknown, options?: RequestOptions) =>
    request<T>(path, {
      ...options,
      method: 'PATCH',
      body: body ? JSON.stringify(body) : undefined,
    }),
  delete: <T,>(path: string, options?: RequestOptions) =>
    request<T>(path, { ...options, method: 'DELETE' }),
};

// ------------------------------------------------------------------
// Types
// ------------------------------------------------------------------

export interface DashboardData {
  status: string;
  system: {
    backend: string;
    postgresql: string;
    chromadb: string;
  };
  ai_providers: {
    total: number;
    enabled: number;
    active: AIProvider | null;
    fallback: AIProvider | null;
    providers: AIProvider[];
  };
  project_cards: { total: number; visible: number; homepage: number };
  knowledge_base: {
    sources: number;
    last_sync_at: string | null;
    last_sync_status: string;
    last_sync_stats: Record<string, unknown> | null;
  };
  logs: { total: number };
  conversations: { total: number; active: number };
  timestamp: string;
}

export interface AIProvider {
  id: string;
  provider_key: string;
  display_name: string;
  model_name: string;
  is_enabled: boolean;
  is_active: boolean;
  is_fallback: boolean;
  temperature: number;
  max_tokens: number;
  base_url: string | null;
  api_key_env_key: string;
  base_url_env_key: string;
  effective_base_url: string | null;
  readiness: string;
  missing_env_keys: string[];
  implementation_status: string;
  created_at: string;
  updated_at: string;
}

export interface AIProviderUpdate {
  model_name?: string;
  is_enabled?: boolean;
  temperature?: number | null;
  max_tokens?: number | null;
  base_url?: string | null;
}

export interface AIProviderTestResult {
  provider_key: string;
  ok: boolean;
  readiness: string;
  message: string;
  missing_env_keys: string[];
  implementation_status: string;
}

export interface KnowledgeSource {
  id: string;
  source_type: 'github_repo' | 'local_directory' | 'local_file';
  identifier: string;
  branch: string | null;
  base_path: string | null;
  is_enabled: boolean;
  last_sync_at: string | null;
  last_sync_status: string;
  last_sync_error: string | null;
  created_at: string;
  updated_at: string;
}

export interface ProjectCard {
  id: string;
  slug: string;
  title: string;
  short_description: string;
  category: string;
  tags: string[];
  display_order: number;
  show_on_homepage: number;
  is_visible: boolean;
  knowledge_content: string | null;
  external_url: string | null;
  created_at: string;
  updated_at: string;
}

export type ProjectCardCreate = Omit<ProjectCard, 'id' | 'created_at' | 'updated_at'>;
export type ProjectCardUpdate = Partial<ProjectCardCreate>;

export type KnowledgeSourceCreate = Omit<KnowledgeSource, 'id' | 'last_sync_at' | 'last_sync_status' | 'last_sync_error' | 'created_at' | 'updated_at'>;
export type KnowledgeSourceUpdate = Partial<KnowledgeSourceCreate>;

export interface ChromaStatus {
  status: 'ok' | 'error';
  collection_name?: string;
  embedding_model?: string;
  chunks?: number;
  error?: string;
}

export interface KnowledgeChunk {
  id: string;
  content: string;
  metadata: Record<string, unknown>;
}

export interface SyncJob {
  job_id: string;
  status: string;
  started_at: string | null;
  finished_at: string | null;
  stats: {
    documents_processed: number;
    chunks_created: number;
    sources_processed: number;
    errors: string[];
  };
  error_message: string | null;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface OperationalLog {
  id: string;
  event_type: string;
  session_id: string | null;
  user_id: string | null;
  source: string | null;
  query: string | null;
  response: string | null;
  model_name: string | null;
  provider_key: string | null;
  from_cache: boolean | null;
  response_time_ms: number | null;
  status: string;
  error_message: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface ChatSession {
  id: string;
  user_id: string | null;
  visitor_id: string | null;
  mode: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  message_count: number;
  turns_approx: number;
  last_execution: ConversationLastExecution | null;
}

export interface ChatMessage {
  id: string;
  role: string;
  content: string;
  created_at: string;
}

export interface ConversationTurn {
  user: string;
  assistant: string;
  cache_hit: boolean | null;
  response_time_ms: number | null;
  execution_id: string | null;
}

export interface ConversationLastExecution {
  id: string;
  route: string;
  status: string;
  provider_key: string | null;
  model_name: string | null;
  client_ip: string | null;
  response_time_ms: number | null;
  cache_hit: boolean | null;
  rag_used: boolean;
  started_at: string | null;
  finished_at: string | null;
}

export interface ConversationBudget {
  max_recent_messages: number;
  max_message_chars: number;
  total_memory_chars_budget: number;
}

export interface ConversationDetail extends ChatSession {
  message_count: number;
  messages: ChatMessage[];
  recent_turns: ConversationTurn[];
  executions: ExecutionSessionDetail[];
  budget: ConversationBudget;
  memory_source: string;
}

export interface ExecutionStep {
  id: string;
  execution_session_id: string;
  stage_name: string;
  step_order: number;
  status: string;
  started_at: string | null;
  finished_at: string | null;
  duration_ms: number | null;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface ExecutionSession {
  id: string;
  session_id: string | null;
  user_id: string | null;
  visitor_id: string | null;
  client_ip: string | null;
  user_agent: string | null;
  event_type: string;
  route: string;
  status: string;
  started_at: string | null;
  finished_at: string | null;
  duration_ms: number | null;
  provider_key: string | null;
  model_name: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
  is_backfilled: boolean;
}

export interface ExecutionSessionDetail extends ExecutionSession {
  steps: ExecutionStep[];
}

// ------------------------------------------------------------------
// API functions
// ------------------------------------------------------------------

export function getDashboard() {
  return apiClient.get<DashboardData>('/dashboard');
}

export function getChromaStatus() {
  return apiClient.get<ChromaStatus>('/knowledge-base/status');
}

export function listSources() {
  return apiClient.get<{ items: KnowledgeSource[] }>('/knowledge-base/sources');
}

export function createSource(data: KnowledgeSourceCreate) {
  return apiClient.post<KnowledgeSource>('/knowledge-base/sources', data);
}

export function updateSource(id: string, data: KnowledgeSourceUpdate) {
  return apiClient.patch<KnowledgeSource>(`/knowledge-base/sources/${id}`, data);
}

export function deleteSource(id: string) {
  return apiClient.delete<{ ok: boolean }>(`/knowledge-base/sources/${id}`);
}

export function syncKnowledgeBase() {
  return apiClient.post<SyncJob>('/knowledge-base/sync');
}

export function getSyncJob(jobId: string) {
  return apiClient.get<SyncJob>(`/knowledge-base/sync/${jobId}`);
}

export function listProjectCards() {
  return apiClient.get<{ items: ProjectCard[] }>('/knowledge-base/project-cards');
}

export function createProjectCard(data: ProjectCardCreate) {
  return apiClient.post<ProjectCard>('/knowledge-base/project-cards', data);
}

export function updateProjectCard(id: string, data: ProjectCardUpdate) {
  return apiClient.patch<ProjectCard>(`/knowledge-base/project-cards/${id}`, data);
}

export function deleteProjectCard(id: string) {
  return apiClient.delete<{ ok: boolean }>(`/knowledge-base/project-cards/${id}`);
}

export function getProjectCardChunks(id: string) {
  return apiClient.get<{ items: KnowledgeChunk[] }>(`/knowledge-base/project-cards/${id}/chunks`);
}

export function listLogs(params?: {
  event_type?: string;
  status?: string;
  date_from?: string;
  date_to?: string;
  limit?: number;
  offset?: number;
}) {
  const searchParams = new URLSearchParams();
  if (params?.event_type) searchParams.set('event_type', params.event_type);
  if (params?.status) searchParams.set('status', params.status);
  if (params?.date_from) searchParams.set('date_from', params.date_from);
  if (params?.date_to) searchParams.set('date_to', params.date_to);
  if (params?.limit !== undefined) searchParams.set('limit', String(params.limit));
  if (params?.offset !== undefined) searchParams.set('offset', String(params.offset));
  const query = searchParams.toString() ? `?${searchParams.toString()}` : '';
  return apiClient.get<PaginatedResponse<OperationalLog>>(`/logs${query}`);
}

export function listConversations(params?: {
  hours?: number;
  route?: string;
  active_only?: boolean;
  search?: string;
  limit?: number;
  offset?: number;
}) {
  const searchParams = new URLSearchParams();
  if (params?.hours !== undefined) searchParams.set('hours', String(params.hours));
  if (params?.route) searchParams.set('route', params.route);
  if (params?.active_only !== undefined) searchParams.set('active_only', String(params.active_only));
  if (params?.search) searchParams.set('search', params.search);
  if (params?.limit !== undefined) searchParams.set('limit', String(params.limit));
  if (params?.offset !== undefined) searchParams.set('offset', String(params.offset));
  const query = searchParams.toString() ? `?${searchParams.toString()}` : '';
  return apiClient.get<PaginatedResponse<ChatSession>>(`/conversations${query}`);
}

export function getConversation(id: string) {
  return apiClient.get<ConversationDetail>(`/conversations/${id}`);
}

export function loginAdmin(token: string) {
  return apiClient.post<{ success: boolean }>(
    '/login',
    { token },
    { requireAuth: false },
  );
}

export function listExecutionSessions(params?: {
  route?: string;
  status?: string;
  date_from?: string;
  date_to?: string;
  search?: string;
  limit?: number;
  offset?: number;
}) {
  const searchParams = new URLSearchParams();
  if (params?.route) searchParams.set('route', params.route);
  if (params?.status) searchParams.set('status', params.status);
  if (params?.date_from) searchParams.set('date_from', params.date_from);
  if (params?.date_to) searchParams.set('date_to', params.date_to);
  if (params?.search) searchParams.set('search', params.search);
  if (params?.limit !== undefined) searchParams.set('limit', String(params.limit));
  if (params?.offset !== undefined) searchParams.set('offset', String(params.offset));
  const query = searchParams.toString() ? `?${searchParams.toString()}` : '';
  return apiClient.get<PaginatedResponse<ExecutionSession>>(`/execution-sessions${query}`);
}

export function getExecutionSession(id: string) {
  return apiClient.get<ExecutionSessionDetail>(`/execution-sessions/${id}`);
}

export function listAIProviders() {
  return apiClient.get<AIProvider[]>('/ai-providers');
}

export function updateAIProvider(providerKey: string, data: AIProviderUpdate) {
  return apiClient.patch<AIProvider>(`/ai-providers/${providerKey}`, data);
}

export function activateAIProvider(providerKey: string) {
  return apiClient.post<AIProvider>(`/ai-providers/${providerKey}/activate`);
}

export function setFallbackAIProvider(providerKey: string) {
  return apiClient.post<AIProvider>(`/ai-providers/${providerKey}/set-fallback`);
}

export function testAIProvider(providerKey: string) {
  return apiClient.post<AIProviderTestResult>(`/ai-providers/${providerKey}/test`);
}
