import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import api, { errMsg, money } from "../api";
import { Empty, Field, Img, Modal, Spinner, useFetch } from "../components.jsx";
import { useAuth, useCart, useToast } from "../context.jsx";
import { CouponBox, Totals } from "./CartPage.jsx";

const blank = { label: "Home", full_name: "", phone: "", line1: "", line2: "", city: "", state: "", postal_code: "", country: "India" };

export function AddressForm({ value, onChange }) {
  const set = (k) => (e) => onChange({ ...value, [k]: e.target.value });
  return (
    <div className="form-grid">
      <Field label="Full name"><input value={value.full_name} onChange={set("full_name")} required /></Field>
      <Field label="Phone"><input value={value.phone} onChange={set("phone")} required /></Field>
      <div className="full"><Field label="Address line 1"><input value={value.line1} onChange={set("line1")} required /></Field></div>
      <div className="full"><Field label="Address line 2"><input value={value.line2 || ""} onChange={set("line2")} /></Field></div>
      <Field label="City"><input value={value.city} onChange={set("city")} required /></Field>
      <Field label="State"><input value={value.state} onChange={set("state")} required /></Field>
      <Field label="PIN / Postal code"><input value={value.postal_code} onChange={set("postal_code")} required /></Field>
      <Field label="Label"><select value={value.label} onChange={set("label")}><option>Home</option><option>Work</option><option>Other</option></select></Field>
    </div>
  );
}

function loadRazorpay() {
  return new Promise((res, rej) => {
    if (window.Razorpay) return res();
    const s = document.createElement("script");
    s.src = "https://checkout.razorpay.com/v1/checkout.js";
    s.onload = res; s.onerror = () => rej(new Error("Could not load Razorpay checkout"));
    document.body.appendChild(s);
  });
}

export default function Checkout() {
  const { user } = useAuth();
  const { cart, reload } = useCart();
  const toast = useToast();
  const nav = useNavigate();
  const { data: addresses } = useFetch("/auth/addresses");
  const { data: pay } = useFetch("/payments/config");
  const [sel, setSel] = useState(null);
  const [addr, setAddr] = useState({ ...blank, full_name: user?.name || "", phone: user?.phone || "" });
  const [sameBilling, setSame] = useState(true);
  const [bill, setBill] = useState(blank);
  const [delivery, setDelivery] = useState("standard");
  const [method, setMethod] = useState("cod");
  const [totals, setTotals] = useState(null);
  const [busy, setBusy] = useState(false);
  const [mock, setMock] = useState(null);

  useEffect(() => { if (addresses?.length) { const d = addresses.find((a) => a.is_default) || addresses[0]; setSel(d.id); } }, [addresses]);
  useEffect(() => { api.get("/cart", { params: { delivery } }).then((r) => setTotals(r.data)).catch(() => {}); }, [delivery, cart?.subtotal, cart?.coupon_code]);
  useEffect(() => { if (pay && !pay.cod_enabled && pay.online_enabled) setMethod("razorpay"); }, [pay]);

  if (!cart || !totals) return <Spinner />;
  if (!cart.items.length) return <Empty title="Your cart is empty" action={<Link to="/shop" className="btn primary">Shop now</Link>} />;
  const useSaved = addresses?.length > 0 && sel !== "new";
  const finish = async (order) => { await reload(); nav(`/orders/${order.id}?placed=1`); };

  const place = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const shipping_address = useSaved ? addresses.find((a) => a.id === sel) : addr;
      const { data } = await api.post("/orders/checkout", { shipping_address, billing_address: sameBilling ? null : bill, billing_same_as_shipping: sameBilling, delivery_option: delivery, payment_method: method });
      if (method === "cod") { toast("Order placed!"); return finish(data.order); }
      const g = data.gateway;
      if (g.mock) { setMock({ order: data.order, gateway: g }); return; }
      await loadRazorpay();
      new window.Razorpay({
        key: g.key_id, amount: g.amount, currency: g.currency, order_id: g.provider_order_id, name: "ShopSphere",
        prefill: { name: user.name, email: user.email, contact: user.phone },
        handler: async (r) => {
          try { await api.post("/payments/verify", { order_id: data.order.id, ...r }); toast("Payment successful"); } catch (er) { toast(errMsg(er), "error"); }
          finish(data.order);
        },
        modal: { ondismiss: async () => { await api.post("/payments/failure", { order_id: data.order.id, reason: "Checkout closed" }).catch(() => {}); toast("Payment not completed. You can retry from your orders.", "error"); finish(data.order); } },
      }).open();
    } catch (er) { toast(errMsg(er), "error"); } finally { setBusy(false); }
  };

  const simulate = async (outcome) => {
    try { await api.post("/payments/sandbox/simulate", { order_id: mock.order.id, outcome }); toast(outcome === "success" ? "Sandbox payment successful" : "Sandbox payment failed", outcome === "success" ? "success" : "error"); }
    catch (er) { toast(errMsg(er), "error"); }
    const o = mock.order; setMock(null); finish(o);
  };

  return (
    <form className="cart-layout" onSubmit={place}>
      <div>
        <div className="card pad" style={{ marginBottom: "1rem" }}>
          <h3>1. Shipping address</h3>
          {addresses?.map((a) => (
            <label key={a.id} className={`radio-card ${sel === a.id ? "on" : ""}`}><input type="radio" checked={sel === a.id} onChange={() => setSel(a.id)} />
              <div><b>{a.full_name}</b> <small className="muted">({a.label})</small><br />{a.line1}, {a.city}, {a.state} {a.postal_code}<br /><small>{a.phone}</small></div></label>
          ))}
          {addresses?.length > 0 && <label className={`radio-card ${sel === "new" ? "on" : ""}`}><input type="radio" checked={sel === "new"} onChange={() => setSel("new")} /><b>Use a new address</b></label>}
          {!useSaved && <AddressForm value={addr} onChange={setAddr} />}
          <label className="check"><input type="checkbox" checked={sameBilling} onChange={(e) => setSame(e.target.checked)} />Billing address same as shipping</label>
          {!sameBilling && <><h4>Billing address</h4><AddressForm value={bill} onChange={setBill} /></>}
        </div>
        <div className="card pad" style={{ marginBottom: "1rem" }}>
          <h3>2. Delivery</h3>
          {[["standard", "Standard (3-6 days)", totals.subtotal >= 999 ? "FREE" : "₹49"], ["express", "Express (1-2 days)", "₹149"]].map(([v, t, p]) => (
            <label key={v} className={`radio-card ${delivery === v ? "on" : ""}`}><input type="radio" checked={delivery === v} onChange={() => setDelivery(v)} /><div className="row between" style={{ flex: 1 }}><b>{t}</b><span>{p}</span></div></label>
          ))}
        </div>
        <div className="card pad">
          <h3>3. Payment</h3>
          {pay?.cod_enabled && <label className={`radio-card ${method === "cod" ? "on" : ""}`}><input type="radio" checked={method === "cod"} onChange={() => setMethod("cod")} /><div><b>Cash on Delivery</b><br /><small className="muted">Pay when your order arrives.</small></div></label>}
          {pay?.online_enabled && <label className={`radio-card ${method === "razorpay" ? "on" : ""}`}><input type="radio" checked={method === "razorpay"} onChange={() => setMethod("razorpay")} /><div><b>Pay online (Razorpay)</b> {pay.mode !== "live" && <span className="badge b-pending">{pay.mock ? "Local sandbox" : "Test mode"}</span>}<br /><small className="muted">UPI, cards, netbanking. We never see or store your card details.</small></div></label>}
        </div>
      </div>
      <div className="card pad" style={{ alignSelf: "start" }}>
        <h3>Order summary</h3>
        {cart.items.map((i) => <div key={i.id} className="row gap-s" style={{ marginBottom: ".5rem" }}><Img src={i.image} alt="" style={{ width: 44, height: 44, borderRadius: 8, objectFit: "cover" }} /><small style={{ flex: 1 }}>{i.name} × {i.quantity}</small><small>{money(i.line_total)}</small></div>)}
        <CouponBox />
        <Totals cart={totals} />
        <button className="btn primary block" style={{ marginTop: "1rem" }} disabled={busy}>{busy ? "Placing order…" : method === "cod" ? "Place order" : "Pay " + money(totals.total)}</button>
      </div>
      {mock && (
        <Modal title="Sandbox payment (mock Razorpay)" onClose={() => simulate("failure")}>
          <p>This is a local test gateway. No real money is used. Amount: <b>{money(mock.order.total)}</b></p>
          <p className="muted">Order id: <code>{mock.gateway.provider_order_id}</code></p>
          <div className="row gap"><button type="button" className="btn primary" onClick={() => simulate("success")}>Simulate successful payment</button><button type="button" className="btn danger" onClick={() => simulate("failure")}>Simulate failure</button></div>
        </Modal>
      )}
    </form>
  );
}
