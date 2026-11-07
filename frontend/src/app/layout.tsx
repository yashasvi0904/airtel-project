import type { Metadata, Viewport } from "next";
import {
  Geist, Geist_Mono, Noto_Sans_Bengali, Noto_Sans_Devanagari, Noto_Sans_Gujarati, Noto_Sans_Gurmukhi, Noto_Sans_Kannada, Noto_Sans_Malayalam, Noto_Sans_Tamil, Noto_Sans_Telugu,
} from "next/font/google";
import "./globals.css";
import { AuthProvider } from "@/lib/auth";
import { LangProvider } from "@/lib/i18n";
import Header from "@/components/Header";
import BackBar from "@/components/BackBar";
import Footer from "@/components/Footer";
import { PwaProvider, InstallBanner } from "@/components/Pwa";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });
// One font per script, fetched only when a page actually contains those glyphs (unicode-range), so English users download none of them.
// (next/font needs literal options: object spread is not allowed here.)
const deva = Noto_Sans_Devanagari({ variable: "--font-deva", subsets: ["devanagari"], display: "swap", preload: false });
const kannada = Noto_Sans_Kannada({ variable: "--font-kannada", subsets: ["kannada"], display: "swap", preload: false });
const gujarati = Noto_Sans_Gujarati({ variable: "--font-gujarati", subsets: ["gujarati"], display: "swap", preload: false });
const telugu = Noto_Sans_Telugu({ variable: "--font-telugu", subsets: ["telugu"], display: "swap", preload: false });
const tamil = Noto_Sans_Tamil({ variable: "--font-tamil", subsets: ["tamil"], display: "swap", preload: false });
const bengali = Noto_Sans_Bengali({ variable: "--font-bengali", subsets: ["bengali"], display: "swap", preload: false });
const gurmukhi = Noto_Sans_Gurmukhi({ variable: "--font-gurmukhi", subsets: ["gurmukhi"], display: "swap", preload: false });
const malayalam = Noto_Sans_Malayalam({ variable: "--font-malayalam", subsets: ["malayalam"], display: "swap", preload: false });

export const metadata: Metadata = {
  title: "Udyam Digital - Accel Business",
  description: "Internet, SIMs, WhatsApp, CCTV and cloud for your small business: AI advisor, instant quote, smart KYC and live order tracking.",
  applicationName: "Udyam Digital",
  // iOS "Add to Home Screen": full-screen, own name and icon (Safari ignores most of the web manifest).
  appleWebApp: { capable: true, title: "Udyam Digital", statusBarStyle: "default" },
  formatDetection: { telephone: false },
  icons: { icon: [{ url: "/icons/icon-192.png", sizes: "192x192", type: "image/png" }, { url: "/icons/icon-512.png", sizes: "512x512", type: "image/png" }], apple: [{ url: "/icons/apple-touch-icon.png", sizes: "180x180" }] },
};

export const viewport: Viewport = { width: "device-width", initialScale: 1, themeColor: "#e40000", viewportFit: "cover" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${geistSans.variable} ${geistMono.variable} ${deva.variable} ${kannada.variable} ${gujarati.variable} ${telugu.variable} ${tamil.variable} ${bengali.variable} ${gurmukhi.variable} ${malayalam.variable} h-full`}>
      <body className="min-h-full flex flex-col">
        <LangProvider>
          <AuthProvider>
            <PwaProvider>
              <Header />
              <InstallBanner />
              <BackBar />
              <main className="flex-1">{children}</main>
              <Footer />
            </PwaProvider>
          </AuthProvider>
        </LangProvider>
      </body>
    </html>
  );
}
