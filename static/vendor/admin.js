/* Admin game edit: "Now" for the publication date, paste a thumbnail from the clipboard. */
(function () {
  "use strict";

  function today() {
    var d = new Date();
    var pad = function (n) { return (n < 10 ? "0" : "") + n; };
    return d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate());
  }

  document.addEventListener("click", function (e) {
    var btn = e.target.closest("[data-set-today]");
    if (!btn) return;
    var input = document.querySelector(btn.getAttribute("data-set-today"));
    if (input) input.value = today();
  });

  var input = document.querySelector("input[type=file][data-paste-target]");
  if (!input) return;
  var preview = document.getElementById(input.getAttribute("data-paste-target"));
  var status = document.getElementById(input.getAttribute("data-paste-status"));
  var pasteBtn = document.querySelector("[data-paste-button]");

  function show(file, how) {
    if (preview) {
      if (preview.dataset.url) URL.revokeObjectURL(preview.dataset.url);
      preview.dataset.url = URL.createObjectURL(file);
      preview.src = preview.dataset.url;
      preview.hidden = false;
    }
    if (status) status.textContent = how + ": " + file.type + ", " + Math.max(1, Math.round(file.size / 1024)) + " KB (saved on Save)";
  }

  function useBlob(blob, how) {
    var ext = (blob.type.split("/")[1] || "png").replace("jpeg", "jpg");
    var file = new File([blob], "pasted." + ext, { type: blob.type });
    var dt = new DataTransfer();
    dt.items.add(file);
    input.files = dt.files;
    show(file, how);
  }

  input.addEventListener("change", function () {
    if (input.files[0]) show(input.files[0], "Selected");
  });

  // Ctrl+V anywhere on the page; text pastes into fields are left alone.
  document.addEventListener("paste", function (e) {
    var items = (e.clipboardData && e.clipboardData.items) || [];
    for (var i = 0; i < items.length; i++) {
      if (items[i].kind === "file" && items[i].type.indexOf("image/") === 0) {
        e.preventDefault();
        useBlob(items[i].getAsFile(), "Pasted");
        return;
      }
    }
  });

  // Button: async Clipboard API (secure context; the browser may ask for permission).
  if (pasteBtn) {
    if (!navigator.clipboard || !navigator.clipboard.read) {
      pasteBtn.hidden = true;
      return;
    }
    pasteBtn.addEventListener("click", function () {
      navigator.clipboard.read().then(function (items) {
        for (var i = 0; i < items.length; i++) {
          for (var j = 0; j < items[i].types.length; j++) {
            var type = items[i].types[j];
            if (type.indexOf("image/") === 0) {
              return items[i].getType(type).then(function (blob) { useBlob(blob, "Pasted"); });
            }
          }
        }
        if (status) status.textContent = "No image in the clipboard";
      }).catch(function (err) {
        if (status) status.textContent = "Clipboard not available (" + err.name + "), press Ctrl+V instead";
      });
    });
  }
})();
