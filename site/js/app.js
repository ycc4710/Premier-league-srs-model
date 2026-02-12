/**
 * NBA SRS Ratings - Frontend Application
 *
 * Three-tab app:
 * 1. Rankings - SRS bar chart, sortable table, scatter plot
 * 2. Predictions - This week's game picks with spreads and probabilities
 * 3. Simulation - Monte Carlo projected standings and playoff probabilities
 */

(function () {
  "use strict";

  let teamsData = [];
  let predictionsData = [];
  let simulationData = {};
  let currentFilter = "all";
  let simFilter = "all";
  let currentSort = { key: "srs_rank", dir: "asc" };
  let chartsRendered = { rankings: false, simulation: false };

  // ── Bootstrap ──────────────────────────────────────────────

  document.addEventListener("DOMContentLoaded", () => {
    init();
    setupTabs();
    setupProbabilityTab();
    setupSimulationTab();
  });

  async function init() {
    try {
      const resp = await fetch("data/srs_data.json");
      if (!resp.ok) throw new Error("HTTP " + resp.status);
      const data = await resp.json();

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

      document.getElementById("loading").style.display = "none";

      // Setup tabs and show the first one
      setupTabs();
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
    // Update buttons
    document.querySelectorAll(".tab-btn").forEach(function (b) {
      b.classList.toggle("active", b.dataset.tab === tabId);
    });

    // Hide all tabs
    document.querySelectorAll(".tab-content").forEach(function (el) {
      el.style.display = "none";
    });

    // Show selected tab
    var tabEl = document.getElementById("tab-" + tabId);
    if (tabEl) tabEl.style.display = "block";

    // Lazy-render tab content
    if (tabId === "rankings" && !chartsRendered.rankings) {
      renderBarChart(teamsData);
      renderTable(teamsData);
      renderScatterChart(teamsData);
      setupFilterButtons();
      setupSorting();
      chartsRendered.rankings = true;
    } else if (tabId === "predictions") {
      renderPredictions(predictionsData);
    } else if (tabId === "simulation" && !chartsRendered.simulation) {
      renderSimulation(simulationData);
      chartsRendered.simulation = true;
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

  function renderSimulation(sim) {
    var emptyEl = document.getElementById("simulation-empty");
    var chartSection = document.getElementById("sim-chart-section");
    var tableSection = document.getElementById("sim-table-section");

    if (!sim || !sim.teams || sim.teams.length === 0) {
      emptyEl.style.display = "block";
      chartSection.style.display = "none";
      tableSection.style.display = "none";
      return;
    }

    emptyEl.style.display = "none";
    chartSection.style.display = "block";
    tableSection.style.display = "block";

    // Update description
    document.getElementById("sim-desc").textContent =
      "Projected final standings based on " + sim.num_simulations.toLocaleString() +
      " simulations of " + sim.remaining_games + " remaining games using SRS-derived win probabilities.";

    // Playoff probability chart
    renderPlayoffChart(sim.teams);

    // Simulation table
    renderSimTable(sim.teams);
    setupSimFilterButtons(sim.teams);
  }

  function renderPlayoffChart(teams) {
    var sorted = teams.slice().sort(function (a, b) { return a.playoff_pct - b.playoff_pct; });
    var labels = sorted.map(function (t) { return t.abbreviation; });
    var playoffPcts = sorted.map(function (t) { return t.playoff_pct; });
    var playInPcts = sorted.map(function (t) { return t.play_in_pct; });

    var ctx = document.getElementById("playoff-chart").getContext("2d");
    new Chart(ctx, {
      type: "bar",
      data: {
        labels: labels,
        datasets: [
          {
            label: "Playoff %",
            data: playoffPcts,
            backgroundColor: "rgba(5, 150, 105, 0.75)",
            borderColor: "rgb(5, 150, 105)",
            borderWidth: 1,
          },
          {
            label: "Play-In %",
            data: playInPcts,
            backgroundColor: "rgba(245, 158, 11, 0.6)",
            borderColor: "rgb(245, 158, 11)",
            borderWidth: 1,
          },
        ],
      },
      options: {
        indexAxis: "y",
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          tooltip: {
            callbacks: {
              label: function (ctx) {
                return ctx.dataset.label + ": " + ctx.raw.toFixed(1) + "%";
              },
            },
          },
        },
        scales: {
          x: {
            stacked: true,
            title: { display: true, text: "Probability %" },
            max: 100,
            grid: { color: "rgba(128,128,128,0.15)" },
          },
          y: {
            stacked: true,
            grid: { display: false },
            ticks: { font: { size: 11, weight: "bold" } },
          },
        },
      },
    });

    document.getElementById("playoff-chart").parentElement.style.height =
      Math.max(400, sorted.length * 22) + "px";
  }

  function renderSimTable(teams) {
    var filtered = simFilter === "all"
      ? teams
      : teams.filter(function (t) { return t.conference === simFilter; });

    // Sort by avg_wins descending
    filtered = filtered.slice().sort(function (a, b) { return b.avg_wins - a.avg_wins; });

    var tbody = document.getElementById("simulation-body");
    tbody.innerHTML = "";

    filtered.forEach(function (team, idx) {
      var row = document.createElement("tr");
      var confBadge = team.conference === "East" ? "conf-east" : "conf-west";
      var logoUrl = team.team_id
        ? "https://cdn.nba.com/logos/nba/" + team.team_id + "/primary/L/logo.svg"
        : "";

      row.innerHTML =
        '<td class="num">' + (idx + 1) + '</td>' +
        '<td><div class="team-cell">' +
          (logoUrl ? '<img class="team-logo" src="' + logoUrl + '" alt="' + team.abbreviation + '" loading="lazy" onerror="this.style.display=\'none\'">' : '') +
          '<span class="team-name">' + team.name + '</span>' +
          '<span class="team-abbr">' + team.abbreviation + '</span>' +
          '<span class="conf-badge ' + confBadge + '">' + (team.conference === "East" ? "E" : "W") + '</span>' +
        '</div></td>' +
        '<td class="num">' + team.current_wins + '-' + team.current_losses + '</td>' +
        '<td class="num" style="font-weight:700">' + team.avg_wins.toFixed(1) + '</td>' +
        '<td class="num win-range">' + team.win_range_low + '-' + team.win_range_high + '</td>' +
        '<td class="num ' + pctClass(team.playoff_pct) + '">' + team.playoff_pct.toFixed(1) + '%</td>' +
        '<td class="num ' + pctClass(team.play_in_pct) + '">' + team.play_in_pct.toFixed(1) + '%</td>' +
        '<td class="num ' + pctClass(team.top_seed_pct) + '">' + team.top_seed_pct.toFixed(1) + '%</td>' +
        '<td class="num ' + pctClass(team.lottery_pct) + '">' + team.lottery_pct.toFixed(1) + '%</td>';

      tbody.appendChild(row);
    });
  }

  function setupSimFilterButtons(teams) {
    document.querySelectorAll(".sim-filter-btn").forEach(function (btn) {
      btn.addEventListener("click", function () {
        simFilter = btn.dataset.filter;
        document.querySelectorAll(".sim-filter-btn").forEach(function (b) { b.classList.remove("active"); });
        btn.classList.add("active");
        renderSimTable(teams);
      });
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
    // Parse YYYY-MM-DD
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
    // Lookup team_id from teamsData
    for (var i = 0; i < teamsData.length; i++) {
      if (teamsData[i].abbreviation === abbr && teamsData[i].team_id) {
        return "https://cdn.nba.com/logos/nba/" + teamsData[i].team_id + "/primary/L/logo.svg";
      }
    }
    return "";
  }

  // ── Tab Logic ───────────────────────────────────────────────
  function setupTabs() {
    document.querySelectorAll(".tab-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        const tab = btn.dataset.tab;
        document.querySelectorAll(".tab-content").forEach((c) => c.classList.remove("active"));
        document.querySelectorAll(".tab-content").forEach((c) => c.style.display = "none");
        document.getElementById(`tab-${tab}`).classList.add("active");
        document.getElementById(`tab-${tab}`).style.display = "block";
      });
    });
  }

  // ── Probability Tab ─────────────────────────────────────────
  function setupProbabilityTab() {
    const btn = document.getElementById("fetch-schedule-btn");
    if (!btn) return;
    btn.addEventListener("click", async () => {
      btn.disabled = true;
      btn.textContent = "Loading...";
      try {
        const resp = await fetch("data/weekly_schedule.json");
        if (!resp.ok) throw new Error("Schedule not found");
        const schedule = await resp.json();
        const resultsDiv = document.getElementById("probability-results");
        // Filter for games in the next 7 days (Sunday-Saturday)
        const today = new Date();
        const dayOfWeek = today.getDay(); // 0=Sunday
        const weekStart = new Date(today);
        weekStart.setDate(today.getDate() - dayOfWeek);
        const weekEnd = new Date(weekStart);
        weekEnd.setDate(weekStart.getDate() + 6);
        const weekGames = schedule.filter(game => {
          const gameDate = new Date(game.date);
          return gameDate >= weekStart && gameDate <= weekEnd;
        });
        weekGames.sort((a, b) => new Date(a.date) - new Date(b.date));
        resultsDiv.innerHTML = renderProbabilityResults(weekGames);
      } catch (err) {
        document.getElementById("probability-results").textContent = "Failed to load schedule.";
      } finally {
        btn.disabled = false;
        btn.textContent = "Fetch This Week's NBA Schedule";
      }
    });
  }

  function renderProbabilityResults(schedule) {
    if (!schedule || !schedule.length) return "No games found.";
    // Use teamsData for SRS
    let html = '<table class="prob-table"><thead><tr><th>Date</th><th>Away</th><th>Home</th><th>Predicted Margin</th><th>Home Win Probability</th></tr></thead><tbody>';
    const abbrMap = {};
    for (const t of teamsData) abbrMap[t.abbreviation] = t;
    for (const game of schedule) {
      const home = abbrMap[game.home];
      const away = abbrMap[game.away];
      if (!home || !away) {
        html += `<tr><td>${game.date}</td><td>${game.away}</td><td>${game.home}</td><td>-</td><td>-</td></tr>`;
        continue;
      }
      const margin = home.srs - away.srs;
      const homeWinProb = 1 / (1 + Math.pow(10, -(margin) / 10));
      html += `<tr><td>${game.date}</td><td>${game.away}</td><td>${game.home}</td><td>${margin > 0 ? '+' : ''}${margin.toFixed(2)}</td><td>${(homeWinProb * 100).toFixed(1)}%</td></tr>`;
    }
    html += '</tbody></table>';
    return html;
  }

  // ── Simulation Tab ─────────────────────────────────────────
  function setupSimulationTab() {
    const form = document.getElementById("simulation-controls");
    if (!form) return;
    async function runSim() {
      const stdError = parseFloat(document.getElementById("sim-std-error").value);
      const numSim = parseInt(document.getElementById("sim-num").value);
      const resultsDiv = document.getElementById("simulation-results");
      resultsDiv.textContent = "Running simulation...";
      try {
        // Trigger backend simulation automatically (Flask server)
        await fetch(`http://localhost:5000/run_simulation?std_error=${stdError}&num_sim=${numSim}`);
        const resp = await fetch("data/simulation_results.json?" + Date.now());
        if (!resp.ok) throw new Error("Simulation results not found");
        const results = await resp.json();
        resultsDiv.innerHTML = renderSimulationResults(results);
      } catch (err) {
        resultsDiv.textContent = "Failed to load simulation results.";
      }
    }
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      await runSim();
    });
    document.getElementById("sim-std-error").addEventListener("change", runSim);
    document.getElementById("sim-num").addEventListener("change", runSim);
  }

  function renderSimulationResults(results) {
    if (!results) return "No results.";
    let html = '<table class="sim-table"><thead><tr><th>Team</th><th>Div. Prob</th><th>Playoff Prob</th><th>Avg Wins</th></tr></thead><tbody>';
    for (const [abbr, res] of Object.entries(results)) {
      html += `<tr><td>${abbr}</td><td>${(res.division_prob * 100).toFixed(1)}%</td><td>${(res.playoff_prob * 100).toFixed(1)}%</td><td>${res.avg_wins.toFixed(1)}</td></tr>`;
    }
    html += '</tbody></table>';
    return html;
  }
})();
