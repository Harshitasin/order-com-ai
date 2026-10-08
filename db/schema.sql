-- schema.sql - full schema for a fresh setup. Run as an admin user (root).
--
-- Relationships:
--   customers 1--* orders 1--* order_items
--                 orders 1--1 shipments 1--* shipment_events
--                 orders 1--* refunds
--   policies and chat_audit_log stand alone (no foreign keys).
-- WARNING: the table definitions have no DROP/IF NOT EXISTS, so run this on a fresh database only.
CREATE DATABASE IF NOT EXISTS shop;
USE shop;

-- Login accounts. password_hash holds a salted hash, never the real password.
-- Only the auth_reader MySQL user may read this table (see grants.sql).
CREATE TABLE customers (
  customer_id   INT PRIMARY KEY AUTO_INCREMENT,
  name          VARCHAR(100) NOT NULL,
  email         VARCHAR(150) NOT NULL UNIQUE,
  password_hash VARCHAR(255) NOT NULL
);

-- One row per order. The chatbot always filters this table by customer_id.
CREATE TABLE orders (
  order_id       VARCHAR(30) PRIMARY KEY,            -- e.g. ORD-100234
  customer_id    INT NOT NULL,
  status         ENUM('PLACED','PACKED','SHIPPED','OUT_FOR_DELIVERY','DELIVERED','CANCELLED') NOT NULL,
  placed_at      DATETIME NOT NULL,
  total_amount   DECIMAL(10,2),
  payment_method VARCHAR(30),
  FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
);

-- One-to-many: an order has one or more line items.
CREATE TABLE order_items (
  id            INT PRIMARY KEY AUTO_INCREMENT,
  order_id      VARCHAR(30) NOT NULL,
  product_name  VARCHAR(255) NOT NULL,
  qty           INT NOT NULL,
  price         DECIMAL(10,2) NOT NULL,
  is_returnable BOOLEAN DEFAULT TRUE,
  FOREIGN KEY (order_id) REFERENCES orders(order_id)
);

-- One-to-one with orders (UNIQUE order_id). No row = not shipped yet.
CREATE TABLE shipments (
  shipment_id       INT PRIMARY KEY AUTO_INCREMENT,
  order_id          VARCHAR(30) NOT NULL UNIQUE,      -- one shipment per order
  carrier           VARCHAR(50),
  tracking_no       VARCHAR(50),
  expected_delivery DATE,
  delivered_at      DATETIME NULL,
  FOREIGN KEY (order_id) REFERENCES orders(order_id)
);

-- Tracking timeline. The composite index makes "events of shipment X in time order" fast.
CREATE TABLE shipment_events (
  id          INT PRIMARY KEY AUTO_INCREMENT,
  shipment_id INT NOT NULL,
  event_time  DATETIME NOT NULL,
  location    VARCHAR(100),
  event_type  VARCHAR(50) NOT NULL,   -- PICKED_UP, IN_TRANSIT, HUB_DELAY, WEATHER_DELAY, ADDRESS_ISSUE, DELIVERED
  note        VARCHAR(255),
  FOREIGN KEY (shipment_id) REFERENCES shipments(shipment_id),
  INDEX idx_events_shipment_time (shipment_id, event_time)
);

-- An order may have 0 or more refunds.
CREATE TABLE refunds (
  refund_id    INT PRIMARY KEY AUTO_INCREMENT,
  order_id     VARCHAR(30) NOT NULL,
  amount       DECIMAL(10,2),
  status       ENUM('INITIATED','PROCESSING','COMPLETED','REJECTED') NOT NULL,
  initiated_at DATETIME,
  expected_by  DATE,
  refund_mode  VARCHAR(30),
  FOREIGN KEY (order_id) REFERENCES orders(order_id)
);

-- Store policy texts the assistant may quote (whitelisted in services/tools.py).
CREATE TABLE policies (
  policy_key  VARCHAR(50) PRIMARY KEY,   -- 'return_policy', 'refund_timeline', 'cancellation_policy'
  policy_text TEXT
);

-- Written by the INSERT-only audit_writer user; the chatbot user cannot read it.
CREATE TABLE chat_audit_log (
  id            BIGINT PRIMARY KEY AUTO_INCREMENT,
  customer_id   INT,
  user_message  TEXT,
  tools_called  JSON,
  response_text TEXT,
  blocked       BOOLEAN DEFAULT FALSE,
  created_at    DATETIME DEFAULT NOW()
);
