// The ten languages that leads in the supplied dataset prefer (smb_leads.csv `preferred_language`), in order of how many leads
// speak them. `locale` drives dates/numbers and browser speech recognition; `font` names the CSS variable of the script's font.
export const LANGS = [
  { code: "hi", native: "हिन्दी", english: "Hindi", locale: "hi-IN", font: "--font-deva" },
  { code: "en", native: "English", english: "English", locale: "en-IN", font: "--font-geist-sans" },
  { code: "mr", native: "मराठी", english: "Marathi", locale: "mr-IN", font: "--font-deva" },
  { code: "kn", native: "ಕನ್ನಡ", english: "Kannada", locale: "kn-IN", font: "--font-kannada" },
  { code: "gu", native: "ગુજરાતી", english: "Gujarati", locale: "gu-IN", font: "--font-gujarati" },
  { code: "te", native: "తెలుగు", english: "Telugu", locale: "te-IN", font: "--font-telugu" },
  { code: "ta", native: "தமிழ்", english: "Tamil", locale: "ta-IN", font: "--font-tamil" },
  { code: "bn", native: "বাংলা", english: "Bengali", locale: "bn-IN", font: "--font-bengali" },
  { code: "pa", native: "ਪੰਜਾਬੀ", english: "Punjabi", locale: "pa-IN", font: "--font-gurmukhi" },
  { code: "ml", native: "മലയാളം", english: "Malayalam", locale: "ml-IN", font: "--font-malayalam" },
] as const;

export type Lang = (typeof LANGS)[number]["code"];
export const DEFAULT_LANG: Lang = "en";
export const isLang = (v: unknown): v is Lang => typeof v === "string" && LANGS.some((l) => l.code === v);
export const localeOf = (lang: Lang) => LANGS.find((l) => l.code === lang)?.locale ?? "en-IN";

/** First supported language in the browser's preference list (e.g. ["ta-IN","en"] -> "ta"), else English. */
export function detectLang(preferred: readonly string[]): Lang {
  for (const p of preferred) {
    const base = p.toLowerCase().split("-")[0];
    if (isLang(base)) return base;
  }
  return DEFAULT_LANG;
}
