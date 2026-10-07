-- SINKI — activer la RLS sur toutes les tables publiques.
-- Sans risque pour l'app : le serveur SINKI utilise la clé service_role, qui ignore la RLS.
-- Effet : la clé "anon" (publique par nature) ne peut plus rien lire ni écrire directement,
-- notamment la table groups qui contient le store des comptes.
-- Réversible : "alter table public.<nom> disable row level security;"
do $$
declare t record;
begin
  for t in select tablename from pg_tables where schemaname = 'public' and rowsecurity = false loop
    execute format('alter table public.%I enable row level security', t.tablename);
    raise notice 'RLS activée sur %', t.tablename;
  end loop;
end $$;
