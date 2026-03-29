// src/components/ui/PageHeader.tsx
import * as React from "react";
import { cn } from "@/lib/utils";

export interface PageHeaderProps extends React.HTMLAttributes<HTMLDivElement> {
  title: string;
  description?: string;
  subtitle?: string; // Alias for description (for backwards compatibility)
  action?: React.ReactNode;
}

export function PageHeader({
  title,
  description,
  subtitle,
  action,
  className,
  ...props
}: PageHeaderProps): JSX.Element {
  // Support both description and subtitle as the same thing
  const descText = description || subtitle;

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
        {descText && (
          <p className="text-sm text-muted-foreground mt-1">{descText}</p>
        )}
      </div>
      {action && <div className="flex items-center gap-2">{action}</div>}
    </div>
  );
}
