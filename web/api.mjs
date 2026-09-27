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
  const values = [lat1, lon1, lat2, lon2].map(Number);
  if (!values.every(Number.isFinite)) return Infinity;
  const [aLat, aLon, bLat, bLon] = values;
  const r = 6371;
  const p1 = (aLat * Math.PI) / 180;
  const p2 = (bLat * Math.PI) / 180;
  const dphi = ((bLat - aLat) * Math.PI) / 180;
  const dlmb = ((bLon - aLon) * Math.PI) / 180;
  const a = Math.sin(dphi / 2) ** 2 + Math.cos(p1) * Math.cos(p2) * Math.sin(dlmb / 2) ** 2;
  return 2 * r * Math.asin(Math.min(1, Math.sqrt(a)));
}

function restHeaders() {
  const key = process.env.SUPABASE_SERVICE_ROLE;
  return { apikey: key, Authorization: "Bearer " + key };
}

export async function supabaseSelect(tableQuery) {
  const base = (process.env.SUPABASE_URL || "").replace(/\/$/, "");
  if (!base || !process.env.SUPABASE_SERVICE_ROLE) {
    throw new Error("Base de données non configurée");
  }
  const res = await fetch(base + "/rest/v1/" + tableQuery, { headers: restHeaders() });
  if (!res.ok) {
    const text = await res.text();
    throw new Error("Catalogue indisponible (" + res.status + ")");
  }
  return res.json();
}

export async function searchCities(q) {
  const term = (q || "").trim();
  if (term.length < 2) return [];
  const safe = term.replace(/[,()*%]/g, " ").slice(0, 40).trim();
  const encoded = encodeURIComponent("*" + safe + "*");
  return supabaseSelect(
    "cities?select=id,name,slug,latitude,longitude&is_active=eq.true&or=(name.ilike." +
      encoded + ",slug.ilike." + encoded + ")&limit=8"
  );
}

export async function fetchOutings(params) {
  const cityId = params.city_id && String(params.city_id).trim();
  const lat = Number(params.lat);
  const lon = Number(params.lon);
  const radius = Number(params.radius_km || 15);
  const budget = params.budget === "" || params.budget == null ? null : Number(params.budget);
  
  // 🔧 MULTI-SELECT : Parser les types séparés par virgule
  const typeStr = String(params.type || "all").trim();
  const types = typeStr === "all" ? ["all"] : typeStr.split(",").map(t => t.trim()).filter(Boolean);
  
  const indoor = params.indoor || "any";
  if (!cityId && !Number.isFinite(lat)) return [];

  const select = "id,city_id,kind,category,name,description,address,latitude,longitude,price_min,price_max,currency,duration_minutes,indoor,photo_url,source_url,website_url";
  const chunks = [];
  if (cityId) chunks.push(supabaseSelect("outings?select=" + select + "&is_active=eq.true&city_id=eq." + encodeURIComponent(cityId) + "&limit=200"));
  if (Number.isFinite(lat) && Number.isFinite(lon) && radius > 0) {
    const dlat = radius / 111;
    const dlon = radius / (111 * Math.max(0.2, Math.cos((lat * Math.PI) / 180)));
    chunks.push(supabaseSelect("outings?select=" + select + "&is_active=eq.true&latitude=gte." + (lat - dlat) + "&latitude=lte." + (lat + dlat) + "&longitude=gte." + (lon - dlon) + "&longitude=lte." + (lon + dlon) + "&limit=250"));
  }
  const rows = (await Promise.all(chunks)).flat();
  const seen = new Set();
  return rows.filter((row) => {
    if (!row?.id || seen.has(row.id) || row.latitude == null || row.longitude == null) return false;
    seen.add(row.id);
    if (Number.isFinite(lat) && Number.isFinite(lon)) {
      const dist = haversineKm(lat, lon, row.latitude, row.longitude);
      row.distance_km = Math.round(dist * 10) / 10;
      if (dist > radius) return false;
    }
    if (budget != null && Number.isFinite(budget) && Number(row.price_min ?? 0) > budget) return false;
    
    // 🔧 MULTI-SELECT : Vérifier si la sortie correspond à AU MOINS UN type sélectionné
    if (!types.includes("all")) {
      const categoryMap = {
        "Restaurants et cafés": ["restaurants"],
        "Activités et loisirs": ["activites"],
        "Lieux gratuits et balades": ["balades"],
        "Soirées et concerts": ["soirees"],
        "Musées et culture": ["culture"],
      };
      const kindMap = {
        "restaurant": ["restaurants"],
        "event": ["evenements"],
        "walk": ["balades"],
      };
      
      const rowTypes = new Set([
        ...((categoryMap[row.category] || []) ),
        ...(kindMap[row.kind] || [])
      ]);
      
      // Au moins un type doit correspondre
      if (!types.some(t => rowTypes.has(t))) return false;
    }
    
    if (indoor === "in" && row.indoor === false) return false;
    if (indoor === "out" && row.indoor === true) return false;
    return true;
  });
}
