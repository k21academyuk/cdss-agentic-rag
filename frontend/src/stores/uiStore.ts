// src/stores/uiStore.ts
// Zustand store for UI state (sidebar, panels, etc.)

import { create } from "zustand";
import { persist } from "zustand/middleware";

interface UIState {
  // Sidebar state
  isSidebarOpen: boolean;
  sidebarWidth: number;

  // Panel state
  activePanel: string | null;
  expandedPanels: string[];

  // Modal state
  activeModal: string | null;
  modalData: unknown;

  // Theme
  isDarkMode: boolean;

  // Actions
  toggleSidebar: () => void;
  setSidebarOpen: (open: boolean) => void;
  setSidebarWidth: (width: number) => void;
  setActivePanel: (panelId: string | null) => void;
  togglePanel: (panelId: string) => void;
  expandPanel: (panelId: string) => void;
  collapsePanel: (panelId: string) => void;
  openModal: (modalId: string, data?: unknown) => void;
  closeModal: () => void;
  toggleDarkMode: () => void;
  setDarkMode: (isDark: boolean) => void;
}

export const useUIStore = create<UIState>()(
  persist(
    (set) => ({
      // Initial state
      isSidebarOpen: true,
      sidebarWidth: 280,
      activePanel: null,
      expandedPanels: [],
      activeModal: null,
      modalData: null,
      isDarkMode: false,

      // Actions
      toggleSidebar: () =>
        set((state) => ({ isSidebarOpen: !state.isSidebarOpen })),

      setSidebarOpen: (open: boolean) => set({ isSidebarOpen: open }),

      setSidebarWidth: (width: number) => set({ sidebarWidth: width }),

      setActivePanel: (panelId: string | null) =>
        set({ activePanel: panelId }),

      togglePanel: (panelId: string) =>
        set((state) => ({
          expandedPanels: state.expandedPanels.includes(panelId)
            ? state.expandedPanels.filter((id) => id !== panelId)
            : [...state.expandedPanels, panelId],
        })),

      expandPanel: (panelId: string) =>
        set((state) => ({
          expandedPanels: state.expandedPanels.includes(panelId)
            ? state.expandedPanels
            : [...state.expandedPanels, panelId],
        })),

      collapsePanel: (panelId: string) =>
        set((state) => ({
          expandedPanels: state.expandedPanels.filter((id) => id !== panelId),
        })),

      openModal: (modalId: string, data?: unknown) =>
        set({ activeModal: modalId, modalData: data }),

      closeModal: () => set({ activeModal: null, modalData: null }),

      toggleDarkMode: () =>
        set((state) => ({ isDarkMode: !state.isDarkMode })),

      setDarkMode: (isDark: boolean) => set({ isDarkMode: isDark }),
    }),
    {
      name: "cdss-ui-storage",
      partialize: (state) => ({
        isSidebarOpen: state.isSidebarOpen,
        sidebarWidth: state.sidebarWidth,
        isDarkMode: state.isDarkMode,
        expandedPanels: state.expandedPanels,
      }),
    }
  )
);

// Selectors
export const selectIsSidebarOpen = (state: UIState) => state.isSidebarOpen;
export const selectSidebarWidth = (state: UIState) => state.sidebarWidth;
export const selectActivePanel = (state: UIState) => state.activePanel;
export const selectExpandedPanels = (state: UIState) => state.expandedPanels;
export const selectActiveModal = (state: UIState) => state.activeModal;
export const selectIsDarkMode = (state: UIState) => state.isDarkMode;
