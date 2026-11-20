import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Heart, ShoppingBag, Trash2 } from "lucide-react";
import api, { errMsg, money } from "../api";
import { Empty, Img, ProductGrid, Spinner, useFetch } from "../components.jsx";
import { useAuth, useCart, useToast } from "../context.jsx";

export function Totals({ cart }) {
  return (
    <>
      <div className="sum-row"><span>Subtotal</span><span>{money(cart.subtotal)}</span></div>
      {cart.discount > 0 && <div className="sum-row green"><span>Discount {cart.coupon_code && `(${cart.coupon_code})`}</span><span>−{money(cart.discount)}</span></div>}
      <div className="sum-row"><span>Tax</span><span>{money(cart.tax)}</span></div>
      <div className="sum-row"><span>Shipping</span><span>{cart.shipping ? money(cart.shipping) : "FREE"}</span></div>
      <div className="sum-row total"><span>Total</span><span>{money(cart.total)}</span></div>
    </>
  );
}

export function CouponBox() {
  const { cart, applyCoupon, removeCoupon } = useCart();
  const { user } = useAuth();
  const [code, setCode] = useState("");
  if (!user) return <small className="muted" style={{ display: "block", margin: ".6rem 0" }}>Log in at checkout to apply a coupon.</small>;
  if (cart?.coupon_code) return <div className="row between" style={{ margin: ".8rem 0" }}><span className="badge b-ok">{cart.coupon_code} applied</span><button className="btn sm" onClick={removeCoupon}>Remove</button></div>;
  return (
    <form className="row gap-s" style={{ margin: ".8rem 0" }} onSubmit={async (e) => { e.preventDefault(); if (code.trim()) { await applyCoupon(code.trim()); setCode(""); } }}>
      <input placeholder="Coupon code" value={code} onChange={(e) => setCode(e.target.value)} aria-label="Coupon code" /><button className="btn">Apply</button>
    </form>
  );
}

export function CartPage() {
  const { user } = useAuth();
  const { cart, updateQty, removeItem } = useCart();
  const nav = useNavigate();
  if (!cart) return user ? <Spinner /> : <Empty icon={<ShoppingBag size={44} />} title="Your cart is empty" text="Add something you love. Your cart is saved on this device until you log in." action={<Link className="btn primary" to="/shop">Start shopping</Link>} />;
  if (!cart.items.length) return <Empty icon={<ShoppingBag size={44} />} title="Your cart is empty" text="Add something you love." action={<Link className="btn primary" to="/shop">Start shopping</Link>} />;
  return (
    <div className="cart-layout">
      <div className="card">
        {cart.items.map((i) => (
          <div className="line" key={i.id}>
            <Link to={`/product/${i.slug}`}><Img src={i.image} alt={i.name} /></Link>
            <div>
              <div className="row between"><Link to={`/product/${i.slug}`}><b>{i.name}</b></Link><button className="icon-btn" aria-label="Remove" onClick={() => removeItem(i.id)}><Trash2 size={18} /></button></div>
              <small className="muted">{[i.size, i.color].filter(Boolean).join(" · ")}</small>
              {!i.available && <div className="badge b-out">No longer available</div>}
              {i.quantity > i.stock && <div className="badge b-low">Only {i.stock} left</div>}
              <div className="row between" style={{ marginTop: ".5rem" }}>
                <div className="qty"><button onClick={() => i.quantity > 1 && updateQty(i.id, i.quantity - 1)} aria-label="Decrease">−</button><span>{i.quantity}</span><button onClick={() => updateQty(i.id, i.quantity + 1)} aria-label="Increase">+</button></div>
                <b>{money(i.line_total)}</b>
              </div>
            </div>
          </div>
        ))}
      </div>
      <div className="card pad" style={{ alignSelf: "start" }}>
        <h3>Order summary</h3>
        <CouponBox />
        {cart.coupon_error && <p className="badge b-failed">{cart.coupon_error}</p>}
        <Totals cart={cart} />
        <button className="btn primary block" style={{ marginTop: "1rem" }} onClick={() => nav("/checkout")}>{user ? "Proceed to checkout" : "Log in to checkout"}</button>
        {cart.subtotal < 999 && <small className="muted">Add {money(999 - cart.subtotal)} more for free shipping.</small>}
      </div>
    </div>
  );
}

export function WishlistPage() {
  const { reload, toggleWishlist } = useCart();
  const toast = useToast();
  const { data, loading, reload: refetch } = useFetch("/wishlist");
  const move = async (id) => { try { await api.post(`/wishlist/${id}/move-to-cart`); toast("Moved to cart"); await reload(); refetch(); } catch (e) { toast(errMsg(e), "error"); } };
  const remove = async (id) => { await toggleWishlist(id); refetch(); };
  if (loading) return <Spinner />;
  if (!data?.length) return <Empty icon={<Heart size={44} />} title="Your wishlist is empty" text="Tap the heart on products you like." action={<Link className="btn primary" to="/shop">Discover products</Link>} />;
  return (
    <>
      <h2>My wishlist ({data.length})</h2>
      <div className="grid products">
        {data.map((p) => (
          <div key={p.id} className="card">
            <Link to={`/product/${p.slug}`} className="pc-img"><Img src={p.image} alt={p.name} /></Link>
            <div className="pc-body"><Link to={`/product/${p.slug}`} className="pc-title">{p.name}</Link><b>{money(p.price)}</b>
              <button className="btn primary block" disabled={!p.in_stock} onClick={() => move(p.id)}>{p.in_stock ? "Move to cart" : "Out of stock"}</button>
              <button className="btn block" onClick={() => remove(p.id)}>Remove</button></div>
          </div>
        ))}
      </div>
    </>
  );
}
