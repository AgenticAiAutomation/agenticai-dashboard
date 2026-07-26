import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AgenticAI SEO Dashboard",
  description: "Team-facing SEO ops dashboard for AgenticAiAutomation",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
