# Implementation mapping to the V04 report

The reference storefront supplies visual design, catalog source data, camera controls, speech/client utilities and the optional Ami assistant. This project implements its own database and commerce lifecycle. Report entity names use singular conceptual names; SQLite tables use the plural naming convention of the supplied source.

## Data and model boundaries

| Report concept | SQLite tables | Python boundary |
| --- | --- | --- |
| Customer, address and verified identity | customers, sessions, addresses, guest_access_proofs | auth.py; Credentials, AddressInput |
| Product, Variant, Category, MediaAsset | products, variants, categories, product_categories, media_assets, price_rules | catalog_product; Product, Variant, ProductCreate, ProductUpdate |
| Cart and CartLine | carts, cart_items | cart_lines; CartInput, CartLine |
| InventoryPosition and Reservation | inventory_positions, reservations | immutable InventoryPosition, ReservationState; inventory.py |
| Order and immutable OrderLine | orders, order_items | immutable Order, OrderLine, OrderStatus; OrderInput, OrderResult |
| PaymentAttempt and ProviderEvent | payment_attempts, provider_events | CallbackInput; process_payment |
| Shipment and ShipmentLine | shipments, shipment_lines | ShipmentInput; dispatch |
| ReturnRequest, ReturnLine and Refund | return_requests, return_lines, refunds | ReturnInput, ReturnView, ReviewInput, InspectionInput, RefundCallback |
| Text and image embeddings | text_embeddings, image_embeddings, index_manifests | SearchInput, EmbeddingResponse; discovery.py |
| Customer DBSCAN segmentation | segment_models, segment_assignments | CustomerFeatures, Scaler; clustering.py, recommendations.py |
| Durable notifications and evidence | outbox_events, audit_events | notify, audit; notifications.py |
| Reference-only camera and chat | try_on_sessions, chat_messages | TryOnInput, ChatInput, ChatReply |

The physical schema is executable SQL in migrations/001_commerce.sql and 002_discovery.sql. Foreign keys are enabled on every connection. IDs are TEXT; new identities use UUIDs. Imported catalog product IDs and SKUs preserve their source strings. Money uses INTEGER VND minor units; quantities use INTEGER; eps uses REAL. Stored application timestamps use UTC `YYYY-MM-DD HH:MM:SS`. Incoming model cutoffs require an explicit timezone and are converted before storage.

Pydantic request DTOs in `backend/dtos/` validate input at HTTP boundaries. Contracts are grouped into accounts, catalog, cart, orders, payments, returns, discovery and experience. Account, catalog, chat and try-on routes live in `backend/api/`; `backend/main.py` composes those routers with the existing commerce, discovery and speech routers, configures lifecycle and serves static assets. Response DTOs expose approved fields rather than raw account/password rows. Domain objects are immutable dataclasses. SQL repositories are implemented directly inside cohesive use-case modules using the supplied application's sqlite3 convention; the project does not claim the additional repository interfaces in the illustrative Chapter 4 scaffold are all implemented classes.

## Transaction rules

1. A checkout opens BEGIN IMMEDIATE, expires overdue holds, checks idempotency and payload hash, recalculates the quote and checks the customer's required, strict integer `expected_total`. A changed total returns HTTP 409 with `detail.code = quote_changed` and the fresh quote before any order or reservation writes. The browser preserves delivery fields, displays the new quote and requires another explicit submit with a new idempotency key; it never silently accepts the changed total.
2. It writes one durable order and immutable line snapshots, conditionally increments reserved inventory, persists reservations and a payment attempt, consumes the voucher and clears the submitted cart in the same transaction. No external request runs while that transaction is open.
3. A verified captured callback checks amount, currency and provider reference, deduplicates `(provider,event_id)`, marks the attempt captured and commits all held reservations. It does not reduce on-hand stock yet.
4. Dispatch requires a processing order with committed stock. It creates a unique tracking reference, shipment lines and dispatches each reservation, reducing on-hand and reserved by the same quantity.
5. Failed or expired unpaid attempts release held stock once. A later verified capture enters reconciliation and does not reacquire already released inventory.
6. Cancellation before dispatch releases stock and vouchers once. Captured money produces a separate pending refund rather than being silently erased.
7. Returns reference purchased order lines using a composite foreign key that also identifies the order. Only delivered orders within seven days qualify. Existing non-rejected quantities count against the remaining returnable quantity.
8. Support approves policy; merchant inspects receipt and may restock once; support authorizes only the computed net line value. Both pending and succeeded refunds count against the original captured ceiling. Signed callback completion updates the return and customer payment view.

A failed-payment order remains a durable failed order for audit. Its submitted cart is not automatically restored. The customer may select products again for a new checkout and key. This is an explicit difference from the other student's Chapter 5 example; the report must describe this application's behavior.

## Roles and ownership

- Customer or guest session: own cart, order, cancellation and return only. Guest reads rely on a random hashed session cookie or a separately issued order-scoped access proof.
- Merchant: catalog, physical inventory, preparation, shipment and return inspection. It cannot authorize refunds or publish customer models.
- Support: return review and inspected-value refund authorization. It cannot edit stock, price or delivery state.
- Operator: audit/outbox, expiry, model/index publication and simulated refund reconciliation. It cannot change catalog or fulfill an order.

The browser's role is for navigation only; dependencies check identity and role at the server. Registration and login rotate session tokens. Cross-origin browser writes are blocked. New accounts cannot submit role fields to acquire staff access.

## Discovery and recommendations

Text search combines exact/lexical evidence and normalized BGE-M3 dense vectors. A separate CLIP model encodes images; the vector spaces are never interchanged. Reciprocal-rank fusion merges available ranked lists and deduplicates product IDs. Each response rechecks live publication, sellable variants and available inventory. A source hash prevents changed text/media from using obsolete vectors.

Index builds perform external encoder calls outside write transactions. After all vectors are complete, the source snapshot is rechecked and one ready generation replaces its predecessor atomically. Model revision and vector dimension must match. An unavailable service/index produces an explicit fallback reason for text search; image-only requests fail visibly instead of inventing visual results.

DBSCAN uses consented customers, not products. Completed-order features cover the prior 90 days: recency, log frequency, log net spend, average basket size, return rate and category quantity shares. Refund adjustments use their recorded settlement times. The scaler is fitted only on pre-cutoff feature vectors. Post-cutoff purchases are used for a holdout hit-rate comparison against popularity. Stability is measured under eps +/-10%; the implementation is a deterministic educational O(n^2) algorithm capped at 1,000 training customers.

Draft publication requires at least one cluster, noise rate <=0.6, pair stability >=0.8, at least two holdout customers and hit-rate@10 at least the popularity baseline. These are prototype gates, not a claim of commercial uplift. Serving uses stored versioned assignments and eligible products purchased by other consented customers in that cluster. There is no fabricated DBSCAN `.predict`. Opt-out, missing model, cold start, noise and an empty eligible peer result use explicit popularity fallback. Revoking consent retires affected models and removes their derived assignments/core samples.

## External boundaries and honest demonstration scope

| Boundary | Implemented behavior | Demonstration limit |
| --- | --- | --- |
| Payment | HMAC verification, amount/reference checks, deduplication, state transitions | Local provider simulator only; no real charge |
| Refund | Ceiling, idempotency, authenticated completion and return updates | Local provider simulator only |
| Shipping | Guarded prepare/ship/deliver and tracking reference | Manual merchant entry; no carrier API or provider assignment role |
| Speech | Consented ElevenLabs request and editable transcript | Requires separately configured key; never reuse reference credentials |
| Text/image models | Separate optional pinned local model service | Initial downloads and model runtime required |
| DBSCAN | Real algorithm, persistence, holdout and publication | Empty live history uses fallback; synthetic fixtures stay in tests |
| Notification | Durable outbox, leases, bounded transient retry and receiver idempotency key | External endpoint must be configured |

## Requirement traceability for Chapter 5

| Requirement group | Implementation | Evidence path |
| --- | --- | --- |
| Discovery, variant detail and filtering | api/catalog.py, discovery.py | screenshots 02-06, multimodal evidence when configured |
| Cart, quote, reservation and checkout | checkout.py, inventory.py | screenshots 07-10; concurrency/idempotency tests |
| Account, privacy and address | auth.py, api/accounts.py, recommendations.py | screenshots 11-13; ownership tests |
| Fulfillment and tracking | fulfillment.py | screenshots 14-17; inventory dispatch tests |
| Return and refund | returns.py, payments.py | screenshots 18-22; partial quantity and ceiling tests |
| Catalog and operational controls | fulfillment.py, recommendations.py, notifications.py | screenshots 23-25; role tests |
| Failure compensation | payments.py, inventory.py | screenshot 26; expiry/late-capture tests |
| Responsive storefront | frontend source design retained | screenshot 27; browser overflow assertion |

The source report contains both grouped and detailed FR numbering. Traceability therefore cites feature groups and concrete use cases rather than inventing an incompatible renumbering. Chapter 5 reports measured test counts and actual captured states only.
