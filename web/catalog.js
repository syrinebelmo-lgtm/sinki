/* Catalogue unique des offres Sinki (EUR de référence + ids stores). */
window.SINKI_CATALOG = {
  plus: {
    week: { id: "sinki.plus.week", family: "plus", period: "week", eur: 2.99, apple: "sinki.plus.week", google: "sinki.plus.week", grants: ["plus", "unlimited"] },
    month: { id: "sinki.plus.month", family: "plus", period: "month", eur: 9.99, apple: "sinki.plus.month", google: "sinki.plus.month", grants: ["plus", "unlimited"] },
    year: { id: "sinki.plus.year", family: "plus", period: "year", eur: 99.99, apple: "sinki.plus.year", google: "sinki.plus.year", grants: ["plus", "unlimited"] },
  },
  unlimited: {
    week: { id: "sinki.unlimited.week", family: "unlimited", period: "week", eur: 1.99, apple: "sinki.unlimited.week", google: "sinki.unlimited.week", grants: ["unlimited"] },
    month: { id: "sinki.unlimited.month", family: "unlimited", period: "month", eur: 7.99, apple: "sinki.unlimited.month", google: "sinki.unlimited.month", grants: ["unlimited"] },
    year: { id: "sinki.unlimited.year", family: "unlimited", period: "year", eur: 89.99, apple: "sinki.unlimited.year", google: "sinki.unlimited.year", grants: ["unlimited"] },
  },
  event: {
    publish: { id: "sinki.event.publish", family: "event", period: "once", eur: 4.99, days: 1, apple: "sinki.event.publish", google: "sinki.event.publish" },
    3: { id: "sinki.event.boost.3", family: "event", period: "once", eur: 7.99, days: 3, apple: "sinki.event.boost.3", google: "sinki.event.boost.3" },
    7: { id: "sinki.event.boost.7", family: "event", period: "once", eur: 12.99, days: 7, apple: "sinki.event.boost.7", google: "sinki.event.boost.7" },
    30: { id: "sinki.event.boost.30", family: "event", period: "once", eur: 39.99, days: 30, apple: "sinki.event.boost.30", google: "sinki.event.boost.30" },
  },
  noads: {
    lifetime: { id: "sinki.noads.lifetime", family: "noads", period: "lifetime", eur: 5.99, apple: "sinki.noads.lifetime", google: "sinki.noads.lifetime" },
  },
};

window.sinkiProduct = function sinkiProduct(id) {
  const cat = window.SINKI_CATALOG || {};
  let found = null;
  Object.keys(cat).forEach((fam) => {
    Object.keys(cat[fam] || {}).forEach((k) => {
      const p = cat[fam][k];
      if (p && p.id === id) found = p;
    });
  });
  return found;
};

window.sinkiSavePct = function sinkiSavePct(weekEur, price, period) {
  const w = Number(weekEur);
  const p = Number(price);
  if (!(w > 0) || !(p > 0) || period === "week") return 0;
  const eq = period === "year" ? w * 52 : w * (52 / 12);
  if (eq <= p) return 0;
  return Math.round((1 - p / eq) * 100);
};
