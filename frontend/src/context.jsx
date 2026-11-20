import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import api, { errMsg, tokens } from "./api";

const AuthCtx = createContext(null);
const CartCtx = createContext(null);
const ToastCtx = createContext(null);
export const useAuth = () => useContext(AuthCtx);
export const useCart = () => useContext(CartCtx);
export const useToast = () => useContext(ToastCtx);

function ToastProvider({ children }) {
  const [items, setItems] = useState([]);
  const push = useCallback((message, type = "success") => {
    const id = Math.random().toString(36).slice(2);
    setItems((l) => [...l, { id, message, type }]);
    setTimeout(() => setItems((l) => l.filter((t) => t.id !== id)), 3800);
  }, []);
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="toasts" role="status" aria-live="polite">
        {items.map((t) => <div key={t.id} className={`toast ${t.type}`}>{t.message}</div>)}
      </div>
    </ToastCtx.Provider>
  );
}

function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(!!tokens.access);

  useEffect(() => {
    if (!tokens.access) return;
    api.get("/auth/me").then((r) => setUser(r.data)).catch(() => tokens.clear()).finally(() => setLoading(false));
  }, []);
  useEffect(() => {
    const h = () => setUser(null);
    window.addEventListener("ss-logout", h);
    return () => window.removeEventListener("ss-logout", h);
  }, []);

  const finish = (data) => { tokens.set(data.access_token, data.refresh_token); setUser(data.user); return data.user; };
  const value = {
    user, loading, setUser,
    login: async (email, password) => finish((await api.post("/auth/login", { email, password })).data),
    register: async (payload) => finish((await api.post("/auth/register", payload)).data),
    registerSeller: async (payload) => finish((await api.post("/auth/register-seller", payload)).data),
    logout: async () => { try { await api.post("/auth/logout"); } catch { /* ignore */ } tokens.clear(); setUser(null); },
    isStaff: !!user && ["super_admin", "store_admin"].includes(user.role),
    isBackoffice: !!user && ["super_admin", "store_admin", "seller"].includes(user.role),
  };
  return <AuthCtx.Provider value={value}>{children}</AuthCtx.Provider>;
}

const GUEST_KEY = "ss_guest_cart";
const readGuest = () => { try { return JSON.parse(localStorage.getItem(GUEST_KEY) || "[]"); } catch { return []; } };
const writeGuest = (a) => localStorage.setItem(GUEST_KEY, JSON.stringify(a));

function CartProvider({ children }) {
  const { user } = useAuth();
  const toast = useToast();
  const nav = useNavigate();
  const [cart, setCart] = useState(null);
  const [wishlist, setWishlist] = useState([]);
  const [unread, setUnread] = useState(0);

  const reload = useCallback(async () => {
    const guest = readGuest();
    if (!user) {
      setWishlist([]); setUnread(0);
      if (!guest.length) { setCart(null); return; }
      try {
        const { data } = await api.post("/cart/guest", { items: guest });
        setCart(data);
        writeGuest(data.items.map((i) => ({ variant_id: i.variant_id, quantity: i.quantity })));
      } catch { /* keep previous */ }
      return;
    }
    if (guest.length) {
      try { await api.post("/cart/merge", { items: guest }); localStorage.removeItem(GUEST_KEY); toast("Items from your guest cart were added to your account", "info"); } catch { /* ignore */ }
    }
    try {
      const [c, w, n] = await Promise.all([api.get("/cart"), api.get("/wishlist"), api.get("/notifications/unread-count")]);
      setCart(c.data); setWishlist(w.data.map((p) => p.id)); setUnread(n.data.unread);
    } catch { /* handled by pages */ }
  }, [user, toast]);
  useEffect(() => { reload(); }, [reload]);

  const needLogin = () => { toast("Please log in to continue", "info"); nav("/login", { state: { from: window.location.pathname } }); };
  const run = async (fn, okMsg) => {
    try { const r = await fn(); if (r?.data?.items) setCart(r.data); if (okMsg) toast(okMsg); return r; }
    catch (e) { toast(errMsg(e), "error"); }
  };
  // Guest carts live in localStorage and are priced by the server (POST /cart/guest).
  const guestOp = async (mutate, okMsg) => {
    const next = mutate(readGuest());
    writeGuest(next);
    try {
      const { data } = await api.post("/cart/guest", { items: next });
      setCart(data);
      writeGuest(data.items.map((i) => ({ variant_id: i.variant_id, quantity: i.quantity })));
      if (okMsg) toast(okMsg);
    } catch (e) { toast(errMsg(e), "error"); }
  };
  const value = {
    cart, wishlist, unread, reload, setCart,
    count: cart?.count || 0,
    addToCart: (body) => {
      if (user) return run(() => api.post("/cart/items", body), "Added to cart");
      const qty = body.quantity || 1;
      return guestOp((g) => {
        const i = g.findIndex((x) => (body.variant_id ? x.variant_id === body.variant_id : x.product_id === body.product_id));
        if (i >= 0) return g.map((x, j) => (j === i ? { ...x, quantity: Math.min(x.quantity + qty, 20) } : x));
        return [...g, body.variant_id ? { variant_id: body.variant_id, quantity: qty } : { product_id: body.product_id, quantity: qty }];
      }, "Added to cart");
    },
    updateQty: (id, quantity) => (user ? run(() => api.patch(`/cart/items/${id}`, { quantity })) : guestOp((g) => g.map((x) => ("v" + x.variant_id === id ? { ...x, quantity } : x)))),
    removeItem: (id) => (user ? run(() => api.delete(`/cart/items/${id}`), "Removed from cart") : guestOp((g) => g.filter((x) => "v" + x.variant_id !== id), "Removed from cart")),
    applyCoupon: (code) => (user ? run(() => api.post("/cart/coupon", { code }), "Coupon applied") : needLogin()),
    removeCoupon: () => run(() => api.delete("/cart/coupon")),
    toggleWishlist: async (pid) => {
      if (!user) return needLogin();
      try {
        if (wishlist.includes(pid)) { await api.delete(`/wishlist/${pid}`); setWishlist((w) => w.filter((x) => x !== pid)); toast("Removed from wishlist"); }
        else { await api.post("/wishlist", { product_id: pid }); setWishlist((w) => [...w, pid]); toast("Saved to wishlist"); }
      } catch (e) { toast(errMsg(e), "error"); }
    },
  };
  return <CartCtx.Provider value={value}>{children}</CartCtx.Provider>;
}

export function Providers({ children }) {
  return <ToastProvider><AuthProvider><CartProvider>{children}</CartProvider></AuthProvider></ToastProvider>;
}
