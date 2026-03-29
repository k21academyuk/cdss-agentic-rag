import React from "react";
import {
  Alert,
  Autocomplete,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Divider,
  Grid,
  Skeleton,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from "@mui/material";
import { Error as ErrorIcon, Medication, Search, WarningAmber } from "@mui/icons-material";
import { useMutation } from "@tanstack/react-query";
import InteractionMatrix from "@/components/drugs/InteractionMatrix";
import { PageContainer, PageHeader } from "@/components/ui";
import { clinicalApi } from "@/lib/api-client";
import type { ApiError, DrugInteraction } from "@/lib/types";
import { alpha as alphaUtil, borderRadius, componentShadows, semantic, severity, spacing } from "@/theme";

const COMMON_MEDICATIONS = [
  "Warfarin",
  "Aspirin",
  "Metformin",
  "Atorvastatin",
  "Lisinopril",
  "Clopidogrel",
  "Amiodarone",
  "Digoxin",
  "Insulin",
  "Prednisone",
  "Omeprazole",
  "Ibuprofen",
];

function severityColor(level: DrugInteraction["severity"]): string {
  if (level === "major") return severity.major.main;
  if (level === "moderate") return severity.moderate.main;
  return severity.minor.main;
}

function sortBySeverity(a: DrugInteraction, b: DrugInteraction): number {
  const weight: Record<DrugInteraction["severity"], number> = {
    major: 3,
    moderate: 2,
    minor: 1,
  };
  return weight[b.severity] - weight[a.severity];
}

export default function DrugCheckerPage() {
  const [medications, setMedications] = React.useState<string[]>([]);
  const [inputValue, setInputValue] = React.useState("");

  const checkInteractions = useMutation({
    mutationFn: () => clinicalApi.checkDrugInteractions(medications),
  });

  const interactions = ((checkInteractions.data as { interactions?: DrugInteraction[] } | undefined)?.interactions ?? []).slice();
  interactions.sort(sortBySeverity);

  const majorInteractions = interactions.filter((entry) => entry.severity === "major");
  const moderateInteractions = interactions.filter((entry) => entry.severity === "moderate");
  const minorInteractions = interactions.filter((entry) => entry.severity === "minor");

  const alternatives = (checkInteractions.data as { alternatives?: string[] } | undefined)?.alternatives ?? [];
  const dosageAdjustments = (checkInteractions.data as { dosage_adjustments?: string[] } | undefined)?.dosage_adjustments ?? [];
  const interactionErrorMessage = React.useMemo(() => {
    if (!checkInteractions.isError) return "";
    const error = checkInteractions.error as ApiError | undefined;
    const details = error?.details as { detail?: unknown } | undefined;
    const detail = details?.detail;
    if (typeof detail === "string" && detail.trim().length > 0) return detail;
    if (Array.isArray(detail) && detail.length > 0) {
      const first = detail[0] as { msg?: string } | string | undefined;
      if (typeof first === "string" && first.trim().length > 0) return first;
      if (first && typeof first === "object" && typeof first.msg === "string" && first.msg.trim().length > 0) {
        return first.msg;
      }
    }
    if (error?.message && error.message.trim().length > 0) return error.message;
    return "Interaction analysis failed. Retry after verifying medication names.";
  }, [checkInteractions.error, checkInteractions.isError]);

  const handleMedicationChange = (_: React.SyntheticEvent, values: string[]) => {
    const normalized = Array.from(
      new Set(
        values
          .map((value) => value.trim())
          .filter((value) => value.length > 0)
          .slice(0, 10)
      )
    );
    setMedications(normalized);
  };

  return (
    <PageContainer>
      <PageHeader
        title="Drug Safety Workspace"
        subtitle="Enter medications in a tokenized command bar, then review the interaction matrix before detailed guidance."
      />

      <Card sx={{ mb: spacing[3], borderRadius: borderRadius.md, boxShadow: componentShadows.card }}>
        <CardContent sx={{ p: spacing[4] }}>
          <Stack spacing={2}>
            <Typography variant="subtitle2" color="text.secondary">
              Medication Command Bar
            </Typography>
            <Autocomplete
              multiple
              freeSolo
              options={COMMON_MEDICATIONS}
              value={medications}
              inputValue={inputValue}
              onInputChange={(_, value) => setInputValue(value)}
              onChange={handleMedicationChange}
              filterSelectedOptions
              renderTags={(value: string[], getTagProps) =>
                value.map((option, index) => (
                  <Chip
                    {...getTagProps({ index })}
                    key={`${option}-${index}`}
                    label={option}
                    icon={<Medication sx={{ fontSize: 16 }} />}
                    sx={{
                      bgcolor: alphaUtil(semantic.info.main, 0.1),
                      color: semantic.info.main,
                      border: `1px solid ${alphaUtil(semantic.info.main, 0.25)}`,
                    }}
                  />
                ))
              }
              renderInput={(params) => (
                <TextField
                  {...params}
                  placeholder="Type medication name and press Enter..."
                  helperText="Add up to 10 medications. Keyboard support: Enter to tokenize, Backspace to remove last token."
                />
              )}
            />

            <Stack direction={{ xs: "column", sm: "row" }} spacing={1.2} alignItems={{ sm: "center" }}>
              <Button
                variant="contained"
                startIcon={<Search />}
                onClick={() => checkInteractions.mutate()}
                disabled={medications.length < 2 || checkInteractions.isPending}
              >
                {checkInteractions.isPending ? "Checking..." : "Run Interaction Check"}
              </Button>
              <Typography variant="caption" color="text.secondary">
                {medications.length < 2 ? "Add at least two medications to compute pairwise risk." : `${medications.length} medications selected.`}
              </Typography>
            </Stack>
          </Stack>
        </CardContent>
      </Card>

      {checkInteractions.isError && (
        <Alert severity="error" sx={{ mb: spacing[3] }}>
          {interactionErrorMessage}
        </Alert>
      )}

      {checkInteractions.isPending && (
        <Card sx={{ mb: spacing[3], borderRadius: borderRadius.md }}>
          <CardContent sx={{ p: spacing[3] }}>
            <Stack spacing={1.2}>
              <Skeleton height={24} width="30%" />
              <Skeleton height={260} />
              <Skeleton height={24} width="45%" />
              <Skeleton height={100} />
            </Stack>
          </CardContent>
        </Card>
      )}

      {checkInteractions.data && !checkInteractions.isPending && (
        <Stack spacing={2.5}>
          {majorInteractions.length > 0 ? (
            <Alert
              icon={<ErrorIcon />}
              severity="error"
              sx={{
                borderRadius: borderRadius.md,
                border: `1px solid ${alphaUtil(severity.major.main, 0.35)}`,
                boxShadow: `0 0 0 1px ${alphaUtil(severity.major.main, 0.2)} inset`,
              }}
            >
              <Typography variant="subtitle2" sx={{ mb: 0.5, fontWeight: 700 }}>
                {majorInteractions.length} major interaction{majorInteractions.length > 1 ? "s" : ""} detected
              </Typography>
              <Typography variant="body2">
                Immediate review required for:
                {" "}
                {majorInteractions.map((item) => `${item.drug_a} + ${item.drug_b}`).join("; ")}.
              </Typography>
            </Alert>
          ) : (
            <Alert severity="success" sx={{ borderRadius: borderRadius.md }}>
              No major interactions detected in the selected regimen.
            </Alert>
          )}

          <Grid container spacing={2}>
            <Grid item xs={12} md={4}>
              <Card sx={{ borderRadius: borderRadius.md, boxShadow: componentShadows.card }}>
                <CardContent>
                  <Typography variant="caption" color="text.secondary">
                    Major
                  </Typography>
                  <Typography variant="h4" sx={{ color: severity.major.main, lineHeight: 1.2 }}>
                    {majorInteractions.length}
                  </Typography>
                </CardContent>
              </Card>
            </Grid>
            <Grid item xs={12} md={4}>
              <Card sx={{ borderRadius: borderRadius.md, boxShadow: componentShadows.card }}>
                <CardContent>
                  <Typography variant="caption" color="text.secondary">
                    Moderate
                  </Typography>
                  <Typography variant="h4" sx={{ color: severity.moderate.main, lineHeight: 1.2 }}>
                    {moderateInteractions.length}
                  </Typography>
                </CardContent>
              </Card>
            </Grid>
            <Grid item xs={12} md={4}>
              <Card sx={{ borderRadius: borderRadius.md, boxShadow: componentShadows.card }}>
                <CardContent>
                  <Typography variant="caption" color="text.secondary">
                    Minor
                  </Typography>
                  <Typography variant="h4" sx={{ color: severity.minor.main, lineHeight: 1.2 }}>
                    {minorInteractions.length}
                  </Typography>
                </CardContent>
              </Card>
            </Grid>
          </Grid>

          <Card sx={{ borderRadius: borderRadius.md, boxShadow: componentShadows.card }}>
            <CardContent sx={{ p: spacing[3] }}>
              <Typography variant="h6" sx={{ mb: 1 }}>
                Interaction Matrix
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                First-pass matrix to quickly identify contraindicated or high-risk medication pairs.
              </Typography>
              <InteractionMatrix medications={medications} interactions={interactions} />
            </CardContent>
          </Card>

          <Card sx={{ borderRadius: borderRadius.md, boxShadow: componentShadows.card }}>
            <CardContent sx={{ p: spacing[3] }}>
              <Typography variant="h6" sx={{ mb: 1 }}>
                Interaction Details
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                Detailed rationale, evidence level, and source attribution.
              </Typography>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Drug Pair</TableCell>
                    <TableCell>Severity</TableCell>
                    <TableCell>Description</TableCell>
                    <TableCell>Evidence</TableCell>
                    <TableCell>Source</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {interactions.length === 0 && (
                    <TableRow>
                      <TableCell colSpan={5} align="center">
                        <Box sx={{ py: 3 }}>
                          <Typography variant="body2" color="text.secondary">
                            No known interactions found for the current medication set.
                          </Typography>
                        </Box>
                      </TableCell>
                    </TableRow>
                  )}
                  {interactions.map((entry, index) => {
                    const tone = severityColor(entry.severity);
                    return (
                      <TableRow key={`${entry.drug_a}-${entry.drug_b}-${index}`} hover>
                        <TableCell sx={{ fontWeight: 600 }}>
                          {entry.drug_a} + {entry.drug_b}
                        </TableCell>
                        <TableCell>
                          <Chip
                            size="small"
                            label={entry.severity.toUpperCase()}
                            icon={entry.severity === "major" ? <WarningAmber sx={{ fontSize: 14 }} /> : undefined}
                            sx={{
                              bgcolor: alphaUtil(tone, 0.12),
                              color: tone,
                              border: `1px solid ${alphaUtil(tone, 0.25)}`,
                              fontWeight: 700,
                            }}
                          />
                        </TableCell>
                        <TableCell>
                          <Typography variant="body2">{entry.description}</Typography>
                          {entry.clinical_significance && (
                            <Typography variant="caption" color="text.secondary">
                              {entry.clinical_significance}
                            </Typography>
                          )}
                        </TableCell>
                        <TableCell>Level {entry.evidence_level}</TableCell>
                        <TableCell>{entry.source}</TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </CardContent>
          </Card>

          {(alternatives.length > 0 || dosageAdjustments.length > 0) && (
            <Card sx={{ borderRadius: borderRadius.md, boxShadow: componentShadows.card }}>
              <CardContent sx={{ p: spacing[3] }}>
                {alternatives.length > 0 && (
                  <>
                    <Typography variant="subtitle2" sx={{ mb: 1 }}>
                      Suggested Alternatives
                    </Typography>
                    <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap sx={{ mb: 2 }}>
                      {alternatives.map((option) => (
                        <Chip key={option} label={option} variant="outlined" />
                      ))}
                    </Stack>
                  </>
                )}

                {alternatives.length > 0 && dosageAdjustments.length > 0 && <Divider sx={{ mb: 2 }} />}

                {dosageAdjustments.length > 0 && (
                  <>
                    <Typography variant="subtitle2" sx={{ mb: 1 }}>
                      Dosage Adjustments
                    </Typography>
                    <Stack spacing={0.8}>
                      {dosageAdjustments.map((item, index) => (
                        <Typography key={`${item}-${index}`} variant="body2">
                          • {item}
                        </Typography>
                      ))}
                    </Stack>
                  </>
                )}
              </CardContent>
            </Card>
          )}
        </Stack>
      )}
    </PageContainer>
  );
}
