import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

export function loadRootEnv() {
  const envPath = path.resolve(__dirname, "..", ".env");
  if (!fs.existsSync(envPath)) return;
  for (const line of fs.readFileSync(envPath, "utf8").split("\n")) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#") || !trimmed.includes("=")) continue;
    const i = trimmed.indexOf("=");
    const key = trimmed.slice(0, i).trim();
    const val = trimmed.slice(i + 1).trim();
    if (!process.env[key]) process.env[key] = val;
  }
}

export function haversineKm(lat1, lon1, lat2, lon2) {
  const r = 6371;
  const p1 = (lat1 * Math.PI) / 180;
  const p2 = (lat2 * Math.PI) / 180;
  const dphi = ((lat2 - lat1) * Math.PI) / 180;
  const dlmb = ((lon2 - lon1) * Math.PI) / 180;
  const a =
    Math.sin(dphi / 2) ** 2 + Math.cos(p1) * Math.cos(p2) * Math.sin(dlmb / 2) ** 2;
  return 2 * r * Math.asin(Math.min(1, Math.sqrt(a)));
}

function restHeaders() {
  const key = process.env.SUPABASE_SERVICE_ROLE;
  return {
    apikey: key,
    Authorization: "Bearer " + key,
  };
}

export async function supabaseSelect(tableQuery) {
  const base = (process.env.SUPABASE_URL || "").replace(/\/$/, "");
  const res = await fetch(base + "/rest/v1/" + tableQuery, { headers: restHeaders() });
  if (!res.ok) {
    const text = await res.text();
    throw new Error("Supabase " + res.status + " " + text.slice(0, 300));
  }
  return res.json();
}

export async function searchCities(q) {
  const term = (q || "").trim();
  if (term.length < 2) return [];
  const safe = term.replace(/[,()*%]/g, " ").slice(0, 40).trim();
  const pattern = "*" + safe + "*";
  const encoded = encodeURIComponent(pattern);
  return supabaseSelect(
    "cities?select=id,name,slug,latitude,longitude&is_active=eq.true&or=(name.ilike." +
      encoded +
      ",slug.ilike." +
      encoded +
      ")&limit=8"
  );
}

export async function fetchOutings(params) {
  const cityId = params.city_id && String(params.city_id).trim();
  const lat = Number(params.lat);
  const lon = Number(params.lon);
  const radius = Number(params.radius_km || 15);
  const budget = params.budget === "" || params.budget == null ? null : Number(params.budget);
  const type = params.type || "all";
  const indoor = params.indoor || "any";

  if (!cityId && !Number.isFinite(lat)) return [];

  const select =
    "id,city_id,kind,category,name,description,address,latitude,longitude,price_min,price_max,duration_minutes,indoor,photo_url,source_url,website_url";

  const chunks = [];
  if (cityId) {
    chunks.push(
      supabaseSelect(
        "outings?select=" +
          select +
          "&is_active=eq.true&city_id=eq." +
          encodeURIComponent(cityId) +
          "&limit=200"
      )
    );
  }
  if (Number.isFinite(lat) && Number.isFinite(lon) && radius > 0) {
    const dlat = radius / 111;
    const dlon = radius / (111 * Math.max(0.2, Math.cos((lat * Math.PI) / 180)));
    chunks.push(
      supabaseSelect(
        "outings?select=" +
          select +
          "&is_active=eq.true&latitude=gte." +
          (lat - dlat) +
          "&latitude=lte." +
          (lat + dlat) +
          "&longitude=gte." +
          (lon - dlon) +
          "&longitude=lte." +
          (lon + dlon) +
          "&limit=250"
      )
    );
  }

  const rows = (await Promise.all(chunks)).flat();
  const seen = new Set();
  const unique = [];
  for (const row of rows) {
    if (!row?.id || seen.has(row.id)) continue;
    seen.add(row.id);
    unique.push(row);
  }

  return unique.filter((row) => {
    if (row.latitude == null || row.longitude == null) return false;
    if (Number.isFinite(lat) && Number.isFinite(lon)) {
      const dist = haversineKm(lat, lon, row.latitude, row.longitude);
      row.distance_km = Math.round(dist * 10) / 10;
      if (dist > radius) return false;
    }
    const pmin = row.price_min == null ? 0 : Number(row.price_min);
    if (budget != null && Number.isFinite(budget) && pmin > budget) return false;
    if (type === "activites" && row.category !== "Activités et loisirs") return false;
    if (type === "evenements" && row.kind !== "event") return false;
    if (type === "restaurants" && row.category !== "Restaurants et cafés" && row.kind !== "restaurant")
      return false;
    if (type === "balades" && row.category !== "Lieux gratuits et balades" && row.kind !== "walk")
      return false;
    if (type === "soirees" && row.category !== "Soirées et concerts") return false;
    if (type === "culture" && row.category !== "Musées et culture") return false;
    if (indoor === "in" && row.indoor === false) return false;
    if (indoor === "out" && row.indoor === true) return false;
    return true;
  });
}
