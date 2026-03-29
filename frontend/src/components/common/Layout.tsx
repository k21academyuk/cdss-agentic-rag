import React, { ReactNode } from "react";
import AppShell from "@/components/layout/AppShell";

interface LayoutProps {
  children: ReactNode;
}

export default function Layout({ children }: LayoutProps) {
  return <AppShell>{children}</AppShell>;
}
