import type { MetadataRoute } from "next";

// Makes the site installable ("Add to Home screen" / "Install app"): it then opens full-screen like a native app.
export default function manifest(): MetadataRoute.Manifest {
  return {
    id: "/",
    name: "Accel Business - Udyam Digital",
    short_name: "Udyam Digital",
    description: "Internet, SIMs, WhatsApp, CCTV and cloud for your small business: AI advisor, instant quote, smart KYC and live order tracking.",
    start_url: "/?source=pwa",
    scope: "/",
    display: "standalone",
    orientation: "portrait",
    background_color: "#ffffff",
    theme_color: "#e40000",
    lang: "en",
    categories: ["business", "productivity", "utilities"],
    icons: [
      { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
      { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
      { src: "/icons/icon-maskable-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
    shortcuts: [
      { name: "Talk to the advisor", short_name: "Advisor", url: "/advisor", icons: [{ src: "/icons/icon-192.png", sizes: "192x192", type: "image/png" }] },
      { name: "My orders", short_name: "Orders", url: "/orders", icons: [{ src: "/icons/icon-192.png", sizes: "192x192", type: "image/png" }] },
    ],
  };
}
