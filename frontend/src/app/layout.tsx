import type { Metadata } from "next";

import { currentBrand } from "@/lib/brand";
import { Hanken_Grotesk, Manrope } from "next/font/google";
import type { ReactNode } from "react";

import "./globals.css";

const manrope = Manrope({
  variable: "--font-manrope",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700", "800"],
});

/**
 * A face da marca FastPark, do manual: Hanken Grotesk nos quatro pesos, com
 * Verdana como fallback declarado — é o que o manual manda quando a webfont não
 * carrega, e escrever `sans-serif` no lugar seria trocar a escolha do cliente
 * por um padrão do navegador.
 *
 * Carregada por `next/font/google` e não por `<link>`: o `<link>` do protótipo
 * custa um round-trip a mais e um flash de fonte que a tela de entrada é
 * justamente onde mais aparece.
 */
const hankenGrotesk = Hanken_Grotesk({
  variable: "--font-hanken",
  subsets: ["latin"],
  weight: ["300", "400", "600", "700"],
  display: "swap",
  fallback: ["Verdana", "sans-serif"],
});

export const metadata: Metadata = {
  title: currentBrand().name,
  description: "Gestão de jornada e custo de pessoal",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html
      lang="pt-BR"
      className={`${manrope.variable} ${hankenGrotesk.variable} h-full antialiased`}
    >
      <body className="bg-canvas text-ink-body min-h-full font-sans">
        {children}
      </body>
    </html>
  );
}
