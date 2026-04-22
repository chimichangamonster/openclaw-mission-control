-- Seed Personal org chat_suggestions — Layer 1 override for the trading/betting
-- prompt set. Personal has no industry_template_id, so without this seed it
-- would fall through to the generic fallback in
-- GET /org-config/chat-suggestions/resolved. Idempotent via uq_org_config_cat_key.
--
-- One-shot: do NOT re-run after initial apply. To edit suggestions, use the
-- admin UI or PUT /org-config/chat_suggestions/{key}.

INSERT INTO org_config_data (
    id, organization_id, category, key, label, value_json, sort_order, is_active, created_at, updated_at
)
SELECT
    gen_random_uuid(),
    o.id,
    'chat_suggestions',
    v.key,
    v.label,
    v.value_json,
    v.sort_order,
    TRUE,
    NOW(),
    NOW()
FROM organizations o
CROSS JOIN (VALUES
    ('market_today',    'Market today',       '{"prompt": "What''s the market doing today?"}', 0),
    ('pending_bets',    'Pending sports bets','{"prompt": "Any pending sports bets?"}',        1),
    ('check_email',     'Check my email',     '{"prompt": "Check my email"}',                   2),
    ('review_q',        'Review the quarter', '{"prompt": "How did my bookkeeping look this quarter?"}', 3)
) AS v(key, label, value_json, sort_order)
WHERE o.slug = 'personal'
ON CONFLICT ON CONSTRAINT uq_org_config_cat_key DO NOTHING;
