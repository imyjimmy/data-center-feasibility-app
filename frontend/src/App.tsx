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
import type { LatLngTuple, PathOptions } from "leaflet";

type ApiHealth = {
  status: string;
  service: string;
  version: string;
};

type ProviderInsight = {
  provider_id: string;
  provider_name: string;
  concern: string;
  status: string;
  summary: string;
  source_url: string;
  queryable: boolean;
  limitations: string[];
};

type AnalysisRun = {
  run_id: string;
  status: string;
  provider_insights: ProviderInsight[];
};

type Page = "question" | "results";
type LandingCategory = "featured" | "site-search" | "utilities" | "risk" | "permits" | "reporting";
type CoolingMode = "air" | "hybrid" | "liquid";
type ZoningFilter = "any" | "industrial" | "review";
type ServiceFilter = "any" | "austin" | "pedernales" | "oncor";
type RoadAccessFilter = "any" | "direct" | "arterial";

type SidebarParameters = {
  itLoad: number;
  minAcres: number;
  coolingMode: CoolingMode;
  excludeFloodplain: boolean;
  zoningFit: ZoningFilter;
  electricService: ServiceFilter;
  waterService: ServiceFilter;
  roadAccess: RoadAccessFilter;
  maxSubstationDistance: number;
  layers: {
    substations: boolean;
    transmission: boolean;
    waterLines: boolean;
    floodplain: boolean;
    wetlands: boolean;
  };
};

type ParcelCandidate = {
  rank: number;
  id: string;
  name: string;
  jurisdiction: string;
  acres: number;
  score: number;
  zoning: string;
  zoningFit: "industrial" | "review" | "blocked";
  landUse: string;
  firstBlocker: string;
  electricService: string;
  waterService: string;
  roadAccess: string;
  roadAccessType: RoadAccessFilter;
  distanceToSubstation: number;
  fiberConfidence: "high" | "medium" | "low";
  floodplain: boolean;
  wetlands: boolean;
  coolingModes: CoolingMode[];
  center: LatLngTuple;
  mapRadius: number;
  evidence: string[];
  scoreBreakdown: {
    power: number;
    water: number;
    site: number;
    constraints: number;
    market: number;
  };
};

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";
const defaultProjectQuestion =
  "Which Austin-area parcels are plausible for a 25 MW edge data center, and what is the first blocker?";

const landingCategories: { id: LandingCategory; label: string }[] = [
  { id: "featured", label: "Featured" },
  { id: "site-search", label: "Site Search" },
  { id: "utilities", label: "Utilities" },
  { id: "risk", label: "Risk" },
  { id: "permits", label: "Permitting" },
  { id: "reporting", label: "Reporting" },
];

const landingActions: {
  category: LandingCategory;
  description: string;
  icon: "map" | "power" | "water" | "shield" | "permit" | "report" | "compare" | "route";
  prompt: string;
  title: string;
}[] = [
  {
    category: "featured",
    description:
      "Rank Austin-area parcels by acreage, substation distance, water service, zoning fit, and first diligence blocker.",
    icon: "map",
    prompt:
      "Shortlist Austin-area parcels for a 25 MW edge data center. Prioritize acreage, nearby substations, water service, zoning fit, road access, and first blocker.",
    title: "Shortlist viable parcels",
  },
  {
    category: "featured",
    description:
      "Start with utility pressure: nearby substations, likely service territory, transmission proximity, and capacity questions.",
    icon: "power",
    prompt:
      "Find data center sites where electric capacity is the main gating item. Compare substation distance, service territory, transmission proximity, and likely utility follow-ups.",
    title: "Run a power-first screen",
  },
  {
    category: "featured",
    description:
      "Check whether a site can support air, hybrid, or liquid cooling with a credible path through water-service diligence.",
    icon: "water",
    prompt:
      "Evaluate Austin-area data center parcels for water-service and cooling feasibility. Separate air-cooled, hybrid, and liquid-cooled options and flag water capacity blockers.",
    title: "Assess cooling and water",
  },
  {
    category: "featured",
    description:
      "Compare candidate sites side by side with first-blocker notes and a clean export-ready feasibility summary.",
    icon: "compare",
    prompt:
      "Compare the top Austin-area data center parcels side by side. Include suitability score, first blocker, utility concerns, zoning risk, road access, and next diligence steps.",
    title: "Compare finalist sites",
  },
  {
    category: "site-search",
    description:
      "Filter by contiguous acreage, industrial context, highway access, parcel geometry, and market-friction signals.",
    icon: "route",
    prompt:
      "Search for 25+ acre Austin-area parcels with industrial context, practical road access, and low market friction for an edge data center.",
    title: "Find acreage with access",
  },
  {
    category: "site-search",
    description:
      "Focus on sites that avoid known floodplain and wetlands overlays while keeping utility options nearby.",
    icon: "shield",
    prompt:
      "Find Austin-area parcels that avoid mapped floodplain and wetlands while staying close to power, water, and arterial road access.",
    title: "Screen clean constraints",
  },
  {
    category: "utilities",
    description:
      "Map electric and water provider evidence into the questions an owner would ask before tying up land.",
    icon: "power",
    prompt:
      "Identify utility-service questions for the strongest Austin-area data center parcels, including electric provider, water provider, substation distance, and capacity diligence.",
    title: "Build utility questions",
  },
  {
    category: "utilities",
    description:
      "Separate sites by cooling path and show where water service, redundancy, or discharge concerns need escalation.",
    icon: "water",
    prompt:
      "Group candidate parcels by cooling feasibility: air, hybrid, and liquid. Explain which sites need water capacity, redundancy, or discharge diligence first.",
    title: "Group by cooling path",
  },
  {
    category: "risk",
    description:
      "Surface floodplain, wetlands, road geometry, zoning, market, and utility risks before deeper engineering spend.",
    icon: "shield",
    prompt:
      "Create a risk register for Austin-area data center candidate parcels, covering floodplain, wetlands, zoning, road access, power, water, and market friction.",
    title: "Create a blocker register",
  },
  {
    category: "permits",
    description:
      "Translate zoning fit and jurisdiction into the likely entitlement path and first public-agency conversations.",
    icon: "permit",
    prompt:
      "Explain the permitting and zoning path for Austin-area data center candidate parcels. Flag industrial fits, ETJ reviews, blocked zoning, and agency questions.",
    title: "Map entitlement path",
  },
  {
    category: "reporting",
    description:
      "Turn parcel scores, evidence, provider notes, and next actions into a concise diligence memo.",
    icon: "report",
    prompt:
      "Draft an export-ready data center site diligence memo for the top Austin-area parcel candidates with scores, evidence, first blockers, and recommended next steps.",
    title: "Draft diligence memo",
  },
];

const defaultParameters: SidebarParameters = {
  itLoad: 25,
  minAcres: 25,
  coolingMode: "air",
  excludeFloodplain: false,
  zoningFit: "any",
  electricService: "any",
  waterService: "any",
  roadAccess: "any",
  maxSubstationDistance: 15,
  layers: {
    substations: true,
    transmission: true,
    waterLines: true,
    floodplain: true,
    wetlands: false,
  },
};

const parcelCandidates: ParcelCandidate[] = [
  {
    rank: 1,
    id: "TCAD-027541",
    name: "Pflugerville - SH 130 East",
    jurisdiction: "Austin ETJ",
    acres: 42.6,
    score: 86,
    zoning: "LI - Light Industrial",
    zoningFit: "industrial",
    landUse: "Undeveloped / light industrial",
    firstBlocker: "Electric Capacity",
    electricService: "Pedernales EC",
    waterService: "Manville WSC",
    roadAccess: "Direct (SH 130)",
    roadAccessType: "direct",
    distanceToSubstation: 5.2,
    fiberConfidence: "high",
    floodplain: false,
    wetlands: false,
    coolingModes: ["air", "hybrid"],
    center: [30.444, -97.566],
    mapRadius: 0.018,
    evidence: ["Direct SH 130 access", "Industrial zoning fit", "No mapped floodplain"],
    scoreBreakdown: { power: 18, water: 20, site: 20, constraints: 18, market: 10 },
  },
  {
    rank: 2,
    id: "TCAD-031908",
    name: "Hutto - CR 110",
    jurisdiction: "Travis / Williamson edge",
    acres: 63.4,
    score: 81,
    zoning: "ETJ review",
    zoningFit: "review",
    landUse: "Agricultural / undeveloped",
    firstBlocker: "Water Capacity",
    electricService: "Oncor",
    waterService: "Jonah SUD",
    roadAccess: "Arterial",
    roadAccessType: "arterial",
    distanceToSubstation: 8.6,
    fiberConfidence: "medium",
    floodplain: false,
    wetlands: false,
    coolingModes: ["air", "hybrid", "liquid"],
    center: [30.548, -97.551],
    mapRadius: 0.022,
    evidence: ["Large contiguous acreage", "Good highway proximity", "Utility territory needs call"],
    scoreBreakdown: { power: 16, water: 16, site: 20, constraints: 19, market: 10 },
  },
  {
    rank: 3,
    id: "TCAD-019776",
    name: "Cedar Park - Whitestone",
    jurisdiction: "Limited purpose",
    acres: 37.9,
    score: 68,
    zoning: "IP",
    zoningFit: "industrial",
    landUse: "Office / industrial flex",
    firstBlocker: "Electric Capacity",
    electricService: "Austin Energy",
    waterService: "Austin Water",
    roadAccess: "Arterial",
    roadAccessType: "arterial",
    distanceToSubstation: 11.4,
    fiberConfidence: "high",
    floodplain: false,
    wetlands: false,
    coolingModes: ["air", "hybrid"],
    center: [30.51, -97.81],
    mapRadius: 0.017,
    evidence: ["Strong fiber proxy", "Compatible use pattern", "Higher market friction"],
    scoreBreakdown: { power: 13, water: 18, site: 17, constraints: 12, market: 8 },
  },
  {
    rank: 4,
    id: "TCAD-016420",
    name: "Lago Vista - Lohmans Ford",
    jurisdiction: "Travis County",
    acres: 55.2,
    score: 64,
    zoning: "ETJ review",
    zoningFit: "review",
    landUse: "Undeveloped",
    firstBlocker: "Road Access",
    electricService: "Pedernales EC",
    waterService: "Travis County WCID",
    roadAccess: "Local",
    roadAccessType: "any",
    distanceToSubstation: 13.9,
    fiberConfidence: "medium",
    floodplain: false,
    wetlands: false,
    coolingModes: ["air", "hybrid"],
    center: [30.452, -97.982],
    mapRadius: 0.021,
    evidence: ["Acreage clears screen", "Water-service uncertainty", "Road geometry needs review"],
    scoreBreakdown: { power: 14, water: 15, site: 18, constraints: 10, market: 7 },
  },
  {
    rank: 5,
    id: "TCAD-044210",
    name: "Manor - FM 973",
    jurisdiction: "Austin ETJ",
    acres: 28.7,
    score: 63,
    zoning: "LI",
    zoningFit: "industrial",
    landUse: "Warehouse / undeveloped",
    firstBlocker: "Floodplain",
    electricService: "Bluebonnet EC",
    waterService: "Manville WSC",
    roadAccess: "Arterial",
    roadAccessType: "arterial",
    distanceToSubstation: 6.8,
    fiberConfidence: "medium",
    floodplain: true,
    wetlands: false,
    coolingModes: ["air"],
    center: [30.341, -97.558],
    mapRadius: 0.016,
    evidence: ["Meets acreage floor", "Industrial context", "Mapped floodplain touches site"],
    scoreBreakdown: { power: 16, water: 18, site: 12, constraints: 7, market: 10 },
  },
  {
    rank: 6,
    id: "TCAD-052118",
    name: "Kyle - Windy Hill",
    jurisdiction: "Hays County",
    acres: 41.3,
    score: 57,
    zoning: "PUD",
    zoningFit: "review",
    landUse: "Undeveloped",
    firstBlocker: "Electric Capacity",
    electricService: "Pedernales EC",
    waterService: "County Line SUD",
    roadAccess: "Arterial",
    roadAccessType: "arterial",
    distanceToSubstation: 14.1,
    fiberConfidence: "medium",
    floodplain: false,
    wetlands: false,
    coolingModes: ["air", "hybrid"],
    center: [30.006, -97.87],
    mapRadius: 0.018,
    evidence: ["Acreage is adequate", "No mapped floodplain", "PUD terms require manual review"],
    scoreBreakdown: { power: 11, water: 15, site: 16, constraints: 10, market: 5 },
  },
  {
    rank: 7,
    id: "TCAD-028815",
    name: "Driftwood - RM 150",
    jurisdiction: "Hays County",
    acres: 31.6,
    score: 55,
    zoning: "ETJ review",
    zoningFit: "review",
    landUse: "Agricultural",
    firstBlocker: "Water Capacity",
    electricService: "Pedernales EC",
    waterService: "Private / unknown",
    roadAccess: "Local",
    roadAccessType: "any",
    distanceToSubstation: 10.2,
    fiberConfidence: "medium",
    floodplain: false,
    wetlands: false,
    coolingModes: ["air"],
    center: [30.116, -98.029],
    mapRadius: 0.016,
    evidence: ["Low flood risk", "Water-service gap", "Rural access friction"],
    scoreBreakdown: { power: 14, water: 8, site: 15, constraints: 14, market: 4 },
  },
  {
    rank: 8,
    id: "TCAD-063904",
    name: "Georgetown - CR 245",
    jurisdiction: "Williamson County",
    acres: 27.8,
    score: 54,
    zoning: "ETJ review",
    zoningFit: "review",
    landUse: "Undeveloped",
    firstBlocker: "Road Access",
    electricService: "Oncor",
    waterService: "Georgetown Utility",
    roadAccess: "Local",
    roadAccessType: "any",
    distanceToSubstation: 9.5,
    fiberConfidence: "medium",
    floodplain: false,
    wetlands: true,
    coolingModes: ["air"],
    center: [30.687, -97.756],
    mapRadius: 0.015,
    evidence: ["Northern growth corridor", "Access road needs review", "Wetlands screen needed"],
    scoreBreakdown: { power: 13, water: 14, site: 11, constraints: 9, market: 7 },
  },
  {
    rank: 9,
    id: "TCAD-037612",
    name: "Buda - FM 1626",
    jurisdiction: "Hays County",
    acres: 35.1,
    score: 42,
    zoning: "GR",
    zoningFit: "review",
    landUse: "Commercial",
    firstBlocker: "Floodplain",
    electricService: "Pedernales EC",
    waterService: "Monarch Utilities",
    roadAccess: "Arterial",
    roadAccessType: "arterial",
    distanceToSubstation: 18.2,
    fiberConfidence: "low",
    floodplain: true,
    wetlands: false,
    coolingModes: ["air"],
    center: [30.082, -97.842],
    mapRadius: 0.017,
    evidence: ["Acreage clears floor", "Commercial reuse possible", "Multiple infrastructure concerns"],
    scoreBreakdown: { power: 7, water: 11, site: 12, constraints: 5, market: 7 },
  },
  {
    rank: 10,
    id: "TCAD-048003",
    name: "Dripping Springs - RR 12",
    jurisdiction: "Hays County",
    acres: 26.4,
    score: 38,
    zoning: "LO",
    zoningFit: "blocked",
    landUse: "Office / rural commercial",
    firstBlocker: "Zoning",
    electricService: "Pedernales EC",
    waterService: "Dripping Springs WSC",
    roadAccess: "Local",
    roadAccessType: "any",
    distanceToSubstation: 16.9,
    fiberConfidence: "low",
    floodplain: false,
    wetlands: false,
    coolingModes: ["air"],
    center: [30.19, -98.091],
    mapRadius: 0.015,
    evidence: ["Meets minimum acreage", "Low zoning fit", "Longer utility diligence path"],
    scoreBreakdown: { power: 8, water: 10, site: 8, constraints: 4, market: 8 },
  },
];

const coolingLabels: Record<CoolingMode, string> = {
  air: "Air Cooled",
  hybrid: "Hybrid",
  liquid: "Liquid",
};

const scoreLabels = [
  { label: "80 - 100", tone: "high", caption: "High" },
  { label: "60 - 79", tone: "medium", caption: "Medium" },
  { label: "0 - 59", tone: "low", caption: "Low" },
  { label: "Insufficient Data", tone: "unknown", caption: "" },
] as const;

const austinMapCenter: LatLngTuple = [30.335, -97.75];

const austinBoundary: LatLngTuple[] = [
  [30.615, -97.93],
  [30.54, -97.69],
  [30.345, -97.54],
  [30.105, -97.6],
  [30.02, -97.82],
  [30.16, -98.02],
  [30.38, -98.0],
  [30.615, -97.93],
];

const transmissionLines: LatLngTuple[][] = [
  [
    [30.7, -97.84],
    [30.48, -97.7],
    [30.25, -97.66],
    [29.98, -97.79],
  ],
  [
    [30.56, -98.03],
    [30.36, -97.8],
    [30.18, -97.63],
    [29.98, -97.54],
  ],
];

const waterLines: LatLngTuple[][] = [
  [
    [30.52, -97.98],
    [30.35, -97.86],
    [30.2, -97.72],
    [30.06, -97.61],
  ],
  [
    [30.46, -97.66],
    [30.37, -97.58],
    [30.3, -97.49],
  ],
];

const floodplainAreas: LatLngTuple[][] = [
  [
    [30.48, -97.86],
    [30.42, -97.83],
    [30.3, -97.78],
    [30.2, -97.7],
    [30.14, -97.73],
    [30.24, -97.84],
    [30.39, -97.91],
  ],
  [
    [30.25, -97.56],
    [30.18, -97.52],
    [30.08, -97.57],
    [30.12, -97.64],
    [30.22, -97.63],
  ],
];

const wetlandAreas: LatLngTuple[][] = [
  [
    [30.7, -97.8],
    [30.68, -97.73],
    [30.63, -97.74],
    [30.64, -97.82],
  ],
];

const substationPoints: LatLngTuple[] = [
  [30.46, -97.61],
  [30.39, -97.75],
  [30.24, -97.66],
  [30.12, -97.87],
  [30.56, -97.77],
];

function createParcelPolygon([lat, lng]: LatLngTuple, radius: number): LatLngTuple[] {
  return [
    [lat + radius * 0.95, lng - radius * 0.52],
    [lat + radius * 0.56, lng + radius * 0.82],
    [lat - radius * 0.24, lng + radius * 0.96],
    [lat - radius * 0.92, lng + radius * 0.14],
    [lat - radius * 0.66, lng - radius * 0.9],
    [lat + radius * 0.18, lng - radius * 1.04],
  ];
}

function parcelPathOptions(parcel: ParcelCandidate, isSelected: boolean): PathOptions {
  const tone = scoreTone(parcel.score);
  const color = tone === "high" ? "#11823b" : tone === "medium" ? "#df9d00" : "#d91e2f";

  return {
    color,
    fillColor: color,
    fillOpacity: isSelected ? 0.28 : 0.16,
    opacity: 0.95,
    weight: isSelected ? 4 : 2.5,
  };
}

function MapFocus({ center }: { center: LatLngTuple }) {
  const map = useMap();

  useEffect(() => {
    map.panTo(center, { animate: true });
  }, [center, map]);

  return null;
}

function scoreTone(score: number) {
  if (score >= 80) {
    return "high";
  }

  if (score >= 60) {
    return "medium";
  }

  return "low";
}

function matchesService(value: string, filter: ServiceFilter) {
  if (filter === "any") {
    return true;
  }

  return value.toLowerCase().includes(filter);
}

function matchesZoningFilter(fit: ParcelCandidate["zoningFit"], filter: ZoningFilter) {
  if (filter === "any") {
    return true;
  }

  if (filter === "review") {
    return fit === "industrial" || fit === "review";
  }

  return fit === "industrial";
}

function SidebarToggleIcon({ isOpen }: { isOpen: boolean }) {
  return (
    <svg aria-hidden="true" className="sidebar-toggle-icon" viewBox="0 0 32 32">
      <rect height="20" rx="5" width="24" x="4" y="6" />
      <path d={isOpen ? "M11 7.5v17" : "M21 7.5v17"} />
    </svg>
  );
}

function LandingActionIcon({ icon }: { icon: (typeof landingActions)[number]["icon"] }) {
  const commonProps = {
    "aria-hidden": true,
    className: "landing-action-icon",
    fill: "none",
    height: 24,
    stroke: "currentColor",
    strokeLinecap: "round",
    strokeLinejoin: "round",
    strokeWidth: 1.9,
    viewBox: "0 0 24 24",
    width: 24,
  } as const;

  if (icon === "power") {
    return (
      <svg {...commonProps}>
        <path d="M13 2 5.8 13h5.4L10 22l8.2-12.5h-5.6L13 2Z" />
      </svg>
    );
  }

  if (icon === "water") {
    return (
      <svg {...commonProps}>
        <path d="M12 3.2s6 6.5 6 11a6 6 0 0 1-12 0c0-4.5 6-11 6-11Z" />
        <path d="M9 14.7c.4 1.4 1.5 2.3 3 2.3" />
      </svg>
    );
  }

  if (icon === "shield") {
    return (
      <svg {...commonProps}>
        <path d="M12 3.2 18.5 6v5.4c0 4.1-2.6 7.5-6.5 9.4-3.9-1.9-6.5-5.3-6.5-9.4V6L12 3.2Z" />
        <path d="m9.3 12.1 1.8 1.8 3.7-4" />
      </svg>
    );
  }

  if (icon === "permit") {
    return (
      <svg {...commonProps}>
        <path d="M7 3.5h7.8L18 6.7v13.8H7V3.5Z" />
        <path d="M14.6 3.8v3.4h3.1" />
        <path d="M9.5 11h5" />
        <path d="M9.5 14.5h4" />
      </svg>
    );
  }

  if (icon === "report") {
    return (
      <svg {...commonProps}>
        <path d="M5 19.5V4.5h14v15H5Z" />
        <path d="M8.5 8h7" />
        <path d="M8.5 11.5h7" />
        <path d="M8.5 15h4.5" />
      </svg>
    );
  }

  if (icon === "compare") {
    return (
      <svg {...commonProps}>
        <path d="M4.5 6.5h15" />
        <path d="M8 4v13" />
        <path d="M16 7v13" />
        <path d="M4.5 17.5h15" />
      </svg>
    );
  }

  if (icon === "route") {
    return (
      <svg {...commonProps}>
        <path d="M6 18.5c4.2 0 2.3-13 7-13 3.6 0 3.3 7.5 6 7.5" />
        <path d="M5.5 18.5h1" />
        <path d="M18.5 13h1" />
        <path d="M13 5.5h1" />
      </svg>
    );
  }

  return (
    <svg {...commonProps}>
      <path d="M4 6.5 12 3l8 3.5v11L12 21l-8-3.5v-11Z" />
      <path d="M8 9.5h8" />
      <path d="M8 13h5" />
      <path d="M12 3v18" />
    </svg>
  );
}

function LandingActionPreview({ icon }: { icon: (typeof landingActions)[number]["icon"] }) {
  return (
    <div className={`landing-action-preview preview-${icon}`} aria-hidden="true">
      <div className="preview-grid">
        <span />
        <span />
        <span />
        <span />
      </div>
      <div className="preview-panel">
        <span />
        <span />
        <span />
      </div>
      <div className="preview-chart">
        <span />
        <span />
        <span />
      </div>
    </div>
  );
}

function App() {
  const [health, setHealth] = useState<ApiHealth | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [projectQuestion, setProjectQuestion] = useState(defaultProjectQuestion);
  const [page, setPage] = useState<Page>("question");
  const [landingCategory, setLandingCategory] = useState<LandingCategory>("featured");
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [scenarioPrompt, setScenarioPrompt] = useState("");
  const [parameters, setParameters] = useState<SidebarParameters>(defaultParameters);
  const [selectedParcelId, setSelectedParcelId] = useState(parcelCandidates[0].id);
  const [analysisRunId, setAnalysisRunId] = useState<string | null>(null);
  const [analysisStatus, setAnalysisStatus] = useState("idle");
  const [providerInsights, setProviderInsights] = useState<ProviderInsight[]>([]);

  const matchingParcels = useMemo(
    () =>
      parcelCandidates.filter((parcel) => {
        if (parcel.acres < parameters.minAcres) {
          return false;
        }

        if (parameters.excludeFloodplain && parcel.floodplain) {
          return false;
        }

        if (parcel.distanceToSubstation > parameters.maxSubstationDistance) {
          return false;
        }

        if (!parcel.coolingModes.includes(parameters.coolingMode)) {
          return false;
        }

        if (!matchesZoningFilter(parcel.zoningFit, parameters.zoningFit)) {
          return false;
        }

        if (!matchesService(parcel.electricService, parameters.electricService)) {
          return false;
        }

        if (!matchesService(parcel.waterService, parameters.waterService)) {
          return false;
        }

        if (parameters.roadAccess !== "any" && parcel.roadAccessType !== parameters.roadAccess) {
          return false;
        }

        return true;
      }),
    [parameters],
  );

  const selectedParcel =
    matchingParcels.find((parcel) => parcel.id === selectedParcelId) ??
    matchingParcels[0] ??
    parcelCandidates[0];

  useEffect(() => {
    const controller = new AbortController();

    fetch(`${apiBaseUrl}/health`, { signal: controller.signal })
      .then((response) => {
        if (!response.ok) {
          throw new Error(`Backend returned ${response.status}`);
        }

        return response.json() as Promise<ApiHealth>;
      })
      .then(setHealth)
      .catch((caughtError: unknown) => {
        if (caughtError instanceof DOMException && caughtError.name === "AbortError") {
          return;
        }

        setError(caughtError instanceof Error ? caughtError.message : "Unable to reach backend");
      });

    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (matchingParcels.length > 0 && !matchingParcels.some((parcel) => parcel.id === selectedParcelId)) {
      setSelectedParcelId(matchingParcels[0].id);
    }
  }, [matchingParcels, selectedParcelId]);

  useEffect(() => {
    if (!analysisRunId || analysisStatus === "complete") {
      return;
    }

    const controller = new AbortController();
    const interval = window.setInterval(() => {
      fetch(`${apiBaseUrl}/api/analysis-runs/${analysisRunId}`, { signal: controller.signal })
        .then((response) => {
          if (!response.ok) {
            throw new Error(`Analysis returned ${response.status}`);
          }

          return response.json() as Promise<AnalysisRun>;
        })
        .then((run) => {
          setAnalysisStatus(run.status);
          setProviderInsights(run.provider_insights);

          if (run.status === "complete") {
            window.clearInterval(interval);
          }
        })
        .catch((caughtError: unknown) => {
          if (caughtError instanceof DOMException && caughtError.name === "AbortError") {
            return;
          }

          setAnalysisStatus("error");
          window.clearInterval(interval);
        });
    }, 750);

    return () => {
      controller.abort();
      window.clearInterval(interval);
    };
  }, [analysisRunId, analysisStatus]);

  function startAnalysis() {
    const question = projectQuestion.trim();
    if (!question) {
      return;
    }

    setPage("results");
    setAnalysisStatus("queued");
    setProviderInsights([]);

    fetch(`${apiBaseUrl}/api/analysis-runs`, {
      body: JSON.stringify({ question, state: "TX" }),
      headers: { "Content-Type": "application/json" },
      method: "POST",
    })
      .then((response) => {
        if (!response.ok) {
          throw new Error(`Analysis start returned ${response.status}`);
        }

        return response.json() as Promise<AnalysisRun>;
      })
      .then((run) => {
        setAnalysisRunId(run.run_id);
        setAnalysisStatus(run.status);
        setProviderInsights(run.provider_insights);
      })
      .catch(() => setAnalysisStatus("error"));
  }

  const backendStatus = health ? `${health.status} (${health.version})` : error ? error : "checking...";
  const visibleLandingActions = landingActions.filter((action) => action.category === landingCategory);

  if (page === "results") {
    return (
      <main className="results-page">
        <header className="results-topbar">
          <div className="brand-lockup">
            <div className="brand-mark" aria-hidden="true">
              DC
            </div>
            <span className="brand-title">Austin Data Center Feasibility</span>
            <span className="mvp-pill">MVP</span>
          </div>
          <p className="topbar-question">{projectQuestion || defaultProjectQuestion}</p>
          <div className="topbar-actions">
            <button type="button">Save Scenario</button>
            <button type="button">Export</button>
            <button type="button">About</button>
          </div>
        </header>

        <div className={sidebarOpen ? "results-shell" : "results-shell sidebar-collapsed"}>
          <ScenarioSidebar
            backendStatus={backendStatus}
            isOpen={sidebarOpen}
            parameters={parameters}
            scenarioPrompt={scenarioPrompt}
            onPromptChange={setScenarioPrompt}
            onParametersChange={setParameters}
            onReset={() => setParameters(defaultParameters)}
            onToggle={() => setSidebarOpen((current) => !current)}
          />

          <section className="map-stage" aria-label="Austin-area parcel map">
            <MapContainer
              center={austinMapCenter}
              className="leaflet-map"
              maxZoom={13}
              minZoom={8}
              scrollWheelZoom
              zoom={10}
              zoomControl={false}
            >
              <MapFocus center={selectedParcel.center} />
              <TileLayer
                attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
                url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
              />
              <Polyline
                pathOptions={{ color: "#1264d8", dashArray: "5 6", opacity: 0.72, weight: 2 }}
                positions={austinBoundary}
              />
              {parameters.layers.transmission
                ? transmissionLines.map((line, index) => (
                    <Polyline
                      key={`transmission-${index}`}
                      pathOptions={{ color: "#718096", opacity: 0.62, weight: 4 }}
                      positions={line}
                    />
                  ))
                : null}
              {parameters.layers.waterLines
                ? waterLines.map((line, index) => (
                    <Polyline
                      key={`water-${index}`}
                      pathOptions={{ color: "#38a7db", opacity: 0.58, weight: 5 }}
                      positions={line}
                    />
                  ))
                : null}
              {parameters.layers.floodplain
                ? floodplainAreas.map((area, index) => (
                    <Polygon
                      key={`floodplain-${index}`}
                      pathOptions={{
                        color: "#4da3ff",
                        fillColor: "#4da3ff",
                        fillOpacity: 0.15,
                        opacity: 0.35,
                        weight: 1,
                      }}
                      positions={area}
                    />
                  ))
                : null}
              {parameters.layers.wetlands
                ? wetlandAreas.map((area, index) => (
                    <Polygon
                      key={`wetland-${index}`}
                      pathOptions={{
                        color: "#2d9b64",
                        fillColor: "#2d9b64",
                        fillOpacity: 0.18,
                        opacity: 0.5,
                        weight: 1,
                      }}
                      positions={area}
                    />
                  ))
                : null}
              {parameters.layers.substations
                ? substationPoints.map((point, index) => (
                    <CircleMarker
                      center={point}
                      key={`substation-${index}`}
                      pathOptions={{
                        color: "#20384a",
                        fillColor: "#ffffff",
                        fillOpacity: 1,
                        opacity: 0.78,
                        weight: 2,
                      }}
                      radius={5}
                    />
                  ))
                : null}
              {matchingParcels.map((parcel) => (
                <Fragment key={parcel.id}>
                  <Polygon
                    eventHandlers={{ click: () => setSelectedParcelId(parcel.id) }}
                    pathOptions={parcelPathOptions(parcel, parcel.id === selectedParcel.id)}
                    positions={createParcelPolygon(parcel.center, parcel.mapRadius)}
                  >
                    <Tooltip sticky>
                      {parcel.name} / Score {parcel.score}
                    </Tooltip>
                  </Polygon>
                  <CircleMarker
                    center={parcel.center}
                    eventHandlers={{ click: () => setSelectedParcelId(parcel.id) }}
                    pathOptions={{
                      color: "#ffffff",
                      fillColor:
                        scoreTone(parcel.score) === "high"
                          ? "#11823b"
                          : scoreTone(parcel.score) === "medium"
                            ? "#df9d00"
                            : "#d91e2f",
                      fillOpacity: 1,
                      opacity: 1,
                      weight: parcel.id === selectedParcel.id ? 4 : 2,
                    }}
                    radius={14}
                  >
                    <Tooltip
                      className={`parcel-rank-tooltip ${scoreTone(parcel.score)}`}
                      direction="center"
                      opacity={1}
                      permanent
                    >
                      {parcel.rank}
                    </Tooltip>
                  </CircleMarker>
                </Fragment>
              ))}
            </MapContainer>

            <div className="map-toolbar">
              <input aria-label="Search by place or address" placeholder="Search by place or address" />
              <div className="map-tools">
                <button type="button">Layers</button>
                <button type="button">Legend</button>
              </div>
            </div>

            <div className="score-legend">
              <strong>Suitability Score</strong>
              {scoreLabels.map((item) => (
                <div className="legend-row" key={item.label}>
                  <span className={`legend-dot ${item.tone}`} />
                  <span>{item.label}</span>
                  {item.caption ? <small>{item.caption}</small> : null}
                </div>
              ))}
            </div>
            <div className="map-scale">5 mi</div>
          </section>

          <ResultsInspector
            analysisStatus={analysisStatus}
            matchingParcels={matchingParcels}
            providerInsights={providerInsights}
            selectedParcel={selectedParcel}
            onSelectParcel={setSelectedParcelId}
          />
        </div>

        <footer className="source-bar">
          <strong>Sources</strong>
          <span>Travis County Appraisal District (2024)</span>
          <span>City of Austin Open Data</span>
          <span>FEMA NFHL (2024)</span>
          <span>USGS NHD (2023)</span>
          <span>OpenStreetMap contributors</span>
          <span>ERCOT (2024)</span>
          <span>PUCT Water CCN (2024)</span>
          <em>Data refreshed: 5/16/2025</em>
        </footer>
      </main>
    );
  }

  return (
    <main className="app-shell">
      <header className="landing-brand">
        <div className="landing-brand-mark" aria-hidden="true">
          DC
        </div>
        <span>Geo Claw</span>
      </header>

      <section className="intro-panel" aria-labelledby="landing-title">
        <div className="landing-hero-copy">
          <h1 id="landing-title">
            Data Center Feasibility
            <span>The Right Parcel for the Job</span>
          </h1>
        </div>

        <form
          className="question-composer"
          onSubmit={(event) => {
            event.preventDefault();
            startAnalysis();
          }}
        >
          <label className="sr-only" htmlFor="project-question">
            Question
          </label>
          <textarea
            className="question-field"
            id="project-question"
            placeholder="Ask for parcels, blockers, utility fit, water risk, or a diligence memo..."
            value={projectQuestion}
            onChange={(event) => setProjectQuestion(event.target.value)}
            rows={3}
          />
          <div className="composer-toolbar">
            <div className="composer-tools">
              <button className="icon-button" type="button" aria-label="Attach context">
                <svg
                  aria-hidden="true"
                  fill="none"
                  height="22"
                  stroke="currentColor"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth="2"
                  viewBox="0 0 24 24"
                  width="22"
                >
                  <path d="m8.2 13.3 5.8-5.8a3.2 3.2 0 0 1 4.5 4.5l-7.4 7.4a5 5 0 0 1-7.1-7.1l7.7-7.7" />
                </svg>
              </button>
              <button className="mode-button" type="button">
                <svg
                  aria-hidden="true"
                  fill="none"
                  height="22"
                  stroke="currentColor"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth="2"
                  viewBox="0 0 24 24"
                  width="22"
                >
                  <path d="M12 3.5v17" />
                  <path d="M3.5 12h17" />
                  <path d="m6 6 12 12" />
                  <path d="M18 6 6 18" />
                </svg>
                Standard
              </button>
            </div>
            <div className="composer-actions">
              <span className="backend-chip">
                <span className={health ? "status-dot online" : "status-dot"} />
                {backendStatus}
              </span>
              <button
                className="submit-button"
                disabled={projectQuestion.trim().length === 0}
                type="submit"
                aria-label="Go"
              >
                <svg
                  aria-hidden="true"
                  fill="none"
                  height="22"
                  stroke="currentColor"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth="2"
                  viewBox="0 0 24 24"
                  width="22"
                >
                  <path d="M12 19V5" />
                  <path d="m6.5 10.5 5.5-5.5 5.5 5.5" />
                </svg>
              </button>
            </div>
          </div>
        </form>
      </section>

      <section className="capabilities-section" aria-labelledby="capabilities-title">
        <h2 className="features-heading" id="capabilities-title">
          Features
        </h2>
        <div className="category-tabs" role="tablist" aria-label="Capability categories">
          {landingCategories.map((category) => (
            <button
              aria-selected={landingCategory === category.id}
              className={landingCategory === category.id ? "active" : undefined}
              key={category.id}
              onClick={() => setLandingCategory(category.id)}
              role="tab"
              type="button"
            >
              {category.label}
            </button>
          ))}
        </div>

        <div className="landing-actions-grid">
          {visibleLandingActions.map((action) => (
            <button
              className="landing-action-card"
              key={`${action.category}-${action.title}`}
              onClick={() => setProjectQuestion(action.prompt)}
              type="button"
            >
              <span className="landing-action-icon-wrap">
                <LandingActionIcon icon={action.icon} />
              </span>
              <strong>{action.title}</strong>
              <span>{action.description}</span>
              <LandingActionPreview icon={action.icon} />
            </button>
          ))}
        </div>
      </section>
    </main>
  );
}

type SidebarProps = {
  backendStatus: string;
  isOpen: boolean;
  parameters: SidebarParameters;
  scenarioPrompt: string;
  onPromptChange: (value: string) => void;
  onParametersChange: (updater: (current: SidebarParameters) => SidebarParameters) => void;
  onReset: () => void;
  onToggle: () => void;
};

function ScenarioSidebar({
  backendStatus,
  isOpen,
  onParametersChange,
  onPromptChange,
  onReset,
  onToggle,
  parameters,
  scenarioPrompt,
}: SidebarProps) {
  return (
    <aside className={`scenario-panel ${isOpen ? "is-open" : "is-collapsed"}`} aria-label="Scenario controls">
      <div className="sidebar-heading">
        <h2>Scenario Controls</h2>
        <button className="reset-button" type="button" onClick={onReset}>
          Reset
        </button>
        <button
          aria-expanded={isOpen}
          aria-label={isOpen ? "Collapse scenario controls" : "Expand scenario controls"}
          className="collapse-button"
          title={isOpen ? "Collapse controls" : "Expand controls"}
          type="button"
          onClick={onToggle}
        >
          <SidebarToggleIcon isOpen={isOpen} />
        </button>
      </div>

      <span className="rail-label" aria-hidden={isOpen}>
        Controls
      </span>

      <div className="sidebar-content" aria-hidden={!isOpen}>
        <label className="field-label" htmlFor="scenario-prompt">
          Scenario prompt
          <textarea
            id="scenario-prompt"
            placeholder="Ask for parcel tradeoffs or describe a diligence scenario."
            value={scenarioPrompt}
            onChange={(event) => onPromptChange(event.target.value)}
            rows={3}
          />
        </label>

        <div className="capacity-control">
          <div className="control-title">
            <span>Capacity (IT Load)</span>
            <strong>{parameters.itLoad} MW</strong>
          </div>
          <input
            aria-label="Capacity in megawatts"
            max="100"
            min="5"
            step="5"
            type="range"
            value={parameters.itLoad}
            onChange={(event) =>
              onParametersChange((current) => ({ ...current, itLoad: Number(event.target.value) }))
            }
          />
          <div className="range-ticks">
            <span>5</span>
            <span>25</span>
            <span>50</span>
            <span>75</span>
            <span>100</span>
          </div>
        </div>

        <div className="segmented-control" aria-label="Cooling Mode">
          <span>Cooling Mode</span>
          <div>
            {(["air", "hybrid", "liquid"] as CoolingMode[]).map((mode) => (
              <button
                className={parameters.coolingMode === mode ? "active" : ""}
                key={mode}
                type="button"
                onClick={() => onParametersChange((current) => ({ ...current, coolingMode: mode }))}
              >
                {coolingLabels[mode]}
              </button>
            ))}
          </div>
        </div>

        <label className="field-label acres-field" htmlFor="minimum-acres">
          Minimum Usable Acres
          <span>
            <input
              id="minimum-acres"
              inputMode="numeric"
              pattern="[0-9]*"
              type="text"
              value={parameters.minAcres}
              onChange={(event) =>
                onParametersChange((current) => ({
                  ...current,
                  minAcres: Number(event.target.value) || 0,
                }))
              }
            />
            <small>acres</small>
          </span>
        </label>

        <label className="switch-row" htmlFor="exclude-floodplain">
          <span>Exclude Floodplain</span>
          <input
            checked={parameters.excludeFloodplain}
            id="exclude-floodplain"
            type="checkbox"
            onChange={(event) =>
              onParametersChange((current) => ({
                ...current,
                excludeFloodplain: event.target.checked,
              }))
            }
          />
        </label>

        <div className="filter-section">
          <h3>Site & Infrastructure Filters</h3>
          <label className="field-label" htmlFor="zoning">
            Zoning
            <select
              id="zoning"
              value={parameters.zoningFit}
              onChange={(event) =>
                onParametersChange((current) => ({
                  ...current,
                  zoningFit: event.target.value as ZoningFilter,
                }))
              }
            >
              <option value="any">All Zoning</option>
              <option value="industrial">Industrial only</option>
              <option value="review">Strong or review</option>
            </select>
          </label>

          <label className="field-label" htmlFor="electric-service">
            Electric Service Area
            <select
              id="electric-service"
              value={parameters.electricService}
              onChange={(event) =>
                onParametersChange((current) => ({
                  ...current,
                  electricService: event.target.value as ServiceFilter,
                }))
              }
            >
              <option value="any">All Providers</option>
              <option value="austin">Austin Energy</option>
              <option value="pedernales">Pedernales EC</option>
              <option value="oncor">Oncor</option>
            </select>
          </label>

          <label className="field-label" htmlFor="water-service">
            Water Service Area
            <select
              id="water-service"
              value={parameters.waterService}
              onChange={(event) =>
                onParametersChange((current) => ({
                  ...current,
                  waterService: event.target.value as ServiceFilter,
                }))
              }
            >
              <option value="any">All Providers</option>
              <option value="austin">Austin Water</option>
              <option value="pedernales">Pedernales EC</option>
              <option value="oncor">Oncor</option>
            </select>
          </label>

          <label className="field-label" htmlFor="road-access">
            Road Access
            <select
              id="road-access"
              value={parameters.roadAccess}
              onChange={(event) =>
                onParametersChange((current) => ({
                  ...current,
                  roadAccess: event.target.value as RoadAccessFilter,
                }))
              }
            >
              <option value="any">Any Access</option>
              <option value="direct">Direct highway</option>
              <option value="arterial">Arterial road</option>
            </select>
          </label>

          <label className="field-label" htmlFor="max-substation">
            Max Distance to Substation
            <select
              id="max-substation"
              value={parameters.maxSubstationDistance}
              onChange={(event) =>
                onParametersChange((current) => ({
                  ...current,
                  maxSubstationDistance: Number(event.target.value),
                }))
              }
            >
              <option value="5">5 miles</option>
              <option value="10">10 miles</option>
              <option value="15">15 miles</option>
              <option value="25">25 miles</option>
            </select>
          </label>
        </div>

        <div className="layers-section">
          <h3>Additional Layers</h3>
          {(
            [
              ["substations", "Electric Substations"],
              ["transmission", "Transmission Lines"],
              ["waterLines", "Major Water Lines"],
              ["floodplain", "Floodplain (100-yr)"],
              ["wetlands", "Wetlands"],
            ] as const
          ).map(([key, label]) => (
            <label className="checkbox-row" htmlFor={`layer-${key}`} key={key}>
              <input
                checked={parameters.layers[key]}
                id={`layer-${key}`}
                type="checkbox"
                onChange={(event) =>
                  onParametersChange((current) => ({
                    ...current,
                    layers: { ...current.layers, [key]: event.target.checked },
                  }))
                }
              />
              {label}
            </label>
          ))}
        </div>

        <button className="run-button" type="button">
          Run Analysis
        </button>
        <p className="scenario-stamp">Scenario last run: 5/16/2025, 10:32 AM</p>
        <p className="backend-stamp">Backend: {backendStatus}</p>
      </div>
    </aside>
  );
}

type ResultsInspectorProps = {
  analysisStatus: string;
  matchingParcels: ParcelCandidate[];
  providerInsights: ProviderInsight[];
  selectedParcel: ParcelCandidate;
  onSelectParcel: (parcelId: string) => void;
};

function ResultsInspector({
  analysisStatus,
  matchingParcels,
  onSelectParcel,
  providerInsights,
  selectedParcel,
}: ResultsInspectorProps) {
  return (
    <aside className="results-inspector" aria-label="Top Candidate Parcels">
      <section className="candidate-table-section">
        <div className="candidate-heading">
          <h2>Top Candidate Parcels</h2>
          <span>{matchingParcels.length} results</span>
        </div>

        <div className="candidate-table" role="table" aria-label="Parcel results sorted by score">
          <div className="candidate-row table-head" role="row">
            <span>Score</span>
            <span>Parcel</span>
            <span>Acres</span>
            <span>First Blocker</span>
          </div>
          {matchingParcels.map((parcel) => (
            <button
              className={`candidate-row ${parcel.id === selectedParcel.id ? "selected" : ""}`}
              key={parcel.id}
              role="row"
              type="button"
              onClick={() => onSelectParcel(parcel.id)}
            >
              <span className={`score-chip ${scoreTone(parcel.score)}`}>{parcel.score}</span>
              <span>{parcel.name}</span>
              <span>{parcel.acres}</span>
              <span>{parcel.firstBlocker}</span>
            </button>
          ))}
        </div>
      </section>

      <section className="parcel-detail">
        <div className="detail-header">
          <h2>{selectedParcel.name}</h2>
          <span className={`detail-score ${scoreTone(selectedParcel.score)}`}>{selectedParcel.score}</span>
          <span className="suitability-pill">
            {selectedParcel.score >= 80 ? "High Suitability" : "Needs Review"}
          </span>
        </div>

        <div className="detail-tabs">
          <button className="active" type="button">
            Overview
          </button>
          <button type="button">Infrastructure</button>
          <button type="button">Zoning & Constraints</button>
          <button type="button">Notes</button>
        </div>

        <div className="overview-grid">
          <div className="parcel-thumbnail" aria-hidden="true">
            <div className="thumbnail-parcel" />
          </div>
          <dl className="detail-facts">
            <div>
              <dt>Usable Acres</dt>
              <dd>{selectedParcel.acres}</dd>
            </div>
            <div>
              <dt>Road Access</dt>
              <dd>{selectedParcel.roadAccess}</dd>
            </div>
            <div>
              <dt>Zoning</dt>
              <dd>{selectedParcel.zoning}</dd>
            </div>
            <div>
              <dt>Electric Service Area</dt>
              <dd>{selectedParcel.electricService}</dd>
            </div>
            <div>
              <dt>Floodplain</dt>
              <dd>{selectedParcel.floodplain ? "Review" : "No"}</dd>
            </div>
            <div>
              <dt>Water Service Area</dt>
              <dd>{selectedParcel.waterService}</dd>
            </div>
            <div>
              <dt>Wetlands</dt>
              <dd>{selectedParcel.wetlands ? "Review" : "No"}</dd>
            </div>
            <div>
              <dt>Distance to Substation</dt>
              <dd>{selectedParcel.distanceToSubstation} miles</dd>
            </div>
          </dl>
        </div>

        <div className="first-blocker-card">
          <strong>First Blocker</strong>
          <div>
            <span className="blocker-icon">!</span>
            <div>
              <b>{selectedParcel.firstBlocker}</b>
              <p>Nearest public grid or utility proxy needs a diligence call before site control.</p>
            </div>
          </div>
          <button type="button">View Infrastructure</button>
        </div>

        <div className="provider-insights">
          <div className="provider-insights-heading">
            <h3>Open Data Provider Signals</h3>
            <span>{analysisStatus === "complete" ? "Updated by FastAPI background run" : "Updating..."}</span>
          </div>
          {providerInsights.length > 0 ? (
            <div className="provider-insight-list">
              {providerInsights.slice(0, 5).map((insight) => (
                <article className="provider-insight-card" key={insight.provider_id}>
                  <div>
                    <strong>{insight.provider_name}</strong>
                    <span>{insight.concern.replaceAll("_", " ")}</span>
                  </div>
                  <p>{insight.summary}</p>
                  <small>{insight.queryable ? "Queryable through backend API" : "Metadata-only source"}</small>
                </article>
              ))}
            </div>
          ) : (
            <p className="provider-insights-empty">
              Provider context is being collected through the backend provider layer.
            </p>
          )}
        </div>

        <div className="score-breakdown">
          <h3>Suitability Score Breakdown</h3>
          <div className="score-bars">
            {Object.entries(selectedParcel.scoreBreakdown).map(([label, value]) => (
              <div className="score-bar-card" key={label}>
                <span>{label}</span>
                <strong>
                  {value} / {label === "market" ? 15 : 25}
                </strong>
                <div>
                  <i style={{ width: `${Math.min(100, (value / (label === "market" ? 15 : 25)) * 100)}%` }} />
                </div>
              </div>
            ))}
            <div className="total-score-card">
              <span>Total</span>
              <strong>{selectedParcel.score} / 100</strong>
            </div>
          </div>
        </div>
      </section>
    </aside>
  );
}

export default App;
