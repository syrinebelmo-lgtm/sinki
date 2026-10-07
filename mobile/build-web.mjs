// Copie les fichiers publics de ../web dans www/ (embarqués dans l'app) et
// indique à l'app l'adresse du serveur en ligne (SINKI_API_BASE).
import { cpSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const web = join(here, "..", "web");
const out = join(here, "www");
const apiBase = process.env.SINKI_API_BASE || "https://sinki.onrender.com";

const files = [
  "index.html", "privacy.html", "delete-account.html",
  "app.js", "i18n.js", "catalog.js", "billing.js", "styles.css",
  "favicon.svg", "biche-sinki.png",
];
const dirs = ["biche", "icons", "public"];

rmSync(out, { recursive: true, force: true });
mkdirSync(out, { recursive: true });
for (const f of files) cpSync(join(web, f), join(out, f));
for (const d of dirs) cpSync(join(web, d), join(out, d), { recursive: true });

const marker = '<script src="/i18n.js';
let html = readFileSync(join(out, "index.html"), "utf8");
if (!html.includes(marker)) throw new Error("index.html: i18n script tag not found");
html = html.replace(marker, `<script>window.SINKI_API_BASE = ${JSON.stringify(apiBase)};</script>\n    ${marker}`);
writeFileSync(join(out, "index.html"), html);
console.log("www/ prêt → API", apiBase);
