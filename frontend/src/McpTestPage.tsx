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

import type { McpAgentTestResponse, McpEvidenceResult, McpGeoFeature, McpSmokeResponse } from "./mcpTestTypes";

type McpTestPageProps = {
  backendStatus: string;
  collectorResult: McpSmokeResponse | null;
  collectorStatus: string;
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
  evidence?: McpEvidenceResult;
  resultItems?: Record<string, unknown>[];
  resultFields?: Record<string, unknown>;
};

function providerResultText(evidenceItem: McpEvidenceResult) {
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

function providerListItems(evidence: McpEvidenceResult[]): Record<string, unknown>[] {
  return evidence.map((item) => ({
    provider_id: item.provider_id,
    provider: item.provider_name,
    queryable: item.queryable,
    source: item.source,
    scope: item.query_scope,
    status: item.query_status,
  }));
}

function buildMcpConversationItems(
  result: McpAgentTestResponse | null,
  collectorResult: McpSmokeResponse | null,
  status: string,
  collectorStatus: string,
  mcpUrl: string,
  prompt: string,
  siteContext: string,
): McpActivityItem[] {
  const evidence = collectorResult?.providers ?? result?.evidence ?? [];
  const currentMcpUrl = collectorResult?.mcp_url ?? result?.mcp_url ?? mcpUrl;
  const requestItems: McpActivityItem[] = [
    {
      id: "user-request",
      actor: "user",
      title: "Site feasibility request",
      mcpUrl: currentMcpUrl,
      status: "submitted",
      kind: "request",
      arguments: {
        site_context: siteContext || null,
        prompt,
      },
      resultPreview: prompt,
    },
  ];

  if (!result && !collectorResult) {
    return [
      ...requestItems,
      {
        id: "planned-request",
        actor: "backend",
        title: "Start feasibility analysis run",
        mcpUrl: currentMcpUrl,
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
        title: "MCP list_providers",
        mcpUrl: currentMcpUrl,
        status: collectorStatus === "running" || status === "running" ? "active" : "planned",
        kind: "pending",
        arguments: { state: "TX" },
        resultPreview: "Waiting for provider discovery results.",
      },
      {
        id: "planned-query-provider",
        actor: "collector",
        title: "MCP provider evidence",
        mcpUrl: currentMcpUrl,
        status: collectorStatus === "running" || status === "running" ? "active" : "planned",
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
        title: "Research agent",
        mcpUrl: currentMcpUrl,
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
      title: "MCP list_providers",
      mcpUrl: currentMcpUrl,
      status: collectorStatus === "error" && evidence.length === 0 ? "error" : "returned",
      kind: "tool_result",
      arguments: { state: "TX" },
      resultPreview: `returned ${evidence.length} configured providers`,
      resultItems: providerListItems(evidence),
    },
    ...evidence.map((evidenceItem, index): McpActivityItem => ({
        id: `raw-evidence-${evidenceItem.provider_id}-${index}`,
        actor: "collector",
        title: evidenceItem.source === "metadata_only" ? "MCP provider_metadata" : "MCP query_provider",
        mcpUrl: currentMcpUrl,
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

  const agentItems: McpActivityItem[] = result
    ? result.tool_call_records.map((toolCall, index) => ({
    id: `agent-${toolCall.tool_name}-${index}`,
    actor: "agent",
    title: `Research agent called ${toolCall.tool_name}`,
    mcpUrl: result.mcp_url,
    status: toolCall.status,
    kind: "tool_result",
    providerId: typeof toolCall.arguments.provider_id === "string" ? toolCall.arguments.provider_id : undefined,
    arguments: toolCall.arguments,
    resultPreview: toolCall.result_preview ?? "returned",
    resultItems: toolCall.result_items,
    resultFields: toolCall.result_fields,
      }))
    : [];

  return [
    ...requestItems,
    {
      id: "request-start",
      actor: "backend",
      title: "Start feasibility analysis run",
      mcpUrl: currentMcpUrl,
      status: result ? "returned" : "collector_returned",
      kind: "tool_result",
      arguments: {
        workflow_endpoint: "POST /api/analysis",
        debug_provider_endpoint: "POST /api/mcp-smoke/providers",
        debug_agent_endpoint: "POST /api/mcp-smoke/agent",
        site_context: result?.site_context ?? (siteContext || null),
        state: "TX",
      },
      resultPreview: result
        ? "completed provider evidence collection and agent research with detailed MCP telemetry"
        : "provider evidence collection returned; agent research is still running",
    },
    ...rawCollectorItems,
    ...agentItems,
    result
      ? {
          id: "agent-conclusion",
          actor: "agent",
          title: "Final site evidence conclusion",
          mcpUrl: result.mcp_url,
          status: "complete",
          kind: "final",
          arguments: {},
          resultPreview: result.summary ?? "No summary returned.",
        }
      : {
          id: "agent-running",
          actor: "agent",
          title: "Research agent",
          mcpUrl: currentMcpUrl,
          status: status === "running" ? "active" : status,
          kind: "pending",
          arguments: {},
          resultPreview: "Researching with MCP tools. Agent tool calls and final answer appear when this step returns.",
        },
  ];
}

function McpCollaborationTranscript({
  collectorResult,
  collectorStatus,
  mcpUrl,
  prompt,
  result,
  siteContext,
  status,
}: {
  collectorResult: McpSmokeResponse | null;
  collectorStatus: string;
  mcpUrl: string;
  prompt: string;
  result: McpAgentTestResponse | null;
  siteContext: string;
  status: string;
}) {
  const conversationItems = useMemo(
    () => buildMcpConversationItems(result, collectorResult, status, collectorStatus, mcpUrl, prompt, siteContext),
    [collectorResult, collectorStatus, mcpUrl, prompt, result, siteContext, status],
  );
  const evidence = collectorResult?.providers ?? result?.evidence ?? [];
  const geoFeatures = evidence.flatMap((item) => item.geo_features);

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
                      <small>{geoFeatures.length} mapped evidence features returned</small>
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
      <dl className="mcp-evidence-metrics">
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
      {evidence.provider_id === "ercot_market_data_transparency" ? (
        <McpErcotLocationReport data={evidence.data_preview} />
      ) : null}
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

function asRecord(value: unknown): Record<string, unknown> {
  return isRecordValue(value) ? value : {};
}

function asArray(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function McpErcotLocationReport({ data }: { data: Record<string, unknown> }) {
  const report = asRecord(data.report);
  if (Object.keys(report).length === 0) {
    return null;
  }

  const reports = asRecord(data.ercot_reports);
  const statewideContext = asRecord(data.statewide_context);
  const gridCondition = asRecord(statewideContext.grid_condition);
  const observations = asArray(report.key_observations).map(String);
  const reportEntries = Object.entries(reports).map(([key, value]) => {
    const reportValue = asRecord(value);
    const summary = asRecord(reportValue.summary);
    return {
      key,
      status: String(reportValue.status ?? "unknown"),
      recordCount: summary.record_count ?? "n/a",
      matchCount: summary.location_match_count ?? "n/a",
      priceSummary: asRecord(summary.price_summary),
      shadowSummary: asRecord(summary.shadow_price_summary),
    };
  });

  return (
    <section className="mcp-ercot-report" aria-label="ERCOT location power report">
      <div className="mcp-ercot-report-heading">
        <div>
          <strong>{String(report.title ?? "ERCOT Location Power Report")}</strong>
          <p>{String(report.summary ?? "No ERCOT report summary returned.")}</p>
        </div>
        <span>{String(report.site_power_risk_level ?? "unknown")}</span>
      </div>

      <dl className="mcp-ercot-kpis">
        <div>
          <dt>Auth</dt>
          <dd>{String(data.public_api_config_status ?? "unknown")}</dd>
        </div>
        <div>
          <dt>Statewide Context</dt>
          <dd>{String(gridCondition.title ?? gridCondition.state ?? "not provided")}</dd>
        </div>
        <div>
          <dt>Reports</dt>
          <dd>{reportEntries.length}</dd>
        </div>
      </dl>

      {observations.length > 0 ? (
        <ul className="mcp-ercot-observations">
          {observations.map((observation, index) => (
            <li key={`ercot-observation-${index}`}>{observation}</li>
          ))}
        </ul>
      ) : null}

      {reportEntries.length > 0 ? (
        <div className="mcp-ercot-report-grid">
          {reportEntries.map((entry) => (
            <article key={entry.key}>
              <strong>{formatStructuredKey(entry.key)}</strong>
              <span>{entry.status}</span>
              <small>
                {String(entry.recordCount)} records · {String(entry.matchCount)} location matches
              </small>
              {Object.keys(entry.priceSummary).length > 0 ? (
                <em>
                  Price min {String(entry.priceSummary.min)} / avg {String(entry.priceSummary.average)} / max{" "}
                  {String(entry.priceSummary.max)}
                </em>
              ) : null}
              {Object.keys(entry.shadowSummary).length > 0 ? (
                <em>
                  Shadow min {String(entry.shadowSummary.min)} / avg {String(entry.shadowSummary.average)} / max{" "}
                  {String(entry.shadowSummary.max)}
                </em>
              ) : null}
            </article>
          ))}
        </div>
      ) : null}

      {report.site_selection_interpretation ? (
        <p className="mcp-ercot-note">{String(report.site_selection_interpretation)}</p>
      ) : null}
    </section>
  );
}

function formatStructuredKey(key: string) {
  return key
    .replace(/_/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function isRecordValue(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function isUrlValue(value: string) {
  return /^https?:\/\//i.test(value);
}

function itemTitle(item: Record<string, unknown>, fallback: string) {
  const title = item.label ?? item.title ?? item.name ?? item.id ?? item.provider_id;
  return typeof title === "string" && title.trim().length > 0 ? title : fallback;
}

function McpStructuredValue({ value }: { value: unknown }) {
  if (Array.isArray(value)) {
    if (value.length === 0) {
      return <span className="mcp-structured-empty">None returned</span>;
    }

    if (value.every((item) => !isRecordValue(item) && !Array.isArray(item))) {
      return (
        <ul className="mcp-structured-bullets">
          {value.map((item, index) => (
            <li key={`structured-scalar-${index}`}>
              <McpStructuredValue value={item} />
            </li>
          ))}
        </ul>
      );
    }

    return (
      <div className="mcp-structured-list">
        {value.map((item, index) => (
          <article className="mcp-structured-card" key={`structured-${index}`}>
            {isRecordValue(item) ? (
              <>
                <strong>{itemTitle(item, `Item ${index + 1}`)}</strong>
                <McpStructuredValue value={item} />
              </>
            ) : (
              <McpStructuredValue value={item} />
            )}
          </article>
        ))}
      </div>
    );
  }

  if (isRecordValue(value)) {
    return (
      <dl className="mcp-structured-fields">
        {Object.entries(value).map(([key, item]) => {
          const isComplex = Array.isArray(item) || isRecordValue(item);
          return (
            <div className={`mcp-structured-row${isComplex ? " complex" : ""}`} key={key}>
              <dt>{formatStructuredKey(key)}</dt>
              <dd>
                <McpStructuredValue value={item} />
              </dd>
            </div>
          );
        })}
      </dl>
    );
  }

  if (typeof value === "string" && isUrlValue(value)) {
    return (
      <a className="mcp-structured-link" href={value} rel="noreferrer" target="_blank">
        {value}
      </a>
    );
  }

  if (value === null || value === undefined || value === "") {
    return <span className="mcp-structured-empty">Not provided</span>;
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
          <p>{features.length} mapped evidence features from provider geometry, geocoding, or catalog extents for {siteContext}.</p>
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
            attribute lookup without geometry, or no geocode/catalog extent was available.
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
  collectorResult,
  collectorStatus,
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
  const displayedEvidence = collectorResult?.providers ?? result?.evidence ?? [];
  const siteScopedEvidenceCount =
    displayedEvidence.filter((item) => item.source === "live_query" && item.query_scope.startsWith("site_")).length;
  const displayedMcpUrl = collectorResult?.mcp_url ?? result?.mcp_url ?? "http://127.0.0.1:9000/mcp";
  const displayedSiteContext = result?.site_context ?? siteContext;

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

        {result || collectorResult ? (
          <div className="mcp-test-summary">
            <span>MCP: {displayedMcpUrl}</span>
            <span>Site: {displayedSiteContext || "not provided"}</span>
            <span>{result?.tool_call_records.length || result?.tool_calls.length || 0} agent tool call records</span>
            <span>{result?.provider_insights.length ?? 0} provider insights</span>
            <span>{siteScopedEvidenceCount} site-scoped live queries</span>
            <span>{displayedEvidence.filter((item) => item.source === "live_query").length} total live queries</span>
            <span>{displayedEvidence.filter((item) => item.source === "metadata_only").length} metadata-only</span>
          </div>
        ) : status !== "running" ? (
          <p className="mcp-test-empty">
            Run the agent test to let the model decide which MCP provider tools to call.
          </p>
        ) : null}

        {status === "running" || collectorResult || result ? (
          <McpCollaborationTranscript
            collectorResult={collectorResult}
            collectorStatus={collectorStatus}
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
