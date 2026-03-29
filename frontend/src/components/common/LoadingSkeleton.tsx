import React from 'react';
import { Box, Skeleton, Card, CardContent, Grid, Paper } from '@mui/material';

interface CardSkeletonProps {
  count?: number;
}

export function CardSkeleton({ count = 4 }: CardSkeletonProps) {
  return (
    <Grid container spacing={3}>
      {Array.from({ length: count }).map((_, i) => (
        <Grid item xs={12} sm={6} md={3} key={i}>
          <Card>
            <CardContent>
              <Skeleton variant="text" width="60%" height={24} />
              <Skeleton variant="text" width="40%" height={40} />
              <Box sx={{ display: 'flex', justifyContent: 'flex-end', mt: 1 }}>
                <Skeleton variant="circular" width={40} height={40} />
              </Box>
            </CardContent>
          </Card>
        </Grid>
      ))}
    </Grid>
  );
}

interface TableSkeletonProps {
  rows?: number;
  columns?: number;
}

export function TableSkeleton({ rows = 5, columns = 4 }: TableSkeletonProps) {
  return (
    <Paper>
      <Box sx={{ p: 2 }}>
        <Skeleton variant="text" width="20%" height={32} />
      </Box>
      <Box sx={{ px: 2, pb: 2 }}>
        <Box sx={{ display: 'flex', gap: 2, mb: 2 }}>
          {Array.from({ length: columns }).map((_, i) => (
            <Skeleton key={i} variant="text" width={`${100 / columns}%`} height={20} />
          ))}
        </Box>
        {Array.from({ length: rows }).map((_, rowIndex) => (
          <Box key={rowIndex} sx={{ display: 'flex', gap: 2, mb: 1.5 }}>
            {Array.from({ length: columns }).map((_, colIndex) => (
              <Skeleton
                key={colIndex}
                variant="text"
                width={`${100 / columns}%`}
                height={24}
              />
            ))}
          </Box>
        ))}
      </Box>
    </Paper>
  );
}

interface QuerySkeletonProps {
  showResults?: boolean;
}

export function QuerySkeleton({ showResults = false }: QuerySkeletonProps) {
  return (
    <Box>
      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Skeleton variant="text" width="30%" height={32} sx={{ mb: 2 }} />
          <Skeleton variant="rectangular" width="100%" height={56} sx={{ mb: 2, borderRadius: 1 }} />
          <Skeleton variant="rectangular" width="100%" height={120} sx={{ mb: 2, borderRadius: 1 }} />
          <Box sx={{ display: 'flex', gap: 1, mb: 2 }}>
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} variant="rounded" width={120} height={32} />
            ))}
          </Box>
          <Skeleton variant="rectangular" width={150} height={48} sx={{ borderRadius: 2 }} />
        </CardContent>
      </Card>

      {showResults && (
        <Card>
          <CardContent>
            <Skeleton variant="text" width="40%" height={32} sx={{ mb: 2 }} />
            <Skeleton variant="rectangular" width="100%" height={200} sx={{ mb: 2, borderRadius: 1 }} />
            <Skeleton variant="rectangular" width="100%" height={150} sx={{ borderRadius: 1 }} />
          </CardContent>
        </Card>
      )}
    </Box>
  );
}

interface PatientProfileSkeletonProps {
  showLabs?: boolean;
}

export function PatientProfileSkeleton({ showLabs = true }: PatientProfileSkeletonProps) {
  return (
    <Box>
      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Skeleton variant="text" width="30%" height={32} sx={{ mb: 2 }} />
          <Grid container spacing={2}>
            <Grid item xs={6}>
              <Skeleton variant="text" width="50%" height={20} />
              <Skeleton variant="text" width="70%" height={28} />
            </Grid>
            <Grid item xs={6}>
              <Skeleton variant="text" width="50%" height={20} />
              <Skeleton variant="text" width="70%" height={28} />
            </Grid>
          </Grid>
        </CardContent>
      </Card>

      <Grid container spacing={3}>
        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Skeleton variant="text" width="40%" height={28} sx={{ mb: 2 }} />
              <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1 }}>
                {Array.from({ length: 5 }).map((_, i) => (
                  <Skeleton key={i} variant="rounded" width={100 + Math.random() * 50} height={32} />
                ))}
              </Box>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Skeleton variant="text" width="40%" height={28} sx={{ mb: 2 }} />
              <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1 }}>
                {Array.from({ length: 4 }).map((_, i) => (
                  <Skeleton key={i} variant="rounded" width={80 + Math.random() * 40} height={32} />
                ))}
              </Box>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {showLabs && (
        <Card sx={{ mt: 3 }}>
          <CardContent>
            <Skeleton variant="text" width="30%" height={28} sx={{ mb: 2 }} />
            <Skeleton variant="rectangular" width="100%" height={300} sx={{ borderRadius: 1 }} />
          </CardContent>
        </Card>
      )}
    </Box>
  );
}

export function DashboardSkeleton() {
  return (
    <Box>
      <Skeleton variant="text" width="20%" height={40} sx={{ mb: 1 }} />
      <Skeleton variant="text" width="40%" height={24} sx={{ mb: 3 }} />
      <CardSkeleton count={4} />
      <Grid container spacing={3} sx={{ mt: 2 }}>
        <Grid item xs={12} md={6}>
          <Paper sx={{ p: 3 }}>
            <Skeleton variant="text" width="30%" height={28} sx={{ mb: 2 }} />
            <Skeleton variant="text" width="100%" height={20} />
            <Skeleton variant="text" width="80%" height={20} />
          </Paper>
        </Grid>
        <Grid item xs={12} md={6}>
          <Paper sx={{ p: 3 }}>
            <Skeleton variant="text" width="30%" height={28} sx={{ mb: 2 }} />
            <Skeleton variant="text" width="100%" height={20} />
            <Skeleton variant="text" width="80%" height={20} />
          </Paper>
        </Grid>
      </Grid>
    </Box>
  );
}
