import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { publicApi, type StoreSettings } from "../../api";

interface StoreState {
  store: StoreSettings | null;
  loading: boolean;
  error: boolean;
  reload: () => Promise<void>;
}

const standaloneFallback: StoreState = {
  store: null,
  loading: false,
  error: false,
  reload: async () => undefined,
};

// A null-store fallback keeps independently rendered admin/login components
// usable in tests and component previews. The application root still installs
// StoreProvider, which supplies the merchant's persisted configuration.
const StoreContext = createContext<StoreState>(standaloneFallback);

function installTracking(store: StoreSettings) {
  if (store.gtm_container_id && !document.querySelector("script[data-store-gtm]")) {
    const script = document.createElement("script");
    script.async = true;
    script.dataset.storeGtm = store.gtm_container_id;
    script.src = `https://www.googletagmanager.com/gtm.js?id=${encodeURIComponent(store.gtm_container_id)}`;
    document.head.appendChild(script);
  }
  if (store.meta_pixel_id && !document.querySelector("script[data-store-meta]")) {
    const script = document.createElement("script");
    script.dataset.storeMeta = store.meta_pixel_id;
    script.text = `!function(f,b,e,v,n,t,s){if(f.fbq)return;n=f.fbq=function(){n.callMethod?n.callMethod.apply(n,arguments):n.queue.push(arguments)};if(!f._fbq)f._fbq=n;n.push=n;n.loaded=!0;n.version='2.0';n.queue=[];t=b.createElement(e);t.async=!0;t.src=v;s=b.getElementsByTagName(e)[0];s.parentNode.insertBefore(t,s)}(window,document,'script','https://connect.facebook.net/en_US/fbevents.js');fbq('init','${store.meta_pixel_id}');fbq('track','PageView');`;
    document.head.appendChild(script);
  }
}

export function StoreProvider({ children }: { children: ReactNode }) {
  const [store, setStore] = useState<StoreSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  async function reload() {
    setLoading(true);
    try {
      const loaded = await publicApi.getStore();
      setStore(loaded);
      setError(false);
      document.documentElement.lang = "es-CO";
      document.title = loaded.seo_title || loaded.store_name;
      let description = document.querySelector<HTMLMetaElement>('meta[name="description"]');
      if (!description) {
        description = document.createElement("meta");
        description.name = "description";
        document.head.appendChild(description);
      }
      description.content = loaded.seo_description;
      if (loaded.favicon_url) {
        let favicon = document.querySelector<HTMLLinkElement>('link[rel="icon"]');
        if (!favicon) {
          favicon = document.createElement("link");
          favicon.rel = "icon";
          document.head.appendChild(favicon);
        }
        favicon.href = loaded.favicon_url;
      }
      installTracking(loaded);
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void reload(); }, []);
  return <StoreContext.Provider value={{ store, loading, error, reload }}>{children}</StoreContext.Provider>;
}

export function useStore() {
  return useContext(StoreContext);
}
