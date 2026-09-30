import { FinanceFab } from "./_components/finance-fab";

export default function FinanceLayout({ children }: { children: React.ReactNode }) {
  return (
    <div>
      {children}
      <FinanceFab />
    </div>
  );
}
