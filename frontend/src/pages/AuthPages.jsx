import { useState } from "react";
import { Link, Navigate, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import api, { errMsg } from "../api";
import { Field } from "../components.jsx";
import { useAuth, useToast } from "../context.jsx";

function Box({ title, sub, children }) {
  return <div className="card auth-box"><h2>{title}</h2>{sub && <p className="muted">{sub}</p>}{children}</div>;
}

export function Login() {
  const { user, login } = useAuth();
  const toast = useToast();
  const nav = useNavigate();
  const loc = useLocation();
  const [f, setF] = useState({ email: "", password: "" });
  const [busy, setBusy] = useState(false);
  if (user) return <Navigate to={loc.state?.from || "/"} replace />;
  const submit = async (e) => {
    e.preventDefault(); setBusy(true);
    try { const u = await login(f.email, f.password); toast(`Welcome back, ${u.name.split(" ")[0]}!`); nav(loc.state?.from || (["super_admin", "store_admin", "seller"].includes(u.role) ? "/admin" : "/"), { replace: true }); }
    catch (er) { toast(errMsg(er), "error"); } finally { setBusy(false); }
  };
  return (
    <Box title="Log in" sub="Welcome back to ShopSphere">
      <form onSubmit={submit}>
        <Field label="Email"><input type="email" required value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} autoComplete="email" /></Field>
        <Field label="Password"><input type="password" required value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} autoComplete="current-password" /></Field>
        <button className="btn primary block" disabled={busy}>{busy ? "Logging in…" : "Log in"}</button>
      </form>
      <p><Link to="/forgot-password" className="muted">Forgot password?</Link></p>
      <p className="muted">New here? <Link to="/register"><b>Create an account</b></Link></p>
    </Box>
  );
}

export function Register() {
  const { user, register } = useAuth();
  const toast = useToast();
  const nav = useNavigate();
  const [f, setF] = useState({ name: "", email: "", phone: "", password: "" });
  if (user) return <Navigate to="/" replace />;
  const submit = async (e) => { e.preventDefault(); try { await register(f); toast("Account created. Welcome!"); nav("/"); } catch (er) { toast(errMsg(er), "error"); } };
  return (
    <Box title="Create account" sub="Join ShopSphere to start shopping">
      <form onSubmit={submit}>
        <Field label="Full name"><input required value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
        <Field label="Email"><input type="email" required value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} /></Field>
        <Field label="Phone (optional)"><input value={f.phone} onChange={(e) => setF({ ...f, phone: e.target.value })} /></Field>
        <Field label="Password" hint="At least 8 characters with letters and numbers"><input type="password" required minLength={8} value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} /></Field>
        <button className="btn primary block">Sign up</button>
      </form>
      <p className="muted">Already registered? <Link to="/login"><b>Log in</b></Link></p>
    </Box>
  );
}

export function SellerRegister() {
  const { user, registerSeller } = useAuth();
  const toast = useToast();
  const nav = useNavigate();
  const [f, setF] = useState({ name: "", email: "", password: "", store_name: "", description: "" });
  if (user) return <Navigate to="/" replace />;
  const submit = async (e) => { e.preventDefault(); try { await registerSeller(f); toast("Seller account created. Verification is pending."); nav("/admin"); } catch (er) { toast(errMsg(er), "error"); } };
  return (
    <Box title="Sell on ShopSphere" sub="Register your store. Our team verifies new sellers before they can list products.">
      <form onSubmit={submit}>
        <Field label="Your name"><input required value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
        <Field label="Store name"><input required value={f.store_name} onChange={(e) => setF({ ...f, store_name: e.target.value })} /></Field>
        <Field label="About your store"><textarea value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} /></Field>
        <Field label="Email"><input type="email" required value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} /></Field>
        <Field label="Password"><input type="password" required minLength={8} value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} /></Field>
        <button className="btn primary block">Register as seller</button>
      </form>
    </Box>
  );
}

export function ForgotPassword() {
  const toast = useToast();
  const [email, setEmail] = useState("");
  const [res, setRes] = useState(null);
  const submit = async (e) => { e.preventDefault(); try { const { data } = await api.post("/auth/forgot-password", { email }); setRes(data); } catch (er) { toast(errMsg(er), "error"); } };
  return (
    <Box title="Forgot password" sub="Enter your email and we'll send a reset link.">
      <form onSubmit={submit}><Field label="Email"><input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} /></Field><button className="btn primary block">Send reset link</button></form>
      {res && <div style={{ marginTop: "1rem" }}><p className="badge b-ok">{res.message}</p>
        {res.dev_reset_link && <p className="muted">Development mode: no email server configured, use <Link to={res.dev_reset_link.replace(/^https?:\/\/[^/]+/, "")}><b>this reset link</b></Link>.</p>}</div>}
    </Box>
  );
}

export function ResetPassword() {
  const [sp] = useSearchParams();
  const toast = useToast();
  const nav = useNavigate();
  const [password, setPassword] = useState("");
  const submit = async (e) => { e.preventDefault(); try { const { data } = await api.post("/auth/reset-password", { token: sp.get("token"), password }); toast(data.message); nav("/login"); } catch (er) { toast(errMsg(er), "error"); } };
  return (
    <Box title="Set a new password">
      <form onSubmit={submit}><Field label="New password" hint="At least 8 characters with letters and numbers"><input type="password" required minLength={8} value={password} onChange={(e) => setPassword(e.target.value)} /></Field><button className="btn primary block">Reset password</button></form>
    </Box>
  );
}
