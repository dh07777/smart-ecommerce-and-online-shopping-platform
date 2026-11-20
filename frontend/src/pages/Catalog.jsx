import { useSearchParams } from "react-router-dom";
import { Empty, ErrorBox, Pagination, ProductGrid, Spinner, useFetch } from "../components.jsx";
import { SearchX } from "lucide-react";

export default function Catalog() {
  const [sp, setSp] = useSearchParams();
  const params = Object.fromEntries(sp.entries());
  const set = (k, v) => { const n = new URLSearchParams(sp); if (v === "" || v == null) n.delete(k); else n.set(k, v); if (k !== "page") n.delete("page"); setSp(n); };
  const toggleList = (k, v) => { const cur = (sp.get(k) || "").split(",").filter(Boolean); set(k, (cur.includes(v) ? cur.filter((x) => x !== v) : [...cur, v]).join(",")); };
  const { data, loading, error, reload } = useFetch("/products", { per_page: 12, ...params });
  const { data: cats } = useFetch("/categories");
  const { data: brands } = useFetch("/brands");
  const selected = (k) => (sp.get(k) || "").split(",").filter(Boolean);
  const advanced = ["min_price", "max_price", "min_rating", "in_stock", "category", "brand"].some((k) => sp.get(k));
  return (
    <div className="layout-shop">
      <aside className="card filters">
        <div className="row between"><h3>Filters</h3>{advanced && <button className="btn sm" onClick={() => setSp(params.q ? { q: params.q } : {})}>Clear</button>}</div>
        <h4>Category</h4>
        {cats?.map((c) => <label key={c.id} className="check"><input type="checkbox" checked={selected("category").includes(c.slug)} onChange={() => toggleList("category", c.slug)} />{c.name}</label>)}
        <h4>Brand</h4>
        {brands?.map((b) => <label key={b.id} className="check"><input type="checkbox" checked={selected("brand").includes(b.slug)} onChange={() => toggleList("brand", b.slug)} />{b.name}</label>)}
        <h4>Price (₹)</h4>
        <div className="row gap-s"><input type="number" min="0" placeholder="Min" defaultValue={params.min_price} onBlur={(e) => set("min_price", e.target.value)} /><input type="number" min="0" placeholder="Max" defaultValue={params.max_price} onBlur={(e) => set("max_price", e.target.value)} /></div>
        <h4>Rating</h4>
        {[4, 3, 2].map((r) => <label key={r} className="check"><input type="radio" name="rating" checked={params.min_rating === String(r)} onChange={() => set("min_rating", r)} />{r}★ &amp; up</label>)}
        <label className="check" style={{ marginTop: ".8rem" }}><input type="checkbox" checked={params.in_stock === "1"} onChange={(e) => set("in_stock", e.target.checked ? "1" : "")} />In stock only</label>
      </aside>
      <section>
        <div className="toolbar">
          <div><h2 style={{ margin: 0 }}>{params.q ? `Results for “${params.q}”` : "All products"}</h2>{data && <small className="muted">{data.total} items</small>}</div>
          <select value={params.sort || "newest"} onChange={(e) => set("sort", e.target.value)} aria-label="Sort">
            <option value="newest">Newest</option><option value="popular">Most popular</option><option value="rating">Top rated</option><option value="price_asc">Price: low to high</option><option value="price_desc">Price: high to low</option>
          </select>
        </div>
        {loading ? <Spinner /> : error ? <ErrorBox message={error} onRetry={reload} /> :
          data.items.length === 0 ? <Empty icon={<SearchX size={42} />} title="No products found" text="Try different keywords or clear some filters." /> :
          <><ProductGrid items={data.items} /><Pagination page={data.page} pages={data.pages} onChange={(p) => { set("page", p); window.scrollTo(0, 0); }} /></>}
      </section>
    </div>
  );
}
