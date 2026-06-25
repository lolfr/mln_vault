// Archive — minimal client-side glue.
(() => {
  const post = (url, body = {}) =>
    fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).then((r) => r.json().then((j) => ({ ok: r.ok, ...j })).catch(() => ({ ok: r.ok })));

  // Reveal master in Finder
  document.querySelectorAll("[data-open-master]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const id = btn.dataset.openMaster;
      const res = await post(`/open-master/${id}`);
      btn.textContent = res.ok ? "Ouvert dans le Finder ✓" : "Master introuvable";
      if (!res.ok) btn.disabled = true;
    });
  });
})();

window.__initTags = function () {
  var el = document.getElementById('tag-cloud');
  if (!el || !window.WordCloud) return;
  var words = JSON.parse(el.dataset.words || '[]');
  var max = words.length ? words[0].n : 1;
  var list = words.map(function (w) { return [w.label, 12 + Math.round(60 * Math.sqrt(w.n / max))]; });
  WordCloud(el, { list: list, gridSize: 8, rotateRatio: 0, backgroundColor: 'transparent',
    click: function (item) {
      var w = words.find(function (x) { return x.label === item[0]; });
      if (w) location.href = '/tags/' + w.slug;
    } });
  var norm = function (s) { return s.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase(); };
  var search = document.getElementById('tag-search');
  search.addEventListener('input', function () {
    var q = norm(search.value.trim());
    document.querySelectorAll('.tag-category').forEach(function (det) {
      var any = false;
      det.querySelectorAll('.tag-item').forEach(function (li) {
        var hit = !q || norm(li.dataset.label).indexOf(q) !== -1;
        li.style.display = hit ? '' : 'none';
        if (hit) any = true;
      });
      det.style.display = any ? '' : 'none';
      det.open = !!q && any;
    });
    el.style.display = q ? 'none' : '';
  });
};

// init au chargement (app.js est defer : DOM parsé + wordcloud2.js déjà chargé)
window.__initTags && window.__initTags();
