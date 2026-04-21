-- Q1 2026 reconciliation: align prod DB with Henz's scratch decisions
-- from .claude/bookkeeping-draft/. One-shot script. Do NOT re-run after
-- months are locked.
--
-- 26 row updates total (12 Jan + 12 Feb + 2 Mar corrections).
-- Wrapped in BEGIN/COMMIT for atomicity — either all apply or none.

BEGIN;

-- ============================================================
-- JANUARY (12 updates)
-- ============================================================
UPDATE personal_transactions SET bucket='personal', t2125_line=NULL, category=NULL, user_note='Amazon refund', classified_by='user', classified_at=now(), updated_at=now()
  WHERE organization_id=(SELECT id FROM organizations WHERE slug='personal') AND source='AMEX' AND txn_date='2026-01-12' AND description='AMAZON Shop with Points' AND amount=-40;

UPDATE personal_transactions SET bucket='personal', t2125_line=NULL, category=NULL, user_note='MSSM personal', classified_by='user', classified_at=now(), updated_at=now()
  WHERE organization_id=(SELECT id FROM organizations WHERE slug='personal') AND source='AMEX' AND txn_date='2026-01-24' AND description='MSSM EDMONTON 001       EDMONTON' AND amount=11.03;

UPDATE personal_transactions SET bucket='personal', t2125_line=NULL, category=NULL, user_note='Vibe parking personal', classified_by='user', classified_at=now(), updated_at=now()
  WHERE organization_id=(SELECT id FROM organizations WHERE slug='personal') AND source='AMEX' AND txn_date='2026-01-24' AND description='VIBE PARKING            EDMONTON' AND amount=18;

UPDATE personal_transactions SET bucket='personal', t2125_line=NULL, category=NULL, user_note='MSSM personal', classified_by='user', classified_at=now(), updated_at=now()
  WHERE organization_id=(SELECT id FROM organizations WHERE slug='personal') AND source='AMEX' AND txn_date='2026-01-24' AND description='MSSM EDMONTON 001       EDMONTON' AND amount=76.70;

UPDATE personal_transactions SET bucket='personal', t2125_line=NULL, category=NULL, user_note='Personal retail', classified_by='user', classified_at=now(), updated_at=now()
  WHERE organization_id=(SELECT id FROM organizations WHERE slug='personal') AND source='AMEX' AND txn_date='2026-01-25' AND description='GLOBAL-E* ALO           VANCOUVER' AND amount=289.79;

UPDATE personal_transactions SET bucket='personal', t2125_line=NULL, category=NULL, user_note='UPS fee refund', classified_by='user', classified_at=now(), updated_at=now()
  WHERE organization_id=(SELECT id FROM organizations WHERE slug='personal') AND source='AMEX' AND txn_date='2026-01-27' AND description='UPS*                    888-520-9090' AND amount=-18.80;

UPDATE personal_transactions SET bucket='business', t2125_line='9200', category='Travel', user_note='Calgary airport hotel - business trip', classified_by='user', classified_at=now(), updated_at=now()
  WHERE organization_id=(SELECT id FROM organizations WHERE slug='personal') AND source='AMEX' AND txn_date='2026-01-30' AND description='SANDMAN CALGARY AIRPORT CALGARY' AND amount=265.68;

UPDATE personal_transactions SET bucket='personal', t2125_line=NULL, category=NULL, user_note='Personal rideshare', classified_by='user', classified_at=now(), updated_at=now()
  WHERE organization_id=(SELECT id FROM organizations WHERE slug='personal') AND source='AMEX' AND txn_date='2026-01-31' AND description='UBER TRIP               HTTPS://HELP.UB' AND amount=21.86;

UPDATE personal_transactions SET bucket='gift', t2125_line=NULL, category=NULL, user_note='Personal gift', classified_by='user', classified_at=now(), updated_at=now()
  WHERE organization_id=(SELECT id FROM organizations WHERE slug='personal') AND source='TD' AND txn_date='2026-01-12' AND description='TD ATM DEP    007702' AND amount=-1530;

UPDATE personal_transactions SET bucket='gift', t2125_line=NULL, category=NULL, user_note='Personal gift', classified_by='user', classified_at=now(), updated_at=now()
  WHERE organization_id=(SELECT id FROM organizations WHERE slug='personal') AND source='TD' AND txn_date='2026-01-19' AND description='E-TRANSFER ***ehp' AND amount=-1400;

UPDATE personal_transactions SET bucket='gift', t2125_line=NULL, category=NULL, user_note='Personal gift', classified_by='user', classified_at=now(), updated_at=now()
  WHERE organization_id=(SELECT id FROM organizations WHERE slug='personal') AND source='TD' AND txn_date='2026-01-22' AND description='E-TRANSFER ***Cby' AND amount=-150;

UPDATE personal_transactions SET bucket='gift', t2125_line=NULL, category=NULL, user_note='Personal gift', classified_by='user', classified_at=now(), updated_at=now()
  WHERE organization_id=(SELECT id FROM organizations WHERE slug='personal') AND source='TD' AND txn_date='2026-01-26' AND description='TD ATM DEP    008071' AND amount=-1400;

-- ============================================================
-- FEBRUARY (12 updates)
-- ============================================================
UPDATE personal_transactions SET bucket='personal', user_note='Restaurant', classified_by='user', classified_at=now(), updated_at=now()
  WHERE organization_id=(SELECT id FROM organizations WHERE slug='personal') AND source='AMEX' AND txn_date='2026-02-07' AND description='AMORE BISTRO            EDMONTON' AND amount=46.47;

UPDATE personal_transactions SET bucket='personal', user_note='Rideshare', classified_by='user', classified_at=now(), updated_at=now()
  WHERE organization_id=(SELECT id FROM organizations WHERE slug='personal') AND source='AMEX' AND txn_date='2026-02-10' AND description='UBER HOLDINGS CANADA IN TORONTO' AND amount=41.42;

UPDATE personal_transactions SET bucket='personal', user_note='PayPal personal', classified_by='user', classified_at=now(), updated_at=now()
  WHERE organization_id=(SELECT id FROM organizations WHERE slug='personal') AND source='AMEX' AND txn_date='2026-02-10' AND description='PAYPAL *SUPER           8777782321' AND amount=427.65;

UPDATE personal_transactions SET bucket='personal', user_note='Amazon refund', classified_by='user', classified_at=now(), updated_at=now()
  WHERE organization_id=(SELECT id FROM organizations WHERE slug='personal') AND source='AMEX' AND txn_date='2026-02-12' AND description='AMAZON Shop with Points' AND amount=-40;

UPDATE personal_transactions SET bucket='personal', user_note='Whoop annual', classified_by='user', classified_at=now(), updated_at=now()
  WHERE organization_id=(SELECT id FROM organizations WHERE slug='personal') AND source='AMEX' AND txn_date='2026-02-15' AND description='WHOOP                   BOSTON' AND amount=366.45;

UPDATE personal_transactions SET bucket='transfer', user_note='Interest reversal (not income)', classified_by='user', classified_at=now(), updated_at=now()
  WHERE organization_id=(SELECT id FROM organizations WHERE slug='personal') AND source='AMEX' AND txn_date='2026-02-18' AND description='INTEREST REVERSAL' AND amount=-24.77;

UPDATE personal_transactions SET bucket='business', user_note='Consulting income', classified_by='user', classified_at=now(), updated_at=now()
  WHERE organization_id=(SELECT id FROM organizations WHERE slug='personal') AND source='TD' AND txn_date='2026-02-02' AND description='E-TRANSFER ***5wh' AND amount=-1620;

UPDATE personal_transactions SET bucket='gift', user_note='Personal gift', classified_by='user', classified_at=now(), updated_at=now()
  WHERE organization_id=(SELECT id FROM organizations WHERE slug='personal') AND source='TD' AND txn_date='2026-02-09' AND description='E-TRANSFER ***ccQ' AND amount=-530;

UPDATE personal_transactions SET bucket='gift', user_note='Personal gift', classified_by='user', classified_at=now(), updated_at=now()
  WHERE organization_id=(SELECT id FROM organizations WHERE slug='personal') AND source='TD' AND txn_date='2026-02-11' AND description='E-TRANSFER ***aWz' AND amount=-1325;

UPDATE personal_transactions SET bucket='business', user_note='Consulting income', classified_by='user', classified_at=now(), updated_at=now()
  WHERE organization_id=(SELECT id FROM organizations WHERE slug='personal') AND source='TD' AND txn_date='2026-02-12' AND description='TD ATM DEP    004543' AND amount=-2045;

UPDATE personal_transactions SET bucket='gift', user_note='Personal gift', classified_by='user', classified_at=now(), updated_at=now()
  WHERE organization_id=(SELECT id FROM organizations WHERE slug='personal') AND source='TD' AND txn_date='2026-02-12' AND description='TD ATM DEP    004545' AND amount=-640;

UPDATE personal_transactions SET bucket='gift', user_note='Personal gift', classified_by='user', classified_at=now(), updated_at=now()
  WHERE organization_id=(SELECT id FROM organizations WHERE slug='personal') AND source='TD' AND txn_date='2026-02-24' AND description='TD ATM DEP    006428' AND amount=-1060;

-- ============================================================
-- MARCH (2 corrections)
-- ============================================================
UPDATE personal_transactions SET bucket='business', user_note='Consulting income', classified_by='user', classified_at=now(), updated_at=now()
  WHERE organization_id=(SELECT id FROM organizations WHERE slug='personal') AND source='TD' AND txn_date='2026-03-02' AND description='E-TRANSFER ***dSj' AND amount=-1550;

UPDATE personal_transactions SET bucket='gift', user_note='Personal gift', classified_by='user', classified_at=now(), updated_at=now()
  WHERE organization_id=(SELECT id FROM organizations WHERE slug='personal') AND source='TD' AND txn_date='2026-03-26' AND description='TD ATM DEP    006938' AND amount=-1840;

COMMIT;
