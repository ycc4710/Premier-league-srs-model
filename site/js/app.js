/**
 * NBA SRS Ratings - Frontend Application
 *
 * Three-tab app:
 * 1. Rankings - SRS bar chart, sortable table, scatter plot
 * 2. Predictions - Next 10 days game picks with spreads and probabilities
 * 3. Simulation - Client-side Monte Carlo with interactive sliders
 */

(function () {
  "use strict";

  var HOME_COURT_ADV = 3.0;

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
        document.getElementById("stat-rmse").textContent = stats.rmse.toFixed(2);
        document.getElementById("stat-ppg").textContent = stats.avg_ppg.toFixed(1);
        document.getElementById("stat-hca").textContent = (stats.home_advantage > 0 ? "+" : "") + stats.home_advantage.toFixed(2) + " pts";
        document.getElementById("model-stats").style.display = "flex";
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
                  "Record: " + team.wins + "-" + team.losses,
                ];
              },
            },
          },
        },
        scales: {
          x: { title: { display: true, text: "SRS Rating" }, grid: { color: "rgba(128,128,128,0.15)" } },
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
      : teams.filter(function (t) { return t.conference === currentFilter; });

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
      var confBadge = team.conference === "East" ? "conf-east" : "conf-west";
      var logoUrl = team.team_id
        ? "https://cdn.nba.com/logos/nba/" + team.team_id + "/primary/L/logo.svg"
        : "";

      row.innerHTML =
        '<td class="num">' + team.srs_rank + '</td>' +
        '<td><div class="team-cell">' +
          (logoUrl ? '<img class="team-logo" src="' + logoUrl + '" alt="' + team.abbreviation + '" loading="lazy" onerror="this.style.display=\'none\'">' : '') +
          '<span class="team-name">' + team.name + '</span>' +
          '<span class="team-abbr">' + team.abbreviation + '</span>' +
          '<span class="conf-badge ' + confBadge + '">' + (team.conference === "East" ? "E" : "W") + '</span>' +
        '</div></td>' +
        '<td class="num ' + srsClass + '">' + formatSRS(team.srs) + '</td>' +
        '<td class="num ' + movClass + '">' + formatSRS(team.mov) + '</td>' +
        '<td class="num ' + sosClass + '">' + formatSRS(team.sos) + '</td>' +
        '<td class="num">' + team.wins + '-' + team.losses + '</td>' +
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
    var eastTeams = teams.filter(function (t) { return t.conference === "East"; });
    var westTeams = teams.filter(function (t) { return t.conference === "West"; });
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
            label: "Eastern Conference",
            data: eastTeams.map(function (t) { return { x: t.standings_rank, y: t.srs_rank, team: t }; }),
            backgroundColor: "rgba(59, 130, 246, 0.7)", borderColor: "rgb(59, 130, 246)",
            borderWidth: 1.5, pointRadius: 6, pointHoverRadius: 9,
          },
          {
            label: "Western Conference",
            data: westTeams.map(function (t) { return { x: t.standings_rank, y: t.srs_rank, team: t }; }),
            backgroundColor: "rgba(239, 68, 68, 0.7)", borderColor: "rgb(239, 68, 68)",
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
                return [
                  t.name + " (" + t.abbreviation + ")",
                  "SRS Rank: #" + t.srs_rank + " (SRS: " + formatSRS(t.srs) + ")",
                  "Standings: #" + t.standings_rank + " (" + t.wins + "-" + t.losses + ")",
                ];
              },
            },
          },
        },
        scales: {
          x: { title: { display: true, text: "Standings Rank (by Win%)" }, min: 0.5, max: maxRank + 0.5, ticks: { stepSize: 5 }, grid: { color: "rgba(128,128,128,0.1)" } },
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

    // Group by date
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

      games.forEach(function (g) {
        var spreadAbs = Math.abs(g.predicted_margin).toFixed(1);
        var homeWinPct = (g.home_win_prob * 100).toFixed(0);
        var awayWinPct = (100 - g.home_win_prob * 100).toFixed(0);
        var spreadClass = g.predicted_margin >= 0 ? "home-fav" : "away-fav";
        var spreadText;
        if (g.predicted_margin >= 0) {
          spreadText = g.home_team + " -" + spreadAbs;
        } else {
          spreadText = g.away_team + " -" + spreadAbs;
        }

        var homeLogoUrl = getLogoUrl(g.home_team);
        var awayLogoUrl = getLogoUrl(g.away_team);

        html += '<div class="prediction-card">';
        html += '  <div class="pred-teams">';
        html += '    <div class="pred-team-row">';
        if (awayLogoUrl) html += '<img src="' + awayLogoUrl + '" alt="' + g.away_team + '" onerror="this.style.display=\'none\'">';
        html += '      <span class="pred-team-name">' + g.away_team + '</span>';
        html += '      <span class="pred-srs">SRS ' + formatSRS(g.away_srs) + '</span>';
        html += '    </div>';
        html += '    <div class="pred-at">at</div>';
        html += '    <div class="pred-team-row">';
        if (homeLogoUrl) html += '<img src="' + homeLogoUrl + '" alt="' + g.home_team + '" onerror="this.style.display=\'none\'">';
        html += '      <span class="pred-team-name">' + g.home_team + '</span>';
        html += '      <span class="pred-srs">SRS ' + formatSRS(g.home_srs) + '</span>';
        html += '    </div>';
        html += '  </div>';
        html += '  <div class="pred-result">';
        html += '    <div class="pred-spread ' + spreadClass + '">' + spreadText + '</div>';
        html += '    <div class="pred-prob">' + g.home_team + ' ' + homeWinPct + '% / ' + g.away_team + ' ' + awayWinPct + '%</div>';
        html += '    <div class="pred-prob-bar"><div class="pred-prob-fill" style="width:' + homeWinPct + '%"></div></div>';
        html += '  </div>';
        html += '</div>';
      });

      html += '</div>';
    });

    container.innerHTML = html;
  }

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

    // Auto-run if no results yet
    if (!lastSimResults) {
      runMonteCarloSim();
    }
  }

  // Normal CDF using error function approximation
  function normalCDF(x) {
    return 0.5 * (1 + erf(x / Math.SQRT2));
  }

  // Error function approximation (Abramowitz & Stegun)
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

    // Use setTimeout to allow UI to update before blocking computation
    setTimeout(function () {
      var t0 = performance.now();
      var results = computeMonteCarlo(sim, stdError, numSims);
      var elapsed = ((performance.now() - t0) / 1000).toFixed(2);

      lastSimResults = results;
      statusEl.textContent = "Completed " + numSims.toLocaleString() +
        " simulations of " + sim.remaining_games.length + " remaining games in " + elapsed + "s" +
        " (SE = " + stdError.toFixed(1) + ")";
      tableSection.style.display = "block";
      renderSimTable(results);

      runBtn.disabled = false;
      runBtn.textContent = "Run Simulation";
    }, 20);
  }

  function computeMonteCarlo(sim, stdError, numSims) {
    var standings = sim.current_standings;
    var games = sim.remaining_games;
    var divisions = sim.divisions || {};

    // Build team list and index
    var teams = Object.keys(standings);
    var teamIdx = {};
    teams.forEach(function (t, i) { teamIdx[t] = i; });
    var n = teams.length;

    // Build SRS lookup from teamsData
    var srsMap = {};
    teamsData.forEach(function (t) { srsMap[t.abbreviation] = t.srs; });

    // Pre-compute win probabilities
    var gameProbs = [];
    games.forEach(function (g) {
      var hi = teamIdx[g.home_team];
      var ai = teamIdx[g.away_team];
      if (hi === undefined || ai === undefined) return;
      var homeSRS = srsMap[g.home_team] || 0;
      var awaySRS = srsMap[g.away_team] || 0;
      var margin = homeSRS - awaySRS + HOME_COURT_ADV;
      var prob = winProbability(margin, stdError);
      gameProbs.push([hi, ai, prob]);
    });

    // Build division lookup: team index -> division name
    var teamDiv = new Array(n);
    // Build conf lookup
    var teamConf = new Array(n);
    teams.forEach(function (t, i) {
      teamConf[i] = standings[t].conference;
      teamDiv[i] = standings[t].division || "";
    });

    // Base wins/losses
    var baseWins = new Float64Array(n);
    var baseLosses = new Float64Array(n);
    teams.forEach(function (t, i) {
      baseWins[i] = standings[t].wins;
      baseLosses[i] = standings[t].losses;
    });

    // Accumulators
    var totalWins = new Float64Array(n);
    var totalWinsSq = new Float64Array(n);
    var playoffCount = new Float64Array(n);
    var playInCount = new Float64Array(n);
    var divWinCount = new Float64Array(n);

    // Build division groups (by index)
    var divGroups = {};
    for (var divName in divisions) {
      divGroups[divName] = [];
      divisions[divName].forEach(function (t) {
        if (teamIdx[t] !== undefined) divGroups[divName].push(teamIdx[t]);
      });
    }

    // Run simulations
    var nGames = gameProbs.length;
    for (var s = 0; s < numSims; s++) {
      // Clone base wins/losses
      var simWins = new Float64Array(baseWins);
      var simLosses = new Float64Array(baseLosses);

      // Simulate each game
      for (var g = 0; g < nGames; g++) {
        var hi = gameProbs[g][0];
        var ai = gameProbs[g][1];
        var prob = gameProbs[g][2];
        if (Math.random() < prob) {
          simWins[hi]++;
          simLosses[ai]++;
        } else {
          simWins[ai]++;
          simLosses[hi]++;
        }
      }

      // Accumulate win totals
      for (var i = 0; i < n; i++) {
        totalWins[i] += simWins[i];
        totalWinsSq[i] += simWins[i] * simWins[i];
      }

      // Determine playoff + play-in teams by conference
      var confTeams = { "East": [], "West": [] };
      for (var i = 0; i < n; i++) {
        var c = teamConf[i];
        if (confTeams[c]) confTeams[c].push(i);
      }
      for (var c in confTeams) {
        confTeams[c].sort(function (a, b) { return simWins[b] - simWins[a]; });
        // Top 6 make playoffs
        for (var k = 0; k < Math.min(6, confTeams[c].length); k++) {
          playoffCount[confTeams[c][k]]++;
        }
        // 7-10 are play-in
        for (var k = 6; k < Math.min(10, confTeams[c].length); k++) {
          playInCount[confTeams[c][k]]++;
        }
      }

      // Determine division winners
      for (var divName in divGroups) {
        var members = divGroups[divName];
        if (members.length === 0) continue;
        var bestIdx = members[0];
        var bestWins = simWins[bestIdx];
        for (var k = 1; k < members.length; k++) {
          if (simWins[members[k]] > bestWins) {
            bestIdx = members[k];
            bestWins = simWins[bestIdx];
          }
        }
        divWinCount[bestIdx]++;
      }
    }

    // Build results array
    var results = [];
    for (var i = 0; i < n; i++) {
      var avgWins = totalWins[i] / numSims;
      var avgLosses = 82 - avgWins;
      var variance = (totalWinsSq[i] / numSims) - (avgWins * avgWins);
      var winSD = Math.sqrt(Math.max(0, variance));
      var playoffPct = (playoffCount[i] / numSims) * 100;
      var playoffSD = Math.sqrt(playoffPct * (100 - playoffPct) / numSims);
      var playInPct = (playInCount[i] / numSims) * 100;
      var playInSD = Math.sqrt(playInPct * (100 - playInPct) / numSims);
      var divPct = (divWinCount[i] / numSims) * 100;
      var divSD = Math.sqrt(divPct * (100 - divPct) / numSims);

      results.push({
        abbreviation: teams[i],
        name: getTeamName(teams[i]),
        team_id: getTeamId(teams[i]),
        conference: teamConf[i],
        division: teamDiv[i],
        current_wins: baseWins[i],
        current_losses: baseLosses[i],
        avg_wins: avgWins,
        avg_losses: avgLosses,
        win_sd: winSD,
        playoff_pct: playoffPct,
        playoff_sd: playoffSD,
        play_in_pct: playInPct,
        play_in_sd: playInSD,
        div_win_pct: divPct,
        div_win_sd: divSD,
      });
    }

    results.sort(function (a, b) { return b.avg_wins - a.avg_wins; });
    return results;
  }

  function renderSimTable(results) {
    var east = results.filter(function (t) { return t.conference === "East"; });
    var west = results.filter(function (t) { return t.conference === "West"; });
    east.sort(function (a, b) { return b.avg_wins - a.avg_wins; });
    west.sort(function (a, b) { return b.avg_wins - a.avg_wins; });

    fillSimBody(document.getElementById("sim-body-east"), east);
    fillSimBody(document.getElementById("sim-body-west"), west);
  }

  function fillSimBody(tbody, teams) {
    tbody.innerHTML = "";
    teams.forEach(function (team, idx) {
      var row = document.createElement("tr");
      var logoUrl = team.team_id
        ? "https://cdn.nba.com/logos/nba/" + team.team_id + "/primary/L/logo.svg"
        : "";

      row.innerHTML =
        '<td class="num">' + (idx + 1) + '</td>' +
        '<td><div class="team-cell">' +
          (logoUrl ? '<img class="team-logo" src="' + logoUrl + '" alt="' + team.abbreviation + '" loading="lazy" onerror="this.style.display=\'none\'">' : '') +
          '<span class="team-name">' + team.name + '</span>' +
          '<span class="team-abbr">' + team.abbreviation + '</span>' +
        '</div></td>' +
        '<td class="num">' + team.current_wins + '-' + team.current_losses + '</td>' +
        '<td class="num" style="font-weight:700">' + team.avg_wins.toFixed(1) + '-' + team.avg_losses.toFixed(1) + '</td>' +
        '<td class="num win-range">' + team.win_sd.toFixed(1) + '</td>' +
        '<td class="num ' + pctClass(team.playoff_pct) + '">' + team.playoff_pct.toFixed(1) + '%</td>' +
        '<td class="num win-range">' + team.playoff_sd.toFixed(1) + '%</td>' +
        '<td class="num ' + pctClass(team.play_in_pct) + '">' + team.play_in_pct.toFixed(1) + '%</td>' +
        '<td class="num win-range">' + team.play_in_sd.toFixed(1) + '%</td>' +
        '<td class="num ' + pctClass(team.div_win_pct) + '">' + team.div_win_pct.toFixed(1) + '%</td>' +
        '<td class="num win-range">' + team.div_win_sd.toFixed(1) + '%</td>';

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

  function pctClass(pct) {
    if (pct >= 50) return "pct-high";
    if (pct >= 20) return "pct-med";
    return "pct-low";
  }

  function getLogoUrl(abbr) {
    for (var i = 0; i < teamsData.length; i++) {
      if (teamsData[i].abbreviation === abbr && teamsData[i].team_id) {
        return "https://cdn.nba.com/logos/nba/" + teamsData[i].team_id + "/primary/L/logo.svg";
      }
    }
    return "";
  }

  function getTeamName(abbr) {
    for (var i = 0; i < teamsData.length; i++) {
      if (teamsData[i].abbreviation === abbr) return teamsData[i].name;
    }
    return abbr;
  }

  function getTeamId(abbr) {
    for (var i = 0; i < teamsData.length; i++) {
      if (teamsData[i].abbreviation === abbr) return teamsData[i].team_id;
    }
    return 0;
  }
})();
