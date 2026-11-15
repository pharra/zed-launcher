import {createContext, useCallback, useContext, useMemo, type ReactNode} from "react";

export type Lang = "en" | "zh";
export type LangChoice = Lang | "auto";

/** Add a language here and it shows up in the header menu and Settings. */
export const LANGUAGES: Array<{value: Lang; label: string; short: string}> = [
  {value: "en", label: "English", short: "EN"},
  {value: "zh", label: "中文", short: "中文"},
];

const I18nContext = createContext<{
  lang: Lang;
  setLang: (lang: LangChoice) => void;
  t: (english: string, chinese: string) => string;
}>({
  lang: "en",
  setLang: () => undefined,
  t: (english) => english,
});

export function detectLang(): Lang {
  const stored = localStorage.getItem("zed.lang");
  if (stored === "en" || stored === "zh") return stored;
  const system = navigator.language || "en";
  return system.toLowerCase().startsWith("zh") ? "zh" : "en";
}

export function resolveLang(setting: string | undefined): Lang {
  if (setting === "en") return "en";
  if (setting === "zh") return "zh";
  return detectLang();
}

export function I18nProvider({
  lang,
  setLang,
  children,
}: {
  lang: Lang;
  setLang: (lang: LangChoice) => void;
  children: ReactNode;
}) {
  const t = useCallback((english: string, chinese: string) => (lang === "zh" ? chinese : english), [lang]);
  const value = useMemo(() => ({lang, setLang, t}), [lang, setLang, t]);
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useT() {
  return useContext(I18nContext);
}
