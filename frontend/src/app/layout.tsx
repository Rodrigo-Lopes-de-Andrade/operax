import type { Metadata } from "next";

import { currentBrand } from "@/lib/brand";
import { Manrope } from "next/font/google";
import type { ReactNode } from "react";

import "./globals.css";

const manrope = Manrope({
  variable: "--font-manrope",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700", "800"],
});

export const metadata: Metadata = {
  title: currentBrand().name,
  description: "Gestão de jornada e custo de pessoal",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="pt-BR" className={`${manrope.variable} h-full antialiased`}>
      <body className="bg-canvas text-ink-body min-h-full font-sans">
        {children}
      </body>
    </html>
  );
}
