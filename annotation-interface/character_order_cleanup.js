(() => {
  'use strict';

  const FRONT = [
    'kratos_old',
    'kratos_modern',
    'henry_of_skalitz',
    'joel_miller',
    'lara_croft',
    'geralt_of_rivia',
    'harrier_harry_du_bois',
    'link',
    'gordon_freeman',
    'chell',
    'master_chief',
    'doom_slayer',
    'samus_aran',
    'solid_snake',
    'cloud_strife',
    'batman'
  ];

  const END = ['mario'];

  const PREFERRED = {
    kratos_modern: ['manual_2018_god-of-war_kratos-modern'],
    henry_of_skalitz: ['steam_379430_henry-of-skalitz'],
    mario: ['igdbpre90_1985_super-mario-bros_mario'],
    lara_croft: ['steam__lara-croft', 'steam_391220_lara-croft'],
    link: ['igdb90_1998_the-legend-of-zelda-ocarina-of-time_link'],
    chell: ['steam__chell_2', 'steam__chell'],
    gordon_freeman: ['steam__gordon-freeman'],
    doom_slayer: ['steam_379720_doom-slayer']
  };

  function norm(value) {
    return String(value || '')
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')
      .replace(/[™®“”"']/g, '')
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, ' ')
      .trim()
      .replace(/\s+/g, ' ');
  }

  function slug(value) { return norm(value).replace(/ /g, '_'); }
  function character(item) { return item && (item.character || item.protagonist_name || item.display_character || item.name || ''); }
  function game(item) { return item && (item.game || item.display_game || item.game_name || item.gameTitle || item.title || ''); }

  function key(item) {
    const c = norm(character(item));
    const g = norm(game(item));
    const id = norm(item && item.id);
    const appid = String(item && item.appid || '').split('.')[0];

    if (id.includes('henry of skalitz') || c.includes('henry of skalitz') || (c === 'henry' && g.includes('kingdom come'))) return 'henry_of_skalitz';
    if (c.includes('kratos')) return (c.includes('norse') || g.includes('2018') || appid === '1593500') ? 'kratos_modern' : 'kratos_old';
    if (c.includes('lara croft')) return 'lara_croft';
    if (c === 'link') return 'link';
    if (c === 'mario' || c === 'jumpman mario') return 'mario';
    if (c.includes('joel')) return 'joel_miller';
    if (c.includes('bruce wayne') || c === 'batman') return 'batman';
    if (c === 'chell') return 'chell';
    if (c === 'gordon freeman') return 'gordon_freeman';
    if (c === 'doomguy' || c === 'doom slayer') return 'doom_slayer';
    if (c === 'samus aran') return 'samus_aran';
    if (c === 'solid snake') return 'solid_snake';
    return slug(c);
  }

  function addMissing(items) {
    const out = items.slice();
    if (!out.some((item) => key(item) === 'joel_miller')) {
      out.push({ id: 'manual_2013_the-last-of-us_joel-miller', game: 'The Last of Us Part I', gameTitle: 'The Last of Us Part I', character: 'Joel Miller', name: 'Joel Miller', protagonist_name: 'Joel Miller', include_main_clean: true });
    }
    if (!out.some((item) => key(item) === 'kratos_modern')) {
      out.push({ id: 'manual_2018_god-of-war_kratos-modern', appid: '1593500', game: 'God of War', gameTitle: 'God of War (2018)', character: 'Kratos (Norse era)', name: 'Kratos (Norse era)', protagonist_name: 'Kratos (Norse era)', include_main_clean: true });
    }
    return out;
  }

  function score(groupKey, item, index) {
    const preferred = PREFERRED[groupKey] || [];
    const p = preferred.indexOf(item && item.id);
    return (p >= 0 ? 100000 - p * 1000 : 0) + Math.max(0, 500 - index);
  }

  function prepareCharactersForValidation(data) {
    if (!Array.isArray(data)) return data;

    const groups = new Map();
    addMissing(data).forEach((item, index) => {
      const groupKey = key(item) || ('unknown_' + index);
      if (!groups.has(groupKey)) groups.set(groupKey, []);
      groups.get(groupKey).push({ item, index });
    });

    const kept = [];
    groups.forEach((entries, groupKey) => {
      let best = entries[0];
      entries.forEach((entry) => {
        if (score(groupKey, entry.item, entry.index) > score(groupKey, best.item, best.index)) best = entry;
      });
      kept.push({ item: Object.assign({}, best.item), index: best.index, groupKey });
    });

    const byKey = new Map();
    kept.forEach((entry) => byKey.set(entry.groupKey, entry));

    const ordered = [];
    const used = new Set();

    FRONT.forEach((frontKey) => {
      const entry = byKey.get(frontKey);
      if (entry && !used.has(entry.item.id)) {
        ordered.push(entry.item);
        used.add(entry.item.id);
      }
    });

    kept.sort((a, b) => a.index - b.index).forEach((entry) => {
      if (END.indexOf(entry.groupKey) < 0 && !used.has(entry.item.id)) {
        ordered.push(entry.item);
        used.add(entry.item.id);
      }
    });

    END.forEach((endKey) => {
      const entry = byKey.get(endKey);
      if (entry && !used.has(entry.item.id)) ordered.push(entry.item);
    });

    ordered.forEach((item, index) => {
      item.order = index + 1;
      if (!item.name) item.name = character(item);
      if (!item.gameTitle) item.gameTitle = game(item);
      item.reorder_note_v4 = 'henry_of_skalitz_third';
    });

    return ordered;
  }

  window.prepareArchetypeCharactersForValidation = prepareCharactersForValidation;
})();

(() => {
  const current = document.currentScript;
  const parent = current && current.parentNode;
  const appScript = document.createElement('script');
  appScript.src = 'app_' + 'cleaned.js?v=henry3';
  const navScript = document.createElement('script');
  navScript.src = 'bottom_character_nav_' + 'cleaned.js?v=henry3';
  if (parent) {
    parent.insertBefore(appScript, current.nextSibling);
    parent.insertBefore(navScript, appScript.nextSibling);
  }
})();
