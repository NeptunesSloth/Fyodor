// Before the app: if this browser can't run it at all (too old to read the app's code), say so instead of a black page.
// A file of its own, not inline in index.html: the server's Content-Security-Policy (script-src 'self') blocks inline scripts,
// so inline this notice never ran (and every page load logged a CSP error).
(function () {
  var shown = false;
  function show(why) {
    if (shown) return; shown = true;
    var r = document.getElementById("root");
    if (r && r.children.length) return;
    document.body.innerHTML = '<div style="font:15px/1.5 system-ui,sans-serif;color:#eadfc8;background:#14110d;position:fixed;inset:0;padding:32px">' +
      '<h1 style="font:600 24px Georgia,serif;color:#e0bd73">Fyodor can\'t start in this browser</h1>' +
      '<p>This browser is too old for Fyodor. Install a current Microsoft Edge or Google Chrome (copy its installer over from another computer if this one is offline), then open this page again.</p>' +
      '<pre style="white-space:pre-wrap;font:12px monospace;color:#cbbf9f">' + String(why).replace(/</g, "&lt;") + "\n\nBrowser: " + navigator.userAgent.replace(/</g, "&lt;") + "</pre></div>";
  }
  window.addEventListener("error", function (e) { if (!window.__fyodorStarted) show(e.message || e); });
  setTimeout(function () { if (!window.__fyodorStarted) show("The app did not start."); }, 30000);
})();
