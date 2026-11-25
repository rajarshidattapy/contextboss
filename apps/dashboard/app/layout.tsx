import "./globals.css";
import Link from "next/link";
import type { ReactNode } from "react";

export const metadata = { title: "ContextBoss Dashboard" };

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <nav>
          <span className="brand">ContextBoss</span>
          <Link href="/">Overview</Link>
          <Link href="/entries">Entries</Link>
          <Link href="/assemble">Assemble</Link>
        </nav>
        <main>{children}</main>
      </body>
    </html>
  );
}
