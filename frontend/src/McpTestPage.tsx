import { Fragment, useEffect, useMemo, useState } from "react";
import {
  CircleMarker,
  MapContainer,
  Polygon,
  Polyline,
  TileLayer,
  Tooltip,
  useMap,
} from "react-leaflet";

import type { McpAgentTestResponse, McpGeoFeature } from "./mcpTestTypes";

type McpTestPageProps = {
  backendStatus: string;
  error: string | null;
  prompt: string;
  result: McpAgentTestResponse | null;
  siteContext: string;
  status: string;
  onBack: () => void;
  onPromptChange: (value: string) => void;
  onRun: () => void;
  onSiteContextChange: (value: string) => void;
};

type McpActivityItem = {
  id: string;
  actor: "user" | "backend" | "collector" | "agent" | "evidence";
  title: string;
  mcpUrl: string;
  status: string;
  kind: "request" | "tool_call" | "tool_result" | "evidence" | "map" | "final" | "pending";
  providerName?: string;
  providerId?: string;
  queryScope?: string;
  source?: string;
  arguments: Record<string, unknown>;
  resultPreview?: string;
  evidence?: McpAgentTestResponse["evidence"][number];
  resultItems?: Record<string, unknown>[];
  resultFields?: Record<string, unknown>;
};

function providerResultText(evidenceItem: McpAgentTestResponse["evidence"][number]) {
  if (evidenceItem.error) {
    return evidenceItem.error;
  }

  if (evidenceItem.feature_count !== null && evidenceItem.feature_count !== undefined) {
    const geometryCount = evidenceItem.geo_features.length;
    return `returned ${evidenceItem.feature_count} features${
      geometryCount > 0 ? ` with ${geometryCount} mapped geometries` : ""
    }`;
  }

  return evidenceItem.data_status ?? evidenceItem.query_status;
}

function buildMcpConversationItems(
  result: McpAgentTestResponse | null,
  status: string,
  mcpUrl: string,
  prompt: string,
  siteContext: string,
): McpActivityItem[] {
  const requestItems: McpActivityItem[] = [
    {
      id: "user-request",
      actor: "user",
      title: "Site feasibility request",
      mcpUrl,
      status: "submitted",
      kind: "request",
      arguments: {
        site_context: siteContext || null,
        prompt,
      },
      resultPreview: prompt,
    },
  ];

  if (!result) {
    return [
      ...requestItems,
      {
        id: "planned-request",
        actor: "backend",
        title: "Start feasibility analysis run",
        mcpUrl,
        status: status === "running" ? "active" : "waiting",
        kind: status === "running" ? "tool_call" : "pending",
        arguments: {
          debug_endpoint: "POST /api/mcp-smoke/agent",
          site_context: siteContext || null,
          state: "TX",
        },
        resultPreview: "Starts the same feasibility-analysis workflow with MCP debug telemetry enabled.",
      },
      {
        id: "planned-list-providers",
        actor: "collector",
        title: "FastMCP list_providers",
        mcpUrl,
        status: status === "running" ? "active" : "planned",
        kind: "pending",
        arguments: { state: "TX" },
        resultPreview: "Waiting for provider discovery results.",
      },
      {
        id: "planned-query-provider",
        actor: "collector",
        title: "FastMCP provider evidence",
        mcpUrl,
        status: status === "running" ? "active" : "planned",
        kind: "pending",
        arguments: {
          metadata_only: "provider_metadata",
          queryable: "query_provider",
          site_filter: "when available",
        },
        resultPreview: "Waiting for provider metadata and site-scoped query results.",
      },
      {
        id: "planned-agent-tools",
        actor: "agent",
        title: "Pydantic AI agent",
        mcpUrl,
        status: status === "running" ? "active" : "planned",
        kind: "pending",
        arguments: {},
        resultPreview: "Researching with MCP tools. Exact agent calls appear when the backend response returns.",
      },
    ];
  }

  const rawCollectorItems: McpActivityItem[] = [
    {
      id: "raw-list-providers",
      actor: "collector",
      title: "FastMCP list_providers",
      mcpUrl: result.mcp_url,
      status: "returned",
      kind: "tool_result",
      arguments: { state: "TX" },
      resultPreview: `returned ${result.evidence.length} configured providers`,
    },
    ...result.evidence.map((evidenceItem, index): McpActivityItem => ({
        id: `raw-evidence-${evidenceItem.provider_id}-${index}`,
        actor: "collector",
        title: evidenceItem.source === "metadata_only" ? "FastMCP provider_metadata" : "FastMCP query_provider",
        mcpUrl: result.mcp_url,
        status: evidenceItem.query_status,
        kind: "evidence",
        providerName: evidenceItem.provider_name,
        providerId: evidenceItem.provider_id,
        source: evidenceItem.source,
        queryScope: evidenceItem.query_scope,
        evidence: evidenceItem,
        arguments: {
          provider_id: evidenceItem.provider_id,
          ...evidenceItem.request_params,
        },
        resultPreview: providerResultText(evidenceItem),
      })),
  ];

  const agentItems: McpActivityItem[] = result.tool_call_records.map((toolCall, index) => ({
    id: `agent-${toolCall.tool_name}-${index}`,
    actor: "agent",
    title: `Pydantic AI agent called ${toolCall.tool_name}`,
    mcpUrl: result.mcp_url,
    status: toolCall.status,
    kind: "tool_result",
    providerId: typeof toolCall.arguments.provider_id === "string" ? toolCall.arguments.provider_id : undefined,
    arguments: toolCall.arguments,
    resultPreview: toolCall.result_preview ?? "returned",
    resultItems: toolCall.result_items,
    resultFields: toolCall.result_fields,
  }));

  return [
    ...requestItems,
    {
      id: "request-start",
      actor: "backend",
      title: "Start feasibility analysis run",
      mcpUrl: result.mcp_url,
      status: "returned",
      kind: "tool_result",
      arguments: {
        debug_endpoint: "POST /api/mcp-smoke/agent",
        site_context: result.site_context ?? null,
        state: "TX",
      },
      resultPreview: "started provider evidence collection and Pydantic AI research with detailed MCP telemetry",
    },
    ...rawCollectorItems,
    ...agentItems,
    {
      id: "agent-conclusion",
      actor: "agent",
      title: "Final site evidence conclusion",
      mcpUrl: result.mcp_url,
      status: "complete",
      kind: "final",
      arguments: {},
      resultPreview: result.summary ?? "No summary returned.",
    },
  ];
}

function McpCollaborationTranscript({
  mcpUrl,
  prompt,
  result,
  siteContext,
  status,
}: {
  mcpUrl: string;
  prompt: string;
  result: McpAgentTestResponse | null;
  siteContext: string;
  status: string;
}) {
  const conversationItems = useMemo(
    () => buildMcpConversationItems(result, status, mcpUrl, prompt, siteContext),
    [mcpUrl, prompt, result, siteContext, status],
  );
  const geoFeatures = result?.evidence.flatMap((item) => item.geo_features) ?? [];

  return (
    <div className="mcp-chat-panel" aria-label="MCP collaboration transcript">
      <div className="mcp-chat-heading">
        <div>
          <h2>MCP Collaboration</h2>
          <p>
            Agent-driven transcript. Tool calls, typed evidence, and map evidence appear before the final answer.
          </p>
        </div>
        <span>{conversationItems.length} messages</span>
      </div>

      <ol className="mcp-chat-thread" aria-label="Chronological MCP collaboration messages">
        {conversationItems.map((item, index) => (
          <Fragment key={item.id}>
            {item.kind === "final" && result ? (
              <li className="mcp-chat-message evidence map">
                <div className="mcp-chat-avatar" aria-hidden="true">
                  MAP
                </div>
                <article className="mcp-chat-bubble">
                  <header>
                    <div>
                      <strong>Mapped geometry evidence</strong>
                      <small>{geoFeatures.length} provider geometries returned</small>
                    </div>
                    <span>evidence</span>
                  </header>
                  <McpEvidenceMap features={geoFeatures} siteContext={result.site_context ?? siteContext} />
                </article>
              </li>
            ) : null}
            <li className={`mcp-chat-message ${item.actor} ${item.kind}`}>
              <div className="mcp-chat-avatar" aria-hidden="true">
                {item.actor === "user" ? "U" : item.actor === "agent" ? "AI" : item.actor === "collector" ? "MCP" : "BE"}
              </div>
              <article className="mcp-chat-bubble">
                <header>
                  <div>
                    <strong>{item.title}</strong>
                    <small>
                      Step {index + 1} · {item.status}
                      {item.providerName ? ` · ${item.providerName}` : ""}
                      {item.queryScope ? ` · ${item.queryScope}` : ""}
                    </small>
                  </div>
                  <span>{item.actor}</span>
                </header>
                {item.resultPreview ? (
                  <p className={item.kind === "final" ? "mcp-agent-summary" : undefined}>{item.resultPreview}</p>
                ) : null}
                {item.kind === "final" && result?.provider_insights.length ? (
                  <McpFinalProviderInsights insights={result.provider_insights} />
                ) : null}
                {item.evidence ? <McpEvidenceCard evidence={item.evidence} /> : null}
                {item.resultItems && item.resultItems.length > 0 ? (
                  <McpToolReturnItems items={item.resultItems} />
                ) : null}
                {item.resultFields && Object.keys(item.resultFields).length > 0 ? (
                  <McpToolReturnFields fields={item.resultFields} />
                ) : null}
                {Object.keys(item.arguments).length > 0 ? (
                  <details>
                    <summary>Arguments</summary>
                    <code>{JSON.stringify(item.arguments, null, 2)}</code>
                  </details>
                ) : null}
              </article>
            </li>
          </Fragment>
        ))}
      </ol>
    </div>
  );
}

function McpToolReturnItems({ items }: { items: Record<string, unknown>[] }) {
  return (
    <div className="mcp-return-items" aria-label="Tool return items">
      {items.map((item, index) => (
        <div className="mcp-return-item" key={`return-item-${index}`}>
          {Object.entries(item).map(([key, value]) => (
            <span key={key}>
              <b>{key}</b>
              <em>{String(value)}</em>
            </span>
          ))}
        </div>
      ))}
    </div>
  );
}

function McpToolReturnFields({ fields }: { fields: Record<string, unknown> }) {
  return (
    <dl className="mcp-return-fields" aria-label="Tool return fields">
      {Object.entries(fields).map(([key, value]) => (
        <div key={key}>
          <dt>{key}</dt>
          <dd>{String(value)}</dd>
        </div>
      ))}
    </dl>
  );
}

function McpFinalProviderInsights({ insights }: { insights: Record<string, unknown>[] }) {
  return (
    <div className="mcp-final-insights" aria-label="Final provider insights">
      {insights.map((insight, index) => (
        <div className="mcp-final-insight" key={`${String(insight.provider_id ?? "provider")}-${index}`}>
          <strong>{String(insight.provider_id ?? "Unknown provider")}</strong>
          <span>{String(insight.status ?? "returned")}</span>
          {insight.summary ? <p>{String(insight.summary)}</p> : null}
          {Array.isArray(insight.limitations) && insight.limitations.length > 0 ? (
            <small>{insight.limitations.join("; ")}</small>
          ) : null}
        </div>
      ))}
    </div>
  );
}

function McpEvidenceCard({ evidence }: { evidence: McpAgentTestResponse["evidence"][number] }) {
  return (
    <div className="mcp-evidence-card">
      <dl>
        <div>
          <dt>Source</dt>
          <dd>{evidence.source}</dd>
        </div>
        <div>
          <dt>Scope</dt>
          <dd>{evidence.query_scope}</dd>
        </div>
        <div>
          <dt>Features</dt>
          <dd>{evidence.feature_count ?? "n/a"}</dd>
        </div>
        <div>
          <dt>Geometry</dt>
          <dd>{evidence.geo_features.length}</dd>
        </div>
      </dl>
      {evidence.request_url ? <small>{evidence.request_url}</small> : null}
      {Object.keys(evidence.data_preview).length > 0 ? (
        <details open={evidence.provider_id === "ercot_market_data_transparency"}>
          <summary>{evidence.source === "metadata_only" ? "Returned MCP metadata" : "Returned MCP data"}</summary>
          <McpStructuredValue value={evidence.data_preview} />
        </details>
      ) : null}
      {Object.keys(evidence.sample_attributes).length > 0 ? (
        <details>
          <summary>Sample attributes</summary>
          <code>{JSON.stringify(evidence.sample_attributes, null, 2)}</code>
        </details>
      ) : null}
    </div>
  );
}

function McpStructuredValue({ value }: { value: unknown }) {
  if (Array.isArray(value)) {
    return (
      <div className="mcp-structured-list">
        {value.map((item, index) => (
          <McpStructuredValue key={`structured-${index}`} value={item} />
        ))}
      </div>
    );
  }

  if (value && typeof value === "object") {
    return (
      <dl className="mcp-structured-object">
        {Object.entries(value as Record<string, unknown>).map(([key, item]) => (
          <div key={key}>
            <dt>{key}</dt>
            <dd>
              <McpStructuredValue value={item} />
            </dd>
          </div>
        ))}
      </dl>
    );
  }

  return <span className="mcp-structured-scalar">{String(value)}</span>;
}

function McpMapFit({ features }: { features: McpGeoFeature[] }) {
  const map = useMap();

  useEffect(() => {
    const points = features.flatMap((feature) => [
      ...(feature.point ? [feature.point] : []),
      ...feature.rings.flat(),
      ...feature.paths.flat(),
    ]);

    if (points.length === 0) {
      map.setView([30.2672, -97.7431], 12);
      return;
    }

    map.fitBounds(points, { animate: false, maxZoom: 17, padding: [24, 24] });
  }, [features, map]);

  return null;
}

function McpEvidenceMap({ features, siteContext }: { features: McpGeoFeature[]; siteContext: string }) {
  return (
    <div className="mcp-map-section">
      <div className="mcp-map-heading">
        <div>
          <h2>Geo Evidence Map</h2>
          <p>{features.length} mapped features from live provider geometry for {siteContext}.</p>
        </div>
      </div>
      <div className="mcp-map-frame">
        <MapContainer
          center={[30.2672, -97.7431]}
          className="mcp-leaflet-map"
          maxZoom={18}
          minZoom={9}
          scrollWheelZoom
          zoom={12}
          zoomControl={false}
        >
          <McpMapFit features={features} />
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />
          {features.map((feature, featureIndex) => (
            <Fragment key={`${feature.provider_id}-${featureIndex}`}>
              {feature.rings.map((ring, ringIndex) => (
                <Polygon
                  key={`${feature.provider_id}-${featureIndex}-ring-${ringIndex}`}
                  pathOptions={{
                    color: feature.provider_id.includes("water") ? "#087ea4" : "#166534",
                    fillColor: feature.provider_id.includes("water") ? "#38a7db" : "#22c55e",
                    fillOpacity: 0.18,
                    opacity: 0.85,
                    weight: 2,
                  }}
                  positions={ring}
                >
                  <Tooltip sticky>
                    {feature.provider_name}: {feature.label}
                  </Tooltip>
                </Polygon>
              ))}
              {feature.paths.map((path, pathIndex) => (
                <Polyline
                  key={`${feature.provider_id}-${featureIndex}-path-${pathIndex}`}
                  pathOptions={{ color: "#7c3aed", opacity: 0.85, weight: 3 }}
                  positions={path}
                >
                  <Tooltip sticky>
                    {feature.provider_name}: {feature.label}
                  </Tooltip>
                </Polyline>
              ))}
              {feature.point ? (
                <CircleMarker
                  center={feature.point}
                  pathOptions={{
                    color: "#ffffff",
                    fillColor: "#d91e2f",
                    fillOpacity: 1,
                    opacity: 1,
                    weight: 2,
                  }}
                  radius={7}
                >
                  <Tooltip sticky>
                    {feature.provider_name}: {feature.label}
                  </Tooltip>
                </CircleMarker>
              ) : null}
            </Fragment>
          ))}
        </MapContainer>
        {features.length === 0 ? (
          <div className="mcp-map-empty">
            No map geometry was returned. This usually means the provider was metadata-only, the query was an
            attribute lookup without geometry, or a geocoder/spatial endpoint is still missing.
          </div>
        ) : null}
      </div>
      {features.length > 0 ? (
        <div className="mcp-geo-list" aria-label="Mapped MCP geo features">
          {features.map((feature, index) => (
            <div className="mcp-geo-item" key={`${feature.provider_id}-geo-${index}`}>
              <strong>{feature.provider_name}</strong>
              <span>{feature.geometry_type}</span>
              <small>{feature.label}</small>
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}

export function McpTestPage({
  backendStatus,
  error,
  onBack,
  onPromptChange,
  onRun,
  onSiteContextChange,
  prompt,
  result,
  siteContext,
  status,
}: McpTestPageProps) {
  const siteScopedEvidenceCount =
    result?.evidence.filter((item) => item.source === "live_query" && item.query_scope.startsWith("site_")).length ?? 0;
  const displayedMcpUrl = result?.mcp_url ?? "http://127.0.0.1:9000/mcp";

  return (
    <main className="mcp-test-page">
      <section className="mcp-test-panel">
        <div className="mcp-test-heading">
          <div>
            <h1>Feasibility Analysis Debug</h1>
            <p>Run the site-feasibility workflow with the MCP/tool transcript exposed.</p>
          </div>
          <button type="button" onClick={onBack}>
            Back
          </button>
        </div>

        <label className="mcp-agent-prompt" htmlFor="mcp-site-context">
          Site / location context
          <input
            id="mcp-site-context"
            type="text"
            value={siteContext}
            onChange={(event) => onSiteContextChange(event.target.value)}
          />
        </label>

        <label className="mcp-agent-prompt" htmlFor="mcp-agent-prompt">
          Feasibility question
          <textarea
            id="mcp-agent-prompt"
            rows={5}
            value={prompt}
            onChange={(event) => onPromptChange(event.target.value)}
          />
        </label>

        <div className="mcp-test-actions">
          <button
            className="primary-button"
            disabled={status === "running" || prompt.trim().length === 0}
            type="button"
            onClick={onRun}
          >
            {status === "running" ? "Running analysis..." : "Start Analysis"}
          </button>
          <span>Backend: {backendStatus}</span>
        </div>

        {error ? <p className="mcp-test-error">{error}</p> : null}

        {result ? (
          <div className="mcp-test-summary">
            <span>MCP: {result.mcp_url}</span>
            <span>Site: {result.site_context ?? "not provided"}</span>
            <span>{result.tool_call_records.length || result.tool_calls.length} tool call records</span>
            <span>{result.provider_insights.length} provider insights</span>
            <span>{siteScopedEvidenceCount} site-scoped live queries</span>
            <span>{result.evidence.filter((item) => item.source === "live_query").length} total live queries</span>
            <span>{result.evidence.filter((item) => item.source === "metadata_only").length} metadata-only</span>
          </div>
        ) : status !== "running" ? (
          <p className="mcp-test-empty">
            Run the agent test to let the model decide which MCP provider tools to call.
          </p>
        ) : null}

        {status === "running" || result ? (
          <McpCollaborationTranscript
            mcpUrl={displayedMcpUrl}
            prompt={prompt}
            result={result}
            siteContext={siteContext}
            status={status}
          />
        ) : null}
      </section>
    </main>
  );
}
