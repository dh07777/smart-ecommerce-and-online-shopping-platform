import axios from "axios";

export const API_ORIGIN = import.meta.env.VITE_API_ORIGIN || "";
const api = axios.create({ baseURL: API_ORIGIN + "/api", timeout: 20000 });

export const tokens = {
  get access() { return localStorage.getItem("ss_access"); },
  get refresh() { return localStorage.getItem("ss_refresh"); },
  set(a, r) { localStorage.setItem("ss_access", a); if (r) localStorage.setItem("ss_refresh", r); },
  clear() { localStorage.removeItem("ss_access"); localStorage.removeItem("ss_refresh"); },
};

api.interceptors.request.use((cfg) => {
  if (tokens.access && !cfg.headers.Authorization) cfg.headers.Authorization = `Bearer ${tokens.access}`;
  return cfg;
});

let refreshing = null;
api.interceptors.response.use(
  (r) => r,
  async (error) => {
    const { config, response } = error;
    const isAuthCall = config?.url?.includes("/auth/login") || config?.url?.includes("/auth/refresh");
    if (response?.status === 401 && tokens.refresh && !config._retried && !isAuthCall) {
      config._retried = true;
      try {
        refreshing = refreshing || axios.post(API_ORIGIN + "/api/auth/refresh", null, { headers: { Authorization: `Bearer ${tokens.refresh}` } });
        const { data } = await refreshing;
        tokens.set(data.access_token);
        config.headers.Authorization = `Bearer ${data.access_token}`;
        return api(config);
      } catch {
        tokens.clear();
        window.dispatchEvent(new Event("ss-logout"));
      } finally {
        refreshing = null;
      }
    }
    return Promise.reject(error);
  }
);

export const errMsg = (e) => e?.response?.data?.error || (e?.code === "ERR_NETWORK" ? "Cannot reach the server. Is the backend running?" : e?.message || "Something went wrong");
export const imgUrl = (u) => (!u ? "/placeholder.svg" : u.startsWith("http") ? u : API_ORIGIN + u);
export const money = (n) => "₹" + Number(n || 0).toLocaleString("en-IN", { minimumFractionDigits: 0, maximumFractionDigits: 2 });
export const dateStr = (s) => (s ? new Date(s).toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" }) : "-");
export const dateTime = (s) => (s ? new Date(s).toLocaleString("en-IN", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }) : "-");

export async function downloadFile(url, filename) {
  const res = await api.get(url, { responseType: "blob" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(res.data);
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 2000);
}
export default api;
