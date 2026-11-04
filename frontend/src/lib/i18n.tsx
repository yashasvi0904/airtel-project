"use client";
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";

// UI strings for the customer-facing entry points. The advisor itself answers in the chosen language
// (Hindi templates are built in; other languages need the LLM provider - see docs/ARCHITECTURE.md).
const dict = {
  en: {
    tagline: "Everything your business needs to go digital - in one sitting.",
    hero_title: "Internet, SIMs, WhatsApp, CCTV and more - one plan, one bill, live in days.",
    hero_sub: "Tell our AI advisor about your business. Get a clear monthly price, verify your documents in minutes and track your installation online - no sales visit needed.",
    cta: "Build my plan",
    cta2: "Track my order",
    how: "How it works",
    s1: "Tell us about your business", s1d: "Type, size, city and budget - takes a minute.",
    s2: "Chat with the advisor", s2d: "A few simple questions, in English or Hindi.",
    s3: "See a clear monthly price", s3d: "Toggle add-ons, pick 12 or 24 months, see GST upfront.",
    s4: "Verify in minutes", s4d: "Upload GST, Udyam, ID and bill. We check them instantly.",
    s5: "Track to activation", s5d: "Book the installation slot and follow every step - no chasing.",
    nav_orders: "My orders", nav_signin: "Sign in", nav_signout: "Sign out", nav_admin: "Admin",
    ob_title: "Tell us about your business", ob_sub: "We only ask what we need to recommend the right plan.",
    submit_ob: "Continue to advisor",
  },
  hi: {
    tagline: "आपके बिज़नेस को डिजिटल बनाने की हर चीज़ - एक ही बार में।",
    hero_title: "इंटरनेट, SIM, WhatsApp, CCTV और बहुत कुछ - एक प्लान, एक बिल, कुछ ही दिनों में चालू।",
    hero_sub: "हमारे AI सलाहकार को अपने बिज़नेस के बारे में बताएँ। साफ़ मासिक कीमत पाएँ, मिनटों में दस्तावेज़ सत्यापित करें और इंस्टॉलेशन ऑनलाइन ट्रैक करें - सेल्स विज़िट की ज़रूरत नहीं।",
    cta: "मेरा प्लान बनाएँ",
    cta2: "ऑर्डर ट्रैक करें",
    how: "यह कैसे काम करता है",
    s1: "अपने बिज़नेस के बारे में बताएँ", s1d: "प्रकार, साइज़, शहर और बजट - बस एक मिनट।",
    s2: "सलाहकार से बात करें", s2d: "कुछ आसान सवाल, हिंदी या अंग्रेज़ी में।",
    s3: "साफ़ मासिक कीमत देखें", s3d: "ऐड-ऑन चुनें, 12 या 24 महीने चुनें, GST पहले से देखें।",
    s4: "मिनटों में वेरिफ़ाई करें", s4d: "GST, Udyam, ID और बिल अपलोड करें। हम तुरंत जाँचते हैं।",
    s5: "एक्टिवेशन तक ट्रैक करें", s5d: "इंस्टॉलेशन स्लॉट बुक करें और हर चरण देखें - बार-बार फ़ोन नहीं।",
    nav_orders: "मेरे ऑर्डर", nav_signin: "साइन इन", nav_signout: "साइन आउट", nav_admin: "एडमिन",
    ob_title: "अपने बिज़नेस के बारे में बताएँ", ob_sub: "सही प्लान सुझाने के लिए हम सिर्फ़ ज़रूरी जानकारी पूछते हैं।",
    submit_ob: "सलाहकार के पास जाएँ",
  },
} as const;

type Lang = "en" | "hi";
type Key = keyof (typeof dict)["en"];
const Ctx = createContext<{ lang: Lang; setLang: (l: Lang) => void; t: (k: Key) => string }>({ lang: "en", setLang: () => {}, t: (k) => dict.en[k] });

export function LangProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>("en");
  useEffect(() => {
    try {
      const saved = localStorage.getItem("udyam.lang");
      if (saved === "hi" || saved === "en") setLangState(saved);
    } catch {
      /* ignore */
    }
  }, []);
  const setLang = useCallback((l: Lang) => {
    setLangState(l);
    try {
      localStorage.setItem("udyam.lang", l);
    } catch {
      /* ignore */
    }
    document.documentElement.lang = l;
  }, []);
  const t = useCallback((k: Key) => dict[lang][k] ?? dict.en[k], [lang]);
  return <Ctx.Provider value={{ lang, setLang, t }}>{children}</Ctx.Provider>;
}

export const useLang = () => useContext(Ctx);
