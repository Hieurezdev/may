CREATE TABLE customers (
 id TEXT PRIMARY KEY, full_name TEXT NOT NULL DEFAULT 'Khách', email TEXT UNIQUE,
 salt TEXT, password_hash TEXT, role TEXT NOT NULL DEFAULT 'customer'
 CHECK(role IN ('customer','merchant','support','operator')),
 consent_state INTEGER NOT NULL DEFAULT 0 CHECK(consent_state IN (0,1)),
 chat_revision INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE sessions (token_hash TEXT PRIMARY KEY, customer_id TEXT NOT NULL REFERENCES customers(id), created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE addresses (id TEXT PRIMARY KEY, customer_id TEXT NOT NULL REFERENCES customers(id), recipient_name TEXT NOT NULL, phone TEXT NOT NULL, address TEXT NOT NULL);
CREATE TABLE categories (id TEXT PRIMARY KEY, name TEXT NOT NULL, icon TEXT NOT NULL);
CREATE TABLE products (
 id TEXT PRIMARY KEY, name TEXT NOT NULL, brand TEXT NOT NULL, category TEXT NOT NULL REFERENCES categories(id),
 price INTEGER NOT NULL CHECK(price>=0), original_price INTEGER NOT NULL CHECK(original_price>=0),
 image TEXT NOT NULL, rating REAL, sold INTEGER, try_on TEXT, tag TEXT NOT NULL, specs TEXT NOT NULL,
 source_url TEXT, collected_at TEXT, active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
 source_version INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE product_categories (product_id TEXT NOT NULL REFERENCES products(id), category_id TEXT NOT NULL REFERENCES categories(id), PRIMARY KEY(product_id,category_id));
CREATE TABLE variants (id TEXT PRIMARY KEY, product_id TEXT NOT NULL REFERENCES products(id), sku TEXT NOT NULL UNIQUE, color TEXT NOT NULL, size TEXT NOT NULL, price INTEGER NOT NULL CHECK(price>=0), sellable INTEGER NOT NULL DEFAULT 1 CHECK(sellable IN (0,1)));
CREATE TABLE media_assets (id TEXT PRIMARY KEY, product_id TEXT NOT NULL REFERENCES products(id), uri TEXT NOT NULL, media_hash TEXT NOT NULL, moderation_state TEXT NOT NULL DEFAULT 'approved' CHECK(moderation_state IN ('approved','pending','rejected')));
CREATE TABLE inventory_positions (
 id TEXT PRIMARY KEY, variant_id TEXT NOT NULL REFERENCES variants(id), location_id TEXT NOT NULL,
 on_hand INTEGER NOT NULL CHECK(on_hand>=0), reserved INTEGER NOT NULL DEFAULT 0 CHECK(reserved>=0 AND reserved<=on_hand), UNIQUE(variant_id,location_id)
);
CREATE TABLE carts (id TEXT PRIMARY KEY, customer_id TEXT NOT NULL UNIQUE REFERENCES customers(id), expires_at TEXT);
CREATE TABLE cart_items (id TEXT PRIMARY KEY, cart_id TEXT NOT NULL REFERENCES carts(id), variant_id TEXT NOT NULL REFERENCES variants(id), quantity INTEGER NOT NULL CHECK(quantity BETWEEN 1 AND 99), UNIQUE(cart_id,variant_id));
CREATE TABLE vouchers (code TEXT PRIMARY KEY, title TEXT NOT NULL, kind TEXT NOT NULL CHECK(kind IN ('percent','fixed','shipping')), value INTEGER NOT NULL CHECK(value>=0), minimum INTEGER NOT NULL, maximum INTEGER NOT NULL, usage_limit INTEGER NOT NULL, used_count INTEGER NOT NULL DEFAULT 0 CHECK(used_count>=0 AND used_count<=usage_limit), active INTEGER NOT NULL DEFAULT 1, expires_at TEXT NOT NULL);
CREATE TABLE price_rules (id TEXT PRIMARY KEY, variant_id TEXT NOT NULL REFERENCES variants(id), price_minor INTEGER NOT NULL CHECK(price_minor>=0), starts_at TEXT NOT NULL, ends_at TEXT NOT NULL CHECK(ends_at>starts_at));
CREATE TABLE orders (
 id TEXT PRIMARY KEY, customer_id TEXT NOT NULL REFERENCES customers(id), recipient_name TEXT NOT NULL, phone TEXT NOT NULL, address TEXT NOT NULL,
 subtotal INTEGER NOT NULL CHECK(subtotal>=0), discount INTEGER NOT NULL CHECK(discount>=0), shipping INTEGER NOT NULL CHECK(shipping>=0), total INTEGER NOT NULL CHECK(total=subtotal-discount+shipping AND total>=0), currency TEXT NOT NULL DEFAULT 'VND' CHECK(currency='VND'),
 voucher TEXT REFERENCES vouchers(code), voucher_released INTEGER NOT NULL DEFAULT 0,
 status TEXT NOT NULL CHECK(status IN ('pending_payment','confirmed','paid','processing','shipped','delivered','cancelled','expired','payment_failed','reconciliation')),
 payment_method TEXT NOT NULL CHECK(payment_method IN ('cod','online-demo')), payment_status TEXT NOT NULL DEFAULT 'pending',
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, delivered_at TEXT, idempotency_key TEXT NOT NULL UNIQUE, request_hash TEXT NOT NULL
);
CREATE TABLE order_items (
 id TEXT PRIMARY KEY, order_id TEXT NOT NULL REFERENCES orders(id), variant_id TEXT NOT NULL REFERENCES variants(id), sku_snapshot TEXT NOT NULL,
 name TEXT NOT NULL, color TEXT NOT NULL, size TEXT NOT NULL, image TEXT NOT NULL, category_snapshot TEXT NOT NULL,
 quantity INTEGER NOT NULL CHECK(quantity>0), unit_price INTEGER NOT NULL CHECK(unit_price>=0), discount_minor INTEGER NOT NULL DEFAULT 0 CHECK(discount_minor>=0), UNIQUE(id,order_id)
);
CREATE TRIGGER immutable_order_line BEFORE UPDATE ON order_items BEGIN SELECT RAISE(ABORT,'Purchased order snapshots are immutable'); END;
CREATE TABLE reservations (
 id TEXT PRIMARY KEY, position_id TEXT NOT NULL REFERENCES inventory_positions(id), order_line_id TEXT NOT NULL UNIQUE REFERENCES order_items(id), quantity INTEGER NOT NULL CHECK(quantity>0), expires_at TEXT NOT NULL,
 state TEXT NOT NULL CHECK(state IN ('held','committed','released','dispatched'))
);
CREATE TABLE payment_attempts (
 id TEXT PRIMARY KEY, order_id TEXT NOT NULL REFERENCES orders(id), provider TEXT NOT NULL,
 provider_reference TEXT NOT NULL UNIQUE, amount INTEGER NOT NULL CHECK(amount>=0), currency TEXT NOT NULL CHECK(currency='VND'),
 status TEXT NOT NULL CHECK(status IN ('pending','failed','cancelled','captured','reconciliation')), created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE UNIQUE INDEX settled_payment_per_order ON payment_attempts(order_id) WHERE status IN ('captured','reconciliation');
CREATE TABLE provider_events (provider TEXT NOT NULL, event_id TEXT NOT NULL, attempt_id TEXT REFERENCES payment_attempts(id), refund_id TEXT, kind TEXT NOT NULL, payload_hash TEXT NOT NULL, outcome TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY(provider,event_id));
CREATE TABLE shipments (id TEXT PRIMARY KEY, order_id TEXT NOT NULL UNIQUE REFERENCES orders(id), provider TEXT NOT NULL, tracking_code TEXT NOT NULL UNIQUE, status TEXT NOT NULL CHECK(status IN ('shipped','delivered')), created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE shipment_lines (shipment_id TEXT NOT NULL REFERENCES shipments(id), order_line_id TEXT NOT NULL REFERENCES order_items(id), quantity INTEGER NOT NULL CHECK(quantity>0), PRIMARY KEY(shipment_id,order_line_id));
CREATE TABLE return_requests (id TEXT PRIMARY KEY, order_id TEXT NOT NULL REFERENCES orders(id), reason TEXT NOT NULL, evidence TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN ('requested','approved','rejected','inspected','refund_pending','completed')), review_reason TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE return_lines (id TEXT PRIMARY KEY, request_id TEXT NOT NULL REFERENCES return_requests(id), order_id TEXT NOT NULL REFERENCES orders(id), order_line_id TEXT NOT NULL, quantity INTEGER NOT NULL CHECK(quantity>0), restocked INTEGER NOT NULL DEFAULT 0, UNIQUE(request_id,order_line_id), FOREIGN KEY(order_line_id,order_id) REFERENCES order_items(id,order_id));
CREATE TABLE refunds (id TEXT PRIMARY KEY, request_id TEXT UNIQUE REFERENCES return_requests(id), order_id TEXT NOT NULL REFERENCES orders(id), attempt_id TEXT NOT NULL REFERENCES payment_attempts(id), amount INTEGER NOT NULL CHECK(amount>0), status TEXT NOT NULL CHECK(status IN ('pending','succeeded','failed','reconciliation')), idempotency_key TEXT NOT NULL UNIQUE, reason TEXT NOT NULL, settled_at TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE guest_access_proofs (proof_hash TEXT PRIMARY KEY, order_id TEXT NOT NULL REFERENCES orders(id), expires_at TEXT NOT NULL);
CREATE TABLE outbox_events (id TEXT PRIMARY KEY, aggregate_id TEXT NOT NULL, kind TEXT NOT NULL, payload TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0, next_attempt_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, lease_until TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE audit_events (id TEXT PRIMARY KEY, actor_id TEXT REFERENCES customers(id), action TEXT NOT NULL, entity_id TEXT NOT NULL, reason TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE try_on_sessions (id TEXT PRIMARY KEY, customer_id TEXT NOT NULL REFERENCES customers(id), product_id TEXT NOT NULL REFERENCES products(id), status TEXT NOT NULL DEFAULT 'preview', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, deleted_at TEXT);
CREATE TABLE chat_messages (id INTEGER PRIMARY KEY, customer_id TEXT NOT NULL REFERENCES customers(id), sender TEXT NOT NULL, content TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE INDEX orders_customer_created ON orders(customer_id,created_at);
CREATE INDEX reservations_state_expiry ON reservations(state,expires_at);
CREATE INDEX return_requests_order ON return_requests(order_id);
