import Link from "next/link";

type BrandProps = {
  href?: string;
  compact?: boolean;
  dark?: boolean;
  className?: string;
  markClassName?: string;
};

export function IdsMark({ className = "h-11 w-11" }: { className?: string }) {
  return (
    <svg viewBox="0 0 256 256" aria-hidden="true" className={className}>
      <defs>
        <linearGradient id="ids-blue" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#1475d1"/><stop offset="1" stopColor="#062f68"/></linearGradient>
        <linearGradient id="ids-green" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#7bd315"/><stop offset="1" stopColor="#249716"/></linearGradient>
      </defs>
      <path d="M42 177C21 144 19 104 34 71 49 37 79 16 114 12" fill="none" stroke="url(#ids-blue)" strokeWidth="10" strokeLinecap="round"/>
      <path d="M197 47c22 24 31 58 24 90-4 19-13 36-26 49" fill="none" stroke="url(#ids-green)" strokeWidth="9" strokeLinecap="round"/>
      <path d="M73 78h18v65H73z" fill="url(#ids-blue)"/>
      <path d="M99 78h25c28 0 44 13 44 32s-16 33-44 33H99V78zm18 17v31h9c15 0 23-5 23-16 0-10-8-15-23-15h-9z" fill="url(#ids-blue)"/>
      <path d="M189 94c-8-5-16-7-24-7-9 0-14 3-14 8 0 6 6 8 17 11 17 5 26 12 26 25 0 17-14 27-36 27-13 0-26-4-36-11l10-15c9 6 18 9 27 9 10 0 16-3 16-9 0-5-5-8-16-11-18-5-27-12-27-25 0-16 13-26 34-26 12 0 23 3 32 8l-9 16z" fill="url(#ids-green)"/>
      <path d="M59 168c26-3 49 4 69 20 20-16 43-23 69-20l-7 36c-24-2-45 4-62 18-17-14-38-20-62-18l-7-36z" fill="#f8fbff" stroke="#07376f" strokeWidth="5" strokeLinejoin="round"/>
      <path d="M64 176c24-1 45 5 64 19 19-14 40-20 64-19" fill="none" stroke="#50b51b" strokeWidth="6" strokeLinecap="round"/>
      <path d="M128 188v31" stroke="#07376f" strokeWidth="4" strokeLinecap="round"/>
      <path d="M214 31l4 9 9 4-9 4-4 9-4-9-9-4 9-4 4-9z" fill="#63c51b"/>
      <path d="M189 45l3 7 7 3-7 3-3 7-3-7-7-3 7-3 3-7z" fill="#1475d1"/>
    </svg>
  );
}

export function IdsBrand({ href = "/", compact = false, dark = false, className = "", markClassName = "h-11 w-11" }: BrandProps) {
  const body = (
    <span className={`inline-flex items-center gap-3 ${className}`}>
      <IdsMark className={markClassName} />
      {compact ? null : (
        <span className="leading-none">
          <span className={`block text-[15px] font-black tracking-[-.035em] ${dark ? "text-white" : "text-[#0b315f]"}`}>Ithute</span>
          <span className="mt-1 block text-[8px] font-black uppercase tracking-[.22em] text-[#58ae21]">Digital Solutions</span>
        </span>
      )}
    </span>
  );
  return href ? <Link href={href} aria-label="Ithute Digital Solutions home">{body}</Link> : body;
}
