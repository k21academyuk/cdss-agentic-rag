import React from "react";
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Collapse,
  FormControlLabel,
  FormGroup,
  Grid,
  LinearProgress,
  Skeleton,
  Snackbar,
  Stack,
  Switch,
  TextField,
  Typography,
} from "@mui/material";
import { Article, ContentCopy, OpenInNew, Search, Tune } from "@mui/icons-material";
import { useMutation } from "@tanstack/react-query";
import { PageContainer, PageHeader } from "@/components/ui";
import { clinicalApi } from "@/lib/api-client";
import type { PubMedArticle } from "@/lib/types";
import { alpha as alphaUtil, borderRadius, componentShadows, semantic, spacing } from "@/theme";

const ARTICLE_TYPE_OPTIONS = ["systematic_review", "randomized_trial", "meta_analysis", "guideline", "observational"];

interface RankedArticle extends PubMedArticle {
  derived_relevance: number;
}

function normalizePapers(raw: unknown): PubMedArticle[] {
  if (!raw || typeof raw !== "object") return [];
  const record = raw as Record<string, unknown>;
  if (Array.isArray(record.articles)) return record.articles as PubMedArticle[];
  if (Array.isArray(record.papers)) return record.papers as PubMedArticle[];
  if (Array.isArray(record.results)) return record.results as PubMedArticle[];
  if (Array.isArray(record.items)) return record.items as PubMedArticle[];
  return [];
}

function getRelevance(article: PubMedArticle, index: number): number {
  if (typeof article.relevance_score === "number" && Number.isFinite(article.relevance_score)) {
    return Math.min(Math.max(article.relevance_score, 0), 1);
  }
  return Math.max(0.35, 0.95 - index * 0.07);
}

function evidenceLevel(score: number): "High" | "Moderate" | "Low" {
  if (score >= 0.8) return "High";
  if (score >= 0.6) return "Moderate";
  return "Low";
}

function evidenceTone(level: "High" | "Moderate" | "Low"): { fg: string; bg: string } {
  if (level === "High") return { fg: semantic.success.main, bg: alphaUtil(semantic.success.main, 0.12) };
  if (level === "Moderate") return { fg: semantic.warning.main, bg: alphaUtil(semantic.warning.main, 0.12) };
  return { fg: semantic.info.main, bg: alphaUtil(semantic.info.main, 0.12) };
}

function buildCitation(article: PubMedArticle): string {
  const authors = article.authors?.slice(0, 3).join(", ") || "Unknown authors";
  const year = article.publication_date ? new Date(article.publication_date).getFullYear() : "";
  return `${authors}${authors ? ". " : ""}${article.title}. ${article.journal}${year ? ` (${year})` : ""}. PMID: ${article.pmid}.`;
}

export default function LiteraturePage() {
  const [query, setQuery] = React.useState("");
  const [maxResults, setMaxResults] = React.useState(15);
  const [includeDateRange, setIncludeDateRange] = React.useState(false);
  const [startYear, setStartYear] = React.useState("2019");
  const [endYear, setEndYear] = React.useState(String(new Date().getFullYear()));
  const [articleTypes, setArticleTypes] = React.useState<string[]>([]);
  const [expandedAbstracts, setExpandedAbstracts] = React.useState<Record<string, boolean>>({});
  const [hasSearched, setHasSearched] = React.useState(false);
  const [snackbarMessage, setSnackbarMessage] = React.useState("");

  const searchLiterature = useMutation({
    mutationFn: () =>
      clinicalApi.searchLiterature({
        query: query.trim(),
        max_results: maxResults,
        article_types: articleTypes.length > 0 ? articleTypes : undefined,
        date_range: includeDateRange
          ? {
              start: `${startYear}-01-01`,
              end: `${endYear}-12-31`,
            }
          : undefined,
      }),
  });

  const rankedResults = React.useMemo(() => {
    const papers = normalizePapers(searchLiterature.data);
    return papers
      .map((paper, index): RankedArticle => ({ ...paper, derived_relevance: getRelevance(paper, index) }))
      .sort((a, b) => b.derived_relevance - a.derived_relevance);
  }, [searchLiterature.data]);

  const runSearch = () => {
    if (!query.trim()) return;
    setHasSearched(true);
    searchLiterature.mutate();
  };

  const toggleArticleType = (value: string, checked: boolean) => {
    setArticleTypes((prev) => (checked ? [...prev, value] : prev.filter((item) => item !== value)));
  };

  const toggleAbstract = (pmid: string) => {
    setExpandedAbstracts((prev) => ({ ...prev, [pmid]: !prev[pmid] }));
  };

  const copyCitation = async (article: PubMedArticle) => {
    const text = buildCitation(article);
    try {
      await navigator.clipboard.writeText(text);
      setSnackbarMessage("Citation copied to clipboard.");
    } catch {
      setSnackbarMessage("Unable to copy citation in this browser session.");
    }
  };

  return (
    <PageContainer>
      <PageHeader
        title="Literature Evidence Workspace"
        subtitle="Search, filter, and rank medical evidence with clear provenance and fast abstract drill-down."
      />

      <Grid container spacing={2}>
        <Grid item xs={12} lg={3}>
          <Card sx={{ borderRadius: borderRadius.md, boxShadow: componentShadows.card }}>
            <CardContent sx={{ p: spacing[3] }}>
              <Stack spacing={2}>
                <Stack direction="row" spacing={1} alignItems="center">
                  <Tune fontSize="small" />
                  <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
                    Search & Filters
                  </Typography>
                </Stack>

                <TextField
                  label="Clinical query"
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="e.g., anticoagulation in AF with CKD"
                  multiline
                  minRows={3}
                />

                <TextField
                  label="Max results"
                  type="number"
                  value={maxResults}
                  onChange={(event) => setMaxResults(Math.min(50, Math.max(5, Number(event.target.value) || 5)))}
                  inputProps={{ min: 5, max: 50 }}
                />

                <FormControlLabel
                  control={
                    <Switch
                      checked={includeDateRange}
                      onChange={(event) => setIncludeDateRange(event.target.checked)}
                    />
                  }
                  label="Limit publication years"
                />

                {includeDateRange && (
                  <Stack direction="row" spacing={1}>
                    <TextField
                      label="From"
                      value={startYear}
                      onChange={(event) => setStartYear(event.target.value.replace(/[^\d]/g, "").slice(0, 4))}
                    />
                    <TextField
                      label="To"
                      value={endYear}
                      onChange={(event) => setEndYear(event.target.value.replace(/[^\d]/g, "").slice(0, 4))}
                    />
                  </Stack>
                )}

                <Box>
                  <Typography variant="caption" color="text.secondary">
                    Article types
                  </Typography>
                  <FormGroup>
                    {ARTICLE_TYPE_OPTIONS.map((option) => (
                      <FormControlLabel
                        key={option}
                        control={
                          <Switch
                            checked={articleTypes.includes(option)}
                            onChange={(event) => toggleArticleType(option, event.target.checked)}
                          />
                        }
                        label={option.replace(/_/g, " ")}
                      />
                    ))}
                  </FormGroup>
                </Box>

                <Button
                  variant="contained"
                  startIcon={<Search />}
                  onClick={runSearch}
                  disabled={!query.trim() || searchLiterature.isPending}
                >
                  {searchLiterature.isPending ? "Searching..." : "Run Evidence Search"}
                </Button>
              </Stack>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} lg={9}>
          {!hasSearched && (
            <Card sx={{ borderRadius: borderRadius.md, boxShadow: componentShadows.card }}>
              <CardContent sx={{ py: spacing[8], textAlign: "center" }}>
                <Article sx={{ fontSize: 44, color: "text.disabled", mb: 1 }} />
                <Typography variant="h6">No search yet</Typography>
                <Typography variant="body2" color="text.secondary">
                  Compose a clinical question in the filter rail to rank relevant evidence.
                </Typography>
              </CardContent>
            </Card>
          )}

          {searchLiterature.isError && (
            <Alert severity="error" sx={{ mb: spacing[2], borderRadius: borderRadius.md }}>
              Literature search failed. Adjust the query or filters and retry.
            </Alert>
          )}

          {searchLiterature.isPending && (
            <Stack spacing={1.5}>
              {Array.from({ length: 4 }).map((_, index) => (
                <Card key={index} sx={{ borderRadius: borderRadius.md }}>
                  <CardContent>
                    <Skeleton width="45%" height={24} />
                    <Skeleton width="90%" height={28} />
                    <Skeleton width="100%" height={18} />
                    <Skeleton width="100%" height={18} />
                    <Skeleton width="35%" height={26} />
                  </CardContent>
                </Card>
              ))}
            </Stack>
          )}

          {!searchLiterature.isPending && hasSearched && rankedResults.length === 0 && (
            <Card sx={{ borderRadius: borderRadius.md, boxShadow: componentShadows.card }}>
              <CardContent sx={{ py: spacing[8], textAlign: "center" }}>
                <Typography variant="h6">No evidence matched this query</Typography>
                <Typography variant="body2" color="text.secondary">
                  Broaden terms, remove strict filters, or increase max results.
                </Typography>
              </CardContent>
            </Card>
          )}

          <Stack spacing={1.5}>
            {rankedResults.map((article, index) => {
              const level = evidenceLevel(article.derived_relevance);
              const tone = evidenceTone(level);
              const abstractText = article.abstract || "Abstract unavailable from current index payload.";
              const pubmedUrl = `https://pubmed.ncbi.nlm.nih.gov/${article.pmid}/`;
              const truncatedAbstract = abstractText.length > 320 ? `${abstractText.slice(0, 320)}...` : abstractText;

              return (
                <Card key={`${article.pmid}-${index}`} sx={{ borderRadius: borderRadius.md, boxShadow: componentShadows.card }}>
                  <CardContent sx={{ p: spacing[3] }}>
                    <Stack spacing={1.2}>
                      <Stack
                        direction={{ xs: "column", sm: "row" }}
                        justifyContent="space-between"
                        alignItems={{ sm: "center" }}
                        spacing={1}
                      >
                        <Typography variant="caption" color="text.secondary">
                          Rank #{index + 1} • PMID {article.pmid}
                        </Typography>
                        <Stack direction="row" spacing={1}>
                          <Chip
                            size="small"
                            label={`${level} evidence`}
                            sx={{ bgcolor: tone.bg, color: tone.fg, fontWeight: 700 }}
                          />
                          <Chip
                            size="small"
                            label={`${Math.round(article.derived_relevance * 100)}% relevance`}
                            variant="outlined"
                          />
                        </Stack>
                      </Stack>

                      <Typography variant="h6" sx={{ lineHeight: 1.4 }}>
                        {article.title}
                      </Typography>
                      <Typography variant="body2" color="text.secondary">
                        {article.journal} • {article.publication_date || "Unknown date"}
                      </Typography>

                      <Box>
                        <Typography variant="caption" color="text.secondary">
                          Relevance signal
                        </Typography>
                        <LinearProgress
                          variant="determinate"
                          value={article.derived_relevance * 100}
                          sx={{
                            mt: 0.4,
                            height: 8,
                            borderRadius: borderRadius.full,
                            backgroundColor: alphaUtil(semantic.info.main, 0.15),
                            "& .MuiLinearProgress-bar": {
                              borderRadius: borderRadius.full,
                              backgroundColor: semantic.info.main,
                            },
                          }}
                        />
                      </Box>

                      <Box>
                        <Typography variant="subtitle2" sx={{ mb: 0.4 }}>
                          Abstract preview
                        </Typography>
                        <Typography variant="body2" color="text.secondary">
                          {expandedAbstracts[article.pmid] ? abstractText : truncatedAbstract}
                        </Typography>
                        {abstractText.length > 320 && (
                          <Button size="small" onClick={() => toggleAbstract(article.pmid)} sx={{ mt: 0.6 }}>
                            {expandedAbstracts[article.pmid] ? "Collapse abstract" : "Expand abstract"}
                          </Button>
                        )}
                      </Box>

                      <Collapse in={expandedAbstracts[article.pmid] === true} timeout="auto" unmountOnExit>
                        <Box
                          sx={{
                            p: spacing[2],
                            borderRadius: borderRadius.sm,
                            bgcolor: alphaUtil(semantic.info.main, 0.08),
                          }}
                        >
                          <Typography variant="caption" color="text.secondary">
                            Citation provenance
                          </Typography>
                          <Typography variant="body2" sx={{ mt: 0.4 }}>
                            {buildCitation(article)}
                          </Typography>
                        </Box>
                      </Collapse>

                      <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
                        <Button
                          variant="outlined"
                          size="small"
                          startIcon={<OpenInNew />}
                          onClick={() => window.open(pubmedUrl, "_blank", "noopener,noreferrer")}
                        >
                          Open PubMed
                        </Button>
                        <Button
                          variant="outlined"
                          size="small"
                          startIcon={<ContentCopy />}
                          onClick={() => copyCitation(article)}
                        >
                          Copy citation
                        </Button>
                      </Stack>
                    </Stack>
                  </CardContent>
                </Card>
              );
            })}
          </Stack>
        </Grid>
      </Grid>

      <Snackbar
        open={snackbarMessage.length > 0}
        autoHideDuration={2800}
        onClose={() => setSnackbarMessage("")}
        message={snackbarMessage}
      />
    </PageContainer>
  );
}
