import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { CheckCircle2, Package } from "lucide-react";
import api, { dateStr, dateTime, downloadFile, errMsg, imgUrl, money } from "../api";
import { Empty, Field, Img, Modal, Pagination, Spinner, StatusBadge, useFetch } from "../components.jsx";
import { useAuth, useCart, useToast } from "../context.jsx";
import { AddressForm } from "./Checkout.jsx";

export function Orders() {
  const [page, setPage] = useState(1);
  const { data, loading } = useFetch("/orders", { page, per_page: 8 });
  if (loading) return <Spinner />;
  if (!data.items.length) return <Empty icon={<Package size={44} />} title="No orders yet" action={<Link className="btn primary" to="/shop">Start shopping</Link>} />;
  return (
    <>
      <h2>My orders</h2>
      {data.items.map((o) => (
        <Link to={`/orders/${o.id}`} key={o.id} className="card pad" style={{ display: "block", marginBottom: ".8rem" }}>
          <div className="row between wrap gap-s"><b>{o.order_number}</b><span><StatusBadge status={o.status} /> <StatusBadge status={o.payment_status} /></span></div>
          <div className="row gap-s" style={{ margin: ".6rem 0" }}>{o.items.slice(0, 4).map((i) => <Img key={i.id} src={i.image} alt={i.name} style={{ width: 52, height: 52, borderRadius: 8, objectFit: "cover" }} />)}</div>
          <div className="row between"><small className="muted">{dateStr(o.created_at)} · {o.item_count} items</small><b>{money(o.total)}</b></div>
        </Link>
      ))}
      <Pagination page={data.page} pages={data.pages} onChange={setPage} />
    </>
  );
}

export function OrderDetail() {
  const { id } = useParams();
  const [sp] = useSearchParams();
  const toast = useToast();
  const nav = useNavigate();
  const { addToCart } = useCart();
  const { data: o, loading, reload } = useFetch(`/orders/${id}`);
  const [reason, setReason] = useState("");
  const [modal, setModal] = useState(null);
  if (loading) return <Spinner />;
  if (!o) return <Empty title="Order not found" />;
  const act = async (fn, msg) => { try { await fn(); toast(msg); setModal(null); setReason(""); reload(); } catch (e) { toast(errMsg(e), "error"); } };
  const retry = async () => {
    try {
      const { data } = await api.post(`/orders/${o.id}/pay`);
      if (data.gateway.mock) { await api.post("/payments/sandbox/simulate", { order_id: o.id, outcome: "success" }); toast("Sandbox payment successful"); reload(); }
      else toast("Online retry requires the Razorpay checkout: please place the order again from the cart.", "info");
    } catch (e) { toast(errMsg(e), "error"); }
  };
  const buyAgain = async () => { for (const i of o.items) await addToCart({ variant_id: i.variant_id, quantity: i.quantity }); nav("/cart"); };
  const canCancel = ["pending", "confirmed", "processing"].includes(o.status);
  const canRefund = o.status === "delivered" && !o.refunds.some((r) => ["pending", "approved", "processed"].includes(r.status));
  const a = o.shipping_address;
  return (
    <>
      {sp.get("placed") && <div className="card pad row gap" style={{ marginBottom: "1rem", borderColor: "var(--ok)" }}><CheckCircle2 color="var(--ok)" size={34} /><div><h3 style={{ margin: 0 }}>Thank you! Your order is confirmed.</h3><small className="muted">A confirmation has been added to your notifications.</small></div></div>}
      <div className="row between wrap gap"><h2>Order {o.order_number}</h2><div><StatusBadge status={o.status} /> <StatusBadge status={o.payment_status} /></div></div>
      <div className="cart-layout">
        <div>
          <div className="card" style={{ marginBottom: "1rem" }}>{o.items.map((i) => (
            <div className="line" key={i.id}><Img src={i.image} alt="" /><div><Link to={`/product/${i.slug}`}><b>{i.name}</b></Link><br /><small className="muted">{[i.size, i.color].filter(Boolean).join(" · ")} · Qty {i.quantity}</small><div><b>{money(i.line_total)}</b></div></div></div>))}</div>
          <div className="card pad">
            <h3>Tracking</h3>
            {o.tracking?.tracking_number && <p>{o.tracking.carrier}: <b>{o.tracking.tracking_number}</b></p>}
            <ul className="timeline">{[...(o.tracking?.events || [])].reverse().map((e, i) => <li key={i}><b style={{ textTransform: "capitalize" }}>{e.status.replace(/_/g, " ")}</b> <small className="muted">{dateTime(e.at)}</small>{e.note && <div className="muted">{e.note}</div>}</li>)}</ul>
          </div>
        </div>
        <div>
          <div className="card pad" style={{ marginBottom: "1rem" }}>
            <h3>Summary</h3>
            <div className="sum-row"><span>Subtotal</span><span>{money(o.subtotal)}</span></div>
            {o.discount > 0 && <div className="sum-row green"><span>Discount</span><span>−{money(o.discount)}</span></div>}
            <div className="sum-row"><span>Tax</span><span>{money(o.tax)}</span></div><div className="sum-row"><span>Shipping</span><span>{money(o.shipping_cost)}</span></div>
            <div className="sum-row total"><span>Total</span><span>{money(o.total)}</span></div>
            <p className="muted">Payment: {o.payment_method === "cod" ? "Cash on delivery" : "Online (Razorpay)"}</p>
            {o.refunds.map((r) => <p key={r.id}>Refund {money(r.amount)}: <StatusBadge status={r.status} /></p>)}
          </div>
          <div className="card pad" style={{ marginBottom: "1rem" }}><h3>Delivery address</h3><p style={{ margin: 0 }}>{a.full_name}<br />{a.line1}{a.line2 && `, ${a.line2}`}<br />{a.city}, {a.state} {a.postal_code}<br />{a.phone}</p></div>
          <div className="row gap-s wrap">
            <button className="btn" onClick={() => downloadFile(`/orders/${o.id}/invoice`, `invoice-${o.order_number}.pdf`).catch((e) => toast(errMsg(e), "error"))}>Download invoice</button>
            {o.payment_method === "razorpay" && ["failed", "pending"].includes(o.payment_status) && ["pending", "confirmed"].includes(o.status) && <button className="btn primary" onClick={retry}>Pay now</button>}
            <button className="btn" onClick={buyAgain}>Buy again</button>
            {canCancel && <button className="btn danger" onClick={() => setModal("cancel")}>Cancel order</button>}
            {canRefund && <button className="btn" onClick={() => setModal("refund")}>Request refund</button>}
          </div>
        </div>
      </div>
      {modal && <Modal title={modal === "cancel" ? "Cancel this order?" : "Request a refund"} onClose={() => setModal(null)}>
        <Field label="Reason"><textarea value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Tell us why" /></Field>
        <button className="btn primary" onClick={() => act(() => modal === "cancel" ? api.post(`/orders/${o.id}/cancel`, { reason }) : api.post(`/orders/${o.id}/refund-request`, { reason }), modal === "cancel" ? "Order cancelled" : "Refund requested")}>Confirm</button>
      </Modal>}
    </>
  );
}

function Profile() {
  const { user, setUser } = useAuth();
  const toast = useToast();
  const [f, setF] = useState({ name: user.name, phone: user.phone || "", promo_opt_in: user.promo_opt_in !== false });
  const file = useRef();
  const save = async (e) => { e.preventDefault(); try { const { data } = await api.put("/auth/me", f); setUser(data); toast("Profile updated"); } catch (er) { toast(errMsg(er), "error"); } };
  const upload = async (e) => { const fd = new FormData(); fd.append("file", e.target.files[0]); try { const { data } = await api.post("/auth/avatar", fd); setUser(data); toast("Picture updated"); } catch (er) { toast(errMsg(er), "error"); } };
  return (
    <form className="card pad" onSubmit={save}>
      <div className="row gap" style={{ marginBottom: "1rem" }}>
        <img src={user.avatar ? imgUrl(user.avatar) : "/placeholder.svg"} alt="" style={{ width: 80, height: 80, borderRadius: "50%", objectFit: "cover" }} />
        <div><button type="button" className="btn sm" onClick={() => file.current.click()}>Change picture</button><input ref={file} type="file" accept="image/png,image/jpeg,image/webp" hidden onChange={upload} /><div className="muted">{user.email} · {user.role.replace("_", " ")}</div></div>
      </div>
      <div className="form-grid"><Field label="Name"><input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} required /></Field><Field label="Phone"><input value={f.phone} onChange={(e) => setF({ ...f, phone: e.target.value })} /></Field></div>
      <label className="check"><input type="checkbox" checked={f.promo_opt_in} onChange={(e) => setF({ ...f, promo_opt_in: e.target.checked })} />Send me promotional offers and notifications</label>
      <button className="btn primary" style={{ marginTop: ".8rem" }}>Save changes</button>
    </form>
  );
}

function Addresses() {
  const toast = useToast();
  const { data, reload } = useFetch("/auth/addresses");
  const [edit, setEdit] = useState(null);
  const save = async (e) => {
    e.preventDefault();
    try { edit.id ? await api.put(`/auth/addresses/${edit.id}`, edit) : await api.post("/auth/addresses", edit); toast("Address saved"); setEdit(null); reload(); } catch (er) { toast(errMsg(er), "error"); }
  };
  const del = async (id) => { try { await api.delete(`/auth/addresses/${id}`); reload(); } catch (er) { toast(errMsg(er), "error"); } };
  return (
    <div>
      <div className="row between"><h3>Saved addresses</h3><button className="btn primary sm" onClick={() => setEdit({ label: "Home", full_name: "", phone: "", line1: "", line2: "", city: "", state: "", postal_code: "", country: "India" })}>Add address</button></div>
      {data?.length === 0 && <Empty title="No saved addresses" />}
      {data?.map((a) => <div key={a.id} className="card pad" style={{ marginBottom: ".6rem" }}><div className="row between"><b>{a.full_name} <small className="muted">({a.label})</small> {a.is_default && <span className="badge b-ok">Default</span>}</b>
        <span><button className="btn sm" onClick={() => setEdit(a)}>Edit</button> <button className="btn sm danger" onClick={() => del(a.id)}>Delete</button></span></div>
        <div className="muted">{a.line1}, {a.city}, {a.state} {a.postal_code} · {a.phone}</div></div>)}
      {edit && <Modal title={edit.id ? "Edit address" : "New address"} onClose={() => setEdit(null)} wide><form onSubmit={save}><AddressForm value={edit} onChange={setEdit} />
        <label className="check"><input type="checkbox" checked={!!edit.is_default} onChange={(e) => setEdit({ ...edit, is_default: e.target.checked })} />Make default</label><button className="btn primary">Save</button></form></Modal>}
    </div>
  );
}

function Password() {
  const toast = useToast();
  const { logout } = useAuth();
  const nav = useNavigate();
  const [f, setF] = useState({ current_password: "", new_password: "" });
  const [del, setDel] = useState("");
  const change = async (e) => { e.preventDefault(); try { await api.post("/auth/change-password", f); toast("Password changed"); setF({ current_password: "", new_password: "" }); } catch (er) { toast(errMsg(er), "error"); } };
  const deactivate = async () => { if (!window.confirm("Deactivate your account? You will be logged out.")) return; try { await api.delete("/auth/me", { data: { password: del } }); await logout(); nav("/"); } catch (er) { toast(errMsg(er), "error"); } };
  return (
    <div>
      <form className="card pad" onSubmit={change} style={{ marginBottom: "1rem" }}><h3>Change password</h3>
        <Field label="Current password"><input type="password" value={f.current_password} onChange={(e) => setF({ ...f, current_password: e.target.value })} required /></Field>
        <Field label="New password" hint="At least 8 characters with letters and numbers"><input type="password" value={f.new_password} onChange={(e) => setF({ ...f, new_password: e.target.value })} required /></Field>
        <button className="btn primary">Update password</button></form>
      <div className="card pad"><h3>Account settings</h3><p className="muted">Deactivating hides your account. Contact support to restore it.</p>
        <Field label="Confirm with password"><input type="password" value={del} onChange={(e) => setDel(e.target.value)} /></Field><button className="btn danger" onClick={deactivate}>Deactivate account</button></div>
    </div>
  );
}

function MyReviews() {
  const { data, loading, reload } = useFetch("/reviews/mine");
  const toast = useToast();
  if (loading) return <Spinner />;
  if (!data.length) return <Empty title="You haven't written any reviews" />;
  const del = async (id) => { try { await api.delete(`/reviews/${id}`); toast("Review deleted"); reload(); } catch (e) { toast(errMsg(e), "error"); } };
  return data.map((r) => <div key={r.id} className="card pad" style={{ marginBottom: ".6rem" }}><div className="row between"><Link to={`/product/${r.product.slug}`}><b>{r.product.name}</b></Link><StatusBadge status={r.status} /></div><div>{"★".repeat(r.rating)}</div><p>{r.body}</p><button className="btn sm danger" onClick={() => del(r.id)}>Delete</button></div>);
}

export function Account() {
  const [tab, setTab] = useState("profile");
  const tabs = [["profile", "Personal info"], ["addresses", "Addresses"], ["reviews", "My reviews"], ["security", "Password & settings"]];
  return (
    <div className="acc-layout">
      <nav className="card pad side-nav">{tabs.map(([k, t]) => <button key={k} className={tab === k ? "on" : ""} onClick={() => setTab(k)}>{t}</button>)}<Link to="/orders">Order history</Link><Link to="/wishlist">Wishlist</Link></nav>
      <div>{tab === "profile" && <Profile />}{tab === "addresses" && <Addresses />}{tab === "reviews" && <MyReviews />}{tab === "security" && <Password />}</div>
    </div>
  );
}
