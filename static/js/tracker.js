/**
 * SmartReco behavioral tracker.
 *
 * Design goals: never block the UI thread, never delay navigation, and avoid
 * flooding the backend with high-frequency noise (no raw mousemove/scroll).
 * Events are buffered in memory and flushed in batches on a timer, when the
 * buffer fills, or when the page is hidden/unloaded (via sendBeacon, which is
 * fire-and-forget and survives navigation).
 */
(function () {
  var ENDPOINT = "/api/events/batch";
  var FLUSH_INTERVAL_MS = 5000;
  var MAX_BUFFER = 10;
  var TIME_HEARTBEAT_MS = 15000;

  var buffer = [];
  var pageEnteredAt = Date.now();
  var productViewStart = null;
  var currentProductId = null;

  function enqueue(eventType, payload) {
    buffer.push({
      event_type: eventType,
      product_id: (payload && payload.product_id) || null,
      query: (payload && payload.query) || null,
      duration_ms: (payload && payload.duration_ms) || null,
      meta: payload || null,
      ts: Date.now(),
    });
    if (buffer.length >= MAX_BUFFER) {
      flush();
    }
  }

  function flush(useBeacon) {
    if (buffer.length === 0) return;
    var events = buffer;
    buffer = [];
    var body = JSON.stringify({ events: events });

    if (useBeacon && navigator.sendBeacon) {
      var blob = new Blob([body], { type: "application/json" });
      var ok = navigator.sendBeacon(ENDPOINT, blob);
      if (ok) return;
    }

    fetch(ENDPOINT, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: body,
      keepalive: true,
      credentials: "same-origin",
    }).catch(function () {
      /* best-effort: dropped events don't break the UX */
    });
  }

  function trackProductView(productId) {
    currentProductId = productId;
    productViewStart = Date.now();
    enqueue("product_view", { product_id: productId });
  }

  function flushTimeSpent() {
    if (currentProductId && productViewStart) {
      var duration = Date.now() - productViewStart;
      if (duration > 1000) {
        enqueue("time_spent", { product_id: currentProductId, duration_ms: duration });
      }
      productViewStart = Date.now();
    }
  }

  setInterval(flush, FLUSH_INTERVAL_MS);
  setInterval(function () {
    if (document.visibilityState === "visible") flushTimeSpent();
  }, TIME_HEARTBEAT_MS);

  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState === "hidden") {
      flushTimeSpent();
      flush(true);
    }
  });
  window.addEventListener("pagehide", function () {
    flushTimeSpent();
    flush(true);
  });

  document.addEventListener("DOMContentLoaded", function () {
    enqueue("page_view", { path: window.location.pathname });
  });

  window.SmartReco = {
    track: enqueue,
    trackProductView: trackProductView,
    flush: flush,
  };
})();
