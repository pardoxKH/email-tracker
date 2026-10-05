import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Email Tracker",
  description: "Action points from your inbox, sorted on an Eisenhower matrix",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
