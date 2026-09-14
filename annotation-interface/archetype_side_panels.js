(() => {
  const archetypes = [
    {
      id: "explorer",
      name: "Explorer",
      short: "Freedom",
      inner: "Explore Spirituality",
      color: "#9bb83d",
      side: "left",
      text: "Explorer seeks freedom, discovery, movement, and self-definition beyond imposed boundaries. In games, this often appears in travel, adventure, survival, archaeology, open-world exploration, and characters who are defined by leaving the known world."
    },
    {
      id: "outlaw",
      name: "Outlaw",
      short: "Liberation",
      inner: "Leave Legacy",
      color: "#d4c80a",
      side: "left",
      text: "Outlaw resists authority, breaks rules, rejects imposed order, or attacks oppressive systems. This archetype may be heroic, criminal, comic, or destructive; the key feature is opposition to established control."
    },
    {
      id: "magician",
      name: "Magician",
      short: "Power",
      inner: "Leave Legacy",
      color: "#d79a16",
      side: "left",
      text: "Magician transforms reality, perception, identity, or systems. This may be literal magic, hacking, psychic power, occult knowledge, technological manipulation, or any role that changes the rules of the world."
    },
    {
      id: "hero",
      name: "Hero",
      short: "Mastery",
      inner: "Leave Legacy",
      color: "#cf7623",
      side: "left",
      text: "Hero is structured around courage, struggle, confrontation, endurance, and overcoming danger. The protagonist does not need to be morally perfect; the key is that the narrative or gameplay frames them through challenge and achievement."
    },
    {
      id: "lover",
      name: "Lover",
      short: "Intimacy",
      inner: "Pursue Connection",
      color: "#c84d53",
      side: "left",
      text: "Lover is driven by attachment, desire, beauty, devotion, intimacy, or emotional connection. This is not only romance: it can also describe protagonists whose main motivation is relational, aesthetic, sensual, or deeply personal."
    },
    {
      id: "jester",
      name: "Jester",
      short: "Enjoyment",
      inner: "Pursue Connection",
      color: "#bf2d75",
      side: "left",
      text: "Jester uses play, humor, irony, trickery, improvisation, or refusal of seriousness. Jester protagonists may be fools, pranksters, comic heroes, chaotic tricksters, or figures who expose the absurdity of social order."
    },
    {
      id: "everyman",
      name: "Everyman",
      short: "Belonging",
      inner: "Pursue Connection",
      color: "#934091",
      side: "right",
      text: "Everyman is ordinary, relatable, socially grounded, and often defined by survival, community, work, or everyday moral pressure. This is especially useful for non-heroic protagonists, civilians, workers, survivors, and reluctant participants."
    },
    {
      id: "caregiver",
      name: "Caregiver",
      short: "Service",
      inner: "Provide Structure",
      color: "#315fa4",
      side: "right",
      text: "Caregiver is motivated by protection, responsibility, repair, sacrifice, and care for another person or community. It often appears in parent-child plots, rescue structures, healing roles, and protagonists whose violence is framed as protection."
    },
    {
      id: "ruler",
      name: "Ruler",
      short: "Control",
      inner: "Provide Structure",
      color: "#1681b3",
      side: "right",
      text: "Ruler seeks order, control, leadership, law, command, or systemic power. In games this can describe kings, commanders, bosses, mayors, managers, strategists, and player roles built around governance or control."
    },
    {
      id: "creator",
      name: "Creator",
      short: "Innovation",
      inner: "Provide Structure",
      color: "#0797b5",
      side: "right",
      text: "Creator is defined by making, shaping, building, composing, inventing, or transforming material into form. It can describe artists and inventors, but also player roles in crafting, construction, sandbox, colony, and design systems."
    },
    {
      id: "innocent",
      name: "Innocent",
      short: "Safety",
      inner: "Explore Spirituality",
      color: "#198f88",
      side: "right",
      text: "Innocent seeks safety, trust, hope, simplicity, purity, or a world that still makes moral sense. In protagonists this can appear as vulnerability, optimism, naivety, or a desire to preserve goodness despite danger."
    },
    {
      id: "sage",
      name: "Sage",
      short: "Understanding",
      inner: "Explore Spirituality",
      color: "#0aa66f",
      side: "right",
      text: "Sage seeks truth, knowledge, interpretation, memory, investigation, or understanding. Detectives, scholars, hackers, scientists, witnesses, and puzzle-solving protagonists often carry Sage functions."
    }
  ];

  const css = `
    .side-archetypes {
      position: fixed;
      top: 50%;
      transform: translateY(-50%);
      display: flex;
      flex-direction: column;
      gap: 8px;
      z-index: 50;
      pointer-events: none;
    }

    .side-archetypes.left { left: 0; }
    .side-archetypes.right { right: 0; }

    .side-panel {
      --panel-color: #111827;
      --panel-width: 300px;
      --tab-width: 108px;
      position: relative;
      width: var(--panel-width);
      min-height: 56px;
      border: 0;
      padding: 0;
      margin: 0;
      background: transparent;
      pointer-events: auto;
      cursor: pointer;
      font: inherit;
      color: #fff;
      text-align: left;
      filter: drop-shadow(0 8px 18px rgba(0,0,0,.18));
      transition: transform .22s ease, filter .22s ease;
    }

    .side-archetypes.left .side-panel {
      transform: translateX(calc(-1 * (var(--panel-width) - var(--tab-width))));
    }

    .side-archetypes.right .side-panel {
      transform: translateX(calc(var(--panel-width) - var(--tab-width)));
    }

    .side-archetypes.left .side-panel.open,
    .side-archetypes.right .side-panel.open {
      transform: translateX(0);
      filter: drop-shadow(0 12px 26px rgba(0,0,0,.25));
    }

    /*
      Desktop/laptop only:
      hover gently reveals the panel, so the inner label
      such as "Provide Structure" or "Pursue Connection" becomes visible.
      On touch/mobile screens this rule is ignored.
    */
    @media (hover: hover) and (pointer: fine) {
      .side-archetypes.left .side-panel:hover,
      .side-archetypes.right .side-panel:hover {
        transform: translateX(0);
        filter: drop-shadow(0 12px 26px rgba(0,0,0,.25));
      }
    }

    .side-panel-inner {
      display: grid;
      min-height: 56px;
      background: var(--panel-color);
      overflow: hidden;
    }

    .side-archetypes.left .side-panel-inner {
      grid-template-columns: 1fr var(--tab-width);
      border-radius: 0 14px 14px 0;
    }

    .side-archetypes.left .side-content { order: 1; }
    .side-archetypes.left .side-tab { order: 2; }

    .side-archetypes.right .side-panel-inner {
      grid-template-columns: var(--tab-width) 1fr;
      border-radius: 14px 0 0 14px;
    }

    .side-archetypes.right .side-tab { order: 1; }
    .side-archetypes.right .side-content { order: 2; }

    .side-tab {
      min-height: 56px;
      padding: 8px 9px;
      display: flex;
      flex-direction: column;
      justify-content: center;
      background: rgba(0,0,0,.10);
      user-select: none;
      overflow: hidden;
    }

    .side-tab-name {
      display: block;
      font-size: 12px;
      line-height: 1.05;
      font-weight: 950;
      text-transform: uppercase;
      letter-spacing: .035em;
      white-space: nowrap;
    }

    .side-tab-short {
      display: block;
      margin-top: 3px;
      font-size: 9.5px;
      line-height: 1.05;
      font-weight: 850;
      opacity: .95;
      white-space: nowrap;
    }

    .side-content {
      padding: 10px 13px 11px;
      min-width: 0;
    }

    .side-title {
      margin: 0;
      font-size: 15px;
      line-height: 1.05;
      font-weight: 950;
      text-transform: uppercase;
      letter-spacing: .04em;
    }

    .side-inner {
      margin: 4px 0 0;
      font-size: 12px;
      line-height: 1.15;
      font-weight: 900;
      opacity: 1;
    }

    .side-detail {
      display: none;
      margin: 8px 0 0;
      font-size: 11px;
      line-height: 1.25;
      opacity: .96;
    }

    .side-panel.open .side-panel-inner {
      min-height: 138px;
    }

    .side-panel.open .side-detail {
      display: block;
    }

    .side-panel:focus-visible {
      outline: 4px solid #111827;
      outline-offset: 2px;
    }

    @media (max-width: 900px) {
      .side-panel {
        --panel-width: 260px;
        --tab-width: 92px;
        min-height: 48px;
      }

      .side-panel-inner { min-height: 48px; }

      .side-tab {
        min-height: 48px;
        padding: 6px 7px;
      }

      .side-tab-name { font-size: 10.5px; }
      .side-tab-short { font-size: 8.5px; }

      .side-content { padding: 8px 10px 9px; }
      .side-title { font-size: 13px; }
      .side-inner { font-size: 10.5px; }
      .side-detail { font-size: 10px; }
    }

    @media (max-width: 620px) {
      .side-archetypes {
        top: auto;
        transform: none;
        display: block;
        gap: 0;
        pointer-events: none;
      }

      .side-panel {
        position: fixed;
        --panel-width: 230px;
        --tab-width: 78px;
        min-height: 42px;
      }

      .side-archetypes.left .side-panel {
        left: 0;
        transform: translateX(calc(-1 * (var(--panel-width) - var(--tab-width))));
      }

      .side-archetypes.right .side-panel {
        right: 0;
        transform: translateX(calc(var(--panel-width) - var(--tab-width)));
      }

      .side-archetypes.left .side-panel.open,
      .side-archetypes.right .side-panel.open {
        transform: translateX(0);
      }

      /* Mobile: side panels remain side panels, but are stacked from the bottom. */
      .side-archetypes.left .side-panel:nth-child(6),
      .side-archetypes.right .side-panel:nth-child(6) {
        bottom: calc(env(safe-area-inset-bottom) + 28px);
        top: auto;
      }

      .side-archetypes.left .side-panel:nth-child(5),
      .side-archetypes.right .side-panel:nth-child(5) {
        bottom: calc(env(safe-area-inset-bottom) + 76px);
        top: auto;
      }

      .side-archetypes.left .side-panel:nth-child(4),
      .side-archetypes.right .side-panel:nth-child(4) {
        bottom: calc(env(safe-area-inset-bottom) + 124px);
        top: auto;
      }

      .side-archetypes.left .side-panel:nth-child(3),
      .side-archetypes.right .side-panel:nth-child(3) {
        bottom: calc(env(safe-area-inset-bottom) + 172px);
        top: auto;
      }

      .side-archetypes.left .side-panel:nth-child(2),
      .side-archetypes.right .side-panel:nth-child(2) {
        bottom: calc(env(safe-area-inset-bottom) + 220px);
        top: auto;
      }

      .side-archetypes.left .side-panel:nth-child(1),
      .side-archetypes.right .side-panel:nth-child(1) {
        bottom: calc(env(safe-area-inset-bottom) + 268px);
        top: auto;
      }

      .side-panel-inner { min-height: 42px; }

      .side-tab {
        min-height: 42px;
        padding: 5px 6px;
      }

      .side-tab-name { font-size: 9px; }
      .side-tab-short { font-size: 7.5px; }

      .side-panel.open {
        width: min(var(--panel-width), 86vw);
      }
    }
  `;

  const style = document.createElement("style");
  style.textContent = css;
  document.head.appendChild(style);

  const left = document.createElement("div");
  left.className = "side-archetypes left";
  left.setAttribute("aria-label", "Left archetype descriptions");

  const right = document.createElement("div");
  right.className = "side-archetypes right";
  right.setAttribute("aria-label", "Right archetype descriptions");

  function makePanel(a) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "side-panel";
    btn.style.setProperty("--panel-color", a.color);
    btn.dataset.archetype = a.id;
    btn.setAttribute("aria-expanded", "false");
    btn.setAttribute("aria-label", `${a.name}: ${a.short}. ${a.inner}.`);

    btn.innerHTML = `
      <div class="side-panel-inner">
        <div class="side-tab">
          <span class="side-tab-name">${a.name}</span>
          <span class="side-tab-short">${a.short}</span>
        </div>
        <div class="side-content">
          <p class="side-title">${a.name}</p>
          <p class="side-inner">${a.inner}</p>
          <p class="side-detail">${a.text}</p>
        </div>
      </div>
    `;

    btn.addEventListener("click", (event) => {
      event.stopPropagation();
      const isOpen = btn.classList.toggle("open");
      btn.setAttribute("aria-expanded", isOpen ? "true" : "false");
    });

    return btn;
  }

  archetypes.forEach(a => {
    if (a.side === "left") left.appendChild(makePanel(a));
    else right.appendChild(makePanel(a));
  });

  document.body.appendChild(left);
  document.body.appendChild(right);

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      document.querySelectorAll(".side-panel.open").forEach(panel => {
        panel.classList.remove("open");
        panel.setAttribute("aria-expanded", "false");
      });
    }
  });
})();
