/* Admin helpers.
   Table rows (themes): forms marked data-ajax-row save in place, without reloading the page.
   Game edit: "Now" for the publication date, paste a thumbnail from the clipboard. */
(function () {
  "use strict";

  function setStatus(el, text, isError) {
    if (!el) return;
    clearTimeout(el._timer);
    el.textContent = text;
    el.style.color = isError ? "#b00" : "#070";
    if (!isError && text === "Saved") {
      el._timer = setTimeout(function () { el.textContent = ""; }, 2500);
    }
  }

  function formData(form, submitter) {
    try {
      return new FormData(form, submitter);
    } catch (e) { // browsers without the submitter argument
      var data = new FormData(form);
      if (submitter && submitter.name) data.append(submitter.name, submitter.value);
      return data;
    }
  }

  // Typing in a row's field marks it unsaved (fields join the row's form via form="…").
  document.addEventListener("input", function (e) {
    var form = e.target.form;
    if (form && form.hasAttribute("data-ajax-row")) {
      setStatus(form.querySelector(".row-status"), "Unsaved", false);
    }
  });

  document.addEventListener("submit", function (e) {
    var form = e.target;
    if (!form.hasAttribute("data-ajax-row") || !window.fetch) return;
    e.preventDefault();
    var status = form.querySelector(".row-status");
    var row = form.closest("tr");
    var buttons = form.querySelectorAll("button");
    buttons.forEach(function (b) { b.disabled = true; });
    setStatus(status, "Saving…", false);

    fetch(form.action, {
      method: "POST",
      body: formData(form, e.submitter),
      headers: { Accept: "application/json" },
      credentials: "same-origin",
    })
      .then(function (resp) {
        return resp.json().catch(function () {
          return { ok: false, error: "HTTP " + resp.status };
        });
      })
      .then(function (data) {
        if (!data.ok) {
          setStatus(status, data.error || "Save failed", true);
          return;
        }
        if (data.deleted) {
          if (row) row.remove();
          return;
        }
        if (row && data.game_count !== undefined) {
          var cell = row.querySelector("[data-game-count]");
          if (cell) cell.textContent = data.game_count;
        }
        Array.prototype.forEach.call(form.elements, function (el) {
          if (/^name_/.test(el.name)) {
            var empty = !el.value.trim();
            el.classList.toggle("missing", empty);
            el.placeholder = empty ? "missing: hidden" : "";
          }
        });
        setStatus(status, "Saved", false);
      })
      .catch(function () {
        setStatus(status, "Save failed: network error", true);
      })
      .then(function () {
        buttons.forEach(function (b) { b.disabled = false; });
      });
  });
})();

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
