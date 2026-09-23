import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { fetchOutings, loadRootEnv, searchCities } from "./api.mjs";

loadRootEnv();
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const dist = path.join(__dirname, "dist");
const port = Number(process.env.PORT || 5173);

const mime = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".png": "image/png",
  ".svg": "image/svg+xml",
  ".webmanifest": "application/manifest+json",
  ".json": "application/json",
};

http
  .createServer(async (req, res) => {
    try {
      const url = new URL(req.url, "http://localhost");
      if (url.pathname.startsWith("/api/")) {
        const p = url.pathname.replace(/\/$/, "");
        if (p === "/api/cities") {
          const cities = await searchCities(url.searchParams.get("q") || "");
          res.writeHead(200, { "Content-Type": "application/json" });
          res.end(JSON.stringify(cities));
          return;
        }
        if (p === "/api/outings") {
          const outings = await fetchOutings(Object.fromEntries(url.searchParams));
          res.writeHead(200, { "Content-Type": "application/json" });
          res.end(JSON.stringify(outings));
          return;
        }
        if (p === "/api/weather") {
          const wr = await fetch(
            "https://api.open-meteo.com/v1/forecast?latitude=" +
              url.searchParams.get("lat") +
              "&longitude=" +
              url.searchParams.get("lon") +
              "&current=temperature_2m,weather_code"
          );
          res.writeHead(200, { "Content-Type": "application/json" });
          res.end(JSON.stringify(await wr.json()));
          return;
        }
        res.writeHead(404);
        res.end();
        return;
      }
      let file = path.join(dist, url.pathname === "/" ? "index.html" : url.pathname);
      if (!file.startsWith(dist)) {
        res.writeHead(403);
        res.end();
        return;
      }
      if (!fs.existsSync(file) || fs.statSync(file).isDirectory()) {
        file = path.join(dist, "index.html");
      }
      const ext = path.extname(file);
      res.writeHead(200, { "Content-Type": mime[ext] || "application/octet-stream" });
      fs.createReadStream(file).pipe(res);
    } catch (err) {
      res.writeHead(500, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ error: String(err.message || err) }));
    }
  })
  .listen(port, () => console.log("Sinki http://localhost:" + port));
