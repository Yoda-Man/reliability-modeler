/** Response shapes of the FastAPI backend (web/api/main.py), as seen through /api/*. */

/** One categorized failure: [ISO timestamp, hours since t0, "Cat1, Cat2", description]. */
export type CategorizedFailure = [string, number, string, string];

export interface GraphReport {
    keystone_categories: Array<{ name: string; pagerank: number; is_bridge: boolean }>;
    top_cascade: { chain: string; confidence: number } | null;
    num_communities: number;
    graph_density: number;
    graph_json?: {
        nodes: Array<{ id: string; pagerank: number; degree: number; community: number }>;
        edges: Array<{ source: string; target: string; weight: number; jaccard: number }>;
        cascade_edges: Array<{ source: string; target: string; weight: number; confidence: number; avg_latency: number }>;
    };
}

export interface ModelResult {
    id: string;
    name: string;
    aic: number;
    total_expected_failures: number | null;
    parameters: Record<string, number>;
}

/** POST /ingest/sentry. `id` is `AN-YYYYMMDD-HHMMSS-xxxxxx` (older archives omit the suffix). */
export interface AnalysisResults {
    id: string;
    summary: {
        total_failures: number;
        duration_hours: number;
        start_time: string;
    };
    /** Empty when no model could be fitted to the data. */
    models: ModelResult[];
    plots: Record<string, string>;
    /** The most recent (up to 100) categorized events, oldest first. */
    categorized_failures: CategorizedFailure[];
    /** Total number of categorized events (may exceed categorized_failures.length). */
    categorized_total?: number;
    /** Forecast horizon (hours) the result was computed with. */
    future_hours?: number;
    /** True when a Sentry project hit the event cap and the timeline was trimmed to a common start. */
    truncated?: boolean;
    graph_insights?: string[];
    graph_report?: GraphReport | null;
    projects?: Record<string, number>;
}

export interface LogEntry {
    id: string;
    date: string;
    file: string;
    status: string;
    summary: {
        total_failures: number;
        duration_hours: number;
    };
}

/** GET /logs */
export interface LogsResponse {
    total: number;
    logs: LogEntry[];
}

export interface TrendRun {
    id: string;
    date: string;
    file: string;
    total_failures: number;
    duration_hours: number;
    mtbf_hours: number;
    failure_rate_per_hour: number;
}

export type TrendDirection = 'improving' | 'degrading' | 'stable' | 'insufficient_data' | 'single_run';

/** Trend of the runs for one source (`file`). */
export interface TrendGroup {
    file: string;
    runs: TrendRun[];
    trend: TrendDirection;
    mtbf_change_pct?: number;
    rate_change_pct?: number;
    num_runs: number;
}

/**
 * GET /trends. Summary fields are only present once there are >= 2 runs.
 * Top-level trend fields describe the group of the most recent run; `runs` holds
 * every run. `groups` (per source) is absent from older API versions.
 */
export interface TrendsResponse {
    runs: TrendRun[];
    trend: TrendDirection;
    mtbf_change_pct?: number;
    rate_change_pct?: number;
    num_runs?: number;
    groups?: TrendGroup[];
}

export interface EngineSettings {
    multi_label: boolean;
    optimization_method: string;
    tolerance: number;
}

/** GET /config (POST /config accepts the same shape). */
export interface ConfigResponse {
    content: string;
    settings: EngineSettings;
}

/** GET /health */
export interface HealthResponse {
    status: 'ok' | 'degraded' | 'error';
    version: string;
    timestamp: string;
    checks?: {
        output_writable: boolean;
        config_readable: boolean;
        sentry_token_configured: boolean;
    };
}
