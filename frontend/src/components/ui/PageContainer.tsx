// src/components/ui/PageContainer.tsx
import * as React from "react";
import { cn } from "@/lib/utils";

export interface PageContainerProps extends React.HTMLAttributes<HTMLDivElement> {
  children: React.ReactNode;
}

export function PageContainer({
  children,
  className,
  ...props
}: PageContainerProps): JSX.Element {
  return (
    <div
      className={cn(
        "flex-1 overflow-y-auto p-6",
        className
      )}
      {...props}
    >
      {children}
    </div>
  );
}

export interface PageHeaderProps extends React.HTMLAttributes<HTMLDivElement> {
  title: string;
  description?: string;
  action?: React.ReactNode;
}

export function PageHeader({
  title,
  description,
  action,
  className,
  ...props
}: PageHeaderProps): JSX.Element {
  return (
    <div
      className={cn(
        "flex items-center justify-between mb-6",
        className
      )}
      {...props}
    >
      <div>
        <h1 className="text-2xl font-semibold text-foreground">{title}</h1>
        {description && (
          <p className="text-sm text-muted-foreground mt-1">{description}</p>
        )}
      </div>
      {action && <div className="flex items-center gap-2">{action}</div>}
    </div>
  );
}
