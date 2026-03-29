import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { clinicalApi } from '@/lib/api-client';
import { PatientProfile, ApiError } from '@/lib/types';

import { usePatientStore } from '@/stores/patientStore';

export function usePatient(patientId: string) {
  return useQuery<PatientProfile, ApiError>({
    queryKey: ['patient', patientId],
    queryFn: () => clinicalApi.getPatient(patientId),
    enabled: !!patientId,
    staleTime: 5 * 60 * 1000,
  });
}

export function usePatientSearch(search: string, page = 1, limit = 20) {
  return useQuery({
    queryKey: ['patients', 'search', search, page, limit],
    queryFn: () => clinicalApi.searchPatients({ search, page, limit }),
    enabled: search.length >= 2,
    staleTime: 30 * 1000,
  });
}

export function useSelectedPatient() {
  return usePatientStore();
}

export function useSetSelectedPatient() {
  const setSelectedPatientId = usePatientStore((state) => state.setSelectedPatientId);
  const setSelectedPatient = usePatientStore((state) => state.setSelectedPatient);
  return (patient: PatientProfile | null) => {
    if (patient) {
      setSelectedPatientId(patient.patient_id);
      setSelectedPatient(patient);
    } else {
      setSelectedPatientId(null);
      setSelectedPatient(null);
    }
  };
}
