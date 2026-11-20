import { useState } from "react";
import { Bell } from "lucide-react";
import api, { dateTime, errMsg } from "../api";
import { Empty, Field, Modal, Spinner, StatusBadge, useFetch } from "../components.jsx";
import { useAuth, useCart, useToast } from "../context.jsx";

function Tickets() {
  const toast = useToast();
  const { data, reload } = useFetch("/support/tickets");
  const [open, setOpen] = useState(null);
  const [reply, setReply] = useState("");
  const view = async (id) => { const { data } = await api.get(`/support/tickets/${id}`); setOpen(data); };
  const send = async (e) => { e.preventDefault(); try { const { data } = await api.post(`/support/tickets/${open.id}/reply`, { message: reply }); setOpen(data); setReply(""); reload(); } catch (er) { toast(errMsg(er), "error"); } };
  if (!data?.items.length) return <p className="muted">You have no support tickets yet.</p>;
  return (
    <>
      <table className="tbl"><thead><tr><th>#</th><th>Subject</th><th>Status</th><th /></tr></thead><tbody>
        {data.items.map((t) => <tr key={t.id}><td>{t.id}</td><td>{t.subject}</td><td><StatusBadge status={t.status} /></td><td><button className="btn sm" onClick={() => view(t.id)}>Open</button></td></tr>)}</tbody></table>
      {open && <Modal title={`Ticket #${open.id}: ${open.subject}`} onClose={() => setOpen(null)} wide>
        {open.messages.map((m) => <div key={m.id} className="card pad" style={{ marginBottom: ".5rem", background: m.sender === "staff" ? "var(--bg)" : undefined }}><small className="muted">{m.sender === "staff" ? "Support team" : "You"} · {dateTime(m.created_at)}</small><p style={{ margin: ".2rem 0 0" }}>{m.body}</p></div>)}
        <form onSubmit={send}><Field label="Reply"><textarea required value={reply} onChange={(e) => setReply(e.target.value)} /></Field><button className="btn primary">Send</button></form></Modal>}
    </>
  );
}

export function Support() {
  const { user } = useAuth();
  const toast = useToast();
  const { data: faqs } = useFetch("/faqs");
  const [f, setF] = useState({ name: user?.name || "", email: user?.email || "", subject: "", message: "" });
  const [openFaq, setOpenFaq] = useState(null);
  const [tab, setTab] = useState("contact");
  const submit = async (e) => {
    e.preventDefault();
    try { const { data } = await api.post("/support/contact", f); toast(`Ticket #${data.id} created. We'll get back to you soon.`); setF({ ...f, subject: "", message: "" }); }
    catch (er) { toast(errMsg(er), "error"); }
  };
  return (
    <>
      <h1>Customer support</h1>
      <div className="tabs">{[["contact", "Contact us"], ["faq", "FAQ"], ...(user ? [["tickets", "My tickets"]] : [])].map(([k, t]) => <button key={k} className={tab === k ? "on" : ""} onClick={() => setTab(k)}>{t}</button>)}</div>
      {tab === "contact" && <form className="card pad" onSubmit={submit} style={{ maxWidth: 640 }}>
        <div className="form-grid"><Field label="Name"><input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} required /></Field><Field label="Email"><input type="email" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} required /></Field></div>
        <Field label="Subject"><input value={f.subject} onChange={(e) => setF({ ...f, subject: e.target.value })} required /></Field>
        <Field label="How can we help?"><textarea value={f.message} onChange={(e) => setF({ ...f, message: e.target.value })} required minLength={10} /></Field>
        <button className="btn primary">Submit ticket</button></form>}
      {tab === "faq" && <div style={{ maxWidth: 760 }}>{faqs?.map((q) => <div key={q.id} className="card pad" style={{ marginBottom: ".6rem", cursor: "pointer" }} onClick={() => setOpenFaq(openFaq === q.id ? null : q.id)}><b>{q.question}</b>{openFaq === q.id && <p className="muted" style={{ marginBottom: 0 }}>{q.answer}</p>}</div>)}</div>}
      {tab === "tickets" && <Tickets />}
    </>
  );
}

export function Notifications() {
  const { reload } = useCart();
  const toast = useToast();
  const { data, loading, reload: refetch } = useFetch("/notifications", { per_page: 50 });
  if (loading) return <Spinner />;
  const markAll = async () => { try { await api.post("/notifications/read-all"); await reload(); refetch(); } catch (e) { toast(errMsg(e), "error"); } };
  const mark = async (n) => { if (n.is_read) return; await api.patch(`/notifications/${n.id}/read`); reload(); refetch(); };
  if (!data.items.length) return <Empty icon={<Bell size={44} />} title="No notifications" text="Order, payment and delivery updates will appear here." />;
  return (
    <>
      <div className="row between"><h2>Notifications</h2><button className="btn sm" onClick={markAll}>Mark all read</button></div>
      {data.items.map((n) => <div key={n.id} className="card pad" onClick={() => mark(n)} style={{ marginBottom: ".6rem", cursor: "pointer", borderLeft: n.is_read ? undefined : "4px solid var(--primary)" }}>
        <div className="row between"><b>{n.title}</b><small className="muted">{dateTime(n.created_at)}</small></div><div className="muted">{n.message}</div></div>)}
    </>
  );
}
