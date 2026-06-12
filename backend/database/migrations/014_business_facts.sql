-- Business facts / Company Brain
-- Plain-English facts Mo writes about AAKE — injected into every Claude prompt.
CREATE TABLE IF NOT EXISTS business_facts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    fact       TEXT    NOT NULL,
    category   TEXT    NOT NULL DEFAULT 'general',
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- Seed with sensible starter facts so the page isn't empty on first open
INSERT OR IGNORE INTO business_facts (id, fact, category, sort_order) VALUES
(1, 'We are AAKE, an IT reseller based in Kuwait.', 'company', 1),
(2, 'We resell Cisco, Fortinet, HP, and Microsoft products.', 'products', 1),
(3, 'Standard delivery lead time is 4–6 weeks for most products.', 'delivery', 1),
(4, 'We quote in KWD. Payment is typically 50% upfront, 50% on delivery.', 'terms', 1);
