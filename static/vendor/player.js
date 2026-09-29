/* Mount the Ruffle player into every .game-player element (see docs/ruffle.md). */
(function () {
  "use strict";

  function showFallback(el) {
    var fb = el.querySelector(".player-fallback");
    if (fb) fb.hidden = false;
  }

  function size(el) {
    var w = parseInt(el.dataset.width, 10) || 0;
    var h = parseInt(el.dataset.height, 10) || 0;
    var maxW = parseInt(el.dataset.maxWidth, 10) || 700;
    var avail = el.parentElement ? el.parentElement.clientWidth : maxW;
    var width = Math.min(maxW, avail || maxW);
    var height = w > 0 && h > 0 ? Math.round((width * h) / w) : width; // legacy default: square
    var maxH = Math.round(window.innerHeight * 0.9);
    if (height > maxH) {
      width = Math.round((width * maxH) / height);
      height = maxH;
    }
    return { width: width, height: height };
  }

  function mount(el) {
    var ruffle = window.RufflePlayer && window.RufflePlayer.newest && window.RufflePlayer.newest();
    if (!ruffle) {
      showFallback(el);
      return;
    }
    var player = ruffle.createPlayer();
    var s = size(el);
    player.style.width = s.width + "px";
    player.style.height = s.height + "px";
    player.style.display = "block";
    player.style.margin = "0 auto";
    el.insertBefore(player, el.firstChild);
    var loaded = player.ruffle ? player.ruffle().load({ url: el.dataset.swf }) : player.load({ url: el.dataset.swf });
    if (loaded && loaded.catch) {
      loaded.catch(function (err) {
        if (window.console) console.error("Ruffle load failed", err);
        showFallback(el);
      });
    }
  }

  function init() {
    var nodes = document.querySelectorAll(".game-player[data-swf]");
    for (var i = 0; i < nodes.length; i++) mount(nodes[i]);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
