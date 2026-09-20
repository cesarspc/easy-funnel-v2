import { Navigate, Route, Routes } from "react-router-dom";
import { NotFoundPage } from "./routes/NotFoundPage";
import { LandingPage } from "./features/landing/LandingPage";
import { MerchantLanding } from "./routes/MerchantLanding";
import { SessionProvider } from "./features/auth/SessionContext";
import { RequireAdmin } from "./features/auth/RequireAdmin";
import { LoginPage } from "./features/auth/LoginPage";
import { AdminShell } from "./features/admin/AdminShell";
import { ProductsPage } from "./features/admin/ProductsPage";
import { LandingsPage } from "./features/admin/LandingsPage";
import { LandingEditorPage } from "./features/admin/LandingEditorPage";
import { OrdersPage } from "./features/admin/OrdersPage";
import { FraudPage } from "./features/admin/FraudPage";
import { AnalyticsPage } from "./features/admin/AnalyticsPage";
import { StoreProvider } from "./features/store/StoreContext";
import { StoreSettingsPage } from "./features/admin/StoreSettingsPage";

/**
 * Root route table. Public storefront routes (`/`, `/p/:slug`) land here as
 * that feature ships. `/p/:slug` renders LandingPage (Requirements
 * 3.21-3.26). Admin routes are session-scoped: `/admin/login` is
 * public, every other `/admin/*` route requires an authenticated session
 * (RequireAdmin) and renders inside AdminShell.
 */
export function App() {
  return (
    <StoreProvider>
    <SessionProvider>
      <Routes>
        <Route path="/" element={<MerchantLanding />} />
        <Route path="/p/:slug" element={<LandingPage />} />

        <Route path="/admin/login" element={<LoginPage />} />
        <Route
          path="/admin"
          element={
            <RequireAdmin>
              <AdminShell />
            </RequireAdmin>
          }
        >
          <Route index element={<Navigate to="/admin/orders" replace />} />
          <Route path="products" element={<ProductsPage />} />
          <Route path="landings" element={<LandingsPage />} />
          <Route path="landings/:landingId" element={<LandingEditorPage />} />
          <Route path="orders" element={<OrdersPage />} />
          <Route path="fraud" element={<FraudPage />} />
          <Route path="analytics" element={<AnalyticsPage />} />
          <Route path="store" element={<StoreSettingsPage />} />
        </Route>

        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </SessionProvider>
    </StoreProvider>
  );
}
