/**
 * NBA SRS Ratings - Frontend Application
 *
 * Fetches srs_data.json and renders:
 * 1. Horizontal bar chart of SRS ratings
 * 2. Sortable rankings table
 * 3. Scatter plot comparing SRS rank vs standings rank
 */

(function () {
  "use strict";

  let teamsData = [];
  let currentFilter = "all";
  let currentSort = { key: "srs_rank", dir: "asc" };

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
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();

      teamsData = data.teams;

      // Update header metadata
      document.getElementById("season-label").textContent =
        data.metadata.season + " Season";
      const updated = new Date(data.metadata.last_updated);
      document.getElementById("last-updated").textContent =
        "Updated " + formatDate(updated) +
        " · " + data.metadata.total_games + " games";

      document.getElementById("loading").style.display = "none";
      document.getElementById("content").style.display = "block";

      renderBarChart(teamsData);
      renderTable(teamsData);
      renderScatterChart(teamsData);
      setupFilterButtons();
      setupSorting();
    } catch (err) {
      console.error("Failed to load SRS data:", err);
      document.getElementById("loading").style.display = "none";
      document.getElementById("error").style.display = "block";
    }
  }

  // ── Bar Chart ──────────────────────────────────────────────

  function renderBarChart(teams) {
    const sorted = [...teams].sort((a, b) => a.srs - b.srs);
    const labels = sorted.map((t) => t.abbreviation);
    const values = sorted.map((t) => t.srs);
    const colors = sorted.map((t) => {
      if (t.srs > 0) return "rgba(5, 150, 105, 0.8)";
      if (t.srs < 0) return "rgba(220, 38, 38, 0.7)";
      return "rgba(107, 114, 128, 0.6)";
    });
    const borderColors = sorted.map((t) => {
      if (t.srs > 0) return "rgb(5, 150, 105)";
      if (t.srs < 0) return "rgb(220, 38, 38)";
      return "rgb(107, 114, 128)";
    });

    const ctx = document.getElementById("srs-chart").getContext("2d");
    new Chart(ctx, {
      type: "bar",
      data: {
        labels: labels,
        datasets: [
          {
            label: "SRS Rating",
            data: values,
            backgroundColor: colors,
            borderColor: borderColors,
            borderWidth: 1,
          },
        ],
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
                const team = sorted[ctx.dataIndex];
                return [
                  `SRS: ${team.srs > 0 ? "+" : ""}${team.srs.toFixed(2)}`,
                  `MOV: ${team.mov > 0 ? "+" : ""}${team.mov.toFixed(2)}`,
                  `SOS: ${team.sos > 0 ? "+" : ""}${team.sos.toFixed(2)}`,
                  `Record: ${team.wins}-${team.losses}`,
                ];
              },
            },
          },
        },
        scales: {
          x: {
            title: { display: true, text: "SRS Rating" },
            grid: { color: "rgba(128,128,128,0.15)" },
          },
          y: {
            grid: { display: false },
            ticks: { font: { size: 11, weight: "bold" } },
          },
        },
      },
    });

    // Set chart height based on number of teams
    document.getElementById("srs-chart").parentElement.style.height =
      Math.max(400, sorted.length * 22) + "px";
  }

  // ── Rankings Table ─────────────────────────────────────────

  function renderTable(teams) {
    const filtered =
      currentFilter === "all"
        ? teams
        : teams.filter((t) => t.conference === currentFilter);

    const sorted = sortTeams(filtered, currentSort.key, currentSort.dir);
    const tbody = document.getElementById("rankings-body");
    tbody.innerHTML = "";

    sorted.forEach((team) => {
      const row = document.createElement("tr");

      const diff = team.standings_rank - team.srs_rank;
      let diffText, diffClass;
      if (diff > 0) {
        diffText = "+" + diff;
        diffClass = "diff-better";
      } else if (diff < 0) {
        diffText = String(diff);
        diffClass = "diff-worse";
      } else {
        diffText = "0";
        diffClass = "diff-same";
      }

      const srsClass = team.srs > 0 ? "srs-positive" : team.srs < 0 ? "srs-negative" : "srs-neutral";
      const movClass = team.mov > 0 ? "srs-positive" : team.mov < 0 ? "srs-negative" : "srs-neutral";
      const sosClass = team.sos > 0 ? "srs-positive" : team.sos < 0 ? "srs-negative" : "srs-neutral";

      const confBadge = team.conference === "East" ? "conf-east" : "conf-west";

      const logoUrl = team.team_id
        ? `https://cdn.nba.com/logos/nba/${team.team_id}/primary/L/logo.svg`
        : "";

      row.innerHTML = `
        <td class="num">${team.srs_rank}</td>
        <td>
          <div class="team-cell">
            ${logoUrl ? `<img class="team-logo" src="${logoUrl}" alt="${team.abbreviation}" loading="lazy" onerror="this.style.display='none'">` : ""}
            <span class="team-name">${team.name}</span>
            <span class="team-abbr">${team.abbreviation}</span>
            <span class="conf-badge ${confBadge}">${team.conference === "East" ? "E" : "W"}</span>
          </div>
        </td>
        <td class="num ${srsClass}">${formatSRS(team.srs)}</td>
        <td class="num ${movClass}">${formatSRS(team.mov)}</td>
        <td class="num ${sosClass}">${formatSRS(team.sos)}</td>
        <td class="num">${team.wins}-${team.losses}</td>
        <td class="num">${(team.win_pct * 100).toFixed(1)}%</td>
        <td class="num">${team.standings_rank}</td>
        <td class="num ${diffClass}">${diffText}</td>
      `;

      tbody.appendChild(row);
    });
  }

  function sortTeams(teams, key, dir) {
    return [...teams].sort((a, b) => {
      let va, vb;
      if (key === "name") {
        va = a.name;
        vb = b.name;
      } else if (key === "record") {
        va = a.win_pct;
        vb = b.win_pct;
      } else {
        va = a[key];
        vb = b[key];
      }
      if (typeof va === "string") {
        return dir === "asc" ? va.localeCompare(vb) : vb.localeCompare(va);
      }
      return dir === "asc" ? va - vb : vb - va;
    });
  }

  function setupSorting() {
    document.querySelectorAll("#rankings-table th.sortable").forEach((th) => {
      th.addEventListener("click", () => {
        const key = th.dataset.sort;

        // Toggle direction
        if (currentSort.key === key) {
          currentSort.dir = currentSort.dir === "asc" ? "desc" : "asc";
        } else {
          currentSort.key = key;
          // Default: descending for numeric values, ascending for names and ranks
          currentSort.dir = (key === "name" || key === "srs_rank" || key === "standings_rank")
            ? "asc" : "desc";
        }

        // Update header classes
        document.querySelectorAll("#rankings-table th.sortable").forEach((h) => {
          h.classList.remove("sort-active", "sort-asc", "sort-desc");
        });
        th.classList.add("sort-active", "sort-" + currentSort.dir);

        renderTable(teamsData);
      });
    });
  }

  function setupFilterButtons() {
    document.querySelectorAll(".filter-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        currentFilter = btn.dataset.filter;
        document.querySelectorAll(".filter-btn").forEach((b) =>
          b.classList.remove("active")
        );
        btn.classList.add("active");
        renderTable(teamsData);
      });
    });
  }

  // ── Scatter Chart ──────────────────────────────────────────

  function renderScatterChart(teams) {
    const eastTeams = teams.filter((t) => t.conference === "East");
    const westTeams = teams.filter((t) => t.conference === "West");

    const maxRank = teams.length;

    // Diagonal line data (perfect agreement)
    const diagPoints = [];
    for (let i = 1; i <= maxRank; i++) diagPoints.push({ x: i, y: i });

    const ctx = document.getElementById("comparison-chart").getContext("2d");
    new Chart(ctx, {
      type: "scatter",
      data: {
        datasets: [
          {
            label: "Perfect Agreement",
            data: diagPoints,
            showLine: true,
            pointRadius: 0,
            borderColor: "rgba(128,128,128,0.3)",
            borderDash: [5, 5],
            borderWidth: 1.5,
          },
          {
            label: "Eastern Conference",
            data: eastTeams.map((t) => ({
              x: t.standings_rank,
              y: t.srs_rank,
              team: t,
            })),
            backgroundColor: "rgba(59, 130, 246, 0.7)",
            borderColor: "rgb(59, 130, 246)",
            borderWidth: 1.5,
            pointRadius: 6,
            pointHoverRadius: 9,
          },
          {
            label: "Western Conference",
            data: westTeams.map((t) => ({
              x: t.standings_rank,
              y: t.srs_rank,
              team: t,
            })),
            backgroundColor: "rgba(239, 68, 68, 0.7)",
            borderColor: "rgb(239, 68, 68)",
            borderWidth: 1.5,
            pointRadius: 6,
            pointHoverRadius: 9,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: true,
        aspectRatio: 1,
        plugins: {
          tooltip: {
            filter: (item) => item.datasetIndex > 0,
            callbacks: {
              label: function (ctx) {
                const t = ctx.raw.team;
                return [
                  `${t.name} (${t.abbreviation})`,
                  `SRS Rank: #${t.srs_rank} (SRS: ${formatSRS(t.srs)})`,
                  `Standings: #${t.standings_rank} (${t.wins}-${t.losses})`,
                ];
              },
            },
          },
        },
        scales: {
          x: {
            title: { display: true, text: "Standings Rank (by Win%)" },
            min: 0.5,
            max: maxRank + 0.5,
            reverse: false,
            ticks: { stepSize: 5 },
            grid: { color: "rgba(128,128,128,0.1)" },
          },
          y: {
            title: { display: true, text: "SRS Rank" },
            min: 0.5,
            max: maxRank + 0.5,
            reverse: true,
            ticks: { stepSize: 5 },
            grid: { color: "rgba(128,128,128,0.1)" },
          },
        },
      },
    });
  }

  // ── Helpers ────────────────────────────────────────────────

  function formatSRS(val) {
    const sign = val > 0 ? "+" : "";
    return sign + val.toFixed(2);
  }

  function formatDate(date) {
    return date.toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
    });
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
