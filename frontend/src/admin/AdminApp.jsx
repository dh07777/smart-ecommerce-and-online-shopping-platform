import { NavLink, Route, Routes, Link } from "react-router-dom";
import { BarChart3, Boxes, Megaphone, ClipboardList, LayoutDashboard, MessageSquare, Package, ScrollText, Settings, ShieldCheck, Star, Store, Tag, Users } from "lucide-react";
import { useAuth } from "../context.jsx";
import Dashboard from "./Dashboard.jsx";
import { CatalogAdmin, ProductsAdmin } from "./Products.jsx";
import { OrdersAdmin, RefundsAdmin } from "./Orders.jsx";
import { InventoryAdmin } from "./Inventory.jsx";
import { CustomersAdmin, ReviewsAdmin, SellerOrders, SellerProfile, SellersAdmin, TicketsAdmin } from "./People.jsx";
import { Analytics, AuditLogs, CouponsAdmin, PromotionsAdmin, SettingsAdmin, StaffAdmin } from "./Misc.jsx";

export default function AdminApp() {
  const { user } = useAuth();
  const seller = user.role === "seller";
  const superA = user.role === "super_admin";
  const nav = seller
    ? [["", "My store", Store, true], ["products", "Products", Package], ["orders", "Orders", ClipboardList], ["inventory", "Inventory", Boxes]]
    : [["", "Dashboard", LayoutDashboard, true], ["products", "Products", Package], ["catalog", "Categories & brands", Tag], ["orders", "Orders", ClipboardList], ["refunds", "Refunds", ScrollText], ["inventory", "Inventory", Boxes], ["customers", "Customers", Users], ["coupons", "Coupons", Tag], ["promotions", "Promotions", Megaphone], ["analytics", "Analytics", BarChart3], ["sellers", "Sellers", Store], ["reviews", "Reviews", Star], ["tickets", "Support", MessageSquare], ["settings", "Settings", Settings], ["audit", "Audit log", ScrollText], ...(superA ? [["staff", "Staff", ShieldCheck]] : [])];
  return (
    <div className="admin">
      <aside className="sidebar">
        <Link to="/" className="logo light">Shop<span>Sphere</span></Link>
        {nav.map(([to, label, Icon, end]) => <NavLink key={to} end={!!end} to={`/admin/${to}`}><Icon size={17} />{label}</NavLink>)}
        <Link to="/" style={{ marginTop: "auto" }}>← Back to store</Link>
      </aside>
      <div className="admin-main">
        <Routes>
          <Route index element={seller ? <SellerProfile /> : <Dashboard />} />
          <Route path="products" element={<ProductsAdmin />} />
          <Route path="inventory" element={<InventoryAdmin />} />
          {seller && <Route path="orders" element={<SellerOrders />} />}
          {!seller && <>
            <Route path="catalog" element={<CatalogAdmin />} />
            <Route path="orders" element={<OrdersAdmin />} />
            <Route path="refunds" element={<RefundsAdmin />} />
            <Route path="customers" element={<CustomersAdmin />} />
            <Route path="coupons" element={<CouponsAdmin />} />
            <Route path="promotions" element={<PromotionsAdmin />} />
            <Route path="analytics" element={<Analytics />} />
            <Route path="sellers" element={<SellersAdmin />} />
            <Route path="reviews" element={<ReviewsAdmin />} />
            <Route path="tickets" element={<TicketsAdmin />} />
            <Route path="settings" element={<SettingsAdmin />} />
            <Route path="audit" element={<AuditLogs />} />
            {superA && <Route path="staff" element={<StaffAdmin />} />}
          </>}
          <Route path="*" element={<p className="muted">Page not found.</p>} />
        </Routes>
      </div>
    </div>
  );
}
