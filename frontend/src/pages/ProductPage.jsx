import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Heart } from "lucide-react";
import api, { dateStr, errMsg, money } from "../api";
import { Empty, ErrorBox, Field, Img, ProductGrid, RecentlyViewedRow, Spinner, Stars, useFetch } from "../components.jsx";
import { useAuth, useCart, useToast } from "../context.jsx";

function Reviews({ product, onChange }) {
  const { user } = useAuth();
  const toast = useToast();
  const [page, setPage] = useState(1);
  const { data, reload } = useFetch(`/products/${product.id}/reviews`, { page, per_page: 5 }, [user?.id]);
  const [form, setForm] = useState({ rating: 5, title: "", body: "" });
  const [editing, setEditing] = useState(false);
  const submit = async (e) => {
    e.preventDefault();
    try {
      const r = data?.mine && editing ? await api.put(`/reviews/${data.mine.id}`, form) : await api.post(`/products/${product.id}/reviews`, form);
      toast(r.data.notice || "Review saved"); setEditing(false); setForm({ rating: 5, title: "", body: "" }); reload(); onChange();
    } catch (err) { toast(errMsg(err), "error"); }
  };
  const del = async () => { try { await api.delete(`/reviews/${data.mine.id}`); toast("Review deleted"); reload(); onChange(); } catch (err) { toast(errMsg(err), "error"); } };
  const showForm = user && (data?.can_review || editing);
  return (
    <div>
      {data && <div className="card pad row wrap gap" style={{ marginBottom: "1rem" }}>
        <div><div className="big-price">{product.rating}</div><Stars value={product.rating} /><div className="muted">{product.review_count} reviews</div></div>
        <div style={{ flex: 1, minWidth: 200 }}>{[5, 4, 3, 2, 1].map((n) => { const c = data.breakdown[n] || 0; const t = Math.max(product.review_count, 1); return <div className="hbar" key={n}><span style={{ width: 30 }}>{n}★</span><div className="t"><i style={{ width: `${(c / t) * 100}%` }} /></div><span style={{ width: 24 }}>{c}</span></div>; })}</div>
      </div>}
      {!user && <p className="muted"><Link to="/login" className="green">Log in</Link> to write a review.</p>}
      {data?.mine && !editing && <div className="card pad" style={{ marginBottom: "1rem" }}><b>Your review</b> <span className={`badge b-${data.mine.status}`}>{data.mine.status}</span><p>{data.mine.body}</p>
        <button className="btn sm" onClick={() => { setForm({ rating: data.mine.rating, title: data.mine.title || "", body: data.mine.body }); setEditing(true); }}>Edit</button> <button className="btn sm danger" onClick={del}>Delete</button></div>}
      {showForm && <form className="card pad" onSubmit={submit} style={{ marginBottom: "1rem" }}>
        <h4>{editing ? "Edit your review" : "Write a review"}</h4>
        <Field label="Rating"><select value={form.rating} onChange={(e) => setForm({ ...form, rating: +e.target.value })}>{[5, 4, 3, 2, 1].map((n) => <option key={n} value={n}>{n} stars</option>)}</select></Field>
        <Field label="Title"><input value={form.title} maxLength={120} onChange={(e) => setForm({ ...form, title: e.target.value })} /></Field>
        <Field label="Review"><textarea required value={form.body} onChange={(e) => setForm({ ...form, body: e.target.value })} /></Field>
        <button className="btn primary">Submit review</button> {editing && <button type="button" className="btn" onClick={() => setEditing(false)}>Cancel</button>}
      </form>}
      {data?.items.length === 0 && <Empty title="No reviews yet" text="Be the first to share your thoughts." />}
      {data?.items.map((r) => <div key={r.id} className="card pad" style={{ marginBottom: ".7rem" }}>
        <div className="row between"><Stars value={r.rating} /><small className="muted">{dateStr(r.created_at)}</small></div>
        <b>{r.title}</b><p style={{ margin: ".3rem 0" }}>{r.body}</p>
        <small className="muted">{r.user} {r.verified_purchase && <span className="badge b-ok">Verified purchase</span>}</small></div>)}
      {data && data.pages > 1 && <div className="pagination"><button className="btn sm" disabled={page <= 1} onClick={() => setPage(page - 1)}>Prev</button><span>{page}/{data.pages}</span><button className="btn sm" disabled={page >= data.pages} onClick={() => setPage(page + 1)}>Next</button></div>}
    </div>
  );
}

export default function ProductPage() {
  const { slug } = useParams();
  const { user } = useAuth();
  const { data: p, loading, error, reload } = useFetch(`/products/${slug}`, null, [user?.id]);
  const { addToCart, toggleWishlist, wishlist } = useCart();
  const [img, setImg] = useState(0);
  const [size, setSize] = useState(null);
  const [color, setColor] = useState(null);
  const [qty, setQty] = useState(1);
  const [tab, setTab] = useState("description");
  useEffect(() => { setImg(0); setQty(1); setTab("description"); window.scrollTo(0, 0); }, [slug]);
  useEffect(() => { if (p) { const v = p.variants.find((x) => x.stock > 0) || p.variants[0]; setSize(v?.size ?? null); setColor(v?.color ?? null); } }, [p?.id]);
  const sizes = useMemo(() => [...new Set((p?.variants || []).map((v) => v.size).filter(Boolean))], [p]);
  const colors = useMemo(() => [...new Set((p?.variants || []).map((v) => v.color).filter(Boolean))], [p]);
  const variant = p?.variants.find((v) => (v.size ?? null) === size && (v.color ?? null) === color);
  const exists = (s, c) => p.variants.find((v) => (v.size ?? null) === s && (v.color ?? null) === c);
  if (loading) return <Spinner />;
  if (error) return <ErrorBox message={error} onRetry={reload} />;
  const stock = variant?.stock ?? 0;
  const price = variant?.price ?? p.price;
  return (
    <>
      <p className="muted"><Link to="/shop">Shop</Link> / <Link to={`/shop?category=${p.category.slug}`}>{p.category.name}</Link> / {p.name}</p>
      <div className="pdp">
        <div className="gallery">
          <div className="main"><Img src={p.images[img]?.url} alt={p.name} /></div>
          <div className="thumbs">{p.images.map((im, i) => <button key={im.id} className={i === img ? "on" : ""} onClick={() => setImg(i)}><Img src={im.url} alt="" /></button>)}</div>
        </div>
        <div>
          <small className="muted">{p.brand?.name}{p.seller ? ` · Sold by ${p.seller}` : ""}</small>
          <h1>{p.name}</h1>
          <div className="row gap-s"><Stars value={p.rating} /><span className="muted">{p.rating} ({p.review_count} reviews)</span></div>
          <div className="row gap" style={{ margin: ".8rem 0" }}><span className="big-price">{money(price)}</span>{p.mrp > p.price && <><s className="muted">{money(p.mrp)}</s><span className="badge b-ok">{p.discount_percent}% off</span></>}</div>
          {sizes.length > 0 && <><b>Size</b><div className="opt-row">{sizes.map((s) => <button key={s} className={`opt ${s === size ? "on" : ""}`} disabled={!exists(s, color) && !p.variants.some((v) => v.size === s)} onClick={() => { setSize(s); if (!exists(s, color)) setColor(p.variants.find((v) => v.size === s)?.color ?? null); }}>{s}</button>)}</div></>}
          {colors.length > 0 && <><b>Color</b><div className="opt-row">{colors.map((c) => <button key={c} className={`opt ${c === color ? "on" : ""}`} disabled={!exists(size, c)} onClick={() => setColor(c)}>{c}</button>)}</div></>}
          <p>{stock === 0 ? <span className="badge b-out">Out of stock</span> : stock <= 5 ? <span className="badge b-low">Only {stock} left</span> : <span className="badge b-ok">In stock</span>}</p>
          <div className="row gap wrap">
            <div className="qty"><button onClick={() => setQty(Math.max(1, qty - 1))} aria-label="Decrease">−</button><span>{qty}</span><button onClick={() => setQty(Math.min(stock || 1, qty + 1))} aria-label="Increase">+</button></div>
            <button className="btn primary" disabled={!variant || stock === 0} onClick={() => addToCart({ variant_id: variant.id, quantity: qty })}>Add to cart</button>
            <button className="btn" onClick={() => toggleWishlist(p.id)}><Heart size={18} fill={wishlist.includes(p.id) ? "currentColor" : "none"} /> {wishlist.includes(p.id) ? "Saved" : "Wishlist"}</button>
          </div>
          {variant && <p><small className="muted">SKU: {variant.sku}</small></p>}
        </div>
      </div>
      <div className="tabs">{["description", "specifications", "reviews"].map((t) => <button key={t} className={tab === t ? "on" : ""} onClick={() => setTab(t)}>{t[0].toUpperCase() + t.slice(1)}</button>)}</div>
      {tab === "description" && <p style={{ maxWidth: 800 }}>{p.description}</p>}
      {tab === "specifications" && <table className="spec-table"><tbody>{Object.entries(p.specifications).map(([k, v]) => <tr key={k}><td>{k}</td><td>{v}</td></tr>)}</tbody></table>}
      {tab === "reviews" && <Reviews product={p} onChange={reload} />}
      <RecentlyViewedRow exclude={p.id} />
      {p.related.length > 0 && <section className="section"><h2>Related products</h2><ProductGrid items={p.related} /></section>}
    </>
  );
}
