// Every number on this page comes from data.json, a copy of results/results.json (bench.py).
// The waveform shapes are drawn for looks only; where speech starts and stops comes from the data.
(function () {
  "use strict";
  var AXIS_MAX = 6.5;                 // seconds shown on the timeline
  var USER_TALK = 2.4;                // how long the drawn user voice lasts (visual only)
  var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var data, speed = 8, raf = 0, clockT = AXIS_MAX, cur = null;
  var css = getComputedStyle(document.documentElement);
  function tok(n) { return css.getPropertyValue(n).trim(); }
  var COL = { bone: tok("--bone"), ember: tok("--ember"), tide: tok("--tide"), sand: tok("--sand") };

  function $(id) { return document.getElementById(id); }
  function ms(v) { return Math.round(v).toLocaleString("en-US") + " ms"; }
  function sec(v) { return v.toFixed(2) + " s"; }
  function row(mode, s) {
    return data.barge_in.filter(function (r) { return r.mode === mode && r.speed === s; })[0];
  }

  /* ---------- speech-like amplitude (deterministic, visual only) ---------- */
  function hash(i) { var x = Math.sin(i * 127.1 + 311.7) * 43758.5453; return x - Math.floor(x); }
  function amp(t, seed, gaps) {
    for (var g = 0; g < gaps.length; g++) if (t > gaps[g][0] && t < gaps[g][1]) return 0.035;
    var syl = Math.pow(Math.abs(Math.sin(t * Math.PI * 3.7 + seed)), 0.6);
    var slow = 0.72 + 0.28 * Math.sin(t * 1.9 + seed * 2);
    var k = Math.floor(t * 40 + seed * 50);
    return Math.min(1, 0.12 + 0.88 * syl * slow * (0.55 + 0.45 * hash(k)));
  }
  function edge(t, a, b) { // soft attack and release
    var up = Math.min(1, (t - a) / 0.08), down = Math.min(1, (b - t) / 0.1);
    return Math.max(0, Math.min(up, down));
  }

  /* ---------- canvas lanes ---------- */
  var waves = [].slice.call(document.querySelectorAll(".wave"));

  function sizeCanvas(c) {
    var dpr = Math.min(2, window.devicePixelRatio || 1), w = c.clientWidth, h = c.clientHeight;
    if (c.width !== Math.round(w * dpr) || c.height !== Math.round(h * dpr)) {
      c.width = Math.round(w * dpr); c.height = Math.round(h * dpr);
    }
    var g = c.getContext("2d"); g.setTransform(dpr, 0, 0, dpr, 0, 0);
    return { g: g, w: w, h: h };
  }

  function drawLane(c, t) {
    var kind = c.dataset.kind, s = sizeCanvas(c), g = s.g, w = s.w, h = s.h, mid = h / 2;
    var cut = cur.cut, pitch = w < 500 ? 4 : 5, bw = w < 500 ? 2 : 3, n = Math.floor(w / pitch);
    g.clearRect(0, 0, w, h);
    // baseline: the silent line
    g.fillStyle = "rgba(242,236,228,.13)";
    g.fillRect(0, mid - 0.5, w, 1);

    var from = 0, to = 0, seed = 0, gaps = [[2.15, 2.32], [4.3, 4.46]];
    if (kind === "user") { from = cut; to = cut + USER_TALK; seed = 1.3; gaps = [[2.05, 2.2]]; }
    else { from = 0.02; to = kind === "sdk" ? cur.sdkEnd : cur.fixEnd; seed = 0.2; }

    for (var i = 0; i < n; i++) {
      var x = i * pitch, ti = (x + bw / 2) / w * AXIS_MAX;
      if (ti > t) break;
      if (ti < from || ti > to) continue;
      var a = amp(ti, seed, gaps) * edge(ti, from, to);
      var bh = Math.max(2, a * (h - 6));
      var col = kind === "user" ? COL.sand : (ti < cut ? COL.bone : COL.ember);
      g.globalAlpha = kind === "user" ? 0.9 : (ti < cut ? 0.78 : 1);
      g.fillStyle = col;
      roundBar(g, x, mid - bh / 2, bw, bh);
    }
    g.globalAlpha = 1;

    // the wrapper's silence after the cut, drawn as a lit line
    if (kind === "fix" && t > cut) {
      var x0 = cut / AXIS_MAX * w, x1 = Math.min(t, AXIS_MAX) / AXIS_MAX * w;
      g.fillStyle = COL.tide; g.globalAlpha = 0.85;
      g.fillRect(x0, mid - 1, x1 - x0, 2);
      g.globalAlpha = 1;
    }
    // playhead
    if (t < AXIS_MAX && t > 0) {
      var px = t / AXIS_MAX * w;
      var grad = g.createLinearGradient(px - 24, 0, px, 0);
      grad.addColorStop(0, "rgba(242,236,228,0)"); grad.addColorStop(1, "rgba(242,236,228,.10)");
      g.fillStyle = grad; g.fillRect(px - 24, 0, 24, h);
      g.fillStyle = COL.bone; g.fillRect(px - 0.5, 0, 1, h);
    }
  }
  function roundBar(g, x, y, w, h) {
    var r = w / 2;
    g.beginPath();
    g.moveTo(x, y + r); g.arc(x + r, y + r, r, Math.PI, 0); g.lineTo(x + w, y + h - r);
    g.arc(x + r, y + h - r, r, 0, Math.PI); g.closePath(); g.fill();
  }

  function frame(t) {
    clockT = t;
    for (var i = 0; i < waves.length; i++) drawLane(waves[i], t);
    var over = Math.max(0, (t - cur.cut) * 1000);
    $("c-sdk").textContent = ms(Math.min(over, cur.sdk.silence_latency_ms));
    $("c-fix").textContent = ms(Math.min(over, cur.fix.silence_latency_ms));
    $("clock").textContent = Math.min(t, AXIS_MAX).toFixed(1) + " s elapsed";
  }

  /* ---------- layout helpers: cut line and axis follow the canvas ---------- */
  function place() {
    var c = waves[1], lanes = $("lanes");
    var left = c.offsetLeft, w = c.offsetWidth;
    $("cutline").style.left = (left + cur.cut / AXIS_MAX * w) + "px";
    var a = $("axis");
    a.style.marginLeft = left + "px"; a.style.marginRight = "0"; a.style.width = w + "px";
    var html = "", step = w < 420 ? 2 : 1;
    for (var s = 0; s <= 6; s += step) html += '<span style="left:' + (s / AXIS_MAX * 100) + '%">' + s + " s</span>";
    a.innerHTML = html;
    lanes.style.setProperty("--w", w + "px");
  }

  /* ---------- the one orchestrated moment: replay ---------- */
  function render() {
    cancelAnimationFrame(raf);
    var sdk = row("sdk_pattern", speed), fix = row("interruptible", speed);
    var cut = sdk.barge_in_after_s;
    cur = { sdk: sdk, fix: fix, cut: cut, sdkEnd: cut + sdk.silence_latency_ms / 1000, fixEnd: cut + fix.silence_latency_ms / 1000 };

    var note = "At " + speed + "x, the README pattern played " + sec(sdk.stale_audio_s) +
      " of stale audio and went quiet " + ms(sdk.silence_latency_ms) + " after cancel(). The wrapper played " +
      sec(fix.stale_audio_s) + " and went quiet in " + ms(fix.silence_latency_ms) + ".";
    if (sdk.server_done_before_cancel) {
      note += " Here the server had already sent task_done, so cancel() returned early and did nothing, and the whole rest of the turn played.";
    }
    $("note").textContent = note;
    var btns = document.querySelectorAll(".seg button");
    for (var i = 0; i < btns.length; i++) btns[i].setAttribute("aria-checked", String(+btns[i].dataset.speed === speed));

    place();
    var end = Math.min(AXIS_MAX, Math.max(cur.sdkEnd, cut + USER_TALK) + 0.2);
    if (reduce) { frame(AXIS_MAX); return; }
    var start = performance.now();
    (function tick(now) {
      var t = (now - start) / 1000;
      if (t < end) { frame(t); raf = requestAnimationFrame(tick); }
      else { raf = 0; frame(AXIS_MAX); }
    })(start);
  }

  /* ---------- before and after ---------- */
  function compare() {
    var max = Math.max.apply(null, data.barge_in.map(function (r) { return r.silence_latency_ms; }));
    var html = "";
    [2, 4, 8].forEach(function (s) {
      html += '<div class="cmp-row"><p class="cmp-speed">' + s + 'x<small>synthesis speed</small></p><div class="cmp-bars">';
      [["sdk_pattern", "README pattern", "var(--ember)"], ["interruptible", "Interruptible wrapper", "var(--tide)"]].forEach(function (m) {
        var r = row(m[0], s), wd = r.silence_latency_ms / max * 100;
        html += '<div class="cmp-line"><p class="cmp-who">' + m[1] + '</p>' +
          '<div class="cmp-track" role="img" aria-label="' + m[1] + ", " + ms(r.silence_latency_ms) + '"><i style="width:' + wd + "%;background:" + m[2] + '"></i></div>' +
          '<p class="cmp-num"><b>' + ms(r.silence_latency_ms) + "</b><small>" + sec(r.stale_audio_s) + " stale audio</small></p></div>";
      });
      html += "</div></div>";
    });
    $("compare").innerHTML = html;
    var a = row("sdk_pattern", 1), b = row("interruptible", 1);
    if (a && b) {
      $("onex").textContent = "Also run at 1x, where synthesis is exactly as fast as playback: nothing is buffered ahead, and both went quiet in " +
        ms(a.silence_latency_ms) + " and " + ms(b.silence_latency_ms) + ". Synthesis speed is the audio the mock server makes per second of wall time.";
    }
  }

  /* ---------- time to first audio ---------- */
  function ttfa() {
    var label = function (r) {
      if (r.scenario === "llm_stall_after_full_sentence") return ["Pause after a full first sentence", "idle_flush_ms not sent"];
      if (r.idle_flush_ms == null) return ["Pause mid sentence", "idle_flush_ms not sent (mock default 800 ms)"];
      return ["Pause mid sentence", "idle_flush_ms = " + r.idle_flush_ms];
    };
    var scale = 1100, html = "";
    data.ttfa.forEach(function (r, i) {
      var ok = r.within_budget, l = label(r);
      html += '<div class="tt-row"><p class="tt-label">' + l[0] + "<small>" + l[1] + "</small></p>" +
        '<div class="tt-track" role="img" aria-label="' + Math.round(r.ttfa_ms) + " ms against an " + Math.round(r.budget_ms) + ' ms budget"><i style="width:' +
        Math.min(100, r.ttfa_ms / scale * 100) + "%;background:" + (ok ? "var(--tide)" : "var(--ember)") + '"></i><b style="left:' +
        (r.budget_ms / scale * 100) + '%"></b>' + (i === 0 ? '<em style="left:' + (r.budget_ms / scale * 100) + '%">' + Math.round(r.budget_ms) + " ms budget</em>" : "") + "</div>" +
        '<p class="tt-num"><b>' + Math.round(r.ttfa_ms).toLocaleString("en-US") + "</b><small>ms</small>" +
        '<span class="' + (ok ? "tide" : "ember") + '">' + (ok ? "Within" : "Over") + " budget</span></p></div>";
    });
    $("ttfa").innerHTML = html;
  }

  fetch("data.json").then(function (r) { return r.json(); }).then(function (d) {
    data = d;
    var sdkMax = data.barge_in.filter(function (r) { return r.mode === "sdk_pattern"; })
      .reduce(function (a, r) { return r.silence_latency_ms > a.silence_latency_ms ? r : a; });
    var fixMax = Math.max.apply(null, data.barge_in.filter(function (r) { return r.mode === "interruptible"; })
      .map(function (r) { return r.silence_latency_ms; }));
    $("h-max").textContent = ms(sdkMax.silence_latency_ms) + " (at " + sdkMax.speed + "x)";
    $("h-fix").textContent = ms(fixMax);
    $("env").textContent = "Python " + data.env.python + ", flam-finesse " + data.env.flam_finesse +
      ", server: " + data.env.server + ". Every number on this page is read from " + data.source + ".";
    compare(); ttfa(); render();
    var btns = document.querySelectorAll(".seg button");
    for (var i = 0; i < btns.length; i++) btns[i].addEventListener("click", function () { speed = +this.dataset.speed; render(); });
    $("replay").addEventListener("click", render);
    var rt = 0;
    window.addEventListener("resize", function () {
      clearTimeout(rt);
      rt = setTimeout(function () { place(); if (!raf) frame(AXIS_MAX); }, 80);
    });
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(function () { place(); });
  });
})();
