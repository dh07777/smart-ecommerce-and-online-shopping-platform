import { useState } from "react";
import api, { dateStr, dateTime, downloadFile, errMsg, money } from "../api";
import { Empty, Field, Modal, Pagination, Spinner, StatusBadge, useFetch } from "../components.jsx";
import { useToast } from "../context.jsx";

const NEXT = { pending: ["confirmed", "cancelled"], confirmed: ["processing", "cancelled"], processing: ["shipped", "cancelled"], shipped: ["out_for_delivery", "delivered"], out_for_delivery: ["delivered"], delivered: [], cancelled: [], returned: [] };

function OrderModal({ id, onClose, onChanged }) {
  const toast = useToast();
  const { data: o, reload } = useFetch(`/admin/orders/${id}`);
  const [f, setF] = useState({ carrier: "", tracking_number: "", note: "" });
  if (!o) return <Modal title="Order" onClose={onClose}><Spinner /></Modal>;
  const move = async (status) => {
    try { await api.patch(`/admin/orders/${id}/status`, { status, ...f }); toast(`Order marked ${status.replace(/_/g, " ")}`); reload(); onChanged(); }
    catch (e) { toast(errMsg(e), "error"); }
  };
  const a = o.shipping_address;
  return (
    <Modal title={`Order ${o.order_number}`} wide onClose={onClose}>
      <div className="row between wrap"><span><StatusBadge status={o.status} /> <StatusBadge status={o.payment_status} /></span><small className="muted">{dateTime(o.created_at)} · {o.customer.name} ({o.customer.email})</small></div>
      <table className="tbl"><tbody>{o.items.map((i) => <tr key={i.id}><td>{i.name} <small className="muted">{[i.size, i.color].filter(Boolean).join("/")}</small></td><td>× {i.quantity}</td><td className="right">{money(i.line_total)}</td></tr>)}
        <tr><td colSpan="2">Subtotal / Discount / Tax / Shipping</td><td className="right">{money(o.subtotal)} / −{money(o.discount)} / {money(o.tax)} / {money(o.shipping_cost)}</td></tr>
        <tr><td colSpan="2"><b>Total ({o.payment_method})</b></td><td className="right"><b>{money(o.total)}</b></td></tr></tbody></table>
      <button className="btn sm" onClick={() => downloadFile(`/orders/${o.id}/invoice`, `invoice-${o.order_number}.pdf`).catch((e) => toast(errMsg(e), "error"))}>Download invoice</button>
      <p className="muted">Ship to: {a.full_name}, {a.line1}, {a.city}, {a.state} {a.postal_code} · {a.phone}</p>
      {o.payment?.transactions.length > 0 && <><h4>Transactions</h4>{o.payment.transactions.map((t) => <div key={t.id} className="muted">{dateTime(t.created_at)} · {t.kind} · {money(t.amount)} · {t.status} {t.reference && `· ${t.reference}`}</div>)}</>}
      {NEXT[o.status].length > 0 && <>
        <h4>Update status</h4>
        <div className="form-grid"><Field label="Carrier"><input value={f.carrier} onChange={(e) => setF({ ...f, carrier: e.target.value })} /></Field><Field label="Tracking number"><input value={f.tracking_number} onChange={(e) => setF({ ...f, tracking_number: e.target.value })} /></Field></div>
        <Field label="Note (shown to customer)"><input value={f.note} onChange={(e) => setF({ ...f, note: e.target.value })} /></Field>
        <div className="row gap-s wrap">{NEXT[o.status].map((s) => <button key={s} className={`btn ${s === "cancelled" ? "danger" : "primary"}`} onClick={() => move(s)}>Mark {s.replace(/_/g, " ")}</button>)}</div></>}
      <h4>Tracking history</h4>
      <ul className="timeline">{[...(o.tracking?.events || [])].reverse().map((e, i) => <li key={i}><b>{e.status.replace(/_/g, " ")}</b> <small className="muted">{dateTime(e.at)}</small> {e.note}</li>)}</ul>
    </Modal>
  );
}

export function OrdersAdmin() {
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState("");
  const [q, setQ] = useState("");
  const [term, setTerm] = useState("");
  const [open, setOpen] = useState(null);
  const { data, loading, reload } = useFetch("/admin/orders", { page, per_page: 12, status, q: term });
  return (
    <>
      <div className="row between wrap gap"><h2>Orders</h2>
        <div className="row gap-s wrap"><select value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }}><option value="">All statuses</option>{Object.keys(NEXT).map((s) => <option key={s} value={s}>{s.replace(/_/g, " ")}</option>)}</select>
          <form onSubmit={(e) => { e.preventDefault(); setPage(1); setTerm(q); }}><input placeholder="Order #, name, email" value={q} onChange={(e) => setQ(e.target.value)} /></form></div></div>
      {loading ? <Spinner /> : !data.items.length ? <Empty title="No orders match" /> : <div className="card table-wrap"><table className="tbl"><thead><tr><th>Order</th><th>Customer</th><th>Date</th><th>Payment</th><th>Status</th><th className="right">Total</th><th /></tr></thead><tbody>
        {data.items.map((o) => <tr key={o.id}><td>{o.order_number}</td><td>{o.customer.name}</td><td>{dateStr(o.created_at)}</td><td>{o.payment_method} <StatusBadge status={o.payment_status} /></td><td><StatusBadge status={o.status} /></td><td className="right">{money(o.total)}</td><td><button className="btn sm" onClick={() => setOpen(o.id)}>Manage</button></td></tr>)}</tbody></table></div>}
      {data && <Pagination page={data.page} pages={data.pages} onChange={setPage} />}
      {open && <OrderModal id={open} onClose={() => setOpen(null)} onChanged={reload} />}
    </>
  );
}

export function RefundsAdmin() {
  const toast = useToast();
  const [status, setStatus] = useState("");
  const { data, loading, reload } = useFetch("/admin/refunds", { status, per_page: 50 });
  const set = async (r, s) => { try { await api.patch(`/admin/refunds/${r.id}`, { status: s }); toast(`Refund ${s}`); reload(); } catch (e) { toast(errMsg(e), "error"); } };
  return (
    <>
      <div className="row between"><h2>Refunds &amp; returns</h2><select value={status} onChange={(e) => setStatus(e.target.value)}><option value="">All</option>{["pending", "approved", "processed", "rejected"].map((s) => <option key={s}>{s}</option>)}</select></div>
      <p className="muted">“Processed” records the refund in ShopSphere. Issue the actual money transfer from your Razorpay dashboard.</p>
      {loading ? <Spinner /> : !data.items.length ? <Empty title="No refunds" /> : <div className="card table-wrap"><table className="tbl"><thead><tr><th>Order</th><th>Type</th><th>Reason</th><th>Amount</th><th>Status</th><th /></tr></thead><tbody>
        {data.items.map((r) => <tr key={r.id}><td>{r.order_number}</td><td>{r.kind}</td><td>{r.reason}</td><td>{money(r.amount)}</td><td><StatusBadge status={r.status} /></td>
          <td className="right">{r.status === "pending" && <><button className="btn sm" onClick={() => set(r, "approved")}>Approve</button> {r.kind === "return" && <button className="btn sm danger" onClick={() => set(r, "rejected")}>Reject</button>} </>}{["pending", "approved"].includes(r.status) && <button className="btn sm primary" onClick={() => set(r, "processed")}>Mark processed</button>}</td></tr>)}</tbody></table></div>}
    </>
  );
}
