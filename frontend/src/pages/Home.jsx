import { useState } from "react";
import { Link } from "react-router-dom";
import api, { errMsg } from "../api";
import { Empty, ErrorBox, ProductGrid, RecentlyViewedRow, Spinner, useFetch } from "../components.jsx";
import { useAuth, useToast } from "../context.jsx";

function Section({ title, params, to }) {
  const { data, loading, error, reload } = useFetch("/products", { per_page: 4, ...params });
  return (
    <section className="section">
      <div className="section-head"><h2>{title}</h2><Link to={to} className="muted">View all →</Link></div>
      {loading ? <Spinner /> : error ? <ErrorBox message={error} onRetry={reload} /> : data.items.length ? <ProductGrid items={data.items} /> : <Empty title="Nothing here yet" />}
    </section>
  );
}

function Recommended() {
  const { user } = useAuth();
  const { data } = useFetch("/products/recommendations", null, [user?.id]);
  if (!data?.length) return null;
  return (
    <section className="section">
      <div className="section-head"><h2>{user ? "Recommended for you" : "Popular picks"}</h2></div>
      <ProductGrid items={data.slice(0, 4)} />
    </section>
  );
}

export default function Home() {
  const { data: cats } = useFetch("/categories");
  const { data: settings } = useFetch("/settings/public");
  const toast = useToast();
  const [email, setEmail] = useState("");
  const subscribe = async (e) => {
    e.preventDefault();
    try { const { data } = await api.post("/newsletter", { email }); toast(data.message); setEmail(""); } catch (err) { toast(errMsg(err), "error"); }
  };
  const promos = [["Free shipping", "On orders above ₹999", "linear-gradient(120deg,#0ea5e9,#6366f1)"], ["Use WELCOME10", "10% off your first order", "linear-gradient(120deg,#ec4899,#f97316)"], ["Easy returns", "7-day hassle-free returns", "linear-gradient(120deg,#10b981,#0ea5e9)"]];
  return (
    <>
      <div className="hero">
        <h1>{settings?.hero_title || "Discover products you'll love"}</h1>
        <p>{settings?.hero_subtitle || "Free shipping above ₹999 · Easy returns"}</p>
        <div><Link to="/shop" className="btn">Shop now</Link></div>
      </div>
      <div className="promo-grid">{promos.map(([t, s, bg]) => <div key={t} className="promo" style={{ background: bg }}><div style={{ fontSize: "1.2rem" }}>{t}</div><small>{s}</small></div>)}</div>
      <div className="cat-row">{cats?.map((c) => <Link key={c.id} className="cat-chip" to={`/shop?category=${c.slug}`}>{c.name} <small>({c.product_count})</small></Link>)}</div>
      <Section title="Featured products" params={{ section: "featured" }} to="/shop?section=featured" />
      <Section title="Trending now" params={{ section: "trending" }} to="/shop?section=trending" />
      <Section title="Best sellers" params={{ section: "bestsellers" }} to="/shop?section=bestsellers" />
      <Section title="New arrivals" params={{ section: "new" }} to="/shop?section=new" />
      <Recommended />
      <RecentlyViewedRow />
      <section className="section">
        <div className="section-head"><h2>Special offers</h2></div>
        <div className="card pad row between wrap gap"><div><h3>Save big with SAVE25</h3><p className="muted">25% off (up to ₹1,500) on orders above ₹2,999. Use FLAT200 for ₹200 off above ₹1,999.</p></div><Link to="/shop?sort=price_asc" className="btn primary">Browse deals</Link></div>
      </section>
      <section className="newsletter">
        <h2>Get deals in your inbox</h2><p>Subscribe for exclusive offers and new arrivals.</p>
        <form onSubmit={subscribe}><input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@example.com" aria-label="Email" /><button className="btn primary">Subscribe</button></form>
      </section>
    </>
  );
}
