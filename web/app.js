const $ = (sel, root = document) => root.querySelector(sel);
const app = $("#app");

const RADII = [5, 15, 30];

function loadLang() {
  const saved = localStorage.getItem("sinki-lang") || "";
  if (saved) return saved;
  return "fr";
}
function langBase(code) {
  return String(code || "fr").toLowerCase().split("-")[0];
}
function hasPack(code) {
  const packs = window.SINKI_I18N || {};
  const b = langBase(code);
  return Boolean(packs[code] || packs[b]);
}
function t(key, vars) {
  const packs = window.SINKI_I18N || {};
  const code = langBase(state.lang || "fr");
  const pack = packs[state.lang] || packs[code] || {};
  let s = pack[key] || packs.en[key] || packs.fr[key] || key;
  if (vars) {
    Object.keys(vars).forEach((k) => {
      s = s.split("{" + k + "}").join(String(vars[k] ?? ""));
    });
  }
  return s;
}
function applyDocumentLang() {
  const code = langBase(state.lang || "fr");
  document.documentElement.lang = state.lang || "fr";
  document.documentElement.dir = window.SINKI_RTL && window.SINKI_RTL[code] ? "rtl" : "ltr";
}
function vibeId(v) {
  const map = { "Détente": "relax", "Fun": "fun", "Culture": "culture", "Soirée": "party", "Peu importe": "any" };
  if (!v) return "fun";
  return map[v] || v;
}
function typeList() {
  return [
    ["all", "✨ " + t("type_all")],
    ["activites", "🎳 " + t("type_act")],
    ["evenements", "🎪 " + t("type_evt")],
    ["restaurants", "☕ " + t("type_rest")],
    ["shopping", "🛍️ " + t("type_shop")],
    ["randonnee", "🥾 " + t("type_hike")],
    ["balades", "🌿 " + t("type_walk")],
    ["soirees", "🎵 " + t("type_night")],
    ["culture", "🏛️ " + t("type_cult")],
  ];
}
function vibeList() {
  return [
    ["relax", t("vibe_relax")],
    ["fun", t("vibe_fun")],
    ["culture", t("vibe_culture")],
    ["party", t("vibe_party")],
    ["any", t("vibe_any")],
  ];
}
function durationList() {
  return [["short", t("dur_short")], ["half", t("dur_half")], ["full", t("dur_full")]];
}
function momentList() {
  return [["morning", "☀️ " + t("mom_morn")], ["afternoon", "🌤️ " + t("mom_aft")], ["evening", "🌙 " + t("mom_eve")]];
}
function indoorList() {
  return [["any", t("in_any")], ["in", t("in_in")], ["out", t("in_out")]];
}
function transportList() {
  return [["walk", "🚶 " + t("tr_walk")], ["transit", "🚌 " + t("tr_transit")], ["car", "🚗 " + t("tr_car")]];
}

const state = {
  intro: true,
  screen: "home",
  lang: loadLang(),
  langQ: "",
  step: 1,
  query: "",
  suggestions: [],
  city: null,
  people: 2,
  alts: [],
  searchNote: "",
  date: todayISO(),
  budget: 40,
  unlimited: false,
  duration: "half",
  moment: "afternoon",
  radius: 15,
  area: "france",
  intCountry: null,
  countryQuery: "",
  countrySuggestions: [],
  type: "all",
  vibe: "fun",
  indoor: "any",
  transport: "transit",
  results: [],
  pool: [],
  loading: false,
  error: "",
  detail: null,
  favs: load("sinki-favs"),
  plans: load("sinki-plans"),
  weather: "",
  exploreQ: "",
  exploreCities: [],
  exploreOutings: [],
  exploreIntent: "",
  exploreScope: localStorage.getItem("sinki-explore-scope") === "world" ? "world" : "home",
  homeCountry: loadHomeCountry(),
  exploreCountry: null,
  exploreCity: null,
  exploreCityQ: "",
  explorePickHome: false,
  groupCode: localStorage.getItem("sinki-group-code") || "",
  groupNick: localStorage.getItem("sinki-nick") || "",
  groupLabel: "",
  groupChat: [],
  groupPoll: null,
  groupVotes: {},
  shareHint: "",
  shareBusy: false,
  nearestFallback: false,
  routeFrom: "search",
  geoBusy: false,
  account: loadObj("sinki-account"),
  session: loadObj("sinki-session"),
  plan: "free",
  plusPeriod: localStorage.getItem("sinki-plus-period") || "year",
  unlimitedPeriod: localStorage.getItem("sinki-unlimited-period") || "year",
  paywall: false,
  payFamily: "plus",
  billingBusy: "",
  billingHint: "",
  storePrices: null,
  myEvents: [],
  publicEvents: [],
  pendingEvents: [],
  isModerator: false,
  eventDraft: null,
  eventPhoto: "",
  eventId: "",
  eventBoostDays: 0,
  geoCountryTried: false,
  authView: "closed",
  authMode: "login",
  authEmail: "",
  authFirst: "",
  authLast: "",
  authPseudo: "",
  authCode: "",
  authBusy: false,
  authError: "",
  authHint: "",
  settingsView: "menu",
  accountDeleteAsk: false,
  profileHint: "",
  notifsPlans: localStorage.getItem("sinki-notifs-plans") !== "0",
  notifsGroup: localStorage.getItem("sinki-notifs-group") !== "0",
};

function todayISO() {
  return new Date().toISOString().slice(0, 10);
}
function addDays(n) {
  const d = new Date();
  d.setDate(d.getDate() + n);
  return d.toISOString().slice(0, 10);
}
function load(key) {
  try { return JSON.parse(localStorage.getItem(key) || "[]"); } catch { return []; }
}
function loadObj(key) {
  try { return JSON.parse(localStorage.getItem(key) || "null"); } catch { return null; }
}
function loadHomeCountry() {
  try {
    const o = JSON.parse(localStorage.getItem("sinki-home-country") || "null");
    if (o && o.code) return { code: String(o.code).toUpperCase(), name: o.name || o.code };
  } catch { /* ignore */ }
  return { code: "FR", name: "France" };
}
function applyHomeArea() {
  const code = (state.homeCountry?.code || "FR").toUpperCase();
  const name = state.homeCountry?.name || code;
  if (code === "FR") {
    state.area = "france";
    state.intCountry = null;
  } else {
    state.area = "international";
    state.intCountry = { code, name };
  }
}
function entitlements() {
  return (state.account && state.account.entitlements) || {};
}
function liveEnt(kind) {
  const row = entitlements()[kind];
  if (!row || !row.active) return null;
  return row;
}
function hasPlus() {
  return Boolean(liveEnt("plus")) || (state.account && state.account.plan === "plus");
}
function hasUnlimited() {
  return Boolean(liveEnt("unlimited"));
}
function hasNoAds() {
  return Boolean(liveEnt("no_ads"));
}
function adsAllowed() {
  return !hasNoAds();
}
const FREE_DAY_CAP = 6;
function loadQuota() {
  const q = loadObj("sinki-quota") || {};
  const day = todayISO();
  if (q.day !== day || !Array.isArray(q.ids)) return { day, ids: [] };
  return { day, ids: q.ids };
}
function remainingToday() {
  if (hasUnlimited()) return 99;
  return Math.max(0, FREE_DAY_CAP - loadQuota().ids.length);
}
function recordFound(rows) {
  if (hasUnlimited()) return rows || [];
  const q = loadQuota();
  const out = [];
  (rows || []).forEach((row) => {
    if (!row || !row.id) return;
    if (q.ids.includes(row.id)) {
      out.push(row);
      return;
    }
    if (q.ids.length >= FREE_DAY_CAP) return;
    q.ids.push(row.id);
    out.push(row);
  });
  save("sinki-quota", q);
  return out;
}
function askQuota() {
  if (hasUnlimited() || remainingToday() > 0) return false;
  openPaywall("quota");
  return true;
}
function askPlus(reason) {
  if (hasPlus()) return false;
  openPaywall(reason || "world");
  return true;
}
function eventFee(key) {
  const pack = (window.SINKI_CATALOG || {}).event || {};
  const row = pack[key] || pack[String(key)] || {};
  return Number(row.eur || 0);
}
function openPaywall(reason) {
  state.paywall = reason || "catalog";
  state.payFamily = reason === "quota" ? "unlimited" : reason === "event" ? "event" : reason === "ads" ? "noads" : "plus";
  state.billingHint = "";
  if (!state.plusPeriod) state.plusPeriod = "year";
  if (!state.unlimitedPeriod) state.unlimitedPeriod = "year";
  render();
}
function eventCredits() {
  return Math.max(0, Number(localStorage.getItem("sinki-event-credits") || 0));
}
function addEventCredit() {
  localStorage.setItem("sinki-event-credits", String(eventCredits() + 1));
}
function useEventCredit() {
  const n = eventCredits();
  if (n < 1) return false;
  localStorage.setItem("sinki-event-credits", String(n - 1));
  return true;
}
function askEventPay() {
  return false;
}
function paywallHtml() {
  if (!state.paywall) return "";
  const title = state.paywall === "quota" ? t("plus_quota_title")
    : state.paywall === "world" ? t("plus_title")
    : state.paywall === "event" ? t("pay_org_title")
    : t("pay_title");
  const lead = state.paywall === "quota" ? t("plus_quota", { n: FREE_DAY_CAP })
    : state.paywall === "world" ? t("plus_lead", { country: state.homeCountry?.name || t("france") })
    : state.paywall === "event" ? t("pay_event_lead")
    : t("pay_catalog_lead");
  return `<div class="sheet"><div class="sheet-bg" data-act="close-paywall"></div><div class="sheet-card pay-sheet">
    ${mascot("emerveillee", lead)}
    <h1 style="font-size:28px">${title}</h1>
    ${tariffsBody()}
    <button class="ghost" data-act="close-paywall">${t("close")}</button>
  </div></div>`;
}
function displayProductPrice(prod) {
  const store = state.storePrices && prod && state.storePrices[prod.id];
  if (store && store.label) return store.label;
  return formatFee(prod && prod.eur);
}
function ownsFamilyPeriod(family, period) {
  if (family === "plus") return Boolean(liveEnt("plus") && liveEnt("plus").period === period);
  if (family === "unlimited") return Boolean(liveEnt("unlimited") && liveEnt("unlimited").period === period);
  if (family === "noads") return hasNoAds();
  return false;
}
function subCardsHtml(family) {
  const pack = (window.SINKI_CATALOG || {})[family] || {};
  const selected = family === "plus" ? (state.plusPeriod || "year") : (state.unlimitedPeriod || "year");
  const weekEur = pack.week && pack.week.eur;
  return ["week", "month", "year"].map((period) => {
    const prod = pack[period];
    if (!prod) return "";
    const save = window.sinkiSavePct ? window.sinkiSavePct(weekEur, prod.eur, period) : 0;
    const featured = period === "year";
    const owned = ownsFamilyPeriod(family, period);
    const label = period === "week" ? t("plus_week") : period === "month" ? t("plus_month") : t("plus_year");
    const saveBadge = save > 0 ? `<span class="pay-save">${t("pay_save", { n: save })}</span>` : "";
    const best = featured ? `<span class="pay-badge">${t("pay_best")}</span>` : "";
    return `<button type="button" class="price-card${featured ? " featured" : ""}${selected === period ? " on" : ""}" data-act="pay-period" data-family="${family}" data-id="${period}">
      <span class="price-card-top">${escapeHtml(label)}${best}${saveBadge}</span>
      <span class="price-val">${escapeHtml(displayProductPrice(prod))}</span>
      ${owned ? `<span class="hint">${t("pay_active")}</span>` : ""}
    </button>`;
  }).join("");
}
function buySubBtn(family) {
  const period = family === "plus" ? (state.plusPeriod || "year") : (state.unlimitedPeriod || "year");
  const prod = ((window.SINKI_CATALOG || {})[family] || {})[period];
  if (!prod) return "";
  const owned = ownsFamilyPeriod(family, period);
  const busy = state.billingBusy === prod.id;
  if (owned) return `<button class="btn" disabled>${t("pay_already")}</button>`;
  return `<button class="btn" data-act="pay-buy" data-id="${escapeHtml(prod.id)}" ${busy || state.billingBusy ? "disabled" : ""}>${busy ? t("pay_loading") : t("pay_buy")}</button>`;
}
function tariffsBody() {
  const fam = state.payFamily || "plus";
  const hint = state.billingHint ? `<p class="${/ok|actif/i.test(state.billingHint) || state.billingHint === t("pay_ok") ? "hint" : "empty"}">${escapeHtml(state.billingHint)}</p>` : "";
  const tabs = `<div class="row">
    <button class="chip${fam === "plus" ? " on" : ""}" data-act="pay-family" data-id="plus">${t("set_plan_plus")}</button>
    <button class="chip${fam === "unlimited" ? " on" : ""}" data-act="pay-family" data-id="unlimited">${t("pay_unlim")}</button>
    <button class="chip${fam === "event" ? " on" : ""}" data-act="pay-family" data-id="event">${t("pay_org")}</button>
    <button class="chip${fam === "noads" ? " on" : ""}" data-act="pay-family" data-id="noads">${t("pay_noads")}</button>
  </div>`;
  let block = "";
  if (fam === "plus") {
    block = `<p class="hint">${t("set_plan_plus_lead")}</p>
      ${subCardsHtml("plus")}
      ${buySubBtn("plus")}`;
  } else if (fam === "unlimited") {
    block = `<p class="hint">${t("pay_unlim_lead")}</p>
      ${subCardsHtml("unlimited")}
      ${buySubBtn("unlimited")}`;
  } else if (fam === "event") {
    const pub = ((window.SINKI_CATALOG || {}).event || {}).publish;
    const extras = [3, 7, 30];
    block = `<p class="hint">${t("pay_event_lead")}</p>
      <div class="account-card">
        <p class="hint" style="margin-top:0"><strong>${t("ev_boost_included", { price: displayProductPrice(pub) })}</strong></p>
        <p class="hint">${t("pay_event_then")}</p>
        <button class="btn" data-act="pay-buy" data-id="${escapeHtml(pub && pub.id || "sinki.event.publish")}" ${state.billingBusy ? "disabled" : ""}>${state.billingBusy === (pub && pub.id) ? t("pay_loading") : t("pay_buy")}</button>
      </div>
      <p class="hint">${t("ev_boost_extra")}</p>
      ${extras.map((d) => {
        const prod = ((window.SINKI_CATALOG || {}).event || {})[d];
        const label = d === 30 ? t("ev_boost_month") : t("ev_boost_days", { n: d });
        return `<div class="account-card">
          <p class="hint" style="margin-top:0"><strong>${escapeHtml(label)}</strong> · ${escapeHtml(displayProductPrice(prod))}</p>
        </div>`;
      }).join("")}`;
  } else {
    const prod = ((window.SINKI_CATALOG || {}).noads || {}).lifetime;
    block = `<div class="account-card">
        <p class="hint" style="margin-top:0"><strong>${t("pay_noads")}</strong></p>
        <p class="hint">${t("pay_noads_once")}</p>
        <p class="price-val">${escapeHtml(displayProductPrice(prod))}</p>
        ${hasNoAds() ? `<p class="hint">${t("pay_active")}</p><button class="btn" disabled>${t("pay_already")}</button>`
          : `<button class="btn" data-act="pay-buy" data-id="${escapeHtml(prod && prod.id || "sinki.noads.lifetime")}" ${state.billingBusy ? "disabled" : ""}>${state.billingBusy === (prod && prod.id) ? t("pay_loading") : t("pay_buy")}</button>`}
      </div>`;
  }
  return `${tabs}${block}${hint}
    <button class="ghost" data-act="pay-restore">${state.billingBusy === "restore" ? t("pay_loading") : t("pay_restore")}</button>`;
}
function saveHomeCountry(c, manual) {
  state.homeCountry = { code: String(c.code || "FR").toUpperCase(), name: c.name || c.code };
  localStorage.setItem("sinki-home-country", JSON.stringify(state.homeCountry));
  if (manual) localStorage.setItem("sinki-home-country-manual", "1");
  applyHomeArea();
}
function onHomeArea() {
  const code = (state.homeCountry?.code || "FR").toUpperCase();
  if (code === "FR") return state.area === "france";
  return Boolean(state.intCountry && String(state.intCountry.code).toUpperCase() === code);
}
function detectHomeCountry() {
  if (state.geoCountryTried) return;
  if (hasPlus() && localStorage.getItem("sinki-home-country-manual") === "1") return;
  state.geoCountryTried = true;
  fetch("/api/geo")
    .then((r) => r.json())
    .then((data) => {
      if (!data || !data.code) return;
      const code = String(data.code).toUpperCase();
      if (state.homeCountry && state.homeCountry.code === code) return;
      saveHomeCountry({ code, name: data.name || code }, false);
      render();
    })
    .catch(() => {});
}
function exploreCountryCode() {
  if (state.exploreScope === "home") return (state.homeCountry?.code || "FR").toUpperCase();
  return (state.exploreCountry?.code || "").toUpperCase();
}
function save(key, val) {
  localStorage.setItem(key, JSON.stringify(val));
}
function toEur(amount, currency) {
  const rate = FX_TO_EUR[String(currency || "EUR").toUpperCase()];
  const val = Number(amount ?? 0);
  if (!Number.isFinite(val)) return 0;
  if (rate == null) return val <= 80 ? val : val * 0.03;
  return val * rate;
}
const FX_TO_EUR = {
  EUR: 1, CHF: 1.05, GBP: 1.17, USD: 0.92, CAD: 0.67, AUD: 0.61, JPY: 0.0062,
  CNY: 0.13, KRW: 0.00068, THB: 0.027, INR: 0.011, IDR: 0.000056, MYR: 0.21,
  SGD: 0.71, PHP: 0.016, VND: 0.000037, AED: 0.25, TRY: 0.027, BRL: 0.17,
  MXN: 0.048, PLN: 0.23, CZK: 0.041, SEK: 0.087, NOK: 0.085, DKK: 0.13,
  MAD: 0.092, TND: 0.30,
};
const COUNTRY_CURRENCY = {
  FR: "EUR", DE: "EUR", ES: "EUR", IT: "EUR", BE: "EUR", NL: "EUR", PT: "EUR",
  AT: "EUR", IE: "EUR", FI: "EUR", GR: "EUR", LU: "EUR", SK: "EUR", SI: "EUR",
  EE: "EUR", LV: "EUR", LT: "EUR", MT: "EUR", CY: "EUR", HR: "EUR", MC: "EUR",
  AD: "EUR", SM: "EUR", VA: "EUR", ME: "EUR", XK: "EUR",
  CH: "CHF", LI: "CHF", GB: "GBP", US: "USD", CA: "CAD", AU: "AUD",
  JP: "JPY", CN: "CNY", KR: "KRW", TH: "THB", IN: "INR", ID: "IDR", MY: "MYR",
  SG: "SGD", PH: "PHP", VN: "VND", AE: "AED", TR: "TRY", BR: "BRL", MX: "MXN",
  PL: "PLN", CZ: "CZK", SE: "SEK", NO: "NOK", DK: "DKK", MA: "MAD", TN: "TND",
};
function homeCurrency() {
  const cc = (state.homeCountry?.code || "FR").toUpperCase();
  return COUNTRY_CURRENCY[cc] || "EUR";
}
function fromEur(eur, code) {
  const rate = FX_TO_EUR[String(code || "EUR").toUpperCase()];
  const val = Number(eur ?? 0);
  if (!Number.isFinite(val)) return 0;
  if (!rate || String(code).toUpperCase() === "EUR") return val;
  return val / rate;
}
function formatFee(eurAmount) {
  const code = homeCurrency();
  const eurTxt = Number(eurAmount).toFixed(2).replace(".", ",") + " €";
  if (code === "EUR") return eurTxt;
  const local = fromEur(eurAmount, code);
  const rounded = ["JPY", "KRW", "VND", "IDR"].indexOf(code) >= 0
    ? String(Math.round(local))
    : Number(local).toFixed(2);
  return eurTxt + " (" + rounded + " " + code + ")";
}
function moneyNum(n) {
  const v = Number(n);
  if (!Number.isFinite(v)) return 0;
  return Math.abs(v - Math.round(v)) < 0.05 ? Math.round(v) : Math.round(v * 10) / 10;
}
function euroRange(a, b) {
  if (a === 0 && b === 0) return t("free");
  if (a === 0 && b > 0) return "<1–" + b + " €";
  if (a === b) return a + " €";
  return a + "–" + b + " €";
}
function isResto(d) {
  return Boolean(d && ((d.category || "").indexOf("Restaurant") >= 0 || d.kind === "restaurant"));
}
function priceLabel(d) {
  if (!d) return t("price_confirm");
  if (!isResto(d)) return euro(d.price_min, d.price_max, d.currency);
  const rawA = Number(d.price_min);
  const rawB = Number(d.price_max);
  const hasA = d.price_min != null && Number.isFinite(rawA) && rawA > 0;
  const hasB = d.price_max != null && Number.isFinite(rawB) && rawB > 0;
  if (!hasA && !hasB) return t("price_confirm");
  const lo = hasA ? d.price_min : d.price_max;
  const hi = hasB ? d.price_max : d.price_min;
  return euro(lo, hi, d.currency);
}
function localRange(min, max, code) {
  const a = moneyNum(min ?? 0);
  const b = moneyNum(max ?? min ?? 0);
  if (a === b) return a + " " + code;
  return a + "–" + b + " " + code;
}
function euro(min, max, currency) {
  if (min == null && max == null) return t("price_confirm");
  const code = String(currency || "EUR").toUpperCase();
  const rawA = Number(min ?? 0);
  const rawB = Number(max ?? min ?? 0);
  if (!Number.isFinite(rawA) || !Number.isFinite(rawB)) return t("price_confirm");
  let a = Math.round(toEur(min ?? 0, code));
  let b = Math.round(toEur(max ?? min, code));
  if (a === 0 && rawA > 0) a = 1;
  if (b === 0 && rawB > 0) b = 1;
  const eurTxt = euroRange(a, b);
  if (eurTxt === t("free") || eurTxt === "Gratuit") return t("free");
  if (code === "EUR" || !code) return eurTxt;
  return eurTxt + " (" + localRange(min, max, code) + ")";
}
function bringNote(d) {
  const bits = [];
  if (d && d.need_tickets) bits.push(t("bring_tickets"));
  if (d && d.need_id) bits.push(t("bring_id"));
  return bits.join(" ");
}
function cityLabel(c) {
  if (!c) return "";
  if (c.country_code && c.country_code !== "FR") return c.name + " · " + c.country_code;
  return c.name;
}
function chatDisplayName() {
  const acc = state.account;
  const first = (acc && acc.first_name ? String(acc.first_name) : "").trim();
  if (first) return first.slice(0, 40);
  const typed = ($("#nick") && $("#nick").value.trim()) || String(state.groupNick || "").trim();
  if (typed) return typed.slice(0, 40);
  const nick = (acc && acc.nick ? String(acc.nick) : "").trim();
  if (nick) return nick.slice(0, 40);
  return "Pote";
}
function foldName(s) {
  return String(s || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .trim();
}
function pickExactCity(typed, rows) {
  const q = foldName(typed);
  if (!q || !Array.isArray(rows)) return null;
  return rows.find((c) => foldName(c.name) === q) || null;
}
const citySuggestCache = new Map();
const cityFeatured = {};
function cityCacheKey(cc, q) {
  return String(cc || "") + "|" + foldName(q);
}
function filterCityRows(rows, typed) {
  const q = foldName(typed);
  if (!q || !Array.isArray(rows) || !rows.length) return [];
  const seen = new Set();
  const out = [];
  for (const c of rows) {
    const name = foldName(c.name);
    const slug = foldName(c.slug);
    const hit = name.startsWith(q) || slug.startsWith(q) || (q.length > 2 && (name.includes(q) || slug.includes(q)));
    const id = c.id || c.slug || c.name;
    if (!hit || seen.has(id)) continue;
    seen.add(id);
    out.push(c);
    if (out.length >= 12) break;
  }
  return out;
}
function localCityHits(cc, typed) {
  const q = foldName(typed);
  if (!cc || !q) return [];
  const exact = citySuggestCache.get(cityCacheKey(cc, q));
  if (exact && exact.length) return exact;
  const pool = [];
  if (cityFeatured[cc]) pool.push(...cityFeatured[cc]);
  for (let i = q.length; i >= 1; i--) {
    const hit = citySuggestCache.get(cityCacheKey(cc, q.slice(0, i)));
    if (hit && hit.length) {
      pool.push(...hit);
      break;
    }
  }
  return filterCityRows(pool, typed);
}
function rememberCityHits(cc, typed, rows) {
  if (!cc || !Array.isArray(rows)) return;
  citySuggestCache.set(cityCacheKey(cc, typed), rows);
  if (!String(typed || "").trim() && rows.length) cityFeatured[cc] = rows;
}
function prefetchFeaturedCities() {
  const cc = countryParam();
  if (!cc || cityFeatured[cc]) return;
  fetch("/api/cities?country=" + encodeURIComponent(cc) + "&q=")
    .then((r) => r.json())
    .then((rows) => {
      if (Array.isArray(rows) && rows.length) {
        cityFeatured[cc] = rows;
        rememberCityHits(cc, "", rows);
      }
    })
    .catch(() => {});
}
function syncCityContinue() {
  const go = document.querySelector('[data-act="to2"]');
  if (go) go.disabled = !state.city;
}
function countryParam() {
  if (onHomeArea()) return (state.homeCountry?.code || "FR").toUpperCase();
  if (state.area === "france") return "FR";
  return state.intCountry?.code || "";
}
function citySuggestHtml() {
  if (!state.suggestions.length) return "";
  return `<div class="suggest">${state.suggestions.map((c) => `<button data-city="${encodeURIComponent(JSON.stringify(c))}">${escapeHtml(c.name)}</button>`).join("")}</div>`;
}
function countrySuggestHtml() {
  if (!state.countrySuggestions.length) return "";
  return `<div class="suggest">${state.countrySuggestions.map((c) => `<button data-country="${encodeURIComponent(JSON.stringify(c))}">${escapeHtml(c.name)}</button>`).join("")}</div>`;
}
function exploreCitySuggestHtml() {
  const typed = ((state.exploreScope === "world" && !state.exploreCity ? state.exploreCityQ : state.exploreQ) || "").trim();
  if (typed.length < 1 || !state.exploreCities.length) return "";
  return `<div class="suggest">${state.exploreCities.map((c) => `<button data-explore-city="${encodeURIComponent(JSON.stringify(c))}">${escapeHtml(cityLabel(c))}</button>`).join("")}</div>`;
}
function exploreResultsHtml() {
  if (state.explorePickHome || (state.exploreScope === "world" && !state.exploreCountry)) {
    return countrySuggestHtml();
  }
  if (state.exploreScope === "world" && state.exploreCountry && !state.exploreCity) {
    return exploreCitySuggestHtml();
  }
  const q = (state.exploreQ || "").trim();
  const mine = (q.length >= 1 && state.exploreScope === "home" && !state.explorePickHome) ? liveEvents() : [];
  const boosted = mine.filter((ev) => ev.boosted);
  const restEv = mine.filter((ev) => !ev.boosted);
  const listed = [...boosted, ...restEv, ...(state.exploreOutings || []).filter((o) => !mine.some((b) => b.id === o.id))];
  return `${exploreCitySuggestHtml()}${listed.length ? listed.map((item) => cardHtml(item, "explore")).join("") : ""}`;
}
function searchStepLiveHtml() {
  if (state.area === "international" && !state.intCountry) return countrySuggestHtml();
  return citySuggestHtml();
}
function paintLiveSearch() {
  const box = $("#live-search");
  if (!box) {
    render();
    return;
  }
  if (state.screen === "explore") box.innerHTML = exploreResultsHtml();
  else if (state.screen === "settings" && state.settingsView === "home-country") box.innerHTML = countrySuggestHtml();
  else if (state.screen === "search" && state.step === 1) box.innerHTML = searchStepLiveHtml();
  else render();
}
function formatDate(iso) {
  return new Date(iso + "T12:00:00").toLocaleDateString(state.lang || "fr", { weekday: "long", day: "numeric", month: "long" });
}
function lastSearch() {
  try { return JSON.parse(localStorage.getItem("sinki-last") || "null"); } catch { return null; }
}
function chips(list, current, onPick) {
  return `<div class="row">${list.map(([id, label]) =>
    `<button class="chip${current === id ? " on" : ""}" data-pick="${onPick}" data-id="${id}">${label}</button>`
  ).join("")}</div>`;
}
function isFav(id) {
  return state.favs.some((x) => x.id === id);
}
function boostChoices() {
  return [
    [3, t("ev_boost_days", { n: 3 }), eventFee(3)],
    [7, t("ev_boost_days", { n: 7 }), eventFee(7)],
    [30, t("ev_boost_month"), eventFee(30)],
  ];
}
function boostListHtml(selected, pick) {
  return `<div class="set-list">${boostChoices().map(([d, label, fee]) =>
    `<button type="button" class="set-row${Number(selected) === d ? " on" : ""}"${pick ? ` data-act="event-boost" data-id="${d}"` : ""}><span>${escapeHtml(label)}</span><span class="set-extra">${escapeHtml(formatFee(fee))}</span></button>`
  ).join("")}</div>`;
}
function eventStatusLabel(ev) {
  if (ev.status === "pending") return t("ev_pending");
  if (ev.status === "rejected") return t("ev_rejected");
  if (ev.boosted) return t("ev_boost_on");
  if (ev.status === "approved") return t("ev_approved");
  return t("ev_pending");
}
function cardHtml(item, mode) {
  const cover = item.photo_url
    ? `<div class="cover" style="background-image:url('${String(item.photo_url).replace(/'/g, "%27")}')">`
    : `<div class="cover empty">🦌`;
  const why = mode === "guided"
        ? `<div class="why">${t("why")} ${item.category === "Shopping" || state.type === "shopping" ? t("why_shop") : state.type === "randonnee" ? t("why_hike") : state.unlimited ? t("why_unlim") : t("why_budget", { n: state.budget })} · ${t("why_people", { n: state.people, who: state.people > 1 ? t("persons") : t("person") })}${item.distance_km != null ? " · " + item.distance_km + " km" : ""}${item.photo_url ? "" : " · " + t("why_nophoto")}</div>`
    : "";
  return `<article class="card${item.boosted ? " is-boost" : ""}" data-id="${item.id}" data-detail="${item.id}">
    ${cover}
      ${item.boosted ? `<span class="boost-tag">${t("ev_boost_tag")}</span>` : ""}
      <button class="heart" data-fav="${item.id}">${isFav(item.id) ? "♥" : "♡"}</button>
    </div>
    <div class="card-body">
      <div class="cat">${escapeHtml(item.category || t("outing"))}${item.boosted ? " · " + t("ev_boost_tag") : ""}</div>
      <h2>${escapeHtml(item.name)}</h2>
      <div class="meta">${priceLabel(item)}${item.distance_km != null ? " · " + item.distance_km + " km" : ""}</div>
      ${isEventItem(item) ? eventSocialHtml(item) : ""}
      ${why}
      <button class="linkish" data-detail="${item.id}">${t("see_all")}</button>
      <button class="linkish" data-route="${item.id}">${t("go_there")}</button>
      <button class="linkish" data-send-group="${item.id}">${t("send_g")}</button>
    </div>
  </article>`;
}
function isEventItem(item) {
  return !!(item && (item.kind === "event" || item.category === "Événements temporaires"));
}
function eventSocialHtml(item) {
  const n = Number(item.like_count || 0);
  const c = (item.comments || []).length;
  return `<div class="ev-social">
    <button type="button" class="like-btn${item.liked ? " on" : ""}" data-like="${escapeHtml(item.id)}">${item.liked ? "♥" : "♡"} ${n}</button>
    <span>${t("ev_comments_n", { n: c })}</span>
  </div>`;
}
function eventCommentsHtml(d) {
  const rows = d.comments || [];
  return `<div class="ev-thread">
    <p class="hint" style="margin-top:12px"><strong>${t("ev_comments")}</strong></p>
    ${rows.length ? rows.map((c) => `<p class="ev-comment"><strong>${escapeHtml(c.nick || "Sinki")}</strong> ${escapeHtml(c.text || "")}</p>`).join("") : `<p class="hint">${t("ev_comments_empty")}</p>`}
    <label>${t("ev_comment")}</label>
    <textarea id="evcomment" rows="2" maxlength="280" placeholder="${escapeHtml(t("ev_comment_ph"))}"></textarea>
    <button class="btn secondary" data-act="event-comment">${t("ev_comment_send")}</button>
  </div>`;
}
function applyEventRow(row) {
  if (!row || !row.id) return;
  const patch = (list) => {
    const i = (list || []).findIndex((x) => x.id === row.id);
    if (i >= 0) list[i] = { ...list[i], ...row };
  };
  patch(state.publicEvents);
  patch(state.myEvents);
  patch(state.exploreOutings);
  patch(state.results);
  patch(state.favs);
  if (state.detail && state.detail.id === row.id) state.detail = { ...state.detail, ...row };
}
async function needEventAccount() {
  if (state.session?.access_token) return false;
  state.screen = "account";
  state.authHint = t("ev_social_login");
  render();
  return true;
}
async function toggleEventLike(id) {
  if (await needEventAccount()) return;
  const r = await fetch("/api/events/like", {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify({ id }),
  });
  if (r.status === 401) {
    await needEventAccount();
    return;
  }
  if (!r.ok) return;
  applyEventRow(await r.json());
  render();
}
async function sendEventComment() {
  if (await needEventAccount()) return;
  const id = state.detail && state.detail.id;
  const text = ($("#evcomment") && $("#evcomment").value || "").trim();
  if (!id || !text) return;
  const r = await fetch("/api/events/comment", {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify({ id, text }),
  });
  if (r.status === 401) {
    await needEventAccount();
    return;
  }
  if (!r.ok) return;
  applyEventRow(await r.json());
  render();
}
function decodeText(s) {
  return String(s ?? "").replace(/\\u([0-9a-fA-F]{4})/gi, (_, hex) =>
    String.fromCharCode(parseInt(hex, 16))
  );
}
function escapeHtml(s) {
  return decodeText(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}
function legalHtml(key) {
  return t(key).split("\n\n").filter(Boolean).map((p) => `<p class="hint">${escapeHtml(p)}</p>`).join("");
}
function liveEvents() {
  const now = Date.now();
  return (state.publicEvents || []).filter((ev) => ev.status === "approved").map((ev) => {
    const boostUntil = Number(ev.boostUntil || 0);
    return {
      ...ev,
      category: ev.category || "Événements temporaires",
      kind: "event",
      boosted: boostUntil > now,
      boostUntil,
    };
  });
}
function boostedEvents() {
  return liveEvents().filter((ev) => ev.boosted);
}
function findOuting(id) {
  return [...state.results, ...state.pool, ...state.exploreOutings, ...state.favs, ...state.plans, ...liveEvents()].find((x) => x.id === id);
}
function startPoint() {
  if (state.city && state.city.latitude != null && state.city.longitude != null) return state.city;
  const last = lastSearch();
  return last?.city && last.city.latitude != null ? last.city : null;
}
function mapsTravelMode(transport) {
  return { walk: "walking", transit: "transit", car: "driving" }[transport] || "transit";
}
function directionsUrl(dest, origin, transport) {
  const params = new URLSearchParams({
    api: "1",
    destination: dest.latitude + "," + dest.longitude,
    travelmode: mapsTravelMode(transport),
  });
  if (origin && origin.latitude != null && origin.longitude != null) {
    params.set("origin", origin.latitude + "," + origin.longitude);
  }
  return "https://www.google.com/maps/dir/?" + params.toString();
}
function geoErrorMessage(err) {
  const code = err && err.code;
  if (code === 1) return t("geo_denied");
  if (code === 3) return t("geo_slow");
  if (code === 2) return t("geo_miss");
  return (err && err.message) || t("geo_fail");
}
function getGeoOrigin() {
  return new Promise((resolve, reject) => {
    if (!navigator.geolocation) {
      reject(new Error(t("geo_off")));
      return;
    }
    const ok = (pos) => resolve({ latitude: pos.coords.latitude, longitude: pos.coords.longitude, name: t("around_me") });
    const fail = (err) => reject(Object.assign(new Error(geoErrorMessage(err)), { code: err && err.code }));
    navigator.geolocation.getCurrentPosition(ok, fail, { enableHighAccuracy: false, timeout: 5000, maximumAge: 300000 });
  });
}
async function applyMyPosition() {
  if (state.geoBusy) return;
  state.geoBusy = true;
  render();
  const timed = (p, ms) => Promise.race([
    p,
    new Promise((_, reject) => setTimeout(() => reject(new Error("timeout")), ms)),
  ]);
  try {
    let origin = null;
    try {
      origin = await timed(getGeoOrigin(), 7000);
    } catch (err) {
      try {
        const r = await timed(fetch("https://ipapi.co/json/"), 5000);
        const j = await r.json();
        if (j && j.latitude != null && j.longitude != null) {
          origin = {
            latitude: Number(j.latitude),
            longitude: Number(j.longitude),
            name: j.city || t("around_me"),
          };
        }
      } catch (_) {}
      if (!origin) throw err;
    }
    let city = {
      id: "",
      name: origin.name || t("around_me"),
      latitude: origin.latitude,
      longitude: origin.longitude,
    };
    try {
      const near = await fetch("/api/cities/near?lat=" + origin.latitude + "&lon=" + origin.longitude);
      const row = await near.json();
      if (row && row.id && row.latitude != null) city = row;
    } catch (_) {}
    state.city = city;
    state.query = city.name || t("around_me");
    state.suggestions = [];
    state.routeFrom = "geo";
    if (city.country_code && city.country_code !== "FR") {
      state.area = "international";
      state.intCountry = { code: city.country_code, name: city.country_name || city.country_code };
    } else {
      state.area = "france";
      state.intCountry = null;
    }
  } catch (err) {
    alert(geoErrorMessage(err));
  } finally {
    state.geoBusy = false;
    render();
  }
}
async function openDirections(dest) {
  if (!dest || dest.latitude == null || dest.longitude == null) {
    alert(t("no_gps"));
    return;
  }
  let origin = null;
  if (state.routeFrom === "geo") {
    try {
      origin = await getGeoOrigin();
    } catch (err) {
      alert(err.message || String(err));
      return;
    }
  } else {
    origin = startPoint();
    if (!origin) {
      try {
        origin = await getGeoOrigin();
      } catch (err) {
        alert(t("pick_city"));
        return;
      }
    }
  }
  window.open(directionsUrl(dest, origin, state.transport), "_blank", "noopener,noreferrer");
}
function kindLabel(kind) {
  return {
    event: t("kind_event"),
    restaurant: t("kind_rest"),
    walk: t("kind_walk"),
    place: t("kind_place"),
  }[kind] || (kind ? String(kind) : t("unknown"));
}
function indoorLabel(indoor) {
  if (indoor === true) return t("indoor_yes");
  if (indoor === false) return t("indoor_no");
  return t("indoor_unk");
}
function durationLabel(minutes) {
  const n = Number(minutes);
  if (!Number.isFinite(n) || n <= 0) return t("dur_unk");
  if (n < 60) return n + " min";
  const h = Math.floor(n / 60);
  const m = Math.round(n % 60);
  return m ? h + " h " + m + " min" : h + " h";
}
function sourceLabel(name) {
  const key = String(name || "").toLowerCase();
  if (key === "osm") return "OpenStreetMap";
  if (key === "nearby") return "Catalogue Sinki (sortie proche)";
  if (key === "datatourisme") return "DATAtourisme";
  if (!key) return "Non renseignée";
  return name;
}
function loadPlaceStory(item) {
  const qs = new URLSearchParams({
    name: item.name || "",
    source_id: item.source_id || "",
    category: item.category || "",
  });
  if (item.latitude != null) qs.set("lat", String(item.latitude));
  if (item.longitude != null) qs.set("lon", String(item.longitude));
  fetch("/api/place-story?" + qs.toString())
    .then((r) => r.json())
    .then((data) => {
      const story = (data && data.story) || "";
      if (state.detail && state.detail.id === item.id) {
        const next = { ...state.detail, story: story || outingPitch({ ...item, storyBusy: false }), storyBusy: false };
        if (data && data.need_tickets != null) next.need_tickets = data.need_tickets;
        if (data && data.need_id) next.need_id = true;
        if (data && data.price_min != null && Number(data.price_min) > 0) {
          next.price_min = data.price_min;
          next.price_max = data.price_max != null && Number(data.price_max) > 0 ? data.price_max : data.price_min;
        } else if (data && data.price_unknown === false && data.price_min === 0 && !isResto(next)) {
          next.price_min = 0;
          next.price_max = 0;
        }
        state.detail = next;
        render();
      }
      const patch = { story: story || undefined, storyBusy: false };
      [state.results, state.pool, state.exploreOutings, state.favs, state.plans].forEach((list) => {
        const found = list.find((x) => x.id === item.id);
        if (found && story) found.story = story;
      });
    })
    .catch(() => {
      if (state.detail && state.detail.id === item.id) {
        state.detail = { ...state.detail, storyBusy: false };
        render();
      }
    });
}
function outingPitch(d) {
  if (d.story) return d.story;
  const written = String(d.description || "").trim();
  if (written) return written;
  if (d.storyBusy) return t("story_loading");
  const name = d.name || "Ce lieu";
  const cat = d.category || "sortie";
  const where = d.address ? " On le trouve " + d.address + "." : "";
  const dist = d.distance_km != null ? " À " + d.distance_km + " km de toi." : "";
  const price = " Compte " + priceLabel(d) + ".";
  if (cat.indexOf("Soirée") >= 0) {
    return name + " est un spot pour un verre, de la musique ou une nuit dehors." + where + dist + price + " Idéal pour poser le rythme de la soirée, pas juste passer devant.";
  }
  if (cat.indexOf("Restaurant") >= 0) {
    return name + " est une adresse pour manger ensemble." + where + dist + price + " Le genre d’endroit où on s’attable, on commande, on discute.";
  }
  if (cat.indexOf("Shopping") >= 0) {
    return name + " est une adresse shopping." + where + dist + " Fripes, boutiques ou grand magasin : on vient chiner, pas faire les courses.";
  }
  if (cat.indexOf("Musée") >= 0 || cat.indexOf("Culture") >= 0) {
    return name + " est un lieu de culture." + where + dist + price + " On y va pour l’ambiance, les œuvres ou l’histoire du quartier.";
  }
  if (cat.indexOf("Randonn") >= 0) {
    return name + " est un itinéraire nature." + where + dist + " Chaussures, un peu d’air, et on avance.";
  }
  if (cat.indexOf("balade") >= 0 || cat.indexOf("Balade") >= 0) {
    return name + " est une pause dehors, souvent gratuite." + where + dist + " Parfait pour marcher, s’asseoir, regarder la ville.";
  }
  return name + " est une sortie « " + cat + " »." + where + dist + price;
}
function factRow(label, value) {
  const text = (value == null || String(value).trim() === "") ? t("unknown") : String(value);
  return `<div class="fact"><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(text)}</dd></div>`;
}
function mapsPlaceUrl(d) {
  if (d.latitude == null || d.longitude == null) return "";
  return "https://www.google.com/maps/search/?api=1&query=" + encodeURIComponent(d.latitude + "," + d.longitude);
}
function detailSheetHtml(d) {
  const cover = d.photo_url
    ? `<div class="sheet-cover" style="background-image:url('${String(d.photo_url).replace(/'/g, "%27")}')"></div>`
    : `<div class="sheet-cover empty">🦌</div>`;
  const site = d.website_url || d.source_url;
  const mapUrl = mapsPlaceUrl(d);
  return `<div class="sheet"><div class="sheet-bg" data-act="close-sheet"></div><div class="sheet-card">
      ${cover}
      <div class="cat">${escapeHtml(d.category || t("outing"))}</div>
      <h1 style="font-size:30px">${escapeHtml(d.name || t("outing"))}</h1>
      <p class="meta">${priceLabel(d)}</p>
      <p class="lead">${escapeHtml(outingPitch(d))}</p>
      ${isEventItem(d) ? eventSocialHtml(d) : ""}
      <dl class="facts">
        ${factRow(t("fact_cat"), d.category)}
        ${factRow(t("fact_type"), kindLabel(d.kind))}
        ${factRow(t("fact_price"), priceLabel(d))}
        ${factRow(t("fact_dur"), durationLabel(d.duration_minutes))}
        ${factRow(t("fact_in"), indoorLabel(d.indoor))}
        ${factRow(t("fact_addr"), d.address)}
        ${factRow(t("fact_dist"), d.distance_km != null ? d.distance_km + " km" : "")}
        ${bringNote(d) ? factRow(t("fact_bring"), bringNote(d)) : ""}
      </dl>
      ${isEventItem(d) ? eventCommentsHtml(d) : ""}
      ${routePanel()}
      ${mapUrl ? `<a class="btn outline" href="${mapUrl}" target="_blank" rel="noreferrer">${t("see_map")}</a>` : ""}
      ${site ? `<a class="btn outline" href="${site}" target="_blank" rel="noreferrer">${t("site")}</a>` : ""}
      <button class="btn sand" data-act="plan">📅 ${t("add_plan")}</button>
      <button class="btn secondary" data-act="send-detail-group">${t("send_detail")}</button>
      <button class="ghost" data-act="close-sheet">${t("close")}</button>
    </div></div>`;
}
function routePanel() {
  const from = startPoint();
  const aroundMe = ((from?.name || "") + "").toLowerCase() === t("around_me").toLowerCase() || ((from?.name || "") + "").toLowerCase() === "autour de moi";
  const usingGeo = state.routeFrom === "geo" || !from || aroundMe;
  const fromLabel = from?.name && !aroundMe ? t("from_city", { name: from.name }) : "";
  return `<div class="route-box">
    <label>${t("how_go")}</label>
    ${chips(transportList(), state.transport, "transport")}
    <label>${t("start_from")}</label>
    <div class="row">
      <button class="chip${usingGeo ? " on" : ""}" data-act="route-from-geo">📍 ${t("my_pos")}</button>
      ${fromLabel ? `<button class="chip${!usingGeo ? " on" : ""}" data-act="route-from-search">${escapeHtml(fromLabel)}</button>` : ""}
    </div>
    <p class="hint">${state.transport === "transit" ? t("route_transit") : state.transport === "walk" ? t("route_walk") : t("route_car")}</p>
    <button class="btn" data-act="open-route">${t("see_route")}</button>
  </div>`;
}
function normalizeOuting(item) {
  if (!item || typeof item !== "object") return item;
  return {
    ...item,
    name: decodeText(item.name),
    description: decodeText(item.description),
    address: decodeText(item.address),
    category: decodeText(item.category),
  };
}
function navHtml(active) {
  return `<nav class="nav">
    <button class="${active === "home" ? "on" : ""}" data-act="home">${t("nav_home")}</button>
    <button class="${active === "explore" ? "on" : ""}" data-act="explore">${t("nav_explore")}</button>
    <button class="${active === "favs" ? "on" : ""}" data-act="favs">${t("nav_favs")}</button>
    <button class="${active === "group" ? "on" : ""}" data-act="group">${t("nav_group")}</button>
  </nav>`;
}
function authHeaders() {
  const token = state.session?.access_token;
  const headers = { "Content-Type": "application/json" };
  if (token) headers.Authorization = "Bearer " + token;
  return headers;
}
function mergeById(a, b) {
  const map = new Map();
  [...(b || []), ...(a || [])].forEach((item) => { if (item?.id) map.set(item.id, item); });
  return [...map.values()];
}
function voterId() {
  let id = localStorage.getItem("sinki-voter");
  if (!id) {
    id = (crypto.randomUUID && crypto.randomUUID()) || ("v" + Date.now());
    localStorage.setItem("sinki-voter", id);
  }
  return id;
}
function applyGroupState(g) {
  if (!g || g.error) return;
  state.groupCode = g.share_code || state.groupCode;
  state.groupLabel = g.origin_label || state.groupLabel || "";
  const filters = g.filters || {};
  state.groupChat = filters.chat || [];
  state.groupPoll = filters.poll || null;
  state.groupVotes = filters.votes || {};
  if (state.groupCode) localStorage.setItem("sinki-group-code", state.groupCode);
}
function isListType() {
  return state.type === "shopping" || state.type === "randonnee";
}
function shareOptions() {
  const list = isListType()
    ? [...(state.pool || [])].sort((a, b) => Number(Boolean(b.photo_url)) - Number(Boolean(a.photo_url)) || (a.distance_km ?? 99) - (b.distance_km ?? 99))
    : (state.results || []);
  return list.filter((o) => o && o.id).slice(0, 3);
}
function pollHtml() {
  const poll = state.groupPoll;
  if (!poll || !poll.options?.length) return "";
  const votes = state.groupVotes || {};
  const mine = votes[voterId()]?.outing_id;
  const counts = {};
  Object.values(votes).forEach((v) => {
    const id = v && (v.outing_id || v);
    if (id) counts[id] = (counts[id] || 0) + 1;
  });
  const total = Object.keys(votes).length;
  return `<div class="poll-card">
    <p class="hint" style="margin-top:0">${t("poll_vote", { n: total })}</p>
    ${poll.options.map((o) => {
      const n = counts[o.id] || 0;
      const on = mine === o.id ? "on" : "";
      return `<button class="poll-opt ${on}" data-vote="${escapeHtml(String(o.id))}">
        <strong>${escapeHtml(decodeText(o.name))}</strong>
        <span>${priceLabel(o)} · ${n} ${n > 1 ? t("votes") : t("vote")}</span>
      </button>`;
    }).join("")}
  </div>`;
}
function voteShareText(code, options) {
  const lines = (options || []).map((r, i) => (i + 1) + ". " + decodeText(r.name) + " — " + priceLabel(r));
  return t("share_vote", { code }) + lines.join("\n");
}
async function copyText(text) {
  try {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch (_) { /* fallback */ }
  try {
    const el = document.createElement("textarea");
    el.value = text;
    el.setAttribute("readonly", "");
    el.style.position = "fixed";
    el.style.left = "-9999px";
    document.body.appendChild(el);
    el.select();
    const ok = document.execCommand("copy");
    document.body.removeChild(el);
    return ok;
  } catch (_) {
    return false;
  }
}
async function shareText(text) {
  try {
    if (navigator.share) {
      await navigator.share({ title: "Sinki", text });
      return "shared";
    }
  } catch (err) {
    if (String(err && err.name) === "AbortError") return "abort";
  }
  const copied = await copyText(text);
  return copied ? "copied" : "fail";
}
function friendlyAuthError(err) {
  const s = String(err || "");
  if (s.includes("email_exists") || s.includes("already been registered") || s.includes("déjà un compte")) return t("err_mail_taken");
  if (s.includes("Aucun compte") || s.includes("no account")) return t("err_no_account");
  if (s.includes("déjà pris") || s.includes("already taken") || s === "taken") return t("err_pseudo_taken");
  if (s.trim().startsWith("{")) return t("err_send_code");
  return s;
}
function validEmail(v) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(String(v || "").trim());
}
function validName(v) {
  return String(v || "").trim().length >= 1 && String(v || "").trim().length <= 40;
}
function validPseudo(v) {
  return /^[A-Za-zÀ-ÿ0-9._-]{2,20}$/.test(String(v || "").trim());
}
function avatarHtml(acc, cls) {
  const url = acc && acc.avatar_url;
  if (url) return `<img class="${cls}" src="${escapeHtml(url)}" alt="" />`;
  const letter = ((acc && (acc.nick || acc.first_name || acc.email)) || "?").trim().charAt(0).toUpperCase();
  return `<span class="${cls} avatar-letter">${escapeHtml(letter)}</span>`;
}
function setRow(act, label, extra) {
  return `<button type="button" class="set-row" data-act="${act}"><span>${escapeHtml(label)}</span><span class="set-extra">${extra ? escapeHtml(extra) : ""} ›</span></button>`;
}
function settingsPage() {
  const view = state.settingsView || "menu";
  const acc = state.account;
  const logged = Boolean(state.session?.access_token && acc?.email);
  const err = state.profileHint ? `<p class="${state.profileHint === t("set_saved") ? "hint" : "empty"}">${escapeHtml(state.profileHint)}</p>` : "";
  if (view === "lang") {
    const cur = currentLangLabel();
    return `<div class="page has-nav">
      <h1>${t("settings_lang")}</h1>
      <p class="lead">${t("settings_lead")}</p>
      <label>${t("settings_current")}</label>
      <p class="hint" style="margin-top:0">${escapeHtml(cur)}</p>
      ${hasPack(state.lang) ? "" : `<p class="hint">${t("lang_partial")}</p>`}
      <label>${t("settings_lang")}</label>
      <input type="text" id="langq" placeholder="${escapeHtml(t("settings_search"))}" value="${escapeHtml(state.langQ)}" autocomplete="off" autocorrect="off" spellcheck="false" />
      <div class="lang-list">${langListHtml()}</div>
      ${navHtml("home")}
    </div>`;
  }
  if (view === "home-country") {
    return `<div class="page has-nav">
      <h1>${t("set_home_country")}</h1>
      <p class="lead">${t("set_home_country_lead")}</p>
      <p class="hint">${t("settings_current")}: ${escapeHtml(state.homeCountry?.name || "France")}</p>
      <label>${t("country")}</label>
      <input type="text" id="countryq" placeholder="${escapeHtml(t("country_ph"))}" value="${escapeHtml(state.countryQuery)}" autocomplete="off" autocorrect="off" spellcheck="false" />
      <div id="live-search">${countrySuggestHtml()}</div>
      ${navHtml("home")}
    </div>`;
  }
  if (view === "profile") {
    if (!logged) {
      return `<div class="page has-nav">
        <h1>${t("set_profile")}</h1>
        <p class="lead">${t("set_need_login")}</p>
        <button class="btn" data-act="account">${t("set_open_account")}</button>
        ${navHtml("home")}
      </div>`;
    }
    return `<div class="page has-nav">
      <h1>${t("set_profile")}</h1>
      <p class="lead">${t("set_profile_lead")}</p>
      <div class="account-card">
        <button type="button" class="avatar-btn" data-act="pick-avatar" aria-label="${t("set_photo")}">${avatarHtml(acc, "avatar")}</button>
        <p class="hint">${t("set_photo_hint")}</p>
        <input type="file" id="avatarfile" accept="image/jpeg,image/png,image/webp" hidden />
        <label>${t("first_name")}</label>
        <input type="text" id="profirst" value="${escapeHtml(acc.first_name || "")}" autocomplete="given-name" />
        <label>${t("last_name")}</label>
        <input type="text" id="prolast" value="${escapeHtml(acc.last_name || "")}" autocomplete="family-name" />
        <label>${t("pseudo")}</label>
        <input type="text" id="pronick" value="${escapeHtml(acc.nick || "")}" autocomplete="username" />
        <p class="hint">${escapeHtml(acc.email || "")}</p>
        ${err}
        <button class="btn stack-gap" data-act="profile-save" ${state.profileBusy ? "disabled" : ""}>${state.profileBusy ? "…" : t("set_save")}</button>
      </div>
      ${navHtml("home")}
    </div>`;
  }
  if (view === "plan") {
    const home = state.homeCountry?.name || t("france");
    return `<div class="page has-nav">
      <h1>${t("set_plan_title")}</h1>
      ${mascot("emerveillee", t("pay_catalog_lead"))}
      <div class="account-card">
        <p class="hint" style="margin-top:0"><strong>${t("set_plan_free")}</strong>${hasPlus() || hasUnlimited() ? "" : " · " + t("set_plan_current")}</p>
        <p class="hint">${t("set_plan_free_lead", { country: home, n: FREE_DAY_CAP })}</p>
      </div>
      ${tariffsBody()}
      ${navHtml("home")}
    </div>`;
  }
  if (view === "events") {
    if (!logged) {
      return `<div class="page has-nav">
        <h1>${t("ev_title")}</h1>
        <p class="lead">${t("set_need_login")}</p>
        <button class="btn" data-act="account">${t("set_open_account")}</button>
        ${navHtml("home")}
      </div>`;
    }
    const rows = state.myEvents || [];
    const queue = state.isModerator ? (state.pendingEvents || []) : [];
    return `<div class="page has-nav">
      <h1>${t("ev_title")}</h1>
      ${state.profileHint ? `<p class="hint">${escapeHtml(state.profileHint)}</p>` : ""}
      ${queue.length ? `<h2 class="section">${t("ev_queue")}</h2>${queue.map((ev) => `<div class="account-card">
        ${ev.photo_url ? `<img class="avatar" src="${escapeHtml(ev.photo_url)}" alt="" />` : ""}
        <p class="hint" style="margin-top:8px"><strong>${escapeHtml(ev.name)}</strong></p>
        <p class="hint">${escapeHtml(ev.address || "")}</p>
        <p class="hint">${escapeHtml(ev.description || "")}</p>
        <p class="hint">${ev.price_min ? priceLabel(ev) : t("ev_free")}</p>
        <button class="btn" data-act="event-approve" data-id="${escapeHtml(ev.id)}">${t("ev_approve")}</button>
        <button class="btn secondary" data-act="event-reject" data-id="${escapeHtml(ev.id)}">${t("ev_reject")}</button>
      </div>`).join("")}` : ""}
      ${rows.length ? rows.map((ev) => `<div class="account-card">
        <p class="hint" style="margin-top:0"><strong>${escapeHtml(ev.name)}</strong></p>
        <p class="hint">${eventStatusLabel(ev)}</p>
      </div>`).join("") : `<p class="empty">${t("ev_empty")}</p>`}
      <div class="account-card">
        <button class="btn" data-act="event-new">${t("ev_new")}<span class="btn-price">${escapeHtml(formatFee(eventFee("publish")))}</span></button>
      </div>
      ${navHtml("home")}
    </div>`;
  }
  if (view === "event-edit") {
    const d = state.eventDraft || {};
    return `<div class="page has-nav">
      <h1>${t("ev_new")}</h1>
      <div class="account-card">
        <label>${t("ev_name")}</label>
        <input type="text" id="evname" maxlength="80" value="${escapeHtml(d.name || "")}" />
        <label>${t("ev_desc")}</label>
        <textarea id="evdesc" rows="4" maxlength="800">${escapeHtml(d.description || "")}</textarea>
        <label>${t("ev_where")}</label>
        <input type="text" id="evaddr" maxlength="160" value="${escapeHtml(d.address || "")}" />
        <label>${t("ev_when")}</label>
        <input type="date" id="evwhen" value="${escapeHtml(d.when || todayISO())}" />
        <label>${t("ev_photo")}</label>
        ${state.eventPhoto ? `<img class="avatar" src="${escapeHtml(state.eventPhoto)}" alt="" />` : ""}
        <input type="file" id="evphoto" accept="image/jpeg,image/png,image/webp" />
        <label class="check-row"><input type="checkbox" id="evpaid"${d.paid ? " checked" : ""} /> ${t("ev_paid")}</label>
        <div id="evprice-wrap"${d.paid ? "" : " hidden"}>
          <label>${t("ev_price")}</label>
          <input type="number" id="evprice" min="0" max="500" step="0.5" inputmode="decimal" value="${escapeHtml(d.price || "")}" />
        </div>
        ${state.profileHint ? `<p class="hint">${escapeHtml(state.profileHint)}</p>` : ""}
        <button class="btn stack-gap" data-act="event-next">${t("ev_next")}</button>
      </div>
      ${navHtml("home")}
    </div>`;
  }
  if (view === "event-boosts") {
    const extra = Number(state.eventBoostDays) || 0;
    return `<div class="page has-nav">
      <h1>${t("ev_boost_page")}</h1>
      <div class="account-card">
        <p class="hint" style="margin-top:0">${t("ev_boost_included", { price: formatFee(eventFee("publish")) })}</p>
      </div>
      <p class="hint">${t("ev_boost_extra")}</p>
      ${boostListHtml(extra, true)}
      ${extra ? `<button class="ghost" data-act="event-boost" data-id="0">${t("ev_boost_none")}</button>` : ""}
      ${state.profileHint ? `<p class="hint">${escapeHtml(state.profileHint)}</p>` : ""}
      <button class="btn" data-act="event-finish">${extra ? t("ev_pay_boost", { price: formatFee(eventFee(extra)) }) : t("ev_send")}</button>
      ${navHtml("home")}
    </div>`;
  }
  if (view === "help") {
    return `<div class="page has-nav">
      <h1>${t("set_help_title")}</h1>
      <div class="account-card">
        <p class="hint" style="margin-top:0"><strong>${t("set_help_q1")}</strong></p>
        <p class="hint">${t("set_help_a1")}</p>
        <p class="hint"><strong>${t("set_help_q2")}</strong></p>
        <p class="hint">${t("set_help_a2")}</p>
        <p class="hint"><strong>${t("set_help_q3")}</strong></p>
        <p class="hint">${t("set_help_a3")}</p>
      </div>
      <button class="ghost" data-act="set-contact">${t("set_contact")}</button>
      ${navHtml("home")}
    </div>`;
  }
  if (view === "contact") {
    const mail = t("set_contact_mail");
    return `<div class="page has-nav">
      <h1>${t("set_contact_title")}</h1>
      <p class="lead">${t("set_contact_lead")}</p>
      <div class="account-card">
        <p class="hint" style="margin-top:0">${escapeHtml(mail)}</p>
        <a class="btn stack-gap" href="mailto:${escapeHtml(mail)}?subject=Sinki">${t("set_contact_btn")}</a>
      </div>
      ${navHtml("home")}
    </div>`;
  }
  if (view === "privacy") {
    return `<div class="page has-nav">
      <h1>${t("set_privacy_title")}</h1>
      <p class="lead">${t("set_privacy_lead")}</p>
      <div class="account-card">${legalHtml("legal_privacy")}</div>
      ${navHtml("home")}
    </div>`;
  }
  if (view === "terms") {
    return `<div class="page has-nav">
      <h1>${t("set_terms_title")}</h1>
      <p class="lead">${t("set_terms_lead")}</p>
      <div class="account-card">${legalHtml("legal_terms")}</div>
      ${navHtml("home")}
    </div>`;
  }
  if (view === "purchases") {
    return `<div class="page has-nav">
      <h1>${t("set_purchases_title")}</h1>
      <p class="lead">${t("set_purchases_lead")}</p>
      <div class="account-card">${legalHtml("legal_purchases")}</div>
      ${navHtml("home")}
    </div>`;
  }
  if (view === "legal") {
    return `<div class="page has-nav">
      <h1>${t("set_legal_title")}</h1>
      <div class="account-card">${legalHtml("legal_mentions")}</div>
      ${navHtml("home")}
    </div>`;
  }
  if (view === "about") {
    return `<div class="page has-nav">
      <h1>${t("set_about_title")}</h1>
      ${mascot("heureuse", "Sinki")}
      <p class="lead">${t("set_about_lead")}</p>
      ${navHtml("home")}
    </div>`;
  }
  if (view === "notifs") {
    return `<div class="page has-nav">
      <h1>${t("set_notifs_title")}</h1>
      <p class="lead">${t("set_notifs_hint")}</p>
      <button type="button" class="set-row" data-act="toggle-notifs-plans"><span>${t("set_notifs_plans")}</span><span class="set-extra">${state.notifsPlans ? "●" : "○"}</span></button>
      <button type="button" class="set-row" data-act="toggle-notifs-group"><span>${t("set_notifs_group")}</span><span class="set-extra">${state.notifsGroup ? "●" : "○"}</span></button>
      ${navHtml("home")}
    </div>`;
  }
  const lang = currentLangLabel();
  return `<div class="page has-nav">
    <h1>${t("settings_title")}</h1>
    <p class="lead">${t("settings_lead")}</p>
    <div class="set-list">
      ${setRow("set-profile", t("set_profile"), logged ? (acc.nick ? "@" + acc.nick : "") : "")}
      ${setRow("set-home-country", t("set_home_country"), state.homeCountry?.name || "France")}
      ${setRow("set-plan", t("set_plan"), hasPlus() ? t("set_plan_plus") : t("set_plan_free"))}
      ${setRow("set-events", t("ev_title"), "")}
      ${setRow("set-notifs", t("set_notifs"))}
      ${setRow("set-lang", t("set_lang_row"), lang)}
    </div>
    <div class="set-list">
      ${setRow("set-help", t("set_help"))}
      ${setRow("set-contact", t("set_contact"))}
      ${setRow("set-privacy", t("set_privacy"))}
      ${setRow("set-terms", t("set_terms"))}
      ${setRow("set-purchases", t("set_purchases"))}
      ${setRow("set-legal", t("set_legal"))}
      ${setRow("set-about", t("set_about"))}
    </div>
    ${navHtml("home")}
  </div>`;
}
function accountPage() {
  const acc = state.account;
  if (state.session?.access_token && acc) {
    const name = [acc.first_name, acc.last_name].filter(Boolean).join(" ");
    return `<div class="page has-nav">
      <h1>${t("account_title")}</h1>
      ${mascot("heureuse", t("connected"))}
      <div class="account-card">
        ${avatarHtml(acc, "avatar")}
        ${name ? `<p class="hint" style="margin-top:8px">${escapeHtml(name)}</p>` : ""}
        ${acc.nick ? `<p class="hint">@${escapeHtml(acc.nick)}</p>` : ""}
        <p class="hint">${escapeHtml(acc.email || "")}</p>
        <p class="hint">${t("favs_sync")}</p>
        <p class="hint">${t("account_logout_hint")}</p>
        ${state.authError ? `<p class="empty">${escapeHtml(state.authError)}</p>` : ""}
        <button class="ghost" data-act="logout">${t("logout")}</button>
        ${state.accountDeleteAsk
          ? `<p class="hint">${t("account_delete_confirm")}</p>
        <button class="btn secondary" data-act="account-delete">${t("account_delete_yes")}</button>
        <button class="ghost" data-act="account-delete-cancel">${t("close")}</button>`
          : `<button class="ghost" data-act="account-delete-ask">${t("account_delete")}</button>`}
      </div>
      ${navHtml("home")}
    </div>`;
  }
  const mode = state.authMode || "login";
  const err = state.authError ? `<p class="empty">${escapeHtml(state.authError)}</p>` : "";
  const hint = state.authHint ? `<p class="hint">${escapeHtml(state.authHint)}</p>` : "";
  if (state.authView === "code") {
    return `<div class="page has-nav">
      <h1>${t("account_title")}</h1>
      <p class="lead">${t("account_code_hint")}</p>
      <div class="account-card">
        <label>${t("auth_code")}</label>
        <input type="text" id="authcode" inputmode="numeric" autocomplete="one-time-code" placeholder="••••••" value="" />
        <p class="hint">${t("sent_to", { email: state.authEmail })}</p>
        ${err}
        <button class="btn stack-gap" data-act="auth-verify" ${state.authBusy ? "disabled" : ""}>${state.authBusy ? t("verifying") : t("verify")}</button>
        <button class="ghost" data-act="auth-open">${t("change_email")}</button>
      </div>
      ${navHtml("home")}
    </div>`;
  }
  if (state.authView === "names") {
    return `<div class="page has-nav">
      <h1>${t("account_signup")}</h1>
      <p class="lead">${t("account_names_hint")}</p>
      <div class="account-card">
        <label>${t("first_name")}</label>
        <input type="text" id="authfirst" autocomplete="given-name" placeholder="${escapeHtml(t("first_ph"))}" value="${escapeHtml(state.authFirst)}" />
        <label>${t("last_name")}</label>
        <input type="text" id="authlast" autocomplete="family-name" placeholder="${escapeHtml(t("last_ph"))}" value="${escapeHtml(state.authLast)}" />
        ${err}
        <button class="btn stack-gap" data-act="auth-next-names">${t("continue")}</button>
        <button class="ghost" data-act="auth-open">${t("back_choices")}</button>
      </div>
      ${navHtml("home")}
    </div>`;
  }
  if (state.authView === "pseudo") {
    return `<div class="page has-nav">
      <h1>${t("account_signup")}</h1>
      <p class="lead">${t("account_pseudo_hint")}</p>
      <div class="account-card">
        <label>${t("pseudo")}</label>
        <input type="text" id="authpseudo" autocomplete="username" placeholder="${escapeHtml(t("pseudo_ph"))}" value="${escapeHtml(state.authPseudo)}" />
        ${err}
        <button class="btn stack-gap" data-act="auth-send" ${state.authBusy ? "disabled" : ""}>${state.authBusy ? t("sending") : t("send_code")}</button>
        <button class="ghost" data-act="auth-back-names">${t("back_choices")}</button>
      </div>
      ${navHtml("home")}
    </div>`;
  }
  if (state.authView === "contact" || state.authView === "email") {
    const lead = mode === "signup" ? t("account_signup_hint") : t("account_login_hint");
    return `<div class="page has-nav">
      <h1>${mode === "signup" ? t("account_signup") : t("account_login")}</h1>
      <p class="lead">${lead}</p>
      <div class="account-card">
        <label>${t("your_email")}</label>
        <input type="email" id="authemail" placeholder="toi@mail.com" value="${escapeHtml(state.authEmail)}" autocomplete="email" />
        ${hint}${err}
        <button class="btn stack-gap" data-act="auth-next-contact" ${state.authBusy ? "disabled" : ""}>${state.authBusy ? t("sending") : (mode === "signup" ? t("continue") : t("send_code"))}</button>
        <button class="ghost" data-act="auth-close">${t("back_choices")}</button>
      </div>
      ${navHtml("home")}
    </div>`;
  }
  return `<div class="page has-nav">
    <h1>${t("account_title")}</h1>
    ${mascot("heureuse", t("account_lead"))}
    ${state.authHint ? `<p class="hint">${escapeHtml(state.authHint)}</p>` : ""}
    <button class="btn" data-act="auth-login">${t("account_login")}</button>
    <button class="btn secondary" data-act="auth-signup">${t("account_signup")}</button>
    ${navHtml("home")}
  </div>`;
}
function mascot(kind, text) {
  const src = { heureuse: "/biche/heureuse.png?v=6", emerveillee: "/biche/emerveillee.png?v=8", triste: "/biche/triste.png?v=2", reflechit: "/biche/reflechit.png?v=7" }[kind];
  return `<div class="mascot-block"><img src="${src}" alt="" /><p>${text}</p></div>`;
}
function pickThree(list, vibe) {
  const vibeCats = {
    "relax": ["Lieux gratuits et balades", "Randonnées", "Musées et culture"],
    "fun": ["Activités et loisirs", "Restaurants et cafés", "Shopping", "Randonnées"],
    "culture": ["Musées et culture"],
    "party": ["Soirées et concerts"],
  };
  function score(o) {
    let s = 0;
    if (o.photo_url) s += 18;
    if (o.distance_km != null) s += Math.max(0, 24 - Number(o.distance_km));
    if (o.source_name === "nearby") s -= 22;
    const wanted = vibeCats[vibe] || [];
    if (wanted.includes(o.category)) s += 9;
    if (o.category === "Randonnées") s += 6;
    if (vibe === "fun" && (o.kind === "restaurant" || (o.category || "").includes("loisirs"))) s += 3;
    if (vibe === "party" && o.kind === "event") s += 4;
    return s;
  }
  function nameKey(n) {
    return decodeText(n || "")
      .toLowerCase()
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .replace(/[^a-z0-9]+/g, " ")
      .trim();
  }
  function tokens(n) {
    const stop = new Set(["le","la","les","de","du","des","et","un","une","au","aux","en","dans","avec","pour","sur"]);
    return new Set(nameKey(n).split(" ").filter((w) => w.length > 2 && !stop.has(w)));
  }
  function isDup(a, b) {
    const ka = nameKey(a.name), kb = nameKey(b.name);
    if (!ka || !kb) return false;
    if (ka === kb) return true;
    const [sh, lo] = ka.length <= kb.length ? [ka, kb] : [kb, ka];
    if (sh.length >= 12 && lo.startsWith(sh + " ")) return true;
    const ta = tokens(a.name), tb = tokens(b.name);
    const inter = [...ta].filter((x) => tb.has(x)).length;
    if (inter >= 3 && inter / Math.min(ta.size, tb.size) >= 0.6) return true;
    const longShared = [...ta].filter((x) => tb.has(x) && x.length >= 5);
    if (longShared.length >= 2) return true;
    return false;
  }
  const uniq = [];
  const ordered = [...list].sort((a, b) => score(b) - score(a) || (a.distance_km ?? 99) - (b.distance_km ?? 99));
  for (const o of ordered) {
    if (!nameKey(o.name)) continue;
    if (uniq.some((p) => isDup(o, p))) continue;
    uniq.push(o);
  }
  const chosen = [];
  const cats = new Set();
  for (const item of uniq) {
    const cat = item.category || item.name;
    if (chosen.length >= 2 && cats.has(cat)) continue;
    chosen.push(item);
    cats.add(cat);
    if (chosen.length === 3) break;
  }
  for (const item of uniq) {
    if (chosen.length === 3) break;
    if (!chosen.includes(item)) chosen.push(item);
  }
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

function langRows() {
  const q = (state.langQ || "").trim().toLowerCase();
  if (!q) return [];
  const rows = window.SINKI_LANGS || [];
  return rows.filter(([id, en, native]) => {
    return id.includes(q) || en.toLowerCase().includes(q) || native.toLowerCase().includes(q);
  }).slice(0, 24);
}
function langListHtml() {
  const q = (state.langQ || "").trim();
  if (!q) return `<p class="hint">${t("settings_type")}</p>`;
  const list = langRows();
  if (!list.length) return `<p class="hint">${t("settings_lang_none", { q })}</p>`;
  return list.map(([id, en, native]) => `<button class="lang-row${langBase(state.lang) === id ? " on" : ""}" data-lang="${id}"><strong>${escapeHtml(native)}</strong><span>${escapeHtml(en)} · ${id}</span></button>`).join("");
}
function currentLangLabel() {
  const rows = window.SINKI_LANGS || [];
  const hit = rows.find(([id]) => id === langBase(state.lang) || id === state.lang);
  if (!hit) return state.lang;
  return hit[2] + " · " + hit[1];
}

function render() {
  if (state.screen !== "account") state.accountDeleteAsk = false;
  if (state.intro) {
    app.classList.add("is-intro");
    app.innerHTML = `<button type="button" class="intro" data-act="intro-done" aria-label="Sinki">
      <img src="/biche/intro.jpg?v=2" alt="" />
    </button>`;
    bind();
    if (!state.introArmed) {
      state.introArmed = true;
      clearTimeout(render.introTimer);
      render.introTimer = setTimeout(() => {
        if (!state.intro) return;
        state.intro = false;
        render();
      }, 1500);
    }
    return;
  }
  app.classList.remove("is-intro");
  if (state.screen === "hike") state.screen = "home";
  applyDocumentLang();
  const last = lastSearch();
  const tab = ["explore", "favs", "group", "home", "settings"].includes(state.screen);
  const back = (state.screen === "home" || (tab && state.screen !== "search" && state.screen !== "settings")) ? "<span></span>" :
    `<button class="icon-btn" data-act="back">←</button>`;
  const vibeLabel = t("vibe_" + vibeId(last?.vibe || state.vibe));
  let body = "";
  if (state.screen === "home") {
    body = `<div class="home page has-nav">
      ${mascot("heureuse", t("home_mascot"))}
      <h1>${t("home_title")}</h1>
      ${hasUnlimited() ? "" : `<p class="hint">${t("quota_left", { n: remainingToday(), max: FREE_DAY_CAP })}</p>`}
      <button class="choice featured" data-act="start"><h3>${t("home_cta")}</h3></button>
      ${last?.city ? `<button class="btn secondary" data-act="resume">↻ ${t("resume")}<small>${escapeHtml(last.city.name)} · ${last.budget == null ? t("budget_free") : t("budget_max", { n: last.budget })} · ${escapeHtml(vibeLabel)}</small></button>` : ""}
      ${navHtml("home")}
    </div>`;
  } else if (state.screen === "settings") {
    body = settingsPage();
  } else if (state.screen === "account") {
    body = accountPage();
  } else if (state.screen === "explore") {
    const pickingCountry = state.explorePickHome || (state.exploreScope === "world" && !state.exploreCountry);
    const pickingCity = state.exploreScope === "world" && state.exploreCountry && !state.exploreCity;
    let masc = mascot("reflechit", pickingCountry ? t("explore_pick_country") : pickingCity ? t("explore_pick_city") : t("explore_type"));
    if (state.exploreLoading) masc = mascot("reflechit", t("explore_loading"));
    else if (pickingCity && state.exploreCityQ.trim().length >= 1 && !state.exploreCities.length)
      masc = mascot("reflechit", t("explore_none"));
    else if (!pickingCountry && !pickingCity && state.exploreQ.trim().length >= 1 && !state.exploreOutings.length && !state.exploreCities.length)
      masc = mascot("reflechit", t("explore_none"));
    else if (state.exploreOutings.length || ((state.exploreQ || state.exploreCityQ).trim().length >= 1 && state.exploreCities.length))
      masc = mascot("reflechit", t("explore_found"));
    const homeName = state.homeCountry?.name || "France";
    const worldName = state.exploreCountry?.name || "";
    const cityName = state.exploreCity?.name || "";
    body = `<div class="page has-nav">
      <h1>${t("explore_title")}</h1>
      <div class="row">
        <button class="chip${state.exploreScope === "home" ? " on" : ""}" data-act="explore-home">${t("explore_home")}</button>
        <button class="chip${state.exploreScope === "world" ? " on" : ""}" data-act="explore-world">${t("explore_world")}</button>
      </div>
      ${state.exploreScope === "home" ? `
        <p class="lead explore-lead">${t("explore_home_lead", { country: homeName })}</p>
        <div class="row">
          <button class="chip on" type="button">${escapeHtml(homeName)}</button>
          <button class="chip" data-act="explore-change-home">${t("explore_change_country")}</button>
        </div>
      ` : `
        <p class="lead explore-lead">${t("explore_world_lead")}</p>
        ${state.exploreCountry ? `
        <div class="row">
          <button class="chip on" type="button">${escapeHtml(worldName)}</button>
          <button class="chip" data-act="explore-clear-country">${t("change_country")}</button>
        </div>
        ` : ""}
        ${state.exploreCity ? `
        <div class="row">
          <button class="chip on" type="button">${escapeHtml(cityName)}</button>
          <button class="chip" data-act="explore-clear-city">${t("explore_change_city")}</button>
        </div>
        ` : ""}
      `}
      ${masc}
      ${pickingCountry ? `
      <label>${t("country")}</label>
      <input type="text" id="countryq" placeholder="${escapeHtml(t("country_ph"))}" value="${escapeHtml(state.countryQuery)}" autocomplete="off" autocorrect="off" spellcheck="false" />
      ` : pickingCity ? `
      <label>${t("city")}</label>
      <input type="text" id="explorecity" placeholder="${escapeHtml(t("explore_city_ph"))}" value="${escapeHtml(state.exploreCityQ)}" autocomplete="off" autocorrect="off" spellcheck="false" />
      <p class="hint">${t("explore_hint_world_city")}</p>
      ` : `
      <input type="text" id="exploreq" placeholder="${escapeHtml(state.exploreScope === "home" ? t("explore_ph_home") : t("explore_act_ph"))}" value="${escapeHtml(state.exploreQ)}" autocomplete="off" autocorrect="off" spellcheck="false" />
      <p class="hint">${state.exploreScope === "home" ? t("explore_hint_home") : t("explore_hint_world_act")}</p>
      `}
      <div id="live-search">${exploreResultsHtml()}</div>
      <button class="ghost" data-act="set-events">${t("ev_open")}</button>
      ${navHtml("explore")}
    </div>`;
  } else if (state.screen === "search" && state.step === 1) {
    body = `<div class="page">
      <div class="step">${t("step", { n: 1, total: 2 })}</div>
      <h1>${t("from_title")}</h1>
      <p class="lead">${t("from_lead")}</p>
      <label>${t("category")}</label>
      <div class="row">
        <button class="chip${onHomeArea() ? " on" : ""}" data-act="area-home">${escapeHtml(state.homeCountry?.name || t("france"))}</button>
        <button class="chip${!onHomeArea() ? " on" : ""}" data-act="area-int">🌍 ${t("international")}</button>
      </div>
      <p class="hint">${onHomeArea() ? t("hint_home", { country: state.homeCountry?.name || t("france") }) : t("hint_int")}</p>
      <button class="btn secondary geo-btn" type="button" data-act="geo">${state.geoBusy ? t("geo_busy") : "⌖ " + t("geo")}</button>
      <p class="hint">${t("geo_privacy")}</p>
      ${!onHomeArea() && state.area === "international" && !state.intCountry ? `
      <label>${t("country")}</label>
      <input type="text" id="countryq" placeholder="${escapeHtml(t("country_ph"))}" value="${escapeHtml(state.countryQuery)}" autocomplete="off" autocorrect="off" spellcheck="false" />
      <div id="live-search">${countrySuggestHtml()}</div>
      ` : ""}
      ${!onHomeArea() && state.area === "international" && state.intCountry ? `
      <label>${t("country")}</label>
      <div class="row">
        <button class="chip on" type="button">${escapeHtml(state.intCountry.name)}</button>
        <button class="chip" data-act="country-clear">${t("change_country")}</button>
      </div>
      <label>${t("city")}</label>
      <input type="text" id="cityq" placeholder="${escapeHtml(t("city_ph"))}" value="${escapeHtml(state.query)}" autocomplete="off" autocorrect="off" spellcheck="false" />
      <div id="live-search">${citySuggestHtml()}</div>
      ` : ""}
      ${onHomeArea() ? `
      <label>${t("start_from")}</label>
      <input type="text" id="cityq" placeholder="${escapeHtml((state.homeCountry?.code || "FR") === "FR" ? t("city_ph_fr") : t("city_ph"))}" value="${escapeHtml(state.query)}" autocomplete="off" autocorrect="off" spellcheck="false" />
      <div id="live-search">${citySuggestHtml()}</div>
      ` : ""}
      <label>${t("people")}</label>
      <div class="people">
        <button class="icon-btn" data-act="minus">−</button>
        <span>${state.people} ${state.people > 1 ? t("persons") : t("person")}</span>
        <button class="icon-btn" data-act="plus">+</button>
      </div>
      <div class="sticky"><button class="btn" data-act="to2" ${state.city ? "" : "disabled"}>${t("continue")}</button></div>
    </div>`;
  } else if (state.screen === "search" && state.step === 2) {
    body = `<div class="page">
      <div class="step">${t("step", { n: 2, total: 2 })}</div>
      <h1>${t("want_title")}</h1>
      <p class="lead">${t("want_lead")}</p>
      <label>${t("date_label")}</label>
      <input type="date" id="date" value="${state.date}" />
      <div class="row" style="margin-top:8px">
        <button class="chip${state.date === todayISO() ? " on" : ""}" data-act="date-today">${t("today")}</button>
        <button class="chip${state.date === addDays(1) ? " on" : ""}" data-act="date-tom">${t("tomorrow")}</button>
        <button class="chip${state.date === addDays(7) ? " on" : ""}" data-act="date-week">${t("week")}</button>
      </div>
      <label>${t("budget_pp")}</label>
      <div class="budget-val">${state.unlimited ? t("unlimited") : state.budget === 0 ? t("free") : t("budget_max", { n: state.budget })}</div>
      <input type="range" id="budget" min="0" max="200" step="5" value="${state.unlimited ? 200 : state.budget}" />
      <div class="row">
        <button class="chip${!state.unlimited && state.budget === 0 ? " on" : ""}" data-act="b0">${t("free")}</button>
        <button class="chip${!state.unlimited && state.budget === 25 ? " on" : ""}" data-act="b25">25 €</button>
        <button class="chip${!state.unlimited && state.budget === 60 ? " on" : ""}" data-act="b60">60 €</button>
        <button class="chip${state.unlimited ? " on" : ""}" data-act="bunlim">${t("unlimited")}</button>
      </div>
      <p class="hint">${t("no_cap")}</p>
      <label>${t("time_avail")}</label>${chips(durationList(), state.duration, "duration")}
      <label>${t("moment")}</label>${chips(momentList(), state.moment, "moment")}
      <label>${t("dist_max")}</label>${chips(RADII.map((k) => [String(k), k + " km"]), String(state.radius), "radius")}
      <label>${t("outing_type")}</label>${chips(typeList(), state.type, "type")}
      <label>${t("vibe")}</label>${chips(vibeList(), vibeId(state.vibe), "vibe")}
      <label>${t("place")}</label>${chips(indoorList(), state.indoor, "indoor")}
      <label>${t("transport")}</label>${chips(transportList(), state.transport, "transport")}
      ${state.error ? `<p class="empty">${escapeHtml(state.error)}</p>` : ""}
      <div class="sticky"><button class="btn" data-act="search" ${state.loading ? "disabled" : ""}>${state.loading ? t("searching") : t("find3")}</button></div>
    </div>`;
  } else if (state.screen === "results") {
    const listed = isListType();
    const fallback = state.nearestFallback;
    const shown = listed
      ? [...state.pool]
          .sort((a, b) => fallback
            ? ((a.distance_km ?? 99) - (b.distance_km ?? 99))
            : (Number(Boolean(b.photo_url)) - Number(Boolean(a.photo_url)) || (a.distance_km ?? 99) - (b.distance_km ?? 99)))
          .slice(0, 48)
      : state.results;
    const title = state.type === "shopping" ? t("type_shop") : state.type === "randonnee" ? t("type_hike") : t("results3");
    const nearTxt = t("near_intro", { city: state.city?.name || "" });
    const intro = !shown.length
      ? mascot("reflechit", t("empty_alts"))
      : state.searchNote
      ? mascot("emerveillee", state.searchNote)
      : fallback
      ? mascot("emerveillee", nearTxt)
      : state.type === "shopping"
      ? mascot("emerveillee", t("shop_intro"))
      : state.type === "randonnee"
      ? mascot("emerveillee", t("hike_intro"))
      : mascot("emerveillee", t("three_intro"));
    const altHtml = state.alts.length
      ? `<div class="alts"><p class="hint">${t("alts_try")}</p><div class="row">${state.alts.map((a, i) => `<button class="chip" data-act="alt" data-id="${i}">${escapeHtml(a.label)}</button>`).join("")}</div></div>`
      : "";
    const who = state.people > 1 ? t("friends") : t("person");
    const budgetLine = listed || state.unlimited ? (state.type === "shopping" ? t("all_budgets") : state.type === "randonnee" ? t("trails") : t("budget_free")) : t("budget_max", { n: state.budget });
    body = `<div class="page">
      ${state.weather ? `<div class="weather">${state.weather} · ${escapeHtml(state.city?.name || "")}</div>` : ""}
      <p class="lead" style="margin-bottom:0">${t("for_who", { n: state.people, who, city: state.city?.name || "" })}</p>
      <h1>${title}${listed && shown.length ? " · " + shown.length : ""}</h1>
      <p class="lead">📅 ${formatDate(state.date)} · ${budgetLine} · ${escapeHtml(t("vibe_" + vibeId(state.vibe)))}</p>
      ${intro}${altHtml}${shown.length ? shown.map((item) => cardHtml(item, "guided")).join("") : ""}
      <button class="btn" data-act="dice">🎲 ${t("dice")}<small>${t("dice_sub")}</small></button>
      ${listed ? "" : `<button class="btn sand" data-act="cheaper">💶 ${t("cheaper")}</button>`}
      <button class="btn outline" data-act="share" ${state.shareBusy ? "disabled" : ""}>${state.shareBusy ? t("share_busy") : t("share")}</button>
      ${state.shareHint ? `<p class="hint">${escapeHtml(state.shareHint)}</p>` : ""}
      <button class="ghost" data-act="edit">${t("edit")}</button>
    </div>`;
  } else if (state.screen === "favs") {
    body = `<div class="page has-nav"><h1>${t("favs_title")}</h1>${state.favs.length ? mascot("emerveillee", t("favs_full")) + state.favs.map((item) => cardHtml(item, "fav")).join("") : mascot("emerveillee", t("favs_empty"))}${navHtml("favs")}</div>`;
  } else if (state.screen === "group") {
    const chat = state.groupChat.map((m) => `<div class="bubble"><div class="who">${escapeHtml(m.name)}</div>${escapeHtml(m.text || "")}${m.outing ? `<div class="share-card">${escapeHtml(m.outing.name)} · ${priceLabel(m.outing)}</div>` : ""}</div>`).join("");
    const autoNick = String((state.account && state.account.first_name) || "").trim();
    const nickField = autoNick
      ? `<p class="hint">${t("nick_auto", { name: autoNick })}</p>`
      : `<label>${t("nick")}</label>
      <input type="text" id="nick" placeholder="Alex" value="${escapeHtml(state.groupNick)}" />`;
    body = `<div class="page has-nav">
      <h1>${t("group_title")}</h1>
      ${state.groupCode ? mascot("heureuse", t("group_on")) : mascot("heureuse", t("group_off"))}
      ${nickField}
      ${state.groupCode ? `<p class="hint">${t("group_code")} : <strong>${escapeHtml(state.groupCode)}</strong> — ${escapeHtml(state.groupLabel || "")}</p>
        ${state.shareHint ? `<p class="hint">${escapeHtml(state.shareHint)}</p>` : ""}
        <button class="btn outline" data-act="copy-code">${t("copy_code")}</button>
        <button class="btn secondary" data-act="share-again">${t("share_again")}</button>
        ${pollHtml()}
        <div class="chat">${chat || "<p class='empty'>" + t("no_msg") + "</p>"}</div>
        <div class="composer"><input type="text" id="chatmsg" placeholder="${escapeHtml(t("chat_ph"))}" /><button class="btn" data-act="send-chat">${t("send")}</button></div>
        <button class="ghost" data-act="leave-group">${t("leave")}</button>` : `
        <label>${t("group_name")}</label>
        <input type="text" id="gname" placeholder="${escapeHtml(t("group_ph"))}" />
        <button class="btn stack-gap" data-act="create-group">${t("create_g")}</button>
        <label>${t("have_code")}</label>
        <input type="text" id="gcode" placeholder="ABC123" />
        <button class="btn secondary stack-gap" data-act="join-group">${t("join")}</button>`}
      ${navHtml("group")}
    </div>`;
  } else if (state.screen === "plans") {
    body = `<div class="page has-nav"><h1>${t("plans_title")}</h1>${state.plans.length ? state.plans.map((item) => `<p class="hint">📅 ${item.planned_for ? formatDate(item.planned_for) : ""}</p>${cardHtml(item, "fav")}`).join("") : `<p class="empty">${t("plans_empty")}</p>`}${navHtml("plans")}</div>`;
  }

  let sheet = "";
  if (state.detail) {
    sheet = detailSheetHtml(state.detail);
  }

  const cal = `<button class="icon-btn cal-btn${state.screen === "plans" ? " on" : ""}" data-act="plans" aria-label="${t("plans_cal")}">📅</button>`;
  const setBtn = `<button class="icon-btn${state.screen === "settings" ? " on" : ""}" data-act="settings" aria-label="${t("settings")}"><img class="top-ico" src="/icons/settings.png" alt="" /></button>`;
  const accPhoto = state.account?.avatar_url;
  const accBtn = `<button class="icon-btn acc-btn${accPhoto ? " has-photo" : ""}${state.screen === "account" ? " on" : ""}" data-act="account" aria-label="${t("account")}">${accPhoto ? `<img class="acc-photo" src="${escapeHtml(accPhoto)}" alt="" />` : `<img class="top-ico" src="/icons/account.png" alt="" />`}</button>`;
  const leftExtra = back.includes("icon-btn") ? back : "";
  app.innerHTML = `<header class="topbar"><div class="top-left">${cal}${leftExtra}</div><div class="brand">Sinki</div><div class="top-actions">${setBtn}${accBtn}</div></header>${body}${sheet}${paywallHtml()}`;
  bind();
}

let searchTimer;
function bind() {
  app.onclick = async (e) => {
    const t = e.target.closest("[data-act],[data-pick],[data-fav],[data-like],[data-detail],[data-city],[data-country],[data-explore-city],[data-send-group],[data-route],[data-vote],[data-lang]");
    if (!t) return;
    const act = t.dataset.act;
    if (act === "intro-done") {
      state.intro = false;
      state.introArmed = false;
      clearTimeout(render.introTimer);
      render();
      return;
    }
    if (t.dataset.lang) {
      state.lang = t.dataset.lang;
      state.langQ = "";
      localStorage.setItem("sinki-lang", state.lang);
      applyDocumentLang();
      render();
      return;
    }
    if (act === "settings") { state.screen = "settings"; state.settingsView = "menu"; state.langQ = ""; state.profileHint = ""; render(); return; }
    if (act === "set-lang") { state.settingsView = "lang"; state.langQ = ""; render(); return; }
    if (act === "set-profile") { state.settingsView = "profile"; state.profileHint = ""; render(); return; }
    if (act === "close-paywall") { state.paywall = false; state.billingHint = ""; render(); return; }
    if (act === "pay-family") {
      state.payFamily = t.dataset.id || "plus";
      state.billingHint = "";
      render();
      return;
    }
    if (act === "pay-period") {
      const family = t.dataset.family || "plus";
      const period = t.dataset.id || "year";
      if (family === "plus") {
        state.plusPeriod = period;
        localStorage.setItem("sinki-plus-period", period);
      } else {
        state.unlimitedPeriod = period;
        localStorage.setItem("sinki-unlimited-period", period);
      }
      render();
      return;
    }
    if (act === "pay-buy") { await startPurchase(t.dataset.id); return; }
    if (act === "pay-restore") { await restorePurchases(); return; }
    if (act === "plus-go") {
      openPaywall("catalog");
      return;
    }
    if (act === "set-plan") { state.settingsView = "plan"; state.payFamily = "plus"; render(); return; }
    if (act === "plus-week") { state.plusPeriod = "week"; localStorage.setItem("sinki-plus-period", "week"); render(); return; }
    if (act === "plus-month") { state.plusPeriod = "month"; localStorage.setItem("sinki-plus-period", "month"); render(); return; }
    if (act === "plus-year") { state.plusPeriod = "year"; localStorage.setItem("sinki-plus-period", "year"); render(); return; }
    if (act === "set-events") {
      state.screen = "settings";
      state.settingsView = "events";
      render();
      loadOrganizerEvents();
      return;
    }
    if (act === "event-pay") {
      if (askEventPay()) return;
      state.eventId = "";
      state.eventBoostDays = 0;
      state.eventDraft = null;
      state.eventPhoto = "";
      state.profileHint = "";
      state.screen = "settings";
      state.settingsView = "event-edit";
      render();
      return;
    }
    if (act === "event-new") {
      if (askEventPay()) return;
      state.eventId = "";
      state.eventBoostDays = 0;
      state.eventDraft = null;
      state.eventPhoto = "";
      state.profileHint = "";
      state.settingsView = "event-edit";
      render();
      return;
    }
    if (act === "event-edit") {
      if (askEventPay()) return;
      state.settingsView = "event-edit";
      render();
      return;
    }
    if (act === "event-comment") {
      await sendEventComment();
      return;
    }
    if (act === "event-boost") {
      state.eventBoostDays = Number(t.dataset.id) || 0;
      render();
      return;
    }
    if (act === "event-approve") {
      await reviewOrganizerEvent(t.dataset.id, "approve");
      return;
    }
    if (act === "event-reject") {
      await reviewOrganizerEvent(t.dataset.id, "reject");
      return;
    }
    if (act === "event-next" || act === "event-save") {
      const name = ($("#evname") && $("#evname").value || "").trim();
      const description = ($("#evdesc") && $("#evdesc").value || "").trim();
      const address = ($("#evaddr") && $("#evaddr").value || "").trim();
      const when = ($("#evwhen") && $("#evwhen").value) || todayISO();
      const paid = $("#evpaid") && $("#evpaid").checked;
      const price = paid ? Number($("#evprice") && $("#evprice").value) : 0;
      const file = $("#evphoto") && $("#evphoto").files && $("#evphoto").files[0];
      state.eventDraft = { name, description, address, when, paid: !!paid, price: paid ? String($("#evprice") && $("#evprice").value || "") : "" };
      if (!name || !description || !address) {
        state.profileHint = t("ev_need_fields");
        render();
        return;
      }
      if (!file && !state.eventPhoto) {
        state.profileHint = t("ev_need_photo");
        render();
        return;
      }
      if (file && file.size > 500000) {
        state.profileHint = t("set_photo_err");
        render();
        return;
      }
      if (paid && !(price > 0)) {
        state.profileHint = t("ev_need_price");
        render();
        return;
      }
      const goBoosts = (photo) => {
        state.eventPhoto = photo;
        state.profileHint = "";
        state.eventBoostDays = Number(state.eventBoostDays) || 0;
        state.settingsView = "event-boosts";
        render();
      };
      if (file) {
        const reader = new FileReader();
        reader.onload = () => goBoosts(reader.result);
        reader.readAsDataURL(file);
        return;
      }
      goBoosts(state.eventPhoto);
      return;
    }
    if (act === "event-finish") {
      const d = state.eventDraft || {};
      if (!d.name || !state.eventPhoto) {
        state.settingsView = "event-edit";
        state.profileHint = t("ev_need_fields");
        render();
        return;
      }
      try {
        const extra = Number(state.eventBoostDays) || 0;
        let extraDays = extra;
        if (extra) {
          const prod = ((window.SINKI_CATALOG || {}).event || {})[extra];
          state.profileHint = t("pay_loading");
          render();
          const pay = await window.SinkiBilling.purchase(prod && prod.id, authHeaders());
          if (pay.status !== "purchased") {
            state.profileHint = pay.status === "cancelled" ? t("pay_cancel") : payErrorText(pay.code);
            render();
            return;
          }
          extraDays = extra;
        }
        const r = await fetch("/api/events", {
          method: "POST",
          headers: authHeaders(),
          body: JSON.stringify({
            name: d.name,
            description: d.description,
            address: d.address,
            when: d.when,
            photo: state.eventPhoto,
            price_min: d.paid ? Number(d.price) : 0,
            paid: true,
            extra_boost_days: extraDays,
          }),
        });
        const data = await r.json().catch(() => ({}));
        if (!r.ok) {
          state.profileHint = data.error === "photo" ? t("set_photo_err") : t("ev_need_fields");
          render();
          return;
        }
        state.settingsView = "events";
        state.eventDraft = null;
        state.eventPhoto = "";
        state.eventBoostDays = 0;
        state.profileHint = t("ev_sent");
        render();
        await loadOrganizerEvents();
      } catch {
        state.profileHint = t("ev_need_fields");
        render();
      }
      return;
    }
    if (act === "set-help") { state.settingsView = "help"; render(); return; }
    if (act === "set-contact") { state.settingsView = "contact"; render(); return; }
    if (act === "set-privacy") { state.settingsView = "privacy"; render(); return; }
    if (act === "set-terms") { state.settingsView = "terms"; render(); return; }
    if (act === "set-purchases") { state.settingsView = "purchases"; render(); return; }
    if (act === "set-legal") { state.settingsView = "legal"; render(); return; }
    if (act === "set-about") { state.settingsView = "about"; render(); return; }
    if (act === "set-notifs") { state.settingsView = "notifs"; render(); return; }
    if (act === "toggle-notifs-plans") {
      state.notifsPlans = !state.notifsPlans;
      localStorage.setItem("sinki-notifs-plans", state.notifsPlans ? "1" : "0");
      render();
      return;
    }
    if (act === "toggle-notifs-group") {
      state.notifsGroup = !state.notifsGroup;
      localStorage.setItem("sinki-notifs-group", state.notifsGroup ? "1" : "0");
      render();
      return;
    }
    if (act === "pick-avatar") {
      const file = $("#avatarfile");
      if (file) file.click();
      return;
    }
    if (act === "profile-save") { await saveProfileEdits(); return; }
    if (act === "account") {
      state.screen = "account";
      if (!state.account?.email && state.authView !== "code") state.authView = "closed";
      render();
      return;
    }
    if (act === "home") { state.screen = "home"; render(); return; }
    if (act === "start") { state.screen = "search"; state.step = 1; prefetchFeaturedCities(); render(); return; }
    if (act === "area-home") {
      applyHomeArea();
      state.countryQuery = "";
      state.countrySuggestions = [];
      state.city = null;
      state.query = "";
      state.suggestions = [];
      render();
      return;
    }
    if (act === "area-france") {
      applyHomeArea();
      state.countryQuery = "";
      state.countrySuggestions = [];
      state.city = null;
      state.query = "";
      state.suggestions = [];
      render();
      return;
    }
    if (act === "area-int") {
      if (askPlus()) return;
      state.area = "international";
      state.intCountry = null;
      state.city = null;
      state.query = "";
      state.suggestions = [];
      state.countryQuery = "";
      state.countrySuggestions = [];
      render();
      return;
    }
    if (act === "country-clear") {
      state.intCountry = null;
      state.city = null;
      state.query = "";
      state.suggestions = [];
      state.countryQuery = "";
      state.countrySuggestions = [];
      render();
      return;
    }
    if (act === "explore") { state.screen = "explore"; state.explorePickHome = false; render(); return; }
    if (act === "explore-home") {
      state.exploreScope = "home";
      localStorage.setItem("sinki-explore-scope", "home");
      state.explorePickHome = false;
      state.exploreQ = "";
      state.exploreCities = [];
      state.exploreOutings = [];
      render();
      return;
    }
    if (act === "explore-world") {
      if (askPlus()) return;
      state.exploreScope = "world";
      localStorage.setItem("sinki-explore-scope", "world");
      state.explorePickHome = false;
      state.exploreCity = null;
      state.exploreCityQ = "";
      state.exploreQ = "";
      state.exploreCities = [];
      state.exploreOutings = [];
      render();
      return;
    }
    if (act === "explore-change-home") {
      if (askPlus()) return;
      state.explorePickHome = true;
      state.countryQuery = "";
      state.countrySuggestions = [];
      render();
      return;
    }
    if (act === "explore-clear-country") {
      state.exploreCountry = null;
      state.exploreCity = null;
      state.exploreCityQ = "";
      state.exploreQ = "";
      state.exploreCities = [];
      state.exploreOutings = [];
      state.countryQuery = "";
      state.countrySuggestions = [];
      render();
      return;
    }
    if (act === "explore-clear-city") {
      state.exploreCity = null;
      state.exploreCityQ = "";
      state.exploreQ = "";
      state.exploreCities = [];
      state.exploreOutings = [];
      render();
      return;
    }
    if (act === "set-home-country") {
      if (askPlus()) return;
      state.settingsView = "home-country"; state.countryQuery = ""; state.countrySuggestions = []; render(); return;
    }
    if (act === "group") { state.screen = "group"; if (state.groupCode) refreshGroup(); else render(); return; }
    if (act === "favs") { state.screen = "favs"; render(); return; }
    if (act === "auth-login") { state.authMode = "login"; state.authView = "contact"; state.authError = ""; state.authHint = ""; render(); return; }
    if (act === "auth-signup") { state.authMode = "signup"; state.authView = "contact"; state.authError = ""; state.authHint = ""; render(); return; }
    if (act === "auth-open") { state.authView = "contact"; state.authError = ""; state.authHint = ""; render(); return; }
    if (act === "auth-back-names") { state.authView = "names"; state.authError = ""; render(); return; }
    if (act === "auth-close") { state.authView = "closed"; state.authError = ""; state.authHint = ""; render(); return; }
    if (act === "auth-next-contact") {
      state.authEmail = ($("#authemail") && $("#authemail").value) || state.authEmail;
      if (!validEmail(state.authEmail)) { state.authError = t("err_mail"); render(); return; }
      state.authError = "";
      if (state.authMode === "signup") { state.authView = "names"; render(); return; }
      await sendLoginCode();
      return;
    }
    if (act === "auth-next-names") {
      state.authFirst = (($("#authfirst") && $("#authfirst").value) || state.authFirst).trim();
      state.authLast = (($("#authlast") && $("#authlast").value) || state.authLast).trim();
      if (!validName(state.authFirst) || !validName(state.authLast)) { state.authError = t("err_name"); render(); return; }
      state.authError = "";
      state.authView = "pseudo";
      render();
      return;
    }
    if (act === "auth-send") {
      state.authPseudo = (($("#authpseudo") && $("#authpseudo").value) || state.authPseudo).trim();
      if (state.authMode === "signup" && !validPseudo(state.authPseudo)) { state.authError = t("err_pseudo"); render(); return; }
      if (state.authMode === "signup") {
        const chk = await fetch("/api/auth/pseudo?q=" + encodeURIComponent(state.authPseudo) + "&email=" + encodeURIComponent(state.authEmail || ""));
        const info = await chk.json().catch(() => ({}));
        if (info.taken) { state.authError = t("err_pseudo_taken"); render(); return; }
      }
      await sendLoginCode();
      return;
    }
    if (act === "auth-verify") { await verifyLoginCode(); return; }
    if (act === "logout") { logoutAccount(); return; }
    if (act === "account-delete-ask") { state.accountDeleteAsk = true; render(); return; }
    if (act === "account-delete-cancel") { state.accountDeleteAsk = false; render(); return; }
    if (act === "account-delete") { await deleteAccountForever(); return; }
    if (act === "plans") { state.screen = "plans"; render(); return; }
    if (act === "back") {
      if (state.screen === "settings" && state.settingsView && state.settingsView !== "menu") {
        state.settingsView = state.settingsView === "event-boosts" ? "event-edit" : state.settingsView === "event-edit" ? "events" : "menu";
        state.profileHint = "";
        render();
        return;
      }
      if (state.screen === "explore" && state.explorePickHome) {
        state.explorePickHome = false;
        state.countryQuery = "";
        state.countrySuggestions = [];
        render();
        return;
      }
      if (state.screen === "search" && state.step === 2) state.step = 1;
      else if (state.screen === "results") { state.screen = "search"; state.step = 2; }
      else { state.screen = "home"; }
      render(); return;
    }
    if (act === "create-group") {
      const name = ($("#gname") && $("#gname").value.trim()) || "Groupe Sinki";
      const nick = chatDisplayName();
      state.groupNick = nick;
      localStorage.setItem("sinki-nick", nick);
      const r = await fetch("/api/groups", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name }) });
      const g = await r.json();
      if (!r.ok) { alert(g.error || t("err_group")); return; }
      applyGroupState(g);
      render();
      persistAccount();
      return;
    }
    if (act === "join-group") {
      const code = (($("#gcode") && $("#gcode").value) || "").trim().toUpperCase();
      const nick = chatDisplayName();
      state.groupNick = nick;
      localStorage.setItem("sinki-nick", nick);
      const r = await fetch("/api/groups?code=" + encodeURIComponent(code));
      const g = await r.json();
      if (!r.ok || g.error) { alert(t("err_code")); return; }
      applyGroupState(g);
      render();
      persistAccount();
      return;
    }
    if (act === "leave-group") {
      state.groupCode = "";
      state.groupChat = [];
      state.groupPoll = null;
      state.groupVotes = {};
      state.shareHint = "";
      localStorage.removeItem("sinki-group-code");
      render();
      persistAccount();
      return;
    }
    if (act === "send-chat") {
      await sendGroupMessage(($("#chatmsg") && $("#chatmsg").value) || "", null);
      return;
    }
    if (act === "send-detail-group") {
      await sendGroupMessage("On part là ?", state.detail);
      state.detail = null;
      state.screen = "group";
      render();
      return;
    }
    if (act === "to2") { state.step = 2; render(); return; }
    if (act === "plus") { state.people = Math.min(12, state.people + 1); render(); return; }
    if (act === "minus") { state.people = Math.max(1, state.people - 1); render(); return; }
    if (act === "alt") {
      const alt = state.alts[Number(t.dataset.id)];
      if (!alt) return;
      if (alt.indoor) state.indoor = alt.indoor;
      if (alt.type) state.type = alt.type;
      if (alt.radius) state.radius = alt.radius;
      if (alt.unlimited) state.unlimited = true;
      await runSearch();
      return;
    }
    if (act === "geo") {
      await applyMyPosition();
      return;
    }
    if (act === "route-from-geo") {
      state.routeFrom = "geo";
      render();
      return;
    }
    if (act === "route-from-search") {
      state.routeFrom = "search";
      render();
      return;
    }
    if (act === "open-route") {
      await openDirections(state.detail);
      return;
    }
    if (act === "date-today") { state.date = todayISO(); render(); return; }
    if (act === "date-tom") { state.date = addDays(1); render(); return; }
    if (act === "date-week") { state.date = addDays(7); render(); return; }
    if (act === "b0") { state.unlimited = false; state.budget = 0; render(); return; }
    if (act === "b25") { state.unlimited = false; state.budget = 25; render(); return; }
    if (act === "b60") { state.unlimited = false; state.budget = 60; render(); return; }
    if (act === "bunlim") { state.unlimited = true; render(); return; }
    if (act === "search" || act === "resume") { if (act === "resume") applyLast(); await runSearch(); return; }
    if (act === "dice" && state.pool.length) {
      if (askQuota()) return;
      const ranked = pickThree(state.pool, state.vibe);
      const extra = state.pool.filter((o) => !ranked.some((r) => r.id === o.id));
      const bag = ranked.concat(extra.slice(0, 8));
      state.results = recordFound([bag[Math.floor(Math.random() * bag.length)]]);
      render();
      return;
    }
    if (act === "cheaper") { state.unlimited = false; state.budget = Math.max(0, state.budget - 15); await runSearch(); return; }
    if (act === "share") { await shareAndVote(); return; }
    if (act === "copy-code") {
      if (!state.groupCode) return;
      const ok = await copyText(state.groupCode);
      state.shareHint = ok ? t("copied", { code: state.groupCode }) : t("code_is", { code: state.groupCode });
      render();
      return;
    }
    if (act === "share-again") {
      if (!state.groupCode) return;
      const how = await shareText(voteShareText(state.groupCode, (state.groupPoll && state.groupPoll.options) || shareOptions()));
      if (how === "abort") return;
      state.shareHint = how === "shared" ? t("shared", { code: state.groupCode }) : how === "copied" ? t("copied_txt") : t("send_code_txt", { code: state.groupCode });
      render();
      return;
    }
    if (act === "edit") { state.screen = "search"; state.step = 2; render(); return; }
    if (act === "plan" && state.detail) {
      const row = { ...state.detail, planned_for: state.date };
      state.plans = [row, ...state.plans.filter((x) => x.id !== row.id)];
      save("sinki-plans", state.plans);
      persistAccount();
      state.detail = null;
      state.screen = "plans";
      render(); return;
    }
    if (act === "close-sheet") { if (e.target.classList.contains("sheet") || t.dataset.act === "close-sheet") { state.detail = null; render(); } return; }
    if (t.dataset.pick) {
      const key = t.dataset.pick;
      let val = t.dataset.id;
      if (key === "radius") val = Number(val);
      state[key] = val;
      render(); return;
    }
    if (t.dataset.like) {
      await toggleEventLike(t.dataset.like);
      return;
    }
    if (t.dataset.fav) {
      const item = findOuting(t.dataset.fav);
      if (!item) return;
      const exists = state.favs.some((x) => x.id === item.id);
      state.favs = exists ? state.favs.filter((x) => x.id !== item.id) : [item, ...state.favs];
      save("sinki-favs", state.favs);
      persistAccount();
      render(); return;
    }
    if (t.dataset.detail) {
      const item = findOuting(t.dataset.detail);
      if (!item) return;
      state.detail = { ...item, storyBusy: !item.story && !isEventItem(item) };
      render();
      if (!item.story && !isEventItem(item)) loadPlaceStory(item);
      return;
    }
    if (t.dataset.country) {
      const c = JSON.parse(decodeURIComponent(t.dataset.country));
      if (state.screen === "settings" && state.settingsView === "home-country") {
        saveHomeCountry(c, true);
        state.settingsView = "menu";
        state.countryQuery = "";
        state.countrySuggestions = [];
        render();
        return;
      }
      if (state.screen === "explore") {
        if (state.explorePickHome || state.exploreScope === "home") {
          saveHomeCountry(c, true);
          state.explorePickHome = false;
        } else {
          state.exploreCountry = { code: c.code, name: c.name };
          state.exploreCity = null;
          state.exploreCityQ = "";
        }
        state.countryQuery = "";
        state.countrySuggestions = [];
        state.exploreQ = "";
        state.exploreCities = [];
        state.exploreOutings = [];
        render();
        if (state.exploreScope === "home") runExplore();
        return;
      }
      state.intCountry = c;
      state.countryQuery = state.intCountry.name;
      state.countrySuggestions = [];
      state.city = null;
      state.query = "";
      state.suggestions = [];
      state.area = "international";
      render();
      return;
    }
    if (t.dataset.city) {
      state.city = JSON.parse(decodeURIComponent(t.dataset.city));
      state.query = state.city.name;
      state.suggestions = [];
      if (state.city.country_code && state.city.country_code !== "FR") {
        state.area = "international";
        if (!state.intCountry) state.intCountry = { code: state.city.country_code, name: state.city.country_code };
        if (state.radius < 30) state.radius = 30;
      } else {
        state.area = "france";
      }
      render();
      return;
    }
    if (t.dataset.exploreCity) {
      const c = JSON.parse(decodeURIComponent(t.dataset.exploreCity));
      if (state.exploreScope === "world") {
        state.exploreCity = c;
        state.exploreCityQ = c.name || "";
        state.exploreCities = [];
        state.exploreOutings = [];
        state.exploreQ = "";
        render();
        return;
      }
      await loadCityExplore(c);
      return;
    }
    if (t.dataset.sendGroup) {
      const item = findOuting(t.dataset.sendGroup);
      await sendGroupMessage("On part là ?", item);
      state.screen = "group";
      render();
      return;
    }
    if (t.dataset.vote) {
      await voteOuting(t.dataset.vote);
      return;
    }
    if (t.dataset.route) {
      const item = findOuting(t.dataset.route);
      if (item) await openDirections(item);
    }
  };

  const cityq = $("#cityq");
  if (cityq) {
    prefetchFeaturedCities();
    cityq.oninput = () => {
      state.query = cityq.value;
      state.city = null;
      clearTimeout(searchTimer);
      const typedNow = cityq.value;
      const ccNow = countryParam();
      const instant = localCityHits(ccNow, typedNow.trim());
      if (instant.length) {
        state.suggestions = instant;
        state.city = pickExactCity(typedNow, instant);
        paintLiveSearch();
        syncCityContinue();
      }
      searchTimer = setTimeout(async () => {
        if (state.query.trim().length < 1) {
          state.suggestions = [];
          paintLiveSearch();
          return;
        }
        const typed = $("#cityq") ? $("#cityq").value : state.query;
        state.query = typed;
        const cc = countryParam();
        if (!cc) { state.suggestions = []; paintLiveSearch(); return; }
        let rows = [];
        try {
          const r = await fetch("/api/cities?country=" + encodeURIComponent(cc) + "&q=" + encodeURIComponent(typed.trim()));
          if ($("#cityq") && $("#cityq").value !== typed) return;
          const data = await r.json();
          rows = Array.isArray(data) ? data : [];
        } catch {
          rows = [];
        }
        if ($("#cityq") && $("#cityq").value !== typed) return;
        rememberCityHits(cc, typed.trim(), rows);
        state.suggestions = rows;
        state.city = pickExactCity(typed, rows);
        paintLiveSearch();
        syncCityContinue();
      }, 60);
    };
  }
  const langq = $("#langq");
  if (langq) {
    langq.oninput = () => {
      state.langQ = langq.value;
      const box = document.querySelector(".lang-list");
      if (!box) { render(); return; }
      box.innerHTML = langListHtml();
    };
    if (!state.langQ) langq.focus();
  }
  const countryq = $("#countryq");
  if (countryq) {
    countryq.oninput = () => {
      state.countryQuery = countryq.value;
      clearTimeout(searchTimer);
      searchTimer = setTimeout(async () => {
        const typed = $("#countryq") ? $("#countryq").value : state.countryQuery;
        state.countryQuery = typed;
        if (typed.trim().length < 2) {
          state.countrySuggestions = [];
          paintLiveSearch();
          return;
        }
        const r = await fetch("/api/countries?q=" + encodeURIComponent(typed.trim()));
        if ($("#countryq") && $("#countryq").value !== typed) return;
        state.countrySuggestions = await r.json();
        if ($("#countryq") && $("#countryq").value !== typed) return;
        paintLiveSearch();
      }, 160);
    };
  }
  const date = $("#date");
  if (date) date.onchange = () => { state.date = date.value; };
  const budget = $("#budget");
  if (budget) budget.oninput = () => { state.unlimited = false; state.budget = Number(budget.value); $(".budget-val").textContent = state.budget === 0 ? "Gratuit" : state.budget + " € max"; };
  const exploreq = $("#exploreq");
  if (exploreq) {
    exploreq.oninput = () => {
      state.exploreQ = exploreq.value;
      clearTimeout(searchTimer);
      searchTimer = setTimeout(() => runExplore(), 140);
    };
  }
  const explorecity = $("#explorecity");
  if (explorecity) {
    explorecity.oninput = () => {
      state.exploreCityQ = explorecity.value;
      clearTimeout(searchTimer);
      searchTimer = setTimeout(() => runExploreCities(), 160);
    };
    if (!state.exploreCityQ) explorecity.focus();
  }
  const nick = $("#nick");
  if (nick) nick.onchange = () => { state.groupNick = nick.value.trim(); localStorage.setItem("sinki-nick", state.groupNick); persistAccount(); };
  const authemail = $("#authemail");
  if (authemail) authemail.oninput = () => { state.authEmail = authemail.value; };
  const authfirst = $("#authfirst");
  if (authfirst) authfirst.oninput = () => { state.authFirst = authfirst.value; };
  const authlast = $("#authlast");
  if (authlast) authlast.oninput = () => { state.authLast = authlast.value; };
  const authpseudo = $("#authpseudo");
  if (authpseudo) authpseudo.oninput = () => { state.authPseudo = authpseudo.value; };
  const authcode = $("#authcode");
  if (authcode) authcode.oninput = () => { state.authCode = authcode.value; };
  const evpaid = $("#evpaid");
  const wrap = $("#evprice-wrap");
  if (evpaid && wrap) {
    evpaid.onchange = () => {
      wrap.hidden = !evpaid.checked;
    };
  }
  const avatarfile = $("#avatarfile");
  if (avatarfile) {
    avatarfile.onchange = async () => {
      const file = avatarfile.files && avatarfile.files[0];
      if (!file) return;
      await uploadAvatarFile(file);
    };
  }
}

async function loadCountries() {
  const r = await fetch("/api/countries?q=" + encodeURIComponent(state.countryQuery || ""));
  state.countrySuggestions = await r.json();
  render();
}

async function loadAreaCities() {
  const cc = countryParam();
  if (!cc) {
    state.suggestions = [];
    render();
    return;
  }
  const r = await fetch("/api/cities?country=" + encodeURIComponent(cc) + "&q=");
  const rows = await r.json();
  state.suggestions = Array.isArray(rows) ? rows : [];
  render();
}

function exploreShopIntent(q) {
  return /(shopping|frip+e|frips?\b|thrift|vintage|mall|second[-\s]?hand)/i.test(String(q || ""));
}

function exploreActivityType(q) {
  const s = String(q || "").toLowerCase();
  if (exploreShopIntent(s)) return "shopping";
  if (/resto|restaurant|cafe|café|bar à|food/.test(s)) return "restaurants";
  if (/concert|soir[eé]e|club|night|karaoke/.test(s)) return "soirees";
  if (/mus[eé]e|museum|culture|galerie/.test(s)) return "culture";
  if (/rando|randonnée|hike/.test(s)) return "randonnee";
  if (/parc|balade|jardin|walk/.test(s)) return "balades";
  if (/activit/.test(s)) return "activites";
  return "all";
}

let exploreGen = 0;
async function runExploreCities() {
  const field = $("#explorecity");
  if (field) state.exploreCityQ = field.value;
  const q = (state.exploreCityQ || "").trim();
  const gen = ++exploreGen;
  const cc = (state.exploreCountry?.code || "").toUpperCase();
  if (!cc || q.length < 1) {
    state.exploreCities = [];
    state.exploreOutings = [];
    state.exploreLoading = false;
    paintLiveSearch();
    return;
  }
  state.exploreLoading = true;
  try {
    const r = await fetch("/api/cities?country=" + encodeURIComponent(cc) + "&q=" + encodeURIComponent(q));
    if (gen !== exploreGen) return;
    const rows = await r.json();
    if (gen !== exploreGen) return;
    state.exploreCities = Array.isArray(rows) ? rows : [];
    state.exploreOutings = [];
  } finally {
    if (gen === exploreGen) {
      state.exploreLoading = false;
      paintLiveSearch();
    }
  }
}

async function runExplore() {
  const field = $("#exploreq");
  if (field) state.exploreQ = field.value;
  const q = state.exploreQ.trim();
  const gen = ++exploreGen;
  if (state.explorePickHome || (state.exploreScope === "world" && !state.exploreCountry)) {
    state.exploreCities = [];
    state.exploreOutings = [];
    state.exploreLoading = false;
    paintLiveSearch();
    return;
  }
  if (state.exploreScope === "world" && state.exploreCountry && !state.exploreCity) {
    return;
  }
  if (state.exploreScope === "world" && state.exploreCity) {
    if (q.length < 2) {
      state.exploreOutings = [];
      state.exploreLoading = false;
      paintLiveSearch();
      return;
    }
    const city = state.exploreCity;
    const typ = exploreActivityType(q);
    state.exploreIntent = typ === "shopping" ? "shopping" : "";
    state.exploreLoading = true;
    try {
      const qs = new URLSearchParams({
        lat: String(city.latitude),
        lon: String(city.longitude),
        radius_km: typ === "shopping" ? "35" : "20",
        type: typ,
      });
      if (city.id) qs.set("city_id", String(city.id));
      if (typ === "shopping") qs.set("need_photo", "0");
      const r = await fetch("/api/outings?" + qs.toString());
      if (gen !== exploreGen) return;
      const data = await r.json();
      if (gen !== exploreGen) return;
      let rows = (Array.isArray(data) ? data : []).map(normalizeOuting);
      if (typ === "shopping") {
        const shop = rows.filter((o) => o.category === "Shopping" || exploreShopIntent(o.name));
        if (shop.length) rows = shop;
      }
      state.exploreOutings = rows;
      state.exploreCities = [];
    } finally {
      if (gen === exploreGen) {
        state.exploreLoading = false;
        paintLiveSearch();
      }
    }
    return;
  }
  const cc = exploreCountryCode();
  if (q.length < 1) {
    state.exploreCities = [];
    state.exploreOutings = [];
    state.exploreLoading = false;
    paintLiveSearch();
    return;
  }
  if (q.length <= 2) {
    state.exploreIntent = "";
    state.exploreLoading = true;
    try {
      const r = await fetch("/api/cities?country=" + encodeURIComponent(cc) + "&q=" + encodeURIComponent(q));
      if (gen !== exploreGen) return;
      const rows = await r.json();
      if (gen !== exploreGen) return;
      state.exploreCities = Array.isArray(rows) ? rows : [];
      state.exploreOutings = [];
    } finally {
      if (gen === exploreGen) {
        state.exploreLoading = false;
        paintLiveSearch();
      }
    }
    return;
  }
  const qs = new URLSearchParams();
  qs.set("q", q);
  if (cc) qs.set("country", cc);
  state.exploreIntent = exploreShopIntent(q) ? "shopping" : "";
  state.exploreLoading = true;
  try {
    const r = await fetch("/api/search?" + qs.toString());
    if (gen !== exploreGen) return;
    const data = await r.json();
    if (gen !== exploreGen) return;
    state.exploreCities = data.cities || [];
    state.exploreOutings = (data.outings || []).map(normalizeOuting);
    if (state.exploreIntent === "shopping") {
      const shop = state.exploreOutings.filter((o) => o.category === "Shopping" || exploreShopIntent(o.name));
      if (shop.length) state.exploreOutings = shop;
    }
  } finally {
    if (gen === exploreGen) {
      state.exploreLoading = false;
      paintLiveSearch();
    }
  }
}

async function loadCityExplore(city) {
  state.exploreLoading = true;
  state.exploreQ = city.name;
  render();
  const qs = new URLSearchParams({
    lat: String(city.latitude),
    lon: String(city.longitude),
    radius_km: state.exploreIntent === "shopping" ? "35" : "20",
  });
  if (city.id) qs.set("city_id", String(city.id));
  if (state.exploreIntent) qs.set("type", state.exploreIntent);
  if (state.exploreIntent === "shopping") qs.set("need_photo", "0");
  const r = await fetch("/api/outings?" + qs.toString());
  const data = await r.json();
  state.exploreOutings = (Array.isArray(data) ? data : []).map(normalizeOuting);
  state.exploreCities = [];
  state.exploreLoading = false;
  render();
}

async function sendGroupMessage(text, outing) {
  if (!state.groupCode) {
    state.screen = "group";
    render();
    alert(t("err_join_first"));
    return;
  }
  const r = await fetch("/api/groups/message", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      code: state.groupCode,
      name: chatDisplayName(),
      text,
      outing: outing ? { id: outing.id, name: outing.name, price_min: outing.price_min, price_max: outing.price_max, currency: outing.currency, photo_url: outing.photo_url, category: outing.category } : null,
    }),
  });
  const g = await r.json();
  if (!r.ok) { alert(g.error || t("err_msg")); return; }
  applyGroupState(g);
  render();
}

async function refreshGroup() {
  if (!state.groupCode) return;
  const r = await fetch("/api/groups?code=" + encodeURIComponent(state.groupCode));
  if (!r.ok) { render(); return; }
  const g = await r.json();
  applyGroupState(g);
  render();
}

async function shareAndVote() {
  const options = shareOptions();
  if (options.length < 2) {
    alert(t("err_two"));
    return;
  }
  const nick = chatDisplayName();
  state.groupNick = nick;
  localStorage.setItem("sinki-nick", nick);
  state.shareBusy = true;
  state.shareHint = "";
  render();
  try {
    if (!state.groupCode) {
      const created = await fetch("/api/groups", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: (state.city && state.city.name) ? "Sortie " + state.city.name : "Vote Sinki" }),
      });
      const g = await created.json();
      if (!created.ok) throw new Error(g.error || t("err_group"));
      applyGroupState(g);
    }
    const pollRes = await fetch("/api/groups/poll", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        code: state.groupCode,
        name: nick,
        outings: options.map((o) => ({
          id: o.id,
          name: o.name,
          price_min: o.price_min,
          price_max: o.price_max,
          currency: o.currency,
          photo_url: o.photo_url,
          category: o.category,
        })),
      }),
    });
    const pollGroup = await pollRes.json();
    if (!pollRes.ok) throw new Error(pollGroup.error || t("err_vote"));
    applyGroupState(pollGroup);
    persistAccount();
    const how = await shareText(voteShareText(state.groupCode, options));
    if (how === "abort") {
      state.shareHint = "Vote prêt. Code : " + state.groupCode;
    } else if (how === "shared") {
      state.shareHint = t("shared", { code: state.groupCode });
    } else if (how === "copied") {
      state.shareHint = "Texte copié. Envoie-le à tes potes — code " + state.groupCode + ".";
    } else {
      state.shareHint = "Vote prêt. Code à envoyer : " + state.groupCode;
      alert(voteShareText(state.groupCode, options));
    }
    state.screen = "group";
  } catch (err) {
    state.shareHint = String(err.message || err);
    alert(state.shareHint);
  } finally {
    state.shareBusy = false;
    render();
  }
}

async function voteOuting(outingId) {
  if (!state.groupCode) return;
  const nick = chatDisplayName();
  state.groupNick = nick;
  localStorage.setItem("sinki-nick", nick);
  const r = await fetch("/api/groups/vote", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      code: state.groupCode,
      name: nick,
      voter_id: voterId(),
      outing_id: outingId,
    }),
  });
  const g = await r.json();
  if (!r.ok) { alert(g.error || t("err_vote")); return; }
  applyGroupState(g);
  render();
}

function applyLast() {
  const last = lastSearch();
  if (!last) return;
  Object.assign(state, {
    city: last.city,
    query: last.city?.name || "",
    people: last.people || 2,
    date: last.date || todayISO(),
    budget: last.budget || 40,
    unlimited: last.budget == null,
    duration: last.duration || "half",
    vibe: vibeId(last.vibe || "fun"),
    type: last.type || "all",
    radius: last.radius || 15,
    indoor: last.indoor || "any",
    area: last.city?.country_code && last.city.country_code !== "FR" ? "international" : "france",
    intCountry: last.city?.country_code && last.city.country_code !== "FR" ? { code: last.city.country_code, name: last.city.country_name || last.city.country_code } : null,
  });
}

function matchesType(item, type) {
  if (!type || type === "all") return true;
  const cat = item.category || "";
  const kind = item.kind || "";
  if (type === "shopping") return cat === "Shopping";
  if (type === "restaurants") return cat === "Restaurants et cafés" || kind === "restaurant";
  if (type === "activites") return cat === "Activités et loisirs";
  if (type === "evenements") return kind === "event";
  if (type === "balades") return cat === "Lieux gratuits et balades" || cat === "Randonnées";
  if (type === "soirees") return cat === "Soirées et concerts" || /\b(bar|pub|club|night|karaoke|lounge|disco|beer|cocktail|rooftop)\b/i.test(item.name || "");
  if (type === "culture") return cat === "Musées et culture";
  if (type === "randonnee") return cat === "Randonnées";
  return true;
}

async function fetchOutingRows(opts) {
  const qs = new URLSearchParams({
    lat: String(state.city.latitude),
    lon: String(state.city.longitude),
    radius_km: String(opts.radius ?? state.radius),
    type: opts.type ?? state.type,
    indoor: opts.indoor ?? state.indoor,
  });
  if (state.city.id) qs.set("city_id", String(state.city.id));
  const unlimited = opts.unlimited ?? state.unlimited;
  const typ = opts.type ?? state.type;
  if (!unlimited && typ !== "shopping" && typ !== "randonnee") qs.set("budget", String(state.budget));
  const outRes = await fetch("/api/outings?" + qs.toString());
  const rows = await outRes.json();
  if (!outRes.ok || !Array.isArray(rows)) {
    const raw = (rows && (rows.error || rows.message)) || "";
    const txt = typeof raw === "string" ? raw : "";
    if (txt.includes("57014") || txt.toLowerCase().includes("timeout"))
      throw new Error(t("err_timeout"));
    throw new Error(t("err_load"));
  }
  return rows.map(normalizeOuting);
}

async function runSearch() {
  if (!state.city) return;
  if (askQuota()) return;
  state.loading = true;
  state.error = "";
  state.searchNote = "";
  state.alts = [];
  render();
  try {
    const [rows0, wRes] = await Promise.all([
      fetchOutingRows({}),
      fetch("/api/weather?lat=" + state.city.latitude + "&lon=" + state.city.longitude),
    ]);
    let rows = rows0;
    const cityName = state.city?.name || "ici";
    const alts = [];
    const usedType = rows.some((o) => o.search_relax === "type") ? "all" : state.type;
    if (state.indoor !== "any") alts.push({ label: t("alt_in"), indoor: "any" });
    if (state.type !== "all") alts.push({ label: t("alt_all"), type: "all" });
    if (!state.unlimited) alts.push({ label: t("alt_budget"), unlimited: true });
    if (state.radius < 80) alts.push({ label: t("alt_far"), radius: 80, indoor: "any", type: "all" });
    if (!rows.length && state.indoor !== "any") {
      rows = await fetchOutingRows({ indoor: "any" });
      if (rows.length) state.searchNote = t("note_out", { city: cityName });
    }
    if (!rows.length && state.type !== "all") {
      rows = await fetchOutingRows({ indoor: "any", type: "all" });
      if (rows.length) state.searchNote = t("note_type", { city: cityName });
    }
    if (!rows.length && !state.unlimited) {
      rows = await fetchOutingRows({ indoor: "any", type: "all", unlimited: true });
      if (rows.length) state.searchNote = t("note_budget", { city: cityName });
    }
    if (!rows.length && state.radius < 80) {
      rows = await fetchOutingRows({ indoor: "any", type: "all", unlimited: true, radius: 80 });
      if (rows.length) state.searchNote = t("note_far", { city: cityName });
    }
    const typeForMatch = rows.some((o) => o.search_relax === "type") ? "all" : usedType;
    const relaxIndoor = rows.some((o) => o.search_relax === "indoor");
    if (relaxIndoor && !state.searchNote) {
      state.searchNote = t("note_out2");
    }
    if (typeForMatch === "all" && state.type !== "all" && rows.length && !state.searchNote) {
      state.searchNote = t("note_type2", { city: cityName });
    }
    if (rows.some((o) => o.search_relax === "city") && !state.searchNote) {
      state.searchNote = t("note_city", { city: cityName });
    }
    state.alts = (!rows.length || state.searchNote) ? alts : [];
    state.pool = rows.filter((o) => typeForMatch === "all" || matchesType(o, typeForMatch));
    state.nearestFallback = state.pool.some((o) => o.search_fallback === "nearest");
    if (state.nearestFallback) state.pool.sort((a, b) => (a.distance_km ?? 99) - (b.distance_km ?? 99));
    state.results = recordFound(pickThree(state.pool, state.vibe));
    const w = await wRes.json();
    state.weather = weatherLabel(w.current?.weather_code, w.current?.temperature_2m);
    localStorage.setItem("sinki-last", JSON.stringify({
      city: state.city, people: state.people, date: state.date,
      budget: state.unlimited ? null : state.budget, duration: state.duration,
      moment: state.moment, radius: state.radius, type: state.type,
      vibe: state.vibe, indoor: state.indoor, transport: state.transport,
    }));
    state.screen = "results";
  } catch (err) {
    state.error = String(err.message || err);
  } finally {
    state.loading = false;
    render();
  }
}

async function sendLoginCode() {
  state.authEmail = (($("#authemail") && $("#authemail").value) || state.authEmail || "").trim();
  state.authBusy = true;
  state.authError = "";
  state.authHint = "";
  render();
  try {
    const r = await fetch("/api/auth/send", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        mode: state.authMode,
        email: state.authEmail,
        first_name: state.authFirst,
        last_name: state.authLast,
        nick: state.authPseudo,
      }),
    });
    const data = await r.json();
    if (!r.ok) throw new Error(friendlyAuthError(data.error || t("err_send_code")));
    state.authView = "code";
    state.authHint = "";
    state.authCode = "";
  } catch (err) {
    state.authError = String(err.message || err);
  } finally {
    state.authBusy = false;
    render();
  }
}

async function verifyLoginCode() {
  const token = (($("#authcode") && $("#authcode").value) || state.authCode || "").trim();
  state.authCode = token;
  state.authBusy = true;
  state.authError = "";
  render();
  try {
    const r = await fetch("/api/auth/verify", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        email: state.authEmail,
        token,
        first_name: state.authFirst,
        last_name: state.authLast,
        nick: state.authPseudo,
      }),
    });
    const data = await r.json();
    if (!r.ok) throw new Error(friendlyAuthError(data.error || t("err_bad_code")));
    state.session = { access_token: data.access_token, refresh_token: data.refresh_token };
    state.account = data.user;
    const chatName = (state.account && state.account.first_name) || state.authFirst || state.authPseudo;
    if (chatName) {
      state.groupNick = String(chatName).trim();
      localStorage.setItem("sinki-nick", state.groupNick);
    }
    save("sinki-session", state.session);
    save("sinki-account", state.account);
    await applyRemoteAccount();
    await persistAccount();
    state.authView = "closed";
    state.authCode = "";
    state.screen = "account";
  } catch (err) {
    state.authError = String(err.message || err);
  } finally {
    state.authBusy = false;
    render();
  }
}

function logoutAccount() {
  state.account = null;
  state.session = null;
  state.authView = "closed";
  state.accountDeleteAsk = false;
  localStorage.removeItem("sinki-session");
  localStorage.removeItem("sinki-account");
  render();
}

async function deleteAccountForever() {
  if (!state.session?.access_token) return;
  state.authBusy = true;
  state.authError = "";
  render();
  try {
    const r = await fetch("/api/me/delete", { method: "POST", headers: authHeaders() });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(data.error || t("account_delete_err"));
    ["sinki-session", "sinki-account", "sinki-favs", "sinki-plans", "sinki-quota", "sinki-event-credits", "sinki-group-code", "sinki-voter", "sinki-plan", "sinki-plus-period"].forEach((k) => localStorage.removeItem(k));
    state.account = null;
    state.session = null;
    state.favs = [];
    state.plans = [];
    state.groupCode = "";
    state.plan = "free";
    state.plusPeriod = "month";
    state.myEvents = [];
    state.authView = "closed";
    state.accountDeleteAsk = false;
    state.screen = "account";
  } catch (err) {
    state.authError = String(err.message || err);
    state.accountDeleteAsk = false;
  } finally {
    state.authBusy = false;
    render();
  }
}

async function saveProfileEdits() {
  if (!state.session?.access_token || !state.account) return;
  const first = (($("#profirst") && $("#profirst").value) || "").trim();
  const last = (($("#prolast") && $("#prolast").value) || "").trim();
  const nick = (($("#pronick") && $("#pronick").value) || "").trim();
  if (!validName(first) || !validName(last)) { state.profileHint = t("err_name"); render(); return; }
  if (nick && !validPseudo(nick)) { state.profileHint = t("err_pseudo"); render(); return; }
  if (nick) {
    const chk = await fetch("/api/auth/pseudo?q=" + encodeURIComponent(nick) + "&email=" + encodeURIComponent(state.account.email || ""));
    const info = await chk.json().catch(() => ({}));
    if (info.taken) { state.profileHint = t("err_pseudo_taken"); render(); return; }
  }
  state.account.first_name = first;
  state.account.last_name = last;
  state.account.nick = nick;
  state.groupNick = first;
  localStorage.setItem("sinki-nick", first);
  save("sinki-account", state.account);
  state.profileBusy = true;
  state.profileHint = "";
  render();
  try {
    const r = await fetch("/api/me/sync", {
      method: "POST",
      headers: authHeaders(),
      body: JSON.stringify({
        nick,
        first_name: first,
        last_name: last,
        group_code: state.groupCode || "",
        fav_ids: state.favs.map((x) => x.id).filter(Boolean),
        plans: state.plans.map((x) => ({ id: x.id, planned_for: x.planned_for, snapshot: x })),
      }),
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(data.error || t("err_send_code"));
    await applyRemoteAccount();
    state.profileHint = t("set_saved");
  } catch (err) {
    state.profileHint = friendlyAuthError(err.message || err);
  } finally {
    state.profileBusy = false;
    render();
  }
}

async function uploadAvatarFile(file) {
  if (!state.session?.access_token) return;
  if (file.size > 500000) { state.profileHint = t("set_photo_err"); render(); return; }
  state.profileBusy = true;
  state.profileHint = "";
  render();
  try {
    const dataUrl = await new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result);
      reader.onerror = () => reject(new Error("read"));
      reader.readAsDataURL(file);
    });
    const r = await fetch("/api/me/avatar", {
      method: "POST",
      headers: { ...authHeaders(), "Content-Type": "application/json" },
      body: JSON.stringify({ image: dataUrl, type: file.type }),
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(data.error || t("set_photo_err"));
    state.account = { ...state.account, avatar_url: data.avatar_url };
    save("sinki-account", state.account);
    state.profileHint = t("set_saved");
  } catch (err) {
    state.profileHint = String(err.message || t("set_photo_err"));
  } finally {
    state.profileBusy = false;
    render();
  }
}

async function applyRemoteAccount() {
  if (!state.session?.access_token) return;
  const r = await fetch("/api/me", { headers: authHeaders() });
  if (r.status === 401) { logoutAccount(); return; }
  if (!r.ok) return;
  const me = await r.json();
  state.account = me.user || state.account;
  save("sinki-account", state.account);
  applyEntitlements((me.user && me.user.entitlements) || {});
  if ((me.user && me.user.plan === "plus") || hasPlus()) {
    state.plan = "plus";
  }
  state.favs = mergeById(state.favs, (me.favs || []).map(normalizeOuting));
  save("sinki-favs", state.favs);
  state.plans = mergeById(state.plans, (me.plans || []).map(normalizeOuting));
  save("sinki-plans", state.plans);
  const chatName = (me.user && me.user.first_name) || me.nick;
  if (chatName) {
    state.groupNick = chatName;
    localStorage.setItem("sinki-nick", chatName);
  }
  if (me.group_code) {
    state.groupCode = me.group_code;
    localStorage.setItem("sinki-group-code", me.group_code);
    state.groupLabel = me.group?.origin_label || state.groupLabel;
    applyGroupState(me.group);
  }
}

async function loadPublicEvents() {
  try {
    const r = await fetch("/api/events", { headers: authHeaders() });
    const data = await r.json();
    state.publicEvents = data.events || [];
  } catch {
    state.publicEvents = [];
  }
}

async function loadOrganizerEvents() {
  if (!state.session?.access_token) return;
  try {
    const mine = await fetch("/api/events?mine=1", { headers: authHeaders() });
    if (mine.ok) {
      const data = await mine.json();
      state.myEvents = data.events || [];
    }
  } catch {
    state.myEvents = [];
  }
  try {
    const pending = await fetch("/api/events?pending=1", { headers: authHeaders() });
    state.isModerator = pending.ok;
    if (pending.ok) {
      const data = await pending.json();
      state.pendingEvents = data.events || [];
    } else {
      state.pendingEvents = [];
    }
  } catch {
    state.isModerator = false;
    state.pendingEvents = [];
  }
  render();
}

async function reviewOrganizerEvent(id, action) {
  const r = await fetch("/api/events/review", {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify({ id, action }),
  });
  if (!r.ok) return;
  await loadPublicEvents();
  await loadOrganizerEvents();
}

function applyEntitlements(ents) {
  if (!ents || typeof ents !== "object") return;
  if (!state.account) state.account = {};
  state.account.entitlements = ents;
  if ((ents.plus || {}).active) {
    state.plan = "plus";
    state.account.plan = "plus";
  } else if (state.account.plan === "plus" && !(ents.plus || {}).active) {
    /* keep legacy server plan until it expires from account.plan */
  }
  save("sinki-account", state.account);
}
function payErrorText(code) {
  if (code === "store_unavailable" || code === "store" || code === "unverified") return t("pay_store_later");
  if (code === "auth") return t("plus_need_account");
  return t("pay_err");
}
async function startPurchase(productId) {
  const id = String(productId || "");
  if (!id) return;
  if (!state.session?.access_token) {
    state.paywall = false;
    state.screen = "account";
    state.authHint = t("plus_need_account");
    render();
    return;
  }
  const prod = window.sinkiProduct ? window.sinkiProduct(id) : null;
  if (prod && ownsFamilyPeriod(prod.family === "noads" ? "noads" : prod.family, prod.period) && prod.family !== "event") {
    state.billingHint = t("pay_already");
    render();
    return;
  }
  state.billingBusy = id;
  state.billingHint = t("pay_loading");
  render();
  const res = await window.SinkiBilling.purchase(id, authHeaders());
  state.billingBusy = "";
  if (res.status === "purchased") {
    applyEntitlements(res.entitlements);
    state.billingHint = t("pay_ok");
    if (id === "sinki.event.publish") {
      state.paywall = false;
      state.screen = "settings";
      state.settingsView = "event-edit";
    }
  } else if (res.status === "cancelled") {
    state.billingHint = t("pay_cancel");
  } else {
    state.billingHint = payErrorText(res.code);
  }
  render();
}
async function restorePurchases() {
  if (!state.session?.access_token) {
    state.screen = "account";
    state.authHint = t("plus_need_account");
    state.paywall = false;
    render();
    return;
  }
  state.billingBusy = "restore";
  state.billingHint = t("pay_loading");
  render();
  const res = await window.SinkiBilling.restore(authHeaders());
  state.billingBusy = "";
  if (res.status === "ok") {
    applyEntitlements(res.entitlements);
    state.billingHint = t("pay_restore_ok");
  } else {
    state.billingHint = payErrorText(res.code);
  }
  render();
}

async function persistAccount() {
  if (!state.session?.access_token) return;
  const body = {
    nick: state.account?.nick || "",
    first_name: state.account?.first_name || state.authFirst || "",
    last_name: state.account?.last_name || state.authLast || "",
    phone: state.account?.phone || "",
    group_code: state.groupCode || "",
    fav_ids: state.favs.map((x) => x.id).filter(Boolean),
    plans: state.plans.map((x) => ({ id: x.id, planned_for: x.planned_for, snapshot: x })),
  };
  const r = await fetch("/api/me/sync", { method: "POST", headers: authHeaders(), body: JSON.stringify(body) });
  if (r.status === 401) logoutAccount();
}

async function bootAccount() {
  const hash = new URLSearchParams((location.hash || "").replace(/^#/, ""));
  const access = hash.get("access_token");
  const refresh = hash.get("refresh_token");
  if (access) {
    state.session = { access_token: access, refresh_token: refresh || "" };
    save("sinki-session", state.session);
    history.replaceState(null, "", location.pathname + location.search);
  }
  if (!state.session?.access_token) return;
  try {
    await applyRemoteAccount();
    await persistAccount();
  } catch {
    /* keep local data */
  }
}

bootAccount().then(() => {
  loadPublicEvents().then(render);
  loadOrganizerEvents();
  render();
});
applyHomeArea();
if (!hasPlus() && state.exploreScope === "world") {
  state.exploreScope = "home";
  localStorage.setItem("sinki-explore-scope", "home");
}
detectHomeCountry();
render();
