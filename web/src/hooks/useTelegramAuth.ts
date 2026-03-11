import { useEffect, useMemo, useState } from "react";
import { authTelegram } from "../api/client";
import { getWebApp, initTelegram } from "../telegram";

const INIT_DATA_WAIT_MS = 3000;
const INIT_DATA_POLL_MS = 150;

const readInitDataFromLocation = (): string => {
  if (typeof window === "undefined") return "";
  const search = new URLSearchParams(window.location.search);
  const fromSearch = search.get("tgWebAppData");
  if (fromSearch) return fromSearch;
  const hash = window.location.hash.startsWith("#")
    ? window.location.hash.slice(1)
    : window.location.hash;
  return new URLSearchParams(hash).get("tgWebAppData") || "";
};

export function useTelegramAuth() {
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [allowStoredToken, setAllowStoredToken] = useState(false);

  const debug = useMemo(() => {
    if (typeof window === "undefined") return false;
    return new URLSearchParams(window.location.search).get("debug") === "1";
  }, []);

  const storedToken = useMemo(() => {
    if (typeof window === "undefined") return null;
    return window.localStorage.getItem("tg_anki_token");
  }, []);

  useEffect(() => {
    let cancelled = false;
    const cleanupTelegram = initTelegram();
    const webApp = getWebApp();
    if (!webApp) {
      setError("Open this Mini App from Telegram (WebApp context missing).");
      if (storedToken) setAllowStoredToken(true);
      return () => cleanupTelegram?.();
    }
    if (webApp?.themeParams) {
      const root = document.documentElement;
      root.style.setProperty("--tg-bg", webApp.themeParams.bg_color || "#f8f6f2");
      root.style.setProperty("--tg-text", webApp.themeParams.text_color || "#1d1b16");
      root.style.setProperty("--tg-secondary-bg", webApp.themeParams.secondary_bg_color || "#ffffff");
      root.style.setProperty("--tg-accent", webApp.themeParams.button_color || "#2f7df6");
    }

    const authenticate = async () => {
      const deadline = Date.now() + INIT_DATA_WAIT_MS;
      let initData = (webApp?.initData || "").trim();

      while (!initData && Date.now() < deadline && !cancelled) {
        initData = (webApp?.initData || readInitDataFromLocation() || "").trim();
        if (initData) break;
        await new Promise((resolve) => setTimeout(resolve, INIT_DATA_POLL_MS));
      }

      if (!initData) {
        if (!cancelled) {
          setError("Missing Telegram initData. Open this app from the bot's WebApp button.");
          if (storedToken) setAllowStoredToken(true);
        }
        return;
      }

      try {
        await authTelegram(initData);
        if (!cancelled) setReady(true);
      } catch (err: unknown) {
        console.error(err);
        if (!cancelled) {
          const message = err instanceof Error ? err.message : "";
          setError(`Authentication failed. ${message}`.trim());
        }
      }
    };

    void authenticate();

    return () => {
      cancelled = true;
      cleanupTelegram?.();
    };
  }, [storedToken]);

  const continueWithStoredToken = () => {
    setError(null);
    setReady(true);
  };

  return { ready, error, allowStoredToken, continueWithStoredToken, debug };
}
