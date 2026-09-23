/* Pont achats : IAP natif (StoreKit / Play) s’il est branché, sinon pas de faux succès. */
window.SinkiBilling = {
  async purchase(productId, headers) {
    const id = String(productId || "");
    if (!id) return { status: "error", code: "unknown" };
    const iap = window.SinkiIAP;
    if (iap && typeof iap.purchase === "function") {
      try {
        const native = await iap.purchase(id);
        if (!native || native.cancelled) return { status: "cancelled" };
        if (!native.receipt) return { status: "error", code: "unverified" };
        const r = await fetch("/api/billing/confirm", {
          method: "POST",
          headers: headers || { "Content-Type": "application/json" },
          body: JSON.stringify({
            productId: id,
            receipt: native.receipt,
            platform: native.platform || "ios",
          }),
        });
        const data = await r.json().catch(() => ({}));
        if (!r.ok) return { status: "error", code: data.error || "store", entitlements: data.entitlements };
        if (!data.ok || !data.verified) return { status: "error", code: "unverified" };
        return { status: "purchased", entitlements: data.entitlements || {} };
      } catch (err) {
        return { status: "error", code: "store", message: String(err && err.message || err) };
      }
    }
    return { status: "error", code: "store_unavailable" };
  },

  async restore(headers) {
    const iap = window.SinkiIAP;
    if (iap && typeof iap.restore === "function") {
      try {
        const native = await iap.restore();
        const r = await fetch("/api/billing/restore", {
          method: "POST",
          headers: headers || { "Content-Type": "application/json" },
          body: JSON.stringify({
            receipts: (native && native.receipts) || [],
            platform: (native && native.platform) || "ios",
          }),
        });
        const data = await r.json().catch(() => ({}));
        if (!r.ok) return { status: "error", code: data.error || "store", entitlements: data.entitlements };
        return { status: "ok", entitlements: data.entitlements || {} };
      } catch (err) {
        return { status: "error", code: "store", message: String(err && err.message || err) };
      }
    }
    const r = await fetch("/api/billing/entitlements", { headers: headers || {} });
    if (r.status === 401) return { status: "error", code: "auth" };
    const data = await r.json().catch(() => ({}));
    if (!r.ok) return { status: "error", code: data.error || "store" };
    return { status: "ok", entitlements: data.entitlements || {} };
  },

  async storePrices(ids) {
    const iap = window.SinkiIAP;
    if (iap && typeof iap.products === "function") {
      try {
        return await iap.products(ids || []);
      } catch {
        return null;
      }
    }
    return null;
  },
};
