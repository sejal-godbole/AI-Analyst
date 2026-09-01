-- Sample schema demonstrating multi-table relationships for the AI Analyst Agent.
-- No real personal data is used.

CREATE TABLE IF NOT EXISTS customers (
    customer_id     SERIAL PRIMARY KEY,
    name            VARCHAR(120) NOT NULL,
    city            VARCHAR(80),
    email           VARCHAR(160) UNIQUE,
    monthly_charge  DECIMAL(10, 2) DEFAULT 0
);

CREATE TABLE IF NOT EXISTS products (
    product_id      SERIAL PRIMARY KEY,
    name            VARCHAR(120) NOT NULL,
    category        VARCHAR(80),
    price           DECIMAL(10, 2) NOT NULL
);

CREATE TABLE IF NOT EXISTS orders (
    order_id        SERIAL PRIMARY KEY,
    customer_id     INTEGER NOT NULL REFERENCES customers(customer_id),
    order_date      DATE NOT NULL DEFAULT CURRENT_DATE,
    amount          DECIMAL(10, 2) NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS order_items (
    order_item_id   SERIAL PRIMARY KEY,
    order_id        INTEGER NOT NULL REFERENCES orders(order_id),
    product_id      INTEGER NOT NULL REFERENCES products(product_id),
    quantity        INTEGER NOT NULL DEFAULT 1,
    unit_price      DECIMAL(10, 2) NOT NULL
);

-- Audit log table used by app/logging/audit.py
CREATE TABLE IF NOT EXISTS agent_audit_log (
    audit_id                SERIAL PRIMARY KEY,
    created_at               TIMESTAMP NOT NULL DEFAULT now(),
    user_question             TEXT NOT NULL,
    intent                    VARCHAR(30),
    generated_sql             TEXT,
    validation_status         VARCHAR(30),
    execution_status          VARCHAR(30),
    error                      TEXT,
    retry_count               INTEGER DEFAULT 0,
    rows_affected              INTEGER,
    result_summary             TEXT,
    confirmation_required     BOOLEAN DEFAULT false,
    confirmation_status       VARCHAR(30)
);

-- Seed data
INSERT INTO customers (name, city, email, monthly_charge) VALUES
    ('Aditi Sharma', 'Pune', 'aditi.sharma@example.com', 499.00),
    ('Rahul Verma', 'Mumbai', 'rahul.verma@example.com', 799.00),
    ('Meera Nair', 'Pune', 'meera.nair@example.com', 299.00),
    ('Karan Patel', 'Ahmedabad', 'karan.patel@example.com', 999.00),
    ('Sneha Iyer', 'Pune', 'sneha.iyer@example.com', 599.00),
    ('Vikram Singh', 'Delhi', 'vikram.singh@example.com', 399.00),
    ('Ananya Rao', 'Bengaluru', 'ananya.rao@example.com', 699.00),
    ('Ishaan Kapoor', 'Pune', 'ishaan.kapoor@example.com', 499.00)
ON CONFLICT DO NOTHING;

INSERT INTO products (name, category, price) VALUES
    ('Wireless Mouse', 'Electronics', 799.00),
    ('Mechanical Keyboard', 'Electronics', 3499.00),
    ('Notebook Set', 'Stationery', 249.00),
    ('Desk Lamp', 'Home', 1199.00),
    ('Water Bottle', 'Lifestyle', 349.00)
ON CONFLICT DO NOTHING;

INSERT INTO orders (customer_id, order_date, amount) VALUES
    (1, '2026-06-01', 4298.00),
    (1, '2026-07-14', 799.00),
    (2, '2026-06-20', 3499.00),
    (3, '2026-08-02', 349.00),
    (5, '2026-08-10', 1199.00),
    (7, '2026-08-15', 4298.00)
ON CONFLICT DO NOTHING;

INSERT INTO order_items (order_id, product_id, quantity, unit_price) VALUES
    (1, 2, 1, 3499.00),
    (1, 1, 1, 799.00),
    (2, 1, 1, 799.00),
    (3, 2, 1, 3499.00),
    (4, 5, 1, 349.00),
    (5, 4, 1, 1199.00),
    (6, 2, 1, 3499.00),
    (6, 1, 1, 799.00)
ON CONFLICT DO NOTHING;

-- Note: customer 4 (Karan Patel), 6 (Vikram Singh), and 8 (Ishaan Kapoor) intentionally
-- have no orders, to demonstrate "customers who never placed an order" queries.
