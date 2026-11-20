import { useRef, useState } from "react";
import api, { errMsg, money } from "../api";
import { Empty, Field, Img, Modal, Pagination, Spinner, StatusBadge, useFetch } from "../components.jsx";
import { useToast } from "../context.jsx";

function ProductForm({ product, onDone }) {
  const toast = useToast();
  const { data: cats } = useFetch("/categories");
  const { data: brands } = useFetch("/brands");
  const [p, setP] = useState(product || { name: "", description: "", price: "", mrp: "", category_id: "", brand_id: "", is_featured: false, is_active: true, specifications: {}, images: [], variants: [] });
  const [specText, setSpecText] = useState(Object.entries(p.specifications || {}).map(([k, v]) => `${k}: ${v}`).join("\n"));
  const [vars, setVars] = useState([{ size: "", color: "", price_delta: 0, stock: 0 }]);
  const [busy, setBusy] = useState(false);
  const fileRef = useRef();
  const editing = !!product;
  const set = (k) => (e) => setP({ ...p, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value });
  const specs = () => Object.fromEntries(specText.split("\n").map((l) => l.split(/:(.*)/s).slice(0, 2).map((s) => s.trim())).filter(([k, v]) => k && v));

  const save = async (e) => {
    e.preventDefault(); setBusy(true);
    const body = { name: p.name, description: p.description, price: p.price, mrp: p.mrp || null, category_id: p.category_id ?? p.category?.id, brand_id: (p.brand_id !== undefined ? p.brand_id : p.brand?.id) || null, is_featured: p.is_featured, is_active: p.is_active, specifications: specs() };
    try {
      if (editing) { const { data } = await api.put(`/admin/products/${p.id}`, body); setP(data); toast("Product updated"); }
      else { const { data } = await api.post("/admin/products", { ...body, variants: vars }); toast("Product created. You can now upload images."); setP(data); onDone(true); }
    } catch (er) { toast(errMsg(er), "error"); } finally { setBusy(false); }
  };
  const refreshFrom = (data) => { setP(data); onDone(true); };
  const upload = async (e) => {
    const fd = new FormData(); [...e.target.files].forEach((f) => fd.append("files", f));
    try { const { data } = await api.post(`/admin/products/${p.id}/images`, fd); refreshFrom(data); toast("Images uploaded"); } catch (er) { toast(errMsg(er), "error"); }
    e.target.value = "";
  };
  const delImg = async (id) => { try { const { data } = await api.delete(`/admin/products/${p.id}/images/${id}`); refreshFrom(data); } catch (er) { toast(errMsg(er), "error"); } };
  const addVariant = async () => { try { const { data } = await api.post(`/admin/products/${p.id}/variants`, { size: "", color: "", stock: 0 }); refreshFrom(data); } catch (er) { toast(errMsg(er), "error"); } };
  const saveVariant = async (v) => { try { await api.put(`/admin/variants/${v.id}`, v); toast("Variant saved"); } catch (er) { toast(errMsg(er), "error"); } };
  const delVariant = async (id) => { try { await api.delete(`/admin/variants/${id}`); const { data } = await api.get(`/admin/products/${p.id}`); refreshFrom(data); } catch (er) { toast(errMsg(er), "error"); } };
  const setVariantField = (id, k, val) => setP({ ...p, variants: p.variants.map((v) => (v.id === id ? { ...v, [k]: val } : v)) });

  const created = !!p.id;
  return (
    <form onSubmit={save}>
      <div className="form-grid">
        <div className="full"><Field label="Name"><input required value={p.name} onChange={set("name")} /></Field></div>
        <Field label="Price (₹)"><input type="number" min="0" step="0.01" required value={p.price} onChange={set("price")} /></Field>
        <Field label="MRP (₹, optional)"><input type="number" min="0" step="0.01" value={p.mrp || ""} onChange={set("mrp")} /></Field>
        <Field label="Category"><select required value={p.category?.id || p.category_id} onChange={(e) => setP({ ...p, category_id: e.target.value, category: undefined })}><option value="">Select…</option>{cats?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></Field>
        <Field label="Brand"><select value={p.brand?.id || p.brand_id || ""} onChange={(e) => setP({ ...p, brand_id: e.target.value, brand: undefined })}><option value="">None</option>{brands?.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}</select></Field>
        <div className="full"><Field label="Description"><textarea value={p.description || ""} onChange={set("description")} /></Field></div>
        <div className="full"><Field label="Specifications (one per line, “Key: value”)"><textarea value={specText} onChange={(e) => setSpecText(e.target.value)} /></Field></div>
        <label className="check"><input type="checkbox" checked={!!p.is_featured} onChange={set("is_featured")} />Featured</label>
        <label className="check"><input type="checkbox" checked={!!p.is_active} onChange={set("is_active")} />Active (visible in store)</label>
      </div>
      {!editing && !created && <>
        <h4>Variants &amp; opening stock</h4>
        {vars.map((v, i) => <div key={i} className="row gap-s" style={{ marginBottom: ".4rem" }}>
          {["size", "color"].map((k) => <input key={k} placeholder={k} value={v[k]} onChange={(e) => setVars(vars.map((x, j) => (j === i ? { ...x, [k]: e.target.value } : x)))} />)}
          <input type="number" placeholder="+price" value={v.price_delta} onChange={(e) => setVars(vars.map((x, j) => (j === i ? { ...x, price_delta: e.target.value } : x)))} />
          <input type="number" min="0" placeholder="stock" value={v.stock} onChange={(e) => setVars(vars.map((x, j) => (j === i ? { ...x, stock: e.target.value } : x)))} />
          {vars.length > 1 && <button type="button" className="btn sm" onClick={() => setVars(vars.filter((_, j) => j !== i))}>✕</button>}</div>)}
        <button type="button" className="btn sm" onClick={() => setVars([...vars, { size: "", color: "", price_delta: 0, stock: 0 }])}>+ Add variant</button>
      </>}
      <div style={{ margin: "1rem 0" }}><button className="btn primary" disabled={busy}>{busy ? "Saving…" : created ? "Save changes" : "Create product"}</button></div>
      {created && <>
        <h4>Images</h4>
        <div className="row gap-s wrap">{p.images?.map((im) => <div key={im.id} style={{ position: "relative" }}><Img src={im.url} alt="" style={{ width: 84, height: 84, objectFit: "cover", borderRadius: 10 }} /><button type="button" className="btn sm danger" style={{ position: "absolute", top: 2, right: 2, padding: "0 .4rem" }} onClick={() => delImg(im.id)}>✕</button></div>)}
          <button type="button" className="btn" onClick={() => fileRef.current.click()}>+ Upload</button><input ref={fileRef} type="file" accept="image/png,image/jpeg,image/webp" multiple hidden onChange={upload} /></div>
        <h4>Variants</h4>
        {p.variants?.map((v) => <div key={v.id} className="row gap-s" style={{ marginBottom: ".4rem" }}><small className="muted" style={{ width: 110 }}>{v.sku}</small>
          <input placeholder="size" value={v.size || ""} onChange={(e) => setVariantField(v.id, "size", e.target.value)} /><input placeholder="color" value={v.color || ""} onChange={(e) => setVariantField(v.id, "color", e.target.value)} />
          <input type="number" title="Price adjustment" value={v.price_delta} onChange={(e) => setVariantField(v.id, "price_delta", e.target.value)} /><small className="muted">stock {v.stock}</small>
          <button type="button" className="btn sm" onClick={() => saveVariant(v)}>Save</button><button type="button" className="btn sm danger" onClick={() => delVariant(v.id)}>✕</button></div>)}
        <button type="button" className="btn sm" onClick={addVariant}>+ Add variant</button>
        <small className="muted" style={{ display: "block", marginTop: ".5rem" }}>Change stock levels from the Inventory page.</small>
      </>}
    </form>
  );
}

export function ProductsAdmin() {
  const toast = useToast();
  const [page, setPage] = useState(1);
  const [q, setQ] = useState("");
  const [term, setTerm] = useState("");
  const { data, loading, reload } = useFetch("/admin/products", { page, per_page: 10, q: term });
  const [edit, setEdit] = useState(undefined);
  const del = async (p) => { if (!window.confirm(`Delete “${p.name}”?`)) return; try { const { data } = await api.delete(`/admin/products/${p.id}`); toast(data.message); reload(); } catch (e) { toast(errMsg(e), "error"); } };
  return (
    <>
      <div className="row between wrap gap"><h2>Products</h2>
        <div className="row gap-s"><form onSubmit={(e) => { e.preventDefault(); setPage(1); setTerm(q); }}><input placeholder="Search…" value={q} onChange={(e) => setQ(e.target.value)} /></form><button className="btn primary" onClick={() => setEdit(null)}>+ Add product</button></div></div>
      {loading ? <Spinner /> : !data.items.length ? <Empty title="No products found" /> : <div className="card table-wrap"><table className="tbl"><thead><tr><th /><th>Product</th><th>Category</th><th>Price</th><th>Stock</th><th>Status</th><th /></tr></thead><tbody>
        {data.items.map((p) => <tr key={p.id}><td><Img src={p.image} alt="" style={{ width: 44, height: 44, borderRadius: 8, objectFit: "cover" }} /></td><td><b>{p.name}</b><br /><small className="muted">{p.brand?.name} · {p.seller || "Store"}</small></td><td>{p.category.name}</td><td>{money(p.price)}</td>
          <td><StatusBadge status={p.stock === 0 ? "out" : p.stock <= 10 ? "low" : "ok"} /> {p.stock}</td><td>{p.is_active ? "Active" : <span className="muted">Hidden</span>}</td>
          <td className="right"><button className="btn sm" onClick={() => setEdit(p)}>Edit</button> <button className="btn sm danger" onClick={() => del(p)}>Delete</button></td></tr>)}</tbody></table></div>}
      {data && <Pagination page={data.page} pages={data.pages} onChange={setPage} />}
      {edit !== undefined && <Modal title={edit ? "Edit product" : "Add product"} wide onClose={() => { setEdit(undefined); reload(); }}><ProductForm product={edit} onDone={reload} /></Modal>}
    </>
  );
}

function Simple({ title, url, listUrl, extra }) {
  const toast = useToast();
  const { data, reload } = useFetch(listUrl);
  const [name, setName] = useState("");
  const [editing, setEditing] = useState(null);
  const add = async (e) => { e.preventDefault(); try { await api.post(`/admin/${url}`, { name }); setName(""); reload(); toast("Added"); } catch (er) { toast(errMsg(er), "error"); } };
  const rename = async (o) => { try { await api.put(`/admin/${url}/${o.id}`, { name: editing.name }); setEditing(null); reload(); toast("Saved"); } catch (er) { toast(errMsg(er), "error"); } };
  const del = async (o) => { if (!window.confirm(`Delete ${o.name}?`)) return; try { await api.delete(`/admin/${url}/${o.id}`); reload(); toast("Deleted"); } catch (er) { toast(errMsg(er), "error"); } };
  return (
    <div className="card pad"><h3>{title}</h3>
      <form className="row gap-s" onSubmit={add}><input required placeholder={`New ${title.toLowerCase().slice(0, -1)} name`} value={name} onChange={(e) => setName(e.target.value)} /><button className="btn primary">Add</button></form>
      <table className="tbl"><tbody>{data?.map((o) => <tr key={o.id}><td>{editing?.id === o.id ? <input value={editing.name} onChange={(e) => setEditing({ ...editing, name: e.target.value })} /> : <>{o.name} {extra && <small className="muted">({o.product_count} products)</small>}</>}</td>
        <td className="right">{editing?.id === o.id ? <button className="btn sm primary" onClick={() => rename(o)}>Save</button> : <button className="btn sm" onClick={() => setEditing({ id: o.id, name: o.name })}>Rename</button>} <button className="btn sm danger" onClick={() => del(o)}>Delete</button></td></tr>)}</tbody></table>
    </div>
  );
}

export function CatalogAdmin() {
  return <><h2>Categories &amp; brands</h2><div className="two-col"><Simple title="Categories" url="categories" listUrl="/categories" extra /><Simple title="Brands" url="brands" listUrl="/brands" /></div></>;
}
