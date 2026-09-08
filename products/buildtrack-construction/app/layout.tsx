import type { Metadata } from "next";
import { BrandNormalizer } from "./brand-normalizer";
import "./globals.css";

export const metadata: Metadata = {
  title: "Nthane Brothers Construction Management System",
  description: "Construction projects, tenders, people, fleet and subcontract operations in one controlled platform developed by Ithute Solution.",
  applicationName: "Nthane Brothers Construction Management System",
  authors: [{ name: "Ithute Solution" }],
  creator: "Ithute Solution",
  openGraph: {
    type: "website",
    title: "Nthane Brothers Construction Management System",
    description: "A focused construction operations workspace for Nthane Brothers, developed by Ithute Solution.",
    images: [
      {
        url: "/og.png",
        width: 1734,
        height: 907,
        alt: "Nthane Brothers Construction Management System",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: "Nthane Brothers Construction Management System",
    description: "A focused construction operations workspace for Nthane Brothers, developed by Ithute Solution.",
    images: ["/og.png"],
  },
  icons: {
    icon: "/favicon.svg",
    shortcut: "/favicon.svg",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="antialiased"><BrandNormalizer>{children}</BrandNormalizer></body>
    </html>
  );
}
