import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";
import { ProductCard } from "../components.jsx";

vi.mock("../context.jsx", () => ({
  useAuth: () => ({ user: null }),
  useCart: () => ({ addToCart: vi.fn(), toggleWishlist: vi.fn(), wishlist: [] }),
  useToast: () => vi.fn(),
}));

const product = { id: 1, name: "Test Phone", slug: "test-phone", price: 999, mrp: 1299, discount_percent: 23, image: null,
  rating: 4.5, review_count: 12, in_stock: true, category: { name: "Phones", slug: "phones" }, brand: { name: "Acme" } };

describe("ProductCard", () => {
  it("shows name, price and discount", () => {
    render(<MemoryRouter><ProductCard p={product} /></MemoryRouter>);
    expect(screen.getByText("Test Phone")).toBeInTheDocument();
    expect(screen.getByText("₹999")).toBeInTheDocument();
    expect(screen.getByText("-23%")).toBeInTheDocument();
  });
  it("disables add-to-cart when out of stock", () => {
    render(<MemoryRouter><ProductCard p={{ ...product, in_stock: false }} /></MemoryRouter>);
    expect(screen.getByRole("button", { name: /out of stock/i })).toBeDisabled();
  });
});
