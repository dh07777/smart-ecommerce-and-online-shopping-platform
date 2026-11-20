import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { vi } from "vitest";
import { money } from "../api";
import { Empty, ProtectedRoute, StatusBadge, Stars } from "../components.jsx";

const mockAuth = { user: null, loading: false };
vi.mock("../context.jsx", () => ({
  useAuth: () => mockAuth,
  useCart: () => ({ addToCart: vi.fn(), toggleWishlist: vi.fn(), wishlist: [] }),
  useToast: () => vi.fn(),
}));

describe("helpers and components", () => {
  it("formats money in rupees", () => {
    expect(money(1999)).toBe("₹1,999");
    expect(money(0)).toBe("₹0");
  });
  it("renders status badge text with spaces", () => {
    render(<StatusBadge status="out_for_delivery" />);
    expect(screen.getByText("out for delivery")).toBeInTheDocument();
  });
  it("renders empty state", () => {
    render(<Empty title="Nothing here" text="Add something" />);
    expect(screen.getByText("Nothing here")).toBeInTheDocument();
  });
  it("renders star rating label", () => {
    render(<Stars value={4} />);
    expect(screen.getByLabelText("4 out of 5")).toBeInTheDocument();
  });
});

describe("ProtectedRoute", () => {
  const tree = (path = "/secret") => (
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/login" element={<div>login page</div>} />
        <Route path="/" element={<div>home</div>} />
        <Route path="/secret" element={<ProtectedRoute><div>secret</div></ProtectedRoute>} />
        <Route path="/admin" element={<ProtectedRoute roles={["store_admin"]}><div>admin area</div></ProtectedRoute>} />
      </Routes>
    </MemoryRouter>
  );
  it("redirects anonymous users to login", () => {
    mockAuth.user = null;
    render(tree());
    expect(screen.getByText("login page")).toBeInTheDocument();
  });
  it("lets logged-in users through", () => {
    mockAuth.user = { role: "customer" };
    render(tree());
    expect(screen.getByText("secret")).toBeInTheDocument();
  });
  it("blocks customers from admin routes", () => {
    mockAuth.user = { role: "customer" };
    render(tree("/admin"));
    expect(screen.getByText("home")).toBeInTheDocument();
  });
  it("allows super admin everywhere", () => {
    mockAuth.user = { role: "super_admin" };
    render(tree("/admin"));
    expect(screen.getByText("admin area")).toBeInTheDocument();
  });
});
