import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";

const source = readFileSync(new URL("../web/app.js", import.meta.url), "utf8");
const section = (start, end) => source.slice(source.indexOf(start), source.indexOf(end));
const context = {
  state: {
    type: "all", city: { id: 1, latitude: 45.75, longitude: 4.85 },
    radius: 15, indoor: "any", unlimited: true, budget: 20,
  },
  typeList: () => [["all"], ["activites"], ["shopping"], ["restaurants"]],
  isNightlifeItem: () => false,
  isCultureShow: () => false,
  normalizeOuting: (item) => item,
  outingsInflight: new Map(),
  URLSearchParams,
  Map,
  Set,
};
vm.createContext(context);
vm.runInContext(section("function selectedTypes(", "function isFav("), context);
vm.runInContext(section("function matchesType(", "function outingPriceEur("), context);
vm.runInContext(section("async function fetchOutingRows(", "async function runSearch("), context);

test("category chips select, deselect and restore all", () => {
  context.toggleType("activites");
  context.toggleType("shopping");
  assert.equal(context.state.type, "activites,shopping");
  assert.equal(context.matchesType({ category: "Shopping" }, context.state.type), true);
  assert.equal(context.matchesType({ category: "Activités et loisirs" }, context.state.type), true);
  assert.equal(context.matchesType({ category: "Restaurants et cafés" }, context.state.type), false);
  context.toggleType("activites");
  assert.equal(context.state.type, "shopping");
  context.toggleType("shopping");
  assert.equal(context.state.type, "all");
});

test("multi category search requests every selection and deduplicates results", async () => {
  context.state.type = "activites,shopping";
  const requested = [];
  context.fetch = async (url) => {
    const type = new URL(url, "https://sinki.test").searchParams.get("type");
    requested.push(type);
    return { ok: true, json: async () => type === "shopping" ? [{ id: "shop" }, { id: "shared" }] : [{ id: "activity" }, { id: "shared" }] };
  };
  const rows = await context.fetchOutingRows({});
  assert.deepEqual(requested.sort(), ["activites", "shopping"]);
  assert.deepEqual(Array.from(rows, (row) => row.id).sort(), ["activity", "shared", "shop"]);
});
