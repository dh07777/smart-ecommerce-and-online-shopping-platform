import { Route, Routes } from "react-router-dom";
import { Footer, Navbar, ProtectedRoute } from "./components.jsx";
import Home from "./pages/Home.jsx";
import Catalog from "./pages/Catalog.jsx";
import ProductPage from "./pages/ProductPage.jsx";
import { CartPage, WishlistPage } from "./pages/CartPage.jsx";
import Checkout from "./pages/Checkout.jsx";
import { Account, OrderDetail, Orders } from "./pages/Account.jsx";
import { ForgotPassword, Login, Register, ResetPassword, SellerRegister } from "./pages/AuthPages.jsx";
import { Notifications, Support } from "./pages/Support.jsx";
import AdminApp from "./admin/AdminApp.jsx";

const NotFound = () => <div className="container center-box empty"><h2>404</h2><p className="muted">That page does not exist.</p></div>;

export default function App() {
  return (
    <Routes>
      <Route path="/admin/*" element={<ProtectedRoute roles={["store_admin", "seller"]}><AdminApp /></ProtectedRoute>} />
      <Route path="*" element={
        <>
          <Navbar />
          <main className="container page">
            <Routes>
              <Route path="/" element={<Home />} />
              <Route path="/shop" element={<Catalog />} />
              <Route path="/product/:slug" element={<ProductPage />} />
              <Route path="/cart" element={<CartPage />} />
              <Route path="/wishlist" element={<ProtectedRoute><WishlistPage /></ProtectedRoute>} />
              <Route path="/checkout" element={<ProtectedRoute><Checkout /></ProtectedRoute>} />
              <Route path="/orders" element={<ProtectedRoute><Orders /></ProtectedRoute>} />
              <Route path="/orders/:id" element={<ProtectedRoute><OrderDetail /></ProtectedRoute>} />
              <Route path="/account" element={<ProtectedRoute><Account /></ProtectedRoute>} />
              <Route path="/notifications" element={<ProtectedRoute><Notifications /></ProtectedRoute>} />
              <Route path="/support" element={<Support />} />
              <Route path="/login" element={<Login />} />
              <Route path="/register" element={<Register />} />
              <Route path="/sell" element={<SellerRegister />} />
              <Route path="/forgot-password" element={<ForgotPassword />} />
              <Route path="/reset-password" element={<ResetPassword />} />
              <Route path="*" element={<NotFound />} />
            </Routes>
          </main>
          <Footer />
        </>
      } />
    </Routes>
  );
}
