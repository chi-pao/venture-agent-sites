CREATE TABLE IF NOT EXISTS travel_trips (
 id TEXT PRIMARY KEY,
 plan_json TEXT NOT NULL,
 version INTEGER NOT NULL DEFAULT 1,
 edit_hash TEXT NOT NULL,
 view_hash TEXT NOT NULL,
 created_at INTEGER NOT NULL,
 updated_at INTEGER NOT NULL,
 expires_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS travel_expiry_idx ON travel_trips(expires_at);
CREATE TABLE IF NOT EXISTS travel_create_limits (
 day TEXT PRIMARY KEY,
 count INTEGER NOT NULL
);
