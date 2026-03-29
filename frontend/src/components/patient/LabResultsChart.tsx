import React, { useMemo } from 'react';
import {
  Box,
  Typography,
  Paper,
  useTheme,
  Alert,
} from '@mui/material';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  ReferenceArea,
} from 'recharts';
import { LabResult } from '@/lib/types';

interface LabResultsChartProps {
  labResults: LabResult[];
  title?: string;
}

interface ChartDataPoint {
  date: string;
  formattedDate: string;
  [key: string]: string | number;
}

interface LabSeries {
  key: string;
  display: string;
  unit: string;
  color: string;
  referenceMin?: number;
  referenceMax?: number;
}

const COLORS = [
  '#1976d2',
  '#d32f2f',
  '#388e3c',
  '#f57c00',
  '#7b1fa2',
  '#00796b',
];

export default function LabResultsChart({
  labResults,
  title = 'Lab Results Trends',
}: LabResultsChartProps) {
  const theme = useTheme();

  const { chartData, series, hasData } = useMemo(() => {
    if (!labResults || labResults.length === 0) {
      return { chartData: [], series: [], hasData: false };
    }

    const groupedByTest: Record<string, LabResult[]> = {};
    labResults.forEach((result) => {
      if (!groupedByTest[result.code]) {
        groupedByTest[result.code] = [];
      }
      groupedByTest[result.code].push(result);
    });

    const testsWithTrends = Object.entries(groupedByTest)
      .filter(([, results]) => results.length >= 2)
      .sort((a, b) => a[1][0].display.localeCompare(b[1][0].display));

    if (testsWithTrends.length === 0) {
      return { chartData: [], series: [], hasData: false };
    }

    const seriesList: LabSeries[] = testsWithTrends.map(([code, results], index) => {
      const firstResult = results[0];
      let referenceMin: number | undefined;
      let referenceMax: number | undefined;

      if (firstResult.reference_range) {
        const rangeMatch = firstResult.reference_range.match(/(\d+\.?\d*)\s*[-–]\s*(\d+\.?\d*)/);
        if (rangeMatch) {
          referenceMin = parseFloat(rangeMatch[1]);
          referenceMax = parseFloat(rangeMatch[2]);
        }
      }

      return {
        key: code,
        display: firstResult.display,
        unit: firstResult.unit,
        color: COLORS[index % COLORS.length],
        referenceMin,
        referenceMax,
      };
    });

    const allDates = Array.from(
      new Set(labResults.map((r) => r.test_date))
    ).sort();

    const data: ChartDataPoint[] = allDates.map((date) => {
      const dataPoint: ChartDataPoint = {
        date,
        formattedDate: new Date(date).toLocaleDateString(),
      };

      testsWithTrends.forEach(([code, results]) => {
        const resultOnDate = results.find((r) => r.test_date === date);
        dataPoint[code] = resultOnDate ? resultOnDate.value : NaN;
      });

      return dataPoint;
    });

    return { chartData: data, series: seriesList, hasData: true };
  }, [labResults]);

  if (!hasData) {
    return (
      <Paper sx={{ p: 3 }}>
        <Typography variant="h6" gutterBottom fontWeight={600}>
          {title}
        </Typography>
        <Alert severity="info">
          No lab results with multiple measurements available to display trends.
          At least two measurements of the same test are needed to show a trend.
        </Alert>
      </Paper>
    );
  }

  return (
    <Paper sx={{ p: 3 }}>
      <Typography variant="h6" gutterBottom fontWeight={600}>
        {title}
      </Typography>
      <Box sx={{ width: '100%', height: 400 }}>
        <ResponsiveContainer>
          <LineChart
            data={chartData}
            margin={{ top: 5, right: 30, left: 20, bottom: 5 }}
          >
            <CartesianGrid
              strokeDasharray="3 3"
              stroke={theme.palette.divider}
            />
            <XAxis
              dataKey="formattedDate"
              tick={{ fill: theme.palette.text.primary, fontSize: 12 }}
              stroke={theme.palette.divider}
            />
            <YAxis
              tick={{ fill: theme.palette.text.primary, fontSize: 12 }}
              stroke={theme.palette.divider}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: theme.palette.background.paper,
                border: `1px solid ${theme.palette.divider}`,
                borderRadius: theme.shape.borderRadius,
              }}
              labelStyle={{ color: theme.palette.text.primary, fontWeight: 600 }}
              formatter={(value: number, name: string) => {
                const labSeries = series.find((s) => s.key === name);
                if (isNaN(value)) return ['N/A', labSeries?.display || name];
                return [
                  `${value} ${labSeries?.unit || ''}`,
                  labSeries?.display || name,
                ];
              }}
            />
            <Legend
              wrapperStyle={{ paddingTop: '20px' }}
              formatter={(value: string) => {
                const labSeries = series.find((s) => s.key === value);
                return labSeries?.display || value;
              }}
            />
            {series.map((s) => (
              <React.Fragment key={s.key}>
                {s.referenceMin !== undefined && s.referenceMax !== undefined && (
                  <ReferenceArea
                    y1={s.referenceMin}
                    y2={s.referenceMax}
                    fill={s.color}
                    fillOpacity={0.1}
                    stroke={s.color}
                    strokeOpacity={0.3}
                    ifOverflow="hidden"
                  />
                )}
                <Line
                  type="monotone"
                  dataKey={s.key}
                  stroke={s.color}
                  strokeWidth={2}
                  dot={{ r: 4, fill: s.color }}
                  activeDot={{ r: 6 }}
                  connectNulls={false}
                />
              </React.Fragment>
            ))}
          </LineChart>
        </ResponsiveContainer>
      </Box>
    </Paper>
  );
}
