import React from "react";
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Grid,
  MenuItem,
  Stack,
  Switch,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from "@mui/material";
import { Download, FilterAlt, Refresh } from "@mui/icons-material";
import { useQuery } from "@tanstack/react-query";
import dayjs from "dayjs";
import { PageContainer, PageHeader } from "@/components/ui";
import { clinicalApi } from "@/lib/api-client";
import type { AuditLogEntry } from "@/lib/types";
import { alpha as alphaUtil, borderRadius, componentShadows, semantic, severity, spacing } from "@/theme";

interface FilterState {
  start_date: string;
  end_date: string;
  event_type: string;
  actor_id: string;
  outcome: string;
  phi_only: boolean;
  failures_only: boolean;
}

const DEFAULT_FILTERS: FilterState = {
  start_date: "",
  end_date: "",
  event_type: "",
  actor_id: "",
  outcome: "",
  phi_only: false,
  failures_only: false,
};

function normalizeAuditEntries(raw: unknown): AuditLogEntry[] {
  if (Array.isArray(raw)) return raw as AuditLogEntry[];
  if (!raw || typeof raw !== "object") return [];
  const record = raw as Record<string, unknown>;
  const candidates = [record.items, record.entries, record.results, record.data, record.audit];
  const firstArray = candidates.find((item) => Array.isArray(item));
  return Array.isArray(firstArray) ? (firstArray as AuditLogEntry[]) : [];
}

function csvEscape(value: string): string {
  const escaped = value.replace(/"/g, '""');
  return `"${escaped}"`;
}

function exportTextFile(filename: string, content: string, mime: string): void {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

function outcomeColor(outcome: string): "success" | "error" | "warning" | "default" {
  if (outcome === "success") return "success";
  if (outcome === "failure") return "error";
  if (outcome === "denied") return "warning";
  return "default";
}

export default function AdminPage() {
  const [draftFilters, setDraftFilters] = React.useState<FilterState>(DEFAULT_FILTERS);
  const [activeFilters, setActiveFilters] = React.useState<FilterState>(DEFAULT_FILTERS);
  const [compactMode, setCompactMode] = React.useState(true);

  const queryParams = React.useMemo(
    () => ({
      start_date: activeFilters.start_date || undefined,
      end_date: activeFilters.end_date || undefined,
      event_type: activeFilters.event_type || undefined,
      actor_id: activeFilters.actor_id || undefined,
      limit: 200,
      page: 1,
    }),
    [activeFilters]
  );

  const auditQuery = useQuery({
    queryKey: ["audit", queryParams],
    queryFn: () => clinicalApi.getAuditTrail(queryParams),
  });

  const entries = React.useMemo(() => normalizeAuditEntries(auditQuery.data), [auditQuery.data]);

  const filteredEntries = React.useMemo(() => {
    return entries
      .filter((entry) => {
        if (activeFilters.outcome && entry.outcome !== activeFilters.outcome) return false;
        if (activeFilters.phi_only && !entry.data_sent_to_llm) return false;
        if (activeFilters.failures_only && entry.outcome === "success") return false;
        return true;
      })
      .slice(0, 150);
  }, [entries, activeFilters]);

  const deniedCount = filteredEntries.filter((entry) => entry.outcome === "denied").length;
  const failureCount = filteredEntries.filter((entry) => entry.outcome === "failure").length;
  const phiSentCount = filteredEntries.filter((entry) => entry.data_sent_to_llm).length;

  const applyFilters = () => setActiveFilters(draftFilters);
  const resetFilters = () => {
    setDraftFilters(DEFAULT_FILTERS);
    setActiveFilters(DEFAULT_FILTERS);
  };

  const exportCsv = () => {
    const headers = ["timestamp", "event_type", "actor_id", "action", "resource_type", "outcome", "phi_sent"];
    const rows = filteredEntries.map((entry) =>
      [
        entry.timestamp,
        entry.event_type || entry.type || "",
        entry.actor?.clinician_id ?? "",
        entry.action || "",
        entry.resource?.type ?? "",
        entry.outcome || "",
        String(Boolean(entry.data_sent_to_llm)),
      ]
        .map((value) => csvEscape(value))
        .join(",")
    );
    exportTextFile(`audit-export-${dayjs().format("YYYYMMDD-HHmmss")}.csv`, `${headers.join(",")}\n${rows.join("\n")}`, "text/csv");
  };

  const exportJson = () => {
    exportTextFile(
      `audit-export-${dayjs().format("YYYYMMDD-HHmmss")}.json`,
      JSON.stringify(filteredEntries, null, 2),
      "application/json"
    );
  };

  const rowPaddingY = compactMode ? 0.55 : 1.2;

  return (
    <PageContainer>
      <PageHeader
        title="Admin Operations Console"
        subtitle="High-density audit surveillance for PHI handling, denied actions, and failure events."
      />

      <Grid container spacing={2}>
        <Grid item xs={12}>
          <Card sx={{ borderRadius: borderRadius.md, boxShadow: componentShadows.card }}>
            <CardContent sx={{ p: spacing[3] }}>
              <Stack spacing={2}>
                <Stack direction="row" spacing={1} alignItems="center">
                  <FilterAlt />
                  <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
                    Advanced Filters
                  </Typography>
                </Stack>

                <Grid container spacing={1.2}>
                  <Grid item xs={12} md={2}>
                    <TextField
                      fullWidth
                      type="date"
                      label="Start date"
                      value={draftFilters.start_date}
                      onChange={(event) => setDraftFilters((prev) => ({ ...prev, start_date: event.target.value }))}
                      InputLabelProps={{ shrink: true }}
                      size="small"
                    />
                  </Grid>
                  <Grid item xs={12} md={2}>
                    <TextField
                      fullWidth
                      type="date"
                      label="End date"
                      value={draftFilters.end_date}
                      onChange={(event) => setDraftFilters((prev) => ({ ...prev, end_date: event.target.value }))}
                      InputLabelProps={{ shrink: true }}
                      size="small"
                    />
                  </Grid>
                  <Grid item xs={12} md={2}>
                    <TextField
                      fullWidth
                      size="small"
                      label="Event type"
                      value={draftFilters.event_type}
                      onChange={(event) => setDraftFilters((prev) => ({ ...prev, event_type: event.target.value }))}
                      placeholder="llm_interaction"
                    />
                  </Grid>
                  <Grid item xs={12} md={2}>
                    <TextField
                      fullWidth
                      size="small"
                      label="Actor ID"
                      value={draftFilters.actor_id}
                      onChange={(event) => setDraftFilters((prev) => ({ ...prev, actor_id: event.target.value }))}
                      placeholder="clinician_123"
                    />
                  </Grid>
                  <Grid item xs={12} md={2}>
                    <TextField
                      fullWidth
                      select
                      size="small"
                      label="Outcome"
                      value={draftFilters.outcome}
                      onChange={(event) => setDraftFilters((prev) => ({ ...prev, outcome: event.target.value }))}
                    >
                      <MenuItem value="">All</MenuItem>
                      <MenuItem value="success">Success</MenuItem>
                      <MenuItem value="failure">Failure</MenuItem>
                      <MenuItem value="denied">Denied</MenuItem>
                    </TextField>
                  </Grid>
                  <Grid item xs={12} md={2}>
                    <Stack spacing={0.5}>
                      <Stack direction="row" spacing={0.4} alignItems="center">
                        <Switch
                          size="small"
                          checked={draftFilters.phi_only}
                          onChange={(event) => setDraftFilters((prev) => ({ ...prev, phi_only: event.target.checked }))}
                        />
                        <Typography variant="caption">PHI only</Typography>
                      </Stack>
                      <Stack direction="row" spacing={0.4} alignItems="center">
                        <Switch
                          size="small"
                          checked={draftFilters.failures_only}
                          onChange={(event) =>
                            setDraftFilters((prev) => ({ ...prev, failures_only: event.target.checked }))
                          }
                        />
                        <Typography variant="caption">Failures</Typography>
                      </Stack>
                    </Stack>
                  </Grid>
                </Grid>

                <Stack direction={{ xs: "column", sm: "row" }} spacing={1} justifyContent="space-between">
                  <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                    <Chip
                      size="small"
                      label={`${phiSentCount} PHI sent`}
                      sx={{ bgcolor: alphaUtil(severity.moderate.main, 0.15), color: severity.moderate.main }}
                    />
                    <Chip
                      size="small"
                      label={`${deniedCount} denied`}
                      sx={{ bgcolor: alphaUtil(semantic.warning.main, 0.15), color: semantic.warning.main }}
                    />
                    <Chip
                      size="small"
                      label={`${failureCount} failures`}
                      sx={{ bgcolor: alphaUtil(severity.major.main, 0.15), color: severity.major.main }}
                    />
                  </Stack>
                  <Stack direction="row" spacing={1}>
                    <Button variant="outlined" startIcon={<Refresh />} onClick={() => void auditQuery.refetch()}>
                      Refresh
                    </Button>
                    <Button variant="outlined" startIcon={<Download />} onClick={exportCsv} disabled={filteredEntries.length === 0}>
                      Export CSV
                    </Button>
                    <Button variant="outlined" startIcon={<Download />} onClick={exportJson} disabled={filteredEntries.length === 0}>
                      Export JSON
                    </Button>
                    <Button variant="contained" onClick={applyFilters}>
                      Apply
                    </Button>
                    <Button variant="text" color="inherit" onClick={resetFilters}>
                      Reset
                    </Button>
                    <Stack direction="row" spacing={0.4} alignItems="center" sx={{ pl: 0.5 }}>
                      <Switch size="small" checked={compactMode} onChange={(event) => setCompactMode(event.target.checked)} />
                      <Typography variant="caption">High density</Typography>
                    </Stack>
                  </Stack>
                </Stack>
              </Stack>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12}>
          <Card sx={{ borderRadius: borderRadius.md, boxShadow: componentShadows.card }}>
            <CardContent sx={{ p: 0 }}>
              <TableContainer sx={{ maxHeight: "70vh" }}>
                <Table stickyHeader size={compactMode ? "small" : "medium"}>
                  <TableHead>
                    <TableRow>
                      <TableCell>Timestamp</TableCell>
                      <TableCell>Event</TableCell>
                      <TableCell>Actor</TableCell>
                      <TableCell>Action</TableCell>
                      <TableCell>Resource</TableCell>
                      <TableCell>Outcome</TableCell>
                      <TableCell>PHI Sent</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {auditQuery.isLoading && (
                      <TableRow>
                        <TableCell colSpan={7} align="center" sx={{ py: spacing[4] }}>
                          Loading audit log...
                        </TableCell>
                      </TableRow>
                    )}

                    {!auditQuery.isLoading && filteredEntries.length === 0 && (
                      <TableRow>
                        <TableCell colSpan={7} align="center" sx={{ py: spacing[6] }}>
                          <Typography variant="body2" color="text.secondary">
                            No audit records match the current filters.
                          </Typography>
                        </TableCell>
                      </TableRow>
                    )}

                    {filteredEntries.map((entry, index) => {
                      const isFailure = entry.outcome === "failure";
                      const isDenied = entry.outcome === "denied";
                      const isPhiSent = Boolean(entry.data_sent_to_llm);
                      const rowBg = isFailure
                        ? alphaUtil(severity.major.main, 0.06)
                        : isDenied
                        ? alphaUtil(semantic.warning.main, 0.08)
                        : isPhiSent
                        ? alphaUtil(severity.moderate.main, 0.06)
                        : "transparent";

                      return (
                        <TableRow key={`${entry.id || entry.timestamp}-${index}`} hover sx={{ backgroundColor: rowBg }}>
                          <TableCell sx={{ py: rowPaddingY }}>
                            {entry.timestamp ? dayjs(entry.timestamp).format("YYYY-MM-DD HH:mm:ss") : "N/A"}
                          </TableCell>
                          <TableCell sx={{ py: rowPaddingY }}>{entry.event_type || "N/A"}</TableCell>
                          <TableCell sx={{ py: rowPaddingY }}>{entry.actor?.clinician_id || "N/A"}</TableCell>
                          <TableCell sx={{ py: rowPaddingY }}>{entry.action || "N/A"}</TableCell>
                          <TableCell sx={{ py: rowPaddingY }}>{entry.resource?.type || "N/A"}</TableCell>
                          <TableCell sx={{ py: rowPaddingY }}>
                            <Chip
                              size="small"
                              color={outcomeColor(entry.outcome || "unknown")}
                              label={entry.outcome || "unknown"}
                            />
                          </TableCell>
                          <TableCell sx={{ py: rowPaddingY }}>
                            <Chip
                              size="small"
                              label={isPhiSent ? "SENT" : "NOT SENT"}
                              sx={
                                isPhiSent
                                  ? {
                                      bgcolor: alphaUtil(severity.moderate.main, 0.2),
                                      color: severity.moderate.main,
                                      fontWeight: 700,
                                    }
                                  : undefined
                              }
                            />
                          </TableCell>
                        </TableRow>
                      );
                    })}
                  </TableBody>
                </Table>
              </TableContainer>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {auditQuery.isError && (
        <Alert severity="error" sx={{ mt: spacing[2], borderRadius: borderRadius.md }}>
          Failed to load audit trail. Check backend availability and retry.
        </Alert>
      )}
    </PageContainer>
  );
}
