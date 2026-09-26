export const homeHtml = `

  <!-- Site Header -->
  <header class="site-header">
    <div class="container">
      <a href="/" class="logo-brand">
        <span>S.H.O.A.V.</span>
        <span class="logo-rule"></span>
        <span class="logo-sub">AI bodyguard</span>
      </a>

      <nav class="nav-links">
        <div class="nav-dropdown-wrapper">
          <a href="/" class="nav-link active">
            <span>Overview</span>
            <svg class="dropdown-caret" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M6 9l6 6 6-6"/></svg>
          </a>
          <div class="nav-horizontal-dropdown">
            <a href="#packet" class="subnav-link">The Packet</a>
            <span class="subnav-sep">&bull;</span>
            <a href="#quickstart" class="subnav-link">Quickstart</a>
            <span class="subnav-sep">&bull;</span>
            <a href="#threats" class="subnav-link">What It Stops</a>
            <span class="subnav-sep">&bull;</span>
            <a href="#simulator" class="subnav-link">Sandbox</a>
          </div>
        </div>

        <div class="nav-dropdown-wrapper">
          <a href="/how-it-works/" class="nav-link">
            <span>How It Works</span>
            <svg class="dropdown-caret" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M6 9l6 6 6-6"/></svg>
          </a>
          <div class="nav-horizontal-dropdown">
            <a href="/how-it-works/#pipeline" class="subnav-link">Pipeline</a>
            <span class="subnav-sep">&bull;</span>
            <a href="/how-it-works/#stack" class="subnav-link">Tech Stack</a>
            <span class="subnav-sep">&bull;</span>
            <a href="/how-it-works/#matrix" class="subnav-link">Comparison</a>
            <span class="subnav-sep">&bull;</span>
            <a href="/how-it-works/#built-on" class="subnav-link">Built On</a>
          </div>
        </div>
      </nav>

      <div class="header-actions">
        <a href="https://github.com/Vassu-V/SHOAV" target="_blank" rel="noopener" class="text-link">GitHub</a>
        <a href="#quickstart" class="btn-primary">Get started</a>
      </div>
    </div>
  </header>

  <!-- Hero -->
  <section class="hero-section">
    <div class="container">
      <div class="hero-meta-row">
        <span>OPEN SOURCE / ALPHA</span>
        <span>BUILT ON AUTO BROWSER / MIT</span>
      </div>

      <div class="hero-grid">
        <div class="hero-content">
          <span class="kicker"><span class="kicker-num">01</span> A framework, not a plugin</span>
          <h1 class="hero-title">A seatbelt for web agents.</h1>
          <p class="hero-fullform">S.H.O.A.V. &mdash; Shield for Hostile Operations &amp; Agent Vulnerability</p>

          <p class="hero-subtitle">
            <strong>S.H.O.A.V.</strong> is a framework to think about and secure agents,
            built for every agent, not bolted onto one. Clone it to run the full guard,
            install the skill so any agent reasons about dark patterns on its own, or
            point one MCP client at the browser it already needs &mdash; nobody is left outside.
          </p>

          <div class="hero-ctas">
            <a href="#quickstart" class="btn-primary">Get started</a>
            <a href="#packet" class="text-link">Read the packet &rarr;</a>
          </div>

          <div class="hero-command">
            <code>git clone https://github.com/Vassu-V/SHOAV.git</code>
            <button class="icon-btn" title="Copy command" data-copy-text="git clone https://github.com/Vassu-V/SHOAV.git">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>
            </button>
          </div>
        </div>

        <!-- HUD panel: instrument window, not a glass card -->
        <div class="hero-visualizer-container">
          <div class="panel">
            <div class="panel-header">
              <span class="panel-caption">FIG. 1 / EGRESS HIT-TEST / SESSION LOG</span>
              <span class="mode-tag">MODE: ENFORCE</span>
            </div>

            <div class="panel-body">
              <div class="mock-strip">
                <div class="mock-strip-label">
                  target: https://demo-site.test/download
                </div>
                <div class="mock-target-wrap">
                  <button class="mock-target-button">Download whitepaper (.pdf)</button>
                  <div class="mock-overlay-trap" data-label="z-index 99999"></div>
                </div>
              </div>

              <div class="log-lines">
                <div class="log-line">
                  <span>click dispatched at (240, 180)</span>
                  <span class="verdict-marker block">BLOCK</span>
                </div>
                <div class="log-line">
                  <span>elementFromPoint(240, 180) &ne; #download-btn</span>
                  <span class="verdict-marker allow">HIT-TEST</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </section>

  <!-- Compatibility strip -->
  <section class="trust-strip">
    <div class="container">
      <span class="trust-line">THREE WAYS IN: git clone the guard &middot; npx the skill &middot; point any MCP client at the browser</span>
    </div>
  </section>

  <!-- The Packet: inverted paper section -->
  <section id="packet" class="paper-section">
    <div class="container">
      <div class="section-head">
        <span class="kicker paper"><span class="kicker-num">02</span> First, the packet</span>
        <h2 class="section-title paper">The design notes, not a pitch deck</h2>
        <p class="section-subtitle paper">
          Everything below is drawn from the design document and README that already describe this
          project. No invented numbers, no placeholder metrics &mdash; the packet is the source.
        </p>
      </div>

      <div class="packet-block">
        <div class="packet-main">
          <div class="packet-label">docs/DESIGN.md</div>
          <h3 class="packet-title">Tool-First Agent Diagnostic Design</h3>
          <p class="packet-desc">
            We were asked to build a middle layer between the agent and the web. A plugin locks the
            defense to one carrier. A proxy in front of an agent's own browser assumes a browser most
            agents don't have. So the browser itself is the product: one MCP server owns the browser,
            and any agent that can call an MCP tool gets a real Chromium with the guard already in
            the path.
          </p>
          <div class="packet-facts">
            <div><strong>Two layers</strong>deterministic guard, advisory skill</div>
            <div><strong>Four verdicts</strong>ALLOW / REWRITE / ESCALATE / BLOCK</div>
            <div><strong>One rule</strong>a model may raise suspicion, never lower it</div>
          </div>
        </div>
        <div class="packet-toc">
          <div class="packet-toc-title">Contents</div>
          <ol>
            <li>Why a tool, not a plugin</li>
            <li>Two layers: deterministic guard, cognitive skill</li>
            <li>What the guard covers</li>
            <li>Where the guard sits in the pipeline</li>
            <li>Verdicts and what the agent gets</li>
            <li>Honest limits</li>
          </ol>
        </div>
      </div>
    </div>
  </section>

  <!-- Creation & the idea -->
  <section id="idea" class="section-wrapper">
    <div class="container">
      <div class="section-head">
        <span class="kicker"><span class="kicker-num">03</span> Then, the idea</span>
        <h2 class="section-title">Why the browser had to be the product</h2>
        <p class="section-subtitle">
          People avoid sketchy pop-ups and pre-ticked boxes by looking at the page. Web-browsing
          agents don't look &mdash; they read the DOM or the pixels, and hostile pages are built to
          exploit exactly that split.
        </p>
      </div>

      <div class="program-list">
        <div class="program-row">
          <div class="program-time"><span class="phase-num">01</span>the problem</div>
          <div>
            <h3 class="program-heading">The awareness split</h3>
            <p class="program-body">
              Hidden text tells the agent what to do. Invisible layers sit over the button it meant
              to press. Boxes are ticked before it even arrives. A human notices; an agent that reads
              structure or pixels does not.
            </p>
          </div>
        </div>

        <div class="program-row">
          <div class="program-time"><span class="phase-num">02</span>the shape</div>
          <div>
            <h3 class="program-heading">A tool, not a plugin</h3>
            <p class="program-body">
              Most agents have no browser and cannot be extended, and the ones that can are each
              different. So we put the guard where every agent has to pass &mdash; at the browser
              itself. Claude, agy, OpenCode, or any MCP client can use it, hosted once for anyone on
              the network.
            </p>
          </div>
        </div>

        <div class="program-row">
          <div class="program-time"><span class="phase-num">03</span>the core</div>
          <div>
            <h3 class="program-heading">Deterministic, not persuaded</h3>
            <p class="program-body">
              The checks look at structure that page text cannot argue with: what is under the
              click, what is visible, what a form will submit. A model may advise on top of that,
              and it can only raise suspicion, never clear an action.
            </p>
          </div>
        </div>

        <div class="program-row">
          <div class="program-time"><span class="phase-num">04</span>the rest</div>
          <div>
            <h3 class="program-heading">A skill for agents with their own browser</h3>
            <p class="program-body">
              Agents that already have a browser can run the S.H.O.A.V. skill instead. The skill is
              advice: it teaches the agent what confirmshaming, fake urgency, and trick wording look
              like. The MCP is enforcement. They are meant to be used together.
            </p>
          </div>
        </div>

        <div class="program-row">
          <div class="program-time"><span class="phase-num">05</span>the base</div>
          <div>
            <h3 class="program-heading">Built on Auto Browser, reworked</h3>
            <p class="program-body">
              Auto Browser (MIT) supplied the browser control and MCP transport. From there:
            </p>
            <ul>
              <li>Runs natively with a visible Chromium, no Docker required</li>
              <li>A live per-session view with a timeline of every tool call</li>
              <li>Real image screenshots plus a compact page snapshot with stable element references</li>
              <li>The guard, wired into the tool gateway behind an off / observe / enforce switch</li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  </section>

  <!-- Verdicts: single ruled row, not tiles -->
  <section id="verdicts" class="section-wrapper">
    <div class="container">
      <div class="section-head">
        <span class="kicker"><span class="kicker-num">04</span> Every check ends in one of four states</span>
        <h2 class="section-title">Verdicts</h2>
        <p class="section-subtitle">
          Modes: off (no guard), observe (checks run and are logged), enforce (rewrites and blocks
          apply). Default is off. If a filter throws, the call fails open unless the fail policy is
          set closed.
        </p>
      </div>

      <div class="verdict-row">
        <div class="verdict-cell">
          <span class="verdict-marker allow">ALLOW</span>
          <p class="verdict-cell-desc">Nothing found. The agent gets the normal result.</p>
        </div>
        <div class="verdict-cell">
          <span class="verdict-marker rewrite">REWRITE</span>
          <p class="verdict-cell-desc">Something removed or flagged. The result comes back with the
            dangerous part stripped and a short note on what was removed.</p>
        </div>
        <div class="verdict-cell">
          <span class="verdict-marker escalate">ESCALATE</span>
          <p class="verdict-cell-desc">Suspicious but not provably hostile. In enforce mode the
            action is held; the agent is asked to re-observe or request a human.</p>
        </div>
        <div class="verdict-cell">
          <span class="verdict-marker block">BLOCK</span>
          <p class="verdict-cell-desc">Physical obstruction or a flood. The action does not happen,
            with a plain reason given.</p>
        </div>
      </div>
    </div>
  </section>

  <!-- What it stops: ruled table -->
  <section id="threats" class="section-wrapper">
    <div class="container">
      <div class="section-head">
        <span class="kicker"><span class="kicker-num">05</span> Targets are drawn from research, still unconfirmed</span>
        <h2 class="section-title">What the guard covers</h2>
        <p class="section-subtitle">
          Out of scope by design: cart sneaking (site specific, cannot be hardcoded), language-level
          dark patterns (that's the skill's job), and text drawn inside images.
        </p>
      </div>

      <div class="vector-table">
        <div class="vector-row">
          <div class="vector-num">01</div>
          <div class="vector-main">
            <div class="vector-tag">INGRESS &middot; HIDDEN TEXT INJECTION</div>
            <h3 class="vector-title">Text the agent should never read</h3>
            <p class="vector-desc">
              display:none, opacity 0, font-size 0, off-screen positioning, zero-width characters,
              or text inside HTML comments &mdash; used to jailbreak the agent's planner.
            </p>
          </div>
          <div class="vector-defense">
            <span class="vector-defense-label">Defense</span>
            computed style and geometry checks plus a Unicode and keyword
            scan. The hidden text is removed before the agent reads the page.
          </div>
        </div>

        <div class="vector-row">
          <div class="vector-num">02</div>
          <div class="vector-main">
            <div class="vector-tag">EGRESS &middot; CLICKJACKING OVERLAY</div>
            <h3 class="vector-title">A transparent element over the real target</h3>
            <p class="vector-desc">
              A stacked or transparent layer sits above the button the agent intends to press,
              redirecting the click somewhere else.
            </p>
          </div>
          <div class="vector-defense">
            <span class="vector-defense-label">Defense</span>
            <code>elementFromPoint</code> at the target's centre. If the
            top element is not the target or one of its children, the click is treated as a decoy.
          </div>
        </div>

        <div class="vector-row">
          <div class="vector-num">03</div>
          <div class="vector-main">
            <div class="vector-tag">INGRESS &amp; EGRESS &middot; PRE-CHECKED CONSENT</div>
            <h3 class="vector-title">A marketing or sharing box, already ticked</h3>
            <p class="vector-desc">
              The default-effect trap: a box is pre-checked so that not touching it counts as
              consent.
            </p>
          </div>
          <div class="vector-defense">
            <span class="vector-defense-label">Defense</span>
            form state captured at load, flagged at read time, and flagged
            again if the agent submits without touching it.
          </div>
        </div>

        <div class="vector-row">
          <div class="vector-num">04</div>
          <div class="vector-main">
            <div class="vector-tag">INGRESS &middot; CONTEXT FLOODING</div>
            <h3 class="vector-title">A DOM built to overload the planner</h3>
            <p class="vector-desc">
              A huge, repeated DOM or rapid meaningless mutation, aimed at blowing out the agent's
              context window rather than deceiving a person.
            </p>
          </div>
          <div class="vector-defense">
            <span class="vector-defense-label">Defense</span>
            node and text budgets, plus a mutation-rate check on the page.
          </div>
        </div>
      </div>
    </div>
  </section>

  <!-- Quickstart -->
  <section id="quickstart" class="section-wrapper">
    <div class="container">
      <div class="section-head">
        <span class="kicker"><span class="kicker-num">06</span> Three ways in, nobody bolted on</span>
        <h2 class="section-title">Set up the framework</h2>
        <p class="section-subtitle">
          Clone it to run the whole guard, install the skill so any agent reasons about traps
          on its own, or just wire one MCP client to the browser. Pick one, or all three.
        </p>
      </div>

      <div class="setup-path-grid">
        <div class="setup-path">
          <span class="setup-path-num">01</span>
          <h3 class="setup-path-title">Clone the framework</h3>
          <p class="setup-path-desc">The full guard: deterministic ingress/egress filters, the MCP gateway, and the live session view. Run it once, it protects every agent that connects.</p>
          <div class="setup-path-command">
            <code>git clone https://github.com/Vassu-V/SHOAV.git</code>
            <button class="icon-btn" title="Copy command" data-copy-text="git clone https://github.com/Vassu-V/SHOAV.git">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>
            </button>
          </div>
        </div>

        <div class="setup-path">
          <span class="setup-path-num">02</span>
          <h3 class="setup-path-title">Install the skill</h3>
          <p class="setup-path-desc">For agents that already have their own browser and can't take an MCP. Advisory only, but it teaches the agent the same dark-pattern vigilance the guard enforces.</p>
          <div class="setup-path-command">
            <code>npx github:vassu-v/SHOAV</code>
            <button class="icon-btn" title="Copy command" data-copy-text="npx github:vassu-v/SHOAV">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>
            </button>
          </div>
        </div>

        <div class="setup-path">
          <span class="setup-path-num">03</span>
          <h3 class="setup-path-title">Point an MCP client</h3>
          <p class="setup-path-desc">Already running the guard? Any MCP client &mdash; agy, Claude Desktop, Cursor, OpenCode &mdash; can connect to the same running gateway over one HTTP endpoint.</p>
          <div class="setup-path-command">
            <code>agy mcp add auto-browser http://127.0.0.1:18500/mcp</code>
            <button class="icon-btn" title="Copy command" data-copy-text="agy mcp add --type http auto-browser http://127.0.0.1:18500/mcp">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>
            </button>
          </div>
        </div>
      </div>

      <div class="panel panel-wide" style="margin-top: 40px;">
        <div class="panel-header">
          <div class="terminal-tabs">
            <button class="term-tab active" data-lang="agy">Antigravity (agy)</button>
            <button class="term-tab" data-lang="claude">Claude Desktop</button>
            <button class="term-tab" data-lang="cursor">Cursor</button>
            <button class="term-tab" data-lang="python">Python</button>
          </div>
          <button class="icon-btn icon-btn-labeled" id="copyCliBtn" data-target="cliCodeDisplay">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>
            <span>Copy</span>
          </button>
        </div>
        <div class="panel-body terminal-body">
          <pre><code id="cliCodeDisplay"><span class="comment"># start the MCP (guard mode: off, observe or enforce)</span>
<span class="cmd-prefix">powershell</span> -ExecutionPolicy Bypass -File server\\scripts\\start-local.ps1 <span class="cmd-flag">-Port</span> 18500 <span class="cmd-flag">-Background</span> <span class="cmd-flag">-Guard</span> enforce

<span class="comment"># then point agy at it</span>
<span class="cmd-prefix">agy</span> mcp add <span class="cmd-flag">--type</span> http auto-browser <span class="cmd-url">http://127.0.0.1:18500/mcp</span></code></pre>
        </div>
      </div>
    </div>
  </section>

  <!-- Live HUD -->
  <section id="observability" class="section-wrapper">
    <div class="container">
      <div class="ui-showcase-grid">
        <div class="ui-showcase-text">
          <span class="kicker"><span class="kicker-num">07</span> What the human sees</span>
          <h2 class="section-title">A link for every session</h2>
          <p class="section-subtitle">
            Every agent session gets an id and a live view: each tool call with its phase, arguments
            and result, the latest screenshot, and an archive after the session ends. Guard events
            appear as markers on the tool rows.
          </p>

          <div class="feature-list">
            <div class="feature-item">
              <span class="feature-num">01</span>
              <div>
                <h3 class="feature-title">Mathematical hit-testing</h3>
                <p class="feature-desc"><code>document.elementFromPoint</code> at the physical click
                  coordinates, checked before the action is dispatched.</p>
              </div>
            </div>

            <div class="feature-item">
              <span class="feature-num">02</span>
              <div>
                <h3 class="feature-title">Guard events on the timeline</h3>
                <p class="feature-desc">Verdicts appear as markers on each tool row, with the reason
                  and findings visible when expanded.</p>
              </div>
            </div>

            <div class="feature-item">
              <span class="feature-num">03</span>
              <div>
                <h3 class="feature-title">Native, visible Chromium</h3>
                <p class="feature-desc">No Docker required. A real, headed browser you can watch
                  while the agent works.</p>
              </div>
            </div>
          </div>
        </div>

        <!-- Dashboard sketch -->
        <div class="panel">
          <div class="panel-header">
            <span class="verdict-marker allow">SESSION ACTIVE</span>
            <span class="panel-caption">/live/sess-9941a</span>
          </div>

          <div class="dashboard-viewport">
            <div class="live-stream-box">
              <span class="verdict-marker block" style="margin-bottom: 8px; display: inline-flex;">LIVE</span>
              <div class="bounding-box-target">
                #submit-order (safe)
              </div>
            </div>

            <div class="live-action-feed">
              <div class="feed-entry">
                <div class="feed-verb">navigate</div>
                <div class="feed-target">-&gt; https://store.test</div>
                <div class="feed-note">ingress audit: clean</div>
              </div>
              <div class="feed-entry">
                <div class="feed-verb feed-verb-block">click</div>
                <div class="feed-target">-&gt; .popup-close</div>
                <div class="feed-note">blocked: adversarial form trigger</div>
              </div>
              <div class="feed-entry">
                <div class="feed-verb">observe</div>
                <div class="feed-target">-&gt; #order-summary</div>
                <div class="feed-note">sanitized 2 hidden injections</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </section>

  <!-- Simulator -->
  <section id="simulator" class="section-wrapper">
    <div class="container">
      <div class="section-head">
        <span class="kicker"><span class="kicker-num">08</span> Side by side</span>
        <h2 class="section-title">Attack sandbox</h2>
        <p class="section-subtitle">
          Toggle a scenario to compare a raw agent against one behind the guard. This is a
          demonstration of the design, not a benchmark result.
        </p>
      </div>

      <div class="panel panel-wide">
        <div class="panel-header sim-controls-bar">
          <div class="sim-attack-selector">
            <button class="sim-attack-btn active" data-attack="clickjack">01 Clickjacking overlay</button>
            <button class="sim-attack-btn" data-attack="fakeclose">02 Phony close trap</button>
            <button class="sim-attack-btn" data-attack="promptinject">03 Hidden text injection</button>
            <button class="sim-attack-btn" data-attack="freetrial">04 Pre-checked consent</button>
          </div>
        </div>

        <div class="panel-body">
          <div id="simMockPage" style="margin-bottom: 20px;">
            <div class="mock-strip" style="margin-bottom: 0;">
              <div class="mock-target-wrap" style="display: block;">
                <button class="mock-target-button">Download free PDF</button>
                <div class="mock-overlay-trap" data-label="transparent overlay, z-index 999999"></div>
              </div>
            </div>
          </div>

          <div class="sim-stage-grid">
            <div class="sim-terminal-pane pane-fail">
              <div class="sim-pane-header">
                <span class="sim-pane-title fail">Raw agent</span>
                <span class="sim-pane-meta">no hit-testing</span>
              </div>
              <div class="sim-log-content" id="simRawLog">
                <div class="log-danger">[action] click at (185, 340)</div>
                <div class="log-dim">target intended: #download-btn</div>
                <div class="log-danger">physical event intercepted by transparent iframe.ad-hijack</div>
                <div class="log-dim">outcome: unintended download initiated</div>
                <div class="log-danger log-strong">status: compromised</div>
              </div>
            </div>

            <div class="sim-terminal-pane pane-safe">
              <div class="sim-pane-header">
                <span class="sim-pane-title success">S.H.O.A.V. guarded</span>
                <span class="sim-pane-meta">deterministic</span>
              </div>
              <div class="sim-log-content" id="simShoavLog">
                <div class="log-ink">[egress audit] target coordinates (185, 340)</div>
                <div class="log-dim">executing elementFromPoint(185, 340)</div>
                <div class="log-ink">mismatch: expected button#download-btn, found iframe.ad-hijack</div>
                <div class="log-ink log-strong">verdict: BLOCK &mdash; clickjacking attempt</div>
                <div class="log-ink log-strong">status: protected, action held</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </section>

  <!-- Honest limits -->
  <section id="limits" class="section-wrapper section-wrapper-last">
    <div class="container">
      <div class="section-head">
        <span class="kicker"><span class="kicker-num">09</span> Said plainly</span>
        <h2 class="section-title">Honest limits</h2>
      </div>
      <ul class="limits-list">
        <li>Keyword lists are pattern matching, not understanding. A paraphrased injection can pass the deterministic layer.</li>
        <li>Thresholds are heuristics until there is attack and benign data to tune them against.</li>
        <li>Iframes and Shadow DOM are not handled by the hit test.</li>
        <li>Only the MCP path is guarded. Other callers of the browser service are not.</li>
        <li>Text inside images is out of reach, and a page that changes between our check and the click can slip through a small window.</li>
      </ul>
    </div>
  </section>

  <!-- Site Footer -->
  <footer class="site-footer">
    <div class="container">
      <div class="footer-grid">
        <div>
          <div class="logo-brand">
            <span>S.H.O.A.V.</span>
          </div>
          <p class="footer-tagline">
            Shield for Hostile Operations &amp; Agent Vulnerability. Open source, alpha. A deterministic
            guard for AI agents that browse.
          </p>
        </div>

        <div>
          <h4 class="footer-col-title">Architecture</h4>
          <div class="footer-links">
            <a href="/how-it-works/" class="footer-link">How it works</a>
            <a href="/how-it-works/#pipeline" class="footer-link">Filter pipeline</a>
            <a href="/how-it-works/#matrix" class="footer-link">Comparison matrix</a>
          </div>
        </div>

        <div>
          <h4 class="footer-col-title">Resources</h4>
          <div class="footer-links">
            <a href="#quickstart" class="footer-link">Connect an agent</a>
            <a href="#observability" class="footer-link">Live per-session view</a>
            <a href="https://github.com/Vassu-V/SHOAV" target="_blank" rel="noopener" class="footer-link">GitHub repository</a>
          </div>
        </div>

        <div>
          <h4 class="footer-col-title">Team</h4>
          <div class="footer-links">
            <a href="https://github.com/Vassu-V" target="_blank" rel="noopener" class="footer-link">Vassu-V</a>
            <a href="https://github.com/str-VaibhavThakkar" target="_blank" rel="noopener" class="footer-link">str-VaibhavThakkar</a>
          </div>
        </div>
      </div>

      <div class="footer-bottom">
        <span>&copy; 2026 S.H.O.A.V. Open source under MIT license.</span>
        <span>No agents were tricked into a free trial during the making of this project.</span>
      </div>
    </div>
  </footer>
`;
