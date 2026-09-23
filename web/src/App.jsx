import { useEffect, useMemo, useState } from "react";

const TYPES = [
  ["all", "✨ Tout"],
  ["activites", "🎳 Activités"],
  ["evenements", "🎪 Événements"],
  ["restaurants", "☕ Restaurants"],
  ["balades", "🌿 Balades"],
  ["soirees", "🎵 Soirées"],
  ["culture", "🏛️ Culture"],
];
const VIBES = ["Détente", "Fun", "Culture", "Soirée", "Peu importe"];
const DURATIONS = [
  ["short", "1–2 h"],
  ["half", "Demi-journée"],
  ["full", "Toute la journée"],
];
const MOMENTS = [
  ["morning", "☀️ Matin"],
  ["afternoon", "🌤️ Après-midi"],
  ["evening", "🌙 Soirée"],
];
const RADII = [5, 15, 30];
const INDOORS = [
  ["any", "Peu importe"],
  ["in", "Intérieur"],
  ["out", "Extérieur"],
];
const TRANSPORTS = [
  ["walk", "🚶 À pied"],
  ["transit", "🚌 Transports"],
  ["car", "🚗 Voiture"],
];

const LS_FAV = "sinki-favs";
const LS_PLAN = "sinki-plans";
const LS_LAST = "sinki-last";

function todayISO() {
  return new Date().toISOString().slice(0, 10);
}
function addDays(n) {
  const d = new Date();
  d.setDate(d.getDate() + n);
  return d.toISOString().slice(0, 10);
}
function load(key) {
  try {
    return JSON.parse(localStorage.getItem(key) || "[]");
  } catch {
    return [];
  }
}
function save(key, val) {
  localStorage.setItem(key, JSON.stringify(val));
}
function euro(min, max) {
  if (min == null && max == null) return "Prix à confirmer";
  const a = Number(min ?? 0);
  const b = Number(max ?? a);
  if (a === 0 && b === 0) return "Gratuit";
  if (a === b) return a + " €";
  return a + "–" + b + " €";
}
function formatDate(iso) {
  try {
    return new Date(iso + "T12:00:00").toLocaleDateString("fr-FR", {
      weekday: "long",
      day: "numeric",
      month: "long",
    });
  } catch {
    return iso;
  }
}
function vibeMatch(outing, vibe) {
  if (!vibe || vibe === "Peu importe") return true;
  const blob = ((outing.category || "") + " " + (outing.kind || "")).toLowerCase();
  if (vibe === "Culture") return /cultur|musée|musee|heritage/.test(blob);
  if (vibe === "Soirée") return /soir|concert|night|bar/.test(blob);
  if (vibe === "Détente") return /balade|parc|gratuit|walk|spa/.test(blob);
  if (vibe === "Fun") return /loisir|activit|resto|escape|game|fun/.test(blob) || true;
  return true;
}
function durationOk(outing, duration) {
  const m = outing.duration_minutes;
  if (!m) return true;
  if (duration === "short") return m <= 150;
  if (duration === "half") return m <= 360;
  return true;
}
function pickThree(list, vibe) {
  const scored = list
    .filter((o) => vibeMatch(o, vibe))
    .map((o) => ({
      o,
      s:
        (o.photo_url ? 8 : 0) +
        (Number(o.price_min) === 0 ? 1 : 0) +
        Math.random() * 4,
    }))
    .sort((a, b) => b.s - a.s)
    .map((x) => x.o);
  const chosen = [];
  const cats = new Set();
  for (const item of scored) {
    const cat = item.category || item.name;
    if (chosen.length < 2 || !cats.has(cat)) {
      chosen.push(item);
      cats.add(cat);
    }
    if (chosen.length === 3) break;
  }
  while (chosen.length < 3 && scored[chosen.length]) chosen.push(scored[chosen.length]);
  return chosen.slice(0, 3);
}
function weatherLabel(code, temp) {
  if (temp == null) return "";
  const t = Math.round(temp) + "°";
  if (code <= 1) return "☀️ " + t;
  if (code <= 3) return "🌤️ " + t;
  if (code <= 67) return "🌧️ " + t;
  return "🌡️ " + t;
}

export default function App() {
  const [screen, setScreen] = useState("home");
  const [step, setStep] = useState(1);
  const [query, setQuery] = useState("");
  const [suggestions, setSuggestions] = useState([]);
  const [city, setCity] = useState(null);
  const [people, setPeople] = useState(2);
  const [date, setDate] = useState(todayISO());
  const [budget, setBudget] = useState(40);
  const [unlimited, setUnlimited] = useState(false);
  const [duration, setDuration] = useState("half");
  const [moment, setMoment] = useState("afternoon");
  const [radius, setRadius] = useState(15);
  const [type, setType] = useState("all");
  const [vibe, setVibe] = useState("Fun");
  const [indoor, setIndoor] = useState("any");
  const [transport, setTransport] = useState("transit");
  const [results, setResults] = useState([]);
  const [pool, setPool] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [detail, setDetail] = useState(null);
  const [favs, setFavs] = useState(() => load(LS_FAV));
  const [plans, setPlans] = useState(() => load(LS_PLAN));
  const [weather, setWeather] = useState("");

  useEffect(() => {
    if (query.trim().length < 2) {
      setSuggestions([]);
      return;
    }
    const t = setTimeout(async () => {
      const r = await fetch("/api/cities?q=" + encodeURIComponent(query.trim()));
      setSuggestions(await r.json());
    }, 180);
    return () => clearTimeout(t);
  }, [query]);

  const last = useMemo(() => {
    try {
      return JSON.parse(localStorage.getItem(LS_LAST) || "null");
    } catch {
      return null;
    }
  }, [screen]);

  function toggleFav(item) {
    setFavs((prev) => {
      const exists = prev.some((x) => x.id === item.id);
      const next = exists ? prev.filter((x) => x.id !== item.id) : [item, ...prev];
      save(LS_FAV, next);
      return next;
    });
  }
  function planItem(item) {
    const row = { ...item, planned_for: date };
    setPlans((prev) => {
      const next = [row, ...prev.filter((x) => x.id !== item.id)];
      save(LS_PLAN, next);
      return next;
    });
  }
  function isFav(id) {
    return favs.some((x) => x.id === id);
  }

  async function search(fromLast) {
    const c = fromLast?.city || city;
    if (!c) return;
    setLoading(true);
    setError("");
    const budgetVal = fromLast ? fromLast.budget : unlimited ? "" : budget;
    const qs = new URLSearchParams({
      city_id: String(c.id),
      lat: String(c.latitude),
      lon: String(c.longitude),
      radius_km: String(fromLast?.radius || radius),
      type: fromLast?.type || type,
      indoor: fromLast?.indoor || indoor,
    });
    if (budgetVal !== "" && budgetVal != null) qs.set("budget", String(budgetVal));
    try {
      const [outRes, wRes] = await Promise.all([
        fetch("/api/outings?" + qs.toString()),
        fetch("/api/weather?lat=" + c.latitude + "&lon=" + c.longitude),
      ]);
      const rows = await outRes.json();
      if (!outRes.ok) throw new Error(rows.error || "Erreur réseau");
      const filtered = (rows || []).filter((o) => durationOk(o, fromLast?.duration || duration));
      setPool(filtered);
      const three = pickThree(filtered, fromLast?.vibe || vibe);
      setResults(three);
      const w = await wRes.json();
      setWeather(weatherLabel(w.current?.weather_code, w.current?.temperature_2m));
      const payload = {
        city: c,
        people,
        date,
        budget: unlimited ? null : budget,
        duration,
        moment,
        radius,
        type,
        vibe,
        indoor,
        transport,
      };
      localStorage.setItem(LS_LAST, JSON.stringify(payload));
      setScreen("results");
    } catch (err) {
      setError(String(err.message || err));
    } finally {
      setLoading(false);
    }
  }

  function Card({ item }) {
    return (
      <article className="card">
        <div
          className={"cover" + (item.photo_url ? "" : " empty")}
          style={item.photo_url ? { backgroundImage: "url(" + item.photo_url + ")" } : undefined}
        >
          {!item.photo_url ? "🦌" : null}
          <button className="heart" onClick={() => toggleFav(item)} aria-label="favori">
            {isFav(item.id) ? "♥" : "♡"}
          </button>
        </div>
        <div className="card-body">
          <div className="cat">{item.category || "Sortie"}</div>
          <h2>{item.name}</h2>
          <div className="meta">
            {euro(item.price_min, item.price_max)}
            {item.distance_km != null ? " · " + item.distance_km + " km" : ""}
            {item.duration_minutes ? " · " + item.duration_minutes + " min" : ""}
            {item.indoor === true ? " · Intérieur" : item.indoor === false ? " · Extérieur" : ""}
          </div>
          <div className="why">
            Pourquoi cette sortie ? {unlimited ? "Aucun plafond de budget" : "Respecte votre budget de " + budget + " €"}
            {" · "}adaptée à {people} {people > 1 ? "personnes" : "personne"}
            {item.photo_url ? "" : " · photo indisponible côté source"}
          </div>
          <button className="linkish" onClick={() => setDetail(item)}>
            Voir la sortie →
          </button>
        </div>
      </article>
    );
  }

  return (
    <div className="shell">
      <header className="topbar">
        {screen === "home" ? <span /> : (
          <button className="icon-btn" onClick={() => (step === 2 && screen === "search" ? setStep(1) : setScreen(screen === "results" ? "search" : "home"))}>
            ←
          </button>
        )}
        <div className="brand">Sinki</div>
        <span style={{ width: 40 }} />
      </header>

      {screen === "home" && (
        <div className="home">
          <img className="biche" src="/biche-sinki.png" alt="Mascotte biche de Sinki" />
          <h1>On fait quoi aujourd’hui ?</h1>
          <p className="lead">Trois sorties faites pour votre groupe, votre budget et votre humeur.</p>
          <button className="btn" onClick={() => { setScreen("search"); setStep(1); }}>
            Commencer
          </button>
          {last?.city && (
            <button
              className="btn secondary"
              onClick={() => {
                setCity(last.city);
                setQuery(last.city.name);
                setPeople(last.people || 2);
                setBudget(last.budget || 40);
                setUnlimited(last.budget == null);
                setVibe(last.vibe || "Fun");
                search(last);
              }}
            >
              ↻ Reprendre ma dernière recherche
              <small>{last.city.name} · {last.budget == null ? "budget libre" : last.budget + " € max"} · {last.vibe}</small>
            </button>
          )}
          <button className="btn outline" onClick={() => setScreen("favs")}>♥ Mes favoris</button>
          <button className="btn sand" onClick={() => setScreen("plans")}>📅 Mes sorties prévues</button>
        </div>
      )}

      {screen === "search" && step === 1 && (
        <div className="page">
          <div className="step">1 sur 2</div>
          <h1>D’où partez-vous ?</h1>
          <p className="lead">Indiquez votre point de départ pour trouver des sorties proches de vous.</p>
          <label>Point de départ</label>
          <input
            type="text"
            placeholder="Commencez à taper une ville"
            value={query}
            onChange={(e) => { setQuery(e.target.value); setCity(null); }}
          />
          {suggestions.length > 0 && (
            <div className="suggest">
              {suggestions.map((c) => (
                <button key={c.id} onClick={() => { setCity(c); setQuery(c.name); setSuggestions([]); }}>
                  {c.name}
                </button>
              ))}
            </div>
          )}
          <button
            className="btn secondary"
            style={{ marginTop: 12 }}
            onClick={() => {
              navigator.geolocation.getCurrentPosition((pos) => {
                setCity({
                  id: "",
                  name: "Autour de moi",
                  latitude: pos.coords.latitude,
                  longitude: pos.coords.longitude,
                });
                setQuery("Autour de moi");
                setSuggestions([]);
              });
            }}
          >
            ⌖ Utiliser ma position
          </button>
          <p className="hint">Votre position sert uniquement à cette recherche et n’est pas enregistrée.</p>
          <label>Nombre de participants</label>
          <div className="people">
            <button className="icon-btn" onClick={() => setPeople((n) => Math.max(1, n - 1))}>−</button>
            <span>{people} {people > 1 ? "personnes" : "personne"}</span>
            <button className="icon-btn" onClick={() => setPeople((n) => Math.min(12, n + 1))}>+</button>
          </div>
          <div className="sticky">
            <button className="btn" disabled={!city} onClick={() => setStep(2)}>Continuer</button>
          </div>
        </div>
      )}

      {screen === "search" && step === 2 && (
        <div className="page">
          <div className="step">2 sur 2</div>
          <h1>Qu’est-ce qui vous ferait plaisir ?</h1>
          <p className="lead">Quelques choix et Sinki s’occupe du reste.</p>
          <label>Date de la sortie</label>
          <input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
          <div className="row" style={{ marginTop: 8 }}>
            <button className={"chip" + (date === todayISO() ? " on" : "")} onClick={() => setDate(todayISO())}>Aujourd’hui</button>
            <button className={"chip" + (date === addDays(1) ? " on" : "")} onClick={() => setDate(addDays(1))}>Demain</button>
            <button className={"chip" + (date === addDays(7) ? " on" : "")} onClick={() => setDate(addDays(7))}>Dans 1 semaine</button>
          </div>
          <label>Budget par personne</label>
          <div className="budget-val">{unlimited ? "Illimité" : budget === 0 ? "Gratuit" : budget + " € max"}</div>
          <input
            type="range"
            min="0"
            max="200"
            step="5"
            value={unlimited ? 200 : budget}
            onChange={(e) => { setUnlimited(false); setBudget(Number(e.target.value)); }}
          />
          <div className="row">
            <button className={"chip" + (!unlimited && budget === 0 ? " on" : "")} onClick={() => { setUnlimited(false); setBudget(0); }}>Gratuit</button>
            <button className={"chip" + (!unlimited && budget === 25 ? " on" : "")} onClick={() => { setUnlimited(false); setBudget(25); }}>25 €</button>
            <button className={"chip" + (!unlimited && budget === 60 ? " on" : "")} onClick={() => { setUnlimited(false); setBudget(60); }}>60 €</button>
            <button className={"chip" + (unlimited ? " on" : "")} onClick={() => setUnlimited(true)}>Illimité</button>
          </div>
          <p className="hint">Pas de plafond global : de 0 € au premium.</p>
          <label>Temps disponible</label>
          <div className="row">{DURATIONS.map(([id, label]) => (
            <button key={id} className={"chip" + (duration === id ? " on" : "")} onClick={() => setDuration(id)}>{label}</button>
          ))}</div>
          <label>Moment de la sortie</label>
          <div className="row">{MOMENTS.map(([id, label]) => (
            <button key={id} className={"chip" + (moment === id ? " on" : "")} onClick={() => setMoment(id)}>{label}</button>
          ))}</div>
          <label>Distance maximale</label>
          <div className="row">{RADII.map((km) => (
            <button key={km} className={"chip" + (radius === km ? " on" : "")} onClick={() => setRadius(km)}>{km} km</button>
          ))}</div>
          <label>Type de sortie</label>
          <div className="row">{TYPES.map(([id, label]) => (
            <button key={id} className={"chip" + (type === id ? " on" : "")} onClick={() => setType(id)}>{label}</button>
          ))}</div>
          <label>Quelle ambiance ?</label>
          <div className="row">{VIBES.map((v) => (
            <button key={v} className={"chip" + (vibe === v ? " on" : "")} onClick={() => setVibe(v)}>{v}</button>
          ))}</div>
          <label>Lieu</label>
          <div className="row">{INDOORS.map(([id, label]) => (
            <button key={id} className={"chip" + (indoor === id ? " on" : "")} onClick={() => setIndoor(id)}>{label}</button>
          ))}</div>
          <label>Transport</label>
          <div className="row">{TRANSPORTS.map(([id, label]) => (
            <button key={id} className={"chip" + (transport === id ? " on" : "")} onClick={() => setTransport(id)}>{label}</button>
          ))}</div>
          {error && <p className="empty">{error}</p>}
          <div className="sticky">
            <button className="btn" disabled={loading} onClick={() => search()}>
              {loading ? "Je cherche…" : "Trouver mes 3 sorties"}
            </button>
          </div>
        </div>
      )}

      {screen === "results" && (
        <div className="page">
          {weather && <div className="weather">{weather} à {city?.name}</div>}
          <p className="lead" style={{ marginBottom: 0 }}>Pour {people} {people > 1 ? "amis" : "personne"} · {city?.name}</p>
          <h1>Vos 3 sorties</h1>
          <p className="lead">📅 {formatDate(date)} · {unlimited ? "budget libre" : budget + " € max"} · {vibe}</p>
          {results.length === 0 && <p className="empty">Aucune sortie ne matche ces critères. Élargis la distance, le budget ou le type.</p>}
          {results.map((item) => <Card key={item.id} item={item} />)}
          <button
            className="btn"
            onClick={() => {
              if (!pool.length) return;
              const pick = pool[Math.floor(Math.random() * pool.length)];
              setResults([pick]);
            }}
          >
            🎲 Sinki choisit pour nous
            <small>Une sortie au hasard qui respecte vos critères</small>
          </button>
          <button
            className="btn sand"
            onClick={() => {
              setUnlimited(false);
              setBudget((b) => Math.max(0, b - 15));
              setTimeout(() => search(), 0);
            }}
          >
            💶 Trouver des options moins chères
          </button>
          <button
            className="btn outline"
            onClick={async () => {
              const text = results.map((r, i) => i + 1 + ". " + r.name + " — " + euro(r.price_min, r.price_max)).join("\n");
              const payload = { title: "Sinki", text: "On hésite entre :\n" + text };
              if (navigator.share) await navigator.share(payload);
              else await navigator.clipboard.writeText(payload.text);
            }}
          >
            Partager et faire voter
          </button>
          <button className="ghost" onClick={() => { setScreen("search"); setStep(2); }}>Modifier mes critères</button>
        </div>
      )}

      {screen === "favs" && (
        <div className="page">
          <h1>Mes favoris</h1>
          {favs.length === 0 && <p className="empty">Encore vide. Ajoute un ♥ sur une sortie.</p>}
          {favs.map((item) => <Card key={item.id} item={item} />)}
        </div>
      )}

      {screen === "plans" && (
        <div className="page">
          <h1>Mes sorties prévues</h1>
          {plans.length === 0 && <p className="empty">Rien de prévu pour l’instant.</p>}
          {plans.map((item) => (
            <div key={item.id}>
              <p className="hint">📅 {item.planned_for ? formatDate(item.planned_for) : ""}</p>
              <Card item={item} />
            </div>
          ))}
        </div>
      )}

      {detail && (
        <div className="sheet" onClick={() => setDetail(null)}>
          <div className="sheet-card" onClick={(e) => e.stopPropagation()}>
            <div className="cat">{detail.category}</div>
            <h1 style={{ fontSize: 30 }}>{detail.name}</h1>
            <p className="meta">{euro(detail.price_min, detail.price_max)}</p>
            {detail.address && <p>{detail.address}</p>}
            {detail.description && <p className="lead">{detail.description}</p>}
            <a className="btn" href={"https://maps.google.com/?q=" + detail.latitude + "," + detail.longitude} target="_blank" rel="noreferrer">
              Ouvrir dans Maps
            </a>
            {detail.website_url || detail.source_url ? (
              <a className="btn outline" href={detail.website_url || detail.source_url} target="_blank" rel="noreferrer">
                Site / source
              </a>
            ) : null}
            <button className="btn sand" onClick={() => { planItem(detail); setDetail(null); setScreen("plans"); }}>
              📅 Ajouter à mes sorties prévues
            </button>
            <button className="ghost" onClick={() => setDetail(null)}>Fermer</button>
          </div>
        </div>
      )}
    </div>
  );
}
