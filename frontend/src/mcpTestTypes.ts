import type { LatLngTuple } from "leaflet";

export type McpAgentTestResponse = {
  mcp_url: string;
  summary?: string | null;
  agent_summary?: string | null;
  provider_insights: Record<string, unknown>[];
  tool_calls: string[];
  tool_call_records: McpToolCallRecord[];
  evidence: McpEvidenceResult[];
  site_context?: string | null;
};

export type McpSmokeResponse = {
  mcp_url: string;
  tools: McpToolSummary[];
  providers: McpEvidenceResult[];
};

export type McpToolSummary = {
  name: string;
  description?: string | null;
};

export type McpToolCallRecord = {
  tool_name: string;
  arguments: Record<string, unknown>;
  status: string;
  result_preview?: string | null;
  result_items: Record<string, unknown>[];
  result_fields: Record<string, unknown>;
};

export type McpEvidenceResult = {
  provider_id: string;
  provider_name: string;
  queryable: boolean;
  source: string;
  query_scope: string;
  mcp_tools: string[];
  request_url?: string | null;
  request_params: Record<string, unknown>;
  health_status?: string | null;
  query_status: string;
  data_status?: string | null;
  data_keys: string[];
  data_preview: Record<string, unknown>;
  feature_count?: number | null;
  sample_attributes: Record<string, unknown>;
  geo_features: McpGeoFeature[];
  error?: string | null;
};

export type McpGeoFeature = {
  provider_id: string;
  provider_name: string;
  label: string;
  geometry_type: string;
  rings: LatLngTuple[][];
  paths: LatLngTuple[][];
  point?: LatLngTuple | null;
  attributes: Record<string, unknown>;
};
