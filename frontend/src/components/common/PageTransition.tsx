import React from "react";
import { motion, useReducedMotion } from "framer-motion";

export interface PageTransitionProps {
  transitionKey?: string;
  children: React.ReactNode;
}

export default function PageTransition({ transitionKey, children }: PageTransitionProps) {
  const prefersReducedMotion = useReducedMotion();

  if (prefersReducedMotion) {
    return <>{children}</>;
  }

  return (
    <motion.div
      key={transitionKey}
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2, ease: "easeOut" }}
      style={{ width: "100%" }}
    >
      {children}
    </motion.div>
  );
}
