(() => {
  'use strict';

  const VISIBLE_COUNT = 11;
  const STEP = 6;
  const STORAGE_KEY = 'icids17_demo_archetype_current_index';

  let characters = [];
  let currentIndex = 0;
  let windowStart = 0;
  let root = null;
  let track = null;
  let countLabel = null;

  const css = `
    .bottom-character-nav {
      position: fixed;
      left: 50%;
      bottom: 10px;
      transform: translateX(-50%);
      width: min(96vw, 1180px);
      height: 78px;
      display: grid;
      grid-template-columns: 42px 1fr 42px;
      align-items: center;
      gap: 8px;
      padding: 8px 10px;
      border-radius: 24px;
      background: rgba(255,255,255,.82);
      backdrop-filter: blur(14px) saturate(1.15);
      -webkit-backdrop-filter: blur(14px) saturate(1.15);
      border: 1px solid rgba(31,35,40,.10);
      box-shadow: 0 18px 38px rgba(0,0,0,.18);
      z-index: 44;
    }
    .bottom-character-nav::before,
    .bottom-character-nav::after {
      content: "";
      position: absolute;
      top: 8px;
      bottom: 8px;
      width: 46px;
      pointer-events: none;
      z-index: 2;
    }
    .bottom-character-nav::before {
      left: 52px;
      background: linear-gradient(90deg, rgba(255,255,255,.92), rgba(255,255,255,0));
    }
    .bottom-character-nav::after {
      right: 52px;
      background: linear-gradient(270deg, rgba(255,255,255,.92), rgba(255,255,255,0));
    }
    .bottom-nav-track {
      min-width: 0;
      height: 100%;
      display: grid;
      grid-template-columns: repeat(11, minmax(0, 1fr));
      gap: 7px;
      align-items: stretch;
    }
    .bottom-nav-card {
      position: relative;
      min-width: 0;
      border: 0;
      border-radius: 16px;
      padding: 8px 7px 7px;
      background: #fff;
      color: #1f2328;
      box-shadow: 0 7px 17px rgba(0,0,0,.10);
      cursor: pointer;
      overflow: hidden;
      text-align: left;
      font: inherit;
      transform: translateY(0) scale(1);
      transition: transform .18s ease, box-shadow .18s ease, background .18s ease, filter .18s ease;
    }
    .bottom-nav-card::before {
      content: "";
      position: absolute;
      left: 0;
      right: 0;
      top: 0;
      height: 4px;
      background: linear-gradient(90deg, rgba(155,184,61,.85), rgba(49,95,164,.85), rgba(191,45,117,.85));
      opacity: .62;
    }
    .bottom-nav-card.is-current {
      background: #111827;
      color: #fff;
      box-shadow: 0 12px 26px rgba(0,0,0,.24);
    }
    .bottom-nav-card.is-current::before { opacity: 1; }
    .bottom-nav-index {
      display: block;
      font-size: 10px;
      line-height: 1;
      font-weight: 950;
      color: #6b7280;
      margin-bottom: 5px;
    }
    .bottom-nav-card.is-current .bottom-nav-index { color: rgba(255,255,255,.72); }
    .bottom-nav-name {
      display: block;
      font-size: 12px;
      line-height: 1.02;
      font-weight: 950;
      letter-spacing: -.02em;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .bottom-nav-game {
      display: block;
      margin-top: 4px;
      font-size: 9px;
      line-height: 1.05;
      font-weight: 800;
      color: #6b7280;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .bottom-nav-card.is-current .bottom-nav-game { color: rgba(255,255,255,.72); }
    .bottom-nav-arrow {
      position: relative;
      z-index: 3;
      width: 42px;
      height: 42px;
      border: 0;
      border-radius: 999px;
      background: #111827;
      color: #fff;
      font-size: 23px;
      line-height: 1;
      font-weight: 950;
      cursor: pointer;
      box-shadow: 0 8px 18px rgba(0,0,0,.18);
      transition: transform .18s ease, box-shadow .18s ease, filter .18s ease, opacity .18s ease;
    }
    .bottom-nav-arrow:disabled {
      opacity: .34;
      cursor: default;
      box-shadow: none;
    }
    .bottom-nav-count {
      position: absolute;
      left: 50%;
      bottom: -16px;
      transform: translateX(-50%);
      padding: 3px 9px;
      border-radius: 999px;
      background: rgba(31,35,40,.88);
      color: #fff;
      font-size: 10px;
      line-height: 1;
      font-weight: 900;
      pointer-events: none;
      box-shadow: 0 5px 12px rgba(0,0,0,.14);
    }
    @media (hover:hover) and (pointer:fine) {
      .bottom-nav-card:hover {
        transform: translateY(-5px) scale(1.025);
        box-shadow: 0 16px 30px rgba(0,0,0,.20);
        filter: brightness(1.025);
      }
      .bottom-nav-arrow:not(:disabled):hover {
        filter: brightness(1.08);
        box-shadow: 0 13px 27px rgba(0,0,0,.24);
      }
      .bottom-nav-arrow.prev:hover { transform: translateX(-4px); }
      .bottom-nav-arrow.next:hover { transform: translateX(4px); }
    }
    @media (min-width: 760px) and (hover:hover) and (pointer:fine) {
      .app { padding-bottom: calc(env(safe-area-inset-bottom) + 92px); }
    }
    @media (max-width: 759px), (hover:none), (pointer:coarse) {
      .bottom-character-nav { display: none !important; }
    }
  `;

  function readCurrentIndex() {
    const progress = document.getElementById('progress');
    const text = progress ? String(progress.textContent || '') : '';
    const match = text.match(/(\d+)\s*\//);
    if (match) return Math.max(0, parseInt(match[1], 10) - 1);
    return Math.max(0, Number(localStorage.getItem(STORAGE_KEY) || 0) || 0);
  }

  function clamp(value, min, max) { return Math.max(min, Math.min(max, value)); }
  function getCharacterName(character) { return character && (character.name || character.character || character.protagonist_name || 'Neznámá postava'); }
  function getGameTitle(character) { return character && (character.gameTitle || character.game || character.title || ''); }

  function recenterWindow() {
    const maxStart = Math.max(0, characters.length - VISIBLE_COUNT);
    windowStart = clamp(currentIndex - Math.floor(VISIBLE_COUNT / 2), 0, maxStart);
  }

  function goToIndex(targetIndex) {
    const safeIndex = clamp(targetIndex, 0, Math.max(0, characters.length - 1));
    localStorage.setItem(STORAGE_KEY, String(safeIndex));
    window.location.reload();
  }

  function shiftWindow(delta) {
    const maxStart = Math.max(0, characters.length - VISIBLE_COUNT);
    windowStart = clamp(windowStart + delta, 0, maxStart);
    renderTrack();
  }

  function escapeHtml(value) {
    return String(value || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  function renderTrack() {
    if (!track || !characters.length) return;
    const total = characters.length;
    const end = Math.min(total, windowStart + VISIBLE_COUNT);
    const slice = characters.slice(windowStart, end);
    track.innerHTML = '';

    slice.forEach((character, offset) => {
      const itemIndex = windowStart + offset;
      const card = document.createElement('button');
      card.type = 'button';
      card.className = 'bottom-nav-card' + (itemIndex === currentIndex ? ' is-current' : '');
      card.title = (itemIndex + 1) + '. ' + getCharacterName(character) + (getGameTitle(character) ? ' — ' + getGameTitle(character) : '');
      card.setAttribute('aria-label', 'Přejít na položku ' + (itemIndex + 1) + ': ' + getCharacterName(character));
      card.innerHTML = `
        <span class="bottom-nav-index">${itemIndex + 1}</span>
        <span class="bottom-nav-name">${escapeHtml(getCharacterName(character))}</span>
        <span class="bottom-nav-game">${escapeHtml(getGameTitle(character))}</span>
      `;
      card.addEventListener('click', () => goToIndex(itemIndex));
      track.appendChild(card);
    });

    const prev = root.querySelector('.bottom-nav-arrow.prev');
    const next = root.querySelector('.bottom-nav-arrow.next');
    if (prev) prev.disabled = windowStart <= 0;
    if (next) next.disabled = end >= total;
    if (countLabel) countLabel.textContent = (currentIndex + 1) + ' / ' + total;
  }

  function buildNav() {
    if (!characters.length || document.querySelector('.bottom-character-nav')) return;

    const style = document.createElement('style');
    style.textContent = css;
    document.head.appendChild(style);

    root = document.createElement('nav');
    root.className = 'bottom-character-nav';
    root.setAttribute('aria-label', 'Rychlá navigace mezi postavami');

    const prev = document.createElement('button');
    prev.type = 'button';
    prev.className = 'bottom-nav-arrow prev';
    prev.textContent = '‹';
    prev.setAttribute('aria-label', 'Zobrazit předchozí postavy');
    prev.addEventListener('click', () => shiftWindow(-STEP));

    track = document.createElement('div');
    track.className = 'bottom-nav-track';

    const next = document.createElement('button');
    next.type = 'button';
    next.className = 'bottom-nav-arrow next';
    next.textContent = '›';
    next.setAttribute('aria-label', 'Zobrazit další postavy');
    next.addEventListener('click', () => shiftWindow(STEP));

    countLabel = document.createElement('div');
    countLabel.className = 'bottom-nav-count';

    root.appendChild(prev);
    root.appendChild(track);
    root.appendChild(next);
    root.appendChild(countLabel);
    document.body.appendChild(root);

    currentIndex = readCurrentIndex();
    recenterWindow();
    renderTrack();
    observeProgress();
  }

  function observeProgress() {
    const progress = document.getElementById('progress');
    if (!progress || !window.MutationObserver) return;
    new MutationObserver(() => {
      const nextIndex = readCurrentIndex();
      if (nextIndex === currentIndex) return;
      currentIndex = nextIndex;
      recenterWindow();
      renderTrack();
    }).observe(progress, { childList: true, characterData: true, subtree: true });
  }

  function init() {
    fetch('characters.json', { cache: 'no-store' })
      .then((response) => {
        if (!response.ok) throw new Error('Nepodařilo se načíst characters.json pro spodní navigaci.');
        return response.json();
      })
      .then((data) => {
        characters = Array.isArray(data) ? data : [];
        if (typeof window.prepareArchetypeCharactersForValidation === 'function') {
          characters = window.prepareArchetypeCharactersForValidation(characters);
        }
        buildNav();
      })
      .catch((error) => console.warn(error));
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
