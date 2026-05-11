function csrfToken() {
  return document.querySelector('meta[name="csrf-token"]').content;
}

const introSeenKey = 'boda_intro_seen';
const introModeKey = 'boda_auth_mode';

function storageGet(key) {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function storageSet(key, value) {
  try {
    localStorage.setItem(key, value);
  } catch {
    // Optional enhancement only.
  }
}

function markIntroSeen() {
  storageSet(introSeenKey, '1');
  storageSet(introModeKey, 'login');
}

async function postJson(url, payload) {
  const res = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': csrfToken(),
    },
    body: JSON.stringify(payload),
  });
  const contentType = res.headers.get('content-type') || '';
  const text = await res.text();
  let data = null;
  if (contentType.includes('application/json')) {
    try {
      data = JSON.parse(text);
    } catch {
      data = null;
    }
  }
  if (!res.ok) {
    const detail = data && data.detail ? data.detail : `Request failed (${res.status})`;
    throw new Error(detail);
  }
  return data || {};
}

function setMessage(text, ok = false) {
  const el = document.getElementById('auth-message');
  el.textContent = text;
  el.style.color = ok ? 'green' : 'crimson';
}

function uiText(key, fallback = '') {
  return window.t ? window.t(key, fallback) : fallback || key;
}

const introScene = document.getElementById('intro-scene');
const authScene = document.getElementById('auth-scene');
const introSlides = Array.from(document.querySelectorAll('.intro-slide'));
const introDots = Array.from(document.querySelectorAll('.intro-dot'));
const introProgressBar = document.getElementById('intro-progress-bar');
const introNextBtn = document.getElementById('intro-next-btn');
const introPrevBtn = document.getElementById('intro-prev-btn');
const introSkipBtn = document.getElementById('intro-skip-btn');

let introIndex = 0;
const returningUser = storageGet(introSeenKey) === '1';

function showAuthScene(persistSeen = false) {
  introScene.classList.add('hidden');
  authScene.classList.remove('hidden');
  if (persistSeen) {
    markIntroSeen();
  }
}

function renderIntro(index) {
  introIndex = Math.max(0, Math.min(introSlides.length - 1, index));
  introSlides.forEach((slide, i) => {
    slide.classList.toggle('active', i === introIndex);
  });
  introDots.forEach((dot, i) => {
    dot.classList.toggle('active', i === introIndex);
  });
  if (introProgressBar) {
    const percent = ((introIndex + 1) / introSlides.length) * 100;
    introProgressBar.style.width = `${percent}%`;
  }
  if (introPrevBtn) {
    introPrevBtn.disabled = introIndex === 0;
  }
  if (introNextBtn) {
    const nextKey = introIndex === introSlides.length - 1 ? 'intro_get_started' : 'intro_next';
    introNextBtn.dataset.i18n = nextKey;
    introNextBtn.textContent = window.t ? window.t(nextKey, introIndex === introSlides.length - 1 ? 'Get Started' : 'Next') : introIndex === introSlides.length - 1 ? 'Get Started' : 'Next';
  }
}

if (introSlides.length) {
  renderIntro(0);
  window.addEventListener('languagechange', () => {
    renderIntro(introIndex);
  });
  introNextBtn.addEventListener('click', () => {
    if (introIndex >= introSlides.length - 1) {
      showAuthScene(true);
      return;
    }
    renderIntro(introIndex + 1);
  });

  introPrevBtn.addEventListener('click', () => {
    renderIntro(introIndex - 1);
  });

  introSkipBtn.addEventListener('click', () => {
    showAuthScene(true);
  });

  introDots.forEach((dot) => {
    dot.addEventListener('click', () => {
      renderIntro(parseInt(dot.dataset.dotIndex, 10));
    });
  });
}

const loginPanel = document.getElementById('login-panel');
const registerPanel = document.getElementById('register-panel');
const switchBtn = document.getElementById('switch-auth-mode');
const asideTitle = document.getElementById('aside-title');
const asideCopy = document.getElementById('aside-copy');

let mode = 'login';
const stationGroup = document.getElementById('driver-station-group');
const stationInput = document.getElementById('register-station');
const stationBadge = document.getElementById('station-verify-badge');
const stationModal = document.getElementById('station-modal');
const stationSuggestions = document.getElementById('station-suggestions');
const stationCancelBtn = document.getElementById('station-cancel-btn');
const stationRequestBtn = document.getElementById('station-request-btn');
const stationRequestModal = document.getElementById('station-request-modal');
const stationRequestName = document.getElementById('station-request-name');
const stationRequestPhone = document.getElementById('station-request-phone');
const stationRequestEmail = document.getElementById('station-request-email');
const stationRequestSubmit = document.getElementById('station-request-submit');
const stationRequestCancel = document.getElementById('station-request-cancel');

let stationOptions = [
  { key: 'stone_town', name: 'Stone Town' },
  { key: 'malindi', name: 'Malindi' },
  { key: 'forodhani', name: 'Forodhani' },
  { key: 'darajani', name: 'Darajani' },
  { key: 'mlandege', name: 'Mlandege' },
  { key: 'amaan_stadium', name: 'Amaan Stadium' },
  { key: 'chukwani', name: 'Chukwani' },
  { key: 'kisauni_airport', name: 'Kisauni Airport' },
  { key: 'fumba', name: 'Fumba' },
  { key: 'bweleo', name: 'Bweleo' },
  { key: 'dunga', name: 'Dunga' },
  { key: 'mwera', name: 'Mwera' },
  { key: 'mangapwani', name: 'Mangapwani' },
  { key: 'mkokotoni', name: 'Mkokotoni' },
  { key: 'nungwi', name: 'Nungwi' },
  { key: 'kendwa', name: 'Kendwa' },
  { key: 'kiwengwa', name: 'Kiwengwa' },
  { key: 'matemwe', name: 'Matemwe' },
  { key: 'paje', name: 'Paje' },
  { key: 'jambiani', name: 'Jambiani' },
  { key: 'michamvi', name: 'Michamvi' },
  { key: 'chwaka', name: 'Chwaka' },
  { key: 'makunduchi', name: 'Makunduchi' },
  { key: 'kwanyanya', name: 'Kwanyanya' },
  { key: 'mbuzini_hospital', name: 'Mbuzini Hospital' },
  { key: 'njia_ya_kama', name: 'Njia ya Kama' },
  { key: 'bububu_skuli', name: 'Bububu Skuli' },
  { key: 'kidichi', name: 'Kidichi' },
  { key: 'njia_ya_bumbwini', name: 'Njia ya Bumbwini' },
];

function normalizeName(value) {
  return String(value || '').trim().toLowerCase();
}

function resolveStationKey(inputValue) {
  const normalized = normalizeName(inputValue);
  const match = stationOptions.find((opt) => normalizeName(opt.name) === normalized);
  return match ? match.key : '';
}

async function loadStationOptions() {
  try {
    const res = await fetch('/api/locations/');
    if (!res.ok) return;
    const data = await res.json();
    if (!data.locations) return;
    stationOptions = data.locations.map((loc) => ({ key: loc.key, name: loc.name }));
    const list = document.getElementById('station-list');
    if (list) {
      list.innerHTML = stationOptions.map((opt) => `<option value="${opt.name}"></option>`).join('');
    }
  } catch {
    // Non-blocking.
  }
}

function updateStationBadge(isVerified) {
  if (!stationBadge) return;
  stationBadge.textContent = isVerified ? uiText('station_verified_label', 'Verified station') : uiText('station_pending_label', 'Not verified yet');
  stationBadge.classList.toggle('verified', isVerified);
  stationBadge.classList.toggle('pending', !isVerified);
}

function getSuggestions(inputValue) {
  const normalized = normalizeName(inputValue);
  if (!normalized) return stationOptions.slice(0, 5);
  const contains = stationOptions.filter((opt) => normalizeName(opt.name).includes(normalized));
  if (contains.length) return contains.slice(0, 5);

  const scored = stationOptions
    .map((opt) => {
      const name = normalizeName(opt.name);
      let score = 0;
      for (const char of normalized) {
        if (name.includes(char)) score += 1;
      }
      return { opt, score };
    })
    .sort((a, b) => b.score - a.score);
  return scored.slice(0, 5).map((item) => item.opt);
}

function openStationModal(suggestions, onPick) {
  if (!stationModal || !stationSuggestions) return;
  stationSuggestions.innerHTML = suggestions
    .map((opt) => `<button type="button" data-key="${opt.key}">${opt.name}</button>`)
    .join('');
  stationSuggestions.querySelectorAll('button').forEach((btn) => {
    btn.addEventListener('click', () => {
      const key = btn.dataset.key;
      const selected = stationOptions.find((opt) => opt.key === key);
      if (selected && stationInput) {
        stationInput.value = selected.name;
      }
      updateStationBadge(true);
      stationModal.classList.add('hidden');
      if (onPick) onPick(selected);
    });
  });
  stationModal.classList.remove('hidden');
}

if (stationCancelBtn && stationModal) {
  stationCancelBtn.addEventListener('click', () => stationModal.classList.add('hidden'));
}
if (stationRequestBtn && stationRequestModal) {
  stationRequestBtn.addEventListener('click', () => {
    if (stationRequestName && stationInput) {
      stationRequestName.value = stationInput.value || '';
    }
    stationRequestModal.classList.remove('hidden');
  });
}
if (stationRequestCancel && stationRequestModal) {
  stationRequestCancel.addEventListener('click', () => stationRequestModal.classList.add('hidden'));
}
if (stationRequestSubmit) {
  stationRequestSubmit.addEventListener('click', async () => {
    const name = (stationRequestName?.value || '').trim();
    const phone = (stationRequestPhone?.value || '').trim();
    const email = (stationRequestEmail?.value || '').trim();
    if (!name) {
      setMessage(uiText('toast_station_required', 'Station name is required'));
      return;
    }
    try {
      await postJson('/api/station-requests/', {
        requested_name: name,
        contact_phone: phone,
        contact_email: email,
      });
      setMessage(uiText('toast_station_submitted', 'Station request submitted. We will review it shortly.'), true);
      if (stationRequestModal) stationRequestModal.classList.add('hidden');
      if (stationModal) stationModal.classList.add('hidden');
    } catch (err) {
      setMessage(err.message);
    }
  });
}

function setMode(nextMode) {
  mode = nextMode;
  const inLogin = mode === 'login';

  loginPanel.classList.toggle('hidden', !inLogin);
  registerPanel.classList.toggle('hidden', inLogin);

  if (inLogin) {
    asideTitle.dataset.i18n = 'auth_aside_title_signup';
    asideCopy.dataset.i18n = 'auth_aside_copy_signup';
    switchBtn.dataset.i18n = 'auth_switch_signup';
  } else {
    asideTitle.dataset.i18n = 'auth_aside_title_signin';
    asideCopy.dataset.i18n = 'auth_aside_copy_signin';
    switchBtn.dataset.i18n = 'auth_switch_signin';
  }

  if (window.applyTranslations) {
    window.applyTranslations(localStorage.getItem('boda_language') || 'en');
  }
  setMessage('');
  storageSet(introModeKey, mode);
}

switchBtn.addEventListener('click', () => {
  setMode(mode === 'login' ? 'register' : 'login');
});

const roleSelect = document.getElementById('register-role');
if (roleSelect && stationGroup) {
  const toggleStation = () => {
    const isDriver = roleSelect.value === 'driver';
    stationGroup.classList.toggle('hidden', !isDriver);
    if (!isDriver) {
      updateStationBadge(false);
    }
  };
  roleSelect.addEventListener('change', toggleStation);
  toggleStation();
}

if (stationInput) {
  stationInput.addEventListener('input', () => {
    const key = resolveStationKey(stationInput.value);
    updateStationBadge(Boolean(key));
  });
}

document.getElementById('register-btn').addEventListener('click', async () => {
  try {
    const role = document.getElementById('register-role').value;
    let stationKey = '';
    if (role === 'driver') {
      const inputValue = stationInput ? stationInput.value : '';
      stationKey = resolveStationKey(inputValue);
      if (!stationKey) {
        const suggestions = getSuggestions(inputValue);
        openStationModal(suggestions);
        setMessage(uiText('toast_select_station', 'Select one of the suggested stations to continue.'));
        return;
      }
    }
    await postJson('/auth/register/', {
      full_name: document.getElementById('register-name').value.trim(),
      email: document.getElementById('register-email').value.trim(),
      phone_number: document.getElementById('register-phone').value.trim(),
      password: document.getElementById('register-password').value,
      role,
      station_key: stationKey,
      language: window.getAppLanguage ? window.getAppLanguage() : storageGet('boda_language') || 'en',
    });
    markIntroSeen();
    setMessage(uiText('toast_registration_success', 'Registration successful. Please verify the OTP sent to your email.'), true);
    const otpModal = document.getElementById('otp-modal');
    const otpEmail = document.getElementById('otp-email');
    if (otpEmail) otpEmail.value = document.getElementById('register-email').value.trim();
    if (otpModal) otpModal.classList.remove('hidden');
  } catch (err) {
    setMessage(err.message);
  }
});

document.getElementById('login-btn').addEventListener('click', async () => {
  try {
    await postJson('/auth/login/', {
      phone_number: document.getElementById('login-phone').value.trim(),
      password: document.getElementById('login-password').value,
    });
    window.location.href = '/dashboard/';
  } catch (err) {
    setMessage(err.message);
  }
});

const otpVerifyBtn = document.getElementById('otp-verify-btn');
if (otpVerifyBtn) {
  otpVerifyBtn.addEventListener('click', async () => {
    try {
      await postJson('/auth/verify-email/', {
        email: document.getElementById('otp-email').value.trim(),
        otp: document.getElementById('otp-code').value.trim(),
      });
      setMessage(uiText('toast_email_verified', 'Email verified. You can now login.'), true);
      const otpModal = document.getElementById('otp-modal');
      if (otpModal) otpModal.classList.add('hidden');
      setMode('login');
    } catch (err) {
      setMessage(err.message);
    }
  });
}

const otpResendBtn = document.getElementById('otp-resend-btn');
if (otpResendBtn) {
  otpResendBtn.addEventListener('click', async () => {
    try {
      otpResendBtn.disabled = true;
      let remaining = 60;
      const originalText = otpResendBtn.textContent;
      otpResendBtn.textContent = `${originalText} (${remaining}s)`;
      const timer = setInterval(() => {
        remaining -= 1;
        if (remaining <= 0) {
          clearInterval(timer);
          otpResendBtn.disabled = false;
          otpResendBtn.textContent = originalText;
          return;
        }
        otpResendBtn.textContent = `${originalText} (${remaining}s)`;
      }, 1000);
      await postJson('/auth/resend-otp/', {
        email: document.getElementById('otp-email').value.trim(),
      });
      setMessage(uiText('toast_otp_resent', 'OTP resent. Check your email.'), true);
    } catch (err) {
      otpResendBtn.disabled = false;
      setMessage(err.message);
    }
  });
}

if (returningUser) {
  introScene.classList.add('hidden');
  authScene.classList.remove('hidden');
  setMode('login');
} else {
  renderIntro(0);
  setMode(storageGet(introModeKey) === 'register' ? 'register' : 'login');
}
loadStationOptions();

document.addEventListener('click', (event) => {
  const btn = event.target.closest('.password-toggle');
  if (!btn) return;
  event.preventDefault();
  const targetId = btn.dataset.target;
  const input = targetId ? document.getElementById(targetId) : null;
  if (!input) return;
  const isVisible = input.type === 'text';
  input.setAttribute('type', isVisible ? 'password' : 'text');
  input.type = isVisible ? 'password' : 'text';
  btn.classList.toggle('is-visible', !isVisible);
  btn.setAttribute('aria-label', isVisible ? 'Show password' : 'Hide password');
});
