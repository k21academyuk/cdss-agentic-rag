import React, { useEffect, useState } from 'react';
import { Box, Typography, LinearProgress, Tooltip, useTheme } from '@mui/material';
import { clinicalColors, confidenceThresholds, getConfidenceLevel } from '@/theme/clinical';

type Size = 'small' | 'medium' | 'large';

interface ConfidenceIndicatorProps {
  score: number;
  showLabel?: boolean;
  size?: Size;
  animated?: boolean;
  className?: string;
}

const sizeConfig: Record<Size, { height: number; fontSize: number; labelSize: number }> = {
  small: { height: 6, fontSize: 12, labelSize: 10 },
  medium: { height: 10, fontSize: 14, labelSize: 12 },
  large: { height: 14, fontSize: 18, labelSize: 14 },
};

export default function ConfidenceIndicator({
  score,
  showLabel = true,
  size = 'medium',
  animated = true,
  className,
}: ConfidenceIndicatorProps) {
  const theme = useTheme();
  const [displayScore, setDisplayScore] = useState(0);
  const clampedScore = Math.max(0, Math.min(1, score));
  const level = getConfidenceLevel(clampedScore);
  const config = sizeConfig[size];

  useEffect(() => {
    if (animated) {
      const duration = 600;
      const startTime = performance.now();
      const startScore = displayScore;

      const animate = (currentTime: number) => {
        const elapsed = currentTime - startTime;
        const progress = Math.min(elapsed / duration, 1);
        const eased = 1 - Math.pow(1 - progress, 3);
        setDisplayScore(startScore + (clampedScore - startScore) * eased);

        if (progress < 1) {
          requestAnimationFrame(animate);
        }
      };

      requestAnimationFrame(animate);
    } else {
      setDisplayScore(clampedScore);
    }
  }, [clampedScore, animated]);

  const percentage = Math.round(displayScore * 100);
  const colorConfig = clinicalColors.confidence[level];
  const isDark = theme.palette.mode === 'dark';

  const getProgressColor = () => {
    switch (level) {
      case 'high':
        return 'success';
      case 'moderate':
        return 'warning';
      case 'low':
        return 'error';
    }
  };

  const getLabelText = () => {
    switch (level) {
      case 'high':
        return 'High Confidence';
      case 'moderate':
        return 'Moderate Confidence';
      case 'low':
        return 'Low Confidence';
    }
  };

  return (
    <Box
      className={className}
      sx={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 1.5,
      }}
    >
      {showLabel && (
        <Typography
          variant="caption"
          sx={{
            fontSize: config.labelSize,
            fontWeight: 500,
            color: isDark ? 'grey.400' : 'text.secondary',
            minWidth: 'auto',
          }}
        >
          Confidence:
        </Typography>
      )}

      <Tooltip
        title={`${getLabelText()} - ${percentage}%`}
        arrow
        placement="top"
      >
        <Box
          sx={{
            display: 'flex',
            alignItems: 'center',
            gap: 1,
            flex: 1,
            minWidth: showLabel ? 80 : 100,
          }}
        >
          <LinearProgress
            variant="determinate"
            value={displayScore * 100}
            color={getProgressColor()}
            sx={{
              flex: 1,
              height: config.height,
              borderRadius: config.height / 2,
              bgcolor: isDark ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.08)',
              '& .MuiLinearProgress-bar': {
                borderRadius: config.height / 2,
                transition: animated ? 'transform 0.6s cubic-bezier(0.4, 0, 0.2, 1)' : 'none',
              },
            }}
            aria-valuenow={percentage}
            aria-valuemin={0}
            aria-valuemax={100}
            role="progressbar"
            aria-label={`Confidence score: ${percentage}%`}
          />

          <Typography
            variant="body2"
            sx={{
              fontSize: config.fontSize,
              fontWeight: 600,
              color: colorConfig.main,
              minWidth: 42,
              textAlign: 'right',
            }}
          >
            {percentage}%
          </Typography>
        </Box>
      </Tooltip>
    </Box>
  );
}

export { clinicalColors, confidenceThresholds, getConfidenceLevel };
