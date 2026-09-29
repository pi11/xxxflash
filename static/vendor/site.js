/* Shared site behaviour: CSRF-protected voting (POST /mark/). */
(function ($) {
  "use strict";

  function csrfToken() {
    var m = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    return m ? decodeURIComponent(m[1]) : "";
  }

  $.ajaxSetup({
    beforeSend: function (xhr, settings) {
      if (!/^(GET|HEAD|OPTIONS)$/i.test(settings.type)) {
        xhr.setRequestHeader("X-CSRFToken", csrfToken());
      }
    },
  });

  // vote('up'|'down', gameId[, targetSelector]) - legacy signature kept for the templates.
  window.vote = function (kind, id, target) {
    $.post("/mark/", { pk: id, vote: kind }, function (json) {
      $(target || "#mark-" + id).text(json.success);
    }, "json");
    return false;
  };
})(jQuery);
