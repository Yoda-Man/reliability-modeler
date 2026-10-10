import type { Metadata } from "next";
import "./globals.css";

// System font stack (see globals.css) — no next/font/google, so builds work air-gapped.

export const metadata: Metadata = {
  title: "Reliability Modeler",
  description: "Advanced Software Reliability Model Analysis Engine",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="font-sans antialiased">
        {children}
      </body>
    </html>
  );
}
