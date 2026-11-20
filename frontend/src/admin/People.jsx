import { useState } from "react";
import api, { dateStr, dateTime, errMsg, money } from "../api";
import { Empty, Field, Modal, Pagination, Spinner, StatusBadge, useFetch } from "../components.jsx";
import { useToast } from "../context.jsx";

export function CustomersAdmin() {
  const toast = useToast();
  const [page, setPage] = useState(1);
  const [q, setQ] = useState("");
  const [term, setTerm] = useState("");
  const { data, loading, reload } = useFetch("/admin/customers", { page, per_page: 12, q: term });
  const [edit, setEdit] = useState(null);
  const toggle = async (u) => { try { await api.patch(`/admin/customers/${u.id}/active`, { is_active: !u.is_active }); toast(u.is_active ? "Account deactivated" : "Account activated"); reload(); } catch (e) { toast(errMsg(e), "error"); } };
  const save = async (e) => { e.preventDefault(); try { await api.put(`/admin/customers/${edit.id}`, edit); toast("Customer updated"); setEdit(null); reload(); } catch (er) { toast(errMsg(er), "error"); } };
  return (
    <>
      <div className="row between wrap"><h2>Customers</h2><form onSubmit={(e) => { e.preventDefault(); setPage(1); setTerm(q); }}><input placeholder="Search name or email" value={q} onChange={(e) => setQ(e.target.value)} /></form></div>
      {loading ? <Spinner /> : <div className="card table-wrap"><table className="tbl"><thead><tr><th>Name</th><th>Email</th><th>Joined</th><th>Orders</th><th>Spent</th><th>Status</th><th /></tr></thead><tbody>
        {data.items.map((u) => <tr key={u.id}><td>{u.name}</td><td>{u.email}</td><td>{dateStr(u.created_at)}</td><td>{u.order_count}</td><td>{money(u.total_spent)}</td><td><StatusBadge status={u.is_active ? "ok" : "out"} /></td>
          <td className="right"><button className="btn sm" onClick={() => setEdit(u)}>Edit</button> <button className={`btn sm ${u.is_active ? "danger" : "primary"}`} onClick={() => toggle(u)}>{u.is_active ? "Deactivate" : "Activate"}</button></td></tr>)}</tbody></table></div>}
      {data && <Pagination page={data.page} pages={data.pages} onChange={setPage} />}
      {edit && <Modal title="Edit customer" onClose={() => setEdit(null)}><form onSubmit={save}>
        <Field label="Name"><input value={edit.name} onChange={(e) => setEdit({ ...edit, name: e.target.value })} /></Field>
        <Field label="Email"><input type="email" value={edit.email} onChange={(e) => setEdit({ ...edit, email: e.target.value })} /></Field>
        <Field label="Phone"><input value={edit.phone || ""} onChange={(e) => setEdit({ ...edit, phone: e.target.value })} /></Field><button className="btn primary">Save</button></form></Modal>}
    </>
  );
}

export function SellersAdmin() {
  const toast = useToast();
  const { data, loading, reload } = useFetch("/admin/sellers");
  const [detail, setDetail] = useState(null);
  const verify = async (s) => { try { await api.patch(`/admin/sellers/${s.id}/verify`, { is_verified: !s.is_verified }); toast(s.is_verified ? "Verification revoked" : "Seller verified"); reload(); } catch (e) { toast(errMsg(e), "error"); } };
  const open = async (s) => { const { data } = await api.get(`/admin/sellers/${s.id}`); setDetail(data); };
  if (loading) return <Spinner />;
  return (
    <>
      <h2>Sellers</h2>
      {!data.length ? <Empty title="No sellers yet" /> : <div className="card table-wrap"><table className="tbl"><thead><tr><th>Store</th><th>Owner</th><th>Products</th><th>Units sold</th><th>Revenue</th><th>Rating</th><th>Status</th><th /></tr></thead><tbody>
        {data.map((s) => <tr key={s.id}><td><b>{s.store_name}</b></td><td>{s.owner}<br /><small className="muted">{s.email}</small></td><td>{s.product_count}</td><td>{s.units_sold}</td><td>{money(s.revenue)}</td><td>{s.avg_rating || "-"}</td><td><StatusBadge status={s.is_verified ? "approved" : "pending"} /></td>
          <td className="right"><button className="btn sm" onClick={() => open(s)}>Profile</button> <button className={`btn sm ${s.is_verified ? "danger" : "primary"}`} onClick={() => verify(s)}>{s.is_verified ? "Revoke" : "Verify"}</button></td></tr>)}</tbody></table></div>}
      {detail && <Modal title={detail.store_name} wide onClose={() => setDetail(null)}><p>{detail.description}</p><p className="muted">Joined {dateStr(detail.created_at)} · Commission {detail.commission_rate}%</p>
        <h4>Top products</h4>{detail.products.length ? detail.products.map((p) => <div key={p.id} className="row between"><span>{p.name}</span><span className="muted">{p.sold_count} sold</span></div>) : <p className="muted">No products listed.</p>}</Modal>}
    </>
  );
}

export function SellerProfile() {
  const toast = useToast();
  const { data, reload } = useFetch("/admin/seller/profile");
  const [f, setF] = useState(null);
  if (!data) return <Spinner />;
  const form = f || { store_name: data.store_name, description: data.description || "" };
  const save = async (e) => { e.preventDefault(); try { await api.put("/admin/seller/profile", form); toast("Store updated"); setF(null); reload(); } catch (er) { toast(errMsg(er), "error"); } };
  return (
    <>
      <h2>My store</h2>
      {!data.is_verified && <div className="card pad" style={{ borderColor: "var(--warn)", marginBottom: "1rem" }}><b>Verification pending.</b> You can add products once our team verifies your store.</div>}
      <div className="kpis">{[["Products", data.product_count], ["Units sold", data.units_sold], ["Revenue", money(data.revenue)], ["Avg. rating", data.avg_rating || "-"]].map(([t, v]) => <div key={t} className="card kpi"><small>{t}</small><b>{v}</b></div>)}</div>
      <form className="card pad" onSubmit={save} style={{ maxWidth: 560 }}><Field label="Store name"><input value={form.store_name} onChange={(e) => setF({ ...form, store_name: e.target.value })} /></Field>
        <Field label="Description"><textarea value={form.description} onChange={(e) => setF({ ...form, description: e.target.value })} /></Field><button className="btn primary">Save</button></form>
    </>
  );
}

export function ReviewsAdmin() {
  const toast = useToast();
  const [status, setStatus] = useState("pending");
  const { data, loading, reload } = useFetch("/admin/reviews", { status, per_page: 30 });
  const mod = async (r, s) => { try { await api.patch(`/admin/reviews/${r.id}`, { status: s }); toast(`Review ${s}`); reload(); } catch (e) { toast(errMsg(e), "error"); } };
  const del = async (r) => { if (!window.confirm("Delete this review permanently?")) return; try { await api.delete(`/reviews/${r.id}`); reload(); } catch (e) { toast(errMsg(e), "error"); } };
  return (
    <>
      <div className="row between"><h2>Reviews</h2><div className="seg">{["pending", "approved", "rejected"].map((s) => <button key={s} className={status === s ? "on" : ""} onClick={() => setStatus(s)}>{s}</button>)}</div></div>
      {loading ? <Spinner /> : !data.items.length ? <Empty title={`No ${status} reviews`} /> : data.items.map((r) => <div key={r.id} className="card pad" style={{ marginBottom: ".6rem" }}>
        <div className="row between wrap"><b>{r.product.name}</b><small className="muted">{r.user} · {dateStr(r.created_at)} · {"★".repeat(r.rating)}</small></div>
        <p>{r.title && <b>{r.title}: </b>}{r.body}</p>
        <div className="row gap-s">{r.status !== "approved" && <button className="btn sm primary" onClick={() => mod(r, "approved")}>Approve</button>}{r.status !== "rejected" && <button className="btn sm" onClick={() => mod(r, "rejected")}>Reject</button>}<button className="btn sm danger" onClick={() => del(r)}>Delete</button></div></div>)}
    </>
  );
}

export function TicketsAdmin() {
  const toast = useToast();
  const [status, setStatus] = useState("");
  const { data, loading, reload } = useFetch("/admin/tickets", { status, per_page: 30 });
  const [open, setOpen] = useState(null);
  const [msg, setMsg] = useState("");
  const view = async (id) => { const { data } = await api.get(`/admin/tickets/${id}`); setOpen(data); };
  const reply = async (e) => { e.preventDefault(); try { const { data } = await api.post(`/admin/tickets/${open.id}/reply`, { message: msg }); setOpen(data); setMsg(""); reload(); } catch (er) { toast(errMsg(er), "error"); } };
  const setSt = async (s) => { try { const { data } = await api.patch(`/admin/tickets/${open.id}`, { status: s }); setOpen({ ...open, status: data.status }); reload(); } catch (er) { toast(errMsg(er), "error"); } };
  return (
    <>
      <div className="row between"><h2>Support tickets</h2><select value={status} onChange={(e) => setStatus(e.target.value)}><option value="">All</option>{["open", "in_progress", "resolved", "closed"].map((s) => <option key={s} value={s}>{s.replace("_", " ")}</option>)}</select></div>
      {loading ? <Spinner /> : !data.items.length ? <Empty title="No tickets" /> : <div className="card table-wrap"><table className="tbl"><thead><tr><th>#</th><th>Subject</th><th>From</th><th>Date</th><th>Status</th><th /></tr></thead><tbody>
        {data.items.map((t) => <tr key={t.id}><td>{t.id}</td><td>{t.subject}</td><td>{t.name}<br /><small className="muted">{t.email}</small></td><td>{dateStr(t.created_at)}</td><td><StatusBadge status={t.status} /></td><td><button className="btn sm" onClick={() => view(t.id)}>Open</button></td></tr>)}</tbody></table></div>}
      {open && <Modal title={`#${open.id} ${open.subject}`} wide onClose={() => setOpen(null)}>
        <div className="row gap-s" style={{ marginBottom: ".6rem" }}><StatusBadge status={open.status} /><button className="btn sm" onClick={() => setSt("resolved")}>Resolve</button><button className="btn sm" onClick={() => setSt("closed")}>Close</button></div>
        {open.messages.map((m) => <div key={m.id} className="card pad" style={{ marginBottom: ".5rem" }}><small className="muted">{m.sender} · {dateTime(m.created_at)}</small><p style={{ margin: 0 }}>{m.body}</p></div>)}
        <form onSubmit={reply}><Field label="Reply"><textarea required value={msg} onChange={(e) => setMsg(e.target.value)} /></Field><button className="btn primary">Send reply</button></form></Modal>}
    </>
  );
}

export function SellerOrders() {
  const { data, loading } = useFetch("/admin/seller/orders");
  if (loading) return <Spinner />;
  if (!data.length) return <><h2>Orders</h2><Empty title="No orders for your products yet" /></>;
  return (
    <>
      <h2>Orders for my products</h2>
      {data.map((o) => <div key={o.id} className="card pad" style={{ marginBottom: ".7rem" }}>
        <div className="row between wrap"><b>{o.order_number}</b><span><StatusBadge status={o.status} /> <StatusBadge status={o.payment_status} /></span></div>
        <small className="muted">{dateStr(o.created_at)} · ship to {o.ship_to}</small>
        {o.items.map((i, k) => <div key={k} className="row between"><span>{i.name} <small className="muted">{[i.size, i.color].filter(Boolean).join("/")} × {i.quantity}</small></span><span>{money(i.price * i.quantity)}</span></div>)}
        <div className="row between" style={{ borderTop: "1px solid var(--line)", marginTop: ".4rem", paddingTop: ".4rem" }}><b>Your items total</b><b>{money(o.seller_total)}</b></div></div>)}
    </>
  );
}
