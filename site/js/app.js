/**
 * EPL SRS Ratings - Frontend Application
 */

(function () {
  "use strict";

  var HOME_COURT_ADV = 0.4;  // EPL home advantage in goals
  var GAME_STD_DEV = 1.2;    // EPL goal std dev

  var teamsData = [];
  var predictionsData = [];
  var simulationData = {};
  var lastSimResults = null;
  var currentFilter = "all";
  var currentSort = { key: "srs_rank", dir: "asc" };
  var chartsRendered = { rankings: false };

  // ── Bootstrap ──────────────────────────────────────────────

  document.addEventListener("DOMContentLoaded", function () {
    init();
  });

  async function init() {
    try {
      var resp = await fetch("data/srs_data.json");
      if (!resp.ok) throw new Error("HTTP " + resp.status);
      var data = await resp.json();

      teamsData = data.teams || [];
      predictionsData = data.predictions || [];
      simulationData = data.simulation || {};

      // Header metadata
      document.getElementById("season-label").textContent =
        data.metadata.season + " Season";
      var updated = new Date(data.metadata.last_updated);
      document.getElementById("last-updated").textContent =
        "Updated " + formatDate(updated) +
        " \u00B7 " + data.metadata.total_games + " games";

      // Model stats
      var stats = data.metadata.model_stats;
      if (stats) {
        HOME_COURT_ADV = stats.home_advantage || 0.4;
        document.getElementById("stat-rmse").textContent = stats.rmse.toFixed(2);
        // support both avg_ppg (old) and avg_gpg (new)
        var gpg = stats.avg_gpg || stats.avg_ppg || 0;
        document.getElementById("stat-ppg").textContent = gpg.toFixed(2);
        document.getElementById("stat-hca").textContent =
          (stats.home_advantage > 0 ? "+" : "") + stats.home_advantage.toFixed(2) + " goals";
        document.getElementById("model-stats").style.display = "flex";

        var stdSlider = document.getElementById("slider-std-error");
        var stdLabel = document.getElementById("std-error-value");
        if (stdSlider && stdLabel) {
          stdSlider.value = Math.min(3, Math.max(0.5, stats.rmse));
          stdLabel.textContent = parseFloat(stdSlider.value).toFixed(1);
        }
      }

      document.getElementById("loading").style.display = "none";

      setupTabs();
      setupSimControls();
      showTab("rankings");
    } catch (err) {
      console.error("Failed to load SRS data:", err);
      document.getElementById("loading").style.display = "none";
      document.getElementById("error").style.display = "block";
    }
  }

  // ── Tabs ───────────────────────────────────────────────────

  function setupTabs() {
    document.querySelectorAll(".tab-btn").forEach(function (btn) {
      btn.addEventListener("click", function () {
        showTab(btn.dataset.tab);
      });
    });
  }

  function showTab(tabId) {
    document.querySelectorAll(".tab-btn").forEach(function (b) {
      b.classList.toggle("active", b.dataset.tab === tabId);
    });
    document.querySelectorAll(".tab-content").forEach(function (el) {
      el.style.display = "none";
    });
    var tabEl = document.getElementById("tab-" + tabId);
    if (tabEl) tabEl.style.display = "block";

    if (tabId === "rankings" && !chartsRendered.rankings) {
      renderBarChart(teamsData);
      renderTable(teamsData);
      renderScatterChart(teamsData);
      setupFilterButtons();
      setupSorting();
      chartsRendered.rankings = true;
    } else if (tabId === "predictions") {
      renderPredictions(predictionsData);
    } else if (tabId === "simulation") {
      initSimTab();
    }
  }

  // ── Bar Chart ──────────────────────────────────────────────

  function renderBarChart(teams) {
    var sorted = teams.slice().sort(function (a, b) { return a.srs - b.srs; });
    var labels = sorted.map(function (t) { return t.abbreviation; });
    var values = sorted.map(function (t) { return t.srs; });
    var colors = sorted.map(function (t) {
      if (t.srs > 0) return "rgba(5, 150, 105, 0.8)";
      if (t.srs < 0) return "rgba(220, 38, 38, 0.7)";
      return "rgba(107, 114, 128, 0.6)";
    });
    var borderColors = sorted.map(function (t) {
      if (t.srs > 0) return "rgb(5, 150, 105)";
      if (t.srs < 0) return "rgb(220, 38, 38)";
      return "rgb(107, 114, 128)";
    });

    var ctx = document.getElementById("srs-chart").getContext("2d");
    new Chart(ctx, {
      type: "bar",
      data: {
        labels: labels,
        datasets: [{
          label: "SRS Rating",
          data: values,
          backgroundColor: colors,
          borderColor: borderColors,
          borderWidth: 1,
        }],
      },
      options: {
        indexAxis: "y",
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: function (ctx) {
                var team = sorted[ctx.dataIndex];
                return [
                  "SRS: " + formatSRS(team.srs),
                  "MOV: " + formatSRS(team.mov),
                  "SOS: " + formatSRS(team.sos),
                  "Record: " + team.wins + "W-" + (team.draws||0) + "D-" + team.losses + "L",
                ];
              },
            },
          },
        },
        scales: {
          x: { title: { display: true, text: "SRS Rating (goals)" }, grid: { color: "rgba(128,128,128,0.15)" } },
          y: { grid: { display: false }, ticks: { font: { size: 11, weight: "bold" } } },
        },
      },
    });

    document.getElementById("srs-chart").parentElement.style.height =
      Math.max(400, sorted.length * 22) + "px";
  }

  // ── Rankings Table ─────────────────────────────────────────

  function renderTable(teams) {
    var filtered = currentFilter === "all"
      ? teams
      : teams.filter(function (t) { return t.division === currentFilter; });

    var sorted = sortTeams(filtered, currentSort.key, currentSort.dir);
    var tbody = document.getElementById("rankings-body");
    tbody.innerHTML = "";

    sorted.forEach(function (team) {
      var row = document.createElement("tr");
      var diff = team.standings_rank - team.srs_rank;
      var diffText, diffClass;
      if (diff > 0) { diffText = "+" + diff; diffClass = "diff-better"; }
      else if (diff < 0) { diffText = String(diff); diffClass = "diff-worse"; }
      else { diffText = "0"; diffClass = "diff-same"; }

      var srsClass = team.srs > 0 ? "srs-positive" : team.srs < 0 ? "srs-negative" : "srs-neutral";
      var movClass = team.mov > 0 ? "srs-positive" : team.mov < 0 ? "srs-negative" : "srs-neutral";
      var sosClass = team.sos > 0 ? "srs-positive" : team.sos < 0 ? "srs-negative" : "srs-neutral";
      var draws = team.draws || 0;
      var record = team.wins + "W-" + draws + "D-" + team.losses + "L";

      var hca = team.home_advantage !== undefined ? team.home_advantage : null;
      var hcaText = hca !== null ? (hca > 0 ? "+" : "") + hca.toFixed(2) : "—";
      var hcaClass = hca !== null ? (hca > 0.5 ? "srs-positive" : hca < 0 ? "srs-negative" : "srs-neutral") : "";
      var hcaTitle = hca !== null
        ? 'title="Home Adv: ' + hcaText + ' goals (' + (team.home_games || "?") + ' home games)"'
        : '';

      row.innerHTML =
        '<td class="num">' + team.srs_rank + '</td>' +
        '<td><div class="team-cell">' +
          '<span class="team-name">' + team.name + '</span>' +
          '<span class="team-abbr">' + team.abbreviation + '</span>' +
        '</div></td>' +
        '<td class="num ' + srsClass + '">' + formatSRS(team.srs) + '</td>' +
        '<td class="num ' + movClass + '">' + formatSRS(team.mov) + '</td>' +
        '<td class="num ' + sosClass + '">' + formatSRS(team.sos) + '</td>' +
        '<td class="num ' + hcaClass + '" ' + hcaTitle + '>' + hcaText + '</td>' +
        '<td class="num">' + record + '</td>' +
        '<td class="num">' + (team.win_pct * 100).toFixed(1) + '%</td>' +
        '<td class="num">' + team.standings_rank + '</td>' +
        '<td class="num ' + diffClass + '">' + diffText + '</td>';

      tbody.appendChild(row);
    });
  }

  function sortTeams(teams, key, dir) {
    return teams.slice().sort(function (a, b) {
      var va, vb;
      if (key === "name") { va = a.name; vb = b.name; }
      else if (key === "record") { va = a.win_pct; vb = b.win_pct; }
      else { va = a[key]; vb = b[key]; }
      if (typeof va === "string") {
        return dir === "asc" ? va.localeCompare(vb) : vb.localeCompare(va);
      }
      return dir === "asc" ? va - vb : vb - va;
    });
  }

  function setupSorting() {
    document.querySelectorAll("#rankings-table th.sortable").forEach(function (th) {
      th.addEventListener("click", function () {
        var key = th.dataset.sort;
        if (currentSort.key === key) {
          currentSort.dir = currentSort.dir === "asc" ? "desc" : "asc";
        } else {
          currentSort.key = key;
          currentSort.dir = (key === "name" || key === "srs_rank" || key === "standings_rank") ? "asc" : "desc";
        }
        document.querySelectorAll("#rankings-table th.sortable").forEach(function (h) {
          h.classList.remove("sort-active", "sort-asc", "sort-desc");
        });
        th.classList.add("sort-active", "sort-" + currentSort.dir);
        renderTable(teamsData);
      });
    });
  }

  function setupFilterButtons() {
    document.querySelectorAll(".filter-btn").forEach(function (btn) {
      btn.addEventListener("click", function () {
        currentFilter = btn.dataset.filter;
        document.querySelectorAll(".filter-btn").forEach(function (b) { b.classList.remove("active"); });
        btn.classList.add("active");
        renderTable(teamsData);
      });
    });
  }

  // ── Scatter Chart ──────────────────────────────────────────

  function renderScatterChart(teams) {
    var maxRank = teams.length;
    var diagPoints = [];
    for (var i = 1; i <= maxRank; i++) diagPoints.push({ x: i, y: i });

    var ctx = document.getElementById("comparison-chart").getContext("2d");
    new Chart(ctx, {
      type: "scatter",
      data: {
        datasets: [
          {
            label: "Perfect Agreement", data: diagPoints, showLine: true,
            pointRadius: 0, borderColor: "rgba(128,128,128,0.3)",
            borderDash: [5, 5], borderWidth: 1.5,
          },
          {
            label: "EPL Teams",
            data: teams.map(function (t) { return { x: t.standings_rank, y: t.srs_rank, team: t }; }),
            backgroundColor: "rgba(59, 130, 246, 0.7)", borderColor: "rgb(59, 130, 246)",
            borderWidth: 1.5, pointRadius: 6, pointHoverRadius: 9,
          },
        ],
      },
      options: {
        responsive: true, maintainAspectRatio: true, aspectRatio: 1,
        plugins: {
          tooltip: {
            filter: function (item) { return item.datasetIndex > 0; },
            callbacks: {
              label: function (ctx) {
                var t = ctx.raw.team;
                var draws = t.draws || 0;
                return [
                  t.name + " (" + t.abbreviation + ")",
                  "SRS Rank: #" + t.srs_rank + " (SRS: " + formatSRS(t.srs) + ")",
                  "Standings: #" + t.standings_rank + " (" + t.wins + "W-" + draws + "D-" + t.losses + "L)",
                ];
              },
            },
          },
        },
        scales: {
          x: { title: { display: true, text: "Standings Rank (by Points)" }, min: 0.5, max: maxRank + 0.5, ticks: { stepSize: 5 }, grid: { color: "rgba(128,128,128,0.1)" } },
          y: { title: { display: true, text: "SRS Rank" }, min: 0.5, max: maxRank + 0.5, reverse: true, ticks: { stepSize: 5 }, grid: { color: "rgba(128,128,128,0.1)" } },
        },
      },
    });
  }

  // ── Predictions ────────────────────────────────────────────

  function renderPredictions(predictions) {
    var container = document.getElementById("predictions-list");
    var emptyEl = document.getElementById("predictions-empty");

    if (!predictions || predictions.length === 0) {
      container.innerHTML = "";
      emptyEl.style.display = "block";
      return;
    }
    emptyEl.style.display = "none";

    var byDate = {};
    predictions.forEach(function (p) {
      var key = p.date_parsed || p.date;
      if (!byDate[key]) byDate[key] = [];
      byDate[key].push(p);
    });

    var html = "";
    var dates = Object.keys(byDate).sort();

    dates.forEach(function (dateKey) {
      var games = byDate[dateKey];
      var displayDate = formatGameDate(dateKey);

      html += '<div class="prediction-day">';
      html += '<div class="prediction-day-header">' + displayDate + '</div>';

      games.forEach(function (g, idx) {
        var cardId = "pred-card-" + dateKey.replace(/-/g,"") + "-" + idx;
        var adj = g.adjustments || {};
        var spreadAbs = Math.abs(g.predicted_margin).toFixed(2);
        var homeWinPct = (g.home_win_prob * 100).toFixed(0);
        var awayWinPct = (100 - g.home_win_prob * 100).toFixed(0);
        var spreadClass = g.predicted_margin >= 0 ? "home-fav" : "away-fav";
        var spreadText = g.predicted_margin >= 0
          ? g.home_team + " -" + spreadAbs
          : g.away_team + " -" + spreadAbs;

        // Format adjustment values with sign + color class
        function adjVal(v) {
          if (v === undefined) return "—";
          var s = (v > 0 ? "+" : "") + v.toFixed(3);
          var cls = v > 0.01 ? "adj-pos" : v < -0.01 ? "adj-neg" : "adj-neutral";
          return '<span class="' + cls + '">' + s + '</span>';
        }

        // Injury badge: show top 2 injured players per team
        function injuryBadges(injuries) {
          if (!injuries || injuries.length === 0) return '<span class="inj-none">None</span>';
          return injuries.slice(0, 3).map(function(p) {
            var statusLabel = p.status === "i" ? "❌" : p.status === "s" ? "🟥" : "⚠️";
            return '<span class="inj-badge" title="Importance: ' + p.importance + ' | Miss prob: ' + (p.miss_prob*100).toFixed(0) + '%">' +
              statusLabel + ' ' + p.name + '</span>';
          }).join(" ");
        }

        // Rest display
        var homeRest = adj.home_rest_days !== undefined ? adj.home_rest_days + "d" : "—";
        var awayRest = adj.away_rest_days !== undefined ? adj.away_rest_days + "d" : "—";
        var homeRestScore = adj.home_rest_score !== undefined ? adj.home_rest_score.toFixed(2) : "—";
        var awayRestScore = adj.away_rest_score !== undefined ? adj.away_rest_score.toFixed(2) : "—";

        // Form display
        var homeForm = adj.home_form !== undefined ? (adj.home_form > 0 ? "+" : "") + adj.home_form.toFixed(2) : "—";
        var awayForm = adj.away_form !== undefined ? (adj.away_form > 0 ? "+" : "") + adj.away_form.toFixed(2) : "—";

        html += '<div class="prediction-card" id="' + cardId + '">';

        // ── Main prediction row ──
        html += '<div class="pred-main">';
        html += '  <div class="pred-teams">';
        html += '    <div class="pred-team-row">';
        html += '      <span class="pred-team-name">' + g.away_team + '</span>';
        html += '      <span class="pred-srs">SRS ' + formatSRS(g.away_srs) + '</span>';
        html += '    </div>';
        html += '    <div class="pred-at">at</div>';
        html += '    <div class="pred-team-row">';
        html += '      <span class="pred-team-name">' + g.home_team + '</span>';
        html += '      <span class="pred-srs">SRS ' + formatSRS(g.home_srs) + '</span>';
        html += '    </div>';
        html += '  </div>';
        html += '  <div class="pred-result">';
        html += '    <div class="pred-spread ' + spreadClass + '">' + spreadText + '</div>';
        html += '    <div class="pred-prob">' + g.home_team + ' ' + homeWinPct + '% / ' + g.away_team + ' ' + awayWinPct + '%</div>';
        html += '    <div class="pred-prob-bar"><div class="pred-prob-fill" style="width:' + homeWinPct + '%"></div></div>';
        html += '  </div>';
        html += '  <button class="pred-details-btn" onclick="togglePredDetails(\'' + cardId + '\')" title="Show model breakdown">▼ Details</button>';
        html += '</div>';

        // ── Adjustments panel (hidden by default) ──
        html += '<div class="pred-details" id="' + cardId + '-details" style="display:none">';

        // Margin breakdown table
        html += '<div class="adj-section">';
        html += '<div class="adj-title">Margin Breakdown (goals)</div>';
        html += '<table class="adj-table">';
        html += '<tr><td>SRS difference</td><td>' + adjVal(adj.srs_base) + '</td></tr>';
        html += '<tr><td>Home advantage</td><td>' + adjVal(adj.home_advantage) + '</td></tr>';
        html += '<tr><td>Form</td><td>' + adjVal(adj.form) + '</td></tr>';
        html += '<tr><td>Rest</td><td>' + adjVal(adj.rest) + '</td></tr>';
        html += '<tr><td>Injury</td><td>' + adjVal(adj.injury) + '</td></tr>';
        html += '<tr class="adj-total"><td><strong>Total margin</strong></td><td><strong>' + (g.predicted_margin > 0 ? "+" : "") + g.predicted_margin.toFixed(2) + '</strong></td></tr>';
        html += '</table>';
        html += '</div>';

        // Form & Rest side by side
        html += '<div class="adj-grid">';

        html += '<div class="adj-section">';
        html += '<div class="adj-title">Form (last 5, SRS-weighted)</div>';
        html += '<div class="adj-row"><span class="adj-label">' + g.home_team + '</span><span class="adj-val">' + homeForm + '</span></div>';
        html += '<div class="adj-row"><span class="adj-label">' + g.away_team + '</span><span class="adj-val">' + awayForm + '</span></div>';
        html += '</div>';

        html += '<div class="adj-section">';
        html += '<div class="adj-title">Rest Days</div>';
        html += '<div class="adj-row"><span class="adj-label">' + g.home_team + '</span><span class="adj-val">' + homeRest + ' <small>(score: ' + homeRestScore + ')</small></span></div>';
        html += '<div class="adj-row"><span class="adj-label">' + g.away_team + '</span><span class="adj-val">' + awayRest + ' <small>(score: ' + awayRestScore + ')</small></span></div>';
        html += '</div>';

        html += '</div>'; // adj-grid

        // Injuries
        html += '<div class="adj-section">';
        html += '<div class="adj-title">Injury Report</div>';
        html += '<div class="adj-row"><span class="adj-label">' + g.home_team + '</span><span class="adj-val">' + injuryBadges(adj.home_injuries) + '</span></div>';
        html += '<div class="adj-row"><span class="adj-label">' + g.away_team + '</span><span class="adj-val">' + injuryBadges(adj.away_injuries) + '</span></div>';
        html += '</div>';

        html += '</div>'; // pred-details
        html += '</div>'; // prediction-card
      });

      html += '</div>'; // prediction-day
    });

    container.innerHTML = html;
  }

  // Toggle details panel
  window.togglePredDetails = function(cardId) {
    var details = document.getElementById(cardId + "-details");
    var btn = document.querySelector("#" + cardId + " .pred-details-btn");
    if (!details) return;
    var isOpen = details.style.display !== "none";
    details.style.display = isOpen ? "none" : "block";
    if (btn) btn.textContent = isOpen ? "▼ Details" : "▲ Details";
  };

  // ── Simulation ─────────────────────────────────────────────

  function setupSimControls() {
    var stdSlider = document.getElementById("slider-std-error");
    var simSlider = document.getElementById("slider-num-sims");
    var stdLabel = document.getElementById("std-error-value");
    var simLabel = document.getElementById("num-sims-value");
    var runBtn = document.getElementById("run-sim-btn");

    if (!stdSlider || !simSlider || !runBtn) return;

    stdSlider.addEventListener("input", function () {
      stdLabel.textContent = parseFloat(stdSlider.value).toFixed(1);
    });
    simSlider.addEventListener("input", function () {
      simLabel.textContent = parseInt(simSlider.value).toLocaleString();
    });
    runBtn.addEventListener("click", function () {
      runMonteCarloSim();
    });
  }

  function initSimTab() {
    var sim = simulationData;
    var emptyEl = document.getElementById("simulation-empty");
    var tableSection = document.getElementById("sim-table-section");

    if (!sim || !sim.remaining_games || sim.remaining_games.length === 0) {
      emptyEl.style.display = "block";
      tableSection.style.display = "none";
      return;
    }
    emptyEl.style.display = "none";
    if (!lastSimResults) runMonteCarloSim();
  }

  function normalCDF(x) {
    return 0.5 * (1 + erf(x / Math.SQRT2));
  }

  function erf(x) {
    var sign = x >= 0 ? 1 : -1;
    x = Math.abs(x);
    var t = 1.0 / (1.0 + 0.3275911 * x);
    var y = 1.0 - (((((1.061405429 * t - 1.453152027) * t) + 1.421413741) * t - 0.284496736) * t + 0.254829592) * t * Math.exp(-x * x);
    return sign * y;
  }

  function winProbability(margin, stdDev) {
    return normalCDF(margin / stdDev);
  }

  function runMonteCarloSim() {
    var sim = simulationData;
    if (!sim || !sim.remaining_games || sim.remaining_games.length === 0) return;

    var stdError = parseFloat(document.getElementById("slider-std-error").value);
    var numSims = parseInt(document.getElementById("slider-num-sims").value);
    var statusEl = document.getElementById("sim-status");
    var runBtn = document.getElementById("run-sim-btn");
    var tableSection = document.getElementById("sim-table-section");

    runBtn.disabled = true;
    runBtn.textContent = "Running...";
    statusEl.textContent = "Simulating " + numSims.toLocaleString() + " seasons...";

    setTimeout(function () {
      var t0 = performance.now();
      var results = computeMonteCarlo(sim, stdError, numSims);
      var elapsed = ((performance.now() - t0) / 1000).toFixed(2);

      lastSimResults = results;
      statusEl.textContent = "Completed " + numSims.toLocaleString() +
        " simulations of " + sim.remaining_games.length + " remaining matches in " + elapsed + "s";
      tableSection.style.display = "block";
      renderSimTable(results);

      runBtn.disabled = false;
      runBtn.textContent = "Run Simulation";
    }, 20);
  }

  function computeMonteCarlo(sim, stdError, numSims) {
    var standings = sim.current_standings;
    var games = sim.remaining_games;

    var teams = Object.keys(standings);
    var teamIdx = {};
    teams.forEach(function (t, i) { teamIdx[t] = i; });
    var n = teams.length;

    var srsMap = {};
    teamsData.forEach(function (t) { srsMap[t.abbreviation] = t.srs; });

    // Pre-compute win/draw/loss probabilities for EPL (draws ~25%)
    var DRAW_PROB = 0.25;
    var gameProbs = [];
    games.forEach(function (g) {
      var hi = teamIdx[g.home_team];
      var ai = teamIdx[g.away_team];
      if (hi === undefined || ai === undefined) return;
      var margin = (srsMap[g.home_team] || 0) - (srsMap[g.away_team] || 0) + HOME_COURT_ADV;
      var probHome = winProbability(margin, stdError) * (1 - DRAW_PROB);
      var probDraw = DRAW_PROB;
      gameProbs.push([hi, ai, probHome, probDraw]);
    });

    var basePoints = new Float64Array(n);
    teams.forEach(function (t, i) {
      var s = standings[t];
      basePoints[i] = (s.points !== undefined) ? s.points : (s.wins * 3 + (s.draws || 0));
    });

    var totalPoints = new Float64Array(n);
    var totalPointsSq = new Float64Array(n);
    var titleCount = new Float64Array(n);
    var top4Count = new Float64Array(n);
    var top6Count = new Float64Array(n);
    var relegCount = new Float64Array(n);

    var nGames = gameProbs.length;
    for (var s = 0; s < numSims; s++) {
      var simPts = new Float64Array(basePoints);

      for (var g = 0; g < nGames; g++) {
        var hi = gameProbs[g][0], ai = gameProbs[g][1];
        var pHome = gameProbs[g][2], pDraw = gameProbs[g][3];
        var r = Math.random();
        if (r < pHome) {
          simPts[hi] += 3;
        } else if (r < pHome + pDraw) {
          simPts[hi] += 1;
          simPts[ai] += 1;
        } else {
          simPts[ai] += 3;
        }
      }

      for (var i = 0; i < n; i++) {
        totalPoints[i] += simPts[i];
        totalPointsSq[i] += simPts[i] * simPts[i];
      }

      // Rank all teams by points
      var ranked = Array.from({length: n}, function(_, i) { return i; });
      ranked.sort(function(a, b) { return simPts[b] - simPts[a]; });

      titleCount[ranked[0]]++;
      for (var k = 0; k < Math.min(4, n); k++) top4Count[ranked[k]]++;
      for (var k = 0; k < Math.min(6, n); k++) top6Count[ranked[k]]++;
      for (var k = n - 3; k < n; k++) relegCount[ranked[k]]++;
    }

    var results = [];
    for (var i = 0; i < n; i++) {
      var avgPts = totalPoints[i] / numSims;
      var variance = (totalPointsSq[i] / numSims) - (avgPts * avgPts);
      var ptsSD = Math.sqrt(Math.max(0, variance));
      var s = standings[teams[i]];
      var curPts = (s.points !== undefined) ? s.points : (s.wins * 3 + (s.draws || 0));

      results.push({
        abbreviation: teams[i],
        name: getTeamName(teams[i]),
        current_points: curPts,
        avg_points: avgPts,
        pts_sd: ptsSD,
        title_pct: (titleCount[i] / numSims) * 100,
        top4_pct: (top4Count[i] / numSims) * 100,
        top6_pct: (top6Count[i] / numSims) * 100,
        releg_pct: (relegCount[i] / numSims) * 100,
      });
    }

    results.sort(function (a, b) { return b.avg_points - a.avg_points; });
    return results;
  }

  function renderSimTable(results) {
    var tbody = document.getElementById("sim-body-epl");
    tbody.innerHTML = "";
    results.forEach(function (team, idx) {
      var row = document.createElement("tr");
      row.innerHTML =
        '<td class="num">' + (idx + 1) + '</td>' +
        '<td><div class="team-cell">' +
          '<span class="team-name">' + team.name + '</span>' +
          '<span class="team-abbr">' + team.abbreviation + '</span>' +
        '</div></td>' +
        '<td class="num">' + team.current_points + '</td>' +
        '<td class="num" style="font-weight:700">' + team.avg_points.toFixed(1) + '</td>' +
        '<td class="num win-range">±' + team.pts_sd.toFixed(1) + '</td>' +
        '<td class="num ' + pctClass(team.title_pct) + '">' + team.title_pct.toFixed(1) + '%</td>' +
        '<td class="num ' + pctClass(team.top4_pct) + '">' + team.top4_pct.toFixed(1) + '%</td>' +
        '<td class="num ' + pctClass(team.top6_pct) + '">' + team.top6_pct.toFixed(1) + '%</td>' +
        '<td class="num ' + pctClass(100 - team.releg_pct, true) + '">' + team.releg_pct.toFixed(1) + '%</td>';
      tbody.appendChild(row);
    });
  }

  // ── Helpers ────────────────────────────────────────────────

  function formatSRS(val) {
    return (val > 0 ? "+" : "") + val.toFixed(2);
  }

  function formatDate(date) {
    return date.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
  }

  function formatGameDate(dateStr) {
    var parts = dateStr.split("-");
    if (parts.length === 3) {
      var d = new Date(parts[0], parts[1] - 1, parts[2]);
      var days = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
      var months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
      return days[d.getDay()] + ", " + months[d.getMonth()] + " " + d.getDate();
    }
    return dateStr;
  }

  function pctClass(pct, invert) {
    if (invert) {
      if (pct >= 80) return "pct-low";
      if (pct >= 50) return "pct-med";
      return "pct-high";
    }
    if (pct >= 50) return "pct-high";
    if (pct >= 20) return "pct-med";
    return "pct-low";
  }

  function getTeamName(abbr) {
    for (var i = 0; i < teamsData.length; i++) {
      if (teamsData[i].abbreviation === abbr) return teamsData[i].name;
    }
    return abbr;
  }
})();