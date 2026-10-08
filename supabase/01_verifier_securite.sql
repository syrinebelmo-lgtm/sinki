-- SINKI — vérification de sécurité (LECTURE SEULE). À coller dans Supabase → SQL Editor → Run.
-- 1) Tables publiques sans RLS (Row Level Security) : n'importe qui possédant la clé "anon"
--    pourrait les lire/écrire via l'API. Résultat attendu après 02_activer_rls.sql : aucune ligne.
select schemaname, tablename, rowsecurity
from pg_tables
where schemaname = 'public' and rowsecurity = false
order by tablename;

-- 2) Politiques existantes (qui a le droit de faire quoi).
select tablename, policyname, roles, cmd
from pg_policies
where schemaname = 'public'
order by tablename, policyname;

-- 3) Taille de la base (le plan gratuit Supabase est limité à 500 Mo).
select pg_size_pretty(pg_database_size(current_database())) as taille_base;
select relname as table_name, pg_size_pretty(pg_total_relation_size(relid)) as taille
from pg_catalog.pg_statio_user_tables order by pg_total_relation_size(relid) desc limit 10;
