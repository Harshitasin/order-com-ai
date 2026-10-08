-- grants.sql - least-privilege MySQL users. Run as root. Replace the <PLACEHOLDERS>
-- with real passwords; NEVER commit real passwords.
-- (If your read-only user has a different name, change DB_RO_USER in .env to match.)

-- 1) Chatbot tools: read-only, and NO access to customers / chat_audit_log
CREATE USER 'assistant_ro'@'localhost' IDENTIFIED BY '<RO_PASSWORD>';
GRANT SELECT ON shop.orders          TO 'assistant_ro'@'localhost';
GRANT SELECT ON shop.order_items     TO 'assistant_ro'@'localhost';
GRANT SELECT ON shop.shipments       TO 'assistant_ro'@'localhost';
GRANT SELECT ON shop.shipment_events TO 'assistant_ro'@'localhost';
GRANT SELECT ON shop.refunds         TO 'assistant_ro'@'localhost';
GRANT SELECT ON shop.policies        TO 'assistant_ro'@'localhost';

-- 2) Audit logging: INSERT only
CREATE USER 'audit_writer'@'localhost' IDENTIFIED BY '<AUDIT_PASSWORD>';
GRANT INSERT ON shop.chat_audit_log TO 'audit_writer'@'localhost';

-- 3) Login only: three columns of customers, nothing else
CREATE USER 'auth_reader'@'localhost' IDENTIFIED BY '<AUTH_PASSWORD>';
GRANT SELECT (customer_id, email, password_hash) ON shop.customers TO 'auth_reader'@'localhost';

FLUSH PRIVILEGES;
