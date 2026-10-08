import type { Metadata } from "next";
import "@fontsource-variable/bodoni-moda";
import "@fontsource-variable/inter";
import "@fontsource/geist-mono/400.css";
import "./globals.css";

export const metadata: Metadata = {
  title: "FaultBrief — Follow the evidence",
  description:
    "An AI support investigator concept for turning customer issues into evidence, clear findings, and a useful next step. Explore the interactive product preview.",
  openGraph: {
    title: "FaultBrief — Follow the evidence",
    description: "From a vague support ticket to a clear next step.",
    type: "website",
  },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
