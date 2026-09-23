import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { fetchOutings, loadRootEnv, searchCities } from "./api.mjs";

loadRootEnv();

function sinkiApi() {
  return {
    name: "sinki-api",
    configureServer(server) {
      server.middlewares.use("/api", async (req, res, next) => {
        try {
          const url = new URL(req.url, "http://localhost");
          let path = url.pathname.replace(/\/$/, "") || "/";
          if (path.startsWith("/api/")) path = path.slice(4);
          if (!path.startsWith("/")) path = "/" + path;
          if (path === "/cities") {
            const cities = await searchCities(url.searchParams.get("q") || "");
            res.setHeader("Content-Type", "application/json");
            res.end(JSON.stringify(cities));
            return;
          }
          if (path === "/outings") {
            const outings = await fetchOutings(Object.fromEntries(url.searchParams));
            res.setHeader("Content-Type", "application/json");
            res.end(JSON.stringify(outings));
            return;
          }
          if (path === "/weather") {
            const lat = url.searchParams.get("lat");
            const lon = url.searchParams.get("lon");
            const wr = await fetch(
              "https://api.open-meteo.com/v1/forecast?latitude=" +
                lat +
                "&longitude=" +
                lon +
                "&current=temperature_2m,weather_code"
            );
            const json = await wr.json();
            res.setHeader("Content-Type", "application/json");
            res.end(JSON.stringify(json));
            return;
          }
          next();
        } catch (err) {
          res.statusCode = 500;
          res.setHeader("Content-Type", "application/json");
          res.end(JSON.stringify({ error: String(err.message || err) }));
        }
      });
    },
  };
}

export default defineConfig({
  plugins: [react(), sinkiApi()],
  server: { port: 5173, host: true },
});
