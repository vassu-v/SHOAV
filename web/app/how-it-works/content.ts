export const howItWorksHtml = `

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
          <a href="/" class="nav-link">
            <span>Overview</span>
            <svg class="dropdown-caret" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M6 9l6 6 6-6"/></svg>
          </a>
          <div class="nav-horizontal-dropdown">
            <a href="/#packet" class="subnav-link">The Packet</a>
            <span class="subnav-sep">&bull;</span>
            <a href="/#quickstart" class="subnav-link">Quickstart</a>
            <span class="subnav-sep">&bull;</span>
            <a href="/#threats" class="subnav-link">What It Stops</a>
            <span class="subnav-sep">&bull;</span>
            <a href="/#simulator" class="subnav-link">Sandbox</a>
          </div>
        </div>

        <div class="nav-dropdown-wrapper">
          <a href="/how-it-works/" class="nav-link active">
            <span>How It Works</span>
            <svg class="dropdown-caret" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M6 9l6 6 6-6"/></svg>
          </a>
          <div class="nav-horizontal-dropdown">
            <a href="#pipeline" class="subnav-link">Pipeline</a>
            <span class="subnav-sep">&bull;</span>
            <a href="#stack" class="subnav-link">Tech Stack</a>
            <span class="subnav-sep">&bull;</span>
            <a href="#matrix" class="subnav-link">Comparison</a>
            <span class="subnav-sep">&bull;</span>
            <a href="#built-on" class="subnav-link">Built On</a>
          </div>
        </div>
      </nav>

      <div class="header-actions">
        <a href="https://github.com/Vassu-V/SHOAV" target="_blank" rel="noopener" class="text-link">GitHub</a>
        <a href="/#quickstart" class="btn-primary">Get started</a>
      </div>
    </div>
  </header>

  <!-- Hero -->
  <section class="hero-section" style="padding-bottom: 40px; border-bottom: 1px solid var(--rule);">
    <div class="container">
      <div class="hero-meta-row">
        <span>ARCHITECTURE &amp; DESIGN NOTES</span>
        <span>SOURCE: DOCS/DESIGN.MD</span>
      </div>
      <span class="kicker"><span class="kicker-num">01</span> Where the guard sits</span>
      <h1 class="hero-title" style="max-width: 760px;">Structure the page cannot argue with.</h1>
      <p class="hero-subtitle" style="max-width: 640px;">
        A model reading page text can be talked out of a warning by the page it is reading.
        Structural checks cannot: an element either sits under the click, or it does not. This page
        walks through the pipeline, the verdicts, and what each layer of the stack is responsible
        for.
      </p>
    </div>
  </section>

  <!-- Pipeline diagram -->
  <section id="pipeline" class="section-wrapper">
    <div class="container">
      <div class="section-head">
        <span class="kicker"><span class="kicker-num">02</span> Request path</span>
        <h2 class="section-title">Where the guard sits</h2>
        <p class="section-subtitle">
          Both channels an MCP result can use (<code>content[0].text</code> and
          <code>structuredContent</code>) carry the rewrite, because some clients read only one of
          them.
        </p>
      </div>

      <div class="panel" style="margin-bottom: 40px;">
        <div class="panel-body">
          <div class="terminal-body" style="min-height: 0;">
<pre><span class="comment">agent  -&gt;  POST /mcp tools/call
             |
             v
        gateway  -&gt;  session resolved
             |          EGRESS check   (click, drag)      abort with a reason if it fails
             |          tool handler runs
             |          INGRESS check  (observe, snapshot, find_elements, get_html)   rewrite the result
             v
        result returned to the agent, and a guard event goes to the live view</span></pre>
          </div>
        </div>
      </div>

      <div class="vector-table">
        <div class="vector-row" style="grid-template-columns: 32px 1fr;">
          <div class="vector-num">A</div>
          <div class="vector-main">
            <div class="vector-tag">INGRESS FILTER</div>
            <h3 class="vector-title">Audits what the agent is about to read</h3>
            <p class="vector-desc">
              Runs on observe, snapshot, find_elements, and get_html results. Checks computed styles
              and geometry, strips non-rendered text, and caps DOM size before the result reaches the
              planner. Verdicts: ALLOW / BLOCK / REWRITE.
            </p>
          </div>
        </div>
        <div class="vector-row" style="grid-template-columns: 32px 1fr;">
          <div class="vector-num">B</div>
          <div class="vector-main">
            <div class="vector-tag">EGRESS FILTER</div>
            <h3 class="vector-title">Verifies what a click will actually hit</h3>
            <p class="vector-desc">
              Runs on click and drag calls. Performs <code>elementFromPoint(x, y)</code> at the
              physical target coordinates before the action is dispatched. If the top element under
              that point is not the intended target or a child of it, the action is aborted with a
              reason.
            </p>
          </div>
        </div>
        <div class="vector-row" style="grid-template-columns: 32px 1fr;">
          <div class="vector-num">C</div>
          <div class="vector-main">
            <div class="vector-tag">COGNITIVE SKILL</div>
            <h3 class="vector-title">Advisory, in the agent itself</h3>
            <p class="vector-desc">
              Runs inside agents that already have their own browser, or alongside the MCP for
              language-level tricks: confirmshaming, fake urgency, trick wording. It can escalate
              suspicion. It cannot clear a structural block.
            </p>
          </div>
        </div>
      </div>
    </div>
  </section>

  <!-- Repository map -->
  <section id="map" class="section-wrapper">
    <div class="container">
      <div class="section-head">
        <span class="kicker"><span class="kicker-num">03</span> Where the code lives</span>
        <h2 class="section-title">Repository map</h2>
      </div>

      <div class="matrix-table-container">
        <table class="matrix-table">
          <thead>
            <tr><th>Path</th><th>What is there</th></tr>
          </thead>
          <tbody>
            <tr><td><code>guard/filters/</code></td><td>Deterministic ingress and egress rules, probes, session state, tests</td></tr>
            <tr><td><code>guard/connectors/</code></td><td>Payload adapters between the MCP and the filters</td></tr>
            <tr><td><code>server/</code></td><td>The SHOAV MCP server, live UI and start scripts</td></tr>
            <tr><td><code>e2e/fixtures/</code></td><td>Tiny synthetic pages for unit and end-to-end tests</td></tr>
            <tr><td><code>skill/</code></td><td>The agent skill, installed by <code>cli/</code></td></tr>
            <tr><td><code>docs/research/</code></td><td>Evidence base behind the detection targets</td></tr>
          </tbody>
        </table>
      </div>
    </div>
  </section>

  <!-- Tech stack -->
  <section id="stack" class="section-wrapper">
    <div class="container">
      <div class="section-head">
        <span class="kicker"><span class="kicker-num">04</span> Every layer, one reason each</span>
        <h2 class="section-title">Tech stack</h2>
      </div>

      <div class="matrix-table-container">
        <table class="matrix-table">
          <thead>
            <tr><th>Layer</th><th>Choice</th><th>Why</th></tr>
          </thead>
          <tbody>
            <tr>
              <td><strong>Guard core</strong></td>
              <td>Python, standard library only</td>
              <td>Pure functions over dicts. No browser, network, or I/O in the rules, so each rule is unit testable and cannot be reached by page content.</td>
            </tr>
            <tr>
              <td><strong>Connectors</strong></td>
              <td>Python, dict in and dict out</td>
              <td>Adapters between MCP payloads and filter inputs. No controller imports, so they test alone.</td>
            </tr>
            <tr>
              <td><strong>MCP server</strong></td>
              <td>Python 3.11+, FastAPI, uvicorn</td>
              <td>MCP over HTTP (JSON-RPC at <code>/mcp</code>). Hostable once, usable from any machine on the network.</td>
            </tr>
            <tr>
              <td><strong>State</strong></td>
              <td>SQLite, JSON and JSONL files</td>
              <td>Audit events, approvals, per-session timelines. All local, nothing uploaded.</td>
            </tr>
            <tr>
              <td><strong>Browser</strong></td>
              <td>Playwright 1.62, Chromium (visible)</td>
              <td>Real rendering is required for style, geometry, and hit tests.</td>
            </tr>
            <tr>
              <td><strong>Live view</strong></td>
              <td>Next.js, TypeScript, Tailwind, SSE</td>
              <td>A page per session, live and archived.</td>
            </tr>
            <tr>
              <td><strong>Skill</strong></td>
              <td>Markdown plus Node and Python audit scripts</td>
              <td>Portable to any agent that supports skills or instruction files, via an <code>npx</code> installer.</td>
            </tr>
            <tr>
              <td><strong>Tests</strong></td>
              <td>pytest, vitest, Playwright browser probes</td>
              <td>Detector authors and test authors are different people.</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </section>

  <!-- Comparison matrix -->
  <section id="matrix" class="section-wrapper">
    <div class="container">
      <div class="section-head">
        <span class="kicker"><span class="kicker-num">05</span> Why a deterministic core</span>
        <h2 class="section-title">Structure versus a prompt guard</h2>
        <p class="section-subtitle">
          A model can be talked out of a warning by the page it is reading. A structural check
          cannot: the page either has an element under the click, or it does not.
        </p>
      </div>

      <div class="matrix-table-container">
        <table class="matrix-table">
          <thead>
            <tr>
              <th>Vector</th>
              <th>Raw browser agent</th>
              <th>LLM prompt guard</th>
              <th>S.H.O.A.V.</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>Invisible clickjacking overlay</td>
              <td>No hit-test, fully exposed</td>
              <td>Blind &mdash; cannot see rendered geometry</td>
              <td class="win">elementFromPoint hit-test, blocked</td>
            </tr>
            <tr>
              <td>Hidden text / prompt injection</td>
              <td>Reads it, planner can be redirected</td>
              <td>Can itself be prompt-injected by the text it reads</td>
              <td class="win">Stripped by ingress before the planner sees it</td>
            </tr>
            <tr>
              <td>Phony close / cancel trigger</td>
              <td>Trusts the label on the element</td>
              <td>Inconsistent, depends on wording</td>
              <td class="win">Event-binding inspection, not label trust</td>
            </tr>
            <tr>
              <td>Pre-checked consent box</td>
              <td>Submits the form state as-is</td>
              <td>Inconsistent detection</td>
              <td class="win">Flagged at load and again at submit</td>
            </tr>
            <tr>
              <td>Can the check itself be argued with?</td>
              <td>&mdash;</td>
              <td>Yes, by the page it inspects</td>
              <td class="win">No &mdash; geometry and computed style, not language</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </section>

  <!-- Built on -->
  <section id="built-on" class="section-wrapper section-wrapper-last">
    <div class="container">
      <div class="section-head">
        <span class="kicker"><span class="kicker-num">06</span> Credit where it's owed</span>
        <h2 class="section-title">Built on Auto Browser</h2>
        <p class="section-subtitle">
          Auto Browser is MIT licensed and included here in reworked form with its license and
          credit. LiteAgent has no license, so none of its code is in this repository. OpenCode and
          agy are used as test clients, not carried code.
        </p>
      </div>
      <ul class="limits-list">
        <li>Runs natively with a visible Chromium; no Docker required.</li>
        <li>A live per-session view built in Next.js, with a timeline of every tool call.</li>
        <li>Real image screenshots plus a compact page snapshot tool with stable element references.</li>
        <li>Tool names adjusted for clients that reject dots.</li>
        <li>The guard, wired into the tool gateway through thin hooks and adapters.</li>
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
            <a href="#pipeline" class="footer-link">Request path</a>
            <a href="#stack" class="footer-link">Tech stack</a>
            <a href="#matrix" class="footer-link">Comparison matrix</a>
          </div>
        </div>

        <div>
          <h4 class="footer-col-title">Resources</h4>
          <div class="footer-links">
            <a href="/#quickstart" class="footer-link">Connect an agent</a>
            <a href="/#observability" class="footer-link">Live per-session view</a>
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
        <span>Alpha, under active development.</span>
      </div>
    </div>
  </footer>
`;
