// Every number on this page comes from data.json, a copy of results/results.json (bench.py).
(function () {
  "use strict";
  var AXIS_MAX = 6.5;            // seconds shown on the timeline
  var STEP = 0.1;                // one bar per 100 ms of wall time
  var NBARS = Math.round(AXIS_MAX / STEP);
  var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var data, speed = 4, raf = 0;

  function $(id) { return document.getElementById(id); }
  function ms(v) { return Math.round(v).toLocaleString("en-US") + " ms"; }
  function sec(v) { return v.toFixed(2) + " s"; }
  function row(mode, s) {
    return data.barge_in.filter(function (r) { return r.mode === mode && r.speed === s; })[0];
  }

  // deterministic waveform heights (visual only)
  var heights = [];
  for (var i = 0; i < NBARS; i++) {
    var h = 0.35 + 0.65 * Math.abs(Math.sin(i * 1.7) * 0.6 + Math.sin(i * 0.53) * 0.4);
    heights.push(Math.min(1, Math.max(0.28, h)));
  }

  function buildTrack(el, kind, cutAt, endAt) {
    el.innerHTML = "";
    var bars = document.createElement("div");
    bars.className = "bars";
    for (var i = 0; i < NBARS; i++) {
      var t0 = i * STEP, b = document.createElement("i");
      b.className = "bar";
      var speaking = kind !== "user" && t0 < endAt - 1e-9;
      if (!speaking) {
        b.classList.add("off");
        b.style.height = "2px";
        b.style.background = kind === "user" ? "transparent" : "var(--line)";
      } else {
        b.style.height = Math.round(heights[i] * 100) + "%";
        b.dataset.t = t0.toFixed(2);
        b.dataset.c = t0 < cutAt - 1e-9 ? "on-brand" : "on-red";
      }
      bars.appendChild(b);
    }
    el.appendChild(bars);
    var cut = document.createElement("div");
    cut.className = "cut";
    cut.style.left = (cutAt / AXIS_MAX * 100) + "%";
    el.appendChild(cut);
    if (kind === "user") {
      var lab = document.createElement("span");
      lab.className = "cut-label";
      lab.style.left = (cutAt / AXIS_MAX * 100) + "%";
      lab.textContent = "User starts talking, cancel() called";
      el.appendChild(lab);
    }
    var head = document.createElement("div");
    head.className = "head";
    el.appendChild(head);
  }

  function paint(t) {
    var all = document.querySelectorAll(".bar[data-t]");
    for (var i = 0; i < all.length; i++) {
      var b = all[i], on = parseFloat(b.dataset.t) < t;
      b.classList.toggle(b.dataset.c, on);
    }
    var heads = document.querySelectorAll(".head");
    for (var j = 0; j < heads.length; j++) heads[j].style.left = Math.min(100, t / AXIS_MAX * 100) + "%";
  }

  function setCounters(t, sdk, fix) {
    var cut = sdk.barge_in_after_s;
    var over = Math.max(0, (t - cut) * 1000);
    $("c-sdk").textContent = ms(Math.min(over, sdk.silence_latency_ms));
    $("c-fix").textContent = ms(Math.min(over, fix.silence_latency_ms));
  }

  function render() {
    cancelAnimationFrame(raf);
    var sdk = row("sdk_pattern", speed), fix = row("interruptible", speed);
    var cut = sdk.barge_in_after_s;
    buildTrack($("track-user"), "user", cut, 0);
    buildTrack($("track-sdk"), "sdk", cut, cut + sdk.silence_latency_ms / 1000);
    buildTrack($("track-fix"), "fix", cut, cut + fix.silence_latency_ms / 1000);

    var note = "At " + speed + "x, the README pattern played " + sec(sdk.stale_audio_s) +
      " of stale audio and went quiet " + ms(sdk.silence_latency_ms) + " after cancel(). The wrapper played " +
      sec(fix.stale_audio_s) + " and went quiet in " + ms(fix.silence_latency_ms) + ".";
    if (sdk.server_done_before_cancel) {
      note += " Here the server had already sent task_done, so cancel() returned early and did nothing, and the whole rest of the turn played.";
    }
    $("note").textContent = note;

    var btns = document.querySelectorAll(".seg button");
    for (var i = 0; i < btns.length; i++) btns[i].setAttribute("aria-checked", String(+btns[i].dataset.speed === speed));

    var end = cut + sdk.silence_latency_ms / 1000 + 0.15;
    if (reduce) { paint(AXIS_MAX); setCounters(AXIS_MAX, sdk, fix); return; }
    var tl = $("timeline"), start = performance.now();
    tl.classList.add("playing");
    (function tick(now) {
      var t = (now - start) / 1000;
      paint(t); setCounters(t, sdk, fix);
      if (t < end) raf = requestAnimationFrame(tick);
      else { paint(AXIS_MAX); tl.classList.remove("playing"); }
    })(start);
  }

  function axis() {
    var a = $("axis"), html = "";
    for (var s = 0; s <= 6; s++) html += '<span style="left:' + (s / AXIS_MAX * 100) + '%">' + s + " s</span>";
    a.innerHTML = html;
  }

  function compare() {
    var speeds = [2, 4, 8];
    var max = Math.max.apply(null, data.barge_in.map(function (r) { return r.silence_latency_ms; }));
    ["sdk_pattern", "interruptible"].forEach(function (mode) {
      var html = "";
      speeds.forEach(function (s) {
        var r = row(mode, s), w = r.silence_latency_ms / max * 100;
        var color = mode === "sdk_pattern" ? "var(--red)" : "var(--brand)";
        html += '<div class="row"><span class="spd">' + s + 'x</span>' +
          '<div class="meter" role="img" aria-label="' + ms(r.silence_latency_ms) + ' silence latency"><i style="width:' +
          Math.max(w, mode === "interruptible" ? 1.5 : 0) + "%;background:" + color + '"></i></div>' +
          '<div class="val"><b>' + ms(r.silence_latency_ms) + "</b><small>" + sec(r.stale_audio_s) + " stale audio</small></div></div>";
      });
      $(mode === "sdk_pattern" ? "rows-sdk" : "rows-fix").innerHTML = html;
    });
    var a = row("sdk_pattern", 1), b = row("interruptible", 1);
    if (a && b) {
      $("onex").textContent = "Also run at 1x (synthesis exactly as fast as playback): nothing is buffered ahead, and both went quiet in " +
        ms(a.silence_latency_ms) + " and " + ms(b.silence_latency_ms) + ". Synthesis speed is the server's audio generated per wall second in the mock.";
    }
  }

  function ttfa() {
    var label = function (r) {
      if (r.scenario === "llm_stall_after_full_sentence") return "Pause comes after a full first sentence, idle_flush_ms not sent";
      if (r.idle_flush_ms == null) return "Pause mid sentence, idle_flush_ms not sent (mock default 800 ms)";
      return "Pause mid sentence, idle_flush_ms = " + r.idle_flush_ms;
    };
    var scale = 1100, html = "";
    data.ttfa.forEach(function (r) {
      var ok = r.within_budget;
      html += '<div class="card"><div class="k1">' + label(r) + '</div>' +
        '<div class="big">' + Math.round(r.ttfa_ms).toLocaleString("en-US") + '<small>ms</small></div>' +
        '<div class="budget" role="img" aria-label="time to first audio against an ' + r.budget_ms + ' ms budget"><i style="width:' +
        Math.min(100, r.ttfa_ms / scale * 100) + "%;background:" + (ok ? "var(--brand)" : "var(--red)") + '"></i><b style="left:' +
        (r.budget_ms / scale * 100) + '%"></b></div>' +
        '<span class="pill ' + (ok ? "ok" : "bad") + '">' + (ok ? "Within" : "Over") + " the " + Math.round(r.budget_ms) + " ms budget</span></div>";
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
    axis(); compare(); ttfa(); render();
    var btns = document.querySelectorAll(".seg button");
    for (var i = 0; i < btns.length; i++) btns[i].addEventListener("click", function () { speed = +this.dataset.speed; render(); });
    $("replay").addEventListener("click", render);
  });
})();
