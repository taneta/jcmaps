// Counts visits with GoatCounter, without cookies and without anything that says who a visitor is. GoatCounter's
// script counts the page view, without the map's filters (they sit after the #). Once a day this also counts
// "new-visitor" or "returning-visitor", from the date of this browser's last visit, which only this browser keeps.
const LAST_VISIT = "jcmaps-last-visit";
const today = new Date().toDateString();

let last = today; // no storage, no telling new from returning: count the page view only
try { const seen = localStorage.getItem(LAST_VISIT); localStorage.setItem(LAST_VISIT, today); last = seen; } catch {}
const visitor = last === today ? null : last ? "returning-visitor" : "new-visitor";

// A pinned version of the script, checked against its hash (goatcounter.com/help/countjs-versions).
const script = Object.assign(document.createElement("script"), {
  src: "https://gc.zgo.at/count.v5.js", crossOrigin: "anonymous",
  integrity: "sha384-atnOLvQb9t+jTSipvd75X2yginT4PjVbqDdlJAmxMm+wYElFmeR6EmLP5bYeoRVQ",
});
script.dataset.goatcounter = "https://jcmaps.goatcounter.com/count";
// No referrer on the event, so "which sites sent visitors" counts page views only.
if (visitor) script.addEventListener("load", () => window.goatcounter.count({ path: visitor, title: "", referrer: "", event: true }));
document.head.append(script);
