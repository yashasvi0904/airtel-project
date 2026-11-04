import type { Metadata, Viewport } from "next";
import { Geist, Geist_Mono, Noto_Sans_Devanagari } from "next/font/google";
import "./globals.css";
import { AuthProvider } from "@/lib/auth";
import { LangProvider } from "@/lib/i18n";
import Header from "@/components/Header";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });
const deva = Noto_Sans_Devanagari({ variable: "--font-deva", subsets: ["devanagari"] });

export const metadata: Metadata = {
  title: "Udyam Digital - Accel Business",
  description: "Internet, SIMs, WhatsApp, CCTV and cloud for your small business: AI advisor, instant quote, smart KYC and live order tracking.",
};

export const viewport: Viewport = { width: "device-width", initialScale: 1, themeColor: "#e40000" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${geistSans.variable} ${geistMono.variable} ${deva.variable} h-full`}>
      <body className="min-h-full flex flex-col">
        <LangProvider>
          <AuthProvider>
            <Header />
            <main className="flex-1">{children}</main>
            <footer className="border-t border-line bg-white py-6 text-center text-xs text-muted">
              Accel Business · Udyam Digital prototype. All businesses and data shown are synthetic. Payments are simulated.
            </footer>
          </AuthProvider>
        </LangProvider>
      </body>
    </html>
  );
}
