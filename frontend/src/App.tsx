import React, { Suspense } from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import { CircularProgress, Box } from '@mui/material';
import Layout from '@/components/common/Layout';

const Dashboard = React.lazy(() => import('@/pages/Dashboard'));
const QueryPage = React.lazy(() => import('@/pages/QueryPage'));
const PatientPage = React.lazy(() => import('@/pages/PatientPage'));
const DrugCheckerPage = React.lazy(() => import('@/pages/DrugCheckerPage'));
const LiteraturePage = React.lazy(() => import('@/pages/LiteraturePage'));
const DocumentUploadPage = React.lazy(() => import('@/pages/DocumentUploadPage'));
const AdminPage = React.lazy(() => import('@/pages/AdminPage'));
const SettingsPage = React.lazy(() => import('@/pages/SettingsPage'));

const LoadingFallback = () => (
  <Box display="flex" justifyContent="center" alignItems="center" minHeight="60vh">
    <CircularProgress />
  </Box>
);

export default function App() {
  return (
    <Layout>
      <Suspense fallback={<LoadingFallback />}>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/query" element={<QueryPage />} />
          <Route path="/patients" element={<PatientPage />} />
          <Route path="/patients/:id" element={<PatientPage />} />
          <Route path="/drugs" element={<DrugCheckerPage />} />
          <Route path="/literature" element={<LiteraturePage />} />
          <Route path="/documents" element={<DocumentUploadPage />} />
          <Route path="/admin" element={<AdminPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Suspense>
    </Layout>
  );
}
