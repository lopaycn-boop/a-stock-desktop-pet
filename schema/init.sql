-- CockroachDB schema for 小土豆 A股操盘手
-- Run: python scripts/init_db.py

CREATE TABLE IF NOT EXISTS markets (
  condition_id STRING PRIMARY KEY,
  question STRING NOT NULL,
  token_id_yes STRING NOT NULL,
  token_id_no STRING NOT NULL,
  price_yes DECIMAL(10, 4),
  price_no DECIMAL(10, 4),
  volume_24h DECIMAL(18, 2),
  spread_pct DECIMAL(10, 4),
  active BOOL DEFAULT true,
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS positions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  token_id STRING NOT NULL,
  condition_id STRING,
  side STRING NOT NULL,
  size DECIMAL(18, 6) NOT NULL,
  avg_entry DECIMAL(10, 4) NOT NULL,
  opened_at TIMESTAMPTZ DEFAULT now(),
  closed_at TIMESTAMPTZ,
  UNIQUE (token_id, closed_at)
);

CREATE INDEX IF NOT EXISTS idx_positions_open ON positions (token_id) WHERE closed_at IS NULL;

CREATE TABLE IF NOT EXISTS orders (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  client_order_id STRING UNIQUE NOT NULL,
  token_id STRING NOT NULL,
  condition_id STRING,
  side STRING NOT NULL,
  price DECIMAL(10, 4) NOT NULL,
  size DECIMAL(18, 6) NOT NULL,
  status STRING NOT NULL DEFAULT 'pending',
  clob_order_id STRING,
  dry_run BOOL DEFAULT false,
  error_message STRING,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_orders_status ON orders (status, created_at DESC);

CREATE TABLE IF NOT EXISTS agent_decisions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id STRING NOT NULL,
  action STRING NOT NULL,
  token_id STRING,
  condition_id STRING,
  price DECIMAL(10, 4),
  size DECIMAL(18, 6),
  reasoning STRING,
  model STRING DEFAULT 'potato-engine',
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_decisions_run ON agent_decisions (run_id, created_at DESC);

CREATE TABLE IF NOT EXISTS risk_limits (
  day DATE PRIMARY KEY,
  spent_cny DECIMAL(18, 2) NOT NULL DEFAULT 0,
  trade_count INT NOT NULL DEFAULT 0,
  circuit_breaker BOOL NOT NULL DEFAULT false,
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS cycle_runs (
  run_id STRING PRIMARY KEY,
  status STRING NOT NULL,
  summary JSONB,
  started_at TIMESTAMPTZ DEFAULT now(),
  finished_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS app_secrets (
  key STRING PRIMARY KEY,
  value STRING NOT NULL,
  category STRING NOT NULL DEFAULT 'credential',
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS platform_credentials (
  platform_id STRING PRIMARY KEY,
  encoded_fields STRING NOT NULL DEFAULT '{}',
  autonomous BOOL NOT NULL DEFAULT false,
  granted_at TIMESTAMPTZ DEFAULT now(),
  last_used_at TIMESTAMPTZ DEFAULT now()
);
