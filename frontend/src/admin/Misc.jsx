import { useState } from "react";
import api, { dateStr, dateTime, downloadFile, errMsg, money } from "../api";
import { BarChart, HBars } from "./Dashboard.jsx";
import { Empty, Field, Modal, Pagination, Spinner, StatusBadge, useFetch } from "../components.jsx";
import { useToast } from "../context.jsx";

const blankCoupon = { code: "", description: "", discount_type: "percent", value: 10, min_order_value: 0, max_discount: "", expires_at: "", usage_limit: "", per_user_limit: 1, is_active: true };

export function CouponsAdmin() {
  const toast = useToast();
  const { data, loading, reload } = useFetch("/admin/coupons");
  const [c, setC] = useState(null);
  const save = async (e) => {
    e.preventDefault();
    const body = { ...c, expires_at: c.expires_at || null };
    try { c.id ? await api.put(`/admin/coupons/${c.id}`, body) : await api.post("/admin/coupons", body); toast("Coupon saved"); setC(null); reload(); } catch (er) { toast(errMsg(er), "error"); }
  };
  const toggle = async (x) => { try { await api.put(`/admin/coupons/${x.id}`, { is_active: !x.is_active }); reload(); } catch (e) { toast(errMsg(e), "error"); } };
  const del = async (x) => { if (!window.confirm(`Delete ${x.code}?`)) return; try { const { data } = await api.delete(`/admin/coupons/${x.id}`); toast(data.message); reload(); } catch (e) { toast(errMsg(e), "error"); } };
  const set = (k) => (e) => setC({ ...c, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value });
  return (
    <>
      <div className="row between"><h2>Coupons</h2><button className="btn primary" onClick={() => setC({ ...blankCoupon })}>+ New coupon</button></div>
      {loading ? <Spinner /> : !data.length ? <Empty title="No coupons yet" /> : <div className="card table-wrap"><table className="tbl"><thead><tr><th>Code</th><th>Discount</th><th>Min order</th><th>Expires</th><th>Used</th><th>Active</th><th /></tr></thead><tbody>
        {data.map((x) => <tr key={x.id}><td><b>{x.code}</b><br /><small className="muted">{x.description}</small></td><td>{x.discount_type === "percent" ? `${x.value}%${x.max_discount ? ` (max ${money(x.max_discount)})` : ""}` : money(x.value)}</td><td>{money(x.min_order_value)}</td><td>{x.expires_at ? dateStr(x.expires_at) : "Never"}</td><td>{x.used_count}{x.usage_limit ? ` / ${x.usage_limit}` : ""}</td>
          <td><label className="check"><input type="checkbox" checked={x.is_active} onChange={() => toggle(x)} /></label></td>
          <td className="right"><button className="btn sm" onClick={() => setC({ ...x, expires_at: x.expires_at ? x.expires_at.slice(0, 10) : "", max_discount: x.max_discount || "", usage_limit: x.usage_limit || "" })}>Edit</button> <button className="btn sm danger" onClick={() => del(x)}>Delete</button></td></tr>)}</tbody></table></div>}
      {c && <Modal title={c.id ? "Edit coupon" : "New coupon"} onClose={() => setC(null)}><form onSubmit={save}><div className="form-grid">
        <Field label="Code"><input required value={c.code} onChange={set("code")} /></Field>
        <Field label="Type"><select value={c.discount_type} onChange={set("discount_type")}><option value="percent">Percentage</option><option value="fixed">Fixed amount</option></select></Field>
        <Field label={c.discount_type === "percent" ? "Percent off" : "Amount off (₹)"}><input type="number" min="1" step="0.01" required value={c.value} onChange={set("value")} /></Field>
        <Field label="Max discount (₹, optional)"><input type="number" min="0" value={c.max_discount} onChange={set("max_discount")} /></Field>
        <Field label="Minimum order (₹)"><input type="number" min="0" value={c.min_order_value} onChange={set("min_order_value")} /></Field>
        <Field label="Expiry date"><input type="date" value={c.expires_at} onChange={set("expires_at")} /></Field>
        <Field label="Total usage limit"><input type="number" min="0" value={c.usage_limit} onChange={set("usage_limit")} /></Field>
        <Field label="Per-user limit"><input type="number" min="1" value={c.per_user_limit || ""} onChange={set("per_user_limit")} /></Field>
        <div className="full"><Field label="Description"><input value={c.description || ""} onChange={set("description")} /></Field></div></div>
        <label className="check"><input type="checkbox" checked={c.is_active} onChange={set("is_active")} />Enabled</label><button className="btn primary">Save coupon</button></form></Modal>}
    </>
  );
}

export function Analytics() {
  const toast = useToast();
  const [period, setPeriod] = useState("daily");
  const { data: sales, loading } = useFetch("/admin/analytics/sales", { period });
  const { data: top } = useFetch("/admin/analytics/top-products");
  const { data: cats } = useFetch("/admin/analytics/by-category");
  const { data: cust } = useFetch("/admin/analytics/customers");
  const { data: ord } = useFetch("/admin/analytics/orders");
  const exp = (t) => downloadFile(`/admin/analytics/export?type=${t}`, `${t}-report.csv`).catch((e) => toast(errMsg(e), "error"));
  return (
    <>
      <div className="row between wrap gap"><h2>Sales analytics</h2>
        <div className="row gap-s wrap">{["orders", "products", "customers"].map((t) => <button key={t} className="btn sm" onClick={() => exp(t)}>Export {t} CSV</button>)}</div></div>
      <div className="card pad"><div className="row between wrap"><h3>Revenue</h3><div className="seg">{["daily", "monthly", "annual"].map((p) => <button key={p} className={period === p ? "on" : ""} onClick={() => setPeriod(p)}>{p}</button>)}</div></div>
        {loading || !sales ? <Spinner /> : <><p className="muted">{money(sales.total_revenue)} paid revenue · {sales.total_orders} orders in this view. Hover or tap a bar for details.</p><BarChart data={sales.series.map((s) => ({ label: s.label, value: s.revenue }))} format={money} /></>}</div>
      <div className="two-col" style={{ marginTop: "1rem" }}>
        <div className="card pad"><h3>Best-selling products</h3>{top ? <HBars rows={top} labelKey="name" valueKey="units" format={(v) => `${v} sold`} /> : <Spinner />}</div>
        <div className="card pad"><h3>Sales by category</h3>{cats ? <HBars rows={cats} labelKey="category" valueKey="revenue" format={money} /> : <Spinner />}</div>
        <div className="card pad"><h3>Customers</h3>{cust ? <><p className="muted">{cust.buyers} buyers · {cust.repeat_buyers} repeat ({cust.repeat_rate}%)</p>
          <h4>New customers by month</h4><BarChart data={cust.new_customers.map((n) => ({ label: n.month, value: n.count }))} />
          <h4>Top customers</h4>{cust.top_customers.map((t) => <div key={t.id} className="row between"><span>{t.name}</span><b>{money(t.spent)}</b></div>)}</> : <Spinner />}</div>
        <div className="card pad"><h3>Orders</h3>{ord ? <><p>Average order value: <b>{money(ord.average_order_value)}</b></p>
          <h4>By status</h4>{Object.entries(ord.by_status).map(([k, v]) => <div key={k} className="row between"><StatusBadge status={k} /><b>{v}</b></div>)}
          <h4>By payment method</h4>{Object.entries(ord.by_payment_method).map(([k, v]) => <div key={k} className="row between"><span>{k}</span><b>{v}</b></div>)}</> : <Spinner />}</div>
      </div>
    </>
  );
}

const LABELS = { store_name: "Store name", store_email: "Support email", store_phone: "Phone", store_address: "Address", currency_symbol: "Currency symbol", tax_rate: "Tax rate (%)", free_shipping_threshold: "Free shipping above (₹)", standard_shipping: "Standard shipping (₹)", express_shipping: "Express shipping (₹)", low_stock_default: "Default low-stock threshold", hero_title: "Homepage headline", hero_subtitle: "Homepage sub-headline" };
const TOGGLES = { cod_enabled: "Cash on delivery", razorpay_enabled: "Online payments (Razorpay)", email_notifications: "E-mail notifications", maintenance_mode: "Maintenance mode (blocks new orders)" };

export function SettingsAdmin() {
  const toast = useToast();
  const { data, reload } = useFetch("/admin/settings");
  const [f, setF] = useState(null);
  if (!data) return <Spinner />;
  const form = f || data;
  const save = async (e) => { e.preventDefault(); try { await api.put("/admin/settings", form); toast("Settings saved"); setF(null); reload(); } catch (er) { toast(errMsg(er), "error"); } };
  return (
    <>
      <h2>Settings</h2>
      <form className="card pad" onSubmit={save} style={{ maxWidth: 760 }}>
        <h3>Store, shipping &amp; tax</h3>
        <div className="form-grid">{Object.entries(LABELS).map(([k, l]) => <Field key={k} label={l}><input value={form[k] ?? ""} onChange={(e) => setF({ ...form, [k]: e.target.value })} /></Field>)}</div>
        <h3>Payments, notifications &amp; website</h3>
        {Object.entries(TOGGLES).map(([k, l]) => <label key={k} className="check"><input type="checkbox" checked={form[k] === "true"} onChange={(e) => setF({ ...form, [k]: e.target.checked ? "true" : "false" })} />{l}</label>)}
        <p className="muted">Razorpay keys are configured on the server with environment variables (never in the browser).</p>
        <button className="btn primary">Save settings</button>
      </form>
    </>
  );
}

export function AuditLogs() {
  const [page, setPage] = useState(1);
  const { data, loading } = useFetch("/admin/audit-logs", { page, per_page: 20 });
  return (
    <>
      <h2>Audit log</h2>
      {loading ? <Spinner /> : <div className="card table-wrap"><table className="tbl"><thead><tr><th>When</th><th>User</th><th>Action</th><th>Entity</th><th>Details</th><th>IP</th></tr></thead><tbody>
        {data.items.map((a) => <tr key={a.id}><td>{dateTime(a.created_at)}</td><td>{a.user || "-"}</td><td><b>{a.action}</b></td><td>{a.entity} {a.entity_id}</td><td>{a.details}</td><td>{a.ip}</td></tr>)}</tbody></table></div>}
      {data && <Pagination page={data.page} pages={data.pages} onChange={setPage} />}
    </>
  );
}

export function StaffAdmin() {
  const toast = useToast();
  const { data, reload } = useFetch("/admin/staff");
  const [f, setF] = useState({ name: "", email: "", password: "" });
  const add = async (e) => { e.preventDefault(); try { await api.post("/admin/staff", f); toast("Store admin created"); setF({ name: "", email: "", password: "" }); reload(); } catch (er) { toast(errMsg(er), "error"); } };
  return (
    <>
      <h2>Staff accounts</h2>
      <div className="two-col"><div className="card pad"><table className="tbl"><tbody>{data?.map((u) => <tr key={u.id}><td>{u.name}<br /><small className="muted">{u.email}</small></td><td><StatusBadge status={u.role === "super_admin" ? "approved" : "confirmed"} /> {u.role.replace("_", " ")}</td></tr>)}</tbody></table></div>
        <form className="card pad" onSubmit={add}><h3>Add store admin</h3>
          <Field label="Name"><input required value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
          <Field label="Email"><input type="email" required value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} /></Field>
          <Field label="Password"><input type="password" required minLength={8} value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} /></Field><button className="btn primary">Create</button></form></div>
    </>
  );
}

export function PromotionsAdmin() {
  const toast = useToast();
  const [f, setF] = useState({ title: "", message: "", audience: "customers" });
  const [busy, setBusy] = useState(false);
  const { data: hist, reload } = useFetch("/admin/promotions", { per_page: 10 });
  const { data: subs, reload: reloadSubs } = useFetch("/admin/subscribers", { per_page: 10 });
  const send = async (e) => {
    e.preventDefault();
    if (!window.confirm("Send this promotion now?")) return;
    setBusy(true);
    try { const { data } = await api.post("/admin/promotions", f); toast(`Sent: ${data.notifications_sent} notifications, ${data.emails_sent} e-mails`); setF({ ...f, title: "", message: "" }); reload(); }
    catch (er) { toast(errMsg(er), "error"); } finally { setBusy(false); }
  };
  const unsub = async (id) => { try { await api.delete(`/admin/subscribers/${id}`); reloadSubs(); } catch (er) { toast(errMsg(er), "error"); } };
  return (
    <>
      <h2>Promotions &amp; newsletter</h2>
      <div className="two-col">
        <form className="card pad" onSubmit={send}><h3>New promotional notification</h3>
          <p className="muted">Customers who opted out of promotions are skipped. E-mails are only delivered when SMTP is configured on the server.</p>
          <Field label="Title"><input required maxLength={150} value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} /></Field>
          <Field label="Message"><textarea required maxLength={500} value={f.message} onChange={(e) => setF({ ...f, message: e.target.value })} placeholder="Use code SAVE25 for 25% off this weekend!" /></Field>
          <Field label="Audience"><select value={f.audience} onChange={(e) => setF({ ...f, audience: e.target.value })}><option value="customers">Customers (in-app + e-mail)</option><option value="subscribers">Newsletter subscribers (e-mail)</option><option value="both">Both</option></select></Field>
          <button className="btn primary" disabled={busy}>{busy ? "Sending…" : "Send promotion"}</button></form>
        <div className="card pad"><h3>Newsletter subscribers {subs && <small className="muted">({subs.total})</small>}</h3>
          {subs?.items.length ? <table className="tbl"><tbody>{subs.items.map((s) => <tr key={s.id}><td>{s.email}<br /><small className="muted">{dateStr(s.created_at)}</small></td><td className="right"><button className="btn sm danger" onClick={() => unsub(s.id)}>Remove</button></td></tr>)}</tbody></table> : <p className="muted">No subscribers yet.</p>}</div>
      </div>
      <div className="card pad" style={{ marginTop: "1rem" }}><h3>History</h3>
        {hist?.items.length ? <div className="table-wrap"><table className="tbl"><thead><tr><th>Sent</th><th>Title</th><th>Audience</th><th>Notifications</th><th>E-mails</th></tr></thead><tbody>{hist.items.map((p) => <tr key={p.id}><td>{dateTime(p.created_at)}</td><td><b>{p.title}</b><br /><small className="muted">{p.message}</small></td><td>{p.audience}</td><td>{p.notifications_sent}</td><td>{p.emails_sent}</td></tr>)}</tbody></table></div> : <p className="muted">No promotions sent yet.</p>}</div>
    </>
  );
}
