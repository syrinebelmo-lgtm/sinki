-- SINKI — structure du nouveau projet Supabase (gratuit, < 500 Mo).
-- Mêmes tables que l'ancien projet, sans les 2,4 millions de clones "nearby".
-- RLS activée partout : seul le serveur SINKI (clé service_role) lit et écrit.

create extension if not exists pg_trgm;

create table public.cities (
  id bigint primary key,
  name text not null,
  slug text not null,
  country_code character(2) not null default 'FR',
  latitude double precision not null,
  longitude double precision not null,
  is_active boolean not null default true,
  created_at timestamptz not null default now()
);
create index cities_slug_idx on public.cities (slug);
create index cities_country_idx on public.cities (country_code);
create index cities_name_trgm_idx on public.cities using gin (name gin_trgm_ops);
create index cities_geo_idx on public.cities (latitude, longitude);

create table public.outings (
  id uuid primary key default gen_random_uuid(),
  city_id bigint not null references public.cities (id),
  kind text not null default 'place',
  category text not null,
  subcategory text,
  name text not null,
  description text,
  address text,
  latitude double precision not null,
  longitude double precision not null,
  price_min numeric,
  price_max numeric,
  currency character(3) not null default 'EUR',
  duration_minutes integer,
  indoor boolean,
  reservation_required boolean,
  min_participants integer,
  max_participants integer,
  vibes text[] not null default '{}',
  transport_modes text[] not null default '{}',
  opening_hours jsonb not null default '{}',
  event_starts_at timestamptz,
  event_ends_at timestamptz,
  website_url text,
  booking_url text,
  photo_url text,
  photo_credit text,
  photo_license text,
  source_name text not null default 'manual',
  source_id text,
  source_url text,
  is_active boolean not null default true,
  verified_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  image_url text,
  image_alt text,
  image_credit text,
  image_source_url text
);
create index outings_city_idx on public.outings (city_id) where is_active;
create index outings_geo_idx on public.outings (latitude, longitude) where is_active;
create index outings_category_idx on public.outings (category) where is_active;
create index outings_name_trgm_idx on public.outings using gin (name gin_trgm_ops);

create table public.groups (
  id uuid primary key default gen_random_uuid(),
  share_code text not null unique,
  origin_label text,
  origin_latitude double precision,
  origin_longitude double precision,
  participant_count integer not null default 1,
  filters jsonb not null default '{}',
  candidate_outing_ids uuid[] not null default '{}',
  status text not null default 'open',
  winner_outing_id uuid references public.outings (id) on delete set null,
  expires_at timestamptz not null default (now() + interval '7 days'),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index groups_origin_label_idx on public.groups (origin_label);

create table public.group_members (
  id uuid primary key default gen_random_uuid(),
  group_id uuid not null references public.groups (id) on delete cascade,
  display_name text not null,
  member_token uuid not null default gen_random_uuid(),
  joined_at timestamptz not null default now()
);
create index group_members_token_idx on public.group_members (member_token);

create table public.favorites (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null,
  outing_id uuid not null references public.outings (id) on delete cascade,
  created_at timestamptz not null default now()
);
create index favorites_user_idx on public.favorites (user_id);

alter table public.cities enable row level security;
alter table public.outings enable row level security;
alter table public.groups enable row level security;
alter table public.group_members enable row level security;
alter table public.favorites enable row level security;
