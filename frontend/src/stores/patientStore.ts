import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { PatientProfile } from '@/lib/types';

interface PatientState {
  selectedPatientId: string | null;
  selectedPatient: PatientProfile | null;
  recentPatients: Array<{ id: string; name: string; timestamp: number }>;
  
  setSelectedPatientId: (id: string | null) => void;
  setSelectedPatient: (patient: PatientProfile | null) => void;
  addRecentPatient: (patient: PatientProfile) => void;
  clearRecentPatients: () => void;
}

export const usePatientStore = create<PatientState>()(
  persist(
    (set, get) => ({
      selectedPatientId: null,
      selectedPatient: null,
      recentPatients: [],
      
      setSelectedPatientId: (id) => set({ selectedPatientId: id }),
      
      setSelectedPatient: (patient) => set({ selectedPatient: patient }),
      
      addRecentPatient: (patient) => {
        const name = patient.demographics
          ? `Patient ${patient.patient_id}`
          : patient.patient_id;
        
        const recent = get().recentPatients.filter(p => p.id !== patient.patient_id);
        set({
          recentPatients: [
            { id: patient.patient_id, name, timestamp: Date.now() },
            ...recent.slice(0, 9),
          ],
        });
      },
      
      clearRecentPatients: () => set({ recentPatients: [] }),
    }),
    {
      name: 'patient-storage',
    }
  )
);
