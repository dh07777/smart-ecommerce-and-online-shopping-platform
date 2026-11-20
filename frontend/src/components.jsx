import { useCallback, useEffect, useRef, useState } from "react";
import { Link, Navigate, NavLink, useLocation, useNavigate } from "react-router-dom";
import { Bell, Heart, LogOut, Menu, Search, ShoppingCart, Star, User, X } from "lucide-react";
import api, { errMsg, imgUrl, money } from "./api";
import { useAuth, useCart } from "./context.jsx";

export function useFetch(url, params, deps = []) {
  const [state, setState] = useState({ data: null, loading: true, error: null });
  const key = JSON.stringify(params || {});
  const load = useCallback(async () => {
    if (!url) return;
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const { data } = await api.get(url, { params });
      setState({ data, loading: false, error: null });
    } catch (e) {
      setState({ data: null, loading: false, error: errMsg(e) });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [url, key, ...deps]);
  useEffect(() => { load(); }, [load]);
  return { ...state, reload: load };
}

export const Img = ({ src, alt = "", ...rest }) => (
  <img src={imgUrl(src)} alt={alt} loading="lazy" onError={(e) => { if (!e.currentTarget.dataset.fb) { e.currentTarget.dataset.fb = "1"; e.currentTarget.src = "/placeholder.svg"; } }} {...rest} />
);

export const Spinner = ({ label = "Loading…" }) => <div className="center-box" role="status"><div className="spinner" /><span className="muted">{label}</span></div>;
export const Empty = ({ icon, title, text, action }) => (
  <div className="center-box empty">{icon}<h3>{title}</h3>{text && <p className="muted">{text}</p>}{action}</div>
);
export const ErrorBox = ({ message, onRetry }) => (
  <div className="center-box empty"><h3>Something went wrong</h3><p className="muted">{message}</p>{onRetry && <button className="btn" onClick={onRetry}>Try again</button>}</div>
);

export function Stars({ value = 0, size = 16 }) {
  return (
    <span className="stars" aria-label={`${value} out of 5`}>
      {[1, 2, 3, 4, 5].map((i) => <Star key={i} size={size} className={i <= Math.round(value) ? "on" : ""} fill={i <= Math.round(value) ? "currentColor" : "none"} />)}
    </span>
  );
}

export const StatusBadge = ({ status }) => <span className={`badge b-${status}`}>{String(status).replace(/_/g, " ")}</span>;

export function Modal({ title, onClose, children, wide }) {
  useEffect(() => { const h = (e) => e.key === "Escape" && onClose(); window.addEventListener("keydown", h); return () => window.removeEventListener("keydown", h); }, [onClose]);
  return (
    <div className="modal-bg" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className={`modal ${wide ? "wide" : ""}`} role="dialog" aria-modal="true">
        <div className="modal-head"><h3>{title}</h3><button className="icon-btn" onClick={onClose} aria-label="Close"><X size={18} /></button></div>
        <div className="modal-body">{children}</div>
      </div>
    </div>
  );
}

export function Pagination({ page, pages, onChange }) {
  if (!pages || pages <= 1) return null;
  return (
    <div className="pagination">
      <button className="btn sm" disabled={page <= 1} onClick={() => onChange(page - 1)}>Prev</button>
      <span>Page {page} of {pages}</span>
      <button className="btn sm" disabled={page >= pages} onClick={() => onChange(page + 1)}>Next</button>
    </div>
  );
}

export function Field({ label, children, hint }) {
  return <label className="field"><span>{label}</span>{children}{hint && <small className="muted">{hint}</small>}</label>;
}

export function ProductCard({ p }) {
  const { addToCart, toggleWishlist, wishlist } = useCart();
  const liked = wishlist.includes(p.id);
  return (
    <article className="card product-card">
      <Link to={`/product/${p.slug}`} className="pc-img">
        <Img src={p.image} alt={p.name} />
        {p.discount_percent > 0 && <span className="tag">-{p.discount_percent}%</span>}
        {!p.in_stock && <span className="tag out">Sold out</span>}
      </Link>
      <button className={`wish ${liked ? "on" : ""}`} onClick={() => toggleWishlist(p.id)} aria-label="Toggle wishlist"><Heart size={18} fill={liked ? "currentColor" : "none"} /></button>
      <div className="pc-body">
        <small className="muted">{p.brand?.name || p.category.name}</small>
        <Link to={`/product/${p.slug}`} className="pc-title">{p.name}</Link>
        <div className="row gap-s"><Stars value={p.rating} size={14} /><small className="muted">({p.review_count})</small></div>
        <div className="price-row"><strong>{money(p.price)}</strong>{p.mrp > p.price && <s className="muted">{money(p.mrp)}</s>}</div>
        <button className="btn primary block" disabled={!p.in_stock} onClick={() => addToCart({ product_id: p.id, quantity: 1 })}>
          {p.in_stock ? "Add to cart" : "Out of stock"}
        </button>
      </div>
    </article>
  );
}

export const ProductGrid = ({ items }) => <div className="grid products">{items.map((p) => <ProductCard key={p.id} p={p} />)}</div>;

export function RecentlyViewedRow({ exclude }) {
  const { user } = useAuth();
  const { data } = useFetch(user ? "/products/recently-viewed" : null, null, [user?.id]);
  const items = (data || []).filter((p) => p.id !== exclude).slice(0, 4);
  if (!user || !items.length) return null;
  return <section className="section"><div className="section-head"><h2>Recently viewed</h2></div><ProductGrid items={items} /></section>;
}

export function ProtectedRoute({ children, roles }) {
  const { user, loading } = useAuth();
  const loc = useLocation();
  if (loading) return <Spinner />;
  if (!user) return <Navigate to="/login" state={{ from: loc.pathname }} replace />;
  if (roles && !roles.includes(user.role) && user.role !== "super_admin") return <Navigate to="/" replace />;
  return children;
}

export function SearchBox() {
  const nav = useNavigate();
  const [q, setQ] = useState("");
  const [sugg, setSugg] = useState([]);
  const timer = useRef();
  useEffect(() => {
    clearTimeout(timer.current);
    if (q.trim().length < 2) { setSugg([]); return; }
    timer.current = setTimeout(() => api.get("/products/suggestions", { params: { q } }).then((r) => setSugg(r.data)).catch(() => {}), 250);
    return () => clearTimeout(timer.current);
  }, [q]);
  const submit = (e) => { e.preventDefault(); setSugg([]); nav(`/shop?q=${encodeURIComponent(q)}`); };
  return (
    <form className="searchbox" onSubmit={submit} role="search">
      <Search size={18} />
      <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search products, brands, categories…" aria-label="Search" />
      {sugg.length > 0 && (
        <ul className="suggest">
          {sugg.map((s) => <li key={s.slug}><Link to={`/product/${s.slug}`} onClick={() => { setSugg([]); setQ(""); }}><Img src={s.image} alt="" /><span>{s.name}</span><b>{money(s.price)}</b></Link></li>)}
        </ul>
      )}
    </form>
  );
}

export function Navbar() {
  const { user, logout, isBackoffice } = useAuth();
  const { count, wishlist, unread } = useCart();
  const [open, setOpen] = useState(false);
  const nav = useNavigate();
  return (
    <header className="navbar">
      <div className="container nav-inner">
        <button className="icon-btn menu-btn" onClick={() => setOpen(!open)} aria-label="Menu">{open ? <X /> : <Menu />}</button>
        <Link to="/" className="logo">Shop<span>Sphere</span></Link>
        <SearchBox />
        <nav className={`nav-links ${open ? "open" : ""}`} onClick={() => setOpen(false)}>
          <NavLink to="/shop">Shop</NavLink>
          <NavLink to="/support">Support</NavLink>
          {isBackoffice && <NavLink to="/admin">{user.role === "seller" ? "Seller hub" : "Admin"}</NavLink>}
          {!user && <NavLink to="/sell">Sell</NavLink>}
        </nav>
        <div className="nav-actions">
          {user && <Link to="/notifications" className="icon-btn" aria-label="Notifications"><Bell size={20} />{unread > 0 && <i className="dot">{unread}</i>}</Link>}
          <Link to="/wishlist" className="icon-btn" aria-label="Wishlist"><Heart size={20} />{wishlist.length > 0 && <i className="dot">{wishlist.length}</i>}</Link>
          <Link to="/cart" className="icon-btn" aria-label="Cart"><ShoppingCart size={20} />{count > 0 && <i className="dot">{count}</i>}</Link>
          {user ? (
            <>
              <Link to="/account" className="icon-btn" aria-label="Account"><User size={20} /></Link>
              <button className="icon-btn" aria-label="Log out" onClick={async () => { await logout(); nav("/"); }}><LogOut size={20} /></button>
            </>
          ) : <Link to="/login" className="btn primary sm">Log in</Link>}
        </div>
      </div>
    </header>
  );
}

export function Footer() {
  return (
    <footer className="footer">
      <div className="container foot-grid">
        <div><div className="logo light">Shop<span>Sphere</span></div><p>Smart shopping with fast delivery and easy returns.</p></div>
        <div><h4>Shop</h4><Link to="/shop">All products</Link><Link to="/shop?section=bestsellers">Best sellers</Link><Link to="/shop?section=new">New arrivals</Link></div>
        <div><h4>Account</h4><Link to="/account">Profile</Link><Link to="/orders">Orders</Link><Link to="/wishlist">Wishlist</Link></div>
        <div><h4>Help</h4><Link to="/support">Contact &amp; FAQ</Link><Link to="/sell">Become a seller</Link></div>
      </div>
      <div className="container copy">© {new Date().getFullYear()} ShopSphere. Demo project.</div>
    </footer>
  );
}
