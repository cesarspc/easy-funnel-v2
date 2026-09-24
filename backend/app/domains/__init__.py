"""Domain rule modules: products, landings, orders, fraud, analytics, images.

Orders domain:
- Field validation/normalization (name, phone, department, city, address, quantity)
- Phone normalization to E.164 using the merchant-configured phone rules
- Stable matching key for duplicate/blacklist/rate-limit
- Centralized legal status-transition graph

Fraud domain:
- Fraud config with defaults and update validation
- Blacklist add/remove with normalization
- GeoIP rule CRUD
- Four fraud checks: duplicate, blacklist, rate-limit phone/IP, GeoIP
- Multi-flag aggregation

Analytics domain:
- View/click recording (no contact fields)
- Per-day and per-landing aggregation
- Conversion rate with zero-guarded denominators
- Flagged-fraud rate computation
"""
