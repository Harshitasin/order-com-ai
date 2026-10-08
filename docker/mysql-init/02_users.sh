#!/bin/sh
# Runs once, the first time the MySQL container starts (after 01_schema.sql).
# Creates the three least-privilege users. '%' = any host, because in Docker the
# app connects from another container. Avoid quotes and $ characters in passwords.
set -e

RO_USER="${DB_RO_USER:-assistant_ro}"
AUDIT_USER="${DB_AUDIT_USER:-audit_writer}"
AUTH_USER="${DB_AUTH_USER:-auth_reader}"

mysql -uroot -p"$MYSQL_ROOT_PASSWORD" <<SQL
CREATE USER IF NOT EXISTS '${RO_USER}'@'%' IDENTIFIED BY '${DB_RO_PASS}';
GRANT SELECT ON shop.orders          TO '${RO_USER}'@'%';
GRANT SELECT ON shop.order_items     TO '${RO_USER}'@'%';
GRANT SELECT ON shop.shipments       TO '${RO_USER}'@'%';
GRANT SELECT ON shop.shipment_events TO '${RO_USER}'@'%';
GRANT SELECT ON shop.refunds         TO '${RO_USER}'@'%';
GRANT SELECT ON shop.policies        TO '${RO_USER}'@'%';

CREATE USER IF NOT EXISTS '${AUDIT_USER}'@'%' IDENTIFIED BY '${DB_AUDIT_PASS}';
GRANT INSERT ON shop.chat_audit_log TO '${AUDIT_USER}'@'%';

CREATE USER IF NOT EXISTS '${AUTH_USER}'@'%' IDENTIFIED BY '${DB_AUTH_PASS}';
GRANT SELECT (customer_id, email, password_hash) ON shop.customers TO '${AUTH_USER}'@'%';

FLUSH PRIVILEGES;
SQL
