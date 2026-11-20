import { useState } from "react";
import { Link } from "react-router-dom";
import { dateStr, money } from "../api";
import { ErrorBox, Spinner, StatusBadge, useFetch } from "../components.jsx";

export function BarChart({ data, format = (v) => v }) {
  const [hover, setHover] = useState(null);
  if (!data.length) return <p className="muted">No data for this period.</p>;
  const W = 640, H = 230, pad = 28, max = Math.max(...data.map((d) => d.value), 1);
  const bw = (W - pad * 2) / data.length;
  const step = Math.ceil(data.length / 8);
  return (
    <svg className="chart" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Bar chart" onMouseLeave={() => setHover(null)}>
      <text x={pad} y="14" style={{ fontSize: 12, fill: "var(--text)" }}>{hover != null ? `${data[hover].label}: ${format(data[hover].value)}` : `Max ${format(max)}`}</text>
      {data.map((d, i) => {
        const h = (d.value / max) * (H - 70);
        return (
          <g key={d.label} onMouseEnter={() => setHover(i)} onClick={() => setHover(i)}>
            <rect className="bar" x={pad + i * bw + 2} y={H - 30 - h} width={Math.max(bw - 4, 2)} height={Math.max(h, 1)} rx="3" />
            {i % step === 0 && <text x={pad + i * bw + bw / 2} y={H - 12} textAnchor="middle">{d.label.slice(-5)}</text>}
          </g>
        );
      })}
    </svg>
  );
}

export function HBars({ rows, valueKey, labelKey, format = (v) => v }) {
  const max = Math.max(...rows.map((r) => r[valueKey]), 1);
  return rows.map((r) => <div key={r[labelKey]} className="hbar"><span title={r[labelKey]}>{r[labelKey]}</span><div className="t"><i style={{ width: `${(r[valueKey] / max) * 100}%` }} /></div><b>{format(r[valueKey])}</b></div>);
}

export default function Dashboard() {
  const { data: d, loading, error, reload } = useFetch("/admin/dashboard");
  if (loading) return <Spinner />;
  if (error) return <ErrorBox message={error} onRetry={reload} />;
  const k = [["Total revenue", money(d.total_revenue)], ["Items sold", d.total_sales], ["Total orders", d.total_orders], ["Customers", d.total_customers], ["Products", d.total_products], ["Pending orders", d.pending_orders], ["Low-stock items", d.low_stock_count]];
  return (
    <>
      <h2>Dashboard</h2>
      <div className="kpis">{k.map(([t, v]) => <div key={t} className="card kpi"><small>{t}</small><b>{v}</b></div>)}</div>
      <div className="two-col">
        <div className="card pad"><h3>Revenue (last 14 days)</h3><BarChart data={d.revenue_chart.map((r) => ({ label: r.label, value: r.revenue }))} format={money} /></div>
        <div className="card pad"><div className="row between"><h3>Low stock</h3><Link to="/admin/inventory" className="muted">Manage →</Link></div>
          {d.low_stock.length === 0 ? <p className="muted">All stocked up.</p> : <div className="table-wrap"><table className="tbl"><tbody>{d.low_stock.map((l) => <tr key={l.variant_id}><td>{l.product}<br /><small className="muted">{l.sku} {[l.size, l.color].filter(Boolean).join("/")}</small></td><td className="right"><StatusBadge status={l.quantity === 0 ? "out" : "low"} /> {l.quantity}</td></tr>)}</tbody></table></div>}</div>
      </div>
      <div className="card pad" style={{ marginTop: "1rem" }}><div className="row between"><h3>Recent orders</h3><Link to="/admin/orders" className="muted">All orders →</Link></div>
        <div className="table-wrap"><table className="tbl"><thead><tr><th>Order</th><th>Customer</th><th>Date</th><th>Status</th><th className="right">Total</th></tr></thead><tbody>
          {d.recent_orders.map((o) => <tr key={o.id}><td>{o.order_number}</td><td>{o.customer.name}</td><td>{dateStr(o.created_at)}</td><td><StatusBadge status={o.status} /></td><td className="right">{money(o.total)}</td></tr>)}</tbody></table></div></div>
    </>
  );
}
