"""Frontend HTML, CSS, and JavaScript templates for Web UI Dashboard."""

def get_login_html() -> str:
    """Return dedicated application login page HTML matching reference UI."""
    return """<!DOCTYPE html>
<html lang="en" class="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Sign In | NSE Catalyst Trading Terminal</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <script>
    tailwind.config = {
      darkMode: 'class',
      theme: {
        extend: {
          colors: {
            brand: { 500: '#10b981', 600: '#059669', 700: '#047857' },
          }
        }
      }
    }
  </script>
</head>
<body class="bg-[#0b0f19] text-gray-200 font-sans antialiased min-h-screen flex items-center justify-center p-4">
  <div class="max-w-md w-full">
    
    <!-- Header / Brand -->
    <div class="text-center mb-6">
      <div class="inline-flex items-center justify-center w-12 h-12 rounded-2xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 font-black text-2xl mb-3 shadow-lg shadow-emerald-500/10">
        ⚡
      </div>
      <h1 class="text-lg font-bold text-white tracking-wide uppercase">NSE Catalyst Trading Terminal</h1>
      <p class="text-xs text-gray-400 mt-1">Sign in to access real-time execution grid</p>
    </div>

    <!-- Login Card Container -->
    <div class="bg-[#111827] border border-gray-800 rounded-2xl p-7 shadow-2xl space-y-5">
      
      <!-- Error / Status Alert Banner -->
      <div id="login-alert" class="hidden text-xs p-3 rounded-xl border transition-all"></div>

      <!-- Credentials Login Form -->
      <form id="login-form" onsubmit="handleCredentialsLogin(event)" class="space-y-4">
        <div>
          <label class="block text-xs font-semibold text-gray-300 mb-1.5" for="username">Username or Email</label>
          <div class="relative">
            <input type="text" id="username" name="username" required autofocus placeholder="Enter username (e.g. amit)" class="w-full bg-[#0b0f19] border border-gray-700 text-xs text-white rounded-xl pl-9 pr-3 py-2.5 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition font-medium">
            <span class="absolute left-3 top-3 text-xs text-gray-400">👤</span>
          </div>
        </div>

        <div>
          <label class="block text-xs font-semibold text-gray-300 mb-1.5" for="password">Password</label>
          <div class="relative">
            <input type="password" id="password" name="password" required placeholder="Enter password" class="w-full bg-[#0b0f19] border border-gray-700 text-xs text-white rounded-xl pl-9 pr-10 py-2.5 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition font-medium">
            <span class="absolute left-3 top-3 text-xs text-gray-400">🔒</span>
            <button type="button" onclick="togglePasswordVisibility()" class="absolute right-3 top-2.5 text-gray-400 hover:text-gray-200 text-xs">
              <span id="pwd-toggle-icon">👁️</span>
            </button>
          </div>
        </div>

        <!-- Primary Blue Sign In Button -->
        <button type="submit" id="btn-submit" class="w-full bg-blue-600 hover:bg-blue-500 active:scale-95 text-white font-bold text-xs py-3 px-4 rounded-xl shadow-lg shadow-blue-600/30 transition flex items-center justify-center gap-2">
          <span>Sign In</span>
        </button>
      </form>

      <!-- Horizontal Divider with "or" -->
      <div class="flex items-center gap-3 my-4">
        <div class="flex-1 h-px bg-gray-700/60"></div>
        <span class="text-xs text-gray-400 font-medium">or</span>
        <div class="flex-1 h-px bg-gray-700/60"></div>
      </div>

      <!-- Dedicated "Log In with Dhan" Button (Matching Diagram) -->
      <button type="button" onclick="handleDhanSSO()" id="btn-dhan-sso" class="w-full bg-white hover:bg-gray-100 active:scale-95 text-gray-800 font-semibold text-xs py-2.5 px-4 rounded-xl border border-gray-300 shadow-sm transition flex items-center justify-center gap-2.5">
        <span class="w-5 h-5 rounded-md bg-[#00b060] flex items-center justify-center text-white font-bold text-xs shadow-inner">
          ध
        </span>
        <span class="text-[13px] font-medium text-gray-800">Log In with Dhan</span>
      </button>

      <!-- Footer: Don't have an account? Create One -->
      <div class="pt-2 text-center text-xs text-gray-400">
        <span>Don't have an account?</span>
        <a href="https://join.dhan.co/?invite=VEVQU13117" target="_blank" rel="noopener noreferrer" class="text-blue-500 hover:underline font-semibold ml-1">Create One</a>
      </div>

    </div>

    <!-- Sub-footer -->
    <div class="text-center mt-6 text-[11px] text-gray-500 font-mono">
      <span>Protected by NSE Quantitative Strategy Engine • v1.0.0</span>
    </div>

  </div>

  <script>
    function togglePasswordVisibility() {
      const pwdInput = document.getElementById('password');
      const icon = document.getElementById('pwd-toggle-icon');
      if (pwdInput.type === 'password') {
        pwdInput.type = 'text';
        icon.textContent = '🙈';
      } else {
        pwdInput.type = 'password';
        icon.textContent = '👁️';
      }
    }

    function showAlert(msg, isError = true) {
      const alertBox = document.getElementById('login-alert');
      alertBox.className = isError 
        ? 'block bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs p-3 rounded-xl' 
        : 'block bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 text-xs p-3 rounded-xl';
      alertBox.textContent = msg;
    }

    async function handleCredentialsLogin(event) {
      event.preventDefault();
      const username = document.getElementById('username').value.trim();
      const password = document.getElementById('password').value;
      const btn = document.getElementById('btn-submit');

      if (!username || !password) {
        showAlert('Please enter both username and password.');
        return;
      }

      btn.disabled = true;
      btn.classList.add('opacity-50');
      btn.innerHTML = '<span>Verifying credentials...</span>';

      try {
        const res = await fetch('/api/auth/login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ username, password })
        });
        const data = await res.json();

        if (res.ok && data.success) {
          showAlert('Login successful! Redirecting to terminal...', false);
          const params = new URLSearchParams(window.location.search);
          const next = params.get('next') || '/';
          setTimeout(() => {
            window.location.href = next;
          }, 300);
        } else {
          showAlert(data.message || 'Invalid username or password.');
        }
      } catch (err) {
        showAlert('Connection error. Please try again.');
      } finally {
        btn.disabled = false;
        btn.classList.remove('opacity-50');
        btn.innerHTML = '<span>Sign In</span>';
      }
    }

    async function handleDhanSSO() {
      const btn = document.getElementById('btn-dhan-sso');
      btn.disabled = true;
      btn.classList.add('opacity-50');

      try {
        const res = await fetch('/api/auth/dhan/sso');
        const data = await res.json();

        if (res.ok && data.success && data.login_url) {
          showAlert('Redirecting to Dhan OAuth login portal...', false);
          setTimeout(() => {
            window.location.href = data.login_url;
          }, 200);
        } else {
          showAlert(data.message || 'Unable to initiate Dhan SSO. Please configure Dhan App ID & Secret, or login with username & password.');
        }
      } catch (err) {
        showAlert('Connection error initiating Dhan SSO.');
      } finally {
        btn.disabled = false;
        btn.classList.remove('opacity-50');
      }
    }

    window.onload = function() {
      const params = new URLSearchParams(window.location.search);
      if (params.get('error')) {
        showAlert(params.get('error'));
      } else if (params.get('logged_out')) {
        showAlert('You have been successfully logged out from the application session.', false);
      }
    };
  </script>
</body>
</html>
"""


def get_dashboard_html(is_simulate_feed: bool = False) -> str:
    """Return a sleek, high-density Trading Terminal Table Grid dashboard."""
    sim_header_btn = """
          <!-- Simulation Button -->
          <button onclick="triggerSimulation()" id="sim-btn" class="bg-indigo-600 hover:bg-indigo-500 active:scale-95 text-white text-xs font-bold px-3 py-2 rounded-lg transition border border-indigo-400/40 shadow-md flex items-center gap-1.5">
            <span>⚡</span>
            <span>Simulate Feed</span>
          </button>
""" if is_simulate_feed else ""

    sim_empty_btn = """
        <div>
          <button onclick="triggerSimulation()" class="inline-flex items-center gap-2 px-3.5 py-2 text-xs font-bold text-white bg-indigo-600 hover:bg-indigo-500 active:scale-95 rounded-lg transition shadow-md border border-indigo-400/30">
            <span>⚡ Test / Simulate Sample Catalyst Feed</span>
          </button>
        </div>
""" if is_simulate_feed else ""

    html = """<!DOCTYPE html>
<html lang="en" class="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>NSE Catalyst Trading Terminal | Real-Time Execution Grid</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <script>
    tailwind.config = {
      darkMode: 'class',
      theme: {
        extend: {
          colors: {
            brand: { 500: '#10b981', 600: '#059669', 700: '#047857' },
          }
        }
      }
    }
  </script>
  <style>
    @keyframes pulse-subtle { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }
    .animate-pulse-subtle { animation: pulse-subtle 2s cubic-bezier(0.4, 0, 0.6, 1) infinite; }
    .custom-scrollbar::-webkit-scrollbar { width: 6px; height: 6px; }
    .custom-scrollbar::-webkit-scrollbar-track { background: #0f172a; }
    .custom-scrollbar::-webkit-scrollbar-thumb { background: #334155; border-radius: 4px; }
    tbody tr:hover { background-color: rgba(30, 41, 59, 0.5) !important; }
  </style>
  <!-- Lucide Icons & Scanner Assets -->
  <script src="https://unpkg.com/lucide@latest"></script>
  <link rel="stylesheet" href="/static/scanner/style.css?v=2.5" />
</head>
<body class="bg-[#0b0f19] text-gray-200 font-sans antialiased min-h-screen flex flex-col custom-scrollbar">

  <!-- TOP APP BAR -->
  <header class="bg-[#111827] border-b border-gray-800 sticky top-0 z-50 px-5 py-2.5 shadow-md">
    <div class="max-w-[1600px] mx-auto flex flex-wrap items-center justify-between gap-3">
      
      <!-- Brand & Strategy Selector Hub -->
      <div class="flex items-center gap-3">
        <div class="w-8 h-8 rounded-lg bg-emerald-500/10 border border-emerald-500/30 flex items-center justify-center text-emerald-400 font-black text-lg shadow-sm">
          ⚡
        </div>
        
        <div>
          <div class="flex items-center gap-2">
            <h1 class="text-xs font-bold text-white tracking-wider uppercase">NSE TERMINAL</h1>
            <span class="px-1.5 py-0.5 text-[10px] font-mono font-bold bg-blue-950/80 text-blue-400 border border-blue-800/60 rounded shadow-sm" title="Application Version 1.0.0">v1.0.0</span>
            <!-- Dynamic Market Status Badge -->
            <span id="market-status-badge" class="px-2 py-0.5 text-[10px] font-bold bg-rose-500/20 text-rose-300 border border-rose-500/40 rounded-full flex items-center gap-1 shadow-sm transition-all" title="NSE Trading Hours (Mon-Fri 09:15 - 15:30 IST)">
              <span id="market-status-dot" class="w-1.5 h-1.5 rounded-full bg-rose-400"></span>
              <span id="market-status-text">MARKET CLOSED</span>
            </span>
            <!-- Dynamic Cutoff Status Badge -->
            <span id="cutoff-status-badge" class="px-2 py-0.5 text-[10px] font-bold bg-gray-800 text-gray-300 border border-gray-700 rounded-full flex items-center gap-1 shadow-sm transition-all" title="Cutoff 14:45 | Square-Off 15:00">
              <span id="cutoff-status-dot" class="w-1.5 h-1.5 rounded-full bg-emerald-400"></span>
              <span id="cutoff-status-text">CUTOFF 14:45</span>
            </span>
          </div>
        </div>

        <!-- Vertical Divider -->
        <div class="h-6 w-px bg-gray-800 hidden sm:block"></div>

        <!-- Navigation Tabs Switcher (Scanner vs EOD Digest vs Strategies) -->
        <div class="flex items-center gap-1 bg-[#0b0f19] p-1 rounded-xl border border-gray-800">
          <button id="nav-tab-scanner" onclick="switchMainTab('scanner')" class="px-2.5 py-1 rounded-lg text-xs font-bold transition bg-indigo-600 text-white shadow-sm flex items-center gap-1.5">
            <span>🔭</span> <span>Scanner</span>
          </button>
          <button id="nav-tab-eod" onclick="switchMainTab('eod')" class="px-2.5 py-1 rounded-lg text-xs font-bold transition text-gray-400 hover:text-gray-200 hover:bg-gray-800 flex items-center gap-1.5">
            <span>🌆</span> <span>EOD Digest</span>
          </button>
          <button id="nav-tab-strategies" onclick="switchMainTab('strategies')" class="px-2.5 py-1 rounded-lg text-xs font-bold transition text-gray-400 hover:text-gray-200 hover:bg-gray-800 flex items-center gap-1.5">
            <span>⚡</span> <span>Strategies</span>
          </button>
        </div>

        <!-- Strategy Quick-Selector Dropdown (Right of Strategies) -->
        <div class="relative" id="strategy-selector-container">
          <button onclick="toggleStrategyMenu()" id="btn-strategy-selector" disabled class="opacity-30 cursor-not-allowed pointer-events-none bg-[#162032] hover:bg-[#1f293d] border border-emerald-500/40 hover:border-emerald-400/70 px-3 py-1.5 rounded-xl transition-all shadow-md flex items-center gap-2.5 active:scale-95" title="Strategy selector disabled in Technical Scanner mode. Switch to Strategies tab to change strategy.">
            <span id="header-strat-icon" class="text-base">⚡</span>
            <div class="text-left">
              <div class="flex items-center gap-1.5">
                <span id="header-strat-code" class="text-[10px] font-mono font-bold bg-emerald-950/90 text-emerald-300 border border-emerald-800/80 px-1.5 py-0.2 rounded">ST-NEWS</span>
                <span id="header-strat-name" class="text-xs font-bold text-white max-w-[170px] truncate">NSE Catalyst News Engine</span>
              </div>
            </div>
            <span class="text-[10px] text-gray-400 ml-0.5">▼</span>
          </button>

          <!-- Floating Strategy Popover Menu -->
          <div id="strategy-menu-dropdown" class="hidden absolute left-0 top-12 w-80 sm:w-96 bg-[#111827] border border-gray-700/90 rounded-2xl shadow-2xl p-3.5 z-50 space-y-2.5">
            <div class="flex items-center justify-between border-b border-gray-800 pb-2">
              <span class="text-[10px] uppercase font-bold text-gray-400 tracking-wider">Select Quantitative Strategy</span>
              <span id="strategies-count-badge" class="text-[10px] font-mono text-emerald-400 bg-emerald-950/60 border border-emerald-800/60 px-2 py-0.5 rounded-full">5 Registered</span>
            </div>
            
            <!-- Category Filter Pills inside popover -->
            <div class="flex items-center gap-1 overflow-x-auto pb-1 custom-scrollbar text-[10px]">
              <button onclick="filterStrategyCategory('ALL')" data-strat-cat="ALL" class="strat-cat-pill px-2 py-0.5 rounded-md font-semibold transition bg-emerald-600 text-white">All (5)</button>
              <button onclick="filterStrategyCategory('event_news')" data-strat-cat="event_news" class="strat-cat-pill px-2 py-0.5 rounded-md font-semibold transition text-gray-400 hover:bg-gray-800">News</button>
              <button onclick="filterStrategyCategory('trend_momentum')" data-strat-cat="trend_momentum" class="strat-cat-pill px-2 py-0.5 rounded-md font-semibold transition text-gray-400 hover:bg-gray-800">Momentum</button>
              <button onclick="filterStrategyCategory('breakouts')" data-strat-cat="breakouts" class="strat-cat-pill px-2 py-0.5 rounded-md font-semibold transition text-gray-400 hover:bg-gray-800">Breakouts</button>
              <button onclick="filterStrategyCategory('reversals')" data-strat-cat="reversals" class="strat-cat-pill px-2 py-0.5 rounded-md font-semibold transition text-gray-400 hover:bg-gray-800">Reversals</button>
              <button onclick="filterStrategyCategory('smart_money')" data-strat-cat="smart_money" class="strat-cat-pill px-2 py-0.5 rounded-md font-semibold transition text-gray-400 hover:bg-gray-800">Smart Money</button>
            </div>

            <!-- List of strategies -->
            <div id="strategy-cards-grid" class="space-y-1.5 max-h-80 overflow-y-auto custom-scrollbar pr-1">
              <!-- Populated dynamically -->
            </div>
          </div>
        </div>

        <!-- Global EOD Scan Live Progress Pill -->
        <div id="global-eod-scan-badge" class="hidden items-center gap-2 px-3 py-1.5 bg-amber-500/15 border border-amber-500/40 rounded-xl text-amber-300 text-xs font-semibold cursor-pointer animate-pulse transition hover:bg-amber-500/25 shadow-sm" onclick="switchMainTab('eod')" title="EOD Batch Scan in progress (~5-10 min). Click to view live progress on EOD tab.">
          <span class="w-2 h-2 rounded-full bg-amber-400 animate-ping"></span>
          <span id="global-eod-scan-text">⚡ EOD Scan: 0%</span>
        </div>

      </div>

      <!-- RIGHT-TOP USER LOGIN & ACCOUNT WIDGET (Pinned to Extreme Top-Right) -->
      <div class="flex items-center gap-2.5 flex-shrink-0">
        <div class="relative" id="user-account-container">
          <!-- Unauthenticated Login Button -->
          <button onclick="openLoginScreen()" id="btn-header-login" class="hidden bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white font-bold text-xs px-3.5 py-2 rounded-xl shadow-lg shadow-emerald-700/30 border border-emerald-400/40 flex items-center gap-2 transition active:scale-95">
            <span>🔐</span>
            <span>Login with Dhan</span>
          </button>

          <!-- Authenticated User Profile Button -->
          <div id="user-profile-widget" class="flex items-center gap-2">
            <button onclick="toggleUserMenu()" id="token-btn" class="group bg-[#162032] hover:bg-[#1f293d] active:scale-95 border border-emerald-500/40 hover:border-emerald-400/70 px-3 py-1.5 rounded-xl transition-all shadow-md flex items-center gap-2" title="Manage Dhan Account & Session">
              <div class="w-6 h-6 rounded-lg bg-emerald-500/20 border border-emerald-500/30 flex items-center justify-center text-emerald-400 font-bold text-xs shadow-inner">
                👤
              </div>
              <div class="text-left">
                <div class="text-[9px] font-bold uppercase tracking-wider text-gray-400 flex items-center gap-1">
                  <span id="user-client-id-label">DHAN</span>
                  <span id="token-indicator-dot" class="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
                </div>
                <div id="header-token-mask" class="text-[11px] font-mono font-bold text-emerald-400 group-hover:text-emerald-300">
                  Active
                </div>
              </div>
              <span class="text-[10px] text-gray-400 group-hover:text-white transition ml-0.5">▼</span>
            </button>

            <!-- User Menu Dropdown -->
            <div id="user-menu-dropdown" class="hidden absolute right-0 top-12 w-64 bg-[#111827] border border-gray-700/80 rounded-xl shadow-2xl p-3 z-50 space-y-2.5 text-xs">
              <div class="border-b border-gray-800 pb-2">
                <div class="text-[10px] uppercase font-bold text-gray-400 tracking-wider">Trading Account (Broker)</div>
                <div id="menu-client-id" class="text-xs font-mono font-bold text-white mt-0.5">Client ID: --</div>
                <div id="menu-expiry-info" class="text-[10px] text-emerald-400 font-mono mt-0.5">Active Session</div>
              </div>
              <div class="space-y-1">
                <button onclick="openLoginScreen(); toggleUserMenu();" class="w-full text-left px-2.5 py-1.5 rounded-lg hover:bg-gray-800 text-gray-300 hover:text-white flex items-center gap-2 transition">
                  <span>🔄</span> Manage Dhan Token
                </button>
                <button onclick="logoutDhan(); toggleUserMenu();" class="w-full text-left px-2.5 py-1.5 rounded-lg hover:bg-rose-950/40 text-rose-400 hover:text-rose-300 flex items-center gap-2 transition font-semibold">
                  <span>🚪</span> Disconnect Dhan Token
                </button>
              </div>
              <div class="border-t border-gray-800 pt-2 space-y-1">
                <div class="text-[10px] uppercase font-bold text-gray-400 tracking-wider">App User Session</div>
                <button onclick="logoutApp();" class="w-full text-left px-2.5 py-1.5 rounded-lg hover:bg-rose-900/50 bg-rose-950/30 text-rose-300 hover:text-white flex items-center gap-2 transition font-bold border border-rose-500/20">
                  <span>🔒</span> Sign Out (App Logout)
                </button>
              </div>
            </div>
          </div>
        </div>

      </div>
    </div>
  </header>

  <!-- STRATEGIES TAB CONTAINER -->
  <div id="main-tab-strategies" class="hidden w-full flex-1 flex flex-col">

    <!-- WORKSPACE 1: ST-NEWS CATALYST WORKSPACE -->
    <div id="workspace-st-news" class="strategy-workspace-pane w-full flex-1 flex flex-col">

      <!-- UNIFIED 1-ROW COMMAND & TELEMETRY STRIP (36px high) -->
      <div class="bg-[#0e1422] border-b border-gray-800/90 px-6 py-1.5 shadow-sm">
        <div class="max-w-[1600px] mx-auto flex flex-wrap items-center justify-between gap-3 text-xs">
          
          <!-- Left: Radar Status, Universe & Strategy Controls -->
          <div class="flex items-center gap-2.5 flex-wrap">
            <div class="inline-flex items-center gap-1.5 bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 px-2.5 py-0.5 rounded-full font-bold text-[11px] shadow-sm" id="radar-badge-container">
              <span class="relative flex h-2 w-2">
                <span id="radar-ping-dot" class="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                <span id="radar-solid-dot" class="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
              </span>
              <span id="poller-status-badge">NSE RADAR</span>
            </div>
            <div class="text-gray-300 flex items-center gap-1.5 font-medium text-[11px]">
              <span>Watching <b id="poller-fno-count" class="text-white font-mono font-bold">228</b> F&O</span>
              <span class="text-gray-600">•</span>
              <span>Check: <span id="poller-last-time" class="text-emerald-400 font-mono font-bold">Just now</span></span>
              <span id="poller-elapsed-tag" class="text-[10px] text-emerald-300 bg-emerald-950/60 border border-emerald-500/30 px-1.5 py-0.2 rounded font-mono font-semibold">0s ago</span>
            </div>

            <!-- Vertical Divider -->
            <div class="h-4 w-px bg-gray-800 hidden sm:block"></div>

            <!-- Strategy Controls Group -->
            <div id="strategy-controls-group" class="flex items-center gap-1.5 flex-wrap">
              <!-- MASTER STRATEGY ENGINE POWER BUTTON (ACTIVE / PAUSED) -->
              <button id="toggle-engine-btn" onclick="toggleStrategyEngine()" class="px-2.5 py-1 text-xs font-bold rounded-lg transition flex items-center gap-1.5 shadow border border-emerald-500/50 bg-emerald-950/70 text-emerald-300 hover:bg-emerald-900 active:scale-95 cursor-pointer" title="Master Power Switch: Start or Pause Strategy Engine (Stops background polling & AI grading)">
                <span id="engine-status-indicator" class="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
                <span id="engine-status-label">ENGINE: ACTIVE</span>
              </button>

              <!-- EXECUTION MODE (VIRTUAL / LIVE) -->
              <button id="toggle-mode-btn" onclick="toggleExecutionMode()" class="px-2.5 py-1 text-xs font-bold rounded-lg transition flex items-center gap-1.5 shadow border border-gray-700 bg-[#1e293b]/80" title="Click to toggle between VIRTUAL (Simulated) and LIVE TRADING">
                <span id="mode-status-indicator" class="w-2 h-2 rounded-full"></span>
                <span id="mode-status-label">VIRTUAL</span>
              </button>

              <!-- AUTO_ORDER Toggle Switch -->
              <button id="toggle-auto-btn" onclick="toggleAutoOrder()" class="px-2.5 py-1 text-xs font-bold rounded-lg transition flex items-center gap-1.5 shadow border border-gray-700 bg-[#1e293b]/80" title="Toggle AI Automatic Order Placement">
                <span id="auto-status-indicator" class="w-2 h-2 rounded-full"></span>
                <span id="auto-status-label">AUTO: ON</span>
              </button>

              <!-- Audio Synthesizer Toggle -->
              <button onclick="toggleAudioSound()" id="sound-toggle-btn" class="bg-gray-800 hover:bg-gray-700 active:scale-95 text-emerald-400 text-xs font-semibold px-2 py-1 rounded-lg transition border border-gray-700 flex items-center gap-1 shadow" title="Toggle Synthesized Audio Chimes">
                <span id="sound-icon">🔊</span>
              </button>

              <!-- Shortcuts Cheat Sheet Button -->
              <button onclick="openHotkeysModal()" class="bg-gray-800 hover:bg-gray-700 active:scale-95 text-gray-300 text-xs font-semibold px-2 py-1 rounded-lg transition border border-gray-700 flex items-center shadow" title="Keyboard Shortcuts Cheat Sheet (?)">
                <span class="font-mono text-xs">⌨️</span>
              </button>

              <!-- Emergency Square-Off Button -->
              <button onclick="confirmEmergencySquareOff()" id="square-off-btn" class="bg-rose-950/70 hover:bg-rose-900 active:scale-95 text-rose-300 hover:text-white text-xs font-bold px-2.5 py-1 rounded-lg transition border border-rose-700/60 shadow flex items-center gap-1.5" title="Close all open intraday positions and cancel open orders immediately (Shift + Q)">
                <span>🛑</span>
                <span>Square Off</span>
              </button>

              __SIM_HEADER_BTN__

              <!-- Refresh Button -->
              <button onclick="fetchFeed()" class="bg-gray-800 hover:bg-gray-700 text-gray-200 text-xs font-semibold p-1 rounded-lg transition border border-gray-700" title="Refresh Table">
                🔄
              </button>
            </div>
          </div>

          <!-- Right: Inline High-Density KPI Badges -->
          <div class="flex items-center gap-2 text-[11px] font-mono flex-wrap">
            <div class="bg-[#131b2e] border border-gray-800/80 px-2.5 py-1 rounded-lg flex items-center gap-1.5 shadow-sm">
              <span class="text-gray-400">Filtered:</span>
              <span id="stat-total" class="font-bold text-white">0</span>
            </div>
            <div class="bg-[#131b2e] border border-gray-800/80 px-2.5 py-1 rounded-lg flex items-center gap-1.5 shadow-sm">
              <span class="text-emerald-400">🟢 Bull:</span>
              <span id="stat-bullish" class="font-bold text-emerald-400">0</span>
            </div>
            <div class="bg-[#131b2e] border border-gray-800/80 px-2.5 py-1 rounded-lg flex items-center gap-1.5 shadow-sm">
              <span class="text-rose-400">🔴 Bear:</span>
              <span id="stat-bearish" class="font-bold text-rose-400">0</span>
            </div>
            <div class="bg-[#131b2e] border border-gray-800/80 px-2.5 py-1 rounded-lg flex items-center gap-1.5 shadow-sm">
              <span class="text-indigo-300">🎯 Orders:</span>
              <span id="stat-placed" class="font-bold text-indigo-300">0</span>
            </div>
            <div class="bg-[#131b2e] border border-gray-800/80 px-2.5 py-1 rounded-lg flex items-center gap-1.5 shadow-sm">
              <span class="text-amber-400">⏳ Pending:</span>
              <span id="stat-pending" class="font-bold text-amber-300">0</span>
            </div>
            <div class="bg-[#131b2e] border border-gray-800/80 px-2.5 py-1 rounded-lg flex items-center gap-1.5 shadow-sm">
              <span class="text-cyan-400">🛡️ Risk:</span>
              <div id="risk-gauge-bars" class="flex items-center gap-0.5">
                <span class="w-1.5 h-2.5 rounded-xs bg-gray-700 border border-gray-600"></span>
                <span class="w-1.5 h-2.5 rounded-xs bg-gray-700 border border-gray-600"></span>
                <span class="w-1.5 h-2.5 rounded-xs bg-gray-700 border border-gray-600"></span>
              </div>
              <span id="risk-gauge-text" class="font-bold text-emerald-400">0/3</span>
            </div>
          </div>

        </div>
      </div>

      <!-- TABLE TOOLBAR (TABS & SEARCH) -->
      <div class="max-w-[1600px] mx-auto w-full px-6 pt-3 pb-2 flex flex-wrap items-center justify-between gap-3">
        
        <!-- Filter Dropdown & Scope Indicator -->
        <div class="flex items-center flex-wrap gap-2.5">
          <div class="relative flex items-center">
            <span class="absolute left-2.5 text-xs text-gray-400 pointer-events-none">🎯</span>
            <select id="feed-filter-select" onchange="setFilter(this.value)" class="bg-[#111827] border border-gray-700/80 hover:border-emerald-500/60 text-xs font-semibold text-gray-200 rounded-lg pl-7 pr-8 py-1.5 focus:outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 shadow-sm transition appearance-none cursor-pointer" title="Filter table signals by conviction verdict or noise">
              <option value="ALL" id="opt-filter-all">⚡ All Actionable (0)</option>
              <option value="BULLISH" id="opt-filter-bullish">🟢 Bullish Only (0)</option>
              <option value="BEARISH" id="opt-filter-bearish">🔴 Bearish Only (0)</option>
              <option value="PENDING" id="opt-filter-pending">⏳ Pending Approval (0)</option>
              <option value="NOISE" id="opt-filter-noise">🔇 Noise Suppressed (0)</option>
            </select>
            <span class="absolute right-2.5 text-[10px] text-gray-400 pointer-events-none">▼</span>
          </div>

          <!-- Scope Indicator (Today / All History Toggle) -->
          <button onclick="toggleScopeMode()" id="btn-session-scope" class="flex items-center gap-1.5 bg-[#111827] hover:bg-[#162032] border border-gray-800 px-2.5 py-1.5 rounded-lg shadow-sm transition active:scale-95" title="Toggle between Today and Historical Signals">
            <span class="text-xs text-gray-400">📅</span>
            <span id="session-scope-badge" class="px-2 py-0.5 text-[11px] font-mono font-bold bg-emerald-950/80 text-emerald-300 border border-emerald-800/80 rounded flex items-center gap-1">
              <span class="w-1.5 h-1.5 rounded-full bg-emerald-400"></span>
              <span id="session-scope-text">Today Only</span>
            </span>
          </button>
        </div>

        <!-- Search input & View Controls -->
        <div class="flex items-center flex-wrap gap-2.5">
          <div class="relative">
            <input type="text" id="search-input" onkeyup="renderFeed()" placeholder="Search symbol or catalyst..." class="bg-[#111827] border border-gray-800 text-xs text-gray-200 placeholder-gray-500 rounded-lg pl-8 pr-3 py-1.5 focus:outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 w-52 sm:w-60 transition">
            <span class="absolute left-2.5 top-2 text-xs text-gray-500">🔍</span>
          </div>

          <!-- Load All History Button -->
          <button onclick="loadFeedHistory()" id="btn-load-history" class="px-2.5 py-1.5 text-xs font-semibold rounded-lg bg-[#162032] hover:bg-[#1f293d] text-gray-300 hover:text-white border border-gray-700/80 hover:border-gray-600 transition flex items-center gap-1.5 shadow-sm active:scale-95" title="Load all past evaluated signals from database">
            <span>📜</span>
            <span>Show History (DB)</span>
          </button>

          <!-- Clear Display Button -->
          <button onclick="clearFeedList()" id="btn-clear-feed" class="px-2.5 py-1.5 text-xs font-semibold rounded-lg bg-[#162032] hover:bg-rose-950/40 text-gray-300 hover:text-rose-200 border border-gray-700/80 hover:border-rose-500/50 transition flex items-center gap-1.5 shadow-sm active:scale-95" title="Clear displayed table list from screen (Database remains untouched)">
            <span>🗑️</span>
            <span>Clear Display</span>
          </button>
        </div>

      </div>

  <!-- TABLE CONTAINER -->
  <main class="max-w-[1600px] mx-auto w-full px-6 pb-8 flex-1 flex flex-col">
    <div class="bg-[#111827] border border-gray-800 rounded-xl shadow-xl overflow-hidden flex-1 flex flex-col">
      <div class="overflow-x-auto custom-scrollbar flex-1">
        <table class="w-full text-left border-collapse min-w-[1100px]" id="feed-table">
          
          <!-- TABLE HEADER -->
          <thead>
            <tr class="bg-[#162032] border-b border-gray-800 text-[11px] font-bold text-gray-400 uppercase tracking-wider">
              <th class="py-3.5 px-4 w-32">Symbol / SecID</th>
              <th class="py-3.5 px-4 w-36">Date / Time</th>
              <th class="py-3.5 px-4">Catalyst & AI Rationale</th>
              <th class="py-3.5 px-4 w-40 text-center">LLM Verdict</th>
              <th class="py-3.5 px-4 w-48 text-right">Bracket Pricing</th>
              <th class="py-3.5 px-4 w-48 text-center" title="Real-time market price & P&L relative to Limit price (or Traded price if executed)">Live Market & P&L</th>
              <th class="py-3.5 px-4 w-52 text-center">Order Status / Action</th>
            </tr>
          </thead>

          <!-- TABLE BODY -->
          <tbody id="table-body" class="divide-y divide-gray-800/80 text-xs">
            <!-- Dynamic Rows -->
          </tbody>

        </table>
      </div>

      <!-- EMPTY STATE -->
      <div id="empty-state" class="p-14 text-center bg-[#111827] my-auto">
        <div class="relative w-16 h-16 mx-auto mb-4 flex items-center justify-center">
          <span id="empty-radar-ping" class="absolute w-16 h-16 rounded-full bg-emerald-500/10 animate-ping"></span>
          <span id="empty-radar-pulse" class="absolute w-12 h-12 rounded-full bg-emerald-500/20 animate-pulse"></span>
          <div id="empty-radar-box" class="w-10 h-10 rounded-full bg-[#162032] border border-emerald-500/40 flex items-center justify-center text-xl shadow-lg">
            <span id="empty-radar-icon">📡</span>
          </div>
        </div>
        <h3 id="empty-state-heading" class="text-sm font-bold text-white uppercase tracking-wider flex items-center justify-center gap-2">
          <span>Live Radar Active — Scanning NSE Corporate Feed</span>
        </h3>
        <p id="empty-state-desc" class="text-xs text-gray-400 max-w-md mx-auto mt-1.5 mb-3 leading-relaxed">
          Actively monitoring 228 F&O tickers on NSE. The AI filter automatically discards routine compliance noise and will alert here the moment an actionable market catalyst breaks.
        </p>
        <div id="empty-state-pill" class="inline-flex items-center gap-2 bg-[#0e1422] border border-gray-800 px-3.5 py-1.5 rounded-lg text-[11px] text-gray-300 font-mono mb-4 shadow-sm">
          <span id="empty-state-dot" class="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
          <span>Last Exchange Scan: <span id="empty-last-check" class="text-emerald-400 font-bold">Just now</span></span>
          <span class="text-gray-600">•</span>
          <span>Status: <span id="empty-state-status-text" class="text-indigo-300 font-semibold">Listening for catalysts...</span></span>
        </div>
        __SIM_EMPTY_BTN__
      </div>

    </div>
  </main>
  </div> <!-- /workspace-st-news -->

  <!-- WORKSPACE 2: ST-14 BULLISH CE OPTIONS STRATEGY WORKSPACE -->
  <!-- WORKSPACE 2: ST-14 BULLISH CE OPTIONS STRATEGY WORKSPACE -->
  <div id="workspace-st14" class="strategy-workspace-pane hidden max-w-[1600px] mx-auto px-4 py-3 w-full space-y-3 flex-1">
    
    <!-- Strategy Header & Status Banner (Ultra-Compact) -->
    <div class="bg-[#111827] border border-gray-800 rounded-xl px-4 py-2.5 shadow-md flex flex-col md:flex-row md:items-center justify-between gap-2.5">
      <div class="flex items-center gap-2.5 flex-wrap min-w-0">
        <span class="text-xl">🚀</span>
        <span class="px-2 py-0.5 rounded text-xs font-mono font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/40">ST-14</span>
        <h2 class="text-sm font-bold text-white tracking-wide">Bullish CE Options Strategy</h2>
        <span id="st14-status-pill" class="px-2 py-0.5 rounded-full text-[11px] font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 flex items-center gap-1.5">
          <span id="st14-status-dot" class="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
          <span id="st14-status-txt">ACTIVE</span>
        </span>
        <span class="hidden xl:inline text-gray-700">|</span>
        <p class="text-[11px] text-gray-400 truncate max-w-xl hidden lg:block">
          Dual-frequency: 1-Hr Discovery (10:15–14:00) across 228 F&amp;O stocks + 5-Min Trigger Monitoring (LTP &gt; Breakout High) with 1-OTM CE Super Orders (+40% TP, -20% SL, 2.0 pts trail).
        </p>
      </div>

      <!-- Strategy-Specific Controls Group -->
      <div class="flex items-center gap-1.5 flex-shrink-0 flex-wrap">
        <!-- MASTER STRATEGY ENGINE POWER BUTTON (ACTIVE / PAUSED) -->
        <button id="st14-toggle-engine-btn" onclick="toggleStrategyEngine('st14_bullish_ce')" class="px-2.5 py-1 text-xs font-bold rounded-lg transition flex items-center gap-1.5 shadow border border-emerald-500/50 bg-emerald-950/70 text-emerald-300 hover:bg-emerald-900 active:scale-95 cursor-pointer" title="Master Power Switch: Start or Pause ST-14 Strategy Engine (Suspends 1-Hr scan & 5-Min breakout monitor)">
          <span id="st14-engine-status-indicator" class="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
          <span id="st14-engine-status-label">ENGINE: ACTIVE</span>
        </button>

        <!-- EXECUTION MODE (VIRTUAL / LIVE) -->
        <button id="st14-toggle-mode-btn" onclick="toggleExecutionMode('st14_bullish_ce')" class="px-2.5 py-1 text-xs font-bold rounded-lg transition flex items-center gap-1.5 shadow border border-amber-500/40 bg-amber-600/90 text-amber-100 hover:bg-amber-600 active:scale-95 cursor-pointer" title="Click to toggle between VIRTUAL (Paper Trading) and LIVE TRADING">
          <span id="st14-mode-status-indicator" class="w-2 h-2 rounded-full bg-amber-300"></span>
          <span id="st14-mode-status-label">VIRTUAL</span>
        </button>

        <!-- AUTO_ORDER Toggle Switch -->
        <button id="st14-toggle-auto-btn" onclick="toggleAutoOrder('st14_bullish_ce')" class="px-2.5 py-1 text-xs font-bold rounded-lg transition flex items-center gap-1.5 shadow border border-emerald-400/40 bg-emerald-600 text-white hover:bg-emerald-500 active:scale-95 cursor-pointer" title="Toggle Automated 1-OTM CE Super Order Placement">
          <span id="st14-auto-status-indicator" class="w-2 h-2 rounded-full bg-white animate-pulse"></span>
          <span id="st14-auto-status-label">ENABLED (Auto-Place)</span>
        </button>

        <!-- Vertical Divider -->
        <div class="h-4 w-px bg-gray-800 hidden sm:block"></div>

        <!-- Product Type Toggle -->
        <button id="st14-btn-product" onclick="toggleSt14Product()" class="px-2.5 py-1 text-xs font-bold rounded-lg transition flex items-center gap-1 shadow bg-cyan-950/70 text-cyan-300 hover:bg-cyan-900 border border-cyan-500/40 active:scale-95 cursor-pointer" title="Toggle between INTRADAY (MIS with 3:00 PM square-off) and DELIVERY (MARGIN carry-forward)">
          <span id="st14-btn-product-txt">⏰ INTRADAY</span>
        </button>

        <!-- Trigger Check -->
        <button id="st14-btn-trigger-check" onclick="runSt14TriggerCheckNow()" class="bg-amber-950/80 hover:bg-amber-900 border border-amber-500/50 text-amber-300 font-bold text-xs px-2.5 py-1 rounded-lg shadow transition flex items-center gap-1.5 active:scale-95 cursor-pointer" title="Trigger immediate 5-minute check on all watchlisted breakout candidates">
          <span id="st14-trigger-btn-spinner" class="hidden animate-spin">🔄</span>
          <span>🎯 Check Triggers</span>
        </button>

        <!-- 1-Hr Scan -->
        <button id="st14-btn-hourly-scan" onclick="runSt14HourlyScanNow()" class="bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white font-bold text-xs px-3 py-1 rounded-lg shadow transition flex items-center gap-1.5 active:scale-95 cursor-pointer" title="Trigger full 1-Hour Discovery Scanner across the 228 F&O universe">
          <span id="st14-hourly-btn-spinner" class="hidden animate-spin">🔄</span>
          <span>⚡ 1-Hr Scan</span>
        </button>

        <!-- Emergency Square Off -->
        <button onclick="confirmSt14SquareOff()" id="st14-btn-square-off" class="bg-rose-950/70 hover:bg-rose-900 active:scale-95 text-rose-300 hover:text-white text-xs font-bold px-2.5 py-1 rounded-lg transition border border-rose-700/60 shadow flex items-center gap-1.5 cursor-pointer" title="Close all open ST-14 option positions immediately">
          <span>🛑</span>
          <span>Square Off</span>
        </button>
      </div>
    </div>

    <!-- Live Dual-Frequency Radar & Telemetry + Parameter Bar (Unified Compact) -->
    <div class="bg-gradient-to-r from-[#0d1527] via-[#111827] to-[#0d1527] border border-gray-800 rounded-xl p-3 px-4 shadow-md space-y-2.5">
      
      <!-- Tier 1: Real-Time Monitoring Telemetry Strip -->
      <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 items-center divide-y lg:divide-y-0 lg:divide-x divide-gray-800/80">
        
        <!-- Telemetry Item 1: Engine Radar Status -->
        <div class="flex items-center gap-2.5 pr-2">
          <div class="relative flex h-3 w-3 items-center justify-center flex-shrink-0">
            <span id="st14-radar-ping" class="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
            <span id="st14-radar-dot" class="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
          </div>
          <div>
            <div class="text-[9px] uppercase font-bold text-gray-400 tracking-wider">Dual-Frequency Radar</div>
            <div id="st14-radar-status-text" class="text-xs font-bold text-emerald-400 font-mono flex items-center gap-1.5 leading-none mt-0.5">
              ACTIVE DUAL LOOP
            </div>
            <div id="st14-radar-subtext" class="text-[10px] text-gray-500 font-mono mt-0.5">1h Discovery + 5m Poller</div>
          </div>
        </div>

        <!-- Telemetry Item 2: Tier 1 - 1-Hour Discovery Scanner -->
        <div class="pt-2 sm:pt-0 lg:px-3 space-y-0.5">
          <div class="flex items-center justify-between">
            <span class="text-[9px] uppercase font-bold text-gray-400 tracking-wider">⚡ Tier 1: 1-Hr Scanner</span>
            <span id="st14-hourly-count-badge" class="px-1.5 py-0.2 rounded text-[10px] font-mono font-bold bg-indigo-950 text-indigo-300 border border-indigo-800/60">0 Discovered</span>
          </div>
          <div class="flex items-center justify-between text-xs font-mono">
            <span class="text-gray-400 text-[11px]">Last: <span id="st14-hourly-last-time" class="text-white font-semibold">-</span></span>
            <span class="text-gray-400 text-[11px]">Next: <span id="st14-hourly-next-time" class="text-indigo-300 font-semibold">-</span></span>
          </div>
          <div class="text-[9px] text-gray-500 font-mono">10:15, 11:15, 12:15, 13:15, 14:00</div>
        </div>

        <!-- Telemetry Item 3: Tier 2 - 5-Min Trigger Poller -->
        <div class="pt-2 sm:pt-0 lg:px-3 space-y-0.5">
          <div class="flex items-center justify-between">
            <span class="text-[9px] uppercase font-bold text-gray-400 tracking-wider">🎯 Tier 2: 5-Min Poller</span>
            <span id="st14-watchlist-count-badge" class="px-1.5 py-0.2 rounded text-[10px] font-mono font-bold bg-amber-950 text-amber-300 border border-amber-800/60">0 Watching</span>
          </div>
          <div class="flex items-center justify-between text-xs font-mono">
            <span class="text-gray-400 text-[11px]">Last: <span id="st14-5min-last-time" class="text-white font-semibold">-</span></span>
            <span class="text-gray-400 text-[11px]">Next: <span id="st14-5min-next-timer" class="text-amber-300 font-semibold">~5m</span></span>
          </div>
          <div class="text-[9px] text-gray-500 font-mono">Trigger: LTP &gt; Breakout High</div>
        </div>

        <!-- Telemetry Item 4: Orders & Capacity -->
        <div class="pt-2 sm:pt-0 lg:pl-3 space-y-0.5">
          <div class="flex items-center justify-between">
            <span class="text-[9px] uppercase font-bold text-gray-400 tracking-wider">Super Orders</span>
            <span id="st14-mode-badge" class="px-1.5 py-0.2 rounded text-[9px] font-bold bg-emerald-950 text-emerald-300 border border-emerald-800">VIRTUAL</span>
          </div>
          <div class="flex items-center justify-between text-xs font-mono">
            <span class="text-gray-400 text-[11px]">Slots: <span id="st14-capacity-text" class="text-white font-semibold">0 / 5 Slots</span></span>
            <span class="text-gray-400 text-[11px]">Auto: <span id="st14-auto-order-text" class="text-emerald-400 font-semibold">ON</span></span>
          </div>
          <div class="text-[9px] text-gray-500 font-mono">Cutoff: 14:00 | Squaring: 15:00</div>
        </div>

      </div>

      <!-- Tier 2: Parameter & Breadth Micro-Pills Bar -->
      <div class="pt-2 border-t border-gray-800/60 grid grid-cols-2 sm:grid-cols-5 gap-2">
        <!-- Breadth Micro Card -->
        <div id="st14-card-breadth" class="bg-[#0b0f19]/60 border border-gray-800/70 px-2.5 py-1.5 rounded-lg">
          <div class="text-[9px] uppercase font-bold text-gray-400 tracking-wider">Macro Breadth</div>
          <div class="text-[11px] font-bold flex items-center gap-1 truncate mt-0.5">
            <span id="st14-breadth-dot" class="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse flex-shrink-0"></span>
            <span id="st14-breadth-title" class="text-emerald-400 truncate">NIFTY &amp; BANKNIFTY GREEN</span>
          </div>
          <div id="st14-card-breadth-detail" class="text-[9px] text-gray-500 font-mono truncate">Both indices positive</div>
        </div>

        <!-- Option Selection Micro Card -->
        <div class="bg-[#0b0f19]/60 border border-gray-800/70 px-2.5 py-1.5 rounded-lg">
          <div class="text-[9px] uppercase font-bold text-gray-400 tracking-wider">Option Selection</div>
          <div class="text-[11px] font-bold text-blue-400 font-mono truncate mt-0.5">1-OTM Call (CE)</div>
          <div id="st14-card-expiry-rule" class="text-[9px] text-gray-400 font-mono truncate">Date &le; 15th = Curr Month</div>
        </div>

        <!-- Super Order Bracket Micro Card -->
        <div class="bg-[#0b0f19]/60 border border-gray-800/70 px-2.5 py-1.5 rounded-lg">
          <div class="text-[9px] uppercase font-bold text-gray-400 tracking-wider">Order Bracket</div>
          <div class="text-[11px] font-bold text-emerald-400 font-mono truncate mt-0.5">+40% TP / -20% SL</div>
          <div class="text-[9px] text-gray-400 font-mono truncate">Trailing: 2.0 Pts Jump</div>
        </div>

        <!-- Capital Allocation Micro Card -->
        <div class="bg-[#0b0f19]/60 border border-gray-800/70 px-2.5 py-1.5 rounded-lg">
          <div class="text-[9px] uppercase font-bold text-gray-400 tracking-wider">Capital Allocation</div>
          <div id="st14-card-capital" class="text-[11px] font-bold text-emerald-400 font-mono truncate mt-0.5">₹25,000 / trade</div>
          <div class="text-[9px] text-gray-400 font-mono truncate">Max 5 Open Positions</div>
        </div>

        <!-- Execution Timing Micro Card -->
        <div class="bg-[#0b0f19]/60 border border-gray-800/70 px-2.5 py-1.5 rounded-lg">
          <div class="text-[9px] uppercase font-bold text-gray-400 tracking-wider">Timing &amp; Cutoff</div>
          <div class="text-[11px] font-bold text-amber-400 font-mono truncate mt-0.5">10:15 - 14:00 IST</div>
          <div class="text-[9px] text-gray-400 font-mono truncate">15:00 Square-Off</div>
        </div>
      </div>

    </div>

    <!-- Active Breakout Candidates Watchlist (Tier 2 Polling Queue / Search Results) -->
    <div class="bg-[#111827] border border-gray-800 rounded-xl p-4 shadow-md space-y-3">
      <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
        <div class="flex items-center gap-2 flex-wrap">
          <span class="text-sm font-bold text-white">🎯 Active Breakout Watchlist (Tier 2 - 5-Min Trigger Poller Queue)</span>
          <span id="st14-watchlist-table-badge" class="text-xs font-mono text-amber-300 bg-amber-950/60 border border-amber-800/50 px-2.5 py-0.5 rounded-full">0 Candidates</span>
        </div>
        <div class="flex items-center gap-2">
          <button onclick="runSt14HourlyScanNow()" class="text-xs font-bold text-emerald-300 hover:text-emerald-200 bg-emerald-950/60 hover:bg-emerald-900/60 border border-emerald-700/60 px-2.5 py-1 rounded-lg transition flex items-center gap-1.5 active:scale-95 cursor-pointer shadow" title="Scan 228 F&O universe for 5D/5H breakouts and rising VWAP">
            <span>⚡ Run 1-Hr Discovery Scan</span>
          </button>
          <button onclick="runSt14TriggerCheckNow()" class="text-xs font-bold text-amber-300 hover:text-amber-200 bg-amber-950/60 hover:bg-amber-900/60 border border-amber-700/60 px-2.5 py-1 rounded-lg transition flex items-center gap-1.5 active:scale-95 cursor-pointer shadow" title="Poll active watchlist candidates for breakout breach">
            <span>🎯 Check Triggers Now</span>
          </button>
        </div>
      </div>
      <p class="text-[11px] text-gray-400 leading-normal">
        Discovered by the 1-hour scanner. Monitored every 5 minutes during market hours. Automatically executes 1-OTM Call Option Super Order when live price crosses Breakout Candle High (LTP &gt; Breakout High).
      </p>

      <div id="st14-watchlist-container" class="overflow-x-auto">
        <!-- Rendered dynamically -->
      </div>
    </div>

    <!-- Active Positions / Super Orders Section -->
    <div class="bg-[#111827] border border-gray-800 rounded-xl p-4 shadow-md space-y-3">
      <div class="flex items-center justify-between">
        <div class="flex items-center gap-2">
          <span class="text-sm font-bold text-white">📦 ST-14 Active Option Positions &amp; Super Orders</span>
          <span id="st14-positions-count-badge" class="text-xs font-mono text-emerald-400 bg-emerald-950/60 border border-emerald-800/50 px-2.5 py-0.5 rounded-full">0 Open Positions</span>
        </div>
        <div class="text-xs font-mono text-gray-400">
          Unrealized P&amp;L: <span id="st14-total-pnl-val" class="font-bold text-emerald-400">₹0.00</span>
        </div>
      </div>

      <div id="st14-positions-container" class="overflow-x-auto">
        <!-- Rendered dynamically -->
      </div>
    </div>

  </div> <!-- /workspace-st14 -->

  <!-- WORKSPACE 3: MODULAR STRATEGY WORKSPACE (For ST-15, ST-08, ST-01, ST-OB) -->
  <div id="workspace-st-modular" class="strategy-workspace-pane hidden max-w-[1600px] mx-auto px-6 py-6 w-full space-y-6 flex-1">

    
    <!-- Strategy Header & Status Banner -->
    <div class="bg-[#111827] border border-gray-800 rounded-2xl p-6 shadow-xl flex flex-col md:flex-row md:items-center justify-between gap-4">
      <div class="space-y-1.5">
        <div class="flex items-center gap-2.5">
          <span id="mod-strat-icon" class="text-2xl">📈</span>
          <span id="mod-strat-code" class="px-2.5 py-0.5 rounded text-xs font-mono font-bold bg-blue-500/20 text-blue-300 border border-blue-500/40">ST-15</span>
          <h2 id="mod-strat-title" class="text-lg font-bold text-white tracking-wide">NIFTY 200 LargeCap Momentum</h2>
          <span id="mod-strat-status-badge" class="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/40">🟢 READY</span>
        </div>
        <p id="mod-strat-desc" class="text-xs text-gray-400 max-w-3xl leading-relaxed">
          Multi-timeframe Heikin-Ashi EMA momentum strategy with dynamic trailing stop-loss on Nifty 200 leaders.
        </p>
      </div>

      <div class="flex items-center gap-3">
        <div class="bg-[#0b0f19] border border-gray-800 px-3.5 py-2 rounded-xl text-right font-mono">
          <div class="text-[10px] uppercase text-gray-500 font-bold">Execution Engine</div>
          <div id="mod-strat-engine-mode" class="text-xs font-bold text-amber-400">🛡️ VIRTUAL MODE</div>
        </div>
        <button onclick="launchModularStrategyScan()" id="btn-run-modular-strat" class="bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white font-bold text-xs px-4 py-2.5 rounded-xl shadow-lg shadow-blue-600/30 transition flex items-center gap-2 active:scale-95">
          <span>⚡</span>
          <span>Run Strategy Screener</span>
        </button>
      </div>
    </div>

    <!-- Key Parameters & Metadata Row -->
    <div class="grid grid-cols-2 sm:grid-cols-4 gap-4">
      <div class="bg-[#111827] border border-gray-800 p-4 rounded-xl space-y-1">
        <span class="text-[10px] uppercase font-bold text-gray-500 tracking-wider">Trading Universe</span>
        <div id="mod-strat-universe" class="text-xs font-bold text-gray-200">NIFTY 200 LargeCap</div>
      </div>
      <div class="bg-[#111827] border border-gray-800 p-4 rounded-xl space-y-1">
        <span class="text-[10px] uppercase font-bold text-gray-500 tracking-wider">Candle Timeframe</span>
        <div id="mod-strat-timeframe" class="text-xs font-bold text-blue-400 font-mono">15m / Daily Heikin-Ashi</div>
      </div>
      <div class="bg-[#111827] border border-gray-800 p-4 rounded-xl space-y-1">
        <span class="text-[10px] uppercase font-bold text-gray-500 tracking-wider">Risk Profile & Bracket</span>
        <div id="mod-strat-risk" class="text-xs font-bold text-amber-400 font-mono">1.5% SL / 4.5% TP (1:3 R:R)</div>
      </div>
      <div class="bg-[#111827] border border-gray-800 p-4 rounded-xl space-y-1">
        <span class="text-[10px] uppercase font-bold text-gray-500 tracking-wider">Allocated Capital</span>
        <div id="mod-strat-capital" class="text-xs font-bold text-emerald-400 font-mono">₹50,000 / trade</div>
      </div>
    </div>

    <!-- Strategy Live Triggers & Execution Feed Area -->
    <div class="bg-[#111827] border border-gray-800 rounded-2xl p-6 shadow-xl space-y-4">
      <div class="flex items-center justify-between">
        <div class="flex items-center gap-2">
          <span class="text-sm font-bold text-white">Live Strategy Triggers & Signal Monitor</span>
          <span id="mod-signals-count" class="text-xs font-mono text-blue-400 bg-blue-950/60 border border-blue-800/50 px-2 py-0.5 rounded-full">0 Signals Generated</span>
        </div>
        <div class="text-xs text-gray-400">
          Dhan Automated Order Routing: <span class="text-emerald-400 font-bold">Enabled</span>
        </div>
      </div>

      <div id="mod-strat-empty" class="text-center py-12 border border-dashed border-gray-800 rounded-xl bg-[#0b0f19]/60 space-y-3">
        <div class="w-12 h-12 rounded-full bg-blue-500/10 border border-blue-500/30 flex items-center justify-center text-2xl mx-auto text-blue-400">
          📡
        </div>
        <h3 class="text-sm font-bold text-white">Strategy Engine Ready for Execution</h3>
        <p class="text-xs text-gray-400 max-w-md mx-auto">
          Click <strong class="text-blue-400">Run Strategy Screener</strong> or toggle on auto-trading to stream live multi-timeframe signals from the DhanHQ market feed.
        </p>
        <div class="pt-2">
          <button onclick="switchMainTab('scanner')" class="text-xs font-semibold text-blue-400 hover:text-blue-300 transition flex items-center gap-1 mx-auto">
            <span>View technical scanner rules in Scanner Studio →</span>
          </button>
        </div>
      </div>
    </div>

  </div> <!-- /workspace-st-modular -->

  </div> <!-- /main-tab-strategies -->

  <!-- TECHNICAL SCANNER TAB CONTAINER -->
  <div id="main-tab-scanner" class="max-w-[1600px] mx-auto px-6 py-6 w-full space-y-6 flex-1">
    
    <!-- View 1: Scanners Directory & Pro Studio (Home View) -->
    <section id="view-home" class="space-y-6">
      
      <!-- Top Overview Bar -->
      <div class="flex flex-col md:flex-row md:items-center justify-between gap-4 bg-slate-900/80 p-6 rounded-3xl border border-slate-800 shadow-xl">
        <div class="space-y-1.5">
          <div class="inline-flex items-center space-x-2 px-3 py-1 rounded-full bg-sky-500/10 border border-sky-500/20 text-sky-400 text-xs font-semibold">
            <i data-lucide="sparkles" class="w-3.5 h-3.5"></i>
            <span>Indian Equities Algorithmic Scanners</span>
          </div>
          <h2 class="text-xl md:text-2xl font-black text-white tracking-tight">
            Scanner Studio & Strategy Studio
          </h2>
          <p class="text-xs text-slate-400 max-w-2xl leading-relaxed">
            Select a strategy on the left to customize live parameters (Universe, Timeframe, Proximity & Multipliers), then launch the real-time scan.
          </p>
        </div>
        <div class="flex items-center space-x-3 flex-wrap gap-y-2">
          <div id="dhan-status-badge" class="flex items-center space-x-2 px-3 py-1.5 rounded-full bg-slate-800 border border-slate-700">
            <span class="w-2 h-2 rounded-full bg-amber-400 animate-pulse"></span>
            <span class="text-xs text-slate-300 font-medium">Checking DhanHQ API...</span>
          </div>
          <div class="relative w-full md:w-56">
            <i data-lucide="search" class="w-4 h-4 text-slate-400 absolute left-3.5 top-1/2 -translate-y-1/2 pointer-events-none"></i>
            <input
              type="text"
              id="home-scanner-search"
              placeholder="Search strategy..."
              class="w-full pl-10 pr-4 py-2 bg-slate-950/80 border border-slate-700 rounded-xl text-xs text-white placeholder-slate-500 focus:outline-none focus:border-sky-500 shadow-inner"
            />
          </div>
        </div>
      </div>

      <!-- Master-Detail 2-Column Studio Workspace -->
      <div class="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        
        <!-- LEFT COLUMN: Master Scanner Selector (4 Cols) -->
        <div class="lg:col-span-4 col-span-12 space-y-3">
          <div class="flex items-center justify-between px-1">
            <span class="text-xs font-bold text-slate-400 uppercase tracking-wider flex items-center space-x-1.5">
              <i data-lucide="layers" class="w-3.5 h-3.5 text-sky-400"></i>
              <span>Available Strategies</span>
            </span>
            <span id="scanners-count-badge" class="text-[11px] font-mono text-sky-400 bg-sky-950/60 border border-sky-800/40 px-2 py-0.5 rounded-full">-- Registered</span>
          </div>

          <!-- Category Filter Tabs -->
          <div class="flex items-center space-x-1.5 overflow-x-auto pb-1 text-xs no-scrollbar" id="home-category-tabs">
            <button data-cat-filter="ALL" class="home-cat-tab px-3 py-1.5 rounded-xl font-semibold bg-sky-500/20 text-sky-300 border border-sky-500/40 whitespace-nowrap transition">All</button>
            <button data-cat-filter="Reversal" class="home-cat-tab px-3 py-1.5 rounded-xl font-semibold bg-slate-800/60 text-slate-400 border border-transparent hover:text-white whitespace-nowrap transition">Reversal</button>
            <button data-cat-filter="Breakout" class="home-cat-tab px-3 py-1.5 rounded-xl font-semibold bg-slate-800/60 text-slate-400 border border-transparent hover:text-white whitespace-nowrap transition">Breakout</button>
            <button data-cat-filter="Smart Money Concepts" class="home-cat-tab px-3 py-1.5 rounded-xl font-semibold bg-slate-800/60 text-slate-400 border border-transparent hover:text-white whitespace-nowrap transition">SMC</button>
            <button data-cat-filter="Trend Following" class="home-cat-tab px-3 py-1.5 rounded-xl font-semibold bg-slate-800/60 text-slate-400 border border-transparent hover:text-white whitespace-nowrap transition">Trend</button>
            <button data-cat-filter="Chart Patterns" class="home-cat-tab px-3 py-1.5 rounded-xl font-semibold bg-slate-800/60 text-slate-400 border border-transparent hover:text-white whitespace-nowrap transition">Patterns</button>
            <button data-cat-filter="Support & Resistance" class="home-cat-tab px-3 py-1.5 rounded-xl font-semibold bg-slate-800/60 text-slate-400 border border-transparent hover:text-white whitespace-nowrap transition">S&R</button>
            <button data-cat-filter="Momentum" class="home-cat-tab px-3 py-1.5 rounded-xl font-semibold bg-slate-800/60 text-slate-400 border border-transparent hover:text-white whitespace-nowrap transition">Momentum</button>
          </div>

          <!-- Scanner Navigation List -->
          <div id="scanner-nav-list" class="space-y-2.5 max-h-[640px] overflow-y-auto pr-1">
            <!-- Populated dynamically by app.js -->
          </div>
        </div>

        <!-- RIGHT COLUMN: Active Scanner Studio & Parameters (8 Cols) -->
        <div class="lg:col-span-8 col-span-12">
          <div id="scanner-studio-panel" class="bg-slate-900/90 border border-slate-800 rounded-3xl p-6 md:p-8 shadow-2xl space-y-6">
            <!-- Populated dynamically for selected scanner by app.js -->
          </div>
        </div>

      </div>

    </section>

    <!-- View 2: Scan Results View -->
    <section id="view-results" class="hidden space-y-6">
      
      <!-- Top Action Bar -->
      <div class="flex flex-col md:flex-row md:items-center justify-between gap-4 bg-slate-900/60 p-4 rounded-2xl border border-slate-800">
        <div class="flex items-center space-x-3">
          <button
            id="btn-back-home"
            class="p-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white transition flex items-center justify-center border border-slate-700"
            title="Back to All Scanners"
          >
            <i data-lucide="arrow-left" class="w-5 h-5"></i>
          </button>
          <div>
            <div class="flex items-center space-x-2">
              <h2 id="results-scanner-title" class="text-lg font-bold text-white leading-none">Scanner Results</h2>
              <span id="scan-time-badge" class="px-2 py-0.5 rounded-md bg-slate-800 text-[10px] font-mono text-slate-400"></span>
            </div>
            <p id="results-scanner-desc" class="text-xs text-slate-400 mt-1"></p>
          </div>
        </div>

        <div class="flex items-center space-x-2 shrink-0 flex-wrap sm:flex-nowrap gap-y-2">
          <!-- Universe Switcher Dropdown -->
          <div class="relative flex items-center">
            <select
              id="results-select-universe"
              class="pl-3 pr-8 py-2 bg-slate-800 border border-slate-700 hover:border-slate-600 rounded-xl text-xs font-semibold text-sky-300 focus:outline-none focus:border-sky-500 cursor-pointer transition shadow-sm appearance-none"
              title="Select Stock Universe"
            >
              <option value="NIFTY_500">Nifty 500 (Broad Market)</option>
              <option value="NIFTY_100">Nifty 100</option>
              <option value="NIFTY_50">Nifty 50</option>
              <option value="NIFTY_MIDCAP_100">Midcap 100</option>
              <option value="NIFTY_SMALLCAP_100">Smallcap 100</option>
              <option value="ALL_F_AND_O">All F&O (215)</option>
            </select>
            <i data-lucide="chevron-down" class="w-3.5 h-3.5 text-slate-400 absolute right-2.5 pointer-events-none"></i>
          </div>

          <!-- Timeframe Switcher Dropdown -->
          <div class="relative flex items-center">
            <select
              id="results-select-timeframe"
              class="pl-3 pr-8 py-2 bg-slate-800 border border-slate-700 hover:border-slate-600 rounded-xl text-xs font-semibold text-sky-300 focus:outline-none focus:border-sky-500 cursor-pointer transition shadow-sm appearance-none"
              title="Select Candle Timeframe"
            >
              <option value="1D">1D (Daily)</option>
              <option value="2H">2H (120m)</option>
              <option value="1H">1H (60m)</option>
              <option value="15M">15M (15m)</option>
            </select>
            <i data-lucide="chevron-down" class="w-3.5 h-3.5 text-slate-400 absolute right-2.5 pointer-events-none"></i>
          </div>

          <!-- Re-Run Button -->
          <button
            id="btn-rerun"
            class="px-3.5 py-2 rounded-xl bg-sky-600 hover:bg-sky-500 text-white font-semibold text-xs transition flex items-center space-x-1.5 shadow-md shadow-sky-950 cursor-pointer whitespace-nowrap"
            title="Re-run scanner with current settings"
          >
            <i data-lucide="refresh-cw" class="w-3.5 h-3.5"></i>
            <span>Re-Run</span>
          </button>

          <!-- Export CSV Button -->
          <button
            id="btn-export-csv"
            class="px-3.5 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-semibold text-xs transition flex items-center space-x-1.5 shadow-md shadow-emerald-950 cursor-pointer whitespace-nowrap"
            title="Export results to CSV file"
          >
            <i data-lucide="download" class="w-3.5 h-3.5"></i>
            <span>Export CSV</span>
          </button>

          <!-- Copy TradingView Watchlist Button -->
          <button
            id="btn-copy-tv"
            class="hidden px-3.5 py-2 rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white font-semibold text-xs transition flex items-center space-x-1.5 shadow-md shadow-blue-950 cursor-pointer whitespace-nowrap"
            title="Copy TradingView Watchlist"
          >
            <i data-lucide="copy" class="w-3.5 h-3.5"></i>
            <span id="btn-copy-tv-text">Copy TradingView</span>
          </button>
        </div>
      </div>

      <!-- Loading State -->
      <div id="results-loading" class="py-24 text-center space-y-4">
        <div class="inline-flex p-4 rounded-2xl bg-sky-500/10 border border-sky-500/20 text-sky-400">
          <svg class="animate-spin h-8 w-8 text-sky-400" viewBox="0 0 24 24">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" fill="none"></circle>
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
          </svg>
        </div>
        <h3 class="text-lg font-bold text-white">Fetching Live Market Candles from DhanHQ...</h3>
        <p class="text-xs text-slate-400 max-w-md mx-auto">
          Downloading OHLCV histories, computing fractal swing zones, EMAs (20, 50, 100, 200), and candlestick patterns.
        </p>
      </div>

      <!-- Error State -->
      <div id="results-error" class="hidden py-4"></div>

      <!-- Results Content (Metrics + 2-Column Layout) -->
      <div id="results-content" class="hidden space-y-6">

        <!-- 4 Summary Metrics -->
        <div class="grid grid-cols-2 md:grid-cols-4 gap-3">
          <div class="metric-badge rounded-xl px-4 py-2.5 flex items-center justify-between">
            <span class="text-xs font-semibold text-slate-400">Total Constituents</span>
            <span id="metric-total" class="text-lg font-black text-white font-mono ml-2">-</span>
          </div>
          <div class="metric-badge rounded-xl px-4 py-2.5 bg-emerald-950/30 border-emerald-800/40 flex items-center justify-between">
            <span class="text-xs font-semibold text-emerald-400">Matched Criteria</span>
            <span id="metric-matched" class="text-lg font-black text-emerald-400 font-mono ml-2">-</span>
          </div>
          <div class="metric-badge rounded-xl px-4 py-2.5 bg-sky-950/30 border-sky-800/40 flex items-center justify-between">
            <span id="metric-third-label" class="text-xs font-semibold text-sky-400">Bullish Reversals</span>
            <span id="metric-reversals" class="text-lg font-black text-sky-400 font-mono ml-2">-</span>
          </div>
          <div class="metric-badge rounded-xl px-4 py-2.5 flex items-center justify-between">
            <span class="text-xs font-semibold text-slate-400">Average RSI (14)</span>
            <span id="metric-avg-rsi" class="text-lg font-black text-indigo-400 font-mono ml-2">-</span>
          </div>
        </div>

        <!-- Clean Full-Width Results Area -->
        <div class="w-full space-y-4">
          
          <!-- Table Header Bar: Search + Signal Dropdown + Match Status + Count Badge -->
          <div class="bg-slate-900/80 p-3.5 rounded-2xl border border-slate-800 shadow-xl">
            
            <div class="flex flex-col lg:flex-row items-stretch lg:items-center justify-between gap-3">
              <!-- Search Input + Level Filter + Signal Filter + Volume Filter -->
              <div class="flex flex-col sm:flex-row items-stretch sm:items-center gap-2.5 flex-1 max-w-4xl">
                <!-- Search Input -->
                <div class="relative flex-1">
                  <i data-lucide="search" class="w-4 h-4 text-slate-500 absolute left-3 top-2.5"></i>
                  <input
                    type="text"
                    id="table-search"
                    placeholder="Quick search symbol (e.g. INFY, TCS)..."
                    class="w-full pl-9 pr-3 py-1.5 text-xs bg-slate-800 border border-slate-700 rounded-xl text-white placeholder-slate-500 focus:outline-none focus:border-sky-500 transition"
                  />
                </div>

                <!-- Level Description Filter Dropdown -->
                <div id="container-level-filter" class="relative flex items-center shrink-0">
                  <select
                    id="table-level-filter"
                    class="pl-3 pr-8 py-1.5 bg-slate-800 border border-slate-700 hover:border-slate-600 rounded-xl text-xs font-semibold text-sky-300 focus:outline-none focus:border-sky-500 cursor-pointer transition shadow-sm appearance-none max-w-[210px] truncate"
                    title="Filter by Key Level / Setup Description"
                  >
                    <option value="ALL">🎯 All Levels</option>
                  </select>
                  <i data-lucide="chevron-down" class="w-3.5 h-3.5 text-slate-400 absolute right-2.5 pointer-events-none"></i>
                </div>

                <!-- Signal Filter Dropdown -->
                <div id="container-signal-filter" class="relative flex items-center shrink-0">
                  <select
                    id="table-signal-filter"
                    class="pl-3 pr-8 py-1.5 bg-slate-800 border border-slate-700 hover:border-slate-600 rounded-xl text-xs font-semibold text-sky-300 focus:outline-none focus:border-sky-500 cursor-pointer transition shadow-sm appearance-none max-w-[200px] truncate"
                    title="Filter by Candle Signal"
                  >
                    <option value="ALL">⚡ All Signals</option>
                  </select>
                  <i data-lucide="chevron-down" class="w-3.5 h-3.5 text-slate-400 absolute right-2.5 pointer-events-none"></i>
                </div>

                <!-- Volume Filter Dropdown -->
                <div id="container-volume-filter" class="relative flex items-center shrink-0">
                  <select
                    id="table-volume-filter"
                    class="pl-3 pr-8 py-1.5 bg-slate-800 border border-slate-700 hover:border-slate-600 rounded-xl text-xs font-semibold text-sky-300 focus:outline-none focus:border-sky-500 cursor-pointer transition shadow-sm appearance-none max-w-[170px] truncate"
                    title="Filter by Volume"
                  >
                    <option value="ALL">📊 All Volumes</option>
                  </select>
                  <i data-lucide="chevron-down" class="w-3.5 h-3.5 text-slate-400 absolute right-2.5 pointer-events-none"></i>
                </div>
              </div>

              <!-- Match Status Pill Switcher + Count Badge -->
              <div class="flex items-center space-x-3">
                <div class="inline-flex bg-slate-800/80 p-1 rounded-xl border border-slate-700">
                  <button
                    id="filter-status-matched"
                    data-status="matched"
                    class="status-pill px-3 py-1 rounded-lg text-xs font-semibold transition bg-sky-500/20 text-sky-300 border border-sky-500/40"
                  >
                    Matched 🟢
                  </button>
                  <button
                    id="filter-status-all"
                    data-status="all"
                    class="status-pill px-3 py-1 rounded-lg text-xs font-semibold text-slate-400 hover:text-slate-200 transition"
                  >
                    All Stocks
                  </button>
                </div>
                <span id="results-count-badge" class="text-xs font-semibold text-slate-300 whitespace-nowrap bg-slate-800/80 px-3 py-1.5 rounded-xl border border-slate-700"></span>
              </div>
            </div>

          </div>

          <!-- Clean Results Table -->
          <div class="overflow-x-auto rounded-2xl border border-slate-800 bg-slate-900/40 shadow-xl">
            <table class="w-full text-left text-sm">
              <thead class="bg-slate-800/90 text-xs font-semibold text-slate-400 uppercase tracking-wider border-b border-slate-800">
                <tr>
                  <th class="py-3.5 px-4 cursor-pointer hover:text-white transition" data-sort="symbol">
                    <div class="flex items-center space-x-1">
                      <span>Symbol</span>
                      <span class="text-[10px] text-slate-500">↕</span>
                    </div>
                  </th>
                  <th class="py-3.5 px-4 cursor-pointer hover:text-white transition" data-sort="ltp">
                    <div class="flex items-center space-x-1">
                      <span>LTP (₹)</span>
                      <span class="text-[10px] text-slate-500">↕</span>
                    </div>
                  </th>
                  <th class="py-3.5 px-4 cursor-pointer hover:text-white transition" data-sort="support_price">
                    <div class="flex items-center space-x-1">
                      <span>Key Level (₹)</span>
                      <span class="text-[10px] text-slate-500">↕</span>
                    </div>
                  </th>
                  <th class="py-3.5 px-4 cursor-pointer hover:text-white transition" data-sort="distance_pct">
                    <div class="flex items-center space-x-1">
                      <span>Distance (%)</span>
                      <span class="text-[10px] text-slate-500">↕</span>
                    </div>
                  </th>
                  <th class="py-3.5 px-4 cursor-pointer hover:text-white transition" data-sort="support_desc">
                    <div class="flex items-center space-x-1">
                      <span>Level Description</span>
                      <span class="text-[10px] text-slate-500">↕</span>
                    </div>
                  </th>
                  <th class="py-3.5 px-4 cursor-pointer hover:text-white transition" data-sort="volume">
                    <div class="flex items-center space-x-1">
                      <span>Volume</span>
                      <span class="text-[10px] text-slate-500">↕</span>
                    </div>
                  </th>
                  <th class="py-3.5 px-4 cursor-pointer hover:text-white transition" data-sort="rsi">
                    <div class="flex items-center space-x-1">
                      <span>RSI (14)</span>
                      <span class="text-[10px] text-slate-500">↕</span>
                    </div>
                  </th>
                  <th class="py-3.5 px-4 cursor-pointer hover:text-white transition" data-sort="candle_signal">
                    <div class="flex items-center space-x-1">
                      <span>Candle Signal</span>
                      <span class="text-[10px] text-slate-500">↕</span>
                    </div>
                  </th>
                </tr>
              </thead>
              <tbody id="results-tbody" class="divide-y divide-slate-800/60">
                <!-- Populated by app.js -->
              </tbody>
            </table>
          </div>

        </div>

      </div>
    </section>

    <!-- View 3: Daily EOD Multi-Scanner Digest View -->
    <section id="view-eod-digest" class="hidden space-y-6">
      
      <!-- Top Control Bar -->
      <div class="bg-slate-900/90 border border-slate-800 rounded-3xl p-6 shadow-2xl flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div class="flex items-center space-x-4">
          <div class="p-3 bg-gradient-to-br from-amber-500 to-orange-600 rounded-2xl shadow-lg shadow-amber-500/20 text-white shrink-0">
            <i data-lucide="sun-medium" class="w-6 h-6"></i>
          </div>
          <div>
            <div class="flex items-center space-x-2.5 flex-wrap">
              <h2 class="text-xl font-black text-white tracking-tight">Daily EOD Multi-Scanner Digest</h2>
              <span id="eod-live-status-badge" class="px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-emerald-950/80 text-emerald-400 border border-emerald-800/60 flex items-center space-x-1.5">
                <span class="w-2 h-2 rounded-full bg-emerald-400 live-dot"></span>
                <span id="eod-status-text">6:30 PM IST Snapshot</span>
              </span>
            </div>
            <p id="eod-header-subtitle" class="text-xs text-slate-400 mt-0.5">Automated Post-Market Snapshot across 500 Liquid NSE Stocks • 12 Active Strategies</p>
          </div>
        </div>

        <!-- Action Buttons & Date Picker -->
        <div class="flex items-center space-x-2.5 flex-wrap gap-y-2">
          <div class="relative">
            <select id="eod-select-date" onchange="onEodDateSelected(this.value)" class="pl-3 pr-8 py-2 bg-slate-800 border border-slate-700 hover:border-slate-600 rounded-xl text-xs font-semibold text-sky-300 focus:outline-none focus:border-sky-500 cursor-pointer shadow-sm appearance-none">
              <!-- Populated dynamically -->
            </select>
            <i data-lucide="chevron-down" class="w-3.5 h-3.5 text-slate-400 absolute right-2.5 top-1/2 -translate-y-1/2 pointer-events-none"></i>
          </div>

          <button onclick="openEodConfirmModal()" id="btn-eod-run-now" class="px-3.5 py-2 bg-slate-800 hover:bg-slate-700 active:scale-95 border border-slate-700 rounded-xl text-xs font-semibold text-slate-200 transition flex items-center space-x-1.5 cursor-pointer shadow-sm">
            <i data-lucide="refresh-cw" class="w-3.5 h-3.5 text-sky-400" id="icon-eod-refresh"></i>
            <span id="btn-eod-run-text">Run All Now</span>
          </button>

          <button onclick="copyEodTradingViewWatchlist(true)" class="px-3.5 py-2 bg-gradient-to-r from-amber-600 to-orange-600 hover:from-amber-500 hover:to-orange-500 text-white font-bold rounded-xl text-xs shadow-lg shadow-amber-500/20 active:scale-95 transition flex items-center space-x-1.5 cursor-pointer" title="Copy only high-confluence stocks for TradingView">
            <i data-lucide="flame" class="w-3.5 h-3.5"></i>
            <span>Copy Confluence</span>
          </button>

          <button onclick="copyEodTradingViewWatchlist(false)" class="px-3.5 py-2 bg-gradient-to-r from-sky-600 to-indigo-600 hover:from-sky-500 hover:to-indigo-500 text-white font-bold rounded-xl text-xs shadow-lg shadow-sky-500/20 active:scale-95 transition flex items-center space-x-1.5 cursor-pointer" title="Copy all flagged stocks for TradingView">
            <i data-lucide="copy" class="w-3.5 h-3.5"></i>
            <span>Copy All Symbols</span>
          </button>
        </div>
      </div>

      <!-- EOD ACTIVE BATCH SCAN PROGRESS CARD (Shown while scan is running) -->
      <div id="eod-active-scan-banner" class="hidden bg-gradient-to-r from-slate-900 via-indigo-950/70 to-slate-900 border-2 border-sky-500/40 rounded-3xl p-6 shadow-2xl space-y-4">
        <div class="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div class="flex items-center space-x-4">
            <div class="p-3 bg-sky-500/20 text-sky-400 border border-sky-500/30 rounded-2xl shrink-0">
              <i data-lucide="loader-2" class="w-7 h-7 animate-spin"></i>
            </div>
            <div>
              <div class="flex items-center space-x-2.5">
                <h3 class="text-lg font-bold text-white tracking-tight">EOD Multi-Scanner Batch in Progress</h3>
                <span class="px-2.5 py-0.5 rounded-full text-xs font-mono font-bold bg-sky-500/20 text-sky-300 border border-sky-500/40" id="eod-scan-pct-badge">0%</span>
              </div>
              <p class="text-xs text-slate-300 mt-1" id="eod-scan-status-detail">
                Scanning 500 stocks across 12 strategies. Estimated time: <strong class="text-amber-300">~5–10 minutes</strong>.
              </p>
            </div>
          </div>
          <div class="text-right shrink-0">
            <span class="text-[11px] font-mono text-emerald-400 bg-emerald-950/70 border border-emerald-800/60 px-3 py-1.5 rounded-xl shadow-sm">
              🛡️ Running on Server • Storing in MySQL
            </span>
          </div>
        </div>

        <!-- Progress Bar -->
        <div class="w-full bg-slate-950/90 rounded-full h-3.5 overflow-hidden border border-slate-700/60 p-0.5 shadow-inner">
          <div id="eod-scan-progress-bar" class="bg-gradient-to-r from-sky-500 via-blue-500 to-indigo-500 h-full rounded-full transition-all duration-500 shadow-md shadow-sky-500/50" style="width: 0%;"></div>
        </div>

        <div class="flex items-center justify-between text-[11px] text-slate-400 font-mono flex-wrap gap-2">
          <span id="eod-scan-step-indicator" class="text-sky-300 font-semibold">Scanner 1 of 12: Initializing...</span>
          <span class="text-amber-400/90 flex items-center gap-1.5">
            <span>⚠️ Screen actions paused for EOD scan. You may safely switch tabs or let it finish.</span>
          </span>
        </div>
      </div>

      <!-- Metric KPI Cards -->
      <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4" id="eod-kpi-container">
        <!-- Populated dynamically -->
      </div>

      <!-- SECTION 1: 🔥 HIGH CONFLUENCE RADAR (2+ STRATEGIES) -->
      <div id="eod-confluence-section" class="bg-slate-900/90 border border-amber-500/30 rounded-3xl p-6 shadow-2xl space-y-4">
        <div class="flex items-center space-x-3">
          <div class="p-2.5 bg-amber-500/20 text-amber-400 border border-amber-500/30 rounded-xl">
            <i data-lucide="flame" class="w-5 h-5"></i>
          </div>
          <div>
            <h3 class="text-base font-bold text-white flex items-center space-x-2">
              <span>High Confluence Radar</span>
              <span id="eod-confluence-badge" class="px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-500/20 text-amber-300 border border-amber-500/40">-- Multi-Strategy Setups</span>
            </h3>
            <p class="text-xs text-slate-400">Stocks that triggered 2 or more independent algorithmic strategies simultaneously today.</p>
          </div>
        </div>

        <div id="eod-confluence-grid" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 pt-2">
          <!-- Populated dynamically -->
        </div>
      </div>

      <!-- SECTION 2: CONSOLIDATED MASTER WATCHLIST TABLE -->
      <div class="bg-slate-900/90 border border-slate-800 rounded-3xl p-6 shadow-2xl space-y-4">
        <div class="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h3 class="text-base font-bold text-white flex items-center space-x-2">
              <i data-lucide="table-2" class="w-4 h-4 text-sky-400"></i>
              <span>Master EOD Watchlist</span>
              <span id="eod-table-count-badge" class="text-xs font-normal text-slate-400">(-- Total Unique Stocks Flagged)</span>
            </h3>
          </div>

          <!-- Category filter tabs, Level dropdown & Search -->
          <div class="flex items-center space-x-2 flex-wrap gap-y-2">
            <div class="flex items-center space-x-1 bg-slate-950/80 p-1 rounded-xl border border-slate-800 text-xs" id="eod-table-filters">
              <button onclick="filterEodTable('ALL')" data-eod-filter="ALL" class="eod-filter-btn px-3 py-1 rounded-lg font-bold bg-sky-500/20 text-sky-300 border border-sky-500/30">All</button>
              <button onclick="filterEodTable('CONFLUENCE')" data-eod-filter="CONFLUENCE" class="eod-filter-btn px-3 py-1 rounded-lg font-semibold text-slate-400 hover:text-white">🔥 Confluence (2+)</button>
              <button onclick="filterEodTable('VCP')" data-eod-filter="VCP" class="eod-filter-btn px-3 py-1 rounded-lg font-semibold text-slate-400 hover:text-white">VCP</button>
              <button onclick="filterEodTable('SMC')" data-eod-filter="SMC" class="eod-filter-btn px-3 py-1 rounded-lg font-semibold text-slate-400 hover:text-white">SMC / OB</button>
              <button onclick="filterEodTable('BREAKOUT')" data-eod-filter="BREAKOUT" class="eod-filter-btn px-3 py-1 rounded-lg font-semibold text-slate-400 hover:text-white">Breakout</button>
              <button onclick="filterEodTable('REVERSAL')" data-eod-filter="REVERSAL" class="eod-filter-btn px-3 py-1 rounded-lg font-semibold text-slate-400 hover:text-white">Reversal</button>
              <button onclick="filterEodTable('TREND')" data-eod-filter="TREND" class="eod-filter-btn px-3 py-1 rounded-lg font-semibold text-slate-400 hover:text-white">Trend</button>
            </div>

            <!-- Dynamic Key Trigger Level / Signal Filter Dropdown -->
            <div class="relative flex items-center shrink-0" id="container-eod-level-filter">
              <select
                id="eod-level-filter"
                onchange="onEodLevelFilterChange(this.value)"
                class="pl-3 pr-8 py-1.5 bg-slate-800 border border-slate-700 hover:border-slate-600 rounded-xl text-xs font-semibold text-sky-300 focus:outline-none focus:border-sky-500 cursor-pointer transition shadow-sm appearance-none max-w-[210px] truncate"
                title="Filter by Key Trigger Level / Signal"
              >
                <option value="ALL">🎯 All Trigger Levels</option>
              </select>
              <i data-lucide="chevron-down" class="w-3.5 h-3.5 text-slate-400 absolute right-2.5 pointer-events-none"></i>
            </div>

            <div class="relative">
              <input
                type="text"
                id="eod-table-search"
                placeholder="Filter symbol..."
                oninput="onEodSearchInput(this.value)"
                class="pl-8 pr-3 py-1.5 bg-slate-800 border border-slate-700 rounded-xl text-xs text-white placeholder-slate-500 focus:outline-none focus:border-sky-500 w-36 shadow-inner"
              />
              <i data-lucide="search" class="w-3.5 h-3.5 text-slate-400 absolute left-2.5 top-1/2 -translate-y-1/2 pointer-events-none"></i>
            </div>
          </div>
        </div>

        <!-- Table Container -->
        <div class="overflow-x-auto rounded-2xl border border-slate-800">
          <table class="w-full text-left text-xs text-slate-300">
            <thead class="bg-slate-950/80 text-[11px] font-bold text-slate-400 uppercase tracking-wider border-b border-slate-800">
              <tr>
                <th class="p-3.5">Symbol</th>
                <th class="p-3.5">LTP / Change</th>
                <th class="p-3.5">Triggered Strategies</th>
                <th class="p-3.5">Key Trigger Level / Signal</th>
                <th class="p-3.5">Volume Multiple</th>
                <th class="p-3.5 text-right">Action</th>
              </tr>
            </thead>
            <tbody id="eod-table-body" class="divide-y divide-slate-800/60 bg-slate-900/40">
              <!-- Populated dynamically -->
            </tbody>
          </table>
        </div>
      </div>

    </section>

  </div>

  <!-- EMBEDDED REAL-TIME INTERACTIVE CHART MODAL -->
  <div id="chart-modal" class="hidden fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-md p-3 sm:p-6">
    <div class="bg-[#111827] border border-gray-700/90 rounded-2xl w-full max-w-6xl h-[85vh] flex flex-col shadow-2xl overflow-hidden animate-in fade-in zoom-in duration-200">
      
      <!-- Chart Modal Header -->
      <div class="px-5 py-3 border-b border-gray-800 flex items-center justify-between bg-[#162032]">
        <div class="flex items-center gap-3">
          <div class="w-8 h-8 rounded-lg bg-emerald-500/20 border border-emerald-500/30 flex items-center justify-center text-emerald-400 font-bold text-base shadow-inner">
            📈
          </div>
          <div>
            <div class="flex items-center gap-2">
              <span id="chart-modal-symbol" class="text-sm font-black px-2.5 py-0.5 bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 rounded tracking-wider">SYMBOL</span>
              <span class="text-xs text-gray-300 font-semibold hidden sm:inline">NSE Real-Time Interactive Candlestick Chart</span>
            </div>
            <div class="text-[10px] text-gray-400 font-mono mt-0.5">Live Market Datafeed • Asia/Kolkata (IST)</div>
          </div>
        </div>

        <div class="flex items-center gap-2">
          <!-- Direct Fullscreen Link -->
          <a id="chart-modal-tv-link" href="#" target="_blank" rel="noopener noreferrer" class="px-3 py-1.5 text-xs font-bold bg-sky-600 hover:bg-sky-500 text-white rounded-lg flex items-center gap-1.5 shadow transition active:scale-95" title="Open Fullscreen on TradingView.com">
            <span>↗</span>
            <span class="hidden sm:inline">Open Fullscreen</span>
          </a>
          <!-- Close Button -->
          <button onclick="closeChartModal()" class="p-1.5 rounded-lg text-gray-400 hover:text-white hover:bg-gray-800 text-xl font-bold leading-none transition" title="Close Chart (Esc)">✕</button>
        </div>
      </div>

      <!-- Live Chart iFrame Container -->
      <div id="chart-modal-container" class="flex-1 w-full h-full bg-[#0b0f19]">
        <!-- Injected dynamically on open -->
      </div>
    </div>
  </div>

  <!-- SLIDE-OUT DETAILS DRAWER (RIGHT OVERLAY) -->
  <div id="details-drawer-backdrop" onclick="closeDrawer()" class="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 opacity-0 pointer-events-none transition-opacity duration-300"></div>
  <aside id="details-drawer" class="fixed inset-y-0 right-0 w-full sm:w-[540px] bg-[#111827] border-l border-gray-700/80 shadow-2xl z-50 transform translate-x-full transition-transform duration-300 flex flex-col">
    <!-- Drawer Header -->
    <div class="px-5 py-4 border-b border-gray-800 flex items-center justify-between bg-[#162032]/80">
      <div class="flex items-center gap-2.5">
        <span id="drawer-symbol-badge" class="text-sm font-black px-2.5 py-1 bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 rounded tracking-wider">TICKER</span>
        <span id="drawer-sec-id" class="text-xs font-mono text-cyan-300 bg-cyan-950/80 px-2 py-0.5 border border-cyan-800/60 rounded">#0</span>
        <span id="drawer-sentiment-badge" class="text-xs font-bold px-2 py-0.5 rounded font-mono">BULLISH</span>
      </div>
      <div class="flex items-center gap-1.5">
        <button onclick="if (activeDrawerItem) openChartModal(activeDrawerItem.symbol);" class="px-2.5 py-1 text-xs font-bold bg-emerald-500/20 hover:bg-emerald-500/35 text-emerald-300 border border-emerald-500/40 rounded-lg flex items-center gap-1.5 transition shadow-sm active:scale-95" title="Open Interactive Real-Time Candlestick Chart">
          <span>📈</span>
          <span>Live Chart</span>
        </button>
        <a id="drawer-tv-chart-btn" href="#" target="_blank" rel="noopener noreferrer" class="px-2 py-1 text-xs font-bold bg-sky-950/60 hover:bg-sky-900/60 text-sky-300 border border-sky-700/60 rounded-lg flex items-center gap-1 transition shadow-sm" title="Open on TradingView.com">
          <span>↗</span>
          <span class="hidden sm:inline">TradingView</span>
        </a>
        <button onclick="copyFilingText()" class="p-1.5 rounded-lg text-gray-400 hover:text-white hover:bg-gray-800 transition" title="Copy Announcement Text">📋</button>
        <button onclick="closeDrawer()" class="p-1.5 rounded-lg text-gray-400 hover:text-white hover:bg-gray-800 text-lg font-bold leading-none transition" title="Close Drawer (Esc)">✕</button>
      </div>
    </div>

    <!-- Drawer Content (Scrollable) -->
    <div class="flex-1 overflow-y-auto custom-scrollbar p-5 space-y-4">
      
      <!-- Timing & Freshness Banner -->
      <div class="bg-[#0e1422] border border-gray-800 rounded-xl p-3 flex items-center justify-between text-xs font-mono">
        <div>
          <span class="text-gray-400">Filed Time:</span>
          <span id="drawer-time" class="text-white font-bold ml-1">--:--:--</span>
        </div>
        <div id="drawer-freshness-pill" class="px-2 py-0.5 rounded text-[11px] font-bold">
          Freshness
        </div>
      </div>

      <!-- AI Catalyst Analysis -->
      <div class="bg-indigo-950/30 border border-indigo-500/30 rounded-xl p-3.5 space-y-2">
        <div class="flex items-center justify-between border-b border-indigo-500/20 pb-2">
          <span class="text-xs font-bold text-indigo-300 flex items-center gap-1.5">
            <span>🧠</span>
            <span id="drawer-catalyst-category">AI CATALYST AUDIT</span>
          </span>
          <span id="drawer-confidence-pill" class="text-xs font-mono font-bold text-indigo-200 bg-indigo-500/20 px-2 py-0.5 rounded">95% Conf</span>
        </div>
        <p id="drawer-summary" class="text-xs text-gray-200 leading-relaxed font-sans">
          Summary
        </p>
      </div>

      <!-- Complete Filing Text -->
      <div>
        <div class="flex items-center justify-between mb-1.5">
          <h4 class="text-[11px] font-bold uppercase text-gray-400 tracking-wider flex items-center gap-1.5">
            <span>📄</span>
            <span>Raw Exchange Announcement</span>
          </h4>
          <span id="drawer-seq-id" class="text-[10px] text-gray-500 font-mono">Seq ID: --</span>
        </div>
        <div class="bg-[#0b0f19] border border-gray-800 rounded-xl p-3.5">
          <p id="drawer-raw-text" class="text-gray-300 font-mono text-xs whitespace-pre-wrap leading-relaxed max-h-[280px] overflow-y-auto custom-scrollbar select-text">
            Text
          </p>
        </div>
      </div>

      <!-- Bracket Pricing Matrix -->
      <div class="bg-[#131b2e] border border-gray-800 rounded-xl p-3.5 space-y-2">
        <h4 class="text-[11px] font-bold uppercase text-gray-400 tracking-wider flex items-center gap-1.5">
          <span>🎯</span>
          <span>Super Order Execution Matrix</span>
        </h4>
        <div class="grid grid-cols-4 gap-2 font-mono text-center">
          <div class="bg-[#0b0f19] p-2 rounded-lg border border-gray-800">
            <div class="text-[10px] text-gray-400">ENTRY LIMIT</div>
            <div id="drawer-entry-price" class="text-xs font-bold text-white mt-0.5">₹0.00</div>
          </div>
          <div class="bg-[#0b0f19] p-2 rounded-lg border border-emerald-500/20">
            <div class="text-[10px] text-emerald-400">TARGET (3%)</div>
            <div id="drawer-target-price" class="text-xs font-bold text-emerald-400 mt-0.5">₹0.00</div>
          </div>
          <div class="bg-[#0b0f19] p-2 rounded-lg border border-rose-500/20">
            <div class="text-[10px] text-rose-400">STOP LOSS (1%)</div>
            <div id="drawer-sl-price" class="text-xs font-bold text-rose-400 mt-0.5">₹0.00</div>
          </div>
          <div class="bg-[#0b0f19] p-2 rounded-lg border border-indigo-500/20">
            <div class="text-[10px] text-indigo-300">LIVE P&L</div>
            <div id="drawer-live-pnl" class="text-xs font-bold text-gray-300 mt-0.5">--</div>
          </div>
        </div>
        <div class="text-[10px] text-gray-500 font-mono flex items-center justify-between pt-1">
          <span id="drawer-qty-info">Position: -- sh</span>
          <span>Trailing Jump: 5.0 pts</span>
        </div>
      </div>

    </div>

    <!-- Drawer Footer Actions -->
    <div id="drawer-footer" class="p-4 border-t border-gray-800 bg-[#162032]/90 flex items-center justify-between gap-3">
      <button onclick="closeDrawer()" class="px-4 py-2 text-xs font-bold text-gray-400 hover:text-white rounded-lg hover:bg-gray-800 transition">Close</button>
      <div id="drawer-action-btn-container" class="flex-1 flex justify-end">
        <!-- Dynamic Action Button -->
      </div>
    </div>
  </aside>

  <!-- SAFETY EMERGENCY SQUARE-OFF MODAL -->
  <div id="squareoff-modal" class="fixed inset-0 bg-black/80 backdrop-blur-md z-50 flex items-center justify-center p-4 opacity-0 pointer-events-none transition-all duration-300">
    <div class="bg-[#111827] border border-rose-600/70 rounded-2xl max-w-md w-full p-6 shadow-2xl space-y-4 transform scale-95 transition-all duration-300 ring-2 ring-rose-500/30" id="squareoff-modal-card">
      <div class="flex items-center gap-3">
        <div class="w-10 h-10 rounded-xl bg-rose-500/20 border border-rose-500/40 flex items-center justify-center text-rose-400 font-black text-xl">
          🛑
        </div>
        <div>
          <h3 class="text-sm font-bold text-white uppercase tracking-wider">Confirm Emergency Square-Off</h3>
          <p class="text-[11px] text-rose-300 mt-0.5">Flatten all active intraday positions immediately</p>
        </div>
      </div>
      <p class="text-xs text-gray-300 leading-relaxed bg-[#0b0f19] border border-rose-900/50 p-3 rounded-xl">
        This action will <b>immediately cancel all pending limit orders</b> and <b>market-close all open Dhan trading positions</b>. This cannot be undone.
      </p>
      <div class="flex items-center justify-end gap-2.5 pt-2 border-t border-gray-800">
        <button onclick="closeSquareOffModal()" class="px-4 py-2 text-xs font-semibold text-gray-400 hover:text-white rounded-lg hover:bg-gray-800 transition">
          Cancel (Esc)
        </button>
        <button onclick="executeConfirmedSquareOff()" id="btn-confirm-squareoff" class="bg-rose-600 hover:bg-rose-500 text-white font-bold text-xs px-4 py-2 rounded-lg transition shadow-lg shadow-rose-600/40 active:scale-95 flex items-center gap-1.5">
          <span>🛑 Yes, Square-Off All</span>
        </button>
      </div>
    </div>
  </div>

  <!-- KEYBOARD SHORTCUTS MODAL -->
  <div id="hotkeys-modal" class="fixed inset-0 bg-black/80 backdrop-blur-md z-50 flex items-center justify-center p-4 opacity-0 pointer-events-none transition-all duration-300">
    <div class="bg-[#111827] border border-gray-700 rounded-2xl max-w-lg w-full p-6 shadow-2xl space-y-4 transform scale-95 transition-all duration-300" id="hotkeys-modal-card">
      <div class="flex items-center justify-between border-b border-gray-800 pb-3">
        <div class="flex items-center gap-2.5">
          <span class="text-lg">⌨️</span>
          <h3 class="text-sm font-bold text-white uppercase tracking-wider">Keyboard Hotkeys Cheat Sheet</h3>
        </div>
        <button onclick="closeHotkeysModal()" class="text-gray-400 hover:text-white text-lg font-bold p-1 rounded-lg hover:bg-gray-800 transition">✕</button>
      </div>
      <div class="grid grid-cols-2 gap-2.5 text-xs">
        <div class="bg-[#0b0f19] p-2.5 rounded-lg border border-gray-800 flex items-center justify-between">
          <span class="text-gray-300">Navigate Feed Down</span>
          <kbd class="px-2 py-0.5 bg-gray-800 text-emerald-400 border border-gray-700 rounded font-mono font-bold">J</kbd>
        </div>
        <div class="bg-[#0b0f19] p-2.5 rounded-lg border border-gray-800 flex items-center justify-between">
          <span class="text-gray-300">Navigate Feed Up</span>
          <kbd class="px-2 py-0.5 bg-gray-800 text-emerald-400 border border-gray-700 rounded font-mono font-bold">K</kbd>
        </div>
        <div class="bg-[#0b0f19] p-2.5 rounded-lg border border-gray-800 flex items-center justify-between">
          <span class="text-gray-300">Open Details Drawer</span>
          <kbd class="px-2 py-0.5 bg-gray-800 text-white border border-gray-700 rounded font-mono font-bold">Enter / Space</kbd>
        </div>
        <div class="bg-[#0b0f19] p-2.5 rounded-lg border border-gray-800 flex items-center justify-between">
          <span class="text-gray-300">Approve Buy Order</span>
          <kbd class="px-2 py-0.5 bg-emerald-950 text-emerald-300 border border-emerald-800 rounded font-mono font-bold">A or B</kbd>
        </div>
        <div class="bg-[#0b0f19] p-2.5 rounded-lg border border-gray-800 flex items-center justify-between">
          <span class="text-gray-300">Approve Short Sell</span>
          <kbd class="px-2 py-0.5 bg-rose-950 text-rose-300 border border-rose-800 rounded font-mono font-bold">S</kbd>
        </div>
        <div class="bg-[#0b0f19] p-2.5 rounded-lg border border-gray-800 flex items-center justify-between">
          <span class="text-gray-300">Emergency Square-Off</span>
          <kbd class="px-2 py-0.5 bg-rose-900 text-white border border-rose-600 rounded font-mono font-bold">Shift + Q</kbd>
        </div>
        <div class="bg-[#0b0f19] p-2.5 rounded-lg border border-gray-800 flex items-center justify-between">
          <span class="text-gray-300">Toggle Mute Audio</span>
          <kbd class="px-2 py-0.5 bg-gray-800 text-gray-300 border border-gray-700 rounded font-mono font-bold">M</kbd>
        </div>
        <div class="bg-[#0b0f19] p-2.5 rounded-lg border border-gray-800 flex items-center justify-between">
          <span class="text-gray-300">Close Modals / Drawer</span>
          <kbd class="px-2 py-0.5 bg-gray-800 text-gray-300 border border-gray-700 rounded font-mono font-bold">Esc</kbd>
        </div>
      </div>
      <div class="flex justify-end pt-2 border-t border-gray-800">
        <button onclick="closeHotkeysModal()" class="px-4 py-2 text-xs font-bold bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg transition">Got It</button>
      </div>
    </div>
  </div>

  <!-- EOD BATCH SCAN CONFIRMATION MODAL -->
  <div id="modal-eod-confirm" class="fixed inset-0 z-50 bg-black/80 backdrop-blur-md hidden flex items-center justify-center p-4">
    <div class="bg-slate-900 border border-slate-700 rounded-3xl p-6 md:p-8 max-w-lg w-full shadow-2xl space-y-5 animate-in fade-in zoom-in duration-200" id="modal-eod-confirm-card">
      <div class="flex items-start space-x-4">
        <div class="p-3.5 bg-gradient-to-br from-amber-500/20 to-orange-500/20 text-amber-400 border border-amber-500/30 rounded-2xl shrink-0">
          <i data-lucide="sun-medium" class="w-7 h-7"></i>
        </div>
        <div>
          <h3 class="text-lg font-bold text-white tracking-tight">Run Full EOD Multi-Scanner Batch?</h3>
          <p class="text-xs text-slate-400 mt-1 leading-relaxed">
            This triggers a complete quantitative scan across all <strong>500 stocks</strong> in Nifty 500 for all <strong>12 algorithmic strategies</strong>.
          </p>
        </div>
      </div>

      <div class="bg-slate-950/80 border border-slate-800 rounded-2xl p-4 space-y-2.5 text-xs text-slate-300">
        <div class="flex items-center space-x-2.5 text-amber-300 font-semibold">
          <i data-lucide="clock" class="w-4 h-4 shrink-0 text-amber-400"></i>
          <span>Estimated Duration: Approx 5–10 minutes</span>
        </div>
        <div class="flex items-center space-x-2.5 text-emerald-400">
          <i data-lucide="database" class="w-4 h-4 shrink-0 text-emerald-400"></i>
          <span>Data Safety: Permanently saved to MySQL & SQLite database</span>
        </div>
        <div class="flex items-center space-x-2.5 text-slate-400">
          <i data-lucide="shield-check" class="w-4 h-4 shrink-0 text-sky-400"></i>
          <span>Background Execution: Safe to switch screens or view live positions</span>
        </div>
      </div>

      <div class="flex items-center justify-end space-x-3 pt-2">
        <button onclick="closeEodConfirmModal()" class="px-4 py-2 bg-slate-800 hover:bg-slate-700 active:scale-95 text-slate-300 font-semibold text-xs rounded-xl border border-slate-700 transition cursor-pointer">
          Cancel
        </button>
        <button onclick="confirmAndStartEodScan()" class="px-5 py-2 bg-gradient-to-r from-amber-600 via-orange-600 to-amber-700 hover:from-amber-500 hover:to-orange-500 active:scale-95 text-white font-bold text-xs rounded-xl shadow-lg shadow-amber-500/20 transition flex items-center space-x-1.5 cursor-pointer">
          <i data-lucide="zap" class="w-4 h-4"></i>
          <span>Start EOD Batch Scan</span>
        </button>
      </div>
    </div>
  </div>

  <!-- DHAN LOGIN & AUTHENTICATION MODAL / SCREEN -->
  <div id="token-modal" class="fixed inset-0 bg-black/80 backdrop-blur-md z-50 flex items-center justify-center p-4 opacity-0 pointer-events-none transition-all duration-300">
    <div class="bg-[#111827] border border-gray-700/90 rounded-2xl max-w-lg w-full p-6 shadow-2xl space-y-5 transform scale-95 transition-all duration-300 max-h-[90vh] overflow-y-auto custom-scrollbar" id="token-modal-card">
      
      <!-- Modal Header -->
      <div class="flex items-center justify-between border-b border-gray-800 pb-3.5">
        <div class="flex items-center gap-3">
          <div class="w-10 h-10 rounded-xl bg-gradient-to-br from-emerald-500/20 to-teal-500/10 border border-emerald-500/30 flex items-center justify-center text-emerald-400 font-bold text-lg shadow-inner">
            🔐
          </div>
          <div>
            <h3 class="text-sm font-bold text-white uppercase tracking-wider flex items-center gap-2">
              <span>Login with DhanHQ</span>
              <span class="px-2 py-0.5 text-[10px] font-bold bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 rounded-full font-mono">Broker Auth</span>
            </h3>
            <p class="text-[11px] text-gray-400 mt-0.5">Authenticate your Dhan trading account for live execution</p>
          </div>
        </div>
        <button onclick="closeTokenModal()" class="text-gray-400 hover:text-white text-lg font-bold p-1 rounded-lg hover:bg-gray-800 transition" title="Dismiss">✕</button>
      </div>

      <!-- Session Expired Alert Banner (Dynamic) -->
      <div id="login-session-alert" class="hidden text-xs p-3 rounded-xl border shadow-inner"></div>

      <!-- Option 1: 1-Click Login with Dhan (OAuth 2.0) -->
      <div class="bg-gradient-to-r from-emerald-950/40 via-teal-950/30 to-slate-900 border border-emerald-500/30 rounded-xl p-4 space-y-3 shadow-inner">
        <div class="flex items-center justify-between">
          <div class="flex items-center gap-2">
            <span class="text-base">⚡</span>
            <h4 class="text-xs font-bold text-emerald-300 uppercase tracking-wide">Option 1: 1-Click Login with Dhan</h4>
          </div>
          <span class="px-2 py-0.5 text-[10px] font-bold bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 rounded-full font-mono">OAuth 2.0</span>
        </div>
        <p class="text-[11px] text-gray-300 leading-relaxed">
          Redirects to Dhan to log in securely via Mobile + OTP/TOTP. Token is automatically fetched & activated with zero copy-pasting.
        </p>

        <div class="pt-1">
          <button onclick="launchDhanOAuth()" id="btn-oauth-login" class="w-full bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white font-bold text-xs py-2.5 px-4 rounded-lg shadow-lg shadow-emerald-700/30 border border-emerald-400/40 flex items-center justify-center gap-2 transition active:scale-95">
            <span>🚀 Log In via Dhan Portal</span>
          </button>
        </div>
      </div>

      <!-- Divider -->
      <div class="flex items-center gap-3 my-2">
        <div class="flex-1 h-px bg-gray-800"></div>
        <span class="text-[10px] text-gray-500 font-mono uppercase tracking-wider">OR PASTE DIRECTLY</span>
        <div class="flex-1 h-px bg-gray-800"></div>
      </div>

      <!-- Option 2: Paste Access Token Manually -->
      <div class="bg-gray-900/80 border border-gray-800 rounded-xl p-3.5 space-y-2.5">
        <div class="flex items-center justify-between">
          <h4 class="text-xs font-bold text-gray-300 uppercase tracking-wide">Option 2: Paste Access Token</h4>
          <a href="https://web.dhan.co" target="_blank" rel="noopener noreferrer" class="text-[10px] text-blue-400 hover:underline">Get from web.dhan.co ↗</a>
        </div>
        <div class="flex gap-2">
          <input type="password" id="modal-manual-token" placeholder="Paste 24-hr Access Token (JWT)..." class="flex-1 bg-[#0b0f19] border border-gray-700 text-xs text-white rounded-lg px-3 py-2 focus:outline-none focus:border-emerald-500 font-mono placeholder:text-gray-600">
          <button onclick="saveManualToken()" id="btn-save-manual-token" class="bg-emerald-600 hover:bg-emerald-500 text-white font-bold text-xs px-3.5 py-2 rounded-lg transition shadow">Save</button>
        </div>
      </div>

      <!-- Modal Status Feedback -->
      <div id="modal-feedback" class="hidden text-xs p-2.5 rounded-lg"></div>

      <!-- Modal Actions -->
      <div class="flex items-center justify-end gap-2.5 pt-2 border-t border-gray-800">
        <button onclick="closeTokenModal()" class="text-xs font-semibold text-gray-400 hover:text-gray-200 px-4 py-2 rounded-lg hover:bg-gray-800 transition">
          <span>Close</span>
        </button>
      </div>

    </div>
  </div>

  <!-- TOAST NOTIFICATION -->
  <div id="toast" class="fixed bottom-5 right-5 bg-gray-900 border border-gray-700 text-white text-xs px-4 py-3 rounded-lg shadow-2xl transition-all duration-300 opacity-0 translate-y-4 pointer-events-none z-50 flex items-center gap-2">
    <span id="toast-icon">ℹ️</span>
    <span id="toast-msg">Notification</span>
  </div>

  <!-- JAVASCRIPT LOGIC -->
  <script>
    let isNewsEngineActive = true;
    let isNewsDryRun = true;
    let isNewsAutoOrder = true;

    let isSt14EngineActive = true;
    let isSt14DryRun = true;
    let isSt14AutoOrder = true;
    let st14ProductType = 'INTRADAY';
    let st14Telemetry = null;

    let isStrategyEngineActive = true;
    let isAutoOrder = true;
    let isDryRun = true;
    let feedItems = [];
    let currentFilter = 'ALL';
    let expandedRows = new Set();
    let selectedRowIndex = -1;
    let activeDrawerItem = null;

    function syncActiveStrategyState() {
      if (activeStrategyId === 'st14_bullish_ce') {
        isStrategyEngineActive = isSt14EngineActive;
        isDryRun = isSt14DryRun;
        isAutoOrder = isSt14AutoOrder;
      } else {
        isStrategyEngineActive = isNewsEngineActive;
        isDryRun = isNewsDryRun;
        isAutoOrder = isNewsAutoOrder;
      }
      updateStrategyEngineUI();
      updateExecutionModeUI();
      updateAutoOrderUI();
    }

    // --- WEB AUDIO API SYNTHESIZER ---
    class WebAudioSynth {
      constructor() {
        this.ctx = null;
        this.enabled = localStorage.getItem('sound_enabled') !== 'false';
      }
      init() {
        if (!this.ctx) {
          const AudioContext = window.AudioContext || window.webkitAudioContext;
          if (AudioContext) this.ctx = new AudioContext();
        }
        if (this.ctx && this.ctx.state === 'suspended') {
          this.ctx.resume();
        }
      }
      playTone(freq, type, duration, gainVal = 0.15) {
        if (!this.enabled) return;
        try {
          this.init();
          if (!this.ctx) return;
          const osc = this.ctx.createOscillator();
          const gain = this.ctx.createGain();
          osc.type = type;
          osc.frequency.setValueAtTime(freq, this.ctx.currentTime);
          gain.gain.setValueAtTime(gainVal, this.ctx.currentTime);
          gain.gain.exponentialRampToValueAtTime(0.0001, this.ctx.currentTime + duration);
          osc.connect(gain);
          gain.connect(this.ctx.destination);
          osc.start();
          osc.stop(this.ctx.currentTime + duration);
        } catch(e) {}
      }
      playBullishChime() {
        if (!this.enabled) return;
        this.playTone(523.25, 'triangle', 0.15, 0.2); // C5
        setTimeout(() => this.playTone(659.25, 'triangle', 0.2, 0.25), 100); // E5
        setTimeout(() => this.playTone(783.99, 'triangle', 0.35, 0.3), 200); // G5
      }
      playBearishChime() {
        if (!this.enabled) return;
        this.playTone(587.33, 'sawtooth', 0.15, 0.15); // D5
        setTimeout(() => this.playTone(493.88, 'sawtooth', 0.2, 0.2), 100); // B4
        setTimeout(() => this.playTone(415.30, 'sawtooth', 0.35, 0.25), 200); // G#4
      }
      playWarningChime() {
        if (!this.enabled) return;
        this.playTone(440, 'square', 0.15, 0.1);
        setTimeout(() => this.playTone(440, 'square', 0.2, 0.15), 150);
      }
      playOrderChime() {
        if (!this.enabled) return;
        this.playTone(587.33, 'sine', 0.12, 0.2);
        setTimeout(() => this.playTone(880, 'sine', 0.25, 0.25), 80);
      }
    }
    const synth = new WebAudioSynth();

    function updateSoundUI() {
      const btn = document.getElementById('sound-toggle-btn');
      const icon = document.getElementById('sound-icon');
      const label = document.getElementById('sound-label');
      if (!btn) return;
      if (synth.enabled) {
        btn.className = 'bg-emerald-950/60 hover:bg-emerald-900/60 active:scale-95 text-emerald-300 text-xs font-semibold px-2.5 py-1.5 rounded-lg transition border border-emerald-500/50 flex items-center gap-1.5 shadow-sm';
        if (icon) icon.textContent = '🔊';
        if (label) label.textContent = 'Audio ON';
      } else {
        btn.className = 'bg-gray-800 hover:bg-gray-700 active:scale-95 text-gray-400 text-xs font-semibold px-2.5 py-1.5 rounded-lg transition border border-gray-700 flex items-center gap-1.5 shadow';
        if (icon) icon.textContent = '🔇';
        if (label) label.textContent = 'Muted';
      }
    }

    function toggleAudioSound() {
      synth.init();
      synth.enabled = !synth.enabled;
      localStorage.setItem('sound_enabled', synth.enabled ? 'true' : 'false');
      updateSoundUI();
      if (synth.enabled) {
        synth.playBullishChime();
        showToast('🔊 Synthesized audio chimes enabled', '🔔');
      } else {
        showToast('🔇 Audio chimes muted', '🔕');
      }
    }

    // --- DESKTOP NOTIFICATIONS & TAB BLINKER ---
    function initDesktopNotifications() {
      if ('Notification' in window && Notification.permission === 'default') {
        Notification.requestPermission();
      }
    }

    function sendDesktopNotification(title, body) {
      if ('Notification' in window && Notification.permission === 'granted') {
        try {
          new Notification(title, { body: body });
        } catch(e) {}
      }
    }

    let originalDocTitle = document.title;
    let blinkInterval = null;
    function triggerTabAlert(symbol, sentiment) {
      if (document.hasFocus()) return;
      if (blinkInterval) clearInterval(blinkInterval);
      let state = false;
      let count = 0;
      blinkInterval = setInterval(() => {
        count++;
        document.title = state ? `🚨 [${sentiment}] ${symbol} CATALYST!` : originalDocTitle;
        state = !state;
        if (count > 24 || document.hasFocus()) {
          clearInterval(blinkInterval);
          blinkInterval = null;
          document.title = originalDocTitle;
        }
      }, 750);
    }
    window.addEventListener('focus', () => {
      if (blinkInterval) {
        clearInterval(blinkInterval);
        blinkInterval = null;
        document.title = originalDocTitle;
      }
    });

    // --- FINANCIAL METRICS REGEX EXTRACTOR ---
    function extractFinancialMetrics(text) {
      if (!text) return [];
      const metrics = [];
      const inrMatches = text.match(/(?:Rs\\.?|₹|INR)\\s*[\\d,]+(?:\\.\\d+)?\\s*(?:Cr(?:ore)?|Lakh|mn|bn)?/gi);
      if (inrMatches) inrMatches.forEach(m => metrics.push({ type: 'currency', value: m.trim() }));
      const usdMatches = text.match(/\\$\\s*[\\d,]+(?:\\.\\d+)?\\s*(?:million|billion|M|B|mn|bn)?/gi);
      if (usdMatches) usdMatches.forEach(m => metrics.push({ type: 'currency', value: m.trim() }));
      const pctMatches = text.match(/[+-]?\\d+(?:\\.\\d+)?%/g);
      if (pctMatches) pctMatches.forEach(m => metrics.push({ type: 'percent', value: m.trim() }));
      const keywords = ['USFDA', 'FDA Approval', 'EIR', 'Bonus Issue', 'Dividend', 'Contract Win', 'Order Win', 'Acquisition', 'Demerger', 'Patent Granted'];
      keywords.forEach(kw => {
        if (new RegExp('\\\\b' + kw + '\\\\b', 'i').test(text)) {
          metrics.push({ type: 'keyword', value: kw });
        }
      });
      const seen = new Set();
      return metrics.filter(item => {
        const key = item.value.toLowerCase();
        if (seen.has(key)) return false;
        seen.add(key);
        return true;
      }).slice(0, 5);
    }

    // --- 180s FRESHNESS ENGINE ---
    function parseExchangeDate(dtStr) {
      if (!dtStr || typeof dtStr !== 'string') return null;
      const clean = dtStr.trim();
      const monthMap = { jan:0, feb:1, mar:2, apr:3, may:4, jun:5, jul:6, aug:7, sep:8, oct:9, nov:10, dec:11 };
      
      if (clean.includes(' ')) {
        const parts = clean.split(' ');
        const tSegments = (parts[1] || '').split(':').map(n => parseInt(n, 10));
        const hr = tSegments[0] || 0, min = tSegments[1] || 0, sec = tSegments[2] || 0;
        
        const dSegments = parts[0].split('-');
        if (dSegments.length === 3) {
          // Check if format is DD-Mon-YYYY (e.g. 10-Sep-2026)
          const mKey = dSegments[1].toLowerCase().slice(0, 3);
          if (mKey in monthMap) {
            const day = parseInt(dSegments[0], 10);
            const year = parseInt(dSegments[2], 10);
            return new Date(year, monthMap[mKey], day, hr, min, sec);
          }
          // Check if format is YYYY-MM-DD
          if (dSegments[0].length === 4) {
            const year = parseInt(dSegments[0], 10);
            const month = parseInt(dSegments[1], 10) - 1;
            const day = parseInt(dSegments[2], 10);
            return new Date(year, month, day, hr, min, sec);
          }
          // Check if format is DD-MM-YYYY
          if (dSegments[2].length === 4) {
            const day = parseInt(dSegments[0], 10);
            const month = parseInt(dSegments[1], 10) - 1;
            const year = parseInt(dSegments[2], 10);
            return new Date(year, month, day, hr, min, sec);
          }
        }
      }
      const direct = new Date(clean);
      return isNaN(direct.getTime()) ? null : direct;
    }

    function getFreshnessState(anDt) {
      if (!anDt) return { isStale: false, ageSec: 0, text: 'FRESH', badgeClass: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40', remainingSec: 180 };
      try {
        const parsed = parseExchangeDate(anDt);
        if (!parsed || isNaN(parsed.getTime())) {
          return { isStale: false, ageSec: 0, text: 'FRESH', badgeClass: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40', remainingSec: 180 };
        }
        const now = new Date();
        const ageSec = Math.max(0, Math.floor((now.getTime() - parsed.getTime()) / 1000));
        const remainingSec = Math.max(0, 180 - ageSec);
        const isStale = ageSec > 180;
        let text = '';
        let badgeClass = '';
        if (isStale) {
          text = `⏱️ Stale (+${ageSec}s)`;
          badgeClass = 'bg-gray-800 text-gray-500 border-gray-700';
        } else if (remainingSec >= 120) {
          text = `⚡ ${remainingSec}s left`;
          badgeClass = 'bg-emerald-950/80 text-emerald-300 border-emerald-500/50 shadow-sm';
        } else if (remainingSec >= 45) {
          text = `⏳ ${remainingSec}s left`;
          badgeClass = 'bg-amber-950/80 text-amber-300 border-amber-500/50 shadow-sm';
        } else {
          text = `🔥 ${remainingSec}s left`;
          badgeClass = 'bg-rose-950/80 text-rose-300 border-rose-500/50 shadow-sm animate-pulse';
        }
        return { isStale, ageSec, remainingSec, text, badgeClass };
      } catch (e) {
        return { isStale: false, ageSec: 0, text: 'FRESH', badgeClass: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40', remainingSec: 180 };
      }
    }

    function updateCountdowns() {
      const badges = document.querySelectorAll('.timer-badge');
      badges.forEach(badge => {
        const anDt = badge.getAttribute('data-andt');
        const fresh = getFreshnessState(anDt);
        badge.textContent = fresh.text;
        badge.className = `timer-badge px-2 py-0.5 rounded text-[10px] font-mono font-bold border transition-colors ${fresh.badgeClass}`;
      });

      // Update drawer freshness pill if drawer is currently open
      if (activeDrawerItem) {
        const drawerPill = document.getElementById('drawer-freshness-pill');
        if (drawerPill) {
          const fresh = getFreshnessState(activeDrawerItem.an_dt);
          drawerPill.textContent = fresh.text;
          drawerPill.className = `px-2 py-0.5 rounded text-[11px] font-bold border ${fresh.badgeClass}`;
        }
      }
    }

    // --- RISK BUDGET GAUGE ---
    function updateRiskBudgetGauge(placedCount) {
      const maxOrders = 3;
      const barsEl = document.getElementById('risk-gauge-bars');
      const textEl = document.getElementById('risk-gauge-text');
      if (!textEl) return;
      const count = Math.min(placedCount, maxOrders);
      textEl.textContent = `${count}/${maxOrders}`;

      if (barsEl) {
        let barsHTML = '';
        for (let i = 0; i < maxOrders; i++) {
          if (i < count) {
            if (count >= maxOrders) {
              barsHTML += '<span class="w-2.5 h-3 rounded-sm bg-rose-500 shadow-[0_0_6px_rgba(244,63,94,0.6)]"></span>';
            } else {
              barsHTML += '<span class="w-2.5 h-3 rounded-sm bg-amber-400 shadow-[0_0_6px_rgba(251,191,36,0.6)]"></span>';
            }
          } else {
            barsHTML += '<span class="w-2.5 h-3 rounded-sm bg-gray-700/80 border border-gray-600/40"></span>';
          }
        }
        barsEl.innerHTML = barsHTML;
      }

      if (count >= maxOrders) {
        textEl.className = 'text-rose-400 text-xs font-mono font-bold whitespace-nowrap';
      } else if (count > 0) {
        textEl.className = 'text-amber-300 text-xs font-mono font-bold whitespace-nowrap';
      } else {
        textEl.className = 'text-emerald-400 text-xs font-mono font-bold whitespace-nowrap';
      }
    }

    function showToast(msg, icon = '✅') {
      const toast = document.getElementById('toast');
      document.getElementById('toast-icon').textContent = icon;
      document.getElementById('toast-msg').textContent = msg;
      toast.classList.remove('opacity-0', 'translate-y-4', 'pointer-events-none');
      toast.classList.add('opacity-100', 'translate-y-0');
      setTimeout(() => {
        toast.classList.add('opacity-0', 'translate-y-4', 'pointer-events-none');
        toast.classList.remove('opacity-100', 'translate-y-0');
      }, 3500);
    }

    // --- MODALS CONTROLLER ---
    function openHotkeysModal() {
      const modal = document.getElementById('hotkeys-modal');
      const card = document.getElementById('hotkeys-modal-card');
      if (!modal || !card) return;
      modal.classList.remove('opacity-0', 'pointer-events-none');
      modal.classList.add('opacity-100');
      card.classList.remove('scale-95');
      card.classList.add('scale-100');
    }

    function closeHotkeysModal() {
      const modal = document.getElementById('hotkeys-modal');
      const card = document.getElementById('hotkeys-modal-card');
      if (!modal || !card) return;
      modal.classList.add('opacity-0', 'pointer-events-none');
      modal.classList.remove('opacity-100');
      card.classList.add('scale-95');
      card.classList.remove('scale-100');
    }

    function openSquareOffModal() {
      const modal = document.getElementById('squareoff-modal');
      const card = document.getElementById('squareoff-modal-card');
      if (!modal || !card) return;
      synth.playWarningChime();
      modal.classList.remove('opacity-0', 'pointer-events-none');
      modal.classList.add('opacity-100');
      card.classList.remove('scale-95');
      card.classList.add('scale-100');
    }

    function closeSquareOffModal() {
      const modal = document.getElementById('squareoff-modal');
      const card = document.getElementById('squareoff-modal-card');
      if (!modal || !card) return;
      modal.classList.add('opacity-0', 'pointer-events-none');
      modal.classList.remove('opacity-100');
      card.classList.add('scale-95');
      card.classList.remove('scale-100');
    }

    async function executeConfirmedSquareOff() {
      closeSquareOffModal();
      const btn = document.getElementById('square-off-btn');
      if (btn) {
        btn.disabled = true;
        btn.classList.add('opacity-50');
      }
      showToast('Initiating intraday square-off sequence...', '🛑');
      try {
        if (activeStrategyId === 'st14_bullish_ce') {
          const res = await fetch('/api/strategies/st14_bullish_ce/square-off', { method: 'POST' });
          if (res.ok) {
            const data = await res.json();
            showToast(`🛑 ${data.message || 'ST-14 positions squared off!'}`, '🛑');
            loadSt14Data();
          } else {
            const err = await res.json().catch(() => ({ detail: 'Square-off failed' }));
            showToast(`Square-off error: ${err.detail || 'Failed'}`, '❌');
          }
        } else {
          const res = await fetch('/api/trades/square-off', { method: 'POST' });
          if (res.ok) {
            const data = await res.json();
            const closedCount = (data.result && data.result.closed_positions) ? data.result.closed_positions.length : 0;
            const cancelledCount = (data.result && data.result.cancelled_orders) ? data.result.cancelled_orders.length : 0;
            showToast(`Square-off completed: ${cancelledCount} orders cancelled, ${closedCount} positions closed.`, '✅');
            fetchFeed();
          } else {
            const err = await res.json().catch(() => ({ detail: 'Square-off failed' }));
            showToast(`Square-off error: ${err.detail || 'Failed'}`, '❌');
          }
        }
      } catch (err) {
        showToast('Failed to trigger square-off request', '❌');
      } finally {
        if (btn) {
          btn.disabled = false;
          btn.classList.remove('opacity-50');
        }
      }
    }

    function confirmEmergencySquareOff() {
      openSquareOffModal();
    }

    function confirmSt14SquareOff() {
      openSquareOffModal();
    }

    // --- DETAILS DRAWER CONTROLLER ---
    function openDrawer(seqId) {
      const item = feedItems.find(i => i.seq_id === seqId);
      if (!item) return;
      activeDrawerItem = item;
      
      const drawer = document.getElementById('details-drawer');
      const backdrop = document.getElementById('details-drawer-backdrop');
      if (!drawer || !backdrop) return;
      
      document.getElementById('drawer-symbol-badge').textContent = item.symbol;
      document.getElementById('drawer-sec-id').textContent = item.security_id && item.security_id !== '0' ? `#${item.security_id}` : '#0';
      
      const cleanSym = (item.symbol || '').toUpperCase().trim();
      const dhanChartBtn = document.getElementById('drawer-dhan-chart-btn');
      if (dhanChartBtn) {
        dhanChartBtn.href = `https://tv.dhan.co/?symbol=NSE:${encodeURIComponent(cleanSym)}-EQ`;
      }
      const tvChartBtn = document.getElementById('drawer-tv-chart-btn');
      if (tvChartBtn) {
        tvChartBtn.href = `https://in.tradingview.com/chart/?symbol=NSE:${encodeURIComponent(cleanSym)}`;
      }
      
      const sentimentBadge = document.getElementById('drawer-sentiment-badge');
      const isBullish = item.sentiment === 'BULLISH';
      const isBearish = item.sentiment === 'BEARISH';
      const isNoise = !!item.is_noise;
      const isMarketClosed = item.sentiment === 'MARKET_CLOSED';
      
      if (isMarketClosed) {
        sentimentBadge.textContent = '🌙 MARKET CLOSED';
        sentimentBadge.className = 'text-xs font-bold px-2 py-0.5 rounded font-mono bg-amber-950/70 text-amber-300 border border-amber-800/60';
      } else if (isNoise) {
        sentimentBadge.textContent = '🔇 NOISE';
        sentimentBadge.className = 'text-xs font-bold px-2 py-0.5 rounded font-mono bg-gray-800 text-gray-400 border border-gray-700';
      } else if (isBullish) {
        sentimentBadge.textContent = `🟢 BULLISH (${item.confidence}%)`;
        sentimentBadge.className = 'text-xs font-bold px-2 py-0.5 rounded font-mono bg-emerald-500/20 text-emerald-300 border border-emerald-500/40';
      } else {
        sentimentBadge.textContent = `🔴 BEARISH (${item.confidence}%)`;
        sentimentBadge.className = 'text-xs font-bold px-2 py-0.5 rounded font-mono bg-rose-500/20 text-rose-300 border border-rose-500/40';
      }
      
      document.getElementById('drawer-time').textContent = item.an_dt || item.timestamp || '--:--:--';
      const fresh = getFreshnessState(item.an_dt);
      const freshnessPill = document.getElementById('drawer-freshness-pill');
      freshnessPill.textContent = fresh.text;
      freshnessPill.className = `px-2 py-0.5 rounded text-[11px] font-bold border ${fresh.badgeClass}`;
      
      document.getElementById('drawer-catalyst-category').textContent = (item.catalyst_type || 'GENERAL').toUpperCase();
      document.getElementById('drawer-confidence-pill').textContent = `${item.confidence || 0}% Conf`;
      document.getElementById('drawer-summary').textContent = item.summary || item.filter_reason || 'No summary available.';
      
      document.getElementById('drawer-seq-id').textContent = `Seq ID: ${item.seq_id}`;
      document.getElementById('drawer-raw-text').textContent = item.details || item.desc || 'No announcement details.';
      
      const order = item.order || {};
      const isTraded = !!(order.placed && (order.traded_price || order.fill_price));
      const basePrice = isTraded ? (order.traded_price || order.fill_price) : (order.entry_price || order.ltp || 0);
      const baseTag = isTraded ? 'vs Traded' : 'vs Limit';
      const currentPrice = order.current_ltp || order.ltp || basePrice;
      document.getElementById('drawer-entry-price').textContent = `₹${order.entry_price ? order.entry_price.toFixed(2) : (order.ltp ? order.ltp.toFixed(2) : '0.00')}`;
      document.getElementById('drawer-target-price').textContent = `₹${order.target_price ? order.target_price.toFixed(2) : '0.00'}`;
      document.getElementById('drawer-sl-price').textContent = `₹${order.stop_loss_price ? order.stop_loss_price.toFixed(2) : '0.00'}`;
      document.getElementById('drawer-qty-info').textContent = `Position: ${order.quantity || 0} sh`;
      
      const drawerLivePnl = document.getElementById('drawer-live-pnl');
      if (basePrice > 0 && currentPrice > 0) {
        let pnlDiff = 0;
        let pnlPct = 0;
        if (isBullish) {
          pnlDiff = currentPrice - basePrice;
          pnlPct = (pnlDiff / basePrice) * 100;
        } else {
          pnlDiff = basePrice - currentPrice;
          pnlPct = (pnlDiff / basePrice) * 100;
        }
        const isProfit = pnlDiff >= 0;
        const arrow = isProfit ? '▲' : '▼';
        const sign = pnlDiff >= 0 ? '+' : '';
        const color = isProfit ? 'text-emerald-400' : 'text-rose-400';
        drawerLivePnl.innerHTML = `
          <div class="flex flex-col items-center">
            <span class="${color} font-bold">${arrow} ${sign}₹${Math.abs(pnlDiff).toFixed(2)} (${sign}${pnlPct.toFixed(2)}%)</span>
            <span class="text-[9px] text-gray-500 font-normal mt-0.5">${baseTag} (₹${basePrice.toFixed(2)})</span>
          </div>
        `;
      } else {
        drawerLivePnl.textContent = '--';
      }
      
      // Footer Action Button
      const btnContainer = document.getElementById('drawer-action-btn-container');
      if (isNoise || isMarketClosed) {
        btnContainer.innerHTML = `<span class="text-xs font-mono text-gray-500 italic">${item.filter_reason || 'Not Actionable'}</span>`;
      } else if (order.placed) {
        btnContainer.innerHTML = `
          <span class="px-3 py-1.5 text-xs font-mono font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 rounded-lg flex items-center gap-1.5 shadow-sm">
            <span>✅</span> Order Placed (${order.order_id || 'SIMULATED'})
          </span>
        `;
      } else if (order.status === 'PENDING_APPROVAL') {
        if (item.is_stale) {
          btnContainer.innerHTML = `
            <button disabled class="bg-gray-800 text-gray-500 font-bold text-xs px-4 py-2 rounded-lg border border-gray-700 cursor-not-allowed flex items-center gap-1.5 opacity-60">
              <span>⏱️ Window Expired (>180s)</span>
            </button>
          `;
        } else {
          const act = isBullish ? 'BUY' : 'SELL';
          const btnBg = isBullish ? 'bg-emerald-600 hover:bg-emerald-500 shadow-emerald-600/40 border-emerald-400/40' : 'bg-rose-600 hover:bg-rose-500 shadow-rose-600/40 border-rose-400/40';
          const label = isBullish ? '🚀 Approve Buy Order [A]' : '🔻 Approve Short Sell [S]';
          btnContainer.innerHTML = `
            <button onclick="placeOrder('${item.seq_id}', '${item.symbol}', '${act}', ${order.ltp || 300.0}, ${item.confidence}, '${item.catalyst_type}'); closeDrawer();" class="${btnBg} text-white font-bold text-xs px-4 py-2 rounded-lg transition shadow-lg active:scale-95 flex items-center gap-1.5 border">
              <span>${label}</span>
            </button>
          `;
        }
      } else {
        btnContainer.innerHTML = `<span class="text-xs font-mono text-gray-500">Status: ${order.status || 'SKIPPED'}</span>`;
      }
      
      drawer.classList.remove('translate-x-full');
      backdrop.classList.remove('opacity-0', 'pointer-events-none');
      backdrop.classList.add('opacity-100');
    }

    function closeDrawer() {
      const drawer = document.getElementById('details-drawer');
      const backdrop = document.getElementById('details-drawer-backdrop');
      if (drawer) drawer.classList.add('translate-x-full');
      if (backdrop) {
        backdrop.classList.remove('opacity-100');
        backdrop.classList.add('opacity-0', 'pointer-events-none');
      }
      activeDrawerItem = null;
    }

    // --- REAL-TIME INTERACTIVE CHART MODAL CONTROLLER ---
    function openChartModal(symbol) {
      if (!symbol) return;
      const cleanSym = symbol.toUpperCase().trim();
      const modal = document.getElementById('chart-modal');
      const symBadge = document.getElementById('chart-modal-symbol');
      const tvLink = document.getElementById('chart-modal-tv-link');
      const container = document.getElementById('chart-modal-container');

      if (symBadge) symBadge.textContent = cleanSym;
      if (tvLink) tvLink.href = `https://in.tradingview.com/chart/?symbol=NSE:${encodeURIComponent(cleanSym)}`;
      if (modal) modal.classList.remove('hidden');

      if (container) {
        container.innerHTML = `
          <iframe
            src="https://s.tradingview.com/widgetembed/?frameElementId=tradingview_widget&symbol=NSE%3A${encodeURIComponent(cleanSym)}&interval=5&hidesidetoolbar=0&symboledit=1&saveimage=1&toolbarbg=162032&studies=%5B%22STD%3BVWAP%22%2C%22STD%3BEverget%2FSuperTrend%22%5D&theme=dark&style=1&timezone=Asia%2FKolkata&studies_overrides=%7B%7D&overrides=%7B%7D&enabled_features=%5B%5D&disabled_features=%5B%5D&locale=in&utmsource=localhost"
            style="width: 100%; height: 100%; border: none;"
            allowfullscreen
          ></iframe>
        `;
      }
    }

    function closeChartModal() {
      const modal = document.getElementById('chart-modal');
      if (modal) modal.classList.add('hidden');
      const container = document.getElementById('chart-modal-container');
      if (container) container.innerHTML = '';
    }

    function copyFilingText() {
      if (activeDrawerItem) {
        const text = `${activeDrawerItem.symbol} [${activeDrawerItem.an_dt || ''}]\n${activeDrawerItem.desc}\n\n${activeDrawerItem.details || ''}`;
        navigator.clipboard.writeText(text).then(() => {
          showToast('📋 Copied announcement to clipboard!', '📋');
        }).catch(() => {
          showToast('Failed copying to clipboard', '❌');
        });
      }
    }

    // --- KEYBOARD HOTKEYS EVENT LISTENER ---
    function updateRowSelection() {
      const rows = document.querySelectorAll('#table-body tr.feed-row');
      rows.forEach((r, idx) => {
        if (idx === selectedRowIndex) {
          r.classList.add('ring-2', 'ring-emerald-400', 'bg-[#1e293b]');
          r.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        } else {
          r.classList.remove('ring-2', 'ring-emerald-400', 'bg-[#1e293b]');
        }
      });
    }

    document.addEventListener('keydown', function(e) {
      if (['INPUT', 'TEXTAREA'].includes(document.activeElement.tagName)) return;
      const key = e.key.toUpperCase();
      const isShift = e.shiftKey;
      
      if (key === 'ESCAPE') {
        closeChartModal();
        closeDrawer();
        closeHotkeysModal();
        closeSquareOffModal();
        closeTokenModal();
        return;
      }
      if (key === '?' || (e.key === '?' && isShift)) {
        openHotkeysModal();
        return;
      }
      if (key === 'Q' && isShift) {
        confirmEmergencySquareOff();
        return;
      }
      if (key === 'M') {
        toggleAudioSound();
        return;
      }
      
      const rows = document.querySelectorAll('#table-body tr.feed-row');
      if (rows.length === 0) return;
      
      if (key === 'J' || e.key === 'ArrowDown') {
        selectedRowIndex = Math.min(rows.length - 1, selectedRowIndex + 1);
        updateRowSelection();
        e.preventDefault();
      } else if (key === 'K' || e.key === 'ArrowUp') {
        selectedRowIndex = Math.max(0, selectedRowIndex - 1);
        updateRowSelection();
        e.preventDefault();
      } else if (key === 'ENTER' || e.key === ' ') {
        if (selectedRowIndex >= 0 && selectedRowIndex < rows.length) {
          const seqId = rows[selectedRowIndex].getAttribute('data-seq-id');
          if (seqId) openDrawer(seqId);
          e.preventDefault();
        }
      } else if (key === 'A' || key === 'B') {
        if (selectedRowIndex >= 0 && selectedRowIndex < rows.length) {
          const seqId = rows[selectedRowIndex].getAttribute('data-seq-id');
          const item = feedItems.find(i => i.seq_id === seqId);
          if (item && item.order && item.order.status === 'PENDING_APPROVAL' && !item.is_stale) {
            placeOrder(item.seq_id, item.symbol, 'BUY', item.order.ltp || 300.0, item.confidence, item.catalyst_type);
            synth.playOrderChime();
            e.preventDefault();
          }
        }
      } else if (key === 'S') {
        if (selectedRowIndex >= 0 && selectedRowIndex < rows.length) {
          const seqId = rows[selectedRowIndex].getAttribute('data-seq-id');
          const item = feedItems.find(i => i.seq_id === seqId);
          if (item && item.order && item.order.status === 'PENDING_APPROVAL' && !item.is_stale) {
            placeOrder(item.seq_id, item.symbol, 'SELL', item.order.ltp || 300.0, item.confidence, item.catalyst_type);
            synth.playOrderChime();
            e.preventDefault();
          }
        }
      }
    });

    async function launchDhanOAuth() {
      const feedback = document.getElementById('modal-feedback');
      const btn = document.getElementById('btn-oauth-login');

      btn.disabled = true;
      btn.classList.add('opacity-50');
      btn.innerHTML = '<span>⏳ Connecting to Dhan...</span>';

      try {
        const res = await fetch('/api/auth/dhan/login');
        const data = await res.json();

        if (res.ok && data.success && data.login_url) {
          showToast('Redirecting to official Dhan login portal...', '⚡');
          setTimeout(() => {
            window.location.href = data.login_url;
          }, 400);
        } else {
          feedback.className = 'block bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs p-2.5 rounded-lg';
          feedback.textContent = `❌ ${data.message || 'Failed to initiate login. Please check server .env configuration.'}`;
        }
      } catch (err) {
        feedback.className = 'block bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs p-2.5 rounded-lg';
        feedback.textContent = '❌ Failed connecting to Dhan login service.';
      } finally {
        btn.disabled = false;
        btn.classList.remove('opacity-50');
        btn.innerHTML = '<span>🚀 Log In via Dhan Portal</span>';
      }
    }

    function toggleUserMenu() {
      const dropdown = document.getElementById('user-menu-dropdown');
      if (dropdown) dropdown.classList.toggle('hidden');
    }

    document.addEventListener('click', function(e) {
      const container = document.getElementById('user-account-container');
      const dropdown = document.getElementById('user-menu-dropdown');
      if (dropdown && container && !container.contains(e.target)) {
        dropdown.classList.add('hidden');
      }
    });

    async function logoutDhan() {
      try {
        const res = await fetch('/api/auth/logout', { method: 'POST' });
        if (res.ok) {
          showToast('👋 Logged out from Dhan trading session.', 'ℹ️');
          fetchTokenStatus();
          setTimeout(() => {
            openLoginScreen();
          }, 300);
        } else {
          showToast('Logout request failed', '❌');
        }
      } catch (err) {
        showToast('Logout request failed', '❌');
      }
    }

    async function logoutApp() {
      try {
        await fetch('/api/auth/app-logout', { method: 'POST' });
        window.location.href = '/login?logged_out=true';
      } catch (err) {
        window.location.href = '/login?logged_out=true';
      }
    }

    function openLoginScreen() {
      openTokenModal();
    }

    async function fetchTokenStatus() {
      try {
        const res = await fetch('/api/auth/me');
        if (res.ok) {
          const data = await res.json();
          const badge = document.getElementById('telemetry-token-status');
          const headerMask = document.getElementById('header-token-mask');
          const dot = document.getElementById('token-indicator-dot');
          const currentBadge = document.getElementById('current-token-badge');
          const tokenBtn = document.getElementById('token-btn');
          const headerLoginBtn = document.getElementById('btn-header-login');
          const userProfileWidget = document.getElementById('user-profile-widget');
          const userClientIdLabel = document.getElementById('user-client-id-label');
          const menuClientId = document.getElementById('menu-client-id');
          const menuExpiry = document.getElementById('menu-expiry-info');
          const sessionAlert = document.getElementById('login-session-alert');

          if (data.authenticated) {
            if (headerLoginBtn) headerLoginBtn.classList.add('hidden');
            if (userProfileWidget) userProfileWidget.classList.remove('hidden');
            if (userClientIdLabel) userClientIdLabel.textContent = data.client_id ? `DHAN ${data.client_id}` : 'DHAN USER';
            if (menuClientId) menuClientId.textContent = `Client ID: ${data.client_id || 'N/A'}`;
            if (menuExpiry) {
              menuExpiry.textContent = data.expiry_message || '🟢 Active Session';
              menuExpiry.className = 'text-[10px] text-emerald-400 font-mono mt-0.5';
            }
            if (badge) {
              badge.textContent = 'Active';
              badge.className = 'text-emerald-400 font-mono font-bold';
            }
            if (headerMask) {
              headerMask.textContent = 'Active';
              headerMask.className = 'text-xs font-mono font-bold text-emerald-400 group-hover:text-emerald-300';
            }
            if (dot) {
              dot.className = 'w-2 h-2 rounded-full bg-emerald-400 animate-pulse';
            }
            if (tokenBtn) {
              tokenBtn.className = 'group bg-[#162032] hover:bg-[#1f293d] active:scale-95 border border-emerald-500/40 hover:border-emerald-400/70 px-3.5 py-1.5 rounded-xl transition-all shadow-md flex items-center gap-2.5';
            }
            if (currentBadge) {
              currentBadge.innerHTML = `<span class="text-emerald-400 font-bold">🟢 Active</span> <span class="text-gray-400 text-[10px]">(${data.expiry_message || 'Valid session'})</span>`;
            }
            if (sessionAlert) {
              sessionAlert.className = 'hidden';
            }
          } else if (data.is_expired) {
            const expText = data.expiry_message || 'Token Expired';
            if (headerLoginBtn) headerLoginBtn.classList.remove('hidden');
            if (userProfileWidget) userProfileWidget.classList.add('hidden');
            if (badge) {
              badge.textContent = 'Expired';
              badge.className = 'text-rose-400 font-mono font-bold';
            }
            if (headerMask) {
              headerMask.textContent = 'Expired';
              headerMask.className = 'text-xs font-mono font-bold text-rose-400 group-hover:text-rose-300';
            }
            if (dot) {
              dot.className = 'w-2 h-2 rounded-full bg-rose-500 animate-ping';
            }
            if (tokenBtn) {
              tokenBtn.className = 'group bg-rose-950/40 hover:bg-rose-900/50 active:scale-95 border border-rose-500/70 hover:border-rose-400 px-3.5 py-1.5 rounded-xl transition-all shadow-lg shadow-rose-950/50 flex items-center gap-2.5 ring-2 ring-rose-500/30';
            }
            if (currentBadge) {
              currentBadge.innerHTML = `<span class="text-rose-400 font-bold">⚠️ Expired</span> <span class="text-gray-400 text-[10px]">(${expText})</span>`;
            }
            if (sessionAlert) {
              sessionAlert.className = 'block bg-rose-500/15 border border-rose-500/40 text-rose-200 text-xs p-3 rounded-xl font-medium shadow-inner';
              sessionAlert.innerHTML = `⚠️ <b>Dhan Session Expired:</b> ${expText}. Please 1-Click Login to reconnect live trading.`;
            }
            if (!window._hasAlertedExpiry) {
              window._hasAlertedExpiry = true;
              showToast(`❌ Dhan Session EXPIRED: ${expText}. Please login.`, '⚠️');
              if (!window._hasDismissedModal) {
                openLoginScreen();
              }
            }
          } else {
            if (headerLoginBtn) headerLoginBtn.classList.remove('hidden');
            if (userProfileWidget) userProfileWidget.classList.add('hidden');
            if (badge) {
              badge.textContent = 'Not Logged In';
              badge.className = 'text-amber-400 font-mono font-semibold';
            }
            if (headerMask) {
              headerMask.textContent = 'Not Logged In';
              headerMask.className = 'text-xs font-mono font-bold text-amber-400/80 group-hover:text-amber-300';
            }
            if (dot) {
              dot.className = 'w-2 h-2 rounded-full bg-amber-400';
            }
            if (tokenBtn) {
              tokenBtn.className = 'group bg-[#162032] hover:bg-[#1f293d] active:scale-95 border border-gray-700 hover:border-gray-500 px-3.5 py-1.5 rounded-xl transition-all shadow-md flex items-center gap-2.5';
            }
            if (currentBadge) {
              currentBadge.textContent = 'Current: Not Configured';
            }
            if (sessionAlert) {
              sessionAlert.className = 'block bg-amber-500/10 border border-amber-500/30 text-amber-200 text-xs p-3 rounded-xl font-medium';
              sessionAlert.innerHTML = `ℹ️ <b>Dhan Login Required:</b> Connect your DhanHQ trading account via 1-Click OAuth.`;
            }
          }
        }
      } catch (err) {
        console.error('Failed fetching token status:', err);
      }
    }

    function openTokenModal() {
      const modal = document.getElementById('token-modal');
      const card = document.getElementById('token-modal-card');
      const feedback = document.getElementById('modal-feedback');
      if (feedback) feedback.className = 'hidden text-xs p-2.5 rounded-lg';
      fetchTokenStatus();
      modal.classList.remove('opacity-0', 'pointer-events-none');
      modal.classList.add('opacity-100');
      card.classList.remove('scale-95');
      card.classList.add('scale-100');
    }

    function closeTokenModal() {
      const modal = document.getElementById('token-modal');
      const card = document.getElementById('token-modal-card');
      modal.classList.add('opacity-0', 'pointer-events-none');
      modal.classList.remove('opacity-100');
      card.classList.add('scale-95');
      card.classList.remove('scale-100');
    }

    async function saveManualToken() {
      const tokenInput = document.getElementById('modal-manual-token');
      const token = tokenInput ? tokenInput.value.trim() : '';
      const feedback = document.getElementById('modal-feedback');
      const btn = document.getElementById('btn-save-manual-token');

      if (!token) {
        if (feedback) {
          feedback.className = 'block bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs p-2.5 rounded-lg';
          feedback.textContent = 'Please paste a valid Dhan Access Token.';
        }
        return;
      }

      if (btn) {
        btn.disabled = true;
        btn.textContent = 'Saving...';
      }

      try {
        const res = await fetch('/api/settings/token', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            access_token: token,
            client_id: '1104872040',
            dry_run: isDryRun
          })
        });
        const data = await res.json();
        if (res.ok && data.success) {
          if (feedback) {
            feedback.className = 'block bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 text-xs p-2.5 rounded-lg';
            feedback.textContent = '✅ Access Token updated and active in production!';
          }
          showToast('✅ Dhan Access Token updated!', '🔑');
          tokenInput.value = '';
          fetchTokenStatus();
          setTimeout(() => { closeTokenModal(); }, 1200);
        } else {
          if (feedback) {
            feedback.className = 'block bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs p-2.5 rounded-lg';
            feedback.textContent = `❌ ${data.expiry_message || 'Failed to update token.'}`;
          }
        }
      } catch (err) {
        if (feedback) {
          feedback.className = 'block bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs p-2.5 rounded-lg';
          feedback.textContent = '❌ Failed to connect to server.';
        }
      } finally {
        if (btn) {
          btn.disabled = false;
          btn.textContent = 'Save';
        }
      }
    }

    function updateStrategyEngineUI() {
      // 1. ST-NEWS Elements
      const btn = document.getElementById('toggle-engine-btn');
      const label = document.getElementById('engine-status-label');
      const indicator = document.getElementById('engine-status-indicator');
      const toggleModeBtn = document.getElementById('toggle-mode-btn');
      const toggleAutoBtn = document.getElementById('toggle-auto-btn');
      
      const emptyHeading = document.getElementById('empty-state-heading');
      const emptyDesc = document.getElementById('empty-state-desc');
      const emptyRadarPing = document.getElementById('empty-radar-ping');
      const emptyRadarPulse = document.getElementById('empty-radar-pulse');
      const emptyRadarIcon = document.getElementById('empty-radar-icon');
      const emptyStateDot = document.getElementById('empty-state-dot');
      const emptyStatusText = document.getElementById('empty-state-status-text');
      const radarPingDot = document.getElementById('radar-ping-dot');
      const radarSolidDot = document.getElementById('radar-solid-dot');

      if (isNewsEngineActive) {
        if (btn) {
          btn.className = 'px-2.5 py-1 text-xs font-bold rounded-lg transition flex items-center gap-1.5 shadow border border-emerald-500/50 bg-emerald-950/70 text-emerald-300 hover:bg-emerald-900 active:scale-95 cursor-pointer';
          btn.setAttribute('title', 'Master Power Switch: Strategy Engine is ACTIVE. Click to Pause (suspends background polling & AI grading).');
        }
        if (label) label.textContent = 'ENGINE: ACTIVE';
        if (indicator) indicator.className = 'w-2 h-2 rounded-full bg-emerald-400 animate-pulse';

        // Re-enable dependent execution controls
        if (toggleModeBtn) {
          toggleModeBtn.disabled = false;
          toggleModeBtn.classList.remove('opacity-40', 'cursor-not-allowed');
          toggleModeBtn.setAttribute('title', 'Click to toggle between VIRTUAL (Simulated) and LIVE TRADING');
        }
        if (toggleAutoBtn) {
          toggleAutoBtn.disabled = false;
          toggleAutoBtn.classList.remove('opacity-40', 'cursor-not-allowed');
          toggleAutoBtn.setAttribute('title', 'Toggle AI Automatic Order Placement');
        }

        if (radarPingDot) radarPingDot.className = 'animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75';
        if (radarSolidDot) radarSolidDot.className = 'relative inline-flex rounded-full h-2 w-2 bg-emerald-500';

        if (emptyHeading) emptyHeading.innerHTML = '<span>Live Radar Active — Scanning NSE Corporate Feed</span>';
        if (emptyDesc) emptyDesc.textContent = 'Actively monitoring 228 F&O tickers on NSE. The AI filter automatically discards routine compliance noise and will alert here the moment an actionable market catalyst breaks.';
        if (emptyRadarPing) emptyRadarPing.className = 'absolute w-16 h-16 rounded-full bg-emerald-500/10 animate-ping';
        if (emptyRadarPulse) emptyRadarPulse.className = 'absolute w-12 h-12 rounded-full bg-emerald-500/20 animate-pulse';
        if (emptyRadarIcon) emptyRadarIcon.textContent = '📡';
        if (emptyStateDot) emptyStateDot.className = 'w-2 h-2 rounded-full bg-emerald-400 animate-pulse';
        if (emptyStatusText) {
          emptyStatusText.textContent = 'Listening for catalysts...';
          emptyStatusText.className = 'text-indigo-300 font-semibold';
        }
      } else {
        if (btn) {
          btn.className = 'px-2.5 py-1 text-xs font-bold rounded-lg transition flex items-center gap-1.5 shadow border border-amber-500/50 bg-amber-950/70 text-amber-300 hover:bg-amber-900 active:scale-95 cursor-pointer animate-pulse-subtle';
          btn.setAttribute('title', 'Master Power Switch: Strategy Engine is PAUSED. Click to Start/Resume.');
        }
        if (label) label.textContent = 'ENGINE: PAUSED';
        if (indicator) indicator.className = 'w-2 h-2 rounded-full bg-amber-400';

        // Dim & lock dependent execution controls when strategy is paused
        if (toggleModeBtn) {
          toggleModeBtn.disabled = true;
          toggleModeBtn.classList.add('opacity-40', 'cursor-not-allowed');
          toggleModeBtn.setAttribute('title', 'Strategy engine is paused. Start strategy to change execution mode.');
        }
        if (toggleAutoBtn) {
          toggleAutoBtn.disabled = true;
          toggleAutoBtn.classList.add('opacity-40', 'cursor-not-allowed');
          toggleAutoBtn.setAttribute('title', 'Strategy engine is paused. Start strategy to change auto-order settings.');
        }

        if (radarPingDot) radarPingDot.className = 'hidden';
        if (radarSolidDot) radarSolidDot.className = 'relative inline-flex rounded-full h-2 w-2 bg-amber-500';

        if (emptyHeading) emptyHeading.innerHTML = '<span class="text-amber-300 flex items-center justify-center gap-2"><span>⏸️</span> <span>Strategy Engine Paused — Radar Standby</span></span>';
        if (emptyDesc) emptyDesc.innerHTML = 'Background NSE announcement polling and Gemini AI grading are completely stopped. Click <button onclick="toggleStrategyEngine(\'st_news\')" class="underline font-bold text-amber-400 hover:text-amber-300 cursor-pointer">Start Engine</button> above or below to resume active scanning.';
        if (emptyRadarPing) emptyRadarPing.className = 'hidden';
        if (emptyRadarPulse) emptyRadarPulse.className = 'hidden';
        if (emptyRadarIcon) emptyRadarIcon.textContent = '⏸️';
        if (emptyStateDot) emptyStateDot.className = 'w-2 h-2 rounded-full bg-amber-400';
        if (emptyStatusText) {
          emptyStatusText.textContent = 'Engine Paused (No API calls)';
          emptyStatusText.className = 'text-amber-300 font-semibold';
        }
      }

      // 2. ST-14 Elements
      const st14Btn = document.getElementById('st14-toggle-engine-btn');
      const st14Label = document.getElementById('st14-engine-status-label');
      const st14Indicator = document.getElementById('st14-engine-status-indicator');
      const st14ToggleModeBtn = document.getElementById('st14-toggle-mode-btn');
      const st14ToggleAutoBtn = document.getElementById('st14-toggle-auto-btn');
      const st14StatusPill = document.getElementById('st14-status-pill');
      const st14StatusTxt = document.getElementById('st14-status-txt');
      const st14StatusDot = document.getElementById('st14-status-dot');

      if (isSt14EngineActive) {
        if (st14Btn) {
          st14Btn.className = 'px-2.5 py-1 text-xs font-bold rounded-lg transition flex items-center gap-1.5 shadow border border-emerald-500/50 bg-emerald-950/70 text-emerald-300 hover:bg-emerald-900 active:scale-95 cursor-pointer';
          st14Btn.setAttribute('title', 'ST-14 Engine is ACTIVE. Click to Pause (suspends 1-Hr scan & 5-Min breakout monitor).');
        }
        if (st14Label) st14Label.textContent = 'ENGINE: ACTIVE';
        if (st14Indicator) st14Indicator.className = 'w-2 h-2 rounded-full bg-emerald-400 animate-pulse';

        if (st14ToggleModeBtn) {
          st14ToggleModeBtn.disabled = false;
          st14ToggleModeBtn.classList.remove('opacity-40', 'cursor-not-allowed');
          st14ToggleModeBtn.setAttribute('title', 'Click to toggle between VIRTUAL (Paper Trading) and LIVE TRADING');
        }
        if (st14ToggleAutoBtn) {
          st14ToggleAutoBtn.disabled = false;
          st14ToggleAutoBtn.classList.remove('opacity-40', 'cursor-not-allowed');
          st14ToggleAutoBtn.setAttribute('title', 'Toggle Automated 1-OTM CE Super Order Placement');
        }

        if (st14StatusPill) st14StatusPill.className = 'px-2 py-0.5 rounded-full text-[11px] font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 flex items-center gap-1.5';
        if (st14StatusTxt) st14StatusTxt.textContent = 'ACTIVE';
        if (st14StatusDot) st14StatusDot.className = 'w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse';
      } else {
        if (st14Btn) {
          st14Btn.className = 'px-2.5 py-1 text-xs font-bold rounded-lg transition flex items-center gap-1.5 shadow border border-amber-500/50 bg-amber-950/70 text-amber-300 hover:bg-amber-900 active:scale-95 cursor-pointer animate-pulse-subtle';
          st14Btn.setAttribute('title', 'ST-14 Engine is PAUSED. Click to Start/Resume.');
        }
        if (st14Label) st14Label.textContent = 'ENGINE: PAUSED';
        if (st14Indicator) st14Indicator.className = 'w-2 h-2 rounded-full bg-amber-400';

        if (st14ToggleModeBtn) {
          st14ToggleModeBtn.disabled = true;
          st14ToggleModeBtn.classList.add('opacity-40', 'cursor-not-allowed');
          st14ToggleModeBtn.setAttribute('title', 'ST-14 engine is paused. Start engine to change mode.');
        }
        if (st14ToggleAutoBtn) {
          st14ToggleAutoBtn.disabled = true;
          st14ToggleAutoBtn.classList.add('opacity-40', 'cursor-not-allowed');
          st14ToggleAutoBtn.setAttribute('title', 'ST-14 engine is paused. Start engine to change auto-order.');
        }

        if (st14StatusPill) st14StatusPill.className = 'px-2 py-0.5 rounded-full text-[11px] font-bold bg-amber-500/20 text-amber-300 border border-amber-500/40 flex items-center gap-1.5';
        if (st14StatusTxt) st14StatusTxt.textContent = 'PAUSED';
        if (st14StatusDot) st14StatusDot.className = 'w-1.5 h-1.5 rounded-full bg-amber-400';
      }

      if (typeof updateSt14TelemetryUI === 'function' && st14Telemetry) {
        updateSt14TelemetryUI(st14Telemetry);
      }
    }

    async function toggleStrategyEngine(strategyId = null, targetStatus = null) {
      const stratId = strategyId || activeStrategyId || 'st_news';
      try {
        const currentActive = (stratId === 'st14_bullish_ce') ? isSt14EngineActive : isNewsEngineActive;
        const nextStatus = targetStatus || (currentActive ? 'PAUSED' : 'ACTIVE');
        const res = await fetch(`/api/strategies/${stratId}/toggle-status`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ status: nextStatus })
        });
        if (res.ok) {
          const data = await res.json();
          const isAct = (data.status === 'ACTIVE');
          if (stratId === 'st_news') {
            isNewsEngineActive = isAct;
          } else if (stratId === 'st14_bullish_ce') {
            isSt14EngineActive = isAct;
            loadSt14Data();
          }
          syncActiveStrategyState();
          loadStrategies();
          const stratName = (stratId === 'st14_bullish_ce') ? 'ST-14 Bullish CE' : 'ST-NEWS Catalyst';
          if (isAct) {
            showToast(`🟢 ${stratName} Engine Started! Active scanning.`, '⚡');
          } else {
            showToast(`⏸️ ${stratName} Engine Paused. Execution suspended.`, '⏸️');
          }
        } else {
          showToast('Failed to toggle Strategy Status', '❌');
        }
      } catch (err) {
        showToast('Failed to toggle Strategy Status', '❌');
      }
    }

    function updateExecutionModeUI() {
      // 1. ST-NEWS Elements
      const btn = document.getElementById('toggle-mode-btn');
      const label = document.getElementById('mode-status-label');
      const indicator = document.getElementById('mode-status-indicator');
      const modeText = document.getElementById('mode-text');

      if (btn && label && indicator) {
        if (isNewsDryRun) {
          btn.className = `px-2.5 py-1 text-xs font-bold rounded-lg transition flex items-center gap-1.5 shadow bg-amber-600/90 text-amber-100 hover:bg-amber-600 border border-amber-500/40 ${!isNewsEngineActive ? 'opacity-40 cursor-not-allowed' : ''}`;
          label.textContent = 'VIRTUAL';
          indicator.className = 'w-2 h-2 rounded-full bg-amber-300';
          if (modeText) {
            modeText.textContent = 'VIRTUAL (Simulated)';
            modeText.className = 'text-amber-400 font-mono font-semibold';
          }
        } else {
          btn.className = `px-2.5 py-1 text-xs font-bold rounded-lg transition flex items-center gap-1.5 shadow bg-emerald-600 text-white hover:bg-emerald-500 border border-emerald-400/40 animate-pulse-subtle ${!isNewsEngineActive ? 'opacity-40 cursor-not-allowed' : ''}`;
          label.textContent = 'LIVE';
          indicator.className = 'w-2 h-2 rounded-full bg-white animate-pulse';
          if (modeText) {
            modeText.textContent = 'LIVE (Real Orders)';
            modeText.className = 'text-emerald-400 font-mono font-bold';
          }
        }
      }

      // 2. ST-14 Elements
      const st14Btn = document.getElementById('st14-toggle-mode-btn');
      const st14Label = document.getElementById('st14-mode-status-label');
      const st14Indicator = document.getElementById('st14-mode-status-indicator');
      const st14ModeBadge = document.getElementById('st14-mode-badge');

      if (st14Btn && st14Label && st14Indicator) {
        if (isSt14DryRun) {
          st14Btn.className = `px-2.5 py-1 text-xs font-bold rounded-lg transition flex items-center gap-1.5 shadow border border-amber-500/40 bg-amber-600/90 text-amber-100 hover:bg-amber-600 active:scale-95 cursor-pointer ${!isSt14EngineActive ? 'opacity-40 cursor-not-allowed' : ''}`;
          st14Label.textContent = 'VIRTUAL';
          st14Indicator.className = 'w-2 h-2 rounded-full bg-amber-300';
          if (st14ModeBadge) {
            st14ModeBadge.textContent = 'VIRTUAL';
            st14ModeBadge.className = 'px-1.5 py-0.2 rounded text-[10px] font-bold bg-amber-950 text-amber-300 border border-amber-800';
          }
        } else {
          st14Btn.className = `px-2.5 py-1 text-xs font-bold rounded-lg transition flex items-center gap-1.5 shadow border border-emerald-400/40 bg-emerald-600 text-white hover:bg-emerald-500 animate-pulse-subtle active:scale-95 cursor-pointer ${!isSt14EngineActive ? 'opacity-40 cursor-not-allowed' : ''}`;
          st14Label.textContent = 'LIVE';
          st14Indicator.className = 'w-2 h-2 rounded-full bg-white animate-pulse';
          if (st14ModeBadge) {
            st14ModeBadge.textContent = 'LIVE';
            st14ModeBadge.className = 'px-1.5 py-0.2 rounded text-[10px] font-bold bg-emerald-950 text-emerald-300 border border-emerald-800 animate-pulse';
          }
        }
      }
    }

    async function toggleExecutionMode(strategyId = null) {
      const stratId = strategyId || activeStrategyId || 'st_news';
      const currentActive = (stratId === 'st14_bullish_ce') ? isSt14EngineActive : isNewsEngineActive;
      if (!currentActive) {
        showToast('⚠️ Strategy Engine is PAUSED. Start strategy engine first.', '⚠️');
        return;
      }

      if (stratId === 'st14_bullish_ce') {
        const targetMode = isSt14DryRun ? 'LIVE' : 'VIRTUAL';
        if (targetMode === 'LIVE') {
          try {
            const res = await fetch('/api/settings/token');
            if (res.ok) {
              const data = await res.json();
              if (!data.is_configured || data.is_expired) {
                showToast('⚠️ Cannot enable Live Trading: Dhan token is missing or expired!', '⚠️');
                openTokenModal();
                return;
              }
            }
          } catch (e) {}
        }
        try {
          const res = await fetch(`/api/strategies/${stratId}/toggle-mode`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ mode: targetMode })
          });
          if (res.ok) {
            const data = await res.json();
            isSt14DryRun = (data.mode === 'VIRTUAL');
            syncActiveStrategyState();
            loadSt14Data();
            loadStrategies();
            if (!isSt14DryRun) {
              showToast('🚨 ST-14 LIVE TRADING ENABLED! Real Dhan Super Orders will be placed.', '⚡');
            } else {
              showToast('🛡️ ST-14 switched to VIRTUAL mode (Paper Trading).', 'ℹ️');
            }
          }
        } catch (err) {
          showToast('Failed to toggle Execution Mode', '❌');
        }
        return;
      }

      // ST-NEWS Mode toggle
      const targetDryRun = !isNewsDryRun;
      if (!targetDryRun) {
        try {
          const res = await fetch('/api/settings/token');
          if (res.ok) {
            const data = await res.json();
            if (!data.is_configured || data.is_expired) {
              showToast('⚠️ Cannot enable Live Trading: Dhan token is missing or expired!', '⚠️');
              openTokenModal();
              return;
            }
          }
        } catch (e) {}
      }

      try {
        const res = await fetch('/api/toggle-dry-run', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ dry_run: targetDryRun })
        });
        if (res.ok) {
          const data = await res.json();
          isNewsDryRun = data.dry_run;
          syncActiveStrategyState();
          loadStrategies();
          if (!isNewsDryRun) {
            showToast('🚨 LIVE TRADING ENABLED! Real Dhan market orders will be placed.', '⚡');
          } else {
            showToast('🛡️ Switched to VIRTUAL mode (Simulated execution).', 'ℹ️');
          }
        } else {
          showToast('Failed to toggle Execution Mode', '❌');
        }
      } catch (err) {
        showToast('Failed to toggle Execution Mode', '❌');
      }
    }


    let lastPolledTimestamp = Date.now();
    let lastKnownMarketOpen = false;
    let lastKnownMarketHoursOnly = true;
    let configuredMarketOpenTime = '09:15';
    let configuredMarketCloseTime = '15:30';

    function updatePollerTimer() {
      const elapsedSec = Math.max(0, Math.floor((Date.now() - lastPolledTimestamp) / 1000));
      const tag = document.getElementById('poller-elapsed-tag');
      const emptyTag = document.getElementById('empty-last-check');
      const elapsedStr = elapsedSec <= 1 ? 'Just now' : `${elapsedSec}s ago`;
      if (tag) {
        tag.textContent = elapsedStr;
        if (elapsedSec > 120) {
          tag.className = 'text-[10px] text-amber-300 bg-amber-950/60 border border-amber-500/30 px-2 py-0.5 rounded font-mono font-semibold';
        } else {
          tag.className = 'text-[10px] text-emerald-300 bg-emerald-950/60 border border-emerald-500/30 px-2 py-0.5 rounded font-mono font-semibold';
        }
      }
      if (emptyTag) emptyTag.textContent = elapsedStr;
    }

    function computeMarketStatusClient() {
      try {
        const now = new Date();
        const istOffset = 5.5 * 60 * 60 * 1000;
        const utc = now.getTime() + (now.getTimezoneOffset() * 60000);
        const istDate = new Date(utc + istOffset);
        
        const day = istDate.getDay();
        if (day === 0 || day === 6) {
          return false;
        }
        const hour = istDate.getHours();
        const min = istDate.getMinutes();
        const totalMinutes = hour * 60 + min;

        const openParts = (configuredMarketOpenTime || '09:15').split(':').map(Number);
        const closeParts = (configuredMarketCloseTime || '15:30').split(':').map(Number);
        const marketOpenMinutes = (openParts[0] || 9) * 60 + (openParts[1] || 15);
        const marketCloseMinutes = (closeParts[0] || 15) * 60 + (closeParts[1] || 30);
        return totalMinutes >= marketOpenMinutes && totalMinutes <= marketCloseMinutes;
      } catch (e) {
        return false;
      }
    }

    function updateRadarStatusUI(isOpen, isMarketHoursOnly) {
      const badge = document.getElementById('radar-badge-container');
      const text = document.getElementById('poller-status-badge');
      const pingDot = document.getElementById('radar-ping-dot');
      const solidDot = document.getElementById('radar-solid-dot');
      if (!badge || !text) return;

      if (!isStrategyEngineActive) {
        badge.className = 'inline-flex items-center gap-2 bg-amber-500/10 border border-amber-500/30 text-amber-300 px-3 py-1 rounded-full font-bold shadow-sm';
        text.textContent = 'NSE RADAR PAUSED (Engine Stopped)';
        if (pingDot) pingDot.className = 'hidden';
        if (solidDot) solidDot.className = 'relative inline-flex rounded-full h-2.5 w-2.5 bg-amber-400';
        return;
      }

      const isStandby = !isOpen && isMarketHoursOnly !== false;
      if (isStandby) {
        badge.className = 'inline-flex items-center gap-2 bg-amber-500/10 border border-amber-500/30 text-amber-300 px-3 py-1 rounded-full font-bold shadow-sm';
        text.textContent = 'NSE RADAR STANDBY (Off-Market)';
        if (pingDot) pingDot.className = 'hidden';
        if (solidDot) solidDot.className = 'relative inline-flex rounded-full h-2.5 w-2.5 bg-amber-400';
      } else {
        badge.className = 'inline-flex items-center gap-2 bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 px-3 py-1 rounded-full font-bold shadow-sm';
        text.textContent = 'NSE RADAR ACTIVE';
        if (pingDot) pingDot.className = 'animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75';
        if (solidDot) solidDot.className = 'relative inline-flex rounded-full h-2.5 w-2.5 bg-emerald-500';
      }
    }

    function updateEmptyStateUI(isOpen, isMarketHoursOnly) {
      const ping = document.getElementById('empty-radar-ping');
      const pulse = document.getElementById('empty-radar-pulse');
      const box = document.getElementById('empty-radar-box');
      const icon = document.getElementById('empty-radar-icon');
      const heading = document.getElementById('empty-state-heading');
      const desc = document.getElementById('empty-state-desc');
      const dot = document.getElementById('empty-state-dot');
      const statusText = document.getElementById('empty-state-status-text');

      if (!isStrategyEngineActive) {
        if (ping) ping.className = 'hidden';
        if (pulse) pulse.className = 'hidden';
        if (box) box.className = 'w-10 h-10 rounded-full bg-[#162032] border border-amber-500/40 flex items-center justify-center text-xl shadow-lg';
        if (icon) icon.textContent = '⏸️';
        if (heading) heading.innerHTML = '<span class="text-amber-300 flex items-center justify-center gap-2"><span>⏸️</span> <span>Strategy Engine Paused — Radar Standby</span></span>';
        if (desc) desc.innerHTML = 'Background NSE announcement polling and Gemini AI grading are completely stopped. Click <button onclick="toggleStrategyEngine()" class="underline font-bold text-amber-400 hover:text-amber-300 cursor-pointer">Start Engine</button> above to resume active scanning.';
        if (dot) dot.className = 'w-2 h-2 rounded-full bg-amber-400';
        if (statusText) {
          statusText.className = 'text-amber-300 font-semibold';
          statusText.textContent = 'Engine Paused (No API calls)';
        }
        return;
      }

      const isStandby = !isOpen && isMarketHoursOnly !== false;
      if (isStandby) {
        if (ping) ping.className = 'absolute w-16 h-16 rounded-full bg-amber-500/10 animate-pulse';
        if (pulse) pulse.className = 'absolute w-12 h-12 rounded-full bg-amber-500/20';
        if (box) box.className = 'w-10 h-10 rounded-full bg-[#162032] border border-amber-500/40 flex items-center justify-center text-xl shadow-lg';
        if (icon) icon.textContent = '🌙';
        if (heading) heading.innerHTML = '<span>Radar Standby — Market Closed (Off-Hours)</span>';
        if (desc) desc.textContent = `NSE equity market is currently closed (${configuredMarketOpenTime} – ${configuredMarketCloseTime} IST). News polling is in standby mode and will automatically resume scanning when market opens.`;
        if (dot) dot.className = 'w-2 h-2 rounded-full bg-amber-400';
        if (statusText) {
          statusText.className = 'text-amber-300 font-semibold';
          statusText.textContent = `Standby (Awaiting ${configuredMarketOpenTime} Open)`;
        }
      } else {
        if (ping) ping.className = 'absolute w-16 h-16 rounded-full bg-emerald-500/10 animate-ping';
        if (pulse) pulse.className = 'absolute w-12 h-12 rounded-full bg-emerald-500/20 animate-pulse';
        if (box) box.className = 'w-10 h-10 rounded-full bg-[#162032] border border-emerald-500/40 flex items-center justify-center text-xl shadow-lg';
        if (icon) icon.textContent = '📡';
        if (heading) heading.innerHTML = '<span>Live Radar Active — Scanning NSE Corporate Feed</span>';
        if (desc) desc.textContent = 'Actively monitoring 228 F&O tickers on NSE. The AI filter automatically discards routine compliance noise and will alert here the moment an actionable market catalyst breaks.';
        if (dot) dot.className = 'w-2 h-2 rounded-full bg-emerald-400 animate-pulse';
        if (statusText) {
          statusText.className = 'text-indigo-300 font-semibold';
          statusText.textContent = 'Listening for catalysts...';
        }
      }
    }

    function renderMarketStatusUI(isOpen, isMarketHoursOnly) {
      lastKnownMarketOpen = isOpen;
      if (isMarketHoursOnly !== undefined) {
        lastKnownMarketHoursOnly = isMarketHoursOnly;
      }
      const badge = document.getElementById('market-status-badge');
      const dot = document.getElementById('market-status-dot');
      const text = document.getElementById('market-status-text');

      if (badge && dot && text) {
        if (isOpen) {
          badge.className = 'px-2.5 py-0.5 text-[10px] font-bold rounded-full flex items-center gap-1.5 shadow-sm border bg-emerald-500/20 text-emerald-300 border-emerald-500/40';
          badge.title = `NSE Equity Market is OPEN (${configuredMarketOpenTime} to ${configuredMarketCloseTime} IST)`;
          dot.className = 'w-2 h-2 rounded-full bg-emerald-400 animate-pulse';
          text.textContent = 'MARKET OPEN';
        } else {
          badge.className = 'px-2.5 py-0.5 text-[10px] font-bold rounded-full flex items-center gap-1.5 shadow-sm border bg-rose-500/20 text-rose-300 border-rose-500/40';
          badge.title = `NSE Equity Market is CLOSED (Regular hours: Mon-Fri ${configuredMarketOpenTime} to ${configuredMarketCloseTime} IST)`;
          dot.className = 'w-2 h-2 rounded-full bg-rose-400';
          text.textContent = 'MARKET CLOSED';
        }
      }

      updateRadarStatusUI(isOpen, lastKnownMarketHoursOnly);
      updateEmptyStateUI(isOpen, lastKnownMarketHoursOnly);
    }

    function renderCutoffUI(isAllowed, cutoffTime, reason) {
      const badge = document.getElementById('cutoff-status-badge');
      const dot = document.getElementById('cutoff-status-dot');
      const text = document.getElementById('cutoff-status-text');
      if (!badge || !dot || !text) return;

      if (isAllowed) {
        badge.className = 'px-2.5 py-0.5 text-[10px] font-bold bg-emerald-500/10 text-emerald-300 border border-emerald-500/30 rounded-full flex items-center gap-1.5 shadow-sm';
        dot.className = 'w-1.5 h-1.5 rounded-full bg-emerald-400';
        text.textContent = `CUTOFF ${cutoffTime || '14:45'}`;
        badge.title = `Trades allowed until ${cutoffTime || '14:45'} IST. Auto Square-off at 15:00 IST.`;
      } else {
        badge.className = 'px-2.5 py-0.5 text-[10px] font-bold bg-amber-500/20 text-amber-300 border border-amber-500/40 rounded-full flex items-center gap-1.5 shadow-sm';
        dot.className = 'w-1.5 h-1.5 rounded-full bg-amber-400';
        text.textContent = 'TRADES CUTOFF (14:45)';
        badge.title = reason || `Trades blocked past ${cutoffTime || '14:45'} IST cutoff.`;
      }
    }

    async function fetchStatus() {
      try {
        const res = await fetch('/api/status');
        if (res.ok) {
          const data = await res.json();
          if (data.strategy_status !== undefined) {
            isNewsEngineActive = (data.strategy_status !== 'PAUSED');
          }
          if (data.auto_order !== undefined) {
            isNewsAutoOrder = data.auto_order;
          }
          if (data.dry_run !== undefined) {
            isNewsDryRun = data.dry_run;
          }
          syncActiveStrategyState();
          if (data.market_open_time) configuredMarketOpenTime = data.market_open_time;
          if (data.market_close_time) configuredMarketCloseTime = data.market_close_time;
          const isOpen = (typeof data.is_market_open === 'boolean') ? data.is_market_open : computeMarketStatusClient();
          renderMarketStatusUI(isOpen, data.poll_market_hours_only);
          if (data.is_trade_allowed !== undefined) {
            renderCutoffUI(data.is_trade_allowed, data.trade_cutoff_time, data.trade_allowed_reason);
          }
          const dbStatus = document.getElementById('db-status');
          if (dbStatus && data.db_description) {
            dbStatus.textContent = data.db_description;
          }
          if (data.last_polled_ts) {
            lastPolledTimestamp = data.last_polled_ts * 1000;
          }
          if (document.getElementById('poller-last-time') && data.last_polled_time) {
            document.getElementById('poller-last-time').textContent = data.last_polled_time;
          }
          if (document.getElementById('poller-noise-count')) {
            document.getElementById('poller-noise-count').textContent = data.suppressed_noise_count || '0';
          }
          if (document.getElementById('poller-fno-count') && data.fno_universe_size) {
            document.getElementById('poller-fno-count').textContent = data.fno_universe_size;
          }
          if (document.getElementById('poller-interval-val') && data.poll_interval_seconds) {
            document.getElementById('poller-interval-val').textContent = `${data.poll_interval_seconds}s`;
          }
          if (data.view_mode) {
            updateScopeUI(data.view_mode === 'TODAY');
          }
          updatePollerTimer();
        }
      } catch (err) {
        console.error('Failed fetching status:', err);
      }
    }

    function updateAutoOrderUI() {
      // 1. ST-NEWS Elements
      const btn = document.getElementById('toggle-auto-btn');
      const label = document.getElementById('auto-status-label');
      const indicator = document.getElementById('auto-status-indicator');
      
      if (btn && label && indicator) {
        if (isNewsAutoOrder) {
          btn.className = `px-2.5 py-1 text-xs font-bold rounded-lg transition bg-emerald-600 text-white hover:bg-emerald-500 border border-emerald-400/40 shadow flex items-center gap-1.5 ${!isNewsEngineActive ? 'opacity-40 cursor-not-allowed' : ''}`;
          label.textContent = 'ENABLED (Auto-Place)';
          indicator.className = 'w-2 h-2 rounded-full bg-white animate-pulse';
        } else {
          btn.className = `px-2.5 py-1 text-xs font-bold rounded-lg transition bg-amber-600 text-white hover:bg-amber-500 border border-amber-400/40 shadow flex items-center gap-1.5 ${!isNewsEngineActive ? 'opacity-40 cursor-not-allowed' : ''}`;
          label.textContent = 'MANUAL (Prompt Approval)';
          indicator.className = 'w-2 h-2 rounded-full bg-amber-200';
        }
      }

      // 2. ST-14 Elements
      const st14Btn = document.getElementById('st14-toggle-auto-btn');
      const st14Label = document.getElementById('st14-auto-status-label');
      const st14Indicator = document.getElementById('st14-auto-status-indicator');
      const st14AutoEl = document.getElementById('st14-auto-order-text');

      if (st14Btn && st14Label && st14Indicator) {
        if (isSt14AutoOrder) {
          st14Btn.className = `px-2.5 py-1 text-xs font-bold rounded-lg transition border border-emerald-400/40 bg-emerald-600 text-white hover:bg-emerald-500 shadow flex items-center gap-1.5 active:scale-95 cursor-pointer ${!isSt14EngineActive ? 'opacity-40 cursor-not-allowed' : ''}`;
          st14Label.textContent = 'ENABLED (Auto-Place)';
          st14Indicator.className = 'w-2 h-2 rounded-full bg-white animate-pulse';
          if (st14AutoEl) {
            st14AutoEl.textContent = 'ON';
            st14AutoEl.className = 'text-emerald-400 font-bold';
          }
        } else {
          st14Btn.className = `px-2.5 py-1 text-xs font-bold rounded-lg transition border border-amber-400/40 bg-amber-600 text-white hover:bg-amber-500 shadow flex items-center gap-1.5 active:scale-95 cursor-pointer ${!isSt14EngineActive ? 'opacity-40 cursor-not-allowed' : ''}`;
          st14Label.textContent = 'MANUAL (Prompt Approval)';
          st14Indicator.className = 'w-2 h-2 rounded-full bg-amber-200';
          if (st14AutoEl) {
            st14AutoEl.textContent = 'OFF';
            st14AutoEl.className = 'text-amber-400 font-bold';
          }
        }
      }
    }

    async function toggleAutoOrder(strategyId = null) {
      const stratId = strategyId || activeStrategyId || 'st_news';
      const currentActive = (stratId === 'st14_bullish_ce') ? isSt14EngineActive : isNewsEngineActive;
      if (!currentActive) {
        showToast('⚠️ Strategy Engine is PAUSED. Start strategy engine first.', '⚠️');
        return;
      }

      if (stratId === 'st14_bullish_ce') {
        const newStatus = !isSt14AutoOrder;
        try {
          const res = await fetch(`/api/strategies/${stratId}/toggle-auto-order`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ auto_order: newStatus })
          });
          if (res.ok) {
            const data = await res.json();
            isSt14AutoOrder = data.auto_order;
            syncActiveStrategyState();
            loadSt14Data();
            loadStrategies();
            showToast(`ST-14 Auto-Order set to: ${isSt14AutoOrder ? 'ENABLED (Auto Super Orders)' : 'MANUAL APPROVAL'}`, '⚙️');
          }
        } catch (err) {
          showToast('Failed to toggle Auto-Order', '❌');
        }
        return;
      }

      // ST-NEWS Auto-Order toggle
      try {
        const newStatus = !isNewsAutoOrder;
        const res = await fetch('/api/toggle-auto-order', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ auto_order: newStatus })
        });
        if (res.ok) {
          const data = await res.json();
          isNewsAutoOrder = data.auto_order;
          syncActiveStrategyState();
          loadStrategies();
          showToast(`Auto-Order set to: ${isNewsAutoOrder ? 'ENABLED (Auto-Place)' : 'MANUAL APPROVAL'}`, '⚙️');
          fetchFeed();
        }
      } catch (err) {
        showToast('Failed to toggle Auto-Order', '❌');
      }
    }


    function setFilter(filter) {
      currentFilter = filter || 'ALL';
      const select = document.getElementById('feed-filter-select');
      if (select && select.value !== currentFilter) {
        select.value = currentFilter;
      }
      selectedRowIndex = -1;
      renderFeed();
    }

    function toggleRowDetails(seqId) {
      openDrawer(seqId);
    }

    let currentScope = 'TODAY';

    function updateScopeUI(isTodayOnly) {
      currentScope = isTodayOnly ? 'TODAY' : 'ALL_HISTORY';
      const badge = document.getElementById('session-scope-badge');
      const text = document.getElementById('session-scope-text');
      const btnToday = document.getElementById('btn-today-signals');
      const btnHist = document.getElementById('btn-load-history');

      if (badge && text) {
        if (isTodayOnly) {
          badge.className = 'px-2 py-0.5 text-[11px] font-mono font-bold bg-emerald-950/80 text-emerald-300 border border-emerald-800/80 rounded flex items-center gap-1';
          text.textContent = 'Today Only';
        } else {
          badge.className = 'px-2 py-0.5 text-[11px] font-mono font-bold bg-indigo-950/80 text-indigo-300 border border-indigo-800/80 rounded flex items-center gap-1';
          text.textContent = 'Full History';
        }
      }

      if (btnToday && btnHist) {
        if (isTodayOnly) {
          btnToday.className = 'px-2.5 py-1.5 text-xs font-semibold rounded-lg bg-emerald-950/80 text-emerald-300 border border-emerald-600 transition flex items-center gap-1.5 shadow-sm';
          btnHist.className = 'px-2.5 py-1.5 text-xs font-semibold rounded-lg bg-[#162032] hover:bg-[#1f293d] text-gray-300 hover:text-white border border-gray-700/80 hover:border-gray-600 transition flex items-center gap-1.5 shadow-sm active:scale-95';
        } else {
          btnToday.className = 'px-2.5 py-1.5 text-xs font-semibold rounded-lg bg-[#162032] hover:bg-[#1f293d] text-gray-300 hover:text-white border border-gray-700/80 hover:border-gray-600 transition flex items-center gap-1.5 shadow-sm active:scale-95';
          btnHist.className = 'px-2.5 py-1.5 text-xs font-semibold rounded-lg bg-indigo-950/80 text-indigo-300 border border-indigo-600 transition flex items-center gap-1.5 shadow-sm';
        }
      }
    }

    async function clearFeedList() {
      if (!feedItems || feedItems.length === 0) {
        showToast('Table display is already empty.', 'ℹ️');
        return;
      }
      try {
        const res = await fetch('/api/feed/clear', { method: 'POST' });
        if (res.ok) {
          feedItems = [];
          expandedRows.clear();
          selectedRowIndex = -1;
          renderFeed();
          showToast('🧹 Display cleared! All signals & orders remain safely stored in DB for audit.', '✅');
        } else {
          showToast('Failed to clear feed list', '❌');
        }
      } catch (err) {
        showToast('Failed to clear feed list', '❌');
      }
    }

    async function loadTodaySignals() {
      showToast("Loading today's trading signals...", "📅");
      try {
        const res = await fetch('/api/feed/load-history', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ today_only: true })
        });
        if (res.ok) {
          const data = await res.json();
          await fetchFeed();
          updateScopeUI(true);
          showToast(`Loaded ${data.count} signals for today's session.`, '✅');
        } else {
          showToast("Failed to load today's signals", '❌');
        }
      } catch (err) {
        showToast("Error connecting to server", '❌');
      }
    }

    async function loadFeedHistory() {
      showToast('Loading all evaluated historical signals from database...', '📜');
      try {
        const res = await fetch('/api/feed/load-history', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ today_only: false })
        });
        if (res.ok) {
          const data = await res.json();
          await fetchFeed();
          updateScopeUI(false);
          showToast(`Loaded ${data.count} total historical signals from database.`, '✅');
        } else {
          showToast('Failed to load past signals', '❌');
        }
      } catch (err) {
        showToast('Error loading signals from database', '❌');
      }
    }

    async function toggleScopeMode() {
      if (currentScope === 'TODAY') {
        await loadFeedHistory();
      } else {
        await loadTodaySignals();
      }
    }

    async function fetchFeed() {
      try {
        const res = await fetch('/api/feed');
        if (res.ok) {
          feedItems = await res.json();
          renderFeed();
        }
      } catch (err) {
        console.error('Failed fetching feed:', err);
      }
    }

    function renderFeed() {
      const tbody = document.getElementById('table-body');
      const emptyState = document.getElementById('empty-state');
      const searchVal = (document.getElementById('search-input').value || '').toLowerCase().trim();

      // Counts
      let totalBullish = 0, totalBearish = 0, totalPlaced = 0, totalPending = 0, totalNoise = 0, totalPassed = 0;
      feedItems.forEach(item => {
        if (item.is_noise) {
          totalNoise++;
        } else {
          totalPassed++;
          if (item.sentiment === 'BULLISH') totalBullish++;
          if (item.sentiment === 'BEARISH') totalBearish++;
          if (item.order && item.order.placed) totalPlaced++;
          if (item.order && item.order.status === 'PENDING_APPROVAL') totalPending++;
        }
      });

      document.getElementById('stat-total').textContent = totalPassed;
      document.getElementById('stat-bullish').textContent = totalBullish;
      document.getElementById('stat-bearish').textContent = totalBearish;
      document.getElementById('stat-placed').textContent = totalPlaced;
      document.getElementById('stat-pending').textContent = totalPending;

      // Update Pill Count Badges
      if (document.getElementById('badge-count-all')) document.getElementById('badge-count-all').textContent = totalPassed;
      if (document.getElementById('badge-count-bullish')) document.getElementById('badge-count-bullish').textContent = totalBullish;
      if (document.getElementById('badge-count-bearish')) document.getElementById('badge-count-bearish').textContent = totalBearish;
      if (document.getElementById('badge-count-pending')) document.getElementById('badge-count-pending').textContent = totalPending;
      if (document.getElementById('badge-count-noise')) document.getElementById('badge-count-noise').textContent = totalNoise;

      // Update Risk Budget Gauge
      updateRiskBudgetGauge(totalPlaced);

      // Keep hidden select options matching tests
      if (document.getElementById('opt-filter-all')) {
        document.getElementById('opt-filter-all').textContent = `⚡ All Passed (${totalPassed})`;
      }
      if (document.getElementById('opt-filter-bullish')) {
        document.getElementById('opt-filter-bullish').textContent = `🟢 Bullish Only (${totalBullish})`;
      }
      if (document.getElementById('opt-filter-bearish')) {
        document.getElementById('opt-filter-bearish').textContent = `🔴 Bearish Only (${totalBearish})`;
      }
      if (document.getElementById('opt-filter-pending')) {
        document.getElementById('opt-filter-pending').textContent = `⏳ Pending Approval (${totalPending})`;
      }
      if (document.getElementById('opt-filter-noise')) {
        document.getElementById('opt-filter-noise').textContent = `🔇 Noise Suppressed (${totalNoise})`;
      }

      // Filter logic
      const filtered = feedItems.filter(item => {
        if (currentFilter === 'NOISE') {
          if (!item.is_noise) return false;
        } else {
          if (item.is_noise) return false;
          if (currentFilter === 'BULLISH' && item.sentiment !== 'BULLISH') return false;
          if (currentFilter === 'BEARISH' && item.sentiment !== 'BEARISH') return false;
          if (currentFilter === 'PENDING' && (!item.order || item.order.status !== 'PENDING_APPROVAL')) return false;
        }

        if (searchVal) {
          const matchSym = (item.symbol || '').toLowerCase().includes(searchVal);
          const matchDesc = (item.desc || '').toLowerCase().includes(searchVal);
          const matchCat = (item.catalyst_type || '').toLowerCase().includes(searchVal);
          const matchReason = (item.filter_reason || '').toLowerCase().includes(searchVal);
          if (!matchSym && !matchDesc && !matchCat && !matchReason) return false;
        }
        return true;
      });

      if (filtered.length === 0) {
        tbody.innerHTML = '';
        emptyState.style.display = 'block';
        updateEmptyStateUI(lastKnownMarketOpen, lastKnownMarketHoursOnly);
        return;
      }
      emptyState.style.display = 'none';

      tbody.innerHTML = filtered.map((item, idx) => createTableRowHTML(item, idx)).join('');
      updateRowSelection();
      updateCountdowns();
    }

    function createTableRowHTML(item, idx) {
      const isBullish = item.sentiment === 'BULLISH';
      const isNoise = !!item.is_noise;
      const isMarketClosed = item.sentiment === 'MARKET_CLOSED' || (item.filter_reason && (item.filter_reason.toLowerCase().includes('market closed') || item.filter_reason.toLowerCase().includes('trade cutoff') || item.filter_reason.toLowerCase().includes('market is not open')));
      const order = item.order || {};

      // Directional Border Accent Class
      let borderAccentClass = 'border-l-4 border-l-emerald-500';
      if (isMarketClosed) borderAccentClass = 'border-l-4 border-l-amber-500';
      else if (isNoise) borderAccentClass = 'border-l-4 border-l-gray-600';
      else if (!isBullish) borderAccentClass = 'border-l-4 border-l-rose-500';

      // Freshness state calculation
      const fresh = getFreshnessState(item.an_dt);

      // LLM Verdict Badge
      let verdictHTML = '';
      if (isMarketClosed) {
        verdictHTML = `
          <div class="inline-flex flex-col items-center">
            <span class="px-2.5 py-1 text-xs font-bold rounded-md bg-amber-950/70 text-amber-300 border border-amber-800/60 flex items-center gap-1.5 shadow-sm">
              <span>🌙</span>
              <span>MARKET CLOSED</span>
            </span>
            <span class="text-[10px] text-amber-400/80 font-mono mt-1">${item.filter_reason || 'Outside 09:15-14:45 IST'}</span>
          </div>
        `;
      } else if (isNoise) {
        verdictHTML = `
          <div class="inline-flex flex-col items-center">
            <span class="px-2.5 py-1 text-xs font-bold rounded-md bg-gray-800 text-gray-400 border border-gray-700 flex items-center gap-1.5 shadow-sm">
              <span>🔇</span>
              <span>SUPPRESSED</span>
            </span>
            <span class="text-[10px] text-gray-500 font-mono mt-1">${item.filter_reason || 'Noise / Routine'}</span>
          </div>
        `;
      } else if (isBullish) {
        const isHighConviction = item.material_impact && (item.confidence >= 70);
        verdictHTML = `
          <div class="inline-flex flex-col items-center">
            <span class="px-2.5 py-1 text-xs font-bold rounded-md bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 flex items-center gap-1.5 shadow-sm">
              <span class="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
              BULLISH 🟢 ${item.confidence}%
            </span>
            <span class="text-[10px] ${isHighConviction ? 'text-emerald-400 font-semibold' : 'text-amber-400/90'} font-mono mt-1">${isHighConviction ? 'High Conviction (≥1.5%)' : 'Non-Material (<1.5% Move)'}</span>
          </div>
        `;
      } else {
        const isHighConviction = item.material_impact && (item.confidence >= 70);
        verdictHTML = `
          <div class="inline-flex flex-col items-center">
            <span class="px-2.5 py-1 text-xs font-bold rounded-md bg-rose-500/20 text-rose-300 border border-rose-500/40 flex items-center gap-1.5 shadow-sm">
              <span class="w-2 h-2 rounded-full bg-rose-400"></span>
              BEARISH 🔴 ${item.confidence}%
            </span>
            <span class="text-[10px] ${isHighConviction ? 'text-rose-400 font-semibold' : 'text-amber-400/90'} font-mono mt-1">${isHighConviction ? 'Negative Catalyst (≥1.5%)' : 'Non-Material (<1.5% Move)'}</span>
          </div>
        `;
      }

      // Bracket Pricing Column (Clean Target / Stop Loss / Limit / Position)
      let pricingHTML = '';
      if (isMarketClosed) {
        pricingHTML = `
          <div class="text-right text-gray-500 font-mono text-xs">
            <div>Ref LTP: ₹${order.ltp ? order.ltp.toFixed(2) : '0.00'}</div>
            <div class="text-[10px] text-amber-500/80 font-mono">LLM Skipped (Market Closed)</div>
          </div>
        `;
      } else if (isNoise) {
        pricingHTML = `
          <div class="text-right text-gray-600 font-mono text-xs">
            <div>Excluded from Orders</div>
            <div class="text-[10px] text-gray-600">${item.filter_reason || 'Filtered Out'}</div>
          </div>
        `;
      } else if (isBullish) {
        pricingHTML = `
          <div class="text-right font-mono space-y-0.5">
            <div class="text-white font-bold">Limit: <span class="text-emerald-400 font-semibold">₹${order.entry_price ? order.entry_price.toFixed(2) : '0.00'}</span></div>
            <div class="text-[11px] text-gray-400">
              TP: <span class="text-emerald-300 font-semibold">₹${order.target_price ? order.target_price.toFixed(2) : '0.00'} (+3%)</span>
            </div>
            <div class="text-[11px] text-gray-400">
              SL: <span class="text-rose-400 font-semibold">₹${order.stop_loss_price ? order.stop_loss_price.toFixed(2) : '0.00'} (-1%)</span>
            </div>
            <div class="text-[10px] text-gray-500">Qty: ${order.quantity} sh • Trail: 5.0 pts</div>
          </div>
        `;
      } else {
        pricingHTML = `
          <div class="text-right font-mono space-y-0.5">
            <div class="text-white font-bold">Limit: <span class="text-rose-400 font-semibold">₹${order.entry_price ? order.entry_price.toFixed(2) : '0.00'}</span></div>
            <div class="text-[11px] text-gray-400">
              TP: <span class="text-emerald-300 font-semibold">₹${order.target_price ? order.target_price.toFixed(2) : '0.00'} (-3%)</span>
            </div>
            <div class="text-[11px] text-gray-400">
              SL: <span class="text-rose-400 font-semibold">₹${order.stop_loss_price ? order.stop_loss_price.toFixed(2) : '0.00'} (+1%)</span>
            </div>
            <div class="text-[10px] text-gray-500">Qty: ${order.quantity} sh • Trail: 5.0 pts</div>
          </div>
        `;
      }

      // Dedicated Live Market Price & P&L Column
      let livePnlHTML = '';
      if (isMarketClosed || isNoise) {
        livePnlHTML = `
          <div class="text-center font-mono text-gray-600 text-xs">
            <span>--</span>
          </div>
        `;
      } else {
        const isTraded = !!(order.placed && (order.traded_price || order.fill_price));
        const basePrice = isTraded ? (order.traded_price || order.fill_price) : (order.entry_price || order.ltp || 0);
        const baseTag = isTraded ? 'vs Traded' : 'vs Limit';
        const baseTitle = isTraded ? `P&L calculated against executed fill price (₹${basePrice.toFixed(2)})` : `P&L calculated against Limit Entry price (₹${basePrice.toFixed(2)}) as no traded fill exists`;
        const currentPrice = order.current_ltp || order.ltp || basePrice;

        if (basePrice > 0 && currentPrice > 0) {
          let pnlDiff = 0;
          let pnlPct = 0;
          if (isBullish) {
            pnlDiff = currentPrice - basePrice;
            pnlPct = (pnlDiff / basePrice) * 100;
          } else {
            pnlDiff = basePrice - currentPrice;
            pnlPct = (pnlDiff / basePrice) * 100;
          }
          const isProfit = pnlDiff >= 0;
          const arrow = isProfit ? '▲' : '▼';
          const sign = pnlDiff >= 0 ? '+' : '';
          const pnlBadgeClass = isProfit
            ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40'
            : 'bg-rose-500/20 text-rose-300 border border-rose-500/40';

          livePnlHTML = `
            <div class="flex flex-col items-center text-center font-mono space-y-1">
              <div class="text-xs font-bold text-white flex items-center gap-1.5">
                <span class="w-1.5 h-1.5 rounded-full ${isProfit ? 'bg-emerald-400 animate-pulse' : 'bg-rose-400'}"></span>
                <span>₹${currentPrice.toFixed(2)}</span>
              </div>
              <span class="px-2 py-0.5 rounded text-[11px] font-bold ${pnlBadgeClass} flex items-center gap-0.5 shadow-sm" title="${baseTitle}">
                <span>${arrow}</span>
                <span>${sign}₹${Math.abs(pnlDiff).toFixed(2)} (${sign}${pnlPct.toFixed(2)}%)</span>
              </span>
              <span class="text-[9px] text-gray-400 font-mono" title="${baseTitle}">
                ${baseTag}: <span class="text-gray-300 font-semibold">₹${basePrice.toFixed(2)}</span>
              </span>
            </div>
          `;
        } else {
          livePnlHTML = `
            <div class="text-center font-mono text-gray-500 text-xs">
              <span>--</span>
            </div>
          `;
        }
      }

      // Order Action Column
      let actionHTML = '';
      if (isMarketClosed) {
        actionHTML = `
          <div class="flex flex-col items-center text-center font-mono">
            <span class="px-2.5 py-1 text-[11px] font-bold bg-amber-950/60 text-amber-300 border border-amber-900/60 rounded flex items-center gap-1 shadow-sm">
              <span>🌙</span> CLOSED
            </span>
            <span class="text-[10px] text-gray-500 mt-1 truncate max-w-[150px]" title="${item.filter_reason || 'Market Closed'}">
              ${item.filter_reason || 'Market Closed'}
            </span>
          </div>
        `;
      } else if (isNoise) {
        actionHTML = `
          <div class="flex flex-col items-center text-center font-mono">
            <span class="px-2.5 py-1 text-[11px] font-bold bg-gray-900/90 text-gray-500 border border-gray-800 rounded flex items-center gap-1 shadow-sm">
              <span>🔇</span> NOISE
            </span>
            <span class="text-[10px] text-gray-600 mt-1 truncate max-w-[150px]" title="${item.filter_reason || 'Filtered'}">
              ${item.filter_reason || 'Filtered'}
            </span>
          </div>
        `;
      } else if (isBullish) {
        if (order.placed) {
          actionHTML = `
            <div class="flex flex-col items-center text-center font-mono">
              <span class="px-2.5 py-1 text-[11px] font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 rounded-md flex items-center gap-1 shadow-sm">
                <span>✅</span> PLACED (Auto)
              </span>
              <span class="text-[10px] text-gray-400 mt-1 truncate max-w-[170px]" title="${order.order_id}">
                ID: <span class="text-gray-200 font-semibold">${order.order_id || 'VIRTUAL_SIMULATED'}</span>
              </span>
              <span class="text-[10px] text-emerald-400 mt-0.5">@ ₹${order.entry_price ? order.entry_price.toFixed(2) : '0.00'} (${order.quantity} sh)</span>
            </div>
          `;
        } else if (order.status === 'PENDING_APPROVAL') {
          if (item.is_stale) {
            actionHTML = `
              <div class="flex flex-col items-center gap-1 font-mono">
                <button disabled class="bg-gray-800/80 text-gray-500 font-bold text-xs px-3 py-1.5 rounded-lg border border-gray-700/60 cursor-not-allowed flex items-center gap-1.5 opacity-60" title="News catalyst is older than 180 seconds. Order blocked to prevent stale trade execution.">
                  <span>⏱️</span>
                  <span>Stale (>180s)</span>
                </button>
                <span class="text-[10px] text-amber-500/80 font-mono">⚠️ Window Expired</span>
              </div>
            `;
          } else {
            actionHTML = `
              <div class="flex flex-col items-center gap-1.5">
                <button onclick="event.stopPropagation(); placeOrder('${item.seq_id}', '${item.symbol}', 'BUY', ${order.ltp || 300.0}, ${item.confidence}, '${item.catalyst_type}')" class="bg-emerald-600 hover:bg-emerald-500 active:scale-95 text-white font-bold text-xs px-3.5 py-1.5 rounded-lg transition shadow-lg shadow-emerald-600/30 border border-emerald-400/40 flex items-center gap-1.5">
                  <span>🚀</span>
                  <span>Approve Buy [A]</span>
                </button>
                <span class="text-[10px] text-amber-400 font-mono animate-pulse">⏳ Awaiting Approval</span>
              </div>
            `;
          }
        } else if (order.status === 'RECORDED') {
          actionHTML = `
            <div class="flex flex-col items-center text-center font-mono">
              <span class="px-2 py-0.5 text-[10px] font-bold bg-gray-800 text-gray-400 border border-gray-700 rounded flex items-center gap-1 shadow-sm">
                <span>📜</span> HISTORICAL
              </span>
              <span class="text-[10px] text-gray-500 mt-1">
                ${item.is_stale ? '⚠️ Past Event' : 'Recorded'}
              </span>
            </div>
          `;
        } else {
          const skipLabel = item.material_impact === false ? 'Non-Material (<1.5%)' : (order.remarks || 'Below Threshold');
          actionHTML = `
            <div class="flex flex-col items-center text-center font-mono">
              <span class="px-2 py-0.5 text-[10px] font-bold bg-gray-800 text-gray-400 border border-gray-700 rounded flex items-center gap-1 shadow-sm" title="${skipLabel}">
                <span>⏸️</span> Skipped
              </span>
              <span class="text-[10px] text-amber-500/80 mt-1 max-w-[150px] truncate" title="${skipLabel}">
                ${skipLabel}
              </span>
            </div>
          `;
        }
      } else {
        // Bearish
        if (order.placed) {
          actionHTML = `
            <div class="flex flex-col items-center text-center font-mono">
              <span class="px-2.5 py-1 text-[11px] font-bold bg-rose-500/20 text-rose-300 border border-rose-500/40 rounded-md flex items-center gap-1 shadow-sm">
                <span>🔻</span> SHORTED (Auto)
              </span>
              <span class="text-[10px] text-gray-400 mt-1 truncate max-w-[170px]" title="${order.order_id}">
                ID: <span class="text-gray-200 font-semibold">${order.order_id || 'VIRTUAL_SIMULATED'}</span>
              </span>
              <span class="text-[10px] text-rose-400 mt-0.5">@ ₹${order.entry_price ? order.entry_price.toFixed(2) : '0.00'} (${order.quantity} sh)</span>
            </div>
          `;
        } else if (order.status === 'PENDING_APPROVAL') {
          if (item.is_stale) {
            actionHTML = `
              <div class="flex flex-col items-center gap-1 font-mono">
                <button disabled class="bg-gray-800/80 text-gray-500 font-bold text-xs px-3 py-1.5 rounded-lg border border-gray-700/60 cursor-not-allowed flex items-center gap-1.5 opacity-60" title="News catalyst is older than 180 seconds. Order blocked to prevent stale trade execution.">
                  <span>⏱️</span>
                  <span>Stale (>180s)</span>
                </button>
                <span class="text-[10px] text-amber-500/80 font-mono">⚠️ Window Expired</span>
              </div>
            `;
          } else {
            actionHTML = `
              <div class="flex flex-col items-center gap-1.5">
                <button onclick="event.stopPropagation(); placeOrder('${item.seq_id}', '${item.symbol}', 'SELL', ${order.ltp || 300.0}, ${item.confidence}, '${item.catalyst_type}')" class="bg-rose-600 hover:bg-rose-500 active:scale-95 text-white font-bold text-xs px-3.5 py-1.5 rounded-lg transition shadow-lg shadow-rose-600/30 border border-rose-400/40 flex items-center gap-1.5">
                  <span>🔻</span>
                  <span>Short Sell [S]</span>
                </button>
                <span class="text-[10px] text-amber-400 font-mono animate-pulse">⏳ Awaiting Approval</span>
              </div>
            `;
          }
        } else if (order.status === 'RECORDED') {
          actionHTML = `
            <div class="flex flex-col items-center text-center font-mono">
              <span class="px-2 py-0.5 text-[10px] font-bold bg-gray-800 text-gray-400 border border-gray-700 rounded flex items-center gap-1 shadow-sm">
                <span>📜</span> HISTORICAL
              </span>
              <span class="text-[10px] text-gray-500 mt-1">
                ${item.is_stale ? '⚠️ Past Event' : 'Recorded'}
              </span>
            </div>
          `;
        } else {
          const skipLabel = item.material_impact === false ? 'Non-Material (<1.5%)' : (order.remarks || 'Below Threshold');
          actionHTML = `
            <div class="flex flex-col items-center text-center font-mono">
              <span class="px-2 py-0.5 text-[10px] font-bold bg-gray-800 text-gray-400 border border-gray-700 rounded flex items-center gap-1 shadow-sm" title="${skipLabel}">
                <span>⏸️</span> Skipped
              </span>
              <span class="text-[10px] text-amber-500/80 mt-1 max-w-[150px] truncate" title="${skipLabel}">
                ${skipLabel}
              </span>
            </div>
          `;
        }
      }

      // Main Row with Directional Accent & Drawer Trigger
      return `
        <tr onclick="openDrawer('${item.seq_id}')" data-seq-id="${item.seq_id}" class="feed-row ${borderAccentClass} cursor-pointer select-none transition-colors border-b border-gray-800/80 ${isNoise ? 'opacity-75 hover:opacity-100 bg-[#0d1322]' : ''}">
          
          <!-- Symbol & SecID -->
          <td class="py-3 px-4 align-middle">
            <div class="flex items-center gap-2">
              <span class="text-sm font-black ${isNoise ? 'text-gray-300' : 'text-white'} px-2 py-0.5 bg-gray-800 border border-gray-700 rounded tracking-wider">${item.symbol}</span>
              ${item.security_id && item.security_id !== '0' ? `<span class="text-[10px] font-mono px-1.5 py-0.5 bg-cyan-950/80 text-cyan-300 border border-cyan-800/60 rounded">#${item.security_id}</span>` : ''}
              
              <!-- 1-Click Interactive Live Chart Modal Button -->
              <button onclick="event.stopPropagation(); openChartModal('${item.symbol}')" class="px-2 py-0.5 rounded bg-emerald-500/20 hover:bg-emerald-500/35 text-emerald-300 border border-emerald-500/40 transition shadow-xs flex items-center gap-1 text-[11px] font-bold active:scale-95 group" title="Open ${item.symbol} Live Interactive Candlestick Chart">
                <span>📈</span>
                <span class="text-[10px]">Chart</span>
              </button>

              <!-- 1-Click TradingView Fullscreen Chart Link -->
              <a href="https://in.tradingview.com/chart/?symbol=NSE:${encodeURIComponent((item.symbol || '').toUpperCase())}" onclick="event.stopPropagation()" target="_blank" rel="noopener noreferrer" class="px-1.5 py-0.5 rounded bg-sky-950/40 hover:bg-sky-900/60 text-sky-400 border border-sky-800/40 transition shadow-xs flex items-center text-[10px] font-mono font-bold" title="Open ${item.symbol} Fullscreen on TradingView.com">
                TV ↗
              </a>
            </div>
            <div class="text-[10px] text-gray-500 mt-1 font-mono">${item.filter_reason && item.filter_reason.includes('Non-F&O') ? 'NSE_EQ • Equity' : 'NSE_EQ • F&O'}</div>
          </td>

          <!-- Date & Time + 180s Countdown Badge -->
          <td class="py-3 px-4 align-middle text-gray-300 font-mono text-xs whitespace-nowrap">
            <div class="font-bold text-gray-100 flex items-center gap-1">
              <span>🕒</span>
              <span>${item.an_dt && item.an_dt.includes(' ') ? item.an_dt.split(' ')[1] : (item.timestamp || item.an_dt || '--:--:--')}</span>
            </div>
            <div class="text-[11px] text-gray-400 mt-0.5 flex items-center gap-1">
              <span>📅</span>
              <span>${item.an_dt && item.an_dt.includes(' ') ? item.an_dt.split(' ')[0] : 'Today'}</span>
            </div>
            ${isMarketClosed ? `
              <div class="text-[10px] text-amber-400/90 font-semibold mt-1 flex items-center gap-1">
                <span>🌙</span><span>MARKET CLOSED</span>
              </div>
            ` : (isNoise ? `
              <div class="text-[10px] text-gray-500 font-semibold mt-1 flex items-center gap-1">
                <span>🔇</span><span>SUPPRESSED</span>
              </div>
            ` : `
              <div class="mt-1 flex items-center">
                <span data-andt="${item.an_dt || ''}" class="timer-badge px-2 py-0.5 rounded text-[10px] font-mono font-bold border transition-colors ${fresh.badgeClass}">${fresh.text}</span>
              </div>
            `)}
          </td>

          <!-- Catalyst & Headline + Extracted Metric Tags -->
          <td class="py-3 px-4 align-middle">
            <div class="flex items-center flex-wrap gap-1.5 mb-1">
              ${isMarketClosed ? `
                <span class="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded bg-amber-950/70 text-amber-300 border border-amber-800/60 font-mono">
                  ${item.filter_reason || 'MARKET_CLOSED'}
                </span>
                <span class="text-[11px] text-amber-500/80 font-mono">🌙 LLM Skipped</span>
              ` : (isNoise ? `
                <span class="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded bg-gray-900 text-gray-400 border border-gray-800 font-mono">
                  ${item.filter_reason || 'ROUTINE_NOISE'}
                </span>
                <span class="text-[11px] text-gray-500 font-mono">🔇 Filtered Out</span>
              ` : `
                <span class="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded bg-indigo-950 text-indigo-300 border border-indigo-800/80 font-mono">
                  ${item.catalyst_type}
                </span>
                <span class="text-[11px] text-emerald-400 font-mono">⚡ Passed</span>
              `)}
            </div>
            <div class="text-xs font-semibold ${isNoise ? 'text-gray-300' : 'text-gray-100'} hover:text-white flex items-center gap-1.5">
              <span>${item.desc}</span>
              <span class="text-[10px] text-gray-500 font-mono">↗</span>
            </div>
            <div class="text-[11px] text-gray-400 italic mt-1 border-l ${isMarketClosed ? 'border-amber-700/60 text-amber-400/70' : (isNoise ? 'border-gray-700 text-gray-500' : 'border-indigo-500/50')} pl-2 line-clamp-1">
              "${item.summary}"
            </div>
          </td>

          <!-- LLM Verdict -->
          <td class="py-3 px-4 align-middle text-center">
            ${verdictHTML}
          </td>

          <!-- Pricing -->
          <td class="py-3 px-4 align-middle">
            ${pricingHTML}
          </td>

          <!-- Live Market Price & P&L (Dedicated Column) -->
          <td class="py-3 px-4 align-middle text-center">
            ${livePnlHTML}
          </td>

          <!-- Action / Status -->
          <td class="py-3 px-4 align-middle text-center">
            ${actionHTML}
          </td>

        </tr>
      `;
    }

    async function placeOrder(seq_id, symbol, action, ltp, confidence, catalyst_type) {
      try {
        const act = (action || 'BUY').toUpperCase();
        const actionLabel = act === 'SELL' ? 'Short Sell' : 'Buy';
        showToast(`Placing ${actionLabel} Super Order for ${symbol}...`, '⏳');
        const res = await fetch('/api/orders/place', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            seq_id: seq_id,
            symbol: symbol,
            action: act,
            product_type: 'INTRADAY',
            confidence: confidence,
            catalyst_type: catalyst_type,
            ltp: ltp
          })
        });

        if (res.ok) {
          const data = await res.json();
          synth.playOrderChime();
          showToast(`${actionLabel} Super Order Placed for ${symbol}! Order ID: ${data.order_id}`, act === 'SELL' ? '🔻' : '🚀');
          fetchFeed();
        } else {
          const err = await res.json();
          showToast(`Order failed: ${err.detail || 'Unknown error'}`, '❌');
        }
      } catch (err) {
        showToast(`Failed placing order for ${symbol}`, '❌');
      }
    }

    async function triggerSimulation() {
      const btn = document.getElementById('sim-btn');
      if (btn) {
        btn.disabled = true;
        btn.classList.add('opacity-50');
      }
      showToast('Running Gemini 3.7 Flash simulation cycle...', '🤖');
      try {
        const res = await fetch('/api/simulate', { method: 'POST' });
        if (res.ok) {
          const data = await res.json();
          showToast(`Simulation complete! Ingested ${data.processed_count} catalyst filings.`, '✅');
          fetchFeed();
        } else {
          const err = await res.json().catch(() => ({ detail: 'Simulation disabled' }));
          showToast(`Simulation failed: ${err.detail || 'Access forbidden'}`, '❌');
        }
      } catch (err) {
        showToast('Simulation request failed', '❌');
      } finally {
        if (btn) {
          btn.disabled = false;
          btn.classList.remove('opacity-50');
        }
      }
    }

    function connectSSE() {
      const evtSource = new EventSource('/api/events');
      evtSource.onmessage = function(event) {
        try {
          const payload = JSON.parse(event.data);
          if (payload.type === 'NEW_CATALYST') {
            fetchFeed();
            fetchTokenStatus();
            fetchStatus();
            if (payload.data) {
              const item = payload.data;
              const isBull = item.sentiment === 'BULLISH';
              if (isBull) synth.playBullishChime();
              else synth.playBearishChime();
              sendDesktopNotification(`🚨 [${item.sentiment}] ${item.symbol} Catalyst!`, item.desc || item.summary);
              triggerTabAlert(item.symbol, item.sentiment);
            }
          } else if (payload.type === 'ORDER_PLACED') {
            synth.playOrderChime();
            fetchFeed();
            fetchTokenStatus();
            fetchStatus();
          } else if (payload.type === 'AUTO_ORDER_TOGGLE' || payload.type === 'TOKEN_UPDATED' || payload.type === 'MODE_TOGGLED' || payload.type === 'FEED_CLEARED') {
            fetchFeed();
            fetchTokenStatus();
            fetchStatus();
          } else if (payload.type === 'STRATEGY_STATUS_TOGGLE') {
            const sid = payload.data ? (payload.data.strategy_id || 'st_news') : 'st_news';
            const stat = payload.data ? (payload.data.status || payload.data.strategy_status) : null;
            if (stat) {
              if (sid === 'st_news') {
                isNewsEngineActive = (stat !== 'PAUSED');
              } else if (sid === 'st14_bullish_ce') {
                isSt14EngineActive = (stat !== 'PAUSED');
              }
              syncActiveStrategyState();
              loadStrategies();
            }
            fetchFeed();
            fetchStatus();
          } else if (payload.type === 'FEED_HISTORY_LOADED') {
            fetchFeed();
            fetchTokenStatus();
            fetchStatus();
            if (payload.data && payload.data.view_mode) {
              updateScopeUI(payload.data.view_mode === 'TODAY');
            }
          } else if (payload.type === 'DAY_ROLLOVER') {
            const newDate = (payload.data && payload.data.new_date) ? payload.data.new_date : 'Today';
            showToast(`🌅 New Trading Day (${newDate})! Feed refreshed for today.`, '📅');
            fetchFeed();
            fetchTokenStatus();
            fetchStatus();
            updateScopeUI(true);
          } else if (payload.type === 'AUTO_SQUARE_OFF' || payload.type === 'MANUAL_SQUARE_OFF') {
            synth.playWarningChime();
            const label = payload.type === 'AUTO_SQUARE_OFF' ? '⏰ 15:00 Auto Square-Off' : '🛑 Manual Square-Off';
            showToast(`${label} executed! Intraday positions flattened.`, '⚠️');
            fetchFeed();
            fetchStatus();
          } else if (payload.type === 'POLL_CYCLE_COMPLETED') {
            if (payload.data && payload.data.last_polled_ts) {
              lastPolledTimestamp = payload.data.last_polled_ts * 1000;
            }
            if (document.getElementById('poller-last-time') && payload.data.last_polled_time) {
              document.getElementById('poller-last-time').textContent = payload.data.last_polled_time;
            }
            if (document.getElementById('poller-noise-count')) {
              document.getElementById('poller-noise-count').textContent = payload.data.suppressed_noise_count || '0';
            }
            if (payload.data && typeof payload.data.is_market_open === 'boolean') {
              lastKnownMarketOpen = payload.data.is_market_open;
              updateRadarStatusUI(payload.data.is_market_open, lastKnownMarketHoursOnly);
              updateEmptyStateUI(payload.data.is_market_open, lastKnownMarketHoursOnly);
            }
            updatePollerTimer();
            const badge = document.getElementById('radar-badge-container');
            if (badge) {
              const ringColor = (payload.data && payload.data.is_market_open === false) ? 'ring-amber-400' : 'ring-emerald-400';
              badge.classList.add('ring-2', ringColor);
              setTimeout(() => badge.classList.remove('ring-2', ringColor), 1200);
            }
          } else if (payload.type === 'ST14_UPDATE') {
            if (activeStrategyId === 'st14_bullish_ce') {
              loadSt14Data();
            }
            if (payload.data && payload.data.orders_placed > 0) {
              synth.playOrderChime();
              showToast(`🎯 ST-14 Trigger! ${payload.data.orders_placed} Super Order(s) dispatched.`, '🚀');
            }
          }
        } catch (e) {}
      };
      evtSource.onerror = function() {
        setTimeout(connectSSE, 5000);
      };
    }

    async function pollLivePrices() {
      try {
        const res = await fetch('/api/prices/live');
        if (res.ok) {
          const data = await res.json();
          if (data && data.prices && Object.keys(data.prices).length > 0) {
            let updated = false;
            for (const item of rawFeedItems) {
              if (item.symbol && data.prices[item.symbol] !== undefined) {
                if (!item.order) item.order = {};
                if (item.order.current_ltp !== data.prices[item.symbol]) {
                  item.order.current_ltp = data.prices[item.symbol];
                  updated = true;
                }
              }
            }
            if (updated) {
              renderFeed();
            }
          }
        }
      } catch (err) {
        console.debug('Live price poll skipped:', err);
      }
    }

    let registeredStrategies = [];
    let activeStrategyId = 'st_news';
    let currentStrategyCategory = 'ALL';

    function toggleStrategyMenu() {
      const btn = document.getElementById('btn-strategy-selector');
      if (btn && btn.disabled) return;
      const menu = document.getElementById('strategy-menu-dropdown');
      if (menu) {
        menu.classList.toggle('hidden');
      }
    }

    // Dismiss dropdowns when clicking outside
    document.addEventListener('click', function(e) {
      const stratContainer = document.getElementById('strategy-selector-container');
      const stratMenu = document.getElementById('strategy-menu-dropdown');
      if (stratContainer && stratMenu && !stratContainer.contains(e.target)) {
        stratMenu.classList.add('hidden');
      }

      const userContainer = document.getElementById('user-account-container');
      const userMenu = document.getElementById('user-menu-dropdown');
      if (userContainer && userMenu && !userContainer.contains(e.target)) {
        userMenu.classList.add('hidden');
      }
    });

    async function loadStrategies() {
      try {
        const res = await fetch('/api/strategies');
        if (res.ok) {
          registeredStrategies = await res.json();

          // Sync state for st_news
          const stNews = registeredStrategies.find(s => s.id === 'st_news');
          if (stNews) {
            isNewsEngineActive = (stNews.status === 'ACTIVE');
            isNewsDryRun = (stNews.execution_mode === 'VIRTUAL');
            isNewsAutoOrder = !!stNews.auto_order_enabled;
          }

          // Sync state for st14
          const st14 = registeredStrategies.find(s => s.id === 'st14_bullish_ce');
          if (st14) {
            isSt14EngineActive = (st14.status === 'ACTIVE');
            isSt14DryRun = (st14.execution_mode === 'VIRTUAL');
            isSt14AutoOrder = !!st14.auto_order_enabled;
          }

          syncActiveStrategyState();
          renderStrategyCards();
        }
      } catch (err) {
        console.debug('Failed loading strategies catalog:', err);
      }
    }

    function filterStrategyCategory(cat) {
      currentStrategyCategory = cat || 'ALL';
      document.querySelectorAll('.strat-cat-pill').forEach(btn => {
        const pillCat = btn.getAttribute('data-strat-cat');
        if (pillCat === currentStrategyCategory) {
          btn.className = 'strat-cat-pill px-2 py-0.5 rounded-md font-semibold transition bg-emerald-600 text-white';
        } else {
          btn.className = 'strat-cat-pill px-2 py-0.5 rounded-md font-semibold transition text-gray-400 hover:bg-gray-800';
        }
      });
      renderStrategyCards();
    }

    function renderStrategyCards() {
      const container = document.getElementById('strategy-cards-grid');
      if (!container || !registeredStrategies || registeredStrategies.length === 0) return;

      const filtered = registeredStrategies.filter(strat => {
        if (currentStrategyCategory === 'ALL') return true;
        return strat.category === currentStrategyCategory;
      });

      const countBadge = document.getElementById('strategies-count-badge');
      if (countBadge) {
        countBadge.textContent = `${registeredStrategies.length} Registered`;
      }

      container.innerHTML = filtered.map(strat => {
        const isSelected = strat.id === activeStrategyId;
        const activeCardClass = isSelected
          ? 'bg-emerald-950/50 border-emerald-500/80 ring-1 ring-emerald-500/60 shadow-md'
          : 'bg-[#162032]/90 hover:bg-[#1f293d] border-gray-800 hover:border-gray-700';

        const statusBg = strat.status === 'ACTIVE'
          ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40'
          : strat.status === 'PAUSED'
          ? 'bg-amber-500/20 text-amber-300 border-amber-500/40'
          : strat.status === 'READY'
          ? 'bg-blue-500/20 text-blue-300 border-blue-500/40'
          : 'bg-gray-800 text-gray-400 border-gray-700';

        return `
          <div onclick="selectStrategy('${strat.id}')" class="cursor-pointer rounded-xl border p-2.5 transition-all duration-150 flex items-center justify-between gap-3 ${activeCardClass}">
            <div class="flex items-center gap-2.5 min-w-0">
              <span class="text-xl flex-shrink-0">${strat.icon || '⚡'}</span>
              <div class="min-w-0">
                <div class="flex items-center gap-1.5">
                  <span class="px-1.5 py-0.2 rounded text-[10px] font-mono font-bold bg-gray-800 text-gray-200 border border-gray-700">${strat.code}</span>
                  <span class="text-xs font-bold text-white truncate">${strat.name}</span>
                </div>
                <div class="text-[10px] text-gray-400 font-mono mt-0.5 truncate">${strat.category_label || strat.category} • ${strat.timeframe}</div>
              </div>
            </div>
            <div class="flex items-center gap-2 flex-shrink-0">
              <span class="px-2 py-0.5 rounded-full text-[10px] font-bold border ${statusBg}">${strat.status}</span>
              ${isSelected ? '<span class="text-emerald-400 font-bold text-xs">✓</span>' : ''}
            </div>
          </div>
        `;
      }).join('');
    }

    async function toggleSt14Product() {
      const targetProd = (st14ProductType === 'INTRADAY') ? 'DELIVERY' : 'INTRADAY';
      try {
        const res = await fetch('/api/strategies/st14_bullish_ce/toggle-product', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ product_type: targetProd })
        });
        if (res.ok) {
          const data = await res.json();
          st14ProductType = data.product_type;
          loadSt14Data();
          showToast(`ST-14 Product set to: ${st14ProductType}`, '📦');
        }
      } catch (e) {
        showToast('Failed to update product type', '❌');
      }
    }

    async function runSt14HourlyScanNow() {
      const spinner = document.getElementById('st14-hourly-btn-spinner');
      const btn = document.getElementById('st14-btn-hourly-scan');
      if (spinner) spinner.classList.remove('hidden');
      if (btn) btn.disabled = true;

      try {
        showToast('🚀 Running ST-14 1-Hour Discovery Scan on 228 F&O Universe...', '⚡');
        const res = await fetch('/api/strategies/st14_bullish_ce/run-hourly-scan', { method: 'POST' });
        const data = await res.json();
        if (res.ok) {
          loadSt14Data();
          loadStrategies();
          showToast(`✅ 1-Hr Scan complete: Found ${data.discovered_candidates_count || 0} candidate(s), active watchlist: ${data.active_watchlist_count || 0}`, '🎯');
        } else {
          showToast(`Scan failed: ${data.detail || data.error}`, '❌');
        }
      } catch (err) {
        showToast('Failed to execute 1-Hour scan', '❌');
      } finally {
        if (spinner) spinner.classList.add('hidden');
        if (btn) btn.disabled = false;
      }
    }

    async function runSt14TriggerCheckNow() {
      const spinner = document.getElementById('st14-trigger-btn-spinner');
      const btn = document.getElementById('st14-btn-trigger-check');
      if (spinner) spinner.classList.remove('hidden');
      if (btn) btn.disabled = true;

      try {
        showToast('🎯 Checking 5-Min triggers for watchlisted stocks...', '🔍');
        const res = await fetch('/api/strategies/st14_bullish_ce/run-trigger-check', { method: 'POST' });
        const data = await res.json();
        if (res.ok) {
          loadSt14Data();
          loadStrategies();
          if (data.signals_count > 0) {
            synth.playOrderChime();
            showToast(`🚀 Dispatched ${data.signals_count} Super Order(s) for triggered stocks!`, '🎉');
          } else {
            showToast(`Checked ${data.watchlist_count || 0} watchlist stock(s): No breakout trigger hit currently.`, 'ℹ️');
          }
        } else {
          showToast(`Trigger check failed: ${data.detail || data.error}`, '❌');
        }
      } catch (err) {
        showToast('Failed to execute 5-min trigger check', '❌');
      } finally {
        if (spinner) spinner.classList.add('hidden');
        if (btn) btn.disabled = false;
      }
    }

    function getNextHourlyScanTime() {
      const now = new Date();
      const istOffset = 5.5 * 60 * 60 * 1000;
      const utc = now.getTime() + (now.getTimezoneOffset() * 60000);
      const istDate = new Date(utc + istOffset);
      const hour = istDate.getHours();
      const min = istDate.getMinutes();
      const totalMin = hour * 60 + min;

      const schedule = [
        { h: 10, m: 15, label: '10:15 IST' },
        { h: 11, m: 15, label: '11:15 IST' },
        { h: 12, m: 15, label: '12:15 IST' },
        { h: 13, m: 15, label: '13:15 IST' },
        { h: 14, m: 0,  label: '14:00 IST' },
      ];

      for (const slot of schedule) {
        if (totalMin < (slot.h * 60 + slot.m)) {
          return slot.label;
        }
      }
      return 'Completed for Today';
    }

    function updateSt14TelemetryUI(telemetry) {
      if (!telemetry) return;

      // Radar Item 1
      const radarStatusText = document.getElementById('st14-radar-status-text');
      const radarSubtext = document.getElementById('st14-radar-subtext');
      const radarPing = document.getElementById('st14-radar-ping');
      const radarDot = document.getElementById('st14-radar-dot');

      const isMarketOpen = computeMarketStatusClient();
      if (!isSt14EngineActive) {
        if (radarStatusText) {
          radarStatusText.textContent = 'ENGINE PAUSED';
          radarStatusText.className = 'text-xs font-bold text-amber-400 font-mono';
        }
        if (radarSubtext) radarSubtext.textContent = 'Manual Resume Required';
        if (radarPing) radarPing.className = 'hidden';
        if (radarDot) radarDot.className = 'relative inline-flex rounded-full h-2.5 w-2.5 bg-amber-400';
      } else if (!isMarketOpen) {
        if (radarStatusText) {
          radarStatusText.textContent = 'STANDBY (OFF-MARKET)';
          radarStatusText.className = 'text-xs font-bold text-amber-300 font-mono';
        }
        if (radarSubtext) radarSubtext.textContent = 'Auto-resumes 09:15 IST';
        if (radarPing) radarPing.className = 'hidden';
        if (radarDot) radarDot.className = 'relative inline-flex rounded-full h-2.5 w-2.5 bg-amber-400';
      } else {
        if (radarStatusText) {
          radarStatusText.textContent = 'ACTIVE DUAL LOOP';
          radarStatusText.className = 'text-xs font-bold text-emerald-400 font-mono';
        }
        if (radarSubtext) radarSubtext.textContent = '1h Discovery + 5m Poller';
        if (radarPing) radarPing.className = 'animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75';
        if (radarDot) radarDot.className = 'relative inline-flex rounded-full h-2.5 w-2.5 bg-emerald-500';
      }

      // Tier 1 - 1-Hour Scanner
      const hourlyLastEl = document.getElementById('st14-hourly-last-time');
      const hourlyNextEl = document.getElementById('st14-hourly-next-time');
      const hourlyBadge = document.getElementById('st14-hourly-count-badge');
      if (hourlyLastEl) hourlyLastEl.textContent = telemetry.last_hourly_scan_time || 'None today';
      if (hourlyNextEl) hourlyNextEl.textContent = getNextHourlyScanTime();
      if (hourlyBadge) hourlyBadge.textContent = `${telemetry.last_hourly_candidates_count || 0} Discovered`;

      // Tier 2 - 5-Min Poller
      const pollerLastEl = document.getElementById('st14-5min-last-time');
      const pollerBadge = document.getElementById('st14-watchlist-count-badge');
      const activeWatchCount = telemetry.active_watchlist_count !== undefined ? telemetry.active_watchlist_count : (telemetry.breakout_watchlist ? telemetry.breakout_watchlist.length : 0);
      if (pollerLastEl) pollerLastEl.textContent = telemetry.last_5min_check_time || 'None yet';
      if (pollerBadge) pollerBadge.textContent = `${activeWatchCount} Watching`;

      // Capacity & Mode
      const capEl = document.getElementById('st14-capacity-text');
      const modeBadge = document.getElementById('st14-mode-badge');
      const autoEl = document.getElementById('st14-auto-order-text');
      const posCount = telemetry.active_positions_count || 0;
      if (capEl) capEl.textContent = `${posCount} / 5 Slots`;
      if (modeBadge) {
        modeBadge.textContent = telemetry.mode || 'VIRTUAL';
        modeBadge.className = (telemetry.mode === 'LIVE')
          ? 'px-1.5 py-0.2 rounded text-[10px] font-bold bg-rose-950 text-rose-300 border border-rose-800 animate-pulse'
          : 'px-1.5 py-0.2 rounded text-[10px] font-bold bg-emerald-950 text-emerald-300 border border-emerald-800';
      }
      if (autoEl) {
        autoEl.textContent = telemetry.auto_order ? 'ON' : 'OFF';
        autoEl.className = telemetry.auto_order ? 'text-emerald-400 font-bold' : 'text-amber-400 font-bold';
      }
    }

    async function loadSt14Data() {
      try {
        const res = await fetch('/api/strategies/st14_bullish_ce');
        if (!res.ok) return;
        const data = await res.json();
        st14Telemetry = data.telemetry || {};

        isSt14EngineActive = (data.status === 'ACTIVE');
        isSt14DryRun = (data.execution_mode === 'VIRTUAL');
        isSt14AutoOrder = !!data.auto_order_enabled;
        st14ProductType = (st14Telemetry.product_type || 'INTRADAY').toUpperCase();

        syncActiveStrategyState();

        // Update ST-14 Status Pill & Product Button
        const statusPill = document.getElementById('st14-status-pill');
        const statusTxt = document.getElementById('st14-status-txt');
        const statusDot = document.getElementById('st14-status-dot');
        if (isSt14EngineActive) {
          if (statusPill) statusPill.className = 'px-2.5 py-0.5 rounded-full text-xs font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 flex items-center gap-1.5';
          if (statusTxt) statusTxt.textContent = 'ACTIVE';
          if (statusDot) statusDot.className = 'w-2 h-2 rounded-full bg-emerald-400 animate-pulse';
        } else {
          if (statusPill) statusPill.className = 'px-2.5 py-0.5 rounded-full text-xs font-bold bg-amber-500/20 text-amber-300 border border-amber-500/40 flex items-center gap-1.5';
          if (statusTxt) statusTxt.textContent = 'PAUSED';
          if (statusDot) statusDot.className = 'w-2 h-2 rounded-full bg-amber-400';
        }

        const btnProdTxt = document.getElementById('st14-btn-product-txt');
        if (btnProdTxt) btnProdTxt.textContent = (st14ProductType === 'INTRADAY') ? '⏰ INTRADAY' : '📦 DELIVERY';

        // Breadth detail
        const breadth = st14Telemetry.market_breadth || {};
        const isBreadthGreen = (breadth.nifty50_green && breadth.banknifty_green);
        const breadthTitle = document.getElementById('st14-breadth-title');
        const breadthDot = document.getElementById('st14-breadth-dot');
        const breadthDetail = document.getElementById('st14-card-breadth-detail');
        if (breadthTitle) {
          breadthTitle.textContent = isBreadthGreen ? 'NIFTY & BANKNIFTY GREEN' : (breadth.message || 'INDICES NOT GREEN');
          breadthTitle.className = isBreadthGreen ? 'text-emerald-400' : 'text-amber-400';
        }
        if (breadthDot) {
          breadthDot.className = isBreadthGreen ? 'w-2 h-2 rounded-full bg-emerald-400 animate-pulse' : 'w-2 h-2 rounded-full bg-amber-400';
        }
        if (breadthDetail) {
          breadthDetail.textContent = `NIFTY: ${breadth.nifty_chg_pct > 0 ? '+' : ''}${breadth.nifty_chg_pct || 0}% | BANKNIFTY: ${breadth.banknifty_chg_pct > 0 ? '+' : ''}${breadth.banknifty_chg_pct || 0}%`;
        }

        // Capital
        if (document.getElementById('st14-card-capital') && st14Telemetry.capital_per_trade) {
          document.getElementById('st14-card-capital').textContent = `₹${st14Telemetry.capital_per_trade.toLocaleString('en-IN')} / trade`;
        }

        // Total PnL
        if (document.getElementById('st14-total-pnl-val')) {
          const pnl = st14Telemetry.total_pnl || 0.0;
          const pnlEl = document.getElementById('st14-total-pnl-val');
          pnlEl.textContent = `${pnl >= 0 ? '+' : ''}₹${pnl.toFixed(2)}`;
          pnlEl.className = pnl >= 0 ? 'font-bold text-emerald-400 font-mono' : 'font-bold text-rose-400 font-mono';
        }

        // Render Telemetry Cards & Tables
        updateSt14TelemetryUI(st14Telemetry);
        renderSt14Watchlist(st14Telemetry.breakout_watchlist || []);
        renderSt14Positions(st14Telemetry.active_positions || []);
      } catch (err) {
        console.debug('Failed loading ST-14 data:', err);
      }
    }

    function renderSt14Watchlist(items) {
      const tbody = document.getElementById('st14-watchlist-tbody');
      const emptyState = document.getElementById('st14-watchlist-empty');
      const countHeader = document.getElementById('st14-watchlist-count-header');
      if (!tbody) return;

      if (countHeader) countHeader.textContent = `${items.length} Stocks`;

      if (!items || items.length === 0) {
        tbody.innerHTML = '';
        if (emptyState) emptyState.classList.remove('hidden');
        return;
      }

      if (emptyState) emptyState.classList.add('hidden');

      tbody.innerHTML = items.map(stock => {
        const isTriggered = stock.is_triggered;
        const triggerBadge = isTriggered
          ? '<span class="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 flex items-center gap-1"><span class="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span> TRIGGER HIT</span>'
          : '<span class="px-2 py-0.5 rounded-full text-[10px] font-mono font-semibold bg-amber-500/10 text-amber-300 border border-amber-500/30">MONITORING</span>';

        const ltpClass = (stock.ltp >= stock.breakout_high) ? 'text-emerald-400 font-bold' : 'text-white font-semibold';
        const chgClass = (stock.day_change_pct >= 0) ? 'text-emerald-400' : 'text-rose-400';

        return `
          <tr class="border-b border-gray-800/60 hover:bg-gray-800/40 transition">
            <td class="px-4 py-2.5">
              <div class="flex items-center gap-2">
                <span class="font-bold text-white text-xs">${stock.symbol}</span>
                <span class="text-[10px] font-mono text-gray-500">Sec ${stock.security_id || '-'}</span>
              </div>
            </td>
            <td class="px-4 py-2.5 font-mono text-xs ${ltpClass}">
              ₹${Number(stock.ltp || 0).toFixed(2)}
            </td>
            <td class="px-4 py-2.5 font-mono text-xs ${chgClass}">
              ${stock.day_change_pct >= 0 ? '+' : ''}${Number(stock.day_change_pct || 0).toFixed(2)}%
            </td>
            <td class="px-4 py-2.5 font-mono text-xs text-indigo-300 font-semibold">
              ₹${Number(stock.breakout_high || 0).toFixed(2)}
            </td>
            <td class="px-4 py-2.5 font-mono text-xs text-gray-400">
              ₹${Number(stock.lookback_5d_high || 0).toFixed(2)}
            </td>
            <td class="px-4 py-2.5 font-mono text-[11px] text-blue-300">
              ${stock.selected_option_symbol || stock.selected_strike_display || '1-OTM CE'}
            </td>
            <td class="px-4 py-2.5">
              ${triggerBadge}
            </td>
            <td class="px-4 py-2.5 text-right">
              <button onclick="triggerImmediateOrder('${stock.symbol}')" class="px-2.5 py-1 text-[11px] font-bold rounded bg-emerald-600 hover:bg-emerald-500 text-white transition active:scale-95 shadow" title="Manually place 1-OTM CE Super Order immediately for ${stock.symbol}">
                ⚡ Trade CE
              </button>
            </td>
          </tr>
        `;
      }).join('');
    }

    async function triggerImmediateOrder(symbol) {
      if (!confirm(`Deploy ST-14 1-OTM Call Option Super Order for ${symbol}?`)) return;
      try {
        const res = await fetch(`/api/strategies/st14_bullish_ce/manual-order/${symbol}`, { method: 'POST' });
        const data = await res.json();
        if (res.ok) {
          synth.playOrderChime();
          showToast(`🚀 Order placed for ${symbol}!`, '✅');
          loadSt14Data();
        } else {
          showToast(`Order failed: ${data.detail || data.error}`, '❌');
        }
      } catch (err) {
        showToast(`Failed to place order for ${symbol}`, '❌');
      }
    }

    function renderSt14Positions(positions) {
      const container = document.getElementById('st14-positions-table-container');
      const emptyState = document.getElementById('st14-positions-empty');
      const countHeader = document.getElementById('st14-positions-count-header');
      if (!container) return;

      if (countHeader) countHeader.textContent = `${positions.length} Positions`;

      if (!positions || positions.length === 0) {
        container.innerHTML = '';
        if (emptyState) emptyState.classList.remove('hidden');
        return;
      }

      if (emptyState) emptyState.classList.add('hidden');

      container.innerHTML = `
        <table class="w-full text-left text-xs border-collapse">
          <thead>
            <tr class="border-b border-gray-800 text-[10px] uppercase font-bold text-gray-400 bg-[#0d1527]/70">
              <th class="px-4 py-2">Symbol / Strike</th>
              <th class="px-4 py-2">Qty</th>
              <th class="px-4 py-2">Entry Price</th>
              <th class="px-4 py-2">LTP</th>
              <th class="px-4 py-2">Target (+40%)</th>
              <th class="px-4 py-2">Stop Loss (-20%)</th>
              <th class="px-4 py-2">P&L</th>
              <th class="px-4 py-2">Status</th>
              <th class="px-4 py-2 text-right">Action</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-800/60 font-mono">
            ${positions.map(pos => {
              const pnl = Number(pos.unrealized_pnl || 0);
              const pnlPct = Number(pos.pnl_pct || 0);
              const pnlClass = pnl >= 0 ? 'text-emerald-400 font-bold' : 'text-rose-400 font-bold';
              return `
                <tr class="hover:bg-gray-800/40 transition">
                  <td class="px-4 py-2.5 font-sans font-bold text-white">
                    <div>${pos.underlying_symbol}</div>
                    <div class="text-[10px] text-blue-400 font-mono font-normal">${pos.option_symbol || pos.strike_price}</div>
                  </td>
                  <td class="px-4 py-2.5 text-gray-300">${pos.quantity}</td>
                  <td class="px-4 py-2.5 text-gray-300">₹${Number(pos.entry_price || 0).toFixed(2)}</td>
                  <td class="px-4 py-2.5 text-white font-bold">₹${Number(pos.ltp || pos.entry_price || 0).toFixed(2)}</td>
                  <td class="px-4 py-2.5 text-emerald-400 font-semibold">₹${Number(pos.target_price || 0).toFixed(2)}</td>
                  <td class="px-4 py-2.5 text-rose-400 font-semibold">₹${Number(pos.stop_loss_price || 0).toFixed(2)}</td>
                  <td class="px-4 py-2.5 ${pnlClass}">
                    ${pnl >= 0 ? '+' : ''}₹${pnl.toFixed(2)} (${pnlPct >= 0 ? '+' : ''}${pnlPct.toFixed(2)}%)
                  </td>
                  <td class="px-4 py-2.5">
                    <span class="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-950 text-emerald-300 border border-emerald-800">
                      ${pos.status || 'OPEN'}
                    </span>
                  </td>
                  <td class="px-4 py-2.5 text-right">
                    <button onclick="closeSt14Position('${pos.position_id || pos.order_id}')" class="px-2 py-0.5 text-[10px] font-bold rounded bg-rose-950 hover:bg-rose-900 text-rose-300 border border-rose-800 transition active:scale-95">
                      Exit
                    </button>
                  </td>
                </tr>
              `;
            }).join('')}
          </tbody>
        </table>
      `;
    }

    async function closeSt14Position(posId) {
      if (!confirm(`Are you sure you want to close position ${posId}?`)) return;
      try {
        const res = await fetch(`/api/strategies/st14_bullish_ce/positions/${posId}/exit`, { method: 'POST' });
        const data = await res.json();
        if (res.ok) {
          showToast('✅ Position closed successfully', '🛑');
          loadSt14Data();
        } else {
          showToast(`Exit failed: ${data.detail || data.error}`, '❌');
        }
      } catch (e) {
        showToast('Failed to exit position', '❌');
      }
    }

    function selectStrategy(strategyId) {
      activeStrategyId = strategyId;
      renderStrategyCards();

      // Close dropdown menu
      const menu = document.getElementById('strategy-menu-dropdown');
      if (menu) menu.classList.add('hidden');

      // Update header active strategy badge
      const strat = registeredStrategies.find(s => s.id === strategyId);
      if (strat) {
        if (document.getElementById('header-strat-icon')) document.getElementById('header-strat-icon').textContent = strat.icon || '⚡';
        if (document.getElementById('header-strat-code')) document.getElementById('header-strat-code').textContent = strat.code;
        if (document.getElementById('header-strat-name')) document.getElementById('header-strat-name').textContent = strat.name;
      }

      const wsNews = document.getElementById('workspace-st-news');
      const wsSt14 = document.getElementById('workspace-st14');
      const wsModular = document.getElementById('workspace-st-modular');
      const strategyControls = document.getElementById('strategy-controls-group');

      if (strategyId === 'st_news') {
        if (wsNews) wsNews.classList.remove('hidden');
        if (wsSt14) wsSt14.classList.add('hidden');
        if (wsModular) wsModular.classList.add('hidden');
        syncActiveStrategyState();
      } else if (strategyId === 'st14_bullish_ce') {
        if (wsNews) wsNews.classList.add('hidden');
        if (wsSt14) wsSt14.classList.remove('hidden');
        if (wsModular) wsModular.classList.add('hidden');
        syncActiveStrategyState();
        loadSt14Data();
      } else {
        if (wsNews) wsNews.classList.add('hidden');
        if (wsSt14) wsSt14.classList.add('hidden');
        if (wsModular) wsModular.classList.remove('hidden');

        if (strat) {
          if (document.getElementById('mod-strat-icon')) document.getElementById('mod-strat-icon').textContent = strat.icon || '📈';
          if (document.getElementById('mod-strat-code')) document.getElementById('mod-strat-code').textContent = strat.code;
          if (document.getElementById('mod-strat-title')) document.getElementById('mod-strat-title').textContent = strat.name;
          if (document.getElementById('mod-strat-desc')) document.getElementById('mod-strat-desc').textContent = strat.description;
          if (document.getElementById('mod-strat-universe')) document.getElementById('mod-strat-universe').textContent = strat.universe;
          if (document.getElementById('mod-strat-timeframe')) document.getElementById('mod-strat-timeframe').textContent = strat.timeframe;
          if (document.getElementById('mod-strat-risk')) document.getElementById('mod-strat-risk').textContent = strat.risk_level;
          if (document.getElementById('mod-strat-capital')) {
            const cap = strat.metrics && strat.metrics.allocated_capital ? strat.metrics.allocated_capital : 20000;
            document.getElementById('mod-strat-capital').textContent = `₹${cap.toLocaleString('en-IN')} / trade`;
          }
          if (document.getElementById('mod-strat-engine-mode')) {
            document.getElementById('mod-strat-engine-mode').textContent = `🛡️ ${strat.execution_mode} MODE`;
          }
          if (document.getElementById('mod-strat-status-badge')) {
            document.getElementById('mod-strat-status-badge').textContent = `🟢 ${strat.status}`;
          }
        }
      }
    }

    function launchModularStrategyScan() {
      switchMainTab('scanner');
      showToast(`Switched to Technical Scanner Studio for ${activeStrategyId.toUpperCase()}`, '🔍');
    }

    function switchMainTab(tabName) {
      const strategiesTab = document.getElementById('main-tab-strategies');
      const scannerTab = document.getElementById('main-tab-scanner');
      const btnStrategies = document.getElementById('nav-tab-strategies');
      const btnScanner = document.getElementById('nav-tab-scanner');
      const btnEod = document.getElementById('nav-tab-eod');
      const btnStratSelector = document.getElementById('btn-strategy-selector');
      const stratMenu = document.getElementById('strategy-menu-dropdown');

      const viewHome = document.getElementById('view-home');
      const viewResults = document.getElementById('view-results');
      const viewEod = document.getElementById('view-eod-digest');

      if (tabName === 'eod') {
        if (strategiesTab) strategiesTab.classList.add('hidden');
        if (scannerTab) scannerTab.classList.remove('hidden');
        if (stratMenu) stratMenu.classList.add('hidden');
        
        if (viewHome) viewHome.classList.add('hidden');
        if (viewResults) viewResults.classList.add('hidden');
        if (viewEod) viewEod.classList.remove('hidden');

        if (btnStratSelector) {
          btnStratSelector.disabled = true;
          btnStratSelector.classList.add('opacity-30', 'cursor-not-allowed', 'pointer-events-none');
          btnStratSelector.setAttribute('title', 'Strategy selector disabled in EOD Digest mode.');
        }

        if (btnStrategies) btnStrategies.className = "px-2.5 py-1 rounded-lg text-xs font-bold transition text-gray-400 hover:text-gray-200 hover:bg-gray-800 flex items-center gap-1.5";
        if (btnScanner) btnScanner.className = "px-2.5 py-1 rounded-lg text-xs font-bold transition text-gray-400 hover:text-gray-200 hover:bg-gray-800 flex items-center gap-1.5";
        if (btnEod) btnEod.className = "px-2.5 py-1 rounded-lg text-xs font-bold transition bg-amber-600 text-white shadow-sm flex items-center gap-1.5";

        if (typeof showEodDigestView === 'function') {
          showEodDigestView();
        } else if (typeof loadEodDatesAndLatest === 'function') {
          loadEodDatesAndLatest();
        }
      } else if (tabName === 'scanner') {
        if (strategiesTab) strategiesTab.classList.add('hidden');
        if (scannerTab) scannerTab.classList.remove('hidden');
        if (stratMenu) stratMenu.classList.add('hidden');
        
        if (viewHome) viewHome.classList.remove('hidden');
        if (viewResults) viewResults.classList.add('hidden');
        if (viewEod) viewEod.classList.add('hidden');

        // Disable Strategy Dropdown in Scanner view
        if (btnStratSelector) {
          btnStratSelector.disabled = true;
          btnStratSelector.classList.add('opacity-30', 'cursor-not-allowed', 'pointer-events-none');
          btnStratSelector.setAttribute('title', 'Strategy selector disabled in Technical Scanner mode. Switch to Strategies tab to change strategy.');
        }

        if (btnStrategies) btnStrategies.className = "px-2.5 py-1 rounded-lg text-xs font-bold transition text-gray-400 hover:text-gray-200 hover:bg-gray-800 flex items-center gap-1.5";
        if (btnScanner) btnScanner.className = "px-2.5 py-1 rounded-lg text-xs font-bold transition bg-indigo-600 text-white shadow-sm flex items-center gap-1.5";
        if (btnEod) btnEod.className = "px-2.5 py-1 rounded-lg text-xs font-bold transition text-gray-400 hover:text-gray-200 hover:bg-gray-800 flex items-center gap-1.5";

        if (typeof showHomeView === 'function') {
          showHomeView();
        }
      } else {
        if (scannerTab) scannerTab.classList.add('hidden');
        if (strategiesTab) strategiesTab.classList.remove('hidden');

        // Re-enable Strategy Dropdown in Strategies view
        if (btnStratSelector) {
          btnStratSelector.disabled = false;
          btnStratSelector.classList.remove('opacity-30', 'cursor-not-allowed', 'pointer-events-none');
          btnStratSelector.setAttribute('title', 'Switch Active Quantitative Strategy');
        }

        if (btnScanner) btnScanner.className = "px-2.5 py-1 rounded-lg text-xs font-bold transition text-gray-400 hover:text-gray-200 hover:bg-gray-800 flex items-center gap-1.5";
        if (btnEod) btnEod.className = "px-2.5 py-1 rounded-lg text-xs font-bold transition text-gray-400 hover:text-gray-200 hover:bg-gray-800 flex items-center gap-1.5";
        if (btnStrategies) btnStrategies.className = "px-2.5 py-1 rounded-lg text-xs font-bold transition bg-emerald-600 text-white shadow-sm flex items-center gap-1.5";

        // Select and display active strategy workspace
        selectStrategy(activeStrategyId);
        fetchStatus();
        loadStrategies();
      }
    }

    window.onload = function() {
      const urlParams = new URLSearchParams(window.location.search);
      if (urlParams.get('auth_success') === 'true') {
        showToast('🎉 Dhan Login Successful! Active trading session connected.', '⚡');
        window.history.replaceState({}, document.title, window.location.pathname);
      } else if (urlParams.get('auth_error')) {
        showToast(`Dhan Login Failed: ${urlParams.get('auth_error')}`, '❌');
        window.history.replaceState({}, document.title, window.location.pathname);
      }

      switchMainTab('scanner');
      updateSoundUI();
      initDesktopNotifications();
      renderMarketStatusUI(computeMarketStatusClient());
      fetchStatus();
      fetchTokenStatus();
      loadStrategies();
      fetchFeed();
      connectSSE();
      loadSt14Data();
      setInterval(fetchFeed, 4000);
      setInterval(loadStrategies, 10000);
      setInterval(() => {
        if (activeStrategyId === 'st14_bullish_ce') loadSt14Data();
      }, 5000);
      setInterval(pollLivePrices, 30000);
      setInterval(fetchTokenStatus, 30000);
      setInterval(updatePollerTimer, 1000);
      setInterval(updateCountdowns, 1000);
      setInterval(() => renderMarketStatusUI(computeMarketStatusClient()), 10000);
    };

  </script>

  <!-- Scanner Application Logic -->
  <script src="/static/scanner/app.js?v=3.8"></script>
</body>
</html>
"""
    return html.replace("__SIM_HEADER_BTN__", sim_header_btn).replace("__SIM_EMPTY_BTN__", sim_empty_btn)



__all__ = ["get_login_html", "get_dashboard_html"]
