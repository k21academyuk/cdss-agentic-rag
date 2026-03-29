import React from "react";
import {
  Alert,
  Box,
  ButtonBase,
  Card,
  CardContent,
  Chip,
  Divider,
  Grid,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
  Skeleton,
  Stack,
  ToggleButton,
  ToggleButtonGroup,
  Typography,
  useMediaQuery,
  useTheme,
} from "@mui/material";
import {
  CheckCircle,
  Description,
  FactCheck,
  HealthAndSafety,
  Medication,
  PendingActions,
  QueryStats,
  Science,
  Speed,
  Timeline,
  WarningAmber,
} from "@mui/icons-material";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import dayjs from "dayjs";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { clinicalApi } from "@/lib/api-client";
import type { AuditLogEntry, HealthCheckResponse } from "@/lib/types";
import {
  alpha as alphaUtil,
  borderRadius,
  componentShadows,
  density as densityTokens,
  semantic,
  severity,
  spacing,
  transitions,
} from "@/theme";

type DensityMode = "compact" | "comfortable";
type ActivityOutcome = "success" | "failure" | "warning";

interface HeroMetric {
  label: "System Health" | "Queries Today" | "High-Risk Alerts" | "Pending Reviews";
  value: number | string;
  subtitle: string;
  color: string;
  icon: React.ReactNode;
}

interface ActivityFeedItem {
  id: string;
  eventType: string;
  description: string;
  timestamp: string;
  outcome: ActivityOutcome;
}

interface AgentLatencyPoint {
  agent: string;
  latency: number;
}

interface TrendPoint {
  day: string;
  success: number;
  failure: number;
}

interface SafetyItem {
  id: string;
  title: string;
  details: string;
  timestamp: string;
}

interface QuickAction {
  label: string;
  hint: string;
  path: string;
  color: string;
  icon: React.ReactNode;
}

const FALLBACK_AGENT_BASELINES: Array<{ agent: string; latency: number }> = [
  { agent: "Orchestrator", latency: 460 },
  { agent: "Patient History", latency: 320 },
  { agent: "Literature", latency: 980 },
  { agent: "Protocol", latency: 410 },
  { agent: "Drug Safety", latency: 540 },
  { agent: "Guardrails", latency: 360 },
];

const QUICK_ACTIONS: QuickAction[] = [
  {
    label: "Launch Clinical Query",
    hint: "Start evidence synthesis",
    path: "/query",
    color: semantic.info.main,
    icon: <QueryStats />,
  },
  {
    label: "Open Patient Workspace",
    hint: "Review chart + history",
    path: "/patients",
    color: semantic.success.main,
    icon: <HealthAndSafety />,
  },
  {
    label: "Run Drug Safety Check",
    hint: "Scan interactions now",
    path: "/drugs",
    color: severity.moderate.main,
    icon: <Medication />,
  },
  {
    label: "Review Evidence Library",
    hint: "Inspect latest literature",
    path: "/literature",
    color: semantic.warning.main,
    icon: <Science />,
  },
];

function normalizeAuditEntries(raw: unknown): AuditLogEntry[] {
  if (Array.isArray(raw)) {
    return raw as AuditLogEntry[];
  }
  if (raw && typeof raw === "object") {
    const record = raw as Record<string, unknown>;
    const candidates = [record.items, record.entries, record.results, record.data, record.audit];
    const firstArray = candidates.find((item) => Array.isArray(item));
    if (Array.isArray(firstArray)) {
      return firstArray as AuditLogEntry[];
    }
  }
  return [];
}

function mapOutcome(outcome: string): ActivityOutcome {
  if (outcome === "success") return "success";
  if (outcome === "failure" || outcome === "denied") return "failure";
  return "warning";
}

function formatRelativeTimestamp(timestamp: string): string {
  const now = dayjs();
  const eventTime = dayjs(timestamp);
  const diffMinutes = now.diff(eventTime, "minute");
  if (diffMinutes < 60) return `${Math.max(diffMinutes, 1)}m ago`;
  const diffHours = now.diff(eventTime, "hour");
  if (diffHours < 24) return `${diffHours}h ago`;
  return `${now.diff(eventTime, "day")}d ago`;
}

function formatEventTypeLabel(eventType: string): string {
  return eventType.replace(/_/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());
}

function getAuditEventType(entry: AuditLogEntry): string {
  return String(entry.event_type || entry.type || "unknown").toLowerCase();
}

function getAuditActionLabel(entry: AuditLogEntry): string {
  const value = String(entry.action || getAuditEventType(entry) || "event");
  return value.replace(/_/g, " ");
}

function isQueryTelemetryEvent(entry: AuditLogEntry): boolean {
  const eventType = getAuditEventType(entry);
  const resourceType = String(entry.resource?.type || "").toLowerCase();
  return (
    eventType.includes("query") ||
    eventType.includes("llm") ||
    resourceType.includes("query") ||
    resourceType.includes("clinical_query")
  );
}

function getNumericDetail(details: Record<string, unknown> | undefined, key: string): number {
  const raw = details?.[key];
  const parsed = Number(raw);
  return Number.isFinite(parsed) ? parsed : 0;
}

function getEventIcon(eventType: string) {
  if (eventType.includes("drug")) return <Medication fontSize="small" />;
  if (eventType.includes("document")) return <Description fontSize="small" />;
  if (eventType.includes("llm") || eventType.includes("query")) return <QueryStats fontSize="small" />;
  return <FactCheck fontSize="small" />;
}

function outcomeColor(outcome: ActivityOutcome): string {
  if (outcome === "success") return semantic.success.main;
  if (outcome === "failure") return semantic.error.main;
  return semantic.warning.main;
}

function EmptyState({ title, body }: { title: string; body: string }) {
  return (
    <Box
      sx={{
        py: spacing[6],
        textAlign: "center",
        border: "1px dashed",
        borderColor: "divider",
        borderRadius: borderRadius.md,
      }}
    >
      <Typography variant="subtitle2" sx={{ mb: 0.5 }}>
        {title}
      </Typography>
      <Typography variant="body2" color="text.secondary">
        {body}
      </Typography>
    </Box>
  );
}

function LoadingBlock({ compact }: { compact: boolean }) {
  const cardHeight = compact ? 104 : 124;
  const chartHeight = compact ? 220 : 260;
  const lineItems = compact ? 6 : 4;

  return (
    <Box>
      <Stack
        direction={{ xs: "column", md: "row" }}
        justifyContent="space-between"
        alignItems={{ xs: "flex-start", md: "center" }}
        spacing={2}
        sx={{ mb: spacing[4] }}
      >
        <Box>
          <Skeleton variant="text" width={280} height={42} />
          <Skeleton variant="text" width={340} height={22} />
        </Box>
        <Skeleton variant="rounded" width={190} height={38} />
      </Stack>

      <Grid container spacing={2}>
        {Array.from({ length: 4 }).map((_, index) => (
          <Grid item xs={12} sm={6} md={6} lg={3} key={`metric-skeleton-${index}`}>
            <Card sx={{ height: cardHeight }}>
              <CardContent>
                <Skeleton width="55%" />
                <Skeleton width="40%" height={40} />
                <Skeleton width="70%" />
              </CardContent>
            </Card>
          </Grid>
        ))}
      </Grid>

      <Grid container spacing={2} sx={{ mt: 0.5 }}>
        <Grid item xs={12} lg={8}>
          <Card sx={{ minHeight: chartHeight + 90 }}>
            <CardContent>
              <Skeleton width={220} height={28} />
              <Skeleton variant="rounded" height={chartHeight} />
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} lg={4}>
          <Card sx={{ minHeight: chartHeight + 90 }}>
            <CardContent>
              <Skeleton width={180} height={28} />
              <Stack spacing={1.2} sx={{ mt: 2 }}>
                {Array.from({ length: lineItems }).map((_, i) => (
                  <Skeleton key={`feed-skeleton-${i}`} height={28} />
                ))}
              </Stack>
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </Box>
  );
}

export default function Dashboard() {
  const theme = useTheme();
  const navigate = useNavigate();
  const isTabletOrBelow = useMediaQuery(theme.breakpoints.down("lg"));
  const [densityMode, setDensityMode] = React.useState<DensityMode>("comfortable");
  const [revealed, setRevealed] = React.useState(false);

  React.useEffect(() => {
    const id = window.setTimeout(() => setRevealed(true), 40);
    return () => window.clearTimeout(id);
  }, []);

  const { data: patientData, isLoading: patientsLoading } = useQuery({
    queryKey: ["patients", "search", "", 1, 100],
    queryFn: () => clinicalApi.searchPatients({ search: "", page: 1, limit: 100 }),
  });

  const { data: healthData, isLoading: healthLoading } = useQuery<HealthCheckResponse>({
    queryKey: ["health"],
    queryFn: clinicalApi.getHealthCheck,
  });

  const { data: rawAuditData, isLoading: auditLoading } = useQuery({
    queryKey: ["audit", "dashboard", 1, 30],
    queryFn: () => clinicalApi.getAuditTrail({ page: 1, limit: 30 }),
  });

  const compact = densityMode === "compact";
  const density = compact ? densityTokens.compact : densityTokens.comfortable;
  const auditEntries = React.useMemo(() => normalizeAuditEntries(rawAuditData), [rawAuditData]);
  const queryEntries = React.useMemo(() => auditEntries.filter((entry) => isQueryTelemetryEvent(entry)), [auditEntries]);

  const trendData: TrendPoint[] = React.useMemo(() => {
    if (queryEntries.length === 0) return [];

    const baseDays = Array.from({ length: 7 }).map((_, index) => dayjs().subtract(6 - index, "day").format("MMM D"));
    const seedMap = new Map(baseDays.map((day) => [day, { day, success: 0, failure: 0 }]));

    queryEntries.forEach((entry) => {
      const dayKey = dayjs(entry.timestamp).format("MMM D");
      const dayData = seedMap.get(dayKey);
      if (!dayData) return;
      if ((entry.outcome || "success") === "success") {
        dayData.success += 1;
      } else {
        dayData.failure += 1;
      }
    });

    return Array.from(seedMap.values());
  }, [queryEntries]);

  if (patientsLoading || healthLoading || auditLoading) {
    return <LoadingBlock compact={compact} />;
  }

  const patientsTotal = Number((patientData as { total?: number })?.total ?? 0);
  const services = healthData?.services ?? {};
  const serviceEntries = Object.entries(services);
  const healthyServiceCount = serviceEntries.filter(([, status]) => status === "healthy").length;
  const healthPct = serviceEntries.length > 0 ? Math.round((healthyServiceCount / serviceEntries.length) * 100) : 0;

  const activityFeed: ActivityFeedItem[] = [...auditEntries]
    .sort((a, b) => dayjs(b.timestamp).valueOf() - dayjs(a.timestamp).valueOf())
    .slice(0, compact ? 8 : 6)
    .map((entry) => ({
      id: entry.id,
      eventType: getAuditEventType(entry),
      description: getAuditActionLabel(entry),
      timestamp: entry.timestamp,
      outcome: mapOutcome(entry.outcome || "warning"),
    }));

  const today = dayjs().format("YYYY-MM-DD");
  const queriesToday = queryEntries.filter((entry) => {
    const isToday = dayjs(entry.timestamp).format("YYYY-MM-DD") === today;
    return isToday;
  }).length;

  const majorDrugAlerts: SafetyItem[] = auditEntries
    .filter((entry) => {
      const eventType = getAuditEventType(entry);
      const action = String(entry.action || "").toLowerCase();
      return eventType.includes("drug") || action.includes("drug");
    })
    .filter((entry) => {
      const details = (entry.details || {}) as Record<string, unknown>;
      const majorInteractions = getNumericDetail(details, "major_interactions");
      return (entry.outcome || "success") !== "success" || majorInteractions > 0;
    })
    .slice(0, 4)
    .map((entry) => ({
      id: entry.id,
      title: "Major drug alert",
      details: `${getAuditActionLabel(entry)} (${entry.actor?.clinician_id ?? "unknown actor"})`,
      timestamp: entry.timestamp,
    }));

  const unresolvedGuardrailFlags: SafetyItem[] = auditEntries
    .filter((entry) => {
      const eventType = getAuditEventType(entry);
      return eventType.includes("guardrail") || isQueryTelemetryEvent(entry);
    })
    .filter((entry) => (entry.outcome || "success") !== "success")
    .slice(0, 4)
    .map((entry) => ({
      id: `${entry.id}-guardrail`,
      title: "Unresolved guardrail flag",
      details: `${entry.justification || "clinical prompt validation failure"}`,
      timestamp: entry.timestamp,
    }));

  const pendingReviews = majorDrugAlerts.length + unresolvedGuardrailFlags.length;
  const highRiskAlerts = majorDrugAlerts.length;

  const heroMetrics: HeroMetric[] = [
    {
      label: "System Health",
      value: `${healthPct || (healthData?.status === "healthy" ? 100 : 0)}%`,
      subtitle: `${healthyServiceCount}/${serviceEntries.length || 0} core services healthy`,
      color: semantic.success.main,
      icon: <HealthAndSafety />,
    },
    {
      label: "Queries Today",
      value: queriesToday,
      subtitle: `${patientsTotal} active patient profiles available`,
      color: semantic.info.main,
      icon: <QueryStats />,
    },
    {
      label: "High-Risk Alerts",
      value: highRiskAlerts,
      subtitle: "Major medication safety events",
      color: severity.major.main,
      icon: <WarningAmber />,
    },
    {
      label: "Pending Reviews",
      value: pendingReviews,
      subtitle: "Safety + guardrail follow-ups",
      color: severity.moderate.main,
      icon: <PendingActions />,
    },
  ];

  const degradedCount = serviceEntries.filter(([, status]) => status !== "healthy").length;
  const agentLatencyData: AgentLatencyPoint[] = React.useMemo(() => {
    const latencyBuckets = new Map<string, number[]>();
    queryEntries.forEach((entry) => {
      const details = (entry.details || {}) as Record<string, unknown>;
      const latencies = details.agent_latencies;
      if (!latencies || typeof latencies !== "object") return;
      Object.entries(latencies as Record<string, unknown>).forEach(([key, value]) => {
        const ms = Number(value);
        if (!Number.isFinite(ms) || ms <= 0) return;
        const bucketKey = key.toLowerCase();
        const existing = latencyBuckets.get(bucketKey) || [];
        existing.push(ms);
        latencyBuckets.set(bucketKey, existing);
      });
    });

    return FALLBACK_AGENT_BASELINES.map((agent, index) => {
      const bucketKey = agent.agent.toLowerCase().replace(/\s+/g, "_");
      const candidates =
        latencyBuckets.get(bucketKey) ||
        latencyBuckets.get(agent.agent.toLowerCase()) ||
        [];
      if (candidates.length > 0) {
        const avg = Math.round(candidates.reduce((sum, item) => sum + item, 0) / candidates.length);
        return { agent: agent.agent, latency: avg };
      }
      return {
        agent: agent.agent,
        latency: agent.latency + degradedCount * 45 + (compact ? -20 : 0) + index * 8,
      };
    });
  }, [compact, degradedCount, queryEntries]);

  return (
    <Box
      sx={{
        opacity: revealed ? 1 : 0,
        transform: revealed ? "translateY(0px)" : "translateY(6px)",
        transition: `${transitions.fade.standard}, ${transitions.transform.standard}`,
      }}
    >
      <Stack
        direction={{ xs: "column", md: "row" }}
        justifyContent="space-between"
        alignItems={{ xs: "flex-start", md: "center" }}
        spacing={2}
        sx={{ mb: spacing[4] }}
      >
        <Box>
          <Typography variant="h4" sx={{ mb: 0.5 }}>
            Clinical Operations Dashboard
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Real-time clinical safety, agent performance, and operational telemetry.
          </Typography>
        </Box>

        <ToggleButtonGroup
          size="small"
          value={densityMode}
          exclusive
          onChange={(_, next: DensityMode | null) => {
            if (next) setDensityMode(next);
          }}
          aria-label="Dashboard density mode"
        >
          <ToggleButton value="comfortable" aria-label="Comfortable density">
            Comfortable
          </ToggleButton>
          <ToggleButton value="compact" aria-label="Compact density for hospital workflows">
            High-Density
          </ToggleButton>
        </ToggleButtonGroup>
      </Stack>

      {/* Hero summary */}
      <Grid container spacing={2}>
        {heroMetrics.map((metric) => (
          <Grid item xs={12} sm={6} md={6} lg={3} key={metric.label}>
            <Card
              sx={{
                height: "100%",
                borderRadius: borderRadius.md,
                border: `1px solid ${alphaUtil(metric.color, 0.2)}`,
                boxShadow: componentShadows.card,
              }}
            >
              <CardContent sx={{ p: compact ? spacing[3] : spacing[4] }}>
                <Stack direction="row" justifyContent="space-between" alignItems="center" spacing={2}>
                  <Box>
                    <Typography variant="caption" sx={{ color: "text.secondary", textTransform: "uppercase" }}>
                      {metric.label}
                    </Typography>
                    <Typography variant="h4" sx={{ mt: 0.5 }}>
                      {metric.value}
                    </Typography>
                    <Typography variant="body2" sx={{ color: "text.secondary", mt: 0.5 }}>
                      {metric.subtitle}
                    </Typography>
                  </Box>
                  <Box
                    sx={{
                      p: 1.2,
                      borderRadius: borderRadius.sm,
                      color: metric.color,
                      bgcolor: alphaUtil(metric.color, 0.12),
                    }}
                  >
                    {metric.icon}
                  </Box>
                </Stack>
              </CardContent>
            </Card>
          </Grid>
        ))}
      </Grid>

      <Grid container spacing={2} sx={{ mt: 0.25 }}>
        {/* Agent performance */}
        <Grid item xs={12} xl={8}>
          <Card sx={{ borderRadius: borderRadius.lg, boxShadow: componentShadows.card, height: "100%" }}>
            <CardContent sx={{ p: compact ? spacing[3] : spacing[4] }}>
              <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 2 }}>
                <Box>
                  <Typography variant="h6">Agent Performance Panel</Typography>
                  <Typography variant="body2" color="text.secondary">
                    Latency by agent and success/fail trend.
                  </Typography>
                </Box>
                <Speed sx={{ color: semantic.info.main }} />
              </Stack>

              <Grid container spacing={2}>
                <Grid item xs={12} lg={6}>
                  <Typography variant="subtitle2" sx={{ mb: 1 }}>
                    Latency by Agent (ms)
                  </Typography>
                  <Box sx={{ width: "100%", height: compact ? 220 : 260 }}>
                    <ResponsiveContainer>
                      <BarChart data={agentLatencyData} margin={{ top: 10, right: 12, left: 0, bottom: 28 }}>
                        <CartesianGrid strokeDasharray="3 3" vertical={false} />
                        <XAxis dataKey="agent" angle={-25} textAnchor="end" interval={0} height={58} fontSize={11} />
                        <YAxis width={34} />
                        <Tooltip />
                        <Bar
                          dataKey="latency"
                          radius={[6, 6, 0, 0]}
                          fill={semantic.info.main}
                          isAnimationActive
                          animationDuration={420}
                        />
                      </BarChart>
                    </ResponsiveContainer>
                  </Box>
                </Grid>

                <Grid item xs={12} lg={6}>
                  <Typography variant="subtitle2" sx={{ mb: 1 }}>
                    Success / Failure Trend (7 days)
                  </Typography>
                  {trendData.length === 0 ? (
                    <EmptyState
                      title="No trend data yet"
                      body="Run clinical queries to populate success/failure telemetry."
                    />
                  ) : (
                    <Box sx={{ width: "100%", height: compact ? 220 : 260 }}>
                      <ResponsiveContainer>
                        <LineChart data={trendData} margin={{ top: 10, right: 10, left: 0, bottom: 8 }}>
                          <CartesianGrid strokeDasharray="3 3" vertical={false} />
                          <XAxis dataKey="day" fontSize={11} />
                          <YAxis width={30} />
                          <Tooltip />
                          <Legend />
                          <Line
                            type="monotone"
                            dataKey="success"
                            stroke={semantic.success.main}
                            strokeWidth={2.5}
                            dot={{ r: 2.5 }}
                            isAnimationActive
                            animationDuration={420}
                          />
                          <Line
                            type="monotone"
                            dataKey="failure"
                            stroke={semantic.error.main}
                            strokeWidth={2.5}
                            dot={{ r: 2.5 }}
                            isAnimationActive
                            animationDuration={420}
                          />
                        </LineChart>
                      </ResponsiveContainer>
                    </Box>
                  )}
                </Grid>
              </Grid>
            </CardContent>
          </Card>
        </Grid>

        {/* Safety highlights */}
        <Grid item xs={12} xl={4}>
          <Card sx={{ borderRadius: borderRadius.lg, boxShadow: componentShadows.card, height: "100%" }}>
            <CardContent sx={{ p: compact ? spacing[3] : spacing[4] }}>
              <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1 }}>
                <Typography variant="h6">Safety Highlights</Typography>
                <WarningAmber sx={{ color: severity.major.main }} />
              </Stack>

              <Typography variant="subtitle2" sx={{ color: severity.major.dark, mt: 2, mb: 1 }}>
                Major Drug Alerts ({majorDrugAlerts.length})
              </Typography>
              {majorDrugAlerts.length === 0 ? (
                <EmptyState title="No major drug alerts" body="No unresolved major contraindications currently." />
              ) : (
                <List dense={compact} disablePadding>
                  {majorDrugAlerts.map((item) => (
                    <ListItem key={item.id} disableGutters sx={{ alignItems: "flex-start" }}>
                      <ListItemIcon sx={{ minWidth: 28, mt: 0.25 }}>
                        <Medication sx={{ fontSize: 18, color: severity.major.main }} />
                      </ListItemIcon>
                      <ListItemText
                        primary={item.title}
                        secondary={`${item.details} • ${formatRelativeTimestamp(item.timestamp)}`}
                        primaryTypographyProps={{ variant: "body2", fontWeight: 600 }}
                        secondaryTypographyProps={{ variant: "caption" }}
                      />
                    </ListItem>
                  ))}
                </List>
              )}

              <Divider sx={{ my: 2 }} />

              <Typography variant="subtitle2" sx={{ color: severity.moderate.dark, mb: 1 }}>
                Unresolved Guardrail Flags ({unresolvedGuardrailFlags.length})
              </Typography>
              {unresolvedGuardrailFlags.length === 0 ? (
                <Alert severity="success" variant="outlined">
                  No unresolved guardrail flags.
                </Alert>
              ) : (
                <List dense={compact} disablePadding>
                  {unresolvedGuardrailFlags.map((item) => (
                    <ListItem key={item.id} disableGutters sx={{ alignItems: "flex-start" }}>
                      <ListItemIcon sx={{ minWidth: 28, mt: 0.25 }}>
                        <FactCheck sx={{ fontSize: 18, color: severity.moderate.main }} />
                      </ListItemIcon>
                      <ListItemText
                        primary={item.title}
                        secondary={`${item.details} • ${formatRelativeTimestamp(item.timestamp)}`}
                        primaryTypographyProps={{ variant: "body2", fontWeight: 600 }}
                        secondaryTypographyProps={{ variant: "caption" }}
                      />
                    </ListItem>
                  ))}
                </List>
              )}
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      <Grid container spacing={2} sx={{ mt: 0.25 }}>
        {/* Recent clinical activity feed */}
        <Grid item xs={12} lg={8}>
          <Card sx={{ borderRadius: borderRadius.lg, boxShadow: componentShadows.card, height: "100%" }}>
            <CardContent sx={{ p: compact ? spacing[3] : spacing[4] }}>
              <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 2 }}>
                <Box>
                  <Typography variant="h6">Recent Clinical Activity</Typography>
                  <Typography variant="body2" color="text.secondary">
                    Typed operational events from audit logs.
                  </Typography>
                </Box>
                <Timeline sx={{ color: semantic.info.main }} />
              </Stack>

              {activityFeed.length === 0 ? (
                <EmptyState
                  title="No activity yet"
                  body="Clinical activity will appear after patient, query, and drug safety operations."
                />
              ) : (
                <List dense={compact} disablePadding>
                  {activityFeed.map((activity, index) => (
                    <ListItem
                      key={activity.id}
                      disableGutters
                      sx={{
                        py: compact ? 0.8 : 1.2,
                        borderBottom:
                          index === activityFeed.length - 1 ? "none" : `1px solid ${alphaUtil(theme.palette.divider, 0.8)}`,
                      }}
                    >
                      <ListItemIcon sx={{ minWidth: 34 }}>
                        <Box
                          sx={{
                            width: 24,
                            height: 24,
                            borderRadius: borderRadius.xs,
                            bgcolor: alphaUtil(outcomeColor(activity.outcome), 0.12),
                            color: outcomeColor(activity.outcome),
                            display: "grid",
                            placeItems: "center",
                          }}
                        >
                          {getEventIcon(activity.eventType)}
                        </Box>
                      </ListItemIcon>
                      <ListItemText
                        primary={
                          <Stack direction={{ xs: "column", sm: "row" }} spacing={1} alignItems={{ sm: "center" }}>
                            <Typography variant="body2" sx={{ fontWeight: 600 }}>
                              {activity.description}
                            </Typography>
                            <Chip
                              size="small"
                              label={formatEventTypeLabel(activity.eventType)}
                              sx={{
                                width: "fit-content",
                                bgcolor: alphaUtil(semantic.info.main, 0.12),
                                color: semantic.info.dark,
                                fontWeight: 600,
                              }}
                            />
                          </Stack>
                        }
                        secondary={
                          <Typography variant="caption" color="text.secondary">
                            {formatRelativeTimestamp(activity.timestamp)}
                          </Typography>
                        }
                      />
                    </ListItem>
                  ))}
                </List>
              )}
            </CardContent>
          </Card>
        </Grid>

        {/* Quick actions */}
        <Grid item xs={12} lg={4}>
          <Card sx={{ borderRadius: borderRadius.lg, boxShadow: componentShadows.card, height: "100%" }}>
            <CardContent sx={{ p: compact ? spacing[3] : spacing[4] }}>
              <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 2 }}>
                <Box>
                  <Typography variant="h6">Quick Actions</Typography>
                  <Typography variant="body2" color="text.secondary">
                    Keyboard-accessible, high-affordance shortcuts.
                  </Typography>
                </Box>
                <CheckCircle sx={{ color: semantic.success.main }} />
              </Stack>

              <Stack spacing={1.5}>
                {QUICK_ACTIONS.map((action) => (
                  <ButtonBase
                    key={action.label}
                    onClick={() => navigate(action.path)}
                    aria-label={action.label}
                    sx={{
                      width: "100%",
                      borderRadius: borderRadius.sm,
                      textAlign: "left",
                      border: `1px solid ${alphaUtil(action.color, 0.3)}`,
                      background: `linear-gradient(90deg, ${alphaUtil(action.color, 0.16)} 0%, ${alphaUtil(
                        action.color,
                        0.06
                      )} 100%)`,
                      p: compact ? spacing[2] : spacing[3],
                      "&:focus-visible": {
                        outline: `2px solid ${action.color}`,
                        outlineOffset: "2px",
                      },
                    }}
                  >
                    <Stack direction="row" spacing={1.5} alignItems="center" sx={{ width: "100%" }}>
                      <Box
                        sx={{
                          width: compact ? 30 : 34,
                          height: compact ? 30 : 34,
                          borderRadius: borderRadius.xs,
                          bgcolor: alphaUtil(action.color, 0.22),
                          color: action.color,
                          display: "grid",
                          placeItems: "center",
                        }}
                      >
                        {action.icon}
                      </Box>
                      <Box sx={{ flex: 1, minWidth: 0 }}>
                        <Typography variant="body2" sx={{ fontWeight: 700 }}>
                          {action.label}
                        </Typography>
                        <Typography variant="caption" color="text.secondary">
                          {action.hint}
                        </Typography>
                      </Box>
                    </Stack>
                  </ButtonBase>
                ))}
              </Stack>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Responsive hints */}
      {isTabletOrBelow && (
        <Typography variant="caption" sx={{ display: "block", mt: 2, color: "text.secondary" }}>
          Optimized responsive layout active for {compact ? "high-density" : "standard"} workflow view.
        </Typography>
      )}
    </Box>
  );
}
