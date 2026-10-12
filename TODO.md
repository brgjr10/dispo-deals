# Dispo-Deals Project Todo

## Completed ✅

- [x] Added `get_full_menu()` method to `api_server.py` querying latest weekly snapshots per store
- [x] Added `send_full_menu()` handler and `/api/menu` route to `DashboardHandler`
- [x] Verified `/api/menu` endpoint returns 2,374 products, 3 stores, 48 categories, 98 brands
- [x] **Complete rewrite of `dashboard.html`** - transformed from deals-only to full cross-shop browser:
  - Dutchie-style sidebar with stores, categories, brands navigation
  - Advanced filtering (store/category/brand, deals-only toggle, stock status, search, sorting)
  - Virtualized grid with 60-item batches, skeleton loading, IntersectionObserver
  - Quick view modal with image navigation, product details, pricing
  - Compare mode (select up to 4 products side-by-side)
  - URL state persistence (filters, sort, search)
  - Responsive dark theme with smooth animations

## In Progress 🔄

- [ ] Test dashboard in browser against running API server
- [ ] Verify all features work correctly (filtering, sorting, modal, compare)

## Next Steps 📋

- [ ] Add keyboard shortcuts (arrow keys for grid navigation, Escape to close modal)
- [ ] Add product image caching/preloading optimization
- [ ] Consider adding "Add to favorites" / wishlist feature
- [ ] Consider adding price history chart for products
- [ ] Add export/share functionality for compare panel
- [ ] Test on mobile devices and refine responsive layout
- [ ] Add unit/integration tests for the new API endpoint

## Known Issues / Blockers

- None currently