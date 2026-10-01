import type { ReactNode } from "react";

export default function PricingLayout({ children }: { children: ReactNode }) {
  return (
    <>
      <span className="sr-only" data-deployment-marker="ithute-pricing-v1">
        Your business online from
      </span>
      {children}
    </>
  );
}
