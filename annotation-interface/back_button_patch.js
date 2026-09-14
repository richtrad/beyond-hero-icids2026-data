(() => {
  function getProgressIndex() {
    const progress = document.getElementById('progress');
    if (!progress) return 0;
    const match = String(progress.textContent || '').match(/(\d+)\s*\//);
    if (!match) return 0;
    return Math.max(0, parseInt(match[1], 10) - 1);
  }

  function updateBackButtonState(button) {
    const currentIndex = getProgressIndex();
    button.disabled = currentIndex <= 0;
    button.setAttribute('aria-disabled', currentIndex <= 0 ? 'true' : 'false');
    button.title = currentIndex <= 0 ? 'Jsi na první položce.' : 'Vrátit se na předchozí položku.';
  }

  function ensureBackButton() {
    const skipButton = document.getElementById('skipBtn');
    if (!skipButton || !skipButton.parentElement) return;

    let button = document.getElementById('prevBtn');
    if (!button) {
      button = document.createElement('button');
      button.id = 'prevBtn';
      button.type = 'button';
      button.className = 'btn secondary';
      button.textContent = 'Zpět';
      skipButton.parentElement.insertBefore(button, skipButton);
    }

    button.addEventListener('click', function (event) {
      event.preventDefault();
      const currentIndex = getProgressIndex();
      if (currentIndex <= 0) {
        updateBackButtonState(button);
        return;
      }
      localStorage.setItem('icids17_demo_archetype_current_index', String(currentIndex - 1));
      window.location.reload();
    });

    updateBackButtonState(button);
    const progress = document.getElementById('progress');
    if (progress && window.MutationObserver) {
      new MutationObserver(function () { updateBackButtonState(button); })
        .observe(progress, { childList: true, characterData: true, subtree: true });
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', ensureBackButton);
  } else {
    ensureBackButton();
  }
})();
