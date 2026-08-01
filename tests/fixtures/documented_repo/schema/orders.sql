CREATE TABLE customer (
  id UUID PRIMARY KEY,
  email TEXT NOT NULL UNIQUE,
  created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE orders (
  id UUID PRIMARY KEY,
  customer_id UUID NOT NULL REFERENCES customer(id),
  total_minor BIGINT NOT NULL,
  currency CHAR(3) NOT NULL,
  placed_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE refund (
  id UUID PRIMARY KEY,
  order_id UUID NOT NULL REFERENCES orders(id),
  amount_minor BIGINT NOT NULL,
  reason TEXT
);
