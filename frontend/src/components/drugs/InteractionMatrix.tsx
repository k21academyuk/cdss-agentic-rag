import React, { useMemo, useState } from 'react';
import {
  Box,
  Tooltip,
  Typography,
  Paper,
  useTheme,
  alpha,
} from '@mui/material';
import { DrugInteraction } from '@/lib/types';

interface InteractionMatrixProps {
  medications: string[];
  interactions: DrugInteraction[];
  maxCellSize?: number;
  minCellSize?: number;
}

type SeverityLevel = 'none' | 'minor' | 'moderate' | 'major';

interface MatrixCell {
  drugA: string;
  drugB: string;
  severity: SeverityLevel;
  interaction?: DrugInteraction;
  isDiagonal: boolean;
}

const SEVERITY_COLORS = {
  none: '#4caf50',
  minor: '#ffeb3b',
  moderate: '#ff9800',
  major: '#f44336',
  diagonal: '#9e9e9e',
} as const;

const SEVERITY_LABELS = {
  none: 'No Interaction',
  minor: 'Minor',
  moderate: 'Moderate',
  major: 'Major',
} as const;

const SEVERITY_PRIORITY: SeverityLevel[] = ['major', 'moderate', 'minor', 'none'];

export default function InteractionMatrix({
  medications,
  interactions,
  maxCellSize = 60,
  minCellSize = 40,
}: InteractionMatrixProps) {
  const theme = useTheme();
  const [hoveredCell, setHoveredCell] = useState<{ row: number; col: number } | null>(null);

  const interactionLookupByDrugPair = useMemo(() => {
    const map = new Map<string, DrugInteraction>();
    
    for (const interaction of interactions) {
      const key1 = `${interaction.drug_a.toLowerCase()}:${interaction.drug_b.toLowerCase()}`;
      const key2 = `${interaction.drug_b.toLowerCase()}:${interaction.drug_a.toLowerCase()}`;
      map.set(key1, interaction);
      map.set(key2, interaction);
    }
    
    return map;
  }, [interactions]);

  const cellMatrix = useMemo((): MatrixCell[][] => {
    return medications.map((drugA, rowIndex) =>
      medications.map((drugB, colIndex) => {
        const isDiagonal = rowIndex === colIndex;
        const key = `${drugA.toLowerCase()}:${drugB.toLowerCase()}`;
        const interaction = interactionLookupByDrugPair.get(key);
        
        let severity: SeverityLevel = 'none';
        if (interaction) {
          severity = interaction.severity;
        }
        
        return {
          drugA,
          drugB,
          severity,
          interaction,
          isDiagonal,
        };
      })
    );
  }, [medications, interactionLookupByDrugPair]);

  const responsiveCellSize = useMemo(() => {
    const count = medications.length;
    if (count <= 4) return maxCellSize;
    if (count <= 6) return 50;
    if (count <= 8) return 45;
    return minCellSize;
  }, [medications.length, maxCellSize, minCellSize]);

  const columnHeaderLabelRotation = medications.length > 5 ? -45 : 0;
  const columnHeaderOffset = medications.length > 5 ? 10 : 0;

  if (medications.length < 2) {
    return (
      <Paper
        sx={{
          p: 3,
          textAlign: 'center',
          bgcolor: alpha(theme.palette.info.main, 0.1),
        }}
      >
        <Typography variant="body2" color="text.secondary">
          Add at least 2 medications to view the interaction matrix
        </Typography>
      </Paper>
    );
  }

  if (medications.length > 10) {
    return (
      <Paper
        sx={{
          p: 3,
          textAlign: 'center',
          bgcolor: alpha(theme.palette.warning.main, 0.1),
        }}
      >
        <Typography variant="body2" color="text.secondary">
          Maximum 10 medications supported in the matrix view
        </Typography>
      </Paper>
    );
  }

  const createCellTooltip = (cell: MatrixCell) => {
    if (cell.isDiagonal) {
      return (
        <Box sx={{ p: 0.5 }}>
          <Typography variant="caption" fontWeight={600}>
            {cell.drugA}
          </Typography>
          <Typography variant="caption" display="block" color="inherit">
            Self-interaction (N/A)
          </Typography>
        </Box>
      );
    }

    if (cell.interaction) {
      return (
        <Box sx={{ p: 0.5, maxWidth: 300 }}>
          <Typography variant="caption" fontWeight={600}>
            {cell.drugA} + {cell.drugB}
          </Typography>
          <Typography
            variant="caption"
            display="block"
            sx={{
              color: SEVERITY_COLORS[cell.severity],
              fontWeight: 600,
              mt: 0.5,
            }}
          >
            {SEVERITY_LABELS[cell.severity]} Interaction
          </Typography>
          <Typography variant="caption" display="block" sx={{ mt: 0.5 }}>
            {cell.interaction.description}
          </Typography>
          <Typography
            variant="caption"
            display="block"
            color="inherit"
            sx={{ mt: 0.5, opacity: 0.8 }}
          >
            Evidence Level: {cell.interaction.evidence_level} | Source: {cell.interaction.source}
          </Typography>
          {cell.interaction.clinical_significance && (
            <Typography variant="caption" display="block" sx={{ mt: 0.5, fontStyle: 'italic' }}>
              {cell.interaction.clinical_significance}
            </Typography>
          )}
        </Box>
      );
    }

    return (
      <Box sx={{ p: 0.5 }}>
        <Typography variant="caption" fontWeight={600}>
          {cell.drugA} + {cell.drugB}
        </Typography>
        <Typography variant="caption" display="block" color="inherit">
          No known interactions
        </Typography>
      </Box>
    );
  };

  return (
    <Paper
      sx={{
        p: 2,
        overflow: 'auto',
        bgcolor: theme.palette.background.paper,
      }}
    >
      <Box
        sx={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'flex-start',
          minWidth: 'fit-content',
        }}
      >
        <Box
          sx={{
            display: 'flex',
            pl: `${responsiveCellSize + 20}px`,
            mb: 0.5,
          }}
        >
          {medications.map((med, colIndex) => (
            <Box
              key={`top-${med}`}
              sx={{
                width: responsiveCellSize,
                height: columnHeaderLabelRotation !== 0 ? 60 : 30,
                display: 'flex',
                alignItems: columnHeaderLabelRotation !== 0 ? 'flex-start' : 'center',
                justifyContent: 'center',
              }}
            >
              <Typography
                variant="caption"
                sx={{
                  transform: `rotate(${columnHeaderLabelRotation}deg)`,
                  transformOrigin: columnHeaderLabelRotation !== 0 ? 'top left' : 'center',
                  whiteSpace: 'nowrap',
                  fontWeight: hoveredCell?.col === colIndex ? 600 : 400,
                  color:
                    hoveredCell?.col === colIndex
                      ? theme.palette.primary.main
                      : theme.palette.text.secondary,
                  transition: 'all 0.2s ease',
                  ml: columnHeaderOffset,
                }}
              >
                {med}
              </Typography>
            </Box>
          ))}
        </Box>

        <Box sx={{ display: 'flex' }}>
          <Box sx={{ display: 'flex', flexDirection: 'column', mr: 0.5 }}>
            {medications.map((med, rowIndex) => (
              <Box
                key={`left-${med}`}
                sx={{
                  width: responsiveCellSize + 16,
                  height: responsiveCellSize,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'flex-end',
                  pr: 1,
                }}
              >
                <Typography
                  variant="caption"
                  sx={{
                    whiteSpace: 'nowrap',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    maxWidth: responsiveCellSize + 10,
                    fontWeight: hoveredCell?.row === rowIndex ? 600 : 400,
                    color:
                      hoveredCell?.row === rowIndex
                        ? theme.palette.primary.main
                        : theme.palette.text.secondary,
                    transition: 'all 0.2s ease',
                  }}
                >
                  {med}
                </Typography>
              </Box>
            ))}
          </Box>

          <Box sx={{ display: 'flex', flexDirection: 'column' }}>
            {cellMatrix.map((row, rowIndex) => (
              <Box key={rowIndex} sx={{ display: 'flex' }}>
                {row.map((cell, colIndex) => (
                  <Tooltip
                    key={`${rowIndex}-${colIndex}`}
                    title={createCellTooltip(cell)}
                    arrow
                    placement="top"
                    enterDelay={200}
                  >
                    <Box
                      sx={{
                        width: responsiveCellSize,
                        height: responsiveCellSize,
                        bgcolor: cell.isDiagonal
                          ? SEVERITY_COLORS.diagonal
                          : SEVERITY_COLORS[cell.severity],
                        border: `1px solid ${alpha(theme.palette.divider, 0.2)}`,
                        cursor: cell.isDiagonal ? 'default' : 'pointer',
                        transition: 'all 0.2s ease',
                        opacity:
                          hoveredCell &&
                          (hoveredCell.row === rowIndex || hoveredCell.col === colIndex)
                            ? 1
                            : hoveredCell
                            ? 0.5
                            : 1,
                        transform:
                          hoveredCell?.row === rowIndex && hoveredCell?.col === colIndex
                            ? 'scale(1.1)'
                            : 'scale(1)',
                        zIndex:
                          hoveredCell?.row === rowIndex && hoveredCell?.col === colIndex
                            ? 1
                            : 0,
                        boxShadow:
                          hoveredCell?.row === rowIndex && hoveredCell?.col === colIndex
                            ? theme.shadows[4]
                            : 'none',
                        '&:hover': cell.isDiagonal
                          ? {}
                          : {
                              transform: 'scale(1.1)',
                              zIndex: 2,
                              boxShadow: theme.shadows[4],
                            },
                      }}
                      onMouseEnter={() => setHoveredCell({ row: rowIndex, col: colIndex })}
                      onMouseLeave={() => setHoveredCell(null)}
                    />
                  </Tooltip>
                ))}
              </Box>
            ))}
          </Box>
        </Box>
      </Box>

      <Box
        sx={{
          display: 'flex',
          flexWrap: 'wrap',
          gap: 2,
          mt: 3,
          pt: 2,
          borderTop: `1px solid ${theme.palette.divider}`,
        }}
      >
        <Typography variant="caption" color="text.secondary" sx={{ alignSelf: 'center' }}>
          Severity Legend:
        </Typography>
        {(['major', 'moderate', 'minor', 'none'] as SeverityLevel[]).map((severity) => (
          <Box key={severity} sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
            <Box
              sx={{
                width: 16,
                height: 16,
                bgcolor: SEVERITY_COLORS[severity],
                borderRadius: 0.5,
                border: `1px solid ${alpha(theme.palette.divider, 0.3)}`,
              }}
            />
            <Typography variant="caption" color="text.secondary">
              {SEVERITY_LABELS[severity]}
            </Typography>
          </Box>
        ))}
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
          <Box
            sx={{
              width: 16,
              height: 16,
              bgcolor: SEVERITY_COLORS.diagonal,
              borderRadius: 0.5,
              border: `1px solid ${alpha(theme.palette.divider, 0.3)}`,
            }}
          />
          <Typography variant="caption" color="text.secondary">
            Same Drug
          </Typography>
        </Box>
      </Box>

      {interactions.length > 0 && (
        <Box sx={{ mt: 2, pt: 2, borderTop: `1px solid ${theme.palette.divider}` }}>
          <Typography variant="caption" color="text.secondary">
            Found {interactions.length} interaction{interactions.length !== 1 ? 's' : ''}:
          </Typography>
          <Box sx={{ display: 'flex', gap: 1, mt: 0.5, flexWrap: 'wrap' }}>
            {SEVERITY_PRIORITY.filter((s) => s !== 'none').map((severity) => {
              const count = interactions.filter((i) => i.severity === severity).length;
              if (count === 0) return null;
              return (
                <Box
                  key={severity}
                  sx={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 0.5,
                    px: 1,
                    py: 0.25,
                    borderRadius: 1,
                    bgcolor: alpha(SEVERITY_COLORS[severity], 0.15),
                  }}
                >
                  <Box
                    sx={{
                      width: 8,
                      height: 8,
                      bgcolor: SEVERITY_COLORS[severity],
                      borderRadius: '50%',
                    }}
                  />
                  <Typography variant="caption" fontWeight={500}>
                    {count} {severity}
                  </Typography>
                </Box>
              );
            })}
          </Box>
        </Box>
      )}
    </Paper>
  );
}
