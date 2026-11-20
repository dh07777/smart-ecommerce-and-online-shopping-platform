import { useState } from "react";
import api, { dateTime, downloadFile, errMsg } from "../api";
import { Field, Modal, Pagination, Spinner, StatusBadge, useFetch } from "../components.jsx";
import { useAuth, useToast } from "../context.jsx";
import { money } from "../api";

export function InventoryAdmin() {
  const { isStaff } = useAuth();
  const toast = useToast();
  const [page, setPage] = useState(1);
  const [low, setLow] = useState(false);
  const [q, setQ] = useState("");
  const [term, setTerm] = useState("");
  const [tab, setTab] = useState("stock");
  const [edit, setEdit] = useState(null);
  const { data, loading, reload } = useFetch("/admin/inventory", { page, per_page: 15, low_stock: low ? 1 : "", q: term });
  const { data: hist } = useFetch(tab === "history" ? "/admin/inventory/history" : null, { per_page: 30 });
  const { data: rep } = useFetch(isStaff ? "/admin/inventory/report" : null, null, [data]);
  const save = async (e) => {
    e.preventDefault();
    try { await api.patch(`/admin/inventory/${edit.variant_id}`, { quantity: edit.newQty, low_stock_threshold: edit.threshold, reason: edit.reason }); toast("Stock updated"); setEdit(null); reload(); }
    catch (er) { toast(errMsg(er), "error"); }
  };
  return (
    <>
      <div className="row between wrap gap"><h2>Inventory</h2>{isStaff && <button className="btn" onClick={() => downloadFile("/admin/analytics/export?type=inventory", "inventory-report.csv").catch((e) => toast(errMsg(e), "error"))}>Export report</button>}</div>
      {rep && <div className="kpis">{[["SKUs", rep.variants], ["Units in stock", rep.units], ["Low stock", rep.low_stock], ["Out of stock", rep.out_of_stock], ["Stock value", money(rep.stock_value)]].map(([t, v]) => <div key={t} className="card kpi"><small>{t}</small><b>{v}</b></div>)}</div>}
      <div className="seg" style={{ marginBottom: "1rem" }}>{["stock", "history"].map((t) => <button key={t} className={tab === t ? "on" : ""} onClick={() => setTab(t)}>{t === "stock" ? "Stock levels" : "Stock history"}</button>)}</div>
      {tab === "stock" && <>
        <div className="row gap-s wrap" style={{ marginBottom: ".8rem" }}><form onSubmit={(e) => { e.preventDefault(); setPage(1); setTerm(q); }}><input placeholder="Search product or SKU" value={q} onChange={(e) => setQ(e.target.value)} /></form>
          <label className="check"><input type="checkbox" checked={low} onChange={(e) => { setLow(e.target.checked); setPage(1); }} />Low stock only</label></div>
        {loading ? <Spinner /> : <div className="card table-wrap"><table className="tbl"><thead><tr><th>Product</th><th>SKU</th><th>Variant</th><th>Qty</th><th>Alert at</th><th>Status</th><th /></tr></thead><tbody>
          {data.items.map((v) => <tr key={v.variant_id}><td>{v.product}</td><td>{v.sku}</td><td>{[v.size, v.color].filter(Boolean).join(" / ") || "-"}</td><td><b>{v.quantity}</b></td><td>{v.threshold}</td><td><StatusBadge status={v.status} /></td>
            <td><button className="btn sm" onClick={() => setEdit({ ...v, newQty: v.quantity, reason: "" })}>Update</button></td></tr>)}</tbody></table></div>}
        {data && <Pagination page={data.page} pages={data.pages} onChange={setPage} />}</>}
      {tab === "history" && (hist ? <div className="card table-wrap"><table className="tbl"><thead><tr><th>When</th><th>Product</th><th>SKU</th><th>Change</th><th>After</th><th>Reason</th></tr></thead><tbody>
        {hist.items.map((h) => <tr key={h.id}><td>{dateTime(h.created_at)}</td><td>{h.product}</td><td>{h.sku}</td><td className={h.change < 0 ? "" : "green"}>{h.change > 0 ? "+" : ""}{h.change}</td><td>{h.quantity_after}</td><td>{h.reason}</td></tr>)}</tbody></table></div> : <Spinner />)}
      {edit && <Modal title={`Update stock: ${edit.product}`} onClose={() => setEdit(null)}><form onSubmit={save}>
        <Field label={`New quantity (currently ${edit.quantity})`}><input type="number" min="0" required value={edit.newQty} onChange={(e) => setEdit({ ...edit, newQty: e.target.value })} /></Field>
        <Field label="Low-stock alert threshold"><input type="number" min="0" value={edit.threshold} onChange={(e) => setEdit({ ...edit, threshold: e.target.value })} /></Field>
        <Field label="Reason"><input value={edit.reason} onChange={(e) => setEdit({ ...edit, reason: e.target.value })} placeholder="e.g. Restock from supplier" /></Field>
        <button className="btn primary">Save</button></form></Modal>}
    </>
  );
}
