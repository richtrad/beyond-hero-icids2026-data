(function () {
  'use strict';

  var archetypes = [
    { id: 'explorer', name: 'Explorer', motive: 'Freedom' },
    { id: 'outlaw', name: 'Outlaw', motive: 'Liberation' },
    { id: 'magician', name: 'Magician', motive: 'Power' },
    { id: 'hero', name: 'Hero', motive: 'Mastery' },
    { id: 'lover', name: 'Lover', motive: 'Intimacy' },
    { id: 'jester', name: 'Jester', motive: 'Enjoyment' },
    { id: 'everyman', name: 'Everyman', motive: 'Belonging' },
    { id: 'caregiver', name: 'Caregiver', motive: 'Service' },
    { id: 'ruler', name: 'Ruler', motive: 'Control' },
    { id: 'creator', name: 'Creator', motive: 'Innovation' },
    { id: 'innocent', name: 'Innocent', motive: 'Safety' },
    { id: 'sage', name: 'Sage', motive: 'Understanding' }
  ];

  var quadrants = [
    { className: 'q0', html: 'Explore<br>spirituality' },
    { className: 'q1', html: 'Leave<br>legacy' },
    { className: 'q2', html: 'Provide<br>structure' },
    { className: 'q3', html: 'Pursue<br>connection' }
  ];

  var cfg = window.ARCHETYPE_CONFIG || {};
  var maxSelections = Number(cfg.MAX_SELECTIONS || 3);
  var endpoint = String(cfg.GOOGLE_SHEETS_WEB_APP_URL || '').trim();
  var keepLocal = cfg.KEEP_LOCAL_BACKUP !== false;

  var characters = [];
  var index = 0;
  var selected = [];
  var participantId = getParticipantId();

  var els = {
    wheel: document.getElementById('wheel'),
    ringLabels: document.getElementById('ringLabels'),
    name: document.getElementById('characterName'),
    game: document.getElementById('gameTitle'),
    progress: document.getElementById('progress'),
    note: document.getElementById('selectionNote'),
    confirm: document.getElementById('confirmBtn'),
    skip: document.getElementById('skipBtn'),
    export: document.getElementById('exportBtn'),
    status: document.getElementById('status')
  };

  init();

  function init() {
    renderStaticWheelParts();
    bindControls();
    loadCharacters();
  }

  function renderStaticWheelParts() {
    var template = document.getElementById('archetypeTemplate');
    for (var i = 0; i < archetypes.length; i += 1) {
      var clone = template.content.firstElementChild.cloneNode(true);
      clone.classList.add('a' + i);
      clone.dataset.id = archetypes[i].id;
      clone.dataset.name = archetypes[i].name;
      clone.querySelector('.arch-name').textContent = archetypes[i].name;
      clone.addEventListener('click', onArchetypeClick);
      els.wheel.appendChild(clone);

      var motive = document.createElement('div');
      motive.className = 'motive m' + i;
      motive.textContent = archetypes[i].motive;
      els.ringLabels.appendChild(motive);
    }
    for (var q = 0; q < quadrants.length; q += 1) {
      var quad = document.createElement('div');
      quad.className = 'quad ' + quadrants[q].className;
      quad.innerHTML = quadrants[q].html;
      els.ringLabels.appendChild(quad);
    }
  }

  function bindControls() {
    els.confirm.addEventListener('click', function () {
      if (!selected.length) return;
      submit(false);
    });
    els.skip.addEventListener('click', function () {
      submit(true);
    });
    els.export.addEventListener('click', exportLocalData);
  }

  function loadCharacters() {
    fetch('characters.json', { cache: 'no-store' })
      .then(function (r) {
        if (!r.ok) throw new Error('Nepodařilo se načíst characters.json');
        return r.json();
      })
      .then(function (data) {
        characters = Array.isArray(data) ? data : [];
        if (!characters.length) throw new Error('characters.json je prázdný');
        index = Number(localStorage.getItem('icids17_demo_archetype_current_index') || 0) || 0;
        index = index % characters.length;
        renderCharacter();
      })
      .catch(function (err) {
        characters = [
          { id: 'arthur_morgan', name: 'Arthur Morgan', gameTitle: 'Red Dead Redemption 2' },
          { id: 'lara_croft', name: 'Lara Croft', gameTitle: 'Tomb Raider' },
          { id: 'glados', name: 'GLaDOS', gameTitle: 'Portal 2' }
        ];
        setStatus('Používám vestavěná testovací data.');
        renderCharacter();
        console.error(err);
      });
  }

  function renderCharacter() {
    var character = characters[index];
    selected = [];
    els.name.textContent = character.name || 'Neznámá postava';
    els.game.textContent = character.gameTitle || '';
    els.progress.textContent = (index + 1) + ' / ' + characters.length;
    document.querySelectorAll('.arch').forEach(function (btn) {
      btn.classList.remove('selected', 'blocked');
      btn.disabled = false;
      btn.querySelector('.rank').textContent = '';
    });
    updateSelectionUI();
  }

  function onArchetypeClick(ev) {
    var btn = ev.currentTarget;
    var id = btn.dataset.id;
    var found = selected.indexOf(id);
    if (found >= 0) {
      selected.splice(found, 1);
    } else {
      if (selected.length >= maxSelections) {
        setStatus('Lze vybrat maximálně ' + maxSelections + ' archetypy.');
        return;
      }
      selected.push(id);
    }
    updateSelectionUI();
  }

  function updateSelectionUI() {
    document.querySelectorAll('.arch').forEach(function (btn) {
      var pos = selected.indexOf(btn.dataset.id);
      var rankEl = btn.querySelector('.rank');
      if (pos >= 0) {
        btn.classList.add('selected');
        btn.classList.remove('blocked');
        rankEl.textContent = String(pos + 1);
      } else {
        btn.classList.remove('selected');
        rankEl.textContent = '';
        if (selected.length >= maxSelections) btn.classList.add('blocked');
        else btn.classList.remove('blocked');
      }
    });

    els.confirm.disabled = selected.length === 0;
    if (!selected.length) {
      els.note.textContent = 'Zatím není vybrán žádný archetyp.';
    } else {
      var parts = selected.map(function (id, i) {
        return (i + 1) + '. ' + archetypeName(id);
      });
      els.note.textContent = parts.join(' · ');
    }
  }

  function submit(skipped) {
    var character = characters[index];
    var response = {
      timestamp: new Date().toISOString(),
      participantId: participantId,
      characterIndex: index,
      characterId: character.id || '',
      characterName: character.name || '',
      gameTitle: character.gameTitle || '',
      primaryArchetype: skipped ? '' : (selected[0] || ''),
      secondaryArchetype: skipped ? '' : (selected[1] || ''),
      tertiaryArchetype: skipped ? '' : (selected[2] || ''),
      selectedArchetypes: skipped ? [] : selected.slice(),
      selectedArchetypeNames: skipped ? [] : selected.map(archetypeName),
      skipped: !!skipped,
      userAgent: navigator.userAgent
    };

    if (keepLocal) saveLocal(response);
    sendToSheets(response);
    nextCharacter();
  }

  function nextCharacter() {
    index = (index + 1) % characters.length;
    localStorage.setItem('icids17_demo_archetype_current_index', String(index));
    renderCharacter();
  }

  function sendToSheets(payload) {
    if (!endpoint) {
      setStatus('Uloženo lokálně. Google Sheets endpoint není nastaven.');
      return;
    }
    setStatus('Ukládám…');
    fetch(endpoint, {
      method: 'POST',
      mode: 'no-cors',
      headers: { 'Content-Type': 'text/plain;charset=utf-8' },
      body: JSON.stringify(payload)
    }).then(function () {
      setStatus('Odesláno.');
    }).catch(function () {
      setStatus('Odeslání selhalo, lokální kopie zůstává.');
    });
  }

  function saveLocal(payload) {
    var key = 'icids17_demo_archetype_responses_jsonl';
    var current = localStorage.getItem(key) || '';
    localStorage.setItem(key, current + JSON.stringify(payload) + '\n');
  }

  function exportLocalData() {
    var data = localStorage.getItem('icids17_demo_archetype_responses_jsonl') || '';
    if (!data) {
      setStatus('Zatím nejsou žádná lokální data.');
      return;
    }
    var blob = new Blob([data], { type: 'application/x-ndjson;charset=utf-8' });
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url;
    a.download = 'archetype_responses_' + new Date().toISOString().slice(0, 10) + '.jsonl';
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  function archetypeName(id) {
    for (var i = 0; i < archetypes.length; i += 1) {
      if (archetypes[i].id === id) return archetypes[i].name;
    }
    return id;
  }

  function getParticipantId() {
    var key = 'icids17_demo_archetype_participant_id';
    var existing = localStorage.getItem(key);
    if (existing) return existing;
    var id = 'p_' + Date.now().toString(36) + '_' + Math.random().toString(36).slice(2, 10);
    localStorage.setItem(key, id);
    return id;
  }

  function setStatus(message) {
    els.status.textContent = message;
    window.clearTimeout(setStatus._t);
    setStatus._t = window.setTimeout(function () { els.status.textContent = ''; }, 3500);
  }
}());
