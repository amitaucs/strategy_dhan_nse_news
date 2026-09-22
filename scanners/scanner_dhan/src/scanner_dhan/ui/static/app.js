/**
 * Frontend Controller for DhanHQ Multi-Scanner Dashboard
 * Clean Left-Hand Side Filter Control Panel & Interactive Trading Table
 */

let allScanners = [];
let currentReport = null;
let currentlyDisplayedItems = [];

// EOD Digest State (Declared at top to prevent TDZ ReferenceError)
let currentEodReport = null;
let eodFilterCategory = "ALL";
let eodFilterLevel = "ALL";
let eodSearchQuery = "";
const _eodReportCache = {};
let _isEodLoading = false;

// Streamlined Filter State
const filterState = {
  status: "matched", // "matched" or "all"
  selectedLevelDropdown: "ALL", // Active key level description dropdown value
  selectedSignalDropdown: "ALL", // Active signal dropdown value
  selectedVolumeDropdown: "ALL", // Active volume dropdown value
  searchQuery: "",
  sortColumn: "distance_pct",
  sortAsc: true,
};

function formatShortScannerName(name) {
  if (!name) return "None";
  return name
    .replace(/^NSE\s+/i, "")
    .replace(/\s+Scanner$/i, "")
    .replace(/\s+Strategy$/i, "")
    .replace(/^ST-\d+\s+/i, "")
    .trim();
}

function initializeScannerApp() {
  initLucide();
  checkHealth();
  loadScanners();
  setupEventListeners();
  if (typeof loadEodDatesAndLatest === "function") {
    loadEodDatesAndLatest();
  }
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initializeScannerApp);
} else {
  initializeScannerApp();
}

function initLucide() {
  if (window.lucide) {
    window.lucide.createIcons();
  }
}

async function checkHealth() {
  try {
    const res = await fetch("/api/health");
    const data = await res.json();
    const badge = document.getElementById("dhan-status-badge");
    if (!badge) return;

    if (!data.dhan_connected) {
      badge.innerHTML = `
        <span class="w-2 h-2 rounded-full bg-amber-400"></span>
        <span class="text-amber-400 text-xs font-semibold">Credentials Not Set (.env)</span>
      `;
    } else if (data.data_api_active === false) {
      if (data.data_api_error_code === "DH-902" || data.data_api_status === "unsubscribed") {
        badge.innerHTML = `
          <span class="w-2 h-2 rounded-full bg-amber-400 animate-pulse"></span>
          <span class="text-amber-300 text-xs font-semibold" title="${data.data_api_message || 'Data API Plan not subscribed'}">⚠️ Data API Inactive (DH-902)</span>
        `;
      } else if (data.data_api_error_code === "DH-901" || data.data_api_status === "token_expired") {
        badge.innerHTML = `
          <span class="w-2 h-2 rounded-full bg-red-400 animate-pulse"></span>
          <span class="text-red-400 text-xs font-semibold" title="${data.data_api_message || 'Token Expired'}">⚠️ Token Expired (DH-901)</span>
        `;
      } else {
        badge.innerHTML = `
          <span class="w-2 h-2 rounded-full bg-amber-400"></span>
          <span class="text-amber-300 text-xs font-semibold" title="${data.data_api_message || ''}">DhanHQ Connected (${data.client_id})</span>
        `;
      }
    } else {
      badge.innerHTML = `
        <span class="w-2 h-2 rounded-full bg-emerald-400 live-dot"></span>
        <span class="text-emerald-400 text-xs font-semibold">DhanHQ Connected (${data.client_id})</span>
      `;
    }
  } catch (err) {
    console.error("Health check error:", err);
  }
}

let selectedScannerId = null;
let selectedCategoryFilter = "ALL";
let homeSearchQuery = "";

const categoryBadgeColors = {
  "Support & Resistance": "bg-emerald-950/60 text-emerald-300 border-emerald-800/50",
  "Momentum": "bg-indigo-950/60 text-indigo-300 border-indigo-800/50",
  "Options / Intraday Momentum": "bg-indigo-950/60 text-indigo-300 border-indigo-800/50",
  "Reversal": "bg-purple-950/60 text-purple-300 border-purple-800/50",
  "Reversal / Momentum": "bg-purple-950/60 text-purple-300 border-purple-800/50",
  "Trend": "bg-amber-950/60 text-amber-300 border-amber-800/50",
  "Trend Following": "bg-amber-950/60 text-amber-300 border-amber-800/50",
  "Breakout": "bg-amber-950/60 text-amber-300 border-amber-800/50",
  "Breakout / Momentum": "bg-amber-950/60 text-amber-300 border-amber-800/50",
  "Smart Money Concepts": "bg-purple-950/60 text-purple-300 border-purple-800/50",
  "Smart Money / ICT": "bg-purple-950/60 text-purple-300 border-purple-800/50",
  "Chart Patterns": "bg-rose-950/60 text-rose-300 border-rose-800/50",
  "Chart Patterns & Breakout": "bg-rose-950/60 text-rose-300 border-rose-800/50",
  "Pattern Recognition": "bg-rose-950/60 text-rose-300 border-rose-800/50",
  "Classic Chart Patterns": "bg-rose-950/60 text-rose-300 border-rose-800/50",
};

const categoryIconGradients = {
  "Support & Resistance": "from-emerald-500 to-teal-600 shadow-emerald-500/20",
  "Momentum": "from-indigo-500 to-purple-600 shadow-indigo-500/20",
  "Options / Intraday Momentum": "from-indigo-500 to-purple-600 shadow-indigo-500/20",
  "Reversal": "from-purple-500 to-pink-600 shadow-purple-500/20",
  "Reversal / Momentum": "from-purple-500 to-pink-600 shadow-purple-500/20",
  "Trend": "from-amber-500 to-orange-600 shadow-amber-500/20",
  "Trend Following": "from-amber-500 to-orange-600 shadow-amber-500/20",
  "Breakout": "from-amber-500 to-yellow-600 shadow-amber-500/20",
  "Breakout / Momentum": "from-amber-500 to-yellow-600 shadow-amber-500/20",
  "Smart Money Concepts": "from-purple-500 to-indigo-600 shadow-purple-500/20",
  "Smart Money / ICT": "from-purple-500 to-indigo-600 shadow-purple-500/20",
  "Chart Patterns": "from-rose-500 to-pink-600 shadow-rose-500/20",
  "Chart Patterns & Breakout": "from-rose-500 to-pink-600 shadow-rose-500/20",
  "Pattern Recognition": "from-rose-500 to-pink-600 shadow-rose-500/20",
  "Classic Chart Patterns": "from-rose-500 to-pink-600 shadow-rose-500/20",
};

function matchesCategory(scanner, selectedFilter) {
  if (!selectedFilter || selectedFilter === "ALL") return true;
  const sCat = (scanner.category || "").toLowerCase();
  const sId = (scanner.id || "").toLowerCase();
  const sName = (scanner.name || "").toLowerCase();
  const fCat = selectedFilter.toLowerCase();

  // Direct exact or substring match
  if (sCat === fCat || sCat.includes(fCat) || fCat.includes(sCat)) return true;

  // Smart Money Concepts / SMC / ICT
  if (fCat.includes("smart money") || fCat.includes("smc") || fCat === "smc") {
    return (
      sCat.includes("smart money") ||
      sCat.includes("smc") ||
      sCat.includes("ict") ||
      sId.includes("order_block") ||
      sId.includes("fvg") ||
      sName.includes("fvg") ||
      sName.includes("order block")
    );
  }

  // Chart Patterns
  if (fCat.includes("pattern")) {
    return (
      sCat.includes("pattern") ||
      sId.includes("head_and_shoulders") ||
      sId.includes("vcp") ||
      sName.includes("head & shoulders") ||
      sName.includes("vcp")
    );
  }

  // Breakouts
  if (fCat.includes("breakout")) {
    return (
      sCat.includes("breakout") ||
      sId.includes("ath") ||
      sId.includes("vcp") ||
      sId.includes("st14") ||
      sName.includes("all-time high") ||
      sName.includes("vcp")
    );
  }

  // Reversals
  if (fCat.includes("reversal")) {
    return (
      sCat.includes("reversal") ||
      sId.includes("rsi") ||
      sId.includes("ha_st01") ||
      sId.includes("head_and_shoulders") ||
      sName.includes("rsi") ||
      sName.includes("heikin")
    );
  }

  // Trend Following
  if (fCat.includes("trend")) {
    return (
      sCat.includes("trend") ||
      sId.includes("st07") ||
      sId.includes("st15") ||
      sName.includes("trend")
    );
  }

  // Support & Resistance
  if (
    fCat.includes("support") ||
    fCat.includes("resistance") ||
    fCat.includes("s&r") ||
    fCat === "s&r"
  ) {
    return (
      sCat.includes("support") ||
      sCat.includes("resistance") ||
      sId.includes("support") ||
      sId.includes("resistance") ||
      sId.includes("nifty50_support") ||
      sId.includes("nifty100_support")
    );
  }

  // Momentum
  if (fCat.includes("momentum")) {
    return (
      sCat.includes("momentum") ||
      sId.includes("rsi") ||
      sId.includes("ath") ||
      sId.includes("st14") ||
      sId.includes("ha_st01") ||
      sId.includes("vcp") ||
      sId.includes("st07")
    );
  }

  return false;
}

async function loadScanners() {
  const navContainer = document.getElementById("scanner-nav-list");
  const studioContainer = document.getElementById("scanner-studio-panel");
  if (navContainer) {
    navContainer.innerHTML = `
      <div class="flex items-center justify-center py-16 text-slate-400">
        <svg class="animate-spin h-5 w-5 text-sky-400 mr-2.5" viewBox="0 0 24 24">
          <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" fill="none"></circle>
          <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
        </svg>
        <span class="text-xs">Loading strategies...</span>
      </div>
    `;
  }

  try {
    const res = await fetch("/api/scanners");
    allScanners = await res.json();
    if (!selectedScannerId && allScanners.length > 0) {
      // Default to order_block or first scanner
      const ob = allScanners.find((s) => s.id === "order_block");
      selectedScannerId = ob ? ob.id : allScanners[0].id;
    }
    renderScannerNavList();
    renderStudioPanel(selectedScannerId);
  } catch (err) {
    console.error("Failed to load scanners:", err);
    if (navContainer) {
      navContainer.innerHTML = `
        <div class="text-center py-8 text-rose-400 bg-rose-950/20 border border-rose-800/40 rounded-xl text-xs">
          Failed to load scanners. Please check backend server.
        </div>
      `;
    }
  }
}

function renderScannerNavList() {
  const container = document.getElementById("scanner-nav-list");
  const countBadge = document.getElementById("scanners-count-badge");
  if (!container) return;

  const query = homeSearchQuery.trim().toLowerCase();
  const filtered = allScanners.filter((s) => {
    const matchesCat = matchesCategory(s, selectedCategoryFilter);
    const matchesSearch =
      !query ||
      s.name.toLowerCase().includes(query) ||
      s.description.toLowerCase().includes(query) ||
      (s.category && s.category.toLowerCase().includes(query));
    return matchesCat && matchesSearch;
  });

  if (countBadge) {
    countBadge.innerText = `${filtered.length} of ${allScanners.length} Available`;
  }

  if (filtered.length === 0) {
    container.innerHTML = `
      <div class="p-6 text-center text-slate-500 bg-slate-900/40 rounded-2xl border border-slate-800 text-xs">
        No strategies found matching "${homeSearchQuery}".
      </div>
    `;
    return;
  }

  container.innerHTML = filtered
    .map((s) => {
      const isSelected = s.id === selectedScannerId;
      const catClass =
        categoryBadgeColors[s.category] || "bg-slate-800 text-slate-300 border-slate-700";

      const activeContainerClass = isSelected
        ? "bg-slate-800/95 border-sky-500/80 shadow-lg shadow-sky-500/10 ring-1 ring-sky-500/40"
        : "bg-slate-900/60 border-slate-800/80 hover:bg-slate-800/50 hover:border-slate-700/80";

      const iconBgClass = isSelected
        ? "bg-sky-500/20 text-sky-400 border border-sky-500/30"
        : "bg-slate-800 text-slate-400 border border-slate-700/50";

      return `
        <div
          onclick="selectScanner('${s.id}')"
          class="cursor-pointer p-3.5 rounded-2xl border transition-all duration-200 flex flex-col space-y-2 ${activeContainerClass} group"
        >
          <div class="flex items-start justify-between gap-2">
            <div class="flex items-center space-x-2.5 min-w-0">
              <div class="p-2 rounded-xl shrink-0 transition ${iconBgClass}">
                <i data-lucide="${s.icon || "activity"}" class="w-4 h-4"></i>
              </div>
              <div class="min-w-0">
                <h4 class="text-xs font-bold text-white group-hover:text-sky-300 transition truncate">${s.name}</h4>
                <span class="inline-block mt-0.5 px-2 py-0.5 text-[10px] font-medium rounded-full border ${catClass}">${s.category}</span>
              </div>
            </div>
            ${
              isSelected
                ? `<span class="flex h-2 w-2 relative shrink-0 mt-1">
                    <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-sky-400 opacity-75"></span>
                    <span class="relative inline-flex rounded-full h-2 w-2 bg-sky-500"></span>
                   </span>`
                : `<i data-lucide="chevron-right" class="w-4 h-4 text-slate-600 group-hover:text-slate-400 transition shrink-0 mt-1"></i>`
            }
          </div>
          <p class="text-[11px] text-slate-400 line-clamp-2 leading-relaxed">
            ${s.description}
          </p>
        </div>
      `;
    })
    .join("");

  initLucide();
}

function selectScanner(scannerId) {
  selectedScannerId = scannerId;
  renderScannerNavList();
  renderStudioPanel(scannerId);
}

function renderStudioPanel(scannerId) {
  const container = document.getElementById("scanner-studio-panel");
  if (!container) return;

  const scanner = allScanners.find((s) => s.id === scannerId);
  if (!scanner) {
    container.innerHTML = `
      <div class="text-center py-20 text-slate-500">
        <i data-lucide="info" class="w-8 h-8 mx-auto mb-2 text-slate-600"></i>
        <p class="text-sm">Select a strategy from the left panel to configure parameters and run scan.</p>
      </div>
    `;
    initLucide();
    return;
  }

  const catClass =
    categoryBadgeColors[scanner.category] || "bg-slate-800 text-slate-300 border-slate-700";
  const iconGradient =
    categoryIconGradients[scanner.category] || "from-sky-500 to-indigo-600 shadow-sky-500/20";

  // Separate parameters into primary (universe/timeframe), select/rule filters, and numeric sensitivity
  const primaryParams = (scanner.parameters || []).filter(
    (p) => p.name === "universe" || p.name === "timeframe"
  );
  const filterParams = (scanner.parameters || []).filter(
    (p) => p.type === "select" && p.name !== "universe" && p.name !== "timeframe"
  );
  const sliderParams = (scanner.parameters || []).filter(
    (p) => p.type === "float" || p.type === "int"
  );
  const boolParams = (scanner.parameters || []).filter(
    (p) => p.type === "bool"
  );

  const renderBoolParam = (p) => `
    <div id="param-card-${scanner.id}-${p.name}" class="bg-slate-950/60 p-4 rounded-2xl border border-slate-800/80 hover:border-slate-700 transition flex items-center justify-between">
      <div>
        <label class="text-xs font-bold text-slate-300 flex items-center space-x-1.5 cursor-pointer" for="input-${scanner.id}-${p.name}">
          <i data-lucide="check-circle-2" class="w-3.5 h-3.5 text-sky-400"></i>
          <span>${p.label}</span>
        </label>
        <p class="text-[10px] text-slate-400 mt-1 max-w-[280px]">${p.description || ""}</p>
      </div>
      <label class="relative inline-flex items-center cursor-pointer shrink-0 ml-3">
        <input
          type="checkbox"
          id="input-${scanner.id}-${p.name}"
          ${p.default ? "checked" : ""}
          class="sr-only peer"
        />
        <div class="w-10 h-5.5 bg-slate-800 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[3px] after:left-[3px] after:bg-white after:border-slate-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-sky-500"></div>
      </label>
    </div>
  `;

  const renderSelectParam = (p) => `
    <div id="param-card-${scanner.id}-${p.name}" class="bg-slate-950/60 p-4 rounded-2xl border border-slate-800/80 hover:border-slate-700 transition">
      <div class="flex items-center justify-between mb-2">
        <label class="text-xs font-bold text-slate-300 flex items-center space-x-1.5">
          <i data-lucide="sliders" class="w-3.5 h-3.5 text-sky-400"></i>
          <span>${p.label}</span>
        </label>
        ${
          p.name === "universe"
            ? `<span class="text-[10px] text-sky-400 bg-sky-950/60 border border-sky-800/40 px-2 py-0.5 rounded-full font-mono">Real-time Feed</span>`
            : p.name === "timeframe"
            ? `<span class="text-[10px] text-indigo-400 bg-indigo-950/60 border border-indigo-800/40 px-2 py-0.5 rounded-full font-mono">Candle Interval</span>`
            : p.name === "target_level" || p.name === "target_ema"
            ? `<span class="text-[10px] text-emerald-400 bg-emerald-950/60 border border-emerald-800/40 px-2 py-0.5 rounded-full font-mono">Direct Target</span>`
            : ""
        }
      </div>
      <select
        id="input-${scanner.id}-${p.name}"
        class="w-full px-3.5 py-2.5 bg-slate-900 border border-slate-700/80 rounded-xl text-xs text-white focus:outline-none focus:border-sky-500 font-semibold cursor-pointer shadow-inner"
      >
        ${(p.options || [])
          .map(
            (opt) => `
          <option value="${opt.value}" ${opt.value === p.default ? "selected" : ""}>
            ${opt.label}
          </option>
        `
          )
          .join("")}
      </select>
    </div>
  `;

  const renderSliderParam = (p) => `
    <div id="param-card-${scanner.id}-${p.name}" class="bg-slate-950/60 p-4 rounded-2xl border border-slate-800/80 hover:border-slate-700 transition">
      <div class="flex items-center justify-between mb-2">
        <label class="text-xs font-bold text-slate-300 flex items-center space-x-1.5">
          <i data-lucide="gauge" class="w-3.5 h-3.5 text-sky-400"></i>
          <span>${p.label}</span>
        </label>
        <span class="font-mono text-xs font-bold text-sky-400 bg-sky-950/70 border border-sky-800/40 px-2.5 py-0.5 rounded-full" id="val-${scanner.id}-${p.name}">
          ${p.default}${p.name.includes("pct") || p.name.includes("dist") ? "%" : ""}
        </span>
      </div>
      <input
        type="range"
        id="input-${scanner.id}-${p.name}"
        min="${p.min || 0}"
        max="${p.max || 100}"
        step="${p.step || 1}"
        value="${p.default}"
        class="w-full h-2 bg-slate-800 rounded-lg appearance-none cursor-pointer accent-sky-400 mt-2 disabled:opacity-30 disabled:cursor-not-allowed"
        oninput="document.getElementById('val-${scanner.id}-${p.name}').innerText = (this.value > 0 && '${p.name}'.includes('dist') ? '+' : '') + this.value + '${p.name.includes("pct") || p.name.includes("dist") ? "%" : ""}'"
      />
      <div class="flex justify-between text-[10px] text-slate-500 font-mono mt-1.5">
        <span>Min: ${p.min}${p.name.includes("pct") || p.name.includes("dist") ? "%" : ""}</span>
        <span>Max: ${p.max}${p.name.includes("pct") || p.name.includes("dist") ? "%" : ""}</span>
      </div>
    </div>
  `;

  container.innerHTML = `
    <!-- Strategy Header Card -->
    <div class="flex flex-col md:flex-row items-start md:items-center justify-between gap-4 pb-6 border-b border-slate-800/80">
      <div class="flex items-start space-x-4">
        <div class="p-3 rounded-2xl bg-gradient-to-tr ${iconGradient} shadow-lg text-white shrink-0 mt-0.5">
          <i data-lucide="${scanner.icon || "activity"}" class="w-6 h-6"></i>
        </div>
        <div>
          <div class="flex items-center space-x-2.5 mb-1.5">
            <span class="px-3 py-0.5 text-xs font-bold rounded-full border ${catClass}">${scanner.category}</span>
            <span class="inline-flex items-center space-x-1 px-2.5 py-0.5 rounded-full bg-emerald-950/60 border border-emerald-800/40 text-[10px] font-semibold text-emerald-400">
              <span class="w-1.5 h-1.5 rounded-full bg-emerald-400 live-dot"></span>
              <span>Ready for Live Scan</span>
            </span>
          </div>
          <h2 class="text-xl font-black text-white tracking-tight">${scanner.name}</h2>
          <p class="text-xs text-slate-300 leading-relaxed mt-1 max-w-2xl">${scanner.description}</p>
        </div>
      </div>
    </div>

    <!-- Strategy Highlights / Technical Engine Badges -->
    <div class="grid grid-cols-1 sm:grid-cols-3 gap-3 py-1">
      <div class="bg-slate-950/40 p-3 rounded-2xl border border-slate-800/60 flex items-center space-x-3">
        <div class="p-2 rounded-xl bg-sky-500/10 text-sky-400">
          <i data-lucide="cpu" class="w-4 h-4"></i>
        </div>
        <div>
          <div class="text-[10px] text-slate-400 uppercase font-bold tracking-wider">Execution Engine</div>
          <div class="text-xs font-semibold text-white">Parallel Dhan API</div>
        </div>
      </div>
      <div class="bg-slate-950/40 p-3 rounded-2xl border border-slate-800/60 flex items-center space-x-3">
        <div class="p-2 rounded-xl bg-indigo-500/10 text-indigo-400">
          <i data-lucide="clock" class="w-4 h-4"></i>
        </div>
        <div>
          <div class="text-[10px] text-slate-400 uppercase font-bold tracking-wider">Timeframe</div>
          <div class="text-xs font-semibold text-white">
            ${
              scanner.id === "st07_monthly_ha_89ema" || scanner.id === "ath_st08_breakout"
                ? "Monthly Only (Dedicated)"
                : scanner.id === "st14_bullish_ce" || scanner.id === "st14_scanner"
                ? "Daily + 1H (Dual TF)"
                : "1D, 2H, 1H, 15M Supported"
            }
          </div>
        </div>
      </div>
      <div class="bg-slate-950/40 p-3 rounded-2xl border border-slate-800/60 flex items-center space-x-3">
        <div class="p-2 rounded-xl bg-purple-500/10 text-purple-400">
          <i data-lucide="target" class="w-4 h-4"></i>
        </div>
        <div>
          <div class="text-[10px] text-slate-400 uppercase font-bold tracking-wider">Target Universe</div>
          <div class="text-xs font-semibold text-white">Nifty 100, 50, Smallcap, F&O</div>
        </div>
      </div>
    </div>

    <!-- Parameter Configuration Form (2-Column Grid) -->
    <div class="space-y-4">
      <div class="flex items-center justify-between pt-2">
        <h3 class="text-xs font-black text-slate-300 uppercase tracking-wider flex items-center space-x-2">
          <i data-lucide="settings-2" class="w-4 h-4 text-sky-400"></i>
          <span>Live Strategy Parameters</span>
        </h3>
        <span class="text-[11px] text-slate-500">Fine-tune sensitivity & criteria</span>
      </div>

      <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
        <!-- Primary Universe & Timeframe Selectors -->
        ${primaryParams.map(renderSelectParam).join("")}

        <!-- Custom Dropdown Rules (e.g. Block Type, First Candle Only) -->
        ${filterParams.map(renderSelectParam).join("")}

        <!-- Numeric Range Sliders (Impulse, Volume, Distance %, Lookback, VWAP) -->
        ${sliderParams.map(renderSliderParam).join("")}

        <!-- Boolean Toggles (Rising VWAP, 10:15 Cutoff) -->
        ${boolParams.map(renderBoolParam).join("")}
      </div>
    </div>

    <!-- Launch Scan Action Button -->
    <div class="pt-4 border-t border-slate-800/80">
      <button
        onclick="runScanner('${scanner.id}')"
        id="btn-run-${scanner.id}"
        class="w-full py-4 px-6 bg-gradient-to-r from-sky-500 via-blue-600 to-indigo-600 hover:from-sky-400 hover:via-blue-500 hover:to-indigo-500 text-white font-bold text-sm rounded-2xl transition duration-200 flex items-center justify-center space-x-2.5 shadow-xl shadow-sky-900/40 glow-blue cursor-pointer"
      >
        <i data-lucide="play" class="w-4 h-4 fill-current"></i>
        <span>⚡ Execute Live Scan</span>
      </button>
      <p class="text-center text-[11px] text-slate-500 mt-2">
        Scans live market data across selected equities universe in parallel.
      </p>
    </div>
  `;

  initLucide();

  // Dynamic Parameter Dependency Handling (e.g. RSI scan_mode auto-disables irrelevant threshold slider)
  const scanModeInput = document.getElementById(`input-${scanner.id}-scan_mode`);
  if (scanModeInput) {
    const updateRsiParamState = () => {
      const mode = scanModeInput.value;
      const oversoldCard = document.getElementById(`param-card-${scanner.id}-oversold_threshold`);
      const overboughtCard = document.getElementById(`param-card-${scanner.id}-overbought_threshold`);
      const oversoldInput = document.getElementById(`input-${scanner.id}-oversold_threshold`);
      const overboughtInput = document.getElementById(`input-${scanner.id}-overbought_threshold`);

      if (mode === "OVERSOLD_ONLY") {
        if (overboughtCard) {
          overboughtCard.classList.add("opacity-35", "grayscale", "pointer-events-none");
          const labelSpan = overboughtCard.querySelector("label span");
          if (labelSpan && !labelSpan.innerText.includes("(Disabled)")) {
            labelSpan.innerText = `${labelSpan.innerText} (Disabled)`;
          }
        }
        if (overboughtInput) overboughtInput.disabled = true;

        if (oversoldCard) {
          oversoldCard.classList.remove("opacity-35", "grayscale", "pointer-events-none");
          const labelSpan = oversoldCard.querySelector("label span");
          if (labelSpan) labelSpan.innerText = labelSpan.innerText.replace(" (Disabled)", "");
        }
        if (oversoldInput) oversoldInput.disabled = false;
      } else if (mode === "OVERBOUGHT_ONLY") {
        if (oversoldCard) {
          oversoldCard.classList.add("opacity-35", "grayscale", "pointer-events-none");
          const labelSpan = oversoldCard.querySelector("label span");
          if (labelSpan && !labelSpan.innerText.includes("(Disabled)")) {
            labelSpan.innerText = `${labelSpan.innerText} (Disabled)`;
          }
        }
        if (oversoldInput) oversoldInput.disabled = true;

        if (overboughtCard) {
          overboughtCard.classList.remove("opacity-35", "grayscale", "pointer-events-none");
          const labelSpan = overboughtCard.querySelector("label span");
          if (labelSpan) labelSpan.innerText = labelSpan.innerText.replace(" (Disabled)", "");
        }
        if (overboughtInput) overboughtInput.disabled = false;
      } else {
        // EXTREMES_ONLY or ALL_STOCKS -> Both active
        if (oversoldCard) {
          oversoldCard.classList.remove("opacity-35", "grayscale", "pointer-events-none");
          const labelSpan = oversoldCard.querySelector("label span");
          if (labelSpan) labelSpan.innerText = labelSpan.innerText.replace(" (Disabled)", "");
        }
        if (oversoldInput) oversoldInput.disabled = false;

        if (overboughtCard) {
          overboughtCard.classList.remove("opacity-35", "grayscale", "pointer-events-none");
          const labelSpan = overboughtCard.querySelector("label span");
          if (labelSpan) labelSpan.innerText = labelSpan.innerText.replace(" (Disabled)", "");
        }
        if (overboughtInput) overboughtInput.disabled = false;
      }
    };

    scanModeInput.addEventListener("change", updateRsiParamState);
    updateRsiParamState(); // Run once immediately on render
  }
}

async function runScanner(scannerId, overrideParams = null) {
  const scanner = allScanners.find((s) => s.id === scannerId);
  if (!scanner) return;

  // Collect current parameter values
  const params = {};
  (scanner.parameters || []).forEach((p) => {
    const input = document.getElementById(`input-${scannerId}-${p.name}`);
    if (input) {
      if (p.type === "int") {
        params[p.name] = parseInt(input.value, 10);
      } else if (p.type === "float") {
        params[p.name] = parseFloat(input.value);
      } else if (p.type === "bool") {
        params[p.name] = input.checked;
      } else {
        params[p.name] = input.value;
      }
    } else if (p.default !== undefined) {
      params[p.name] = p.default;
    }
  });

  if (overrideParams) {
    Object.assign(params, overrideParams);
  }

  // Sync universe select on home card if it exists
  const homeUnivSelect = document.getElementById(`input-${scannerId}-universe`);
  if (homeUnivSelect && params.universe) {
    homeUnivSelect.value = params.universe;
  }

  // Sync results view universe dropdown
  const resultsUnivSelect = document.getElementById("results-select-universe");
  if (resultsUnivSelect) {
    const univParam = (scanner.parameters || []).find((p) => p.name === "universe");
    if (univParam && Array.isArray(univParam.options) && univParam.options.length > 0) {
      const selectedVal = params.universe || univParam.default || "NIFTY_500";
      resultsUnivSelect.innerHTML = univParam.options
        .map(
          (opt) =>
            `<option value="${opt.value}" ${opt.value === selectedVal ? "selected" : ""}>${opt.label}</option>`
        )
        .join("");
    }
    if (params.universe) {
      resultsUnivSelect.value = params.universe;
    }
  }

  // Sync timeframe select on home card if it exists
  const homeTfSelect = document.getElementById(`input-${scannerId}-timeframe`);
  if (homeTfSelect && params.timeframe) {
    homeTfSelect.value = params.timeframe;
  }

  // Sync results view timeframe dropdown
  const resultsTfSelect = document.getElementById("results-select-timeframe");
  if (resultsTfSelect) {
    if (scannerId === "st07_monthly_ha_89ema" || scannerId === "ath_st08_breakout") {
      resultsTfSelect.innerHTML = `<option value="1M" selected>1M (Monthly)</option>`;
      resultsTfSelect.disabled = true;
      resultsTfSelect.classList.add("opacity-75", "cursor-not-allowed");
      resultsTfSelect.title = "Monthly Strategy (Fixed Timeframe)";
    } else if (scannerId === "st14_bullish_ce" || scannerId === "st14_scanner") {
      resultsTfSelect.innerHTML = `<option value="Daily+1H" selected>Daily + 1H (Dual TF)</option>`;
      resultsTfSelect.disabled = true;
      resultsTfSelect.classList.add("opacity-75", "cursor-not-allowed");
      resultsTfSelect.title = "ST-14 Dual Timeframe (Daily Trend + 1H Momentum Breakout & VWAP)";
    } else {
      resultsTfSelect.disabled = false;
      resultsTfSelect.classList.remove("opacity-75", "cursor-not-allowed");
      resultsTfSelect.title = "Select Candle Timeframe";
      resultsTfSelect.innerHTML = `
        <option value="1D">1D (Daily)</option>
        <option value="2H">2H (120m)</option>
        <option value="1H">1H (60m)</option>
        <option value="15M">15M (15m)</option>
      `;
      if (params.timeframe) {
        resultsTfSelect.value = params.timeframe;
      }
    }
  }

  selectedScannerId = scannerId;

  // Switch to Results view in Loading state
  showResultsView();
  document.getElementById("results-scanner-title").innerText = scanner.name;
  document.getElementById("results-scanner-desc").innerText = scanner.description;
  document.getElementById("results-loading")?.classList.remove("hidden");
  document.getElementById("results-content")?.classList.add("hidden");
  document.getElementById("results-error")?.classList.add("hidden");

  try {
    const res = await fetch(`/api/scanners/${scannerId}/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ parameters: params }),
    });

    let resData;
    try {
      resData = await res.json();
    } catch (e) {
      if (res.status === 504 || res.status === 524 || res.status === 408) {
        resData = {
          status: "error",
          error_title: "Scanner Request Timeout",
          error_message: `The scan request timed out (HTTP ${res.status}) because scanning a large universe takes longer than the gateway timeout. Try selecting 'Nifty 100' or 'Nifty 50' for immediate scans, or use the automated EOD Multi-Scanner Daily Digest for the entire Nifty 500.`,
          error_type: "TIMEOUT_ERROR",
        };
      } else if (res.status === 502 || res.status === 503) {
        resData = {
          status: "error",
          error_title: "Server Busy / Gateway Unavailable",
          error_message: `The server gateway encountered HTTP ${res.status}. Please wait a few seconds and retry.`,
          error_type: "GATEWAY_ERROR",
        };
      } else {
        resData = {
          status: "error",
          error_title: "Scan Execution Failed",
          error_message: `Server returned HTTP ${res.status || "Unknown"}. Please check server logs or retry with Nifty 100.`,
          error_type: "HTTP_ERROR",
        };
      }
    }

    if (!res.ok || resData.status === "error") {
      renderErrorView(resData, scanner, params);
      return;
    }

    currentReport = resData;
    currentReport.scanner_id = scannerId;
    currentReport._lastParams = params;
    renderReport(currentReport);
  } catch (err) {
    renderErrorView({
      status: "error",
      error_title: "Scan Execution Failed",
      error_message: err.message || "Could not complete scan request.",
      error_type: "EXECUTION_ERROR",
    }, scanner, params);
  } finally {
    document.getElementById("results-loading")?.classList.add("hidden");
  }
}

function renderErrorView(errReport, scanner, params) {
  const errContainer = document.getElementById("results-error");
  document.getElementById("results-content")?.classList.add("hidden");
  document.getElementById("results-loading")?.classList.add("hidden");
  document.getElementById("btn-copy-tv")?.classList.add("hidden");

  const errType = errReport.error_type || "EXECUTION_ERROR";
  const errTitle = errReport.error_title || (errType === "DATA_API_UNSUBSCRIBED" ? "DhanHQ Data API Subscription Required" : "Scan Execution Failed");
  const errMsg = errReport.error_message || errReport.detail || "An error occurred while fetching live market data.";
  const actionUrl = errReport.action_url || (errType === "DATA_API_UNSUBSCRIBED" || errType === "AUTH_ERROR" ? "https://web.dhan.co" : "");
  const actionLabel = errReport.action_label || (errType === "DATA_API_UNSUBSCRIBED" ? "Enable Data Plan on Dhan" : "Open DhanHQ Portal");

  let helpStepsHtml = "";
  if (errType === "DATA_API_UNSUBSCRIBED" || (errMsg && (errMsg.includes("DH-902") || errMsg.includes("451") || errMsg.includes("Data API")))) {
    helpStepsHtml = `
      <div class="mt-4 p-4 rounded-2xl bg-amber-950/40 border border-amber-600/30 text-left space-y-2">
        <h4 class="text-xs font-bold text-amber-300 uppercase tracking-wider flex items-center space-x-1.5">
          <i data-lucide="help-circle" class="w-4 h-4 text-amber-400"></i>
          <span>How to Enable Historical Data APIs on Dhan:</span>
        </h4>
        <ol class="list-decimal list-inside text-xs text-slate-300 space-y-1.5 leading-relaxed">
          <li>Log in to your Dhan web dashboard at <a href="https://web.dhan.co" target="_blank" class="text-sky-400 font-semibold underline hover:text-sky-300">web.dhan.co</a>.</li>
          <li>Click your <strong>Profile Icon</strong> (top-right) and select <strong>DhanHQ Trading APIs</strong>.</li>
          <li>Go to the <strong>API Plans</strong> tab and activate / subscribe to the <strong>Data APIs Plan</strong>.</li>
          <li>Once subscribed, return here and click <strong>Re-Run Scan</strong> below.</li>
        </ol>
      </div>
    `;
  } else if (errType === "AUTH_ERROR" || (errMsg && (errMsg.includes("DH-901") || errMsg.includes("401") || errMsg.includes("Token")))) {
    helpStepsHtml = `
      <div class="mt-4 p-4 rounded-2xl bg-red-950/40 border border-red-600/30 text-left space-y-2">
        <h4 class="text-xs font-bold text-red-300 uppercase tracking-wider flex items-center space-x-1.5">
          <i data-lucide="key" class="w-4 h-4 text-red-400"></i>
          <span>How to Refresh Your Dhan Access Token:</span>
        </h4>
        <ol class="list-decimal list-inside text-xs text-slate-300 space-y-1.5 leading-relaxed">
          <li>Log in to <a href="https://web.dhan.co" target="_blank" class="text-sky-400 font-semibold underline hover:text-sky-300">web.dhan.co</a>.</li>
          <li>Navigate to <strong>DhanHQ Trading APIs > Access Tokens</strong>.</li>
          <li>Generate a new 24-hour Access Token.</li>
          <li>Click <strong>API Settings (🔑)</strong> in the top header of this terminal to save the fresh token.</li>
        </ol>
      </div>
    `;
  }

  if (errContainer) {
    errContainer.innerHTML = `
      <div class="max-w-2xl mx-auto py-8 px-6 text-center space-y-5 bg-slate-900/90 border border-slate-800 rounded-3xl shadow-2xl">
        <div class="inline-flex p-4 rounded-2xl bg-amber-500/10 border border-amber-500/30 text-amber-400">
          <i data-lucide="alert-triangle" class="w-10 h-10 text-amber-400"></i>
        </div>
        <div class="space-y-2">
          <div class="inline-flex items-center space-x-2 px-3 py-1 rounded-full bg-amber-950/60 border border-amber-800/40 text-amber-300 text-xs font-mono font-bold">
            <span>${errType}</span>
          </div>
          <h3 class="text-xl font-black text-white">${errTitle}</h3>
          <p class="text-xs sm:text-sm text-slate-300 max-w-lg mx-auto leading-relaxed">
            ${errMsg}
          </p>
        </div>

        ${helpStepsHtml}

        <div class="flex items-center justify-center space-x-3 pt-3 flex-wrap gap-y-2">
          ${actionUrl ? `
            <a
              href="${actionUrl}"
              target="_blank"
              class="px-5 py-2.5 rounded-xl bg-gradient-to-r from-sky-600 to-blue-600 hover:from-sky-500 hover:to-blue-500 text-white font-bold text-xs shadow-lg shadow-sky-950/60 flex items-center space-x-2 transition"
            >
              <i data-lucide="external-link" class="w-4 h-4"></i>
              <span>${actionLabel}</span>
            </a>
          ` : ''}
          <button
            onclick="rerunCurrentScanner()"
            class="px-5 py-2.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 hover:text-white font-semibold text-xs border border-slate-700 flex items-center space-x-2 transition cursor-pointer"
          >
            <i data-lucide="refresh-cw" class="w-4 h-4"></i>
            <span>Retry Scan</span>
          </button>
          <button
            onclick="showHomeView()"
            class="px-4 py-2.5 rounded-xl bg-slate-800/60 hover:bg-slate-700/80 text-slate-400 hover:text-slate-200 font-semibold text-xs border border-transparent transition cursor-pointer"
          >
            <span>Back to Scanners</span>
          </button>
        </div>
      </div>
    `;
    errContainer.classList.remove("hidden");
  }

  // Update Dhan Status Badge in Header
  const badge = document.getElementById("dhan-status-badge");
  if (badge) {
    if (errType === "DATA_API_UNSUBSCRIBED" || (errMsg && errMsg.includes("DH-902"))) {
      badge.innerHTML = `
        <span class="w-2 h-2 rounded-full bg-amber-400 animate-pulse"></span>
        <span class="text-amber-300 text-xs font-semibold">⚠️ Data API Inactive (DH-902)</span>
      `;
    } else if (errType === "AUTH_ERROR" || (errMsg && errMsg.includes("DH-901"))) {
      badge.innerHTML = `
        <span class="w-2 h-2 rounded-full bg-red-400 animate-pulse"></span>
        <span class="text-red-400 text-xs font-semibold">⚠️ Token Expired (DH-901)</span>
      `;
    }
  }

  initLucide();
}

function rerunCurrentScanner() {
  if (currentReport && currentReport.scanner_id) {
    const univSelect = document.getElementById("results-select-universe");
    const tfSelect = document.getElementById("results-select-timeframe");
    const updatedParams = { ...(currentReport._lastParams || {}) };
    if (univSelect && univSelect.value) updatedParams.universe = univSelect.value;
    if (tfSelect && tfSelect.value) updatedParams.timeframe = tfSelect.value;
    runScanner(currentReport.scanner_id, updatedParams);
  } else if (selectedScannerId) {
    runScanner(selectedScannerId);
  }
}
window.rerunCurrentScanner = rerunCurrentScanner;
window.showHomeView = showHomeView;

function getItemLevelDesc(r, report) {
  if (!r) return "";

  // Dedicated handling for ST-14 scanner (Only Bullish CE Trigger or Watchlist Setup)
  if (report && (report.scanner_id === "st14_bullish_ce" || report.scanner_id === "st14_scanner")) {
    if (r.status === "QUALIFIED" || r.is_at_support || r.matched) {
      return "Bullish CE Trigger";
    }
    return "Watchlist Setup";
  }

  // Dedicated handling for Head & Shoulders scanner
  if (report && report.scanner_id === "head_and_shoulders") {
    if (r.support_desc) return r.support_desc;
    if (r.pattern && r.pattern.pattern_type) {
      const pType = r.pattern.pattern_type === "REGULAR_HS" ? "🔴 Bearish H&S" : "🟢 Bullish Inv H&S";
      const pStat = r.pattern.status === "CONFIRMED" ? "Confirmed" : "Forming";
      return `${pType} (${pStat})`;
    }
    return "Head & Shoulders";
  }

  // Dedicated handling for FVG + 0.618 Fib scanner
  if (report && (report.scanner_id === "fvg_fib_0618" || report.scanner_id === "fvg_fibonacci")) {
    if (r.support_desc) return r.support_desc;
    if (r.setup && r.setup.fvg) {
      const dir = r.setup.fvg.fvg_type === "BULLISH_FVG" ? "⚡ Bullish FVG + 0.618" : "⚡ Bearish FVG + 0.618";
      const stat = r.setup.is_at_confluence ? "Pullback Confirmed" : "Testing Level";
      return `${dir} (${stat})`;
    }
    return "⚡ FVG + 0.618 Fib";
  }

  // Dedicated handling for VCP Contraction scanner
  if (report && (report.scanner_id === "vcp_contraction" || report.scanner_id === "vcp_scanner")) {
    if (r.support_desc) return r.support_desc;
    if (r.setup) {
      const cCount = r.setup.contractions_count || 3;
      const stat = r.setup.status === "BREAKOUT_ACTIVE" ? "Breakout Active" : r.setup.status === "PRIMED_TIGHT" ? "Primed" : "Forming";
      return `⚡ ${cCount}T VCP (${stat})`;
    }
    return "⚡ VCP Contraction";
  }

  // 1. Extract raw level description from whichever field is populated by the backend search
  let raw =
    r.support_desc ||
    (r.nearest_support && r.nearest_support.description) ||
    r.setup_type ||
    r.scan_category ||
    r.ath_class ||
    r.block_type ||
    (r.nearest_order_block && r.nearest_order_block.block_type) ||
    r.nearest_ema_name ||
    r.support_type ||
    "";

  if (typeof raw !== "string") raw = String(raw || "");
  raw = raw.trim();

  if (!raw || raw === "N/A" || raw === "NONE" || raw === "null" || raw === "undefined") {
    return "Key Level";
  }

  // 2. Clean out stock-specific price/bounce tags in parentheses e.g. "(₹1013.90)", "(4 Bounces | ₹2653-₹2711)"
  let clean = raw
    .replace(/\s*\([^)]*₹[^)]*\)/g, "")
    .replace(/\s*\([^)]*bounces?[^)]*\)/gi, "")
    .replace(/\s*\([^)]*rejections?[^)]*\)/gi, "")
    .replace(/\s*@\s*₹?[0-9.,]+/g, "")
    .trim();

  // If cleaning resulted in empty string, fallback to original without parentheses
  if (!clean) {
    clean = raw.replace(/[()]/g, "").trim() || raw;
  }

  // 3. Format enum/raw identifiers nicely if applicable
  if (clean === "BULLISH_DEMAND" || clean === "DEMAND") clean = "Demand OB (Bullish)";
  else if (clean === "BEARISH_SUPPLY" || clean === "SUPPLY") clean = "Supply OB (Bearish)";

  return clean;
}

function renderLevelFilterDropdown(report) {
  const container = document.getElementById("container-level-filter");
  const select = document.getElementById("table-level-filter");
  if (!container || !select || !report) return;

  container.classList.remove("hidden");
  container.classList.add("flex");

  // Collect all distinct Level Description values across all scanned stocks in report.results
  const allResults = report.results || [];
  const currentValue = filterState.selectedLevelDropdown || "ALL";

  const levelCounts = {};
  allResults.forEach((r) => {
    const desc = getItemLevelDesc(r, report);
    if (desc && desc !== "N/A") {
      levelCounts[desc] = (levelCounts[desc] || 0) + 1;
    }
  });

  const uniqueLevels = Object.keys(levelCounts).sort((a, b) => levelCounts[b] - levelCounts[a]);

  let optionsHtml = `<option value="ALL" ${currentValue === "ALL" ? "selected" : ""}>🎯 All Levels (${allResults.length})</option>`;
  uniqueLevels.forEach((lvl) => {
    const count = levelCounts[lvl];
    const isSelected = currentValue === lvl ? "selected" : "";
    optionsHtml += `<option value="${lvl.replace(/"/g, "&quot;")}" ${isSelected}>${lvl} (${count})</option>`;
  });

  select.innerHTML = optionsHtml;
  initLucide();
}

function renderSignalFilterDropdown(report) {
  const container = document.getElementById("container-signal-filter");
  const select = document.getElementById("table-signal-filter");
  if (!container || !select || !report) return;

  container.classList.remove("hidden");
  container.classList.add("flex");

  const allResults = report.results || [];
  const scannerId = report.scanner_id;
  const currentValue = filterState.selectedSignalDropdown || "ALL";

  let optionsHtml = `<option value="ALL" ${currentValue === "ALL" ? "selected" : ""}>⚡ All Signals (${allResults.length})</option>`;

  if (scannerId === "nifty50_rsi") {
    const oversoldVal =
      report._lastParams && report._lastParams.oversold_threshold !== undefined
        ? parseFloat(report._lastParams.oversold_threshold)
        : 38.0;
    const overboughtVal =
      report._lastParams && report._lastParams.overbought_threshold !== undefined
        ? parseFloat(report._lastParams.overbought_threshold)
        : 68.0;

    const oversoldCount = allResults.filter(
      (r) => r.rsi !== null && r.rsi !== undefined && r.rsi <= oversoldVal
    ).length;
    const overboughtCount = allResults.filter(
      (r) => r.rsi !== null && r.rsi !== undefined && r.rsi >= overboughtVal
    ).length;
    const neutralCount = allResults.filter(
      (r) =>
        r.rsi !== null &&
        r.rsi !== undefined &&
        r.rsi > oversoldVal &&
        r.rsi < overboughtVal
    ).length;

    optionsHtml += `<option value="RSI_OVERSOLD" ${currentValue === "RSI_OVERSOLD" ? "selected" : ""}>❄️ Oversold (RSI ≤ ${oversoldVal}) (${oversoldCount})</option>`;
    optionsHtml += `<option value="RSI_OVERBOUGHT" ${currentValue === "RSI_OVERBOUGHT" ? "selected" : ""}>🔥 Overbought (RSI ≥ ${overboughtVal}) (${overboughtCount})</option>`;
    optionsHtml += `<option value="RSI_NEUTRAL" ${currentValue === "RSI_NEUTRAL" ? "selected" : ""}>⚖️ Neutral (${oversoldVal} - ${overboughtVal}) (${neutralCount})</option>`;
  } else {
    // Collect all distinct candle_signal values from allResults
    const signalCounts = {};
    allResults.forEach((r) => {
      const sig = (r.candle_signal || "Standard").trim();
      if (sig) {
        signalCounts[sig] = (signalCounts[sig] || 0) + 1;
      }
    });

    const uniqueSignals = Object.keys(signalCounts).sort((a, b) => signalCounts[b] - signalCounts[a]);

    uniqueSignals.forEach((sig) => {
      const count = signalCounts[sig];
      const isSelected = currentValue === sig ? "selected" : "";
      optionsHtml += `<option value="${sig.replace(/"/g, "&quot;")}" ${isSelected}>${sig} (${count})</option>`;
    });
  }

  select.innerHTML = optionsHtml;
  initLucide();
}

function renderVolumeFilterDropdown(report) {
  const container = document.getElementById("container-volume-filter");
  const select = document.getElementById("table-volume-filter");
  if (!container || !select || !report) return;

  container.classList.remove("hidden");
  container.classList.add("flex");

  const allResults = report.results || [];
  const currentValue = filterState.selectedVolumeDropdown || "ALL";

  const count10M = allResults.filter((r) => (r.volume || 0) >= 10000000).length;
  const count5M = allResults.filter((r) => (r.volume || 0) >= 5000000).length;
  const count1M = allResults.filter((r) => (r.volume || 0) >= 1000000).length;
  const count500K = allResults.filter((r) => (r.volume || 0) >= 500000).length;
  const count100K = allResults.filter((r) => (r.volume || 0) >= 100000).length;
  const countLow = allResults.filter((r) => (r.volume || 0) < 100000).length;

  let optionsHtml = `<option value="ALL" ${currentValue === "ALL" ? "selected" : ""}>📊 All Volumes (${allResults.length})</option>`;
  if (count10M > 0) {
    optionsHtml += `<option value="VOL_10M" ${currentValue === "VOL_10M" ? "selected" : ""}>🚀 > 10M / 1 Cr (${count10M})</option>`;
  }
  if (count5M > 0) {
    optionsHtml += `<option value="VOL_5M" ${currentValue === "VOL_5M" ? "selected" : ""}>⚡ > 5M / 50L (${count5M})</option>`;
  }
  if (count1M > 0) {
    optionsHtml += `<option value="VOL_1M" ${currentValue === "VOL_1M" ? "selected" : ""}>📈 > 1M / 10L (${count1M})</option>`;
  }
  if (count500K > 0) {
    optionsHtml += `<option value="VOL_500K" ${currentValue === "VOL_500K" ? "selected" : ""}>🔹 > 500K / 5L (${count500K})</option>`;
  }
  if (count100K > 0) {
    optionsHtml += `<option value="VOL_100K" ${currentValue === "VOL_100K" ? "selected" : ""}>🔸 > 100K / 1L (${count100K})</option>`;
  }
  if (countLow > 0) {
    optionsHtml += `<option value="VOL_LOW" ${currentValue === "VOL_LOW" ? "selected" : ""}>🔻 < 100K (${countLow})</option>`;
  }

  select.innerHTML = optionsHtml;
  initLucide();
}

function renderReport(report) {
  document.getElementById("results-content")?.classList.remove("hidden");
  document.getElementById("btn-copy-tv")?.classList.remove("hidden");

  // Reset basic filter state
  filterState.status = (report.matched_count && report.matched_count > 0) ? "matched" : "all";
  filterState.selectedLevelDropdown = "ALL";
  filterState.selectedSignalDropdown = "ALL";
  filterState.selectedVolumeDropdown = "ALL";
  filterState.searchQuery = "";

  const searchInput = document.getElementById("table-search");
  if (searchInput) searchInput.value = "";

  // Reset status buttons styling
  const btnMatched = document.getElementById("filter-status-matched");
  const btnAll = document.getElementById("filter-status-all");
  if (filterState.status === "matched") {
    if (btnMatched) {
      btnMatched.classList.add("bg-sky-500/20", "text-sky-300", "border-sky-500/40");
      btnMatched.classList.remove("text-slate-400", "border-transparent");
    }
    if (btnAll) {
      btnAll.classList.remove("bg-sky-500/20", "text-sky-300", "border-sky-500/40");
      btnAll.classList.add("text-slate-400", "border-transparent");
    }
  } else {
    if (btnMatched) {
      btnMatched.classList.remove("bg-sky-500/20", "text-sky-300", "border-sky-500/40");
      btnMatched.classList.add("text-slate-400", "border-transparent");
    }
    if (btnAll) {
      btnAll.classList.add("bg-sky-500/20", "text-sky-300", "border-sky-500/40");
      btnAll.classList.remove("text-slate-400", "border-transparent");
    }
  }

  // Update Metric badges
  document.getElementById("metric-total").innerText = report.total_scanned;
  document.getElementById("metric-matched").innerText = report.matched_count;

  // Dynamic 3rd Metric Badge
  const thirdMetricLabel =
    document.getElementById("metric-third-label") ||
    document.querySelector("#results-content .metric-badge:nth-child(3) span");
  if (report.scanner_id === "vcp_contraction" || report.scanner_id === "vcp_scanner") {
    if (thirdMetricLabel) thirdMetricLabel.innerText = "Primed VCPs";
    const primedCount = (report.results || []).filter(
      (r) => r.is_at_support || (r.setup && (r.setup.status === "PRIMED_TIGHT" || r.setup.status === "BREAKOUT_ACTIVE"))
    ).length;
    document.getElementById("metric-reversals").innerText = primedCount;
  } else if (report.scanner_id === "fvg_fib_0618" || report.scanner_id === "fvg_fibonacci") {
    if (thirdMetricLabel) thirdMetricLabel.innerText = "Confirmed Pullbacks";
    const readyCount = (report.results || []).filter(
      (r) => r.is_at_support || r.is_pullback || (r.status === "PULLBACK_AT_618")
    ).length;
    document.getElementById("metric-reversals").innerText = readyCount;
  } else if (report.scanner_id === "head_and_shoulders") {
    if (thirdMetricLabel) thirdMetricLabel.innerText = "Confirmed Setups";
    const confirmedCount = (report.results || []).filter(
      (r) => r.is_confirmed || (r.status === "CONFIRMED") || (r.pattern && r.pattern.status === "CONFIRMED")
    ).length;
    document.getElementById("metric-reversals").innerText = confirmedCount;
  } else if (report.scanner_id === "ha_st01_rsi_reversal") {
    if (thirdMetricLabel) thirdMetricLabel.innerText = "Bullish Divergences";
    const divCount = (report.results || []).filter((r) => r.has_bullish_divergence).length;
    document.getElementById("metric-reversals").innerText = divCount;
  } else if (report.scanner_id === "ath_st08_breakout") {
    if (thirdMetricLabel) thirdMetricLabel.innerText = "A-Class (>30m)";
    const aClassCount = (report.results || []).filter(
      (r) => r.ath_class && r.ath_class.includes("A-Class")
    ).length;
    document.getElementById("metric-reversals").innerText = aClassCount;
  } else if (report.scanner_id === "st07_monthly_ha_89ema") {
    if (thirdMetricLabel) thirdMetricLabel.innerText = "Fresh Crossovers";
    const crossoverCount = (report.results || []).filter((r) => r.is_fresh_crossover).length;
    document.getElementById("metric-reversals").innerText = crossoverCount;
  } else if (report.scanner_id === "heikin_ashi_ema_pullback") {
    if (thirdMetricLabel) thirdMetricLabel.innerText = "Green HA Candles";
    const greenHaCount = (report.results || []).filter((r) => r.is_ha_green).length;
    document.getElementById("metric-reversals").innerText = greenHaCount;
  } else if (report.scanner_id === "order_block") {
    if (thirdMetricLabel) thirdMetricLabel.innerText = "Demand Zones";
    const demandCount = (report.results || []).filter((r) => r.block_type === "BULLISH_DEMAND").length;
    document.getElementById("metric-reversals").innerText = demandCount;
  } else if (report.scanner_id === "nifty50_rsi") {
    if (thirdMetricLabel) thirdMetricLabel.innerText = "Oversold Stocks";
    const oversoldVal =
      report._lastParams && report._lastParams.oversold_threshold !== undefined
        ? parseFloat(report._lastParams.oversold_threshold)
        : 38.0;
    const oversoldCount = (report.results || []).filter(
      (r) => r.rsi !== null && r.rsi <= oversoldVal
    ).length;
    document.getElementById("metric-reversals").innerText = oversoldCount;
  } else if (report.scanner_id === "nifty50_resistance") {
    if (thirdMetricLabel) thirdMetricLabel.innerText = "At Resistance";
    document.getElementById("metric-reversals").innerText = report.matched_count;
  } else {
    if (thirdMetricLabel) thirdMetricLabel.innerText = "Bullish Reversals";
    const reversalCount = (report.results || []).filter(
      (r) =>
        r.candle_signal &&
        (r.candle_signal.toLowerCase().includes("hammer") ||
          r.candle_signal.toLowerCase().includes("reversal") ||
          r.candle_signal.toLowerCase().includes("engulfing"))
    ).length;
    document.getElementById("metric-reversals").innerText = reversalCount;
  }

  const validRsis = (report.results || [])
    .map((r) => r.rsi)
    .filter((rsi) => rsi !== null && rsi !== undefined);
  const avgRsi = validRsis.length
    ? (validRsis.reduce((a, b) => a + b, 0) / validRsis.length).toFixed(1)
    : "-";
  document.getElementById("metric-avg-rsi").innerText = avgRsi;

  document.getElementById("scan-time-badge").innerText = `Scanned at ${new Date(
    report.timestamp
  ).toLocaleTimeString()}`;

  renderLevelFilterDropdown(report);
  renderSignalFilterDropdown(report);
  renderVolumeFilterDropdown(report);
  applyFiltersAndRender();
}

function applyFiltersAndRender() {
  if (!currentReport || !currentReport.results) return;

  let items = [...currentReport.results];

  // 1. Match Status & Core Strategy Filter
  if (filterState.status === "matched") {
    items = items.filter(
      (r) =>
        r.is_at_support ||
        r.is_pullback ||
        r.has_pattern ||
        r.matched ||
        r.is_confirmed ||
        (r.status === "CONFIRMED") ||
        (r.pattern && r.pattern.status === "CONFIRMED")
    );
  }

  // 2. Key Level / Setup Description Dropdown Filter
  if (filterState.selectedLevelDropdown && filterState.selectedLevelDropdown !== "ALL") {
    const selectedLvl = filterState.selectedLevelDropdown;
    items = items.filter((r) => {
      const desc = getItemLevelDesc(r, currentReport);
      return desc === selectedLvl;
    });
  }

  // 3. Candlestick / Dynamic Signal Dropdown Filter
  if (filterState.selectedSignalDropdown && filterState.selectedSignalDropdown !== "ALL") {
    if (currentReport && currentReport.scanner_id === "nifty50_rsi") {
      const oversoldVal =
        currentReport._lastParams && currentReport._lastParams.oversold_threshold !== undefined
          ? parseFloat(currentReport._lastParams.oversold_threshold)
          : 38.0;
      const overboughtVal =
        currentReport._lastParams && currentReport._lastParams.overbought_threshold !== undefined
          ? parseFloat(currentReport._lastParams.overbought_threshold)
          : 68.0;

      if (filterState.selectedSignalDropdown === "RSI_OVERSOLD") {
        items = items.filter((r) => r.rsi !== null && r.rsi !== undefined && r.rsi <= oversoldVal);
      } else if (filterState.selectedSignalDropdown === "RSI_OVERBOUGHT") {
        items = items.filter((r) => r.rsi !== null && r.rsi !== undefined && r.rsi >= overboughtVal);
      } else if (filterState.selectedSignalDropdown === "RSI_NEUTRAL") {
        items = items.filter(
          (r) =>
            r.rsi !== null &&
            r.rsi !== undefined &&
            r.rsi > oversoldVal &&
            r.rsi < overboughtVal
        );
      }
    } else {
      const selected = filterState.selectedSignalDropdown;
      items = items.filter((r) => {
        const sig = (r.candle_signal || "Standard").trim();
        return sig === selected;
      });
    }
  }

  // 4. Volume Dropdown Filter
  if (filterState.selectedVolumeDropdown && filterState.selectedVolumeDropdown !== "ALL") {
    const vFilter = filterState.selectedVolumeDropdown;
    if (vFilter === "VOL_10M") {
      items = items.filter((r) => (r.volume || 0) >= 10000000);
    } else if (vFilter === "VOL_5M") {
      items = items.filter((r) => (r.volume || 0) >= 5000000);
    } else if (vFilter === "VOL_1M") {
      items = items.filter((r) => (r.volume || 0) >= 1000000);
    } else if (vFilter === "VOL_500K") {
      items = items.filter((r) => (r.volume || 0) >= 500000);
    } else if (vFilter === "VOL_100K") {
      items = items.filter((r) => (r.volume || 0) >= 100000);
    } else if (vFilter === "VOL_LOW") {
      items = items.filter((r) => (r.volume || 0) < 100000);
    }
  }

  // 5. Global Search Query
  if (filterState.searchQuery.trim()) {
    const q = filterState.searchQuery.toLowerCase().trim();
    items = items.filter(
      (r) =>
        r.symbol.toLowerCase().includes(q) ||
        getItemLevelDesc(r, currentReport).toLowerCase().includes(q) ||
        (r.support_desc && r.support_desc.toLowerCase().includes(q)) ||
        (r.candle_signal && r.candle_signal.toLowerCase().includes(q))
    );
  }

  // 6. Sorting
  items.sort((a, b) => {
    let valA, valB;
    if (filterState.sortColumn === "support_desc" || filterState.sortColumn === "level_desc") {
      valA = getItemLevelDesc(a, currentReport);
      valB = getItemLevelDesc(b, currentReport);
    } else if (filterState.sortColumn === "rsi") {
      valA = a.rsi ?? a.hourly_rsi ?? a.daily_rsi ?? (filterState.sortAsc ? 999999 : -999999);
      valB = b.rsi ?? b.hourly_rsi ?? b.daily_rsi ?? (filterState.sortAsc ? 999999 : -999999);
    } else if (filterState.sortColumn === "volume") {
      valA = a.volume ?? a.hourly_volume ?? a.daily_volume ?? 0;
      valB = b.volume ?? b.hourly_volume ?? b.daily_volume ?? 0;
    } else {
      valA = a[filterState.sortColumn];
      valB = b[filterState.sortColumn];
    }
    if (valA === null || valA === undefined) valA = 999999;
    if (valB === null || valB === undefined) valB = 999999;

    if (typeof valA === "string") {
      return filterState.sortAsc ? valA.localeCompare(valB) : valB.localeCompare(valA);
    }
    return filterState.sortAsc ? valA - valB : valB - valA;
  });

  currentlyDisplayedItems = items;
  renderTable(items);
}

function formatVolume(val) {
  if (val === null || val === undefined) return "-";
  const num = Number(val);
  if (isNaN(num) || num <= 0) return "-";
  if (num >= 10000000) {
    return (num / 10000000).toFixed(2) + " Cr";
  }
  if (num >= 1000000) {
    return (num / 1000000).toFixed(2) + "M";
  }
  if (num >= 1000) {
    return (num / 1000).toFixed(1) + "K";
  }
  return num.toLocaleString("en-IN");
}

function renderTable(items) {
  const tbody = document.getElementById("results-tbody");
  document.getElementById("results-count-badge").innerText = `${items.length} of ${
    currentReport ? currentReport.total_scanned : 50
  } stocks`;

  const isSt14Scanner = currentReport && (currentReport.scanner_id === "st14_bullish_ce" || currentReport.scanner_id === "st14_scanner");
  const isHsScanner = currentReport && currentReport.scanner_id === "head_and_shoulders";
  const isFvgFibScanner = currentReport && (currentReport.scanner_id === "fvg_fib_0618" || currentReport.scanner_id === "fvg_fibonacci");
  const isVcpScanner = currentReport && (currentReport.scanner_id === "vcp_contraction" || currentReport.scanner_id === "vcp_scanner");
  const thKeyLevel = document.getElementById("th-col-key-level-text");
  const thDist = document.getElementById("th-col-distance-text");
  const thDesc = document.getElementById("th-col-desc-text");
  const thRsi = document.getElementById("th-col-rsi-text");

  if (thKeyLevel) thKeyLevel.innerText = isSt14Scanner ? "5H Breakout (₹)" : isHsScanner ? "Neckline (₹)" : isFvgFibScanner ? "0.618 Fib / FVG (₹)" : isVcpScanner ? "Pivot Trigger (₹)" : "Key Level (₹)";
  if (thDist) thDist.innerText = isSt14Scanner ? "5H Dist (%)" : isHsScanner ? "Neckline Dist (%)" : isFvgFibScanner ? "0.618 Dist (%)" : isVcpScanner ? "Pivot Dist (%)" : "Distance (%)";
  if (thDesc) thDesc.innerText = isSt14Scanner ? "Setup Status" : isHsScanner ? "Pattern & Status" : isFvgFibScanner ? "Imbalance & Confluence" : isVcpScanner ? "Contraction Sequence" : "Level Description";
  if (thRsi) thRsi.innerText = isSt14Scanner ? "Intraday VWAP" : "RSI (14)";

  if (items.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="8" class="py-16 text-center text-slate-400">
          <div class="inline-flex p-3 rounded-full bg-slate-800 text-slate-400 mb-2">
            <i data-lucide="filter-x" class="w-5 h-5"></i>
          </div>
          <div class="text-sm font-semibold text-slate-300">No stocks match the selected criteria</div>
          <p class="text-xs text-slate-500 mt-1">Try selecting "All Candidates" or switching to "All Stocks".</p>
        </td>
      </tr>
    `;
    initLucide();
    return;
  }

  tbody.innerHTML = items
    .map((r) => {
      const distVal = (r.distance_pct !== undefined && r.distance_pct !== null && !isNaN(r.distance_pct)) ? Number(r.distance_pct) : 0.0;
      const distFormatted = (distVal >= 0 ? "+" : "") + distVal.toFixed(2) + "%";
      const distColor = r.is_at_support
        ? "text-emerald-400 font-semibold"
        : Math.abs(distVal) <= 3.0
        ? "text-amber-400"
        : "text-slate-400";

      let rsiBadge = "-";
      const rsiRaw =
        r.rsi !== null && r.rsi !== undefined && !isNaN(r.rsi)
          ? r.rsi
          : r.hourly_rsi !== null && r.hourly_rsi !== undefined && !isNaN(r.hourly_rsi)
          ? r.hourly_rsi
          : r.daily_rsi;

      if (rsiRaw !== null && rsiRaw !== undefined && !isNaN(rsiRaw) && Number(rsiRaw) > 0) {
        const rsiVal = Number(rsiRaw);
        let rsiColor = "text-slate-300";
        if (rsiVal <= 38)
          rsiColor = "text-emerald-400 font-bold bg-emerald-950/50 px-2 py-0.5 rounded border border-emerald-800/40";
        else if (rsiVal >= 60 && rsiVal < 70)
          rsiColor = "text-emerald-300 font-semibold bg-emerald-950/30 px-2 py-0.5 rounded border border-emerald-800/30";
        else if (rsiVal >= 70)
          rsiColor = "text-rose-400 font-bold bg-rose-950/50 px-2 py-0.5 rounded border border-rose-800/40";
        rsiBadge = `<span class="${rsiColor}">${rsiVal.toFixed(1)}</span>`;
      }

      const sigStr = r.candle_signal || "";
      const isBearishSignal =
        sigStr.includes("🔴") ||
        sigStr.includes("Shooting Star") ||
        sigStr.includes("Bearish") ||
        sigStr.includes("Red") ||
        (sigStr.includes("Rejection") && !sigStr.includes("🟢"));

      const isBullish =
        sigStr.includes("Hammer") ||
        sigStr.includes("Bullish") ||
        sigStr.includes("Green") ||
        sigStr.includes("🟢") ||
        sigStr.includes("TRIGGER");

      const isFreshFirstGreen = r.is_first_green || sigStr.includes("1st Green");
      const isFreshCrossover = r.is_fresh_crossover || sigStr.includes("Fresh Crossover");
      const isAccumulation = r.is_accumulation_pullback || sigStr.includes("Accumulation Pullback");
      const isBullishCeTrigger = sigStr.includes("BULLISH CE TRIGGER");

      let signalBadge;
      if (isBullishCeTrigger) {
        signalBadge = `<span class="inline-flex items-center space-x-1 text-emerald-300 font-bold bg-emerald-950/80 border border-emerald-400/80 px-2.5 py-1 rounded-lg text-xs shadow-md shadow-emerald-950">
             <span>${sigStr}</span>
           </span>`;
      } else if (isBearishSignal) {
        signalBadge = `<span class="inline-flex items-center space-x-1 text-rose-300 font-bold bg-rose-950/70 border border-rose-500/60 px-2.5 py-1 rounded-lg text-xs shadow-sm shadow-rose-950">
             <span>${sigStr}</span>
           </span>`;
      } else if (isFreshCrossover) {
        signalBadge = `<span class="inline-flex items-center space-x-1 text-cyan-300 font-bold bg-cyan-950/70 border border-cyan-500/60 px-2.5 py-1 rounded-lg text-xs shadow-sm shadow-cyan-950">
             <span>${sigStr}</span>
           </span>`;
      } else if (isAccumulation) {
        signalBadge = `<span class="inline-flex items-center space-x-1 text-purple-300 font-bold bg-purple-950/70 border border-purple-500/60 px-2.5 py-1 rounded-lg text-xs shadow-sm shadow-purple-950">
             <span>${sigStr}</span>
           </span>`;
      } else if (isFreshFirstGreen) {
        signalBadge = `<span class="inline-flex items-center space-x-1 text-emerald-300 font-bold bg-emerald-950/70 border border-emerald-500/60 px-2.5 py-1 rounded-lg text-xs shadow-sm shadow-emerald-950">
             <span>${sigStr}</span>
           </span>`;
      } else if (isBullish) {
        signalBadge = `<span class="inline-flex items-center space-x-1 text-emerald-300 font-medium bg-emerald-950/30 border border-emerald-800/30 px-2 py-0.5 rounded-lg text-xs">
             <span>${sigStr}</span>
           </span>`;
      } else {
        signalBadge = `<span class="text-slate-400 text-xs">${sigStr || "-"}</span>`;
      }

      const isSt07 = currentReport && currentReport.scanner_id === "st07_monthly_ha_89ema";
      const isAth08 = currentReport && currentReport.scanner_id === "ath_st08_breakout";
      const isHaSt01 = currentReport && currentReport.scanner_id === "ha_st01_rsi_reversal";
      const isSt14 = currentReport && (currentReport.scanner_id === "st14_bullish_ce" || currentReport.scanner_id === "st14_scanner");
      const isHs = currentReport && currentReport.scanner_id === "head_and_shoulders";
      const isFvgFib = currentReport && (currentReport.scanner_id === "fvg_fib_0618" || currentReport.scanner_id === "fvg_fibonacci");
      const isVcp = currentReport && (currentReport.scanner_id === "vcp_contraction" || currentReport.scanner_id === "vcp_scanner");
      const keyLevelPrice = isAth08
        ? r.prior_ath_price
        : isHaSt01
        ? r.stop_loss
        : isSt07
        ? r.ema_89
        : isSt14
        ? (r.five_hour_high || r.support_price)
        : isHs
        ? (r.neckline || (r.pattern ? r.pattern.neckline_price : null) || r.support_price)
        : isFvgFib
        ? (r.confluence_price || (r.setup ? r.setup.confluence_price : null) || r.support_price)
        : isVcp
        ? (r.setup ? r.setup.pivot_level : (r.pivot_level || r.support_price))
        : (r.support_price !== undefined ? r.support_price : (r.nearest_support ? r.nearest_support.price : null));
      const keyLevelDesc = getItemLevelDesc(r, currentReport);
      const hoverTitle = isAth08
        ? `Trigger Entry: ₹${r.trigger_entry_price} (+1%) | 30W SMA: ₹${r.weekly_30_sma} | ATH Date: ${r.prior_ath_date} | Exp: ${r.expansion_ratio}x`
        : isHaSt01
        ? `Entry Trigger: ₹${r.entry_trigger_price} (+0.2%) | SL: ₹${r.stop_loss} | Risk: ₹${r.risk_per_share} | 1R Target: ₹${r.target_1r} | 2R Target: ₹${r.target_2r} | HA Close: ₹${r.ha_close}`
        : isSt07
        ? `Buy Trigger: ₹${r.buy_trigger_price} | SL: ₹${r.stop_loss} | 21 EMA: ₹${r.ema_21} | HA Close: ₹${r.ha_close}`
        : isSt14
        ? `5H Breakout High: ₹${r.five_hour_high} | 5D High: ₹${r.five_day_high} | VWAP: ₹${r.vwap} (${r.vwap_dist_pct > 0 ? '+' : ''}${r.vwap_dist_pct}%, ${r.vwap_angle_deg || 0}°) | 1H 20 EMA: ₹${r.hourly_ema20} | Daily 20 EMA: ₹${r.daily_ema20} | [${r.timing_message || ''}]`
        : isHs
        ? `Neckline: ₹${r.neckline || (r.pattern ? r.pattern.neckline_price : 0)} | T1: ₹${r.target_1 || (r.pattern ? r.pattern.target_1 : 0)} | SL: ₹${r.stop_loss || (r.pattern ? r.pattern.stop_loss : 0)} | Head: ₹${r.head_price || (r.pattern ? r.pattern.head.price : 0)} | Left: ₹${r.left_shoulder_price || (r.pattern ? r.pattern.left_shoulder.price : 0)} | Right: ₹${r.right_shoulder_price || (r.pattern ? r.pattern.right_shoulder.price : 0)}`
        : isFvgFib
        ? `0.618 Fib: ₹${r.confluence_price || (r.setup ? r.setup.confluence_price : 0)} | FVG: ${r.setup ? r.setup.fvg_overlap_desc : ''} | T1: ₹${r.target_1 || 0} | T2: ₹${r.target_2 || (r.setup ? r.setup.target_2 : 0)} | SL: ₹${r.stop_loss || 0} | R:R 1:${r.risk_reward_ratio || (r.setup ? r.setup.risk_reward_ratio : 0)}`
        : isVcp && r.setup
        ? `Pivot: ₹${r.setup.pivot_level} | SL: ₹${r.setup.stop_loss} (${r.setup.risk_pct}%) | VDU: ${r.setup.vdu_ratio}x | T1: ₹${r.setup.target_1} | T2: ₹${r.setup.target_2} | R:R 1:${r.setup.risk_reward_ratio} | [${r.setup.schematic}]`
        : (r.support_desc || "");

      let levelBadgeColor = "text-slate-300 bg-slate-800/80 border-slate-700";
      const desc = keyLevelDesc;
      if (desc.includes("Bearish FVG") || desc.includes("Bearish H&S") || desc.includes("Supply OB") || (desc.includes("Bearish") && !desc.includes("Bullish"))) {
        levelBadgeColor = "text-rose-300 font-bold bg-rose-950/70 border-rose-500/60 shadow-sm shadow-rose-950";
      } else if (desc.includes("Bullish FVG") || desc.includes("Bullish Inv H&S") || desc.includes("Demand OB") || desc.includes("BULLISH CE") || desc.includes("Bullish") || desc.includes("Pullback Confirmed")) {
        levelBadgeColor = "text-emerald-300 font-bold bg-emerald-950/60 border-emerald-500/50 shadow-sm shadow-emerald-950";
      } else if (desc.includes("Rejection Confirmed")) {
        levelBadgeColor = "text-rose-300 font-bold bg-rose-950/70 border-rose-500/60 shadow-sm shadow-rose-950";
      } else if (desc.includes("Testing Level") || desc.includes("Watchlist")) {
        levelBadgeColor = "text-amber-300 font-bold bg-amber-950/60 border-amber-500/50 shadow-sm shadow-amber-950";
      } else if (desc.includes("Divergence + Oversold")) {
        levelBadgeColor = "text-purple-300 font-bold bg-purple-950/60 border-purple-500/50 shadow-sm shadow-purple-950";
      } else if (desc.includes("Bullish Divergence")) {
        levelBadgeColor = "text-emerald-300 font-bold bg-emerald-950/60 border-emerald-500/50 shadow-sm shadow-emerald-950";
      } else if (desc.includes("Oversold Flip")) {
        levelBadgeColor = "text-cyan-300 font-bold bg-cyan-950/60 border-cyan-500/50 shadow-sm shadow-cyan-950";
      } else if (desc.includes("A-Class")) {
        levelBadgeColor = "text-amber-300 font-bold bg-amber-950/60 border-amber-500/50 shadow-sm shadow-amber-950";
      } else if (desc.includes("B-Class")) {
        levelBadgeColor = "text-cyan-300 bg-cyan-950/40 border-cyan-800/40";
      } else if (desc.includes("Confluence")) {
        levelBadgeColor = "text-amber-300 font-bold bg-amber-950/60 border-amber-500/50 shadow-sm shadow-amber-950";
      } else if (desc.includes("Major Support Zone")) {
        levelBadgeColor = "text-emerald-300 font-bold bg-emerald-950/60 border-emerald-500/50 shadow-sm shadow-emerald-950";
      } else if (desc.includes("Major Resistance Zone")) {
        levelBadgeColor = "text-rose-300 font-bold bg-rose-950/60 border-rose-500/50 shadow-sm shadow-rose-950";
      } else if (desc.includes("Fresh Crossover") || desc.includes("89 EMA")) {
        levelBadgeColor = "text-cyan-300 bg-cyan-950/40 border-cyan-800/40";
      } else if (desc.includes("Accumulation")) {
        levelBadgeColor = "text-purple-300 bg-purple-950/40 border-purple-800/40";
      } else if (desc.includes("Demand OB")) {
        levelBadgeColor = "text-emerald-300 bg-emerald-950/40 border-emerald-800/40";
      } else if (desc.includes("Supply OB")) {
        levelBadgeColor = "text-rose-300 bg-rose-950/40 border-rose-800/40";
      } else if (desc.includes("20 EMA")) {
        levelBadgeColor = "text-sky-300 bg-sky-950/40 border-sky-800/40";
      } else if (desc.includes("50 EMA")) {
        levelBadgeColor = "text-emerald-300 bg-emerald-950/40 border-emerald-800/40";
      } else if (desc.includes("100 EMA")) {
        levelBadgeColor = "text-indigo-300 bg-indigo-950/40 border-indigo-800/40";
      } else if (desc.includes("200 EMA")) {
        levelBadgeColor = "text-amber-300 bg-amber-950/40 border-amber-800/40";
      } else if (desc.includes("Swing Low")) {
        levelBadgeColor = "text-cyan-300 bg-cyan-950/40 border-cyan-800/40";
      } else if (desc.includes("Swing High")) {
        levelBadgeColor = "text-rose-300 bg-rose-950/40 border-rose-800/40";
      } else if (desc.includes("Pivot")) {
        levelBadgeColor = "text-purple-300 bg-purple-950/40 border-purple-800/40";
      }

      const volRaw = (r.volume !== null && r.volume !== undefined && r.volume > 0)
        ? r.volume
        : (r.hourly_volume || r.daily_volume || 0);

      const vwapBadge = isSt14
        ? `<span class="px-2 py-0.5 rounded-lg bg-sky-950/60 border border-sky-500/40 text-sky-300 font-mono font-semibold" title="VWAP: ₹${r.vwap} | Dist: ${r.vwap_dist_pct}% | Angle: ${r.vwap_angle_deg}°">₹${Number(r.vwap || 0).toLocaleString('en-IN', {minimumFractionDigits: 2})} <span class="text-[10px] text-sky-400 font-bold ml-1">${r.vwap_angle_deg || 0}° ${r.is_vwap_rising ? '↗' : '↘'}</span></span>`
        : rsiBadge;

      return `
      <tr class="border-b border-slate-800/80 hover:bg-slate-800/40 transition">
        <td class="py-3.5 px-4">
          <div class="flex items-center space-x-2">
            <a
              href="https://in.tradingview.com/chart/?symbol=NSE:${r.symbol}"
              target="_blank"
              class="font-bold text-white hover:text-sky-400 flex items-center space-x-1.5 transition group"
              title="Open ${r.symbol} on TradingView"
            >
              <span>${r.symbol}</span>
              <i data-lucide="external-link" class="w-3.5 h-3.5 text-slate-500 group-hover:text-sky-400 transition"></i>
            </a>
            <a
              href="https://tv.dhan.co/?symbol=NSE:${encodeURIComponent(r.symbol)}"
              target="_blank"
              class="p-0.5 px-1.5 rounded bg-[#00b060]/15 hover:bg-[#00b060]/35 text-[#00e676] border border-[#00b060]/40 transition text-[10px] font-bold"
              title="Open ${r.symbol} on Dhan TradingView (tv.dhan.co)"
            >
              Dhan
            </a>
          </div>
        </td>
        <td class="py-3.5 px-4 font-mono font-medium text-slate-200">₹${Number(r.ltp).toLocaleString(
          "en-IN",
          { minimumFractionDigits: 2 }
        )}</td>
        <td class="py-3.5 px-4 font-mono text-slate-300">${
          keyLevelPrice !== null && keyLevelPrice !== undefined
            ? "₹" + Number(keyLevelPrice).toLocaleString("en-IN", { minimumFractionDigits: 2 })
            : "N/A"
        }</td>
        <td class="py-3.5 px-4 font-mono ${distColor}">${distFormatted}</td>
        <td class="py-3.5 px-4">
          <span class="inline-block text-xs px-2 py-0.5 rounded-lg border ${levelBadgeColor}" title="${hoverTitle}">
            ${keyLevelDesc}
          </span>
        </td>
        <td class="py-3.5 px-4 font-mono text-xs text-slate-300 font-medium" title="${Number(volRaw || 0).toLocaleString('en-IN')} shares">
          ${formatVolume(volRaw)}
        </td>
        <td class="py-3.5 px-4 font-mono text-xs">${vwapBadge}</td>
        <td class="py-3.5 px-4 text-xs">${signalBadge}</td>
      </tr>
    `;
    })
    .join("");

  initLucide();
}

function setupEventListeners() {
  // Home Strategy Search
  const homeSearchInput = document.getElementById("home-scanner-search");
  if (homeSearchInput) {
    homeSearchInput.addEventListener("input", (e) => {
      homeSearchQuery = e.target.value;
      renderScannerNavList();
    });
  }

  // Home Category Tabs
  document.querySelectorAll(".home-cat-tab").forEach((tab) => {
    tab.addEventListener("click", (e) => {
      document.querySelectorAll(".home-cat-tab").forEach((t) => {
        t.classList.remove("bg-sky-500/20", "text-sky-300", "border-sky-500/40");
        t.classList.add("bg-slate-800/60", "text-slate-400", "border-transparent");
      });
      const target = e.currentTarget;
      target.classList.add("bg-sky-500/20", "text-sky-300", "border-sky-500/40");
      target.classList.remove("bg-slate-800/60", "text-slate-400", "border-transparent");

      selectedCategoryFilter = target.dataset.catFilter;
      renderScannerNavList();
    });
  });

  // Navigation
  const btnBackHome = document.getElementById("btn-back-home");
  if (btnBackHome) btnBackHome.addEventListener("click", showHomeView);

  const btnRerun = document.getElementById("btn-rerun");
  if (btnRerun) {
    btnRerun.addEventListener("click", () => {
      if (currentReport && currentReport.scanner_id) {
        const univSelect = document.getElementById("results-select-universe");
        const tfSelect = document.getElementById("results-select-timeframe");
        const updatedParams = { ...(currentReport._lastParams || {}) };
        if (univSelect) updatedParams.universe = univSelect.value;
        if (tfSelect) updatedParams.timeframe = tfSelect.value;
        runScanner(currentReport.scanner_id, updatedParams);
      }
    });
  }

  // Export CSV
  const btnExportCsv = document.getElementById("btn-export-csv");
  if (btnExportCsv) btnExportCsv.addEventListener("click", exportCSV);

  // Copy TradingView Watchlist
  const btnCopyTv = document.getElementById("btn-copy-tv");
  if (btnCopyTv) {
    btnCopyTv.addEventListener("click", copyTradingViewWatchlist);
  }

  // Global Search input
  const searchInput = document.getElementById("table-search");
  if (searchInput) {
    searchInput.addEventListener("input", (e) => {
      filterState.searchQuery = e.target.value;
      applyFiltersAndRender();
    });
  }

  // Signal Filter Dropdown
  const signalFilterSelect = document.getElementById("table-signal-filter");
  if (signalFilterSelect) {
    signalFilterSelect.addEventListener("change", (e) => {
      filterState.selectedSignalDropdown = e.target.value;
      applyFiltersAndRender();
    });
  }

  // Level Description Filter Dropdown
  const levelFilterSelect = document.getElementById("table-level-filter");
  if (levelFilterSelect) {
    levelFilterSelect.addEventListener("change", (e) => {
      filterState.selectedLevelDropdown = e.target.value;
      applyFiltersAndRender();
    });
  }

  // Volume Filter Dropdown
  const volumeFilterSelect = document.getElementById("table-volume-filter");
  if (volumeFilterSelect) {
    volumeFilterSelect.addEventListener("change", (e) => {
      filterState.selectedVolumeDropdown = e.target.value;
      applyFiltersAndRender();
    });
  }

  // Status Switch (Matched vs All)
  const btnStatusMatched = document.getElementById("filter-status-matched");
  if (btnStatusMatched) {
    btnStatusMatched.addEventListener("click", () => {
      filterState.status = "matched";
      btnStatusMatched.classList.add("bg-sky-500/20", "text-sky-300", "border-sky-500/40");
      btnStatusMatched.classList.remove("text-slate-400", "border-transparent");
      const btnStatusAll = document.getElementById("filter-status-all");
      if (btnStatusAll) {
        btnStatusAll.classList.remove("bg-sky-500/20", "text-sky-300", "border-sky-500/40");
        btnStatusAll.classList.add("text-slate-400", "border-transparent");
      }
      if (currentReport) {
        renderSignalFilterDropdown(currentReport);
        renderLevelFilterDropdown(currentReport);
        renderVolumeFilterDropdown(currentReport);
      }
      applyFiltersAndRender();
    });
  }

  const btnStatusAll = document.getElementById("filter-status-all");
  if (btnStatusAll) {
    btnStatusAll.addEventListener("click", () => {
      filterState.status = "all";
      btnStatusAll.classList.add("bg-sky-500/20", "text-sky-300", "border-sky-500/40");
      btnStatusAll.classList.remove("text-slate-400", "border-transparent");
      const btnStatusMatched = document.getElementById("filter-status-matched");
      if (btnStatusMatched) {
        btnStatusMatched.classList.remove("bg-sky-500/20", "text-sky-300", "border-sky-500/40");
        btnStatusMatched.classList.add("text-slate-400", "border-transparent");
      }
      if (currentReport) {
        renderSignalFilterDropdown(currentReport);
        renderLevelFilterDropdown(currentReport);
        renderVolumeFilterDropdown(currentReport);
      }
      applyFiltersAndRender();
    });
  }

  // Table Column Sort Headers
  document.querySelectorAll("th[data-sort]").forEach((th) => {
    th.addEventListener("click", (e) => {
      const col = e.currentTarget.dataset.sort;
      if (filterState.sortColumn === col) {
        filterState.sortAsc = !filterState.sortAsc;
      } else {
        filterState.sortColumn = col;
        filterState.sortAsc = true;
      }
      applyFiltersAndRender();
    });
  });
}

function showHomeView() {
  const stratTab = document.getElementById("main-tab-strategies");
  const scanTab = document.getElementById("main-tab-scanner");
  if (stratTab) { stratTab.style.display = "none"; stratTab.classList.add("hidden"); }
  if (scanTab) { scanTab.style.display = "block"; scanTab.classList.remove("hidden"); }

  const vHome = document.getElementById("view-home");
  const vResults = document.getElementById("view-results");
  const vEod = document.getElementById("view-eod-digest");
  if (vHome) { vHome.style.display = "block"; vHome.classList.remove("hidden"); }
  if (vResults) { vResults.style.display = "none"; vResults.classList.add("hidden"); }
  if (vEod) { vEod.style.display = "none"; vEod.classList.add("hidden"); }

  const btnCopyTv = document.getElementById("btn-copy-tv");
  if (btnCopyTv) btnCopyTv.classList.add("hidden");

  // Highlight top navbar tabs
  const btnStrategies = document.getElementById("nav-tab-strategies");
  const btnScanner = document.getElementById("nav-tab-scanner");
  const btnEod = document.getElementById("nav-tab-eod");
  if (btnScanner) btnScanner.className = "px-2.5 py-1 rounded-lg text-xs font-bold transition bg-indigo-600 text-white shadow-sm flex items-center gap-1.5";
  if (btnEod) btnEod.className = "px-2.5 py-1 rounded-lg text-xs font-bold transition text-gray-400 hover:text-gray-200 hover:bg-gray-800 flex items-center gap-1.5";
  if (btnStrategies) btnStrategies.className = "px-2.5 py-1 rounded-lg text-xs font-bold transition text-gray-400 hover:text-gray-200 hover:bg-gray-800 flex items-center gap-1.5";
}

function showResultsView() {
  const stratTab = document.getElementById("main-tab-strategies");
  const scanTab = document.getElementById("main-tab-scanner");
  if (stratTab) { stratTab.style.display = "none"; stratTab.classList.add("hidden"); }
  if (scanTab) { scanTab.style.display = "block"; scanTab.classList.remove("hidden"); }

  const vHome = document.getElementById("view-home");
  const vResults = document.getElementById("view-results");
  const vEod = document.getElementById("view-eod-digest");
  if (vHome) { vHome.style.display = "none"; vHome.classList.add("hidden"); }
  if (vResults) { vResults.style.display = "block"; vResults.classList.remove("hidden"); }
  if (vEod) { vEod.style.display = "none"; vEod.classList.add("hidden"); }

  const btnCopyTv = document.getElementById("btn-copy-tv");
  if (btnCopyTv) btnCopyTv.classList.remove("hidden");

  const btnStrategies = document.getElementById("nav-tab-strategies");
  const btnScanner = document.getElementById("nav-tab-scanner");
  const btnEod = document.getElementById("nav-tab-eod");
  if (btnScanner) btnScanner.className = "px-2.5 py-1 rounded-lg text-xs font-bold transition bg-indigo-600 text-white shadow-sm flex items-center gap-1.5";
  if (btnEod) btnEod.className = "px-2.5 py-1 rounded-lg text-xs font-bold transition text-gray-400 hover:text-gray-200 hover:bg-gray-800 flex items-center gap-1.5";
  if (btnStrategies) btnStrategies.className = "px-2.5 py-1 rounded-lg text-xs font-bold transition text-gray-400 hover:text-gray-200 hover:bg-gray-800 flex items-center gap-1.5";
}

function showEodDigestView() {
  const stratTab = document.getElementById("main-tab-strategies");
  const scanTab = document.getElementById("main-tab-scanner");
  if (stratTab) { stratTab.style.display = "none"; stratTab.classList.add("hidden"); }
  if (scanTab) { scanTab.style.display = "block"; scanTab.classList.remove("hidden"); }

  const vHome = document.getElementById("view-home");
  const vResults = document.getElementById("view-results");
  const vEod = document.getElementById("view-eod-digest");
  if (vHome) { vHome.style.display = "none"; vHome.classList.add("hidden"); }
  if (vResults) { vResults.style.display = "none"; vResults.classList.add("hidden"); }
  if (vEod) { vEod.style.display = "block"; vEod.classList.remove("hidden"); }

  const btnCopyTv = document.getElementById("btn-copy-tv");
  if (btnCopyTv) btnCopyTv.classList.add("hidden");

  // Highlight top navbar tabs
  const btnStrategies = document.getElementById("nav-tab-strategies");
  const btnScanner = document.getElementById("nav-tab-scanner");
  const btnEod = document.getElementById("nav-tab-eod");
  if (btnScanner) btnScanner.className = "px-2.5 py-1 rounded-lg text-xs font-bold transition text-gray-400 hover:text-gray-200 hover:bg-gray-800 flex items-center gap-1.5";
  if (btnEod) btnEod.className = "px-2.5 py-1 rounded-lg text-xs font-bold transition bg-amber-600 text-white shadow-sm flex items-center gap-1.5";
  if (btnStrategies) btnStrategies.className = "px-2.5 py-1 rounded-lg text-xs font-bold transition text-gray-400 hover:text-gray-200 hover:bg-gray-800 flex items-center gap-1.5";

  loadEodDatesAndLatest();

  fetch("/api/eod-scans/status")
    .then((r) => r.json())
    .then((status) => {
      if (status && status.is_executing) {
        startEodStatusPolling();
      }
    })
    .catch(() => {});
}

window.showHomeView = showHomeView;
window.showResultsView = showResultsView;
window.showEodDigestView = showEodDigestView;

// ==================== DAILY EOD DIGEST CONTROLLER ====================

async function loadEodDatesAndLatest(forceRefresh = false) {
  if (_isEodLoading) return;
  _isEodLoading = true;

  try {
    const dateSelect = document.getElementById("eod-select-date");

    if (forceRefresh) {
      delete _eodReportCache["latest"];
    }

    // Fetch dates and latest report in parallel
    const [datesRes, reportData] = await Promise.all([
      fetch("/api/eod-scans/dates")
        .then((r) => r.json())
        .catch((e) => {
          console.warn("Failed to load EOD dates:", e);
          return [];
        }),
      loadEodDigest("", false),
    ]);

    if (dateSelect && Array.isArray(datesRes) && datesRes.length > 0) {
      const selectedVal = dateSelect.value || datesRes[0];
      dateSelect.innerHTML = datesRes
        .map((d, i) => `<option value="${d}" ${d === selectedVal ? "selected" : ""}>${i === 0 ? `📅 Today (${d})` : `📅 ${d}`}</option>`)
        .join("");
      dateSelect.value = selectedVal;
    }
  } catch (err) {
    console.error("Failed in loadEodDatesAndLatest:", err);
  } finally {
    _isEodLoading = false;
  }
}

async function loadEodDigest(dateStr = "", showSpinner = true) {
  const kpiContainer = document.getElementById("eod-kpi-container");
  const tableBody = document.getElementById("eod-table-body");
  const confluenceGrid = document.getElementById("eod-confluence-grid");

  const cacheKey = dateStr || "latest";
  if (_eodReportCache[cacheKey]) {
    currentEodReport = _eodReportCache[cacheKey];
    renderEodDashboard();
    return currentEodReport;
  }

  if (showSpinner && kpiContainer && !currentEodReport) {
    kpiContainer.innerHTML = `
      <div class="col-span-full py-12 text-center text-slate-400 flex items-center justify-center space-x-2">
        <svg class="animate-spin h-5 w-5 text-amber-400" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" fill="none"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>
        <span class="text-xs">Loading EOD Snapshot...</span>
      </div>
    `;
  }

  try {
    const url = dateStr ? `/api/eod-scans/${dateStr}` : `/api/eod-scans/latest`;
    const res = await fetch(url);
    const data = await res.json();

    if (data.status === "no_data" || !data.date) {
      if (kpiContainer) {
        kpiContainer.innerHTML = `
          <div class="col-span-full py-2.5 px-4 bg-slate-900/60 border border-slate-800 rounded-2xl flex flex-wrap items-center justify-between gap-2.5 text-xs">
            <div class="flex items-center space-x-2 text-slate-300">
              <span class="px-2 py-0.5 rounded-lg bg-amber-500/10 border border-amber-500/30 text-amber-400 font-bold text-[11px] flex items-center gap-1 shrink-0">
                <span>🌆</span> <span>6:30 PM IST Snapshot</span>
              </span>
              <span class="text-slate-400 text-xs">Automated multi-scanner runs daily at 6:30 PM IST across 500 NSE stocks & 12 strategies.</span>
            </div>
            <div class="text-[11px] font-mono text-slate-400 flex items-center gap-1.5 shrink-0">
              <span class="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
              <span>Next Run: Today at 6:30 PM</span>
            </div>
          </div>
        `;
      }
      if (confluenceGrid) {
        confluenceGrid.innerHTML = `
          <div class="col-span-full py-4 text-center text-slate-500 text-xs font-medium">
            No confluence setups compiled for today yet.
          </div>
        `;
      }
      if (tableBody) {
        tableBody.innerHTML = `
          <tr>
            <td colspan="6" class="py-6 px-4 text-center text-slate-500 text-xs">
              No EOD watchlist entries available for today yet. Use the top toolbar to run on-demand or wait for the 6:30 PM snapshot.
            </td>
          </tr>
        `;
      }
      initLucide();
      return data;
    }

    _eodReportCache[cacheKey] = data;
    if (data.date) _eodReportCache[data.date] = data;
    currentEodReport = data;
    renderEodDashboard();
    return data;
  } catch (err) {
    console.error("Failed to fetch EOD digest:", err);
  }
}

function renderEodDashboard() {
  if (!currentEodReport) return;
  const r = currentEodReport;

  // Status subtitle
  const subtitle = document.getElementById("eod-header-subtitle");
  if (subtitle) {
    subtitle.innerText = `Automated Post-Market Snapshot for ${r.date} • ${r.universe} (${r.total_scanners_run || 12} Strategies • Executed in ${r.execution_time_seconds || 0}s)`;
  }

  // Render KPI Cards
  const kpiContainer = document.getElementById("eod-kpi-container");
  if (kpiContainer) {
    const bullishPct = r.unique_stocks_count > 0 ? Math.round((r.bullish_count / r.unique_stocks_count) * 100) : 100;
    
    // Top Strategy
    let topStratName = "VCP Contraction";
    let topStratHits = 0;
    Object.values(r.strategies || {}).forEach((st) => {
      if (st.matches_count > topStratHits) {
        topStratHits = st.matches_count;
        topStratName = st.scanner_name;
      }
    });
    const shortStratName = formatShortScannerName(topStratName);

    kpiContainer.innerHTML = `
      <div class="bg-slate-900/70 border border-slate-800 rounded-2xl p-4 flex items-center justify-between shadow-lg min-w-0">
        <div class="min-w-0 flex-1 pr-2">
          <p class="text-[11px] font-bold text-slate-400 uppercase tracking-wider truncate">Total Stocks Flagged</p>
          <p class="text-2xl font-black text-white mt-1 truncate">${r.unique_stocks_count} <span class="text-xs font-normal text-slate-500">/ 500 Scanned</span></p>
        </div>
        <div class="p-3 bg-sky-950/60 border border-sky-800/40 rounded-xl text-sky-400 shrink-0">
          <i data-lucide="layers" class="w-5 h-5"></i>
        </div>
      </div>

      <div class="bg-gradient-to-br from-amber-950/40 to-slate-900/80 border border-amber-500/40 rounded-2xl p-4 flex items-center justify-between shadow-lg shadow-amber-500/5 min-w-0">
        <div class="min-w-0 flex-1 pr-2">
          <p class="text-[11px] font-bold text-amber-300 uppercase tracking-wider flex items-center gap-1 truncate">
            <i data-lucide="flame" class="w-3.5 h-3.5 text-amber-400 shrink-0"></i> <span>High Confluence</span>
          </p>
          <p class="text-2xl font-black text-amber-300 mt-1 truncate">${r.confluence_stocks_count} Stocks <span class="text-xs font-semibold text-amber-400/80">(2+ Scanners)</span></p>
        </div>
        <div class="p-3 bg-amber-950/80 border border-amber-600/50 rounded-xl text-amber-400 shrink-0">
          <i data-lucide="crosshair" class="w-5 h-5"></i>
        </div>
      </div>

      <div class="bg-slate-900/70 border border-slate-800 rounded-2xl p-4 flex items-center justify-between shadow-lg min-w-0">
        <div class="min-w-0 flex-1 pr-2">
          <p class="text-[11px] font-bold text-slate-400 uppercase tracking-wider truncate">Market Sentiment</p>
          <p class="text-2xl font-black text-emerald-400 mt-1 truncate">${bullishPct}% Bullish <span class="text-xs font-normal text-slate-400">(${r.bullish_count}L / ${r.bearish_count}S)</span></p>
        </div>
        <div class="p-3 bg-emerald-950/60 border border-emerald-800/40 rounded-xl text-emerald-400 shrink-0">
          <i data-lucide="trending-up" class="w-5 h-5"></i>
        </div>
      </div>

      <div class="bg-slate-900/70 border border-slate-800 rounded-2xl p-4 flex items-center justify-between shadow-lg min-w-0">
        <div class="min-w-0 flex-1 pr-2">
          <p class="text-[11px] font-bold text-slate-400 uppercase tracking-wider truncate">Top Dominant Setup</p>
          <p class="text-base font-black text-purple-300 mt-1 truncate" title="${topStratName}">${shortStratName}</p>
          <p class="text-[11px] font-semibold text-purple-400/80 font-mono mt-0.5">${topStratHits} Hits</p>
        </div>
        <div class="p-3 bg-purple-950/60 border border-purple-800/40 rounded-xl text-purple-400 shrink-0">
          <i data-lucide="target" class="w-5 h-5"></i>
        </div>
      </div>
    `;
  }

  // Render Confluence Section
  const confSection = document.getElementById("eod-confluence-section");
  const confGrid = document.getElementById("eod-confluence-grid");
  const confBadge = document.getElementById("eod-confluence-badge");

  const topStocks = r.top_confluence_stocks || [];
  if (confBadge) confBadge.innerText = `${topStocks.length} Multi-Strategy Setups`;

  if (topStocks.length === 0) {
    if (confGrid) {
      confGrid.innerHTML = `
        <div class="col-span-full py-8 text-center text-slate-500 bg-slate-950/40 rounded-2xl border border-slate-800 text-xs">
          No stocks matched 2 or more strategies on this scan date. Check individual scanner matches below.
        </div>
      `;
    }
  } else if (confGrid) {
    confGrid.innerHTML = topStocks
      .map((s) => {
        const chgColor = s.change_pct >= 0 ? "text-emerald-400" : "text-rose-400";
        const chgSign = s.change_pct >= 0 ? "+" : "";
        const stratBadges = (s.strategies || [])
          .map((st) => {
            const bColor = categoryBadgeColors[st.category] || "bg-slate-800 text-slate-300 border-slate-700";
            return `<span class="px-2 py-0.5 text-[10px] font-bold rounded-lg border ${bColor}">${st.scanner_name}</span>`;
          })
          .join("");

        const primaryStrat = s.strategies[0] || {};
        const levelDesc = primaryStrat.level_desc || "Key Level Triggered";

        return `
          <div class="bg-slate-950/80 border border-amber-500/40 hover:border-amber-400 rounded-2xl p-4 space-y-3 transition group shadow-lg">
            <div class="flex items-start justify-between">
              <div>
                <div class="flex items-center space-x-2">
                  <span class="text-sm font-black text-white group-hover:text-amber-300 transition">${s.symbol}</span>
                  <span class="text-[10px] px-1.5 py-0.2 rounded bg-slate-800 text-slate-400 font-mono">NSE</span>
                </div>
                <p class="text-[11px] text-slate-400 truncate max-w-[180px]">${s.company_name || s.symbol}</p>
              </div>
              <div class="text-right">
                <span class="text-sm font-mono font-black ${chgColor}">₹${s.close.toFixed(2)}</span>
                <span class="block text-[11px] font-mono ${chgColor} font-semibold">${chgSign}${s.change_pct.toFixed(2)}%</span>
              </div>
            </div>

            <!-- Strategies Badges -->
            <div class="space-y-1.5">
              <p class="text-[10px] font-bold uppercase tracking-wider text-slate-400">${s.match_count} Strategies Confluence:</p>
              <div class="flex flex-wrap gap-1.5">
                ${stratBadges}
              </div>
            </div>

            <!-- Key Levels -->
            <div class="bg-slate-900/90 rounded-xl p-2.5 border border-slate-800 text-[11px] space-y-1">
              <div class="flex justify-between text-slate-400">
                <span>Trigger Level:</span>
                <span class="font-mono text-white font-bold truncate max-w-[180px]">${levelDesc}</span>
              </div>
              ${
                s.pivot_level
                  ? `<div class="flex justify-between text-slate-400">
                      <span>Pivot Level:</span>
                      <span class="font-mono text-sky-400 font-bold">₹${s.pivot_level.toFixed(2)}</span>
                     </div>`
                  : ""
              }
              <div class="flex justify-between text-slate-400">
                <span>Volume Surge:</span>
                <span class="font-mono text-sky-400 font-bold">${s.volume_ratio}x Avg</span>
              </div>
            </div>

            <div class="flex items-center justify-between pt-1">
              <span class="text-[10px] font-bold text-amber-400 bg-amber-950/60 px-2 py-0.5 rounded-full border border-amber-800/40">⭐ Score: ${s.confluence_score}/100</span>
              <div class="space-x-1.5">
                <a href="https://in.tradingview.com/chart/?symbol=NSE:${s.symbol}" target="_blank" class="text-xs text-sky-400 hover:text-sky-300 font-bold inline-flex items-center space-x-1">
                  <span>TV Chart</span> <i data-lucide="external-link" class="w-3 h-3"></i>
                </a>
              </div>
            </div>
          </div>
        `;
      })
      .join("");
  }

  // Render Master Table & Level Filter Dropdown
  renderEodLevelFilterDropdown();
  renderEodWatchlistTable();
  initLucide();
}

function getCleanEodStrategyLevel(st) {
  if (!st) return "Key Level";
  const desc = st.level_desc || "";
  const sig = st.signal || "";
  const scanId = st.scanner_id || "";

  if (scanId.includes("vcp") || desc.toUpperCase().includes("VCP")) {
    return "VCP Contraction";
  }
  if (desc.includes("Pullback to 200 EMA")) return "Pullback to 200 EMA";
  if (desc.includes("Pullback to 20 EMA")) return "Pullback to 20 EMA";
  if (desc.includes("Pullback to 50 EMA")) return "Pullback to 50 EMA";
  if (desc.includes("Pullback to 89 EMA")) return "Pullback to 89 EMA";
  if (desc.includes("Pullback to") && desc.includes("EMA")) {
    const match = desc.match(/Pullback to \d+ EMA/);
    if (match) return match[0];
  }
  if (desc.toUpperCase().includes("INVERSE_HS") || desc.toUpperCase().includes("INVERSE H&S")) {
    return desc.toUpperCase().includes("CONFIRMED") ? "Inverse H&S (Confirmed)" : "Inverse H&S (Forming)";
  }
  if (desc.toUpperCase().includes("REGULAR_HS") || desc.toUpperCase().includes("REGULAR H&S")) {
    return desc.toUpperCase().includes("CONFIRMED") ? "Regular H&S (Confirmed)" : "Regular H&S (Forming)";
  }
  if (desc.toUpperCase().includes("DEMAND") || desc.toUpperCase().includes("BULLISH_DEMAND")) {
    return "Demand Order Block";
  }
  if (desc.toUpperCase().includes("SUPPLY") || desc.toUpperCase().includes("BEARISH_SUPPLY")) {
    return "Supply Order Block";
  }
  if (desc.toUpperCase().includes("FVG") || scanId.includes("fvg")) {
    return "FVG 0.618 Fib Zone";
  }
  if (desc.includes("HA Reversal: Bullish") || (scanId.includes("ha_st01") && sig.toUpperCase().includes("BULLISH"))) {
    return "HA Bullish Reversal";
  }
  if (desc.includes("HA Reversal: Bearish") || (scanId.includes("ha_st01") && sig.toUpperCase().includes("BEARISH"))) {
    return "HA Bearish Reversal";
  }
  if (scanId.includes("ath") || desc.toUpperCase().includes("ATH")) {
    return "Monthly ATH Breakout";
  }
  if (scanId.includes("rsi") || desc.toUpperCase().includes("RSI")) {
    return sig.toUpperCase().includes("OVERSOLD") || sig.toUpperCase().includes("BULLISH") ? "RSI Oversold Reversal" : "RSI Momentum Setup";
  }
  if (scanId.includes("support")) {
    return sig && sig !== "Setup Triggered" ? `Support (${sig})` : "Support Level";
  }
  if (scanId.includes("resistance")) {
    return sig && sig !== "Setup Triggered" ? `Resistance (${sig})` : "Resistance Level";
  }

  // Generic fallback cleanup: strip price/bounce tags
  let clean = (desc || sig || "Key Level")
    .replace(/\s*\([^)]*₹[^)]*\)/g, "")
    .replace(/\s*@\s*₹?[0-9.,]+/g, "")
    .replace(/\s*•.*$/, "")
    .trim();
  return clean || "Key Level";
}

function renderEodLevelFilterDropdown() {
  const container = document.getElementById("container-eod-level-filter");
  const select = document.getElementById("eod-level-filter");
  if (!container || !select || !currentEodReport) return;

  const allStocks = currentEodReport.all_stocks || [];

  // Get stocks matching the active category
  const categoryStocks = allStocks.filter((s) => {
    if (eodFilterCategory === "CONFLUENCE") return s.match_count >= 2;
    if (eodFilterCategory === "VCP") return (s.strategies || []).some((st) => st.scanner_id.includes("vcp"));
    if (eodFilterCategory === "SMC") return (s.strategies || []).some((st) => st.category.toLowerCase().includes("smart") || st.scanner_id.includes("order_block") || st.scanner_id.includes("fvg"));
    if (eodFilterCategory === "BREAKOUT") return (s.strategies || []).some((st) => st.category.toLowerCase().includes("breakout") || st.scanner_id.includes("ath"));
    if (eodFilterCategory === "REVERSAL") return (s.strategies || []).some((st) => st.category.toLowerCase().includes("reversal") || st.scanner_id.includes("rsi") || st.scanner_id.includes("ha_st01"));
    if (eodFilterCategory === "TREND") return (s.strategies || []).some((st) => st.category.toLowerCase().includes("trend") || st.scanner_id.includes("st07") || st.scanner_id.includes("st15"));
    return true;
  });

  const levelCounts = {};
  categoryStocks.forEach((s) => {
    const stockLevels = new Set();
    (s.strategies || []).forEach((st) => {
      const lvl = getCleanEodStrategyLevel(st);
      if (lvl && lvl !== "N/A" && lvl !== "Key Level") {
        stockLevels.add(lvl);
      }
    });
    stockLevels.forEach((lvl) => {
      levelCounts[lvl] = (levelCounts[lvl] || 0) + 1;
    });
  });

  const uniqueLevels = Object.keys(levelCounts).sort((a, b) => levelCounts[b] - levelCounts[a]);
  const currentVal = eodFilterLevel || "ALL";

  let optionsHtml = `<option value="ALL" ${currentVal === "ALL" ? "selected" : ""}>🎯 All Trigger Levels (${categoryStocks.length})</option>`;
  uniqueLevels.forEach((lvl) => {
    const count = levelCounts[lvl];
    const isSelected = currentVal === lvl ? "selected" : "";
    optionsHtml += `<option value="${lvl.replace(/"/g, "&quot;")}" ${isSelected}>${lvl} (${count})</option>`;
  });

  select.innerHTML = optionsHtml;
}

function onEodLevelFilterChange(val) {
  eodFilterLevel = val || "ALL";
  renderEodWatchlistTable();
}
window.onEodLevelFilterChange = onEodLevelFilterChange;

function renderEodWatchlistTable() {
  if (!currentEodReport) return;
  const tableBody = document.getElementById("eod-table-body");
  const countBadge = document.getElementById("eod-table-count-badge");
  if (!tableBody) return;

  const query = eodSearchQuery.trim().toLowerCase();
  const allStocks = currentEodReport.all_stocks || [];

  const filtered = allStocks.filter((s) => {
    // Category filter
    let matchesCat = true;
    if (eodFilterCategory === "CONFLUENCE") {
      matchesCat = s.match_count >= 2;
    } else if (eodFilterCategory === "VCP") {
      matchesCat = (s.strategies || []).some((st) => st.scanner_id.includes("vcp"));
    } else if (eodFilterCategory === "SMC") {
      matchesCat = (s.strategies || []).some((st) => st.category.toLowerCase().includes("smart") || st.scanner_id.includes("order_block") || st.scanner_id.includes("fvg"));
    } else if (eodFilterCategory === "BREAKOUT") {
      matchesCat = (s.strategies || []).some((st) => st.category.toLowerCase().includes("breakout") || st.scanner_id.includes("ath"));
    } else if (eodFilterCategory === "REVERSAL") {
      matchesCat = (s.strategies || []).some((st) => st.category.toLowerCase().includes("reversal") || st.scanner_id.includes("rsi") || st.scanner_id.includes("ha_st01"));
    } else if (eodFilterCategory === "TREND") {
      matchesCat = (s.strategies || []).some((st) => st.category.toLowerCase().includes("trend") || st.scanner_id.includes("st07") || st.scanner_id.includes("st15"));
    }

    // Dynamic Key Trigger Level Filter
    let matchesLevel = true;
    if (eodFilterLevel && eodFilterLevel !== "ALL") {
      matchesLevel = (s.strategies || []).some((st) => getCleanEodStrategyLevel(st) === eodFilterLevel);
    }

    // Search query
    const matchesSearch =
      !query ||
      s.symbol.toLowerCase().includes(query) ||
      (s.company_name && s.company_name.toLowerCase().includes(query)) ||
      (s.strategies || []).some((st) => st.scanner_name.toLowerCase().includes(query) || (st.level_desc || '').toLowerCase().includes(query) || getCleanEodStrategyLevel(st).toLowerCase().includes(query));

    return matchesCat && matchesLevel && matchesSearch;
  });

  if (countBadge) {
    countBadge.innerText = `(${filtered.length} of ${allStocks.length} Flagged)`;
  }

  if (filtered.length === 0) {
    tableBody.innerHTML = `
      <tr>
        <td colspan="6" class="p-8 text-center text-slate-500 text-xs">
          No stocks match the selected filter "${eodFilterCategory}"${eodFilterLevel !== "ALL" ? ` and level "${eodFilterLevel}"` : ""}.
        </td>
      </tr>
    `;
    return;
  }

  tableBody.innerHTML = filtered
    .map((s) => {
      const chgColor = s.change_pct >= 0 ? "text-emerald-400" : "text-rose-400";
      const chgSign = s.change_pct >= 0 ? "+" : "";
      const isConfluence = s.match_count >= 2;

      const stratPills = (s.strategies || [])
        .map((st) => {
          const bColor = categoryBadgeColors[st.category] || "bg-slate-800 text-slate-300 border-slate-700";
          return `<span class="px-2 py-0.5 text-[10px] font-bold rounded border ${bColor}">${st.scanner_name}</span>`;
        })
        .join(" ");

      const primaryStrat = s.strategies[0] || {};
      const triggerDesc = primaryStrat.level_desc || primaryStrat.signal || "Triggered";

      return `
        <tr class="hover:bg-slate-800/40 transition">
          <td class="p-3.5 font-bold text-white flex items-center space-x-2">
            ${
              isConfluence
                ? `<span class="w-2 h-2 rounded-full bg-amber-400" title="High Confluence (2+ Scanners)"></span>`
                : `<span class="w-2 h-2 rounded-full bg-slate-600"></span>`
            }
            <span>${s.symbol}</span>
          </td>
          <td class="p-3.5 font-mono">₹${s.close.toFixed(2)} <span class="${chgColor} font-bold ml-1">${chgSign}${s.change_pct.toFixed(2)}%</span></td>
          <td class="p-3.5">
            <div class="flex gap-1 flex-wrap">
              ${stratPills}
            </div>
          </td>
          <td class="p-3.5 text-slate-300 max-w-[280px] truncate" title="${triggerDesc}">${triggerDesc}</td>
          <td class="p-3.5 font-mono font-bold text-sky-400">${s.volume_ratio}x</td>
          <td class="p-3.5 text-right space-x-2 whitespace-nowrap">
            <a href="https://in.tradingview.com/chart/?symbol=NSE:${s.symbol}" target="_blank" class="px-2.5 py-1 bg-slate-800 hover:bg-slate-700 text-sky-300 rounded-lg text-[11px] font-semibold transition inline-block">TV Chart</a>
            <a href="https://web.dhan.co" target="_blank" class="px-2.5 py-1 bg-sky-600/20 hover:bg-sky-600/40 text-sky-300 border border-sky-500/40 rounded-lg text-[11px] font-semibold transition inline-block">Dhan</a>
          </td>
        </tr>
      `;
    })
    .join("");

  initLucide();
}

function filterEodTable(cat) {
  eodFilterCategory = cat;
  eodFilterLevel = "ALL";
  document.querySelectorAll(".eod-filter-btn").forEach((btn) => {
    if (btn.dataset.eodFilter === cat) {
      btn.className = "eod-filter-btn px-3 py-1 rounded-lg font-bold bg-sky-500/20 text-sky-300 border border-sky-500/30";
    } else {
      btn.className = "eod-filter-btn px-3 py-1 rounded-lg font-semibold text-slate-400 hover:text-white";
    }
  });
  renderEodLevelFilterDropdown();
  renderEodWatchlistTable();
}
window.filterEodTable = filterEodTable;

function onEodSearchInput(query) {
  eodSearchQuery = query;
  renderEodWatchlistTable();
}
window.onEodSearchInput = onEodSearchInput;

function onEodDateSelected(date) {
  loadEodDigest(date);
}
window.onEodDateSelected = onEodDateSelected;

function openEodConfirmModal() {
  const modal = document.getElementById("modal-eod-confirm");
  if (modal) {
    modal.style.display = "flex";
    modal.classList.remove("hidden");
    initLucide();
  }
}
window.openEodConfirmModal = openEodConfirmModal;

function closeEodConfirmModal() {
  const modal = document.getElementById("modal-eod-confirm");
  if (modal) {
    modal.classList.add("hidden");
    modal.style.display = "none";
  }
}
window.closeEodConfirmModal = closeEodConfirmModal;

async function confirmAndStartEodScan() {
  closeEodConfirmModal();
  await runEodScanNow();
}
window.confirmAndStartEodScan = confirmAndStartEodScan;

function updateEodProgressUI(status) {
  const banner = document.getElementById("eod-active-scan-banner");
  const pBar = document.getElementById("eod-scan-progress-bar");
  const pctBadge = document.getElementById("eod-scan-pct-badge");
  const stepInd = document.getElementById("eod-scan-step-indicator");
  const btn = document.getElementById("btn-eod-run-now");
  const icon = document.getElementById("icon-eod-refresh");
  const text = document.getElementById("btn-eod-run-text");
  const dateSelect = document.getElementById("eod-select-date");

  // Global nav badge
  const globalBadge = document.getElementById("global-eod-scan-badge");
  const globalText = document.getElementById("global-eod-scan-text");

  if (status && status.is_executing) {
    const pct = status.progress_pct !== undefined ? status.progress_pct : 0;
    const count = status.completed_scanners ? `${status.completed_scanners}/${status.total_scanners || 12}` : "0/12";
    const curName = status.current_scanner || "Starting scanners";

    // 1. Show & update EOD banner
    if (banner) {
      banner.classList.remove("hidden");
    }
    if (pBar) {
      pBar.style.width = `${Math.max(5, pct)}%`;
    }
    if (pctBadge) {
      pctBadge.innerText = `${pct}%`;
    }
    if (stepInd) {
      stepInd.innerHTML = `Scanner <strong class="text-sky-300">${count}</strong>: <span class="text-amber-300 font-semibold">${curName}</span>`;
    }

    // 2. Lock EOD screen action controls
    if (btn) btn.disabled = true;
    if (icon) icon.classList.add("animate-spin");
    if (text) text.innerText = `Scanning (${pct}%)...`;
    if (dateSelect) dateSelect.disabled = true;

    // 3. Show & update global navbar badge across tabs
    if (globalBadge) {
      globalBadge.classList.remove("hidden");
      globalBadge.classList.add("flex");
    }
    if (globalText) {
      globalText.innerText = `⚡ EOD Scan: ${pct}% (${curName})`;
    }
  } else {
    // Hide EOD banner & global badge, re-enable controls
    if (banner) {
      banner.classList.add("hidden");
    }
    if (globalBadge) {
      globalBadge.classList.add("hidden");
      globalBadge.classList.remove("flex");
    }
    if (btn) btn.disabled = false;
    if (icon) icon.classList.remove("animate-spin");
    if (text) text.innerText = "Run All Now";
    if (dateSelect) dateSelect.disabled = false;
  }
  initLucide();
}
window.updateEodProgressUI = updateEodProgressUI;

let eodPollInterval = null;

async function runEodScanNow() {
  updateEodProgressUI({
    is_executing: true,
    progress_pct: 0,
    completed_scanners: 0,
    total_scanners: 12,
    current_scanner: "Initializing Batch Scan",
  });

  try {
    const res = await fetch("/api/eod-scans/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ universe: "NIFTY_500" }),
    });

    if (!res.ok) {
      const errData = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
      throw new Error(errData.detail || `Server returned ${res.status}`);
    }

    const startData = await res.json();
    console.log("EOD Scan started:", startData);
    if (typeof showToast === "function") {
      showToast("🚀 EOD Batch Scan started (~5–10 min). Safe to switch tabs!", "⏳");
    }

    startEodStatusPolling();
  } catch (err) {
    console.error("Error running EOD batch scan:", err);
    updateEodProgressUI({ is_executing: false });
    if (typeof showToast === "function") {
      showToast(`EOD Scan error: ${err.message || err}`, "❌");
    } else {
      alert(`EOD Scan failed: ${err.message || err}`);
    }
  }
}
window.runEodScanNow = runEodScanNow;

function startEodStatusPolling() {
  if (eodPollInterval) clearInterval(eodPollInterval);

  eodPollInterval = setInterval(async () => {
    try {
      const res = await fetch("/api/eod-scans/status");
      if (!res.ok) return;
      const status = await res.json();

      if (status.is_executing) {
        updateEodProgressUI(status);
      } else {
        clearInterval(eodPollInterval);
        eodPollInterval = null;
        updateEodProgressUI({ is_executing: false });

        await loadEodDatesAndLatest();
        if (typeof showToast === "function") {
          showToast("🎉 Daily EOD Multi-Scanner Digest complete & saved to MySQL!", "🌆");
        }
      }
    } catch (e) {
      console.warn("Polling EOD status error:", e);
    }
  }, 2000);
}
window.startEodStatusPolling = startEodStatusPolling;

function checkInitialEodStatus() {
  fetch("/api/eod-scans/status")
    .then((r) => r.json())
    .then((status) => {
      if (status && status.is_executing) {
        updateEodProgressUI(status);
        startEodStatusPolling();
      }
    })
    .catch(() => {});
}
checkInitialEodStatus();
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", checkInitialEodStatus);
}

function triggerAppToast(msg, icon = "📋") {
  if (typeof window.showToast === "function") {
    window.showToast(msg, icon);
    return;
  }
  let toast = document.getElementById("toast");
  if (!toast) {
    toast = document.createElement("div");
    toast.id = "toast";
    toast.className =
      "fixed bottom-5 right-5 bg-gray-900 border border-gray-700 text-white text-xs px-4 py-3 rounded-lg shadow-2xl transition-all duration-300 opacity-0 translate-y-4 pointer-events-none z-50 flex items-center gap-2";
    toast.innerHTML = `<span id="toast-icon">${icon}</span><span id="toast-msg">${msg}</span>`;
    document.body.appendChild(toast);
  } else {
    const iconEl = document.getElementById("toast-icon");
    const msgEl = document.getElementById("toast-msg");
    if (iconEl) iconEl.textContent = icon;
    if (msgEl) msgEl.textContent = msg;
  }
  toast.classList.remove("opacity-0", "translate-y-4", "pointer-events-none");
  toast.classList.add("opacity-100", "translate-y-0");
  setTimeout(() => {
    toast.classList.add("opacity-0", "translate-y-4", "pointer-events-none");
    toast.classList.remove("opacity-100", "translate-y-0");
  }, 3500);
}

async function copyEodTradingViewWatchlist(onlyConfluence = false) {
  if (!currentEodReport) {
    triggerAppToast("No EOD report loaded yet.", "⚠️");
    return;
  }

  const stocks = onlyConfluence
    ? currentEodReport.top_confluence_stocks || []
    : currentEodReport.all_stocks || [];

  if (stocks.length === 0) {
    triggerAppToast("No stocks in selected list.", "⚠️");
    return;
  }

  const tvString = stocks.map((s) => `NSE:${s.symbol}`).join(", ");
  try {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      await navigator.clipboard.writeText(tvString);
    } else {
      const textarea = document.createElement("textarea");
      textarea.value = tvString;
      textarea.style.position = "fixed";
      textarea.style.opacity = "0";
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand("copy");
      document.body.removeChild(textarea);
    }
    const label = onlyConfluence ? "Confluence" : "EOD";
    triggerAppToast(`📋 Copied ${stocks.length} ${label} symbols for TradingView!`, "📋");
  } catch (err) {
    const textarea = document.createElement("textarea");
    textarea.value = tvString;
    textarea.style.position = "fixed";
    textarea.style.opacity = "0";
    document.body.appendChild(textarea);
    textarea.select();
    document.execCommand("copy");
    document.body.removeChild(textarea);
    triggerAppToast(`📋 Copied ${stocks.length} symbols for TradingView!`, "📋");
  }
}
window.copyEodTradingViewWatchlist = copyEodTradingViewWatchlist;

async function copyTradingViewWatchlist() {
  const itemsToCopy =
    currentlyDisplayedItems.length > 0
      ? currentlyDisplayedItems
      : currentReport
      ? currentReport.results
      : [];

  if (!itemsToCopy || itemsToCopy.length === 0) {
    triggerAppToast("No symbols to copy.", "⚠️");
    return;
  }

  // Format as plain comma-separated symbols for TradingView
  const tvString = itemsToCopy.map((r) => r.symbol).join(", ");

  try {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      await navigator.clipboard.writeText(tvString);
    } else {
      const textarea = document.createElement("textarea");
      textarea.value = tvString;
      textarea.style.position = "fixed";
      textarea.style.opacity = "0";
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand("copy");
      document.body.removeChild(textarea);
    }
    triggerAppToast(`📋 Copied ${itemsToCopy.length} symbols for TradingView!`, "📋");

    // Animate button feedback
    const btn = document.getElementById("btn-copy-tv");
    const textSpan = document.getElementById("btn-copy-tv-text");
    const originalText = textSpan ? textSpan.innerText : "Copy TradingView Watchlist";

    if (btn) {
      btn.classList.remove(
        "from-blue-600",
        "to-indigo-600",
        "hover:from-blue-500",
        "hover:to-indigo-500"
      );
      btn.classList.add("from-emerald-600", "to-teal-600", "glow-green");
      btn.innerHTML = `
        <i data-lucide="check" class="w-3.5 h-3.5 text-white"></i>
        <span>Copied ${itemsToCopy.length} Symbols!</span>
      `;
      initLucide();

      setTimeout(() => {
        if (btn) {
          btn.classList.remove("from-emerald-600", "to-teal-600", "glow-green");
          btn.classList.add(
            "from-blue-600",
            "to-indigo-600",
            "hover:from-blue-500",
            "hover:to-indigo-500"
          );
          btn.innerHTML = `
            <i data-lucide="copy" class="w-3.5 h-3.5"></i>
            <span id="btn-copy-tv-text">${originalText}</span>
          `;
          initLucide();
        }
      }, 2500);
    }
  } catch (err) {
    console.error("Clipboard copy failed:", err);
    prompt("Copy these symbols for TradingView:", tvString);
  }
}

function exportCSV() {
  if (!currentReport || !currentReport.results) return;

  const headers = [
    "Symbol",
    "LTP",
    "Key Level Price",
    "Distance (%)",
    "Level Description",
    "Volume",
    "At Key Level",
    "RSI (14)",
    "Signal",
  ];
  const rows = (currentlyDisplayedItems.length > 0
    ? currentlyDisplayedItems
    : currentReport.results
  ).map((r) => [
    r.symbol,
    r.ltp,
    r.support_price ?? r.stop_loss ?? r.prior_ath_price ?? r.ema_89 ?? "",
    r.distance_pct,
    `"${(getItemLevelDesc(r, currentReport) || "").replace(/"/g, '""')}"`,
    r.volume || 0,
    (r.is_at_support || r.is_pullback) ? "YES" : "NO",
    r.rsi ?? "",
    `"${(r.candle_signal || "").replace(/"/g, '""')}"`,
  ]);

  const csvContent =
    "data:text/csv;charset=utf-8," +
    [headers.join(","), ...rows.map((e) => e.join(","))].join("\n");
  const encodedUri = encodeURI(csvContent);
  const link = document.createElement("a");
  link.setAttribute("href", encodedUri);
  link.setAttribute(
    "download",
    `${currentReport.scanner_id}_${new Date().toISOString().slice(0, 10)}.csv`
  );
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}
