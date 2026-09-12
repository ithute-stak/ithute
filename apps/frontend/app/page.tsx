const platformCapabilities = [
  {
    number: "01",
    title: "Identity",
    copy: "One secure Ithute identity layer for people, sessions, access and trusted service-to-service authentication.",
  },
  {
    number: "02",
    title: "Realtime",
    copy: "A dedicated realtime layer for live events, presence and dependable application communication.",
  },
  {
    number: "03",
    title: "Push",
    copy: "A central notification service designed for important alerts across web and mobile experiences.",
  },
  {
    number: "04",
    title: "Operations",
    copy: "Production routing, health checks and deployment are treated as part of the Ithute system itself.",
  },
];

export default function Home() {
  return (
    <main>
      <section className="hero">
        <div className="heroGlow heroGlowOne" />
        <div className="heroGlow heroGlowTwo" />
        <div className="shell heroShell">
          <header className="siteHeader">
            <a className="brand" href="/" aria-label="Ithute home">
              <span className="brandMark" aria-hidden="true">!</span>
              <span className="brandText">
                <strong>thute</strong>
                <small>Digital infrastructure</small>
              </span>
            </a>
            <nav className="nav" aria-label="Primary navigation">
              <a href="#platform">Platform</a>
              <a href="#principles">Principles</a>
              <a className="navButton" href="https://auth.ithute.co.ls/">Sign in</a>
            </nav>
          </header>

          <div className="heroGrid">
            <div className="heroCopy">
              <div className="statusPill"><span /> Built in Lesotho · engineered for dependable operations</div>
              <p className="eyebrow">ITHUTE</p>
              <h1>One focused platform.<br />One trusted foundation.</h1>
              <p className="heroLead">
                Ithute is a standalone digital infrastructure project for secure identity,
                realtime communication, notifications and production operations. No nested
                product applications. No shared frontend routing. One clear system boundary.
              </p>
              <div className="heroActions">
                <a className="primaryButton" href="#platform">Explore the platform <span aria-hidden="true">→</span></a>
                <a className="secondaryButton" href="https://auth.ithute.co.ls/">Open Ithute Auth</a>
              </div>
            </div>

            <div className="systemCard" aria-label="Ithute system status">
              <div className="systemCardTop">
                <div>
                  <span className="cardKicker">SYSTEM BOUNDARY</span>
                  <h2>Ithute is now its own project.</h2>
                </div>
                <span className="systemBadge">ITHUTE</span>
              </div>
              <div className="systemRows">
                <div className="systemRow"><span>Website</span><strong>ithute.co.ls</strong><i className="okDot" /></div>
                <div className="systemRow"><span>Identity</span><strong>auth.ithute.co.ls</strong><i className="okDot" /></div>
                <div className="systemRow"><span>Realtime</span><strong>realtime.ithute.co.ls</strong><i className="okDot" /></div>
                <div className="systemRow"><span>Notifications</span><strong>push.ithute.co.ls</strong><i className="okDot" /></div>
              </div>
              <p className="systemNote">Each public hostname has one deterministic Ithute upstream.</p>
            </div>
          </div>
        </div>
      </section>

      <section id="platform" className="section shell">
        <div className="sectionHeading">
          <div>
            <p className="eyebrow dark">CORE PLATFORM</p>
            <h2>A small, clear architecture that is easier to trust.</h2>
          </div>
          <p>
            Ithute keeps its shared infrastructure together while application projects stay
            in their own repositories, deployments and data boundaries.
          </p>
        </div>
        <div className="capabilityGrid">
          {platformCapabilities.map((item) => (
            <article className="capabilityCard" key={item.number}>
              <span className="capabilityNumber">{item.number}</span>
              <h3>{item.title}</h3>
              <p>{item.copy}</p>
            </article>
          ))}
        </div>
      </section>

      <section id="principles" className="principlesSection">
        <div className="shell principlesGrid">
          <div>
            <p className="eyebrow">OPERATING PRINCIPLES</p>
            <h2>Simple boundaries prevent complicated failures.</h2>
          </div>
          <div className="principleList">
            <div><span>01</span><p><strong>Deterministic routing.</strong> The Ithute domain can only resolve to the Ithute web service.</p></div>
            <div><span>02</span><p><strong>Independent applications.</strong> Other systems do not live inside this repository or share its frontend runtime.</p></div>
            <div><span>03</span><p><strong>Central identity, separate data.</strong> Authentication stays shared while application databases remain outside Ithute.</p></div>
            <div><span>04</span><p><strong>Production verification.</strong> Deployments check the rendered page and stylesheet assets before being accepted.</p></div>
          </div>
        </div>
      </section>

      <footer className="footer">
        <div className="shell footerInner">
          <div className="brand footerBrand">
            <span className="brandMark" aria-hidden="true">!</span>
            <span className="brandText"><strong>thute</strong><small>Lesotho</small></span>
          </div>
          <p>Secure digital infrastructure with a clear system boundary.</p>
          <span>© {new Date().getFullYear()} Ithute</span>
        </div>
      </footer>
    </main>
  );
}
