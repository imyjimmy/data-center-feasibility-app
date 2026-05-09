# Design

This document captures the current top-level component design for later updates.

```mermaid
flowchart LR
    frontend[Frontend]
    backend[Backend]
    openclaw[OpenClaw]

    subgraph mcps[FastMCP MCP Servers]
        mcpResearch[Research MCPs]
        mcpQuery[Query MCPs]
        mcpData[Data MCPs]
    end

    frontend -->|API requests| backend
    backend -->|tasks, context, orchestration| openclaw
    openclaw -->|data updates| backend
    openclaw -->|query and research| mcps
    mcps -->|results and evidence| openclaw
```

## Component Roles

- `Frontend`: user-facing application that interacts with the backend.
- `Backend`: application API and data owner. It serves the frontend, invokes OpenClaw, and accepts data updates from OpenClaw.
- `OpenClaw`: research and orchestration layer. It can update backend data and use FastMCP-based MCP servers for query and research workflows.
- `FastMCP MCP Servers`: specialized tools exposed through FastMCP for external data lookup, research, and related task-specific capabilities.
