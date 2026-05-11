function csrfToken() {
  return document.querySelector('meta[name="csrf-token"]').content;
}

function generateRequestId() {
  if (window.crypto?.randomUUID) return window.crypto.randomUUID();
  return `req_${Date.now()}_${Math.floor(Math.random() * 100000)}`;
}

const offlineQueueKey = 'bodaboda_offline_queue';

function getOfflineQueue() {
  try {
    return JSON.parse(localStorage.getItem(offlineQueueKey) || '[]');
  } catch {
    return [];
  }
}

function setOfflineQueue(queue) {
  localStorage.setItem(offlineQueueKey, JSON.stringify(queue));
}

function enqueueOfflineAction(action) {
  const queue = getOfflineQueue();
  queue.push({ ...action, queued_at: Date.now() });
  setOfflineQueue(queue);
}

async function flushOfflineQueue() {
  const queue = getOfflineQueue();
  if (!queue.length) return;
  const remaining = [];
  for (const action of queue) {
    try {
      await api(action.url, action.method || 'POST', action.payload || null);
    } catch {
      remaining.push(action);
    }
  }
  setOfflineQueue(remaining);
}

async function api(url, method = 'GET', payload = null) {
  const options = {
    method,
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': csrfToken(),
    },
  };
  if (payload) {
    options.body = JSON.stringify(payload);
  }
  const res = await fetch(url, options);
  const data = await res.json();
  if (!res.ok) {
    throw new Error(data.detail || 'Request failed');
  }
  return data;
}

async function apiForm(url, formData) {
  const res = await fetch(url, {
    method: 'POST',
    headers: {
      'X-CSRFToken': csrfToken(),
    },
    body: formData,
  });
  const data = await res.json();
  if (!res.ok) {
    throw new Error(data.detail || 'Request failed');
  }
  return data;
}

function msg(text, ok = false) {
  const el = document.getElementById('dashboard-message');
  el.textContent = text;
  el.style.color = ok ? 'green' : 'crimson';
}

function uiText(key, fallback = '') {
  return window.t ? window.t(key, fallback) : fallback || key;
}

function uiTextFormat(key, values = {}, fallback = '') {
  let text = uiText(key, fallback);
  Object.entries(values).forEach(([name, value]) => {
    text = text.replaceAll(`{${name}}`, String(value));
  });
  return text;
}

function emptyUi(key, fallback = '') {
  return `<div class="empty-ui">${escapeHtml(uiText(key, fallback))}</div>`;
}

function setupOfflineUi() {
  const banner = document.getElementById('offline-banner');
  if (!banner) return;
  const refresh = () => {
    banner.classList.toggle('active', !navigator.onLine);
  };
  window.addEventListener('online', () => {
    refresh();
    flushOfflineQueue().catch(() => {});
    msg(uiText('toast_back_online', 'Back online. Syncing queued actions...'), true);
  });
  window.addEventListener('offline', refresh);
  refresh();
}

function escapeHtml(text) {
  return String(text ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}

function sanitizeUrl(url) {
  const value = String(url ?? '').trim();
  if (!value) return '';
  if (value.startsWith('/')) return value;
  if (/^https?:\/\//i.test(value)) return value;
  return '';
}

function sanitizePhone(phone) {
  const value = String(phone ?? '').trim();
  return /^[+0-9][0-9\s-]{6,19}$/.test(value) ? value : '';
}

function updateIdentityAvatar(imageUrl, name) {
  const card = document.querySelector('.identity-card');
  if (!card) return;
  const safeUrl = sanitizeUrl(imageUrl);
  const existingImg = card.querySelector('.identity-avatar');
  const existingBadge = card.querySelector('.identity-badge');
  if (safeUrl) {
    if (existingImg) {
      existingImg.src = safeUrl;
      return;
    }
    if (existingBadge) {
      existingBadge.outerHTML = `<img class="identity-avatar" src="${safeUrl}" alt="Profile" />`;
    }
    return;
  }
  if (!existingBadge && existingImg) {
    const initial = (name || '?').slice(0, 1).toUpperCase();
    existingImg.outerHTML = `<div class="identity-badge">${initial}</div>`;
  }
}

function emergencyContactsPayload(prefix) {
  return [1, 2].map((idx) => ({
    name: document.getElementById(`${prefix}-emergency-name-${idx}`)?.value.trim() || '',
    phone_number: document.getElementById(`${prefix}-emergency-phone-${idx}`)?.value.trim() || '',
    relationship: document.getElementById(`${prefix}-emergency-relationship-${idx}`)?.value.trim() || '',
  }));
}

function populateEmergencyContacts(prefix, contacts = []) {
  [1, 2].forEach((idx) => {
    const contact = contacts[idx - 1] || {};
    const nameNode = document.getElementById(`${prefix}-emergency-name-${idx}`);
    const phoneNode = document.getElementById(`${prefix}-emergency-phone-${idx}`);
    const relationNode = document.getElementById(`${prefix}-emergency-relationship-${idx}`);
    if (nameNode) nameNode.value = contact.name || '';
    if (phoneNode) phoneNode.value = contact.phone_number || '';
    if (relationNode) relationNode.value = contact.relationship || '';
  });
}

function getCurrentPositionAsync() {
  return new Promise((resolve, reject) => {
    if (!navigator.geolocation) {
      reject(new Error(uiText('toast_geolocation_unsupported', 'Geolocation not supported on this browser')));
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (position) => {
        resolve({
          lat: Number(position.coords.latitude.toFixed(6)),
          lng: Number(position.coords.longitude.toFixed(6)),
        });
      },
      () => reject(new Error(uiText('toast_location_unavailable', 'Unable to get your current location')))
    );
  });
}

function setupRatingStars(starContainer, onSelect) {
  if (!starContainer) return;
  starContainer.querySelectorAll('button').forEach((btn) => {
    btn.addEventListener('click', () => {
      const value = parseInt(btn.dataset.star, 10);
      starContainer.dataset.value = String(value);
      starContainer.querySelectorAll('button').forEach((b) => {
        b.classList.toggle('active', parseInt(b.dataset.star, 10) <= value);
      });
      if (onSelect) onSelect(value);
    });
  });
}

function createConfirmModal() {
  const modal = document.getElementById('confirm-modal');
  const title = document.getElementById('confirm-title');
  const message = document.getElementById('confirm-message');
  const okBtn = document.getElementById('confirm-ok-btn');
  const cancelBtn = document.getElementById('confirm-cancel-btn');
  if (!modal || !title || !message || !okBtn || !cancelBtn) {
    return async () => false;
  }

  return (options) =>
    new Promise((resolve) => {
      title.textContent = options?.title || uiText('confirm_action_title', 'Confirm Action');
      message.textContent = options?.message || uiText('confirm_action_message', 'Are you sure?');
      okBtn.textContent = options?.okText || uiText('confirm_yes', 'Yes');
      cancelBtn.textContent = options?.cancelText || uiText('confirm_no', 'No');
      modal.classList.remove('hidden');

      const cleanup = () => {
        modal.classList.add('hidden');
        okBtn.removeEventListener('click', onOk);
        cancelBtn.removeEventListener('click', onCancel);
        modal.removeEventListener('click', onBackdrop);
      };

      const onOk = () => {
        cleanup();
        resolve(true);
      };
      const onCancel = () => {
        cleanup();
        resolve(false);
      };
      const onBackdrop = (event) => {
        if (event.target === modal) {
          cleanup();
          resolve(false);
        }
      };

      okBtn.addEventListener('click', onOk);
      cancelBtn.addEventListener('click', onCancel);
      modal.addEventListener('click', onBackdrop);
    });
}

const showConfirm = createConfirmModal();

let seenNotificationIds = new Set();
let initialNotificationSyncDone = false;

function relativeTime(isoString) {
  try {
    const deltaMs = Date.now() - new Date(isoString).getTime();
    const mins = Math.floor(deltaMs / 60000);
    if (mins < 1) return 'just now';
    if (mins < 60) return `${mins}m ago`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs}h ago`;
    const days = Math.floor(hrs / 24);
    return `${days}d ago`;
  } catch {
    return '';
  }
}

function showToast(title, message) {
  const stack = document.getElementById('toast-stack');
  if (!stack) return;
  const toast = document.createElement('article');
  toast.className = 'toast';
  const heading = document.createElement('strong');
  heading.textContent = String(title ?? '');
  const body = document.createElement('span');
  body.textContent = String(message ?? '');
  toast.append(heading, body);
  stack.appendChild(toast);
  setTimeout(() => {
    toast.remove();
  }, 4500);
}

function playTone({ frequency, durationMs = 140, type = 'sine', volume = 0.06, delayMs = 0 }) {
  setTimeout(() => {
    const AudioCtx = window.AudioContext || window.webkitAudioContext;
    if (!AudioCtx) return;
    const ctx = new AudioCtx();
    const oscillator = ctx.createOscillator();
    const gain = ctx.createGain();

    oscillator.type = type;
    oscillator.frequency.value = frequency;
    gain.gain.value = volume;

    oscillator.connect(gain);
    gain.connect(ctx.destination);

    oscillator.start();
    oscillator.stop(ctx.currentTime + durationMs / 1000);
    oscillator.onended = () => ctx.close();
  }, delayMs);
}

function playNotificationSound(eventName) {
  // Distinct short patterns per event.
  if (eventName === 'ride_requested') {
    playTone({ frequency: 740, durationMs: 140, type: 'square', volume: 0.05 });
    playTone({ frequency: 880, durationMs: 140, type: 'square', volume: 0.05, delayMs: 170 });
    return;
  }
  if (eventName === 'ride_accepted') {
    playTone({ frequency: 523, durationMs: 120, type: 'triangle', volume: 0.055 });
    playTone({ frequency: 659, durationMs: 120, type: 'triangle', volume: 0.055, delayMs: 140 });
    return;
  }
  if (eventName === 'ride_started') {
    playTone({ frequency: 659, durationMs: 110, type: 'sine', volume: 0.05 });
    playTone({ frequency: 784, durationMs: 110, type: 'sine', volume: 0.05, delayMs: 130 });
    playTone({ frequency: 988, durationMs: 130, type: 'sine', volume: 0.05, delayMs: 260 });
    return;
  }
  if (eventName === 'ride_completed') {
    playTone({ frequency: 523, durationMs: 100, type: 'triangle', volume: 0.055 });
    playTone({ frequency: 659, durationMs: 100, type: 'triangle', volume: 0.055, delayMs: 110 });
    playTone({ frequency: 784, durationMs: 100, type: 'triangle', volume: 0.055, delayMs: 220 });
    playTone({ frequency: 1046, durationMs: 150, type: 'triangle', volume: 0.055, delayMs: 340 });
    return;
  }

  // Generic fallback sound.
  playTone({ frequency: 700, durationMs: 120, type: 'sine', volume: 0.05 });
}

function renderNotifications(data) {
  const panel = document.getElementById('notif-list');
  const badge = document.getElementById('notif-unread-badge');
  if (!panel || !badge) return;

  const notifications = data.notifications || [];
  const unread = data.unread_count || 0;

  if (unread > 0) {
    badge.textContent = String(unread);
    badge.classList.remove('hidden');
  } else {
    badge.classList.add('hidden');
  }

  if (!notifications.length) {
    panel.innerHTML = emptyUi('empty_no_notifications', 'No notifications yet.');
    return;
  }

  panel.innerHTML = notifications
    .map((n) => {
      let label = '';
      if (n.event === 'scheduled_pre_alert') {
        const lead = n.payload?.lead_minutes;
        label = lead
          ? `<span class="notif-label pre-alert">Starts in ${escapeHtml(lead)} min</span>`
          : '<span class="notif-label pre-alert">Starting soon</span>';
      }
      return `
        <article class="notif-item ${n.is_read ? '' : 'unread'}">
          <div class="notif-head">
            <h5>${escapeHtml(n.title)}</h5>
            ${label}
          </div>
          <p>${escapeHtml(n.message)}</p>
          <span class="meta">${relativeTime(n.created_at)}</span>
        </article>
      `;
    })
    .join('');
}

function setupNotificationUi() {
  const toggleBtn = document.getElementById('notif-toggle-btn');
  const panel = document.getElementById('notif-panel');
  const markAllBtn = document.getElementById('notif-mark-all-btn');
  const clearAllBtn = document.getElementById('notif-clear-btn');
  if (!toggleBtn || !panel || !markAllBtn || !clearAllBtn) return;

  toggleBtn.addEventListener('click', () => {
    panel.classList.toggle('hidden');
  });

  markAllBtn.addEventListener('click', async () => {
    try {
      await api('/api/notifications/mark-read/', 'POST', { mark_all: true });
      const data = await api('/api/notifications/');
      renderNotifications(data);
      msg(uiText('toast_notifications_marked_read', 'Notifications marked as read'), true);
    } catch (err) {
      msg(err.message);
    }
  });

  clearAllBtn.addEventListener('click', async () => {
    const confirmed = window.confirm(uiText('confirm_clear_notifications_message', 'Clear all notifications? This cannot be undone.'));
    if (!confirmed) return;
    try {
      await api('/api/notifications/clear/', 'POST', {});
      renderNotifications({ unread_count: 0, notifications: [] });
      msg(uiText('toast_notifications_cleared', 'Notifications cleared'), true);
    } catch (err) {
      msg(err.message);
    }
  });
}

function initNotifications() {
  setupNotificationUi();

  const poll = async () => {
    try {
      const data = await api('/api/notifications/');
      renderNotifications(data);
      const notifications = data.notifications || [];
      notifications.forEach((n) => {
        if (!seenNotificationIds.has(n.id)) {
          seenNotificationIds.add(n.id);
          if (initialNotificationSyncDone && !n.is_read) {
            showToast(n.title, n.message);
            playNotificationSound(n.event);
          }
        }
      });
      initialNotificationSyncDone = true;
    } catch {
      // Notification polling failures are non-blocking for dashboard.
    }
  };

  poll();
  setInterval(poll, 5000);
}

function vehicleLabel(value) {
  return value === 'bajaji' ? 'Bajaji' : 'Bodaboda';
}

let passengerLastRideId = null;
let passengerLastRideStatus = null;
let driverSeenIncomingIds = new Set();

function playAnimation({
  stageId,
  titleId,
  textId,
  statusId,
  vehicleId,
  title,
  text,
  status,
  vehicleType,
}) {
  const stage = document.getElementById(stageId);
  const titleEl = document.getElementById(titleId);
  const textEl = document.getElementById(textId);
  const statusEl = document.getElementById(statusId);
  const vehicleEl = document.getElementById(vehicleId);
  if (!stage || !titleEl || !textEl || !statusEl || !vehicleEl) return;

  titleEl.textContent = title;
  textEl.textContent = text;
  statusEl.textContent = status;
  vehicleEl.classList.remove('vehicle-motorcycle', 'vehicle-bajaji');
  vehicleEl.classList.add(vehicleType === 'bajaji' ? 'vehicle-bajaji' : 'vehicle-motorcycle');
  vehicleEl.textContent = vehicleType === 'bajaji' ? 'BAJAJI' : 'BODABODA';

  stage.classList.remove('hidden', 'anim-play');
  // Restart CSS animation reliably.
  void stage.offsetWidth;
  stage.classList.add('anim-play');
}

function passengerStatusText(status, vehicleType) {
  const vehicle = vehicleLabel(vehicleType);
  if (status === 'requested') return `${vehicle} request created. Looking for the best driver...`;
  if (status === 'accepted') return `${vehicle} driver accepted your ride and is heading to pickup.`;
  if (status === 'started') return `${vehicle} ride started. Enjoy your trip.`;
  if (status === 'completed') return `${vehicle} ride completed. Thank you for riding with us.`;
  if (status === 'cancelled') return `${vehicle} ride was cancelled. Please request another driver.`;
  return 'Ride status updated.';
}

function driverActionText(status, vehicleType) {
  const vehicle = vehicleLabel(vehicleType);
  if (status === 'incoming') return `New ${vehicle} ride request available near your area.`;
  if (status === 'accepted') return `You accepted this ${vehicle} ride. Proceed to pickup.`;
  if (status === 'started') return `${vehicle} ride started. Follow route to destination.`;
  if (status === 'completed') return `${vehicle} ride completed. Earnings updated.`;
  if (status === 'cancelled') return `${vehicle} ride cancelled. You can accept a new request.`;
  return 'Driver status updated.';
}

function showPassengerRideAnimation(status, vehicleType) {
  playAnimation({
    stageId: 'passenger-anim-stage',
    titleId: 'passenger-anim-title',
    textId: 'passenger-anim-text',
    statusId: 'passenger-anim-status',
    vehicleId: 'passenger-vehicle',
    title: 'Passenger Ride Update',
    text: passengerStatusText(status, vehicleType),
    status,
    vehicleType,
  });
}

function showDriverRideAnimation(status, vehicleType) {
  playAnimation({
    stageId: 'driver-anim-stage',
    titleId: 'driver-anim-title',
    textId: 'driver-anim-text',
    statusId: 'driver-anim-status',
    vehicleId: 'driver-vehicle',
    title: 'Driver Workflow Update',
    text: driverActionText(status, vehicleType),
    status,
    vehicleType,
  });
}

function renderNearbyDrivers(data) {
  const el = document.getElementById('nearby-output');
  const drivers = data.drivers || [];
  if (!drivers.length) {
    el.innerHTML = emptyUi('empty_no_nearby_drivers', 'No nearby drivers found.');
    return;
  }

  el.innerHTML = drivers
    .map(
      (d) => `
        <article class="mini-card nearby-driver-card">
          <div class="nearby-driver-top">
            <div class="current-ride-top">
              <div class="ride-badge ${d.vehicle_type === 'bajaji' ? 'bajaji' : 'boda'}">${d.vehicle_type === 'bajaji' ? 'BJ' : 'BD'}</div>
              <div>
                <h5 class="nearby-driver-name">${escapeHtml(d.name || `Driver #${d.driver_id}`)}</h5>
                <p class="nearby-driver-subtitle">${escapeHtml(vehicleLabel(d.vehicle_type))} ready near your pickup</p>
              </div>
            </div>
            <span class="ride-price-pill">${escapeHtml(d.distance_km)} km</span>
          </div>
          <div class="nearby-driver-grid">
            <div class="info-chip">
              <span>Vehicle</span>
              <strong>${vehicleLabel(d.vehicle_type)}</strong>
            </div>
            <div class="info-chip">
              <span>ETA</span>
              <strong>${estimateEtaMinutes(Number(d.distance_km || 1))} min</strong>
            </div>
          </div>
        </article>
      `
    )
    .join('');
}

function renderCurrentRide(data) {
  const el = document.getElementById('current-ride-output');
  if (!data.ride) {
    el.innerHTML = emptyUi('empty_no_active_ride', 'No active ride currently.');
    const receiptEl = document.getElementById('receipt-output');
    if (receiptEl) receiptEl.innerHTML = '';
    return;
  }
  const ride = data.ride;
  const canCancelRide = ['requested', 'accepted'].includes(String(ride.status || '').toLowerCase());
  const eta = ride.distance_km ? `${estimateEtaMinutes(Number(ride.distance_km))} min` : '-- min';
  const driver = ride.driver || null;
  const callPhone = sanitizePhone(driver?.phone_number);
  const callHtml = callPhone
    ? `<a class="call-link" href="tel:${encodeURIComponent(callPhone)}">Call Driver</a>`
    : '';
  const driverImageUrl = sanitizeUrl(driver?.profile_image_url);
  const driverPhoto = driverImageUrl
    ? `<img class="avatar" src="${driverImageUrl}" alt="Driver" />`
    : '<div class="avatar placeholder">D</div>';
  const stopLabel = ride.stops?.length ? ride.stops.map((s) => s.name).join(', ') : ride.stop_location;
  el.innerHTML = `
    <article class="mini-card">
      <div class="current-ride-top">
        <div>
          <h5 class="current-ride-title">${vehicleLabel(ride.vehicle_type)} Ride #${escapeHtml(ride.id)}</h5>
          <p class="current-ride-subtitle">${escapeHtml(ride.pickup_location ?? '-')} to ${escapeHtml(ride.dropoff_location ?? '-')}</p>
        </div>
        <span class="ride-status-pill">${escapeHtml(ride.status)}</span>
      </div>
      <div class="current-ride-grid">
        <div class="info-chip">
          <span>Fare</span>
          <strong>TZS ${escapeHtml(ride.fare_tzs)}</strong>
        </div>
        <div class="info-chip">
          <span>ETA</span>
          <strong>${eta}</strong>
        </div>
        <div class="info-chip">
          <span>Distance</span>
          <strong>${escapeHtml(ride.distance_km)} km</strong>
        </div>
        <div class="info-chip">
          <span>Vehicle</span>
          <strong>${vehicleLabel(ride.vehicle_type)}</strong>
        </div>
      </div>
      ${stopLabel ? `<div class="info-chip"><span>Stops</span><strong>${escapeHtml(stopLabel)}</strong></div>` : ''}
      ${
        driver
          ? `<div class="ride-contact-card">
              ${driverPhoto}
              <div>
                <strong>${escapeHtml(driver.name ?? 'Driver')}</strong>
                <p>${escapeHtml(driver.phone_number ?? '-')}</p>
                <p>${vehicleLabel(driver.vehicle_type)} | Plate: ${escapeHtml(driver.plate_number || '-')}</p>
                ${callHtml}
              </div>
              </div>`
          : ''
      }
      ${
        canCancelRide
          ? `<div class="ride-selection-actions">
              <button id="passenger-cancel-ride-btn" class="secondary-ride-btn" type="button" data-ride-id="${escapeHtml(ride.id)}">Cancel Ride</button>
            </div>`
          : ''
      }
    </article>
  `;
  const cancelBtn = document.getElementById('passenger-cancel-ride-btn');
  if (cancelBtn) {
    cancelBtn.addEventListener('click', async () => {
      const rideId = parseInt(cancelBtn.dataset.rideId || '', 10);
      if (!rideId) {
        msg(uiText('toast_no_ride_selected', 'No ride selected.'));
        return;
      }
      const confirmed = await showConfirm({
        title: uiText('confirm_cancel_ride_title', 'Cancel Ride'),
        message: uiText('confirm_cancel_ride_message', 'Cancel this ride? This cannot be undone.'),
        okText: uiText('confirm_yes', 'Yes'),
        cancelText: uiText('confirm_no', 'No'),
      });
      if (!confirmed) return;
      try {
        const data = await api('/api/passenger/cancel-ride/', 'POST', { ride_id: rideId });
        renderCurrentRide({ ride: null });
        showPassengerRideAnimation('cancelled', ride.vehicle_type || 'motorcycle');
        msg(data.detail || uiText('toast_ride_cancelled', 'Ride cancelled'), true);
      } catch (err) {
        msg(err.message);
      }
    });
  }
}

function renderReceiptPreview(ride) {
  const el = document.getElementById('receipt-output');
  if (!el || !ride) return;
  const breakdown = ride.fare_breakdown || null;
  if (!breakdown) {
    el.innerHTML = `<div class="receipt-board">
      <div class="mini-row"><span>Receipt</span><strong>Ride #${escapeHtml(ride.id)}</strong></div>
      <div class="ride-secondary-actions">
        <a class="call-link" href="/receipt/${ride.id}/" target="_blank">View</a>
        <a class="call-link" href="/receipt/${ride.id}/?print=1" target="_blank">Download PDF</a>
      </div>
    </div>`;
    return;
  }
  el.innerHTML = `
    <article class="mini-card receipt-board">
      <div class="mini-row"><span>Base Fare</span><strong>${escapeHtml(breakdown.base_fare)} TZS</strong></div>
      <div class="mini-row"><span>Price/KM</span><strong>${escapeHtml(breakdown.price_per_km)} TZS</strong></div>
      <div class="mini-row"><span>Surge</span><strong>x ${escapeHtml(breakdown.surge_multiplier)}</strong></div>
      <div class="mini-row"><span>Discount</span><strong>- ${escapeHtml(breakdown.discount_amount)} TZS</strong></div>
      <div class="mini-row"><span>Total</span><strong>${escapeHtml(breakdown.final_fare)} TZS</strong></div>
      <div class="mini-row"><span>Receipt</span>
        <span>
          <a class="call-link" href="/receipt/${ride.id}/" target="_blank">Open</a>
          <a class="call-link" href="/receipt/${ride.id}/?print=1" target="_blank">Download PDF</a>
        </span>
      </div>
    </article>
  `;
}

function renderChatMessages(container, messages, selfId) {
  if (!container) return;
  if (!messages.length) {
    container.innerHTML = emptyUi('empty_no_messages', 'No messages yet.');
    return;
  }
  container.innerHTML = messages
    .map((msg) => {
      const isSelf = msg.sender_id === selfId;
      return `
        <div class="chat-bubble ${isSelf ? 'self' : 'other'}">
          <strong>${escapeHtml(msg.sender_name || '')}</strong><br/>
          ${escapeHtml(msg.message)}
        </div>
      `;
    })
    .join('');
  container.scrollTop = container.scrollHeight;
}

function setupChat({ listId, inputId, sendBtnId, rideIdGetter }) {
  const listEl = document.getElementById(listId);
  const inputEl = document.getElementById(inputId);
  const sendBtn = document.getElementById(sendBtnId);
  if (!listEl || !inputEl || !sendBtn) return;

  const loadMessages = async () => {
    const rideId = rideIdGetter();
    if (!rideId) {
      listEl.innerHTML = emptyUi('empty_start_chat', 'Start a ride to chat.');
      return;
    }
    const data = await api(`/api/ride/chat/?ride_id=${rideId}`);
    renderChatMessages(listEl, data.messages || [], data.self_id || null);
  };

  sendBtn.addEventListener('click', async () => {
    const rideId = rideIdGetter();
    if (!rideId) {
      msg(uiText('toast_no_active_ride_for_chat', 'No active ride for chat'));
      return;
    }
    const message = inputEl.value.trim();
    if (!message) return;
    const payload = { ride_id: rideId, message };
    if (!navigator.onLine) {
      enqueueOfflineAction({ url: '/api/ride/chat/send/', method: 'POST', payload });
      inputEl.value = '';
      msg(uiText('toast_offline_message_queued', 'Offline: message queued'), true);
      return;
    }
    try {
      await api('/api/ride/chat/send/', 'POST', payload);
      inputEl.value = '';
      await loadMessages();
    } catch (err) {
      msg(err.message);
    }
  });

  loadMessages().catch(() => {});
  setInterval(() => loadMessages().catch(() => {}), 4000);
}

function renderRideHistory(data) {
  const el = document.getElementById('history-output');
  const rides = data.rides || [];
  if (!rides.length) {
    el.innerHTML = emptyUi('empty_no_history', 'No ride history yet.');
    return;
  }

  el.innerHTML = `
    <table class="mini-table">
      <thead>
        <tr><th>Ride</th><th>Driver</th><th>Vehicle</th><th>Status</th><th>Fare</th><th>Receipt</th></tr>
      </thead>
      <tbody>
        ${rides
          .map(
            (r) => `
              <tr>
                <td>#${escapeHtml(r.id)}</td>
                <td>#${escapeHtml(r.driver_id ?? '-')}</td>
                <td>${vehicleLabel(r.vehicle_type)}</td>
                <td>${escapeHtml(r.status)}</td>
                <td>TZS ${escapeHtml(r.fare_tzs)}</td>
                <td>
                  <a class="call-link" href="/receipt/${escapeHtml(r.id)}/" target="_blank">View</a>
                  <a class="call-link" href="/receipt/${escapeHtml(r.id)}/?print=1" target="_blank">PDF</a>
                </td>
              </tr>
            `
          )
          .join('')}
      </tbody>
    </table>
  `;
}

function renderIncomingRides(data) {
  const el = document.getElementById('incoming-output');
  const rides = data.rides || [];
  if (!rides.length) {
    el.innerHTML = emptyUi('empty_no_incoming_rides', 'No incoming rides right now.');
    return;
  }

  el.innerHTML = rides
    .map(
      (r) => `
        <article class="mini-card">
          <div class="mini-row"><span>Ride</span><strong>#${escapeHtml(r.id)}</strong></div>
          <div class="mini-row"><span>Pickup</span><strong>${escapeHtml(r.pickup_location ?? '-')}</strong></div>
          ${
            r.stops?.length
              ? `<div class="mini-row"><span>Stops</span><strong>${escapeHtml(r.stops.map((s) => s.name).join(', '))}</strong></div>`
              : ''
          }
          <div class="mini-row"><span>Dropoff</span><strong>${escapeHtml(r.dropoff_location ?? '-')}</strong></div>
          <div class="mini-row"><span>Distance</span><strong>${escapeHtml(r.distance_km)} km</strong></div>
          <div class="mini-row"><span>ETA</span><strong>${estimateEtaMinutes(Number(r.distance_km))} min</strong></div>
          <div class="mini-row"><span>Fare</span><strong>TZS ${escapeHtml(r.fare_tzs)}</strong></div>
          <div class="contact-card">
            ${
              sanitizeUrl(r.passenger?.profile_image_url)
                ? `<img class="avatar" src="${sanitizeUrl(r.passenger?.profile_image_url)}" alt="Passenger" />`
                : '<div class="avatar placeholder">P</div>'
            }
            <div>
              <strong>${escapeHtml(r.passenger?.name ?? 'Passenger')}</strong>
              <p>${escapeHtml(r.passenger?.phone_number ?? '-')}</p>
              ${
                sanitizePhone(r.passenger?.phone_number)
                  ? `<a class="call-link" href="tel:${encodeURIComponent(sanitizePhone(r.passenger?.phone_number))}">Call Passenger</a>`
                  : ''
              }
            </div>
          </div>
        </article>
      `
    )
    .join('');
}

function renderEarnings(data) {
  const el = document.getElementById('earnings-output');
  const entries = data.entries || [];
  const history = entries.length
    ? `
      <div class="mini-stack">
        ${entries
          .map(
            (entry) => `
              <div class="mini-row">
                <span>${escapeHtml(entry.entry_type)}${entry.ride_id ? ` · #${escapeHtml(entry.ride_id)}` : ''}</span>
                <strong>${Number(entry.amount_tzs) < 0 ? '-' : ''}TZS ${escapeHtml(Math.abs(Number(entry.amount_tzs || 0)).toString())}</strong>
              </div>
            `
          )
          .join('')}
      </div>
    `
    : `<div class="empty-ui">${escapeHtml(uiText('empty_no_commission_history', 'No commission history yet.'))}</div>`;
  el.innerHTML = `
    <article class="mini-card">
      <div class="mini-row"><span>Completed Rides</span><strong>${escapeHtml(data.completed_rides ?? 0)}</strong></div>
      <div class="mini-row"><span>Total Earnings</span><strong>TZS ${escapeHtml(data.total_earnings_tzs ?? 0)}</strong></div>
      <div class="mini-row"><span>Today's App Fees</span><strong>TZS ${escapeHtml(data.today_fees_tzs ?? 0)}</strong></div>
      <div class="mini-row"><span>Outstanding Balance</span><strong>TZS ${escapeHtml(data.outstanding_balance_tzs ?? 0)}</strong></div>
      <div class="mini-row"><span>Debt Limit</span><strong>TZS ${escapeHtml(data.debt_limit_tzs ?? 0)}</strong></div>
      <div class="mini-row"><span>Total Settled</span><strong>TZS ${escapeHtml(data.total_settled_tzs ?? 0)}</strong></div>
      <div class="mini-row"><span>Online Status</span><strong>${data.is_over_limit ? 'Settlement Required' : 'Clear to Operate'}</strong></div>
      <h5>Recent Commission Activity</h5>
      ${history}
    </article>
  `;
}

function renderSettlementInstructions(data) {
  const el = document.getElementById('driver-settlement-output');
  if (!el) return;
  const info = data.settlement_instructions || {};
  const outstanding = data.outstanding_balance_tzs || '0';
  el.innerHTML = `
    <article class="mini-card">
      <div class="mini-row"><span>Provider</span><strong>${escapeHtml(info.provider || '-')}</strong></div>
      <div class="mini-row"><span>Pay To</span><strong>${escapeHtml(info.phone_number || '-')}</strong></div>
      <div class="mini-row"><span>Reference</span><strong>${escapeHtml(info.reference || '-')}</strong></div>
      <div class="mini-row"><span>Outstanding</span><strong>TZS ${escapeHtml(outstanding)}</strong></div>
      <p class="mini-note">${escapeHtml(info.note || 'Use the reference when sending your weekly settlement payment.')}</p>
    </article>
  `;
}

function renderWeatherAdvisory(data) {
  const el = document.getElementById('weather-advisory-output');
  if (!el) return;
  if (!data || data.enabled === false) {
    el.innerHTML = emptyUi('empty_weather_disabled', 'Weather advisory is not active right now.');
    return;
  }
  const advisory = data.advisory || {};
  const strongVehicle = advisory.recommended_vehicle === 'bajaji' ? 'Bajaji' : 'Bodaboda';
  const action = advisory.recommended_vehicle === 'bajaji'
    ? `<button id="use-bajaji-recommendation-btn" type="button">Switch to Bajaji</button>`
    : '';
  el.innerHTML = `
    <article class="mini-card weather-card ${advisory.rain_expected ? 'rain-watch' : 'clear-sky'}">
      <div class="mini-row"><span>Current Weather</span><strong>${escapeHtml(advisory.weather_label || '-')}</strong></div>
      <div class="mini-row"><span>Temperature</span><strong>${escapeHtml(advisory.temperature_c ?? '-')}°C</strong></div>
      <div class="mini-row"><span>Rain Chance</span><strong>${escapeHtml(advisory.rain_probability_pct ?? 0)}%</strong></div>
      <div class="mini-row"><span>Current Rain</span><strong>${escapeHtml(advisory.current_precipitation_mm ?? 0)} mm</strong></div>
      <div class="mini-row"><span>Recommended Ride</span><strong>${escapeHtml(strongVehicle)}</strong></div>
      <p class="mini-note">${escapeHtml(advisory.advice || '')}</p>
      ${action}
    </article>
  `;
  const switchBtn = document.getElementById('use-bajaji-recommendation-btn');
  if (switchBtn) {
    switchBtn.addEventListener('click', () => {
      const vehicleSelect = document.getElementById('ride-vehicle-type');
      if (vehicleSelect) {
        vehicleSelect.value = 'bajaji';
        syncRideOptionCards();
        updateRoutePreview();
      }
    });
  }
}

const zanzibarLocations = {
  stone_town: { name: 'Stone Town', lat: -6.1659, lng: 39.2026 },
  malindi: { name: 'Malindi', lat: -6.1643, lng: 39.1894 },
  forodhani: { name: 'Forodhani', lat: -6.1629, lng: 39.1936 },
  darajani: { name: 'Darajani', lat: -6.1669, lng: 39.2085 },
  mlandege: { name: 'Mlandege', lat: -6.1758, lng: 39.2127 },
  amaan_stadium: { name: 'Amaan Stadium', lat: -6.1585, lng: 39.1897 },
  chukwani: { name: 'Chukwani', lat: -6.2238, lng: 39.2152 },
  kisauni_airport: { name: 'Kisauni Airport', lat: -6.222, lng: 39.2247 },
  fumba: { name: 'Fumba', lat: -6.3189, lng: 39.2502 },
  bweleo: { name: 'Bweleo', lat: -6.3134, lng: 39.3246 },
  dunga: { name: 'Dunga', lat: -6.2703, lng: 39.2893 },
  mwera: { name: 'Mwera', lat: -6.2504, lng: 39.3053 },
  mangapwani: { name: 'Mangapwani', lat: -6.0053, lng: 39.1758 },
  mkokotoni: { name: 'Mkokotoni', lat: -5.8796, lng: 39.2205 },
  nungwi: { name: 'Nungwi', lat: -5.7265, lng: 39.2933 },
  kendwa: { name: 'Kendwa', lat: -5.7374, lng: 39.2985 },
  kiwengwa: { name: 'Kiwengwa', lat: -5.9892, lng: 39.3763 },
  matemwe: { name: 'Matemwe', lat: -5.8857, lng: 39.3677 },
  paje: { name: 'Paje', lat: -6.2649, lng: 39.5358 },
  jambiani: { name: 'Jambiani', lat: -6.3239, lng: 39.5616 },
  michamvi: { name: 'Michamvi', lat: -6.1849, lng: 39.5101 },
  chwaka: { name: 'Chwaka', lat: -6.1596, lng: 39.4362 },
  makunduchi: { name: 'Makunduchi', lat: -6.3466, lng: 39.5535 },
  kwanyanya: { name: 'Kwanyanya', lat: -6.1628, lng: 39.2041 },
  mbuzini_hospital: { name: 'Mbuzini Hospital', lat: -6.1745, lng: 39.2178 },
  njia_ya_kama: { name: 'Njia ya Kama', lat: -6.1492, lng: 39.2135 },
  bububu_skuli: { name: 'Bububu Skuli', lat: -6.1029, lng: 39.2451 },
  kidichi: { name: 'Kidichi', lat: -6.0903, lng: 39.2338 },
  njia_ya_bumbwini: { name: 'Njia ya Bumbwini', lat: -6.0668, lng: 39.2214 },
};

function applyLocations(locations) {
  if (!Array.isArray(locations) || !locations.length) return;
  Object.keys(zanzibarLocations).forEach((key) => delete zanzibarLocations[key]);
  locations.forEach((loc) => {
    if (!loc || !loc.key) return;
    zanzibarLocations[loc.key] = { name: loc.name, lat: loc.lat, lng: loc.lng };
  });

  const pickupSelect = document.getElementById('pickup-location');
  const dropoffSelect = document.getElementById('dropoff-location');
  const optionsHtml = locations.map((loc) => `<option value="${loc.key}">${loc.name}</option>`).join('');
  if (pickupSelect) pickupSelect.innerHTML = optionsHtml;
  if (dropoffSelect) dropoffSelect.innerHTML = optionsHtml;
}

async function loadLocations() {
  try {
    const res = await fetch('/api/locations/');
    if (!res.ok) return;
    const data = await res.json();
    if (data.locations) {
      applyLocations(data.locations);
    }
  } catch {
    // Non-blocking.
  }
}

let passengerMap = null;
let passengerRouteLayer = null;
let passengerNearbyLayer = null;
let passengerLiveLayer = null;
let simulatedDriverMarker = null;
let simulatedDriverInterval = null;
let simulatedDriverState = {
  rideId: null,
  phase: null,
  progress: 0,
  from: null,
  to: null,
  label: 'Driver',
  vehicleType: 'motorcycle',
};

let driverMap = null;
let driverSelfLayer = null;
let driverIncomingLayer = null;
let passengerCurrentRideId = null;
let driverCurrentRideId = null;

function clearSimulatedDriverMovement() {
  if (simulatedDriverInterval) {
    clearInterval(simulatedDriverInterval);
    simulatedDriverInterval = null;
  }
  if (passengerLiveLayer) {
    passengerLiveLayer.clearLayers();
  }
  simulatedDriverMarker = null;
  simulatedDriverState = {
    rideId: null,
    phase: null,
    progress: 0,
    from: null,
    to: null,
    label: 'Driver',
    vehicleType: 'motorcycle',
  };
}

function toNumber(value) {
  const parsed = parseFloat(value);
  return Number.isNaN(parsed) ? null : parsed;
}

function interpolatePoint(from, to, progress) {
  return [
    from[0] + (to[0] - from[0]) * progress,
    from[1] + (to[1] - from[1]) * progress,
  ];
}

function createSimulatedDriverMarker(point, label, vehicleType) {
  const color = vehicleType === 'bajaji' ? '#d97706' : '#2563eb';
  return L.circleMarker(point, {
    radius: 9,
    color,
    fillColor: color,
    fillOpacity: 0.78,
    weight: 2,
  }).bindPopup(`Driver: ${label}`);
}

function resolveSimulationPhase(ride) {
  if (ride.status === 'started') return 'to_dropoff';
  if (ride.status === 'accepted' || ride.status === 'requested') return 'to_pickup';
  if (ride.status === 'completed') return 'completed';
  return 'to_pickup';
}

function configureSimulationState(ride) {
  const pickupLat = toNumber(ride.pickup_lat);
  const pickupLng = toNumber(ride.pickup_lng);
  const dropoffLat = toNumber(ride.dropoff_lat);
  const dropoffLng = toNumber(ride.dropoff_lng);
  if (pickupLat === null || pickupLng === null || dropoffLat === null || dropoffLng === null) return null;

  const driverLat = toNumber(ride?.driver?.latitude);
  const driverLng = toNumber(ride?.driver?.longitude);

  const pickup = [pickupLat, pickupLng];
  const dropoff = [dropoffLat, dropoffLng];
  const phase = resolveSimulationPhase(ride);

  let from = pickup;
  let to = pickup;
  if (phase === 'to_pickup') {
    from = driverLat !== null && driverLng !== null ? [driverLat, driverLng] : pickup;
    to = pickup;
  } else if (phase === 'to_dropoff' || phase === 'completed') {
    from = driverLat !== null && driverLng !== null ? [driverLat, driverLng] : pickup;
    to = dropoff;
  }

  return { from, to, phase, pickup, dropoff };
}

function stepSimulatedDriver() {
  if (!simulatedDriverMarker || !simulatedDriverState.from || !simulatedDriverState.to) return;

  const stepSize = simulatedDriverState.phase === 'to_dropoff' ? 0.14 : 0.1;
  simulatedDriverState.progress = Math.min(1, simulatedDriverState.progress + stepSize);
  const basePoint = interpolatePoint(simulatedDriverState.from, simulatedDriverState.to, simulatedDriverState.progress);

  const jitterLat = (Math.random() - 0.5) * 0.0001;
  const jitterLng = (Math.random() - 0.5) * 0.0001;
  const animatedPoint = [basePoint[0] + jitterLat, basePoint[1] + jitterLng];
  simulatedDriverMarker.setLatLng(animatedPoint);

  if (simulatedDriverState.progress >= 1) {
    if (simulatedDriverState.phase === 'to_pickup') {
      simulatedDriverState.phase = 'to_dropoff';
      simulatedDriverState.progress = 0;
      simulatedDriverState.from = simulatedDriverState.to;
      const rideDropoff = simulatedDriverState.dropoff || simulatedDriverState.to;
      simulatedDriverState.to = rideDropoff;
      return;
    }
    if (simulatedDriverInterval) {
      clearInterval(simulatedDriverInterval);
      simulatedDriverInterval = null;
    }
  }
}

function initPassengerMap() {
  if (!window.L || passengerMap) return;
  const mapNode = document.getElementById('passenger-map');
  if (!mapNode) return;

  passengerMap = L.map(mapNode).setView([-6.165917, 39.202641], 13);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19,
    attribution: '&copy; OpenStreetMap contributors',
  }).addTo(passengerMap);

  passengerRouteLayer = L.layerGroup().addTo(passengerMap);
  passengerNearbyLayer = L.layerGroup().addTo(passengerMap);
  passengerLiveLayer = L.layerGroup().addTo(passengerMap);
}

function initDriverMap() {
  if (!window.L || driverMap) return;
  const mapNode = document.getElementById('driver-map');
  if (!mapNode) return;

  driverMap = L.map(mapNode).setView([-6.165917, 39.202641], 13);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19,
    attribution: '&copy; OpenStreetMap contributors',
  }).addTo(driverMap);

  driverSelfLayer = L.layerGroup().addTo(driverMap);
  driverIncomingLayer = L.layerGroup().addTo(driverMap);
}

function fitMapToPoints(map, points) {
  if (!map || points.length === 0) return;
  if (points.length === 1) {
    map.setView(points[0], 14);
    return;
  }
  const bounds = L.latLngBounds(points);
  map.fitBounds(bounds, { padding: [28, 28] });
}

function syncPassengerRouteMap(pickup, dropoff, stops) {
  initPassengerMap();
  if (!passengerMap || !pickup || !dropoff) return;

  passengerRouteLayer.clearLayers();
  const pickupPoint = [pickup.lat, pickup.lng];
  const dropoffPoint = [dropoff.lat, dropoff.lng];

  L.marker(pickupPoint).bindPopup(`Pickup: ${pickup.name}`).addTo(passengerRouteLayer);
  (stops || []).forEach((stop) => {
    L.marker([stop.lat, stop.lng]).bindPopup(`Stop: ${stop.name}`).addTo(passengerRouteLayer);
  });
  L.marker(dropoffPoint).bindPopup(`Dropoff: ${dropoff.name}`).addTo(passengerRouteLayer);
  const polylinePoints = [pickupPoint, ...(stops || []).map((s) => [s.lat, s.lng]), dropoffPoint];
  L.polyline(polylinePoints, { color: '#2563eb', weight: 4, opacity: 0.85 }).addTo(passengerRouteLayer);
  fitMapToPoints(passengerMap, polylinePoints);
}

function syncPassengerNearbyDriversMap(drivers) {
  initPassengerMap();
  if (!passengerMap || !passengerNearbyLayer) return;
  passengerNearbyLayer.clearLayers();

  const points = [];
  drivers.forEach((driver) => {
    if (typeof driver.latitude !== 'number' || typeof driver.longitude !== 'number') return;
    const point = [driver.latitude, driver.longitude];
    points.push(point);
    L.circleMarker(point, {
      radius: 7,
      color: '#16a34a',
      weight: 2,
      fillColor: '#22c55e',
      fillOpacity: 0.7,
    })
      .bindPopup(`${driver.name || `Driver #${driver.driver_id}`} (${vehicleLabel(driver.vehicle_type)})`)
      .addTo(passengerNearbyLayer);
  });

  if (points.length) {
    fitMapToPoints(passengerMap, points);
  }
}

function syncPassengerLiveDriverMap(ride) {
  initPassengerMap();
  if (!passengerMap || !passengerLiveLayer) return;
  if (!ride) {
    clearSimulatedDriverMovement();
    return;
  }

  const simulationConfig = configureSimulationState(ride);
  if (!simulationConfig) return;

  const rideChanged = simulatedDriverState.rideId !== ride.id || simulatedDriverState.phase !== simulationConfig.phase;
  if (rideChanged) {
    passengerLiveLayer.clearLayers();
    simulatedDriverState = {
      rideId: ride.id,
      phase: simulationConfig.phase,
      progress: simulationConfig.phase === 'completed' ? 1 : 0,
      from: simulationConfig.from,
      to: simulationConfig.to,
      pickup: simulationConfig.pickup,
      dropoff: simulationConfig.dropoff,
      label: ride?.driver?.name || 'Driver',
      vehicleType: ride?.driver?.vehicle_type || 'motorcycle',
    };
    const initialPoint =
      simulatedDriverState.phase === 'completed'
        ? simulatedDriverState.to
        : interpolatePoint(simulatedDriverState.from, simulatedDriverState.to, 0);
    simulatedDriverMarker = createSimulatedDriverMarker(
      initialPoint,
      `${simulatedDriverState.label} (${vehicleLabel(simulatedDriverState.vehicleType)})`,
      simulatedDriverState.vehicleType
    ).addTo(passengerLiveLayer);
    fitMapToPoints(passengerMap, [simulationConfig.pickup, simulationConfig.dropoff, initialPoint]);
  }

  if (simulatedDriverState.phase === 'completed') {
    if (simulatedDriverInterval) {
      clearInterval(simulatedDriverInterval);
      simulatedDriverInterval = null;
    }
    return;
  }

  if (!simulatedDriverInterval) {
    simulatedDriverInterval = setInterval(stepSimulatedDriver, 2500);
  }
}

function syncDriverSelfMap(lat, lng) {
  initDriverMap();
  if (!driverMap || !driverSelfLayer || Number.isNaN(lat) || Number.isNaN(lng)) return;
  driverSelfLayer.clearLayers();
  const point = [lat, lng];
  L.marker(point).bindPopup('Your current location').addTo(driverSelfLayer);
  fitMapToPoints(driverMap, [point]);
}

function syncDriverIncomingRideMap(ride) {
  initDriverMap();
  if (!driverMap || !driverIncomingLayer) return;
  driverIncomingLayer.clearLayers();
  if (!ride) return;

  const pickup = [parseFloat(ride.pickup_lat), parseFloat(ride.pickup_lng)];
  const dropoff = [parseFloat(ride.dropoff_lat), parseFloat(ride.dropoff_lng)];
  const stop = ride.stops && ride.stops.length > 0 ? ride.stops[0] : null;
  if (Number.isNaN(pickup[0]) || Number.isNaN(pickup[1]) || Number.isNaN(dropoff[0]) || Number.isNaN(dropoff[1])) return;

  L.marker(pickup).bindPopup(`Pickup: ${ride.pickup_location || 'Location'}`).addTo(driverIncomingLayer);
  if (stop) {
    L.marker([stop.latitude, stop.longitude]).bindPopup(`Stop: ${stop.name}`).addTo(driverIncomingLayer);
  }
  L.marker(dropoff).bindPopup(`Dropoff: ${ride.dropoff_location || 'Location'}`).addTo(driverIncomingLayer);
  const points = stop ? [pickup, [stop.latitude, stop.longitude], dropoff] : [pickup, dropoff];
  L.polyline(points, { color: '#f59e0b', weight: 4, opacity: 0.85 }).addTo(driverIncomingLayer);
  fitMapToPoints(driverMap, points);
}

function toRad(value) {
  return (value * Math.PI) / 180;
}

function haversineKm(a, b) {
  const R = 6371;
  const dLat = toRad(b.lat - a.lat);
  const dLng = toRad(b.lng - a.lng);
  const x =
    Math.sin(dLat / 2) * Math.sin(dLat / 2) +
    Math.cos(toRad(a.lat)) * Math.cos(toRad(b.lat)) * Math.sin(dLng / 2) * Math.sin(dLng / 2);
  const y = 2 * Math.atan2(Math.sqrt(x), Math.sqrt(1 - x));
  return R * y;
}

function selectedRoute() {
  const pickupKey = document.getElementById('pickup-location').value;
  const dropoffKey = document.getElementById('dropoff-location').value;
  const vehicleType = document.getElementById('ride-vehicle-type').value;
  return {
    vehicleType,
    pickup: zanzibarLocations[pickupKey],
    dropoff: zanzibarLocations[dropoffKey],
  };
}

function estimateEtaMinutes(distanceKm) {
  const avgSpeedKmH = 25;
  const minutes = (distanceKm / avgSpeedKmH) * 60;
  return Math.max(4, Math.round(minutes));
}

function updateRoutePreview() {
  const { vehicleType, pickup, dropoff } = selectedRoute();
  if (!pickup || !dropoff) {
    return;
  }
  const roundedKm = Math.max(0.5, Math.round(haversineKm(pickup, dropoff) * 100) / 100);
  const estimateFare = (type) => {
    const baseFare = type === 'bajaji' ? 2500 : 1500;
    return Math.round(baseFare + roundedKm * 700);
  };
  const fare = estimateFare(vehicleType);
  const motorcycleFare = estimateFare('motorcycle');
  const bajajiFare = estimateFare('bajaji');
  const etaPreview = document.getElementById('eta-preview');
  const fareLabel = document.getElementById('fare-preview-label');
  const motorcycleFareEl = document.getElementById('ride-card-motorcycle-fare');
  const bajajiFareEl = document.getElementById('ride-card-bajaji-fare');
  const motorcycleMetaEl = document.getElementById('ride-card-motorcycle-meta');
  const bajajiMetaEl = document.getElementById('ride-card-bajaji-meta');
  document.getElementById('distance-preview').textContent = `${roundedKm.toFixed(2)} km`;
  document.getElementById('fare-preview').textContent = `TZS ${fare.toLocaleString()}`;
  if (etaPreview) etaPreview.value = `${estimateEtaMinutes(roundedKm)} min`;
  if (fareLabel) {
    fareLabel.textContent = vehicleType === 'bajaji'
      ? uiText('fare_label_bajaji', 'Estimated Fare (Bajaji)')
      : uiText('fare_label', 'Estimated Fare (Motorcycle)');
  }
  if (motorcycleFareEl) motorcycleFareEl.textContent = `TZS ${motorcycleFare.toLocaleString()}`;
  if (bajajiFareEl) bajajiFareEl.textContent = `TZS ${bajajiFare.toLocaleString()}`;
  if (motorcycleMetaEl) motorcycleMetaEl.textContent = `${estimateEtaMinutes(roundedKm)} min • 1 seat`;
  if (bajajiMetaEl) bajajiMetaEl.textContent = `${Math.max(5, estimateEtaMinutes(roundedKm) + 1)} min • 3 seats`;
  syncPassengerRouteMap(pickup, dropoff);
}

function syncRideOptionCards() {
  const vehicleField = document.getElementById('ride-vehicle-type');
  if (!vehicleField) return;
  document.querySelectorAll('[data-vehicle-option]').forEach((card) => {
    const isSelected = card.dataset.vehicleOption === vehicleField.value;
    card.classList.toggle('selected', isSelected);
    card.setAttribute('aria-pressed', isSelected ? 'true' : 'false');
  });
}

function debounce(fn, delay = 400) {
  let timer = null;
  return (...args) => {
    if (timer) clearTimeout(timer);
    timer = setTimeout(() => fn(...args), delay);
  };
}

async function searchPlaces(query) {
  const trimmed = String(query || '').trim();
  if (!trimmed) return [];
  const now = Date.now();
  if (!searchPlaces.lastAt) searchPlaces.lastAt = 0;
  if (searchPlaces.inFlight) return [];
  if (now - searchPlaces.lastAt < 1200) return [];
  searchPlaces.lastAt = now;
  searchPlaces.inFlight = true;
  try {
    const res = await fetch(`/api/geo/search/?q=${encodeURIComponent(trimmed)}`);
    if (!res.ok) return [];
    const data = await res.json();
    return data.results || [];
  } finally {
    searchPlaces.inFlight = false;
  }
}

function renderSearchResults(container, results, onPick) {
  if (!container) return;
  if (!results.length) {
    container.innerHTML = '';
    return;
  }
  container.innerHTML = results
    .map(
      (r, idx) => `
        <button type="button" data-idx="${idx}">
          ${escapeHtml(r.display_name || 'Location')}
        </button>
      `
    )
    .join('');
  container.querySelectorAll('button').forEach((btn) => {
    btn.addEventListener('click', () => {
      const idx = parseInt(btn.dataset.idx, 10);
      const item = results[idx];
      if (!item) return;
      onPick({
        name: item.display_name || 'Custom Location',
        lat: parseFloat(item.lat),
        lng: parseFloat(item.lon),
      });
      container.innerHTML = '';
    });
  });
}

async function wirePassenger() {
  document.getElementById('passenger-panel').classList.remove('hidden');
  initPassengerMap();
  await loadLocations();
  const confirmModal = createConfirmModal();
  const passengerSosBtn = document.getElementById('passenger-sos-btn');
  const passengerRatingCard = document.getElementById('passenger-rating-card');
  const passengerRatingStars = document.getElementById('passenger-rating-stars');
  const passengerRatingTarget = document.getElementById('passenger-rating-target');
  const passengerRatingComment = document.getElementById('passenger-rating-comment');
  const passengerSubmitRatingBtn = document.getElementById('passenger-submit-rating-btn');
  const passengerLanguageSelect = document.getElementById('passenger-language');
  const passengerEmailInput = document.getElementById('passenger-email');
  const profileCard = document.getElementById('passenger-profile-card');
  const profileSettings = document.getElementById('passenger-profile-settings');
  const profileCloseBtn = document.getElementById('close-passenger-settings');
  const paymentModal = document.getElementById('payment-setup-modal');
  const paymentCashOption = document.getElementById('payment-cash-option');
  const paymentContinue = document.getElementById('payment-continue-btn');
  const paymentCashSetting = document.getElementById('payment-cash-setting');
  const savePaymentSettingsBtn = document.getElementById('save-payment-settings-btn');
  const paymentCashCard = document.getElementById('payment-cash-card');
  const scheduledOutput = document.getElementById('scheduled-output');
  const refreshWeatherBtn = document.getElementById('refresh-weather-btn');
  let pendingPassengerRating = null;
  const loadPassengerProfile = async () => {
    const data = await api('/api/passenger/profile/me/');
    const profile = data.profile;
    window.currentPassengerId = profile.id;
    document.getElementById('passenger-name').value = profile.name || '';
    document.getElementById('passenger-phone').value = profile.phone_number || '';
    if (passengerEmailInput) passengerEmailInput.value = profile.email || '';
    const profileAvatar = document.getElementById('passenger-profile-avatar');
    const profileName = document.getElementById('passenger-profile-name');
    const profileEmail = document.getElementById('passenger-profile-email');
    const safePassengerImg = sanitizeUrl(profile.profile_image_url);
    if (profileAvatar) {
      if (safePassengerImg) {
        profileAvatar.style.backgroundImage = `url('${safePassengerImg}')`;
        profileAvatar.textContent = '';
      } else {
        profileAvatar.style.backgroundImage = '';
        profileAvatar.textContent = (profile.name || 'P').slice(0, 1).toUpperCase();
      }
    }
    if (profileName) profileName.textContent = profile.name || 'Passenger';
    if (profileEmail) profileEmail.textContent = profile.email || profile.phone_number || '';
    updateIdentityAvatar(profile.profile_image_url, profile.name || '');
    const passengerProfilePreview = document.getElementById('passenger-profile-preview');
    if (passengerProfilePreview) {
      passengerProfilePreview.innerHTML = `
        <div class="contact-card">
          ${
            safePassengerImg
              ? `<img class="avatar" src="${safePassengerImg}" alt="Passenger" />`
              : '<div class="avatar placeholder">P</div>'
          }
          <div>
            <strong>${escapeHtml(profile.name || '-')}</strong>
            <p>${escapeHtml(profile.phone_number || '-')}</p>
          </div>
        </div>
      `;
    }
    if (passengerLanguageSelect) {
      const lang = profile.language || (window.getAppLanguage ? window.getAppLanguage() : 'en');
      passengerLanguageSelect.value = lang;
      if (window.setAppLanguage) window.setAppLanguage(lang);
    }

    if (paymentModal) {
      const key = `payment_setup_done_${profile.id}`;
      const done = localStorage.getItem(key) === '1';
      if (paymentCashSetting) {
        paymentCashSetting.checked = done;
      }
      if (paymentCashCard) {
        paymentCashCard.classList.toggle('is-selected', done);
      }
      if (!done) {
        paymentModal.classList.remove('hidden');
      }
      if (paymentContinue) {
        paymentContinue.addEventListener('click', () => {
          localStorage.setItem(key, '1');
          paymentModal.classList.add('hidden');
          if (paymentCashSetting) paymentCashSetting.checked = true;
          if (paymentCashCard) paymentCashCard.classList.add('is-selected');
        });
      }
      if (paymentCashOption) {
        paymentCashOption.classList.add('is-selected');
        paymentCashOption.setAttribute('aria-pressed', 'true');
      }
    }
  };

    document.getElementById('save-passenger-profile-btn').addEventListener('click', async () => {
    try {
      const formData = new FormData();
      formData.append('full_name', document.getElementById('passenger-name').value.trim());
      formData.append('phone_number', document.getElementById('passenger-phone').value.trim());
      if (passengerEmailInput) {
        formData.append('email', passengerEmailInput.value.trim());
      }
      if (passengerLanguageSelect) {
        formData.append('language', passengerLanguageSelect.value);
        if (window.setAppLanguage) window.setAppLanguage(passengerLanguageSelect.value);
      }
      const image = document.getElementById('passenger-image').files[0];
      if (image) formData.append('profile_image', image);
      const data = await apiForm('/api/passenger/profile/update/', formData);
      msg(data.detail, true);
      await loadPassengerProfile();
    } catch (err) {
      msg(err.message);
    }
  });

  const loadEmergencyContacts = async () => {
    const data = await api('/api/emergency-contacts/');
    populateEmergencyContacts('passenger', data.contacts || []);
  };

  document.getElementById('save-passenger-emergency-btn').addEventListener('click', async () => {
    try {
      const contacts = emergencyContactsPayload('passenger');
      const data = await api('/api/emergency-contacts/upsert/', 'POST', { contacts });
      msg(uiTextFormat('toast_emergency_contacts_saved', { count: data.count }, 'Emergency contacts saved ({count})'), true);
    } catch (err) {
      msg(err.message);
    }
  });

  if (passengerLanguageSelect) {
    passengerLanguageSelect.addEventListener('change', async () => {
      const lang = passengerLanguageSelect.value;
      if (window.setAppLanguage) window.setAppLanguage(lang);
      try {
        const formData = new FormData();
        formData.append('language', lang);
        await apiForm('/api/passenger/profile/update/', formData);
      } catch (err) {
        msg(err.message);
      }
    });
  }

  if (savePaymentSettingsBtn && paymentCashSetting) {
    savePaymentSettingsBtn.addEventListener('click', () => {
      const profileId = window.currentPassengerId || null;
      const key = profileId ? `payment_setup_done_${profileId}` : 'payment_setup_done';
      if (!paymentCashSetting.checked) {
        msg(uiText('toast_cash_payment_required', 'Cash payment must be selected'), false);
        return;
      }
      localStorage.setItem(key, '1');
      if (paymentCashCard) paymentCashCard.classList.add('is-selected');
      msg(uiText('toast_payment_saved', 'Payment preference saved'), true);
    });
  }

  if (paymentCashCard && paymentCashSetting) {
    paymentCashCard.addEventListener('click', () => {
      paymentCashSetting.checked = true;
      paymentCashCard.classList.add('is-selected');
    });
  }
  if (paymentCashOption) {
    paymentCashOption.addEventListener('click', () => {
      paymentCashOption.classList.add('is-selected');
      paymentCashOption.setAttribute('aria-pressed', 'true');
      if (paymentCashSetting) paymentCashSetting.checked = true;
    });
  }

  if (profileCard && profileSettings) {
    const openSettings = () => {
      profileSettings.classList.remove('hidden');
      profileSettings.setAttribute('aria-hidden', 'false');
      profileSettings.scrollIntoView({ behavior: 'smooth', block: 'start' });
    };
    profileCard.addEventListener('click', openSettings);
    profileCard.addEventListener('keypress', (event) => {
      if (event.key === 'Enter') openSettings();
    });
    if (profileCloseBtn) {
      profileCloseBtn.addEventListener('click', () => {
        profileSettings.classList.add('hidden');
        profileSettings.setAttribute('aria-hidden', 'true');
      });
    }
  }

  const deletePassengerBtn = document.getElementById('delete-passenger-account-btn');
  if (deletePassengerBtn) {
    deletePassengerBtn.addEventListener('click', async () => {
      const promptText = window.t ? window.t('account_delete_prompt') : 'Type DELETE to confirm account deletion.';
      const cancelText = window.t ? window.t('account_delete_cancelled') : 'Account deletion cancelled';
      const typed = window.prompt(promptText);
      if (typed !== 'DELETE') {
        msg(cancelText, false);
        return;
      }
      const password = window.prompt(uiText('prompt_delete_password', 'Enter your password to confirm deletion.'));
      if (!password) {
        msg(uiText('toast_password_required', 'Password confirmation required'), false);
        return;
      }
      try {
        await api('/api/profile/delete/', 'POST', { password });
        window.location.href = '/';
      } catch (err) {
        msg(err.message);
      }
    });
  }

  if (passengerSosBtn) {
    passengerSosBtn.addEventListener('click', async () => {
      const confirmed = window.confirm(uiText('confirm_sos_message', 'Send SOS alert now? This will notify admin and your emergency contacts.'));
      if (!confirmed) return;
      try {
        const coords = await getCurrentPositionAsync();
        const data = await api('/api/sos/trigger/', 'POST', {
          confirm: true,
          lat: coords.lat,
          lng: coords.lng,
        });
        msg(uiTextFormat('toast_sos_sent', { count: data.notified_contacts }, 'SOS sent successfully (contacts notified: {count})'), true);
      } catch (err) {
        msg(err.message);
      }
    });
  }

  const renderScheduledRides = (data) => {
    if (!scheduledOutput) return;
    const rides = data.rides || [];
    if (!rides.length) {
      scheduledOutput.innerHTML = emptyUi('empty_no_scheduled_rides', 'No scheduled rides yet.');
      return;
    }
    scheduledOutput.innerHTML = rides
      .map(
        (ride) => `
          <article class="mini-card">
            <div class="mini-row"><span>Ride</span><strong>#${escapeHtml(ride.id)}</strong></div>
            <div class="mini-row"><span>Pickup</span><strong>${escapeHtml(ride.pickup_location)}</strong></div>
            ${
              ride.stops?.length
                ? `<div class="mini-row"><span>Stops</span><strong>${escapeHtml(ride.stops.map((s) => s.name).join(', '))}</strong></div>`
                : ''
            }
            <div class="mini-row"><span>Dropoff</span><strong>${escapeHtml(ride.dropoff_location)}</strong></div>
            <div class="mini-row"><span>Vehicle</span><strong>${vehicleLabel(ride.vehicle_type)}</strong></div>
            <div class="mini-row"><span>Scheduled For</span><strong>${escapeHtml(ride.scheduled_for)}</strong></div>
            <div class="mini-row"><span>Fare</span><strong>TZS ${escapeHtml(ride.fare_tzs)}</strong></div>
            <div class="action-row">
              <button class="scheduled-update-btn" data-ride-id="${ride.id}" type="button">Update Time</button>
              <button class="scheduled-cancel-btn" data-ride-id="${ride.id}" type="button">Cancel</button>
            </div>
          </article>
        `
      )
      .join('');

    scheduledOutput.querySelectorAll('.scheduled-cancel-btn').forEach((btn) => {
      btn.addEventListener('click', async () => {
        const rideId = parseInt(btn.dataset.rideId, 10);
        const confirmed = await confirmModal({
          title: 'Cancel Scheduled Ride',
          message: 'Cancel this scheduled ride? This cannot be undone.',
        });
        if (!confirmed) return;
        try {
          const data = await api('/api/passenger/scheduled-ride/cancel/', 'POST', { ride_id: rideId });
          msg(data.detail, true);
          await loadScheduledRides();
        } catch (err) {
          msg(err.message);
        }
      });
    });

    scheduledOutput.querySelectorAll('.scheduled-update-btn').forEach((btn) => {
      btn.addEventListener('click', async () => {
        const rideId = parseInt(btn.dataset.rideId, 10);
        const dateValue = document.getElementById('schedule-date').value;
        const timeValue = document.getElementById('schedule-time').value;
        if (!dateValue || !timeValue) {
          msg(uiText('toast_select_new_datetime', 'Select a new date and time first'));
          return;
        }
        const confirmed = await confirmModal({
          title: 'Reschedule Ride',
          message: `Reschedule ride #${rideId} to ${dateValue} ${timeValue}?`,
        });
        if (!confirmed) return;
        try {
          const data = await api('/api/passenger/scheduled-ride/update/', 'POST', {
            ride_id: rideId,
            date: dateValue,
            time: timeValue,
          });
          msg(data.detail, true);
          await loadScheduledRides();
        } catch (err) {
          msg(err.message);
        }
      });
    });
  };

  const loadScheduledRides = async () => {
    const data = await api('/api/passenger/scheduled-rides/');
    renderScheduledRides(data);
  };

  const loadWeatherAdvisory = async () => {
    const { pickup } = selectedRoute();
    if (!pickup) return;
    try {
      const data = await api(`/api/passenger/weather-advisory/?lat=${pickup.lat}&lng=${pickup.lng}`);
      renderWeatherAdvisory(data);
    } catch (err) {
      const weatherOutput = document.getElementById('weather-advisory-output');
      if (weatherOutput) {
        weatherOutput.innerHTML = `<div class="empty-ui">${escapeHtml(err.message || 'Weather service is unavailable right now.')}</div>`;
      }
    }
  };

  const showPassengerRatingPrompt = (item) => {
    pendingPassengerRating = item;
    if (!passengerRatingCard || !passengerRatingTarget) return;
    passengerRatingTarget.textContent = `${item.target_name} (Driver)`;
    passengerRatingCard.classList.remove('hidden');
  };

  const clearPassengerRatingPrompt = () => {
    pendingPassengerRating = null;
    if (!passengerRatingCard) return;
    passengerRatingCard.classList.add('hidden');
    if (passengerRatingStars) {
      passengerRatingStars.dataset.value = '0';
      passengerRatingStars.querySelectorAll('button').forEach((btn) => btn.classList.remove('active'));
    }
    if (passengerRatingComment) passengerRatingComment.value = '';
  };

  const loadPassengerPendingRatings = async () => {
    const data = await api('/api/ride/pending-ratings/');
    const pending = data.pending || [];
    if (pending.length) {
      showPassengerRatingPrompt(pending[0]);
      return;
    }
    clearPassengerRatingPrompt();
  };

  setupRatingStars(passengerRatingStars);
  if (passengerSubmitRatingBtn) {
    passengerSubmitRatingBtn.addEventListener('click', async () => {
      if (!pendingPassengerRating) return;
      const value = parseInt(passengerRatingStars.dataset.value || '0', 10);
      if (!value) {
        msg(uiText('toast_select_rating', 'Select a rating first'));
        return;
      }
      try {
        const data = await api('/api/ride/rate/', 'POST', {
          ride_id: pendingPassengerRating.ride_id,
          rating: value,
          comment: passengerRatingComment.value.trim(),
        });
        msg(data.detail, true);
        await loadPassengerPendingRatings();
      } catch (err) {
        msg(err.message);
      }
    });
  }

  loadPassengerProfile().catch(() => {});
  loadEmergencyContacts().catch(() => {});
  loadScheduledRides().catch(() => {});
  loadPassengerPendingRatings().catch(() => {});
  document.querySelectorAll('[data-vehicle-option]').forEach((card) => {
    card.addEventListener('click', () => {
      const vehicleField = document.getElementById('ride-vehicle-type');
      if (!vehicleField) return;
      vehicleField.value = card.dataset.vehicleOption || 'motorcycle';
      syncRideOptionCards();
      updateRoutePreview();
    });
  });
  syncRideOptionCards();
  updateRoutePreview();
  loadWeatherAdvisory().catch(() => {});
  document.getElementById('ride-vehicle-type').addEventListener('change', updateRoutePreview);
  document.getElementById('pickup-location').addEventListener('change', () => {
    updateRoutePreview();
    loadWeatherAdvisory().catch(() => {});
  });
  document.getElementById('dropoff-location').addEventListener('change', updateRoutePreview);
  if (refreshWeatherBtn) {
    refreshWeatherBtn.addEventListener('click', () => {
      loadWeatherAdvisory()
        .then(() => msg('Weather advisory updated', true))
        .catch((err) => msg(err.message));
    });
  }

  document.getElementById('check-nearby-btn').addEventListener('click', async () => {
    try {
      const { vehicleType, pickup } = selectedRoute();
      const data = await api(
        `/api/passenger/nearby-drivers/?lat=${pickup.lat}&lng=${pickup.lng}&vehicle_type=${vehicleType}`
      );
      renderNearbyDrivers(data);
      syncPassengerNearbyDriversMap(data.drivers || []);
      msg(uiText('toast_nearby_drivers_loaded', 'Nearby drivers loaded'), true);
    } catch (err) {
      msg(err.message);
    }
  });

  document.getElementById('request-ride-btn').addEventListener('click', async () => {
    try {
      const { vehicleType, pickup, dropoff } = selectedRoute();
      if (!pickup || !dropoff) {
        msg(uiText('toast_pickup_dropoff_required', 'Select pickup and dropoff locations first'));
        return;
      }
      if (pickup.name === dropoff.name) {
        msg(uiText('toast_same_location', 'Pickup and dropoff cannot be the same location'));
        return;
      }
      const distanceKm = Math.max(0.5, Math.round(haversineKm(pickup, dropoff) * 100) / 100);
      const payload = {
        vehicle_type: vehicleType,
        pickup_lat: pickup.lat,
        pickup_lng: pickup.lng,
        dropoff_lat: dropoff.lat,
        dropoff_lng: dropoff.lng,
        distance_km: distanceKm,
        promo_code: document.getElementById('promo-code')?.value.trim() || '',
        request_id: generateRequestId(),
      };
      if (!navigator.onLine) {
        enqueueOfflineAction({ url: '/api/passenger/request-ride/', method: 'POST', payload });
        msg(uiText('toast_ride_queued', 'Offline: ride request queued'), true);
        return;
      }
      const data = await api('/api/passenger/request-ride/', 'POST', payload);
      renderCurrentRide({ ride: data.ride });
      showPassengerRideAnimation('requested', data.ride.vehicle_type || vehicleType);
      renderReceiptPreview(data.ride);
      msg(uiText('toast_ride_requested', 'Ride requested'), true);
    } catch (err) {
      msg(err.message);
    }
  });

  document.getElementById('schedule-ride-btn').addEventListener('click', async () => {
    try {
      const { vehicleType, pickup, dropoff } = selectedRoute();
      if (!pickup || !dropoff) {
        msg(uiText('toast_pickup_dropoff_required', 'Select pickup and dropoff locations first'));
        return;
      }
      if (pickup.name === dropoff.name) {
        msg(uiText('toast_same_location', 'Pickup and dropoff cannot be the same location'));
        return;
      }
      const dateValue = document.getElementById('schedule-date').value;
      const timeValue = document.getElementById('schedule-time').value;
      const distanceKm = Math.max(0.5, Math.round(haversineKm(pickup, dropoff) * 100) / 100);
      const payload = {
        vehicle_type: vehicleType,
        pickup_lat: pickup.lat,
        pickup_lng: pickup.lng,
        dropoff_lat: dropoff.lat,
        dropoff_lng: dropoff.lng,
        distance_km: distanceKm,
        date: dateValue,
        time: timeValue,
        promo_code: document.getElementById('promo-code')?.value.trim() || '',
        request_id: generateRequestId(),
      };
      if (!navigator.onLine) {
        enqueueOfflineAction({ url: '/api/passenger/schedule-ride/', method: 'POST', payload });
        msg(uiText('toast_scheduled_ride_queued', 'Offline: scheduled ride queued'), true);
        return;
      }
      const data = await api('/api/passenger/schedule-ride/', 'POST', payload);
      msg(data.detail, true);
      await loadScheduledRides();
    } catch (err) {
      msg(err.message);
    }
  });

  document.getElementById('load-history-btn').addEventListener('click', async () => {
    try {
      const data = await api('/api/passenger/ride-history/');
      renderRideHistory(data);
      msg(uiText('toast_history_loaded', 'History loaded'), true);
    } catch (err) {
      msg(err.message);
    }
  });

  async function refreshCurrentRide() {
    try {
      const data = await api('/api/passenger/current-ride/');
      renderCurrentRide(data);
      if (data.ride) renderReceiptPreview(data.ride);
      if (!data.ride) {
        passengerLastRideId = null;
        passengerLastRideStatus = null;
        passengerCurrentRideId = null;
        syncPassengerLiveDriverMap(null);
        if (passengerSosBtn) passengerSosBtn.classList.add('hidden');
        loadPassengerPendingRatings().catch(() => {});
        return;
      }

      const ride = data.ride;
      passengerCurrentRideId = ride.id;
      syncPassengerLiveDriverMap(ride);
      const changed =
        passengerLastRideId !== ride.id || passengerLastRideStatus !== ride.status;
      if (changed) {
        showPassengerRideAnimation(ride.status, ride.vehicle_type || 'motorcycle');
      }
      if (passengerSosBtn) passengerSosBtn.classList.remove('hidden');
      if (ride.status === 'completed') {
        loadPassengerPendingRatings().catch(() => {});
      }
      passengerLastRideId = ride.id;
      passengerLastRideStatus = ride.status;
    } catch {
      // No-op on polling failures
    }
  }

  refreshCurrentRide();
  setInterval(refreshCurrentRide, 5000);
  setupChat({
    listId: 'chat-messages',
    inputId: 'chat-input',
    sendBtnId: 'chat-send-btn',
    rideIdGetter: () => passengerCurrentRideId,
  });
}

async function wireDriver() {
  document.getElementById('driver-panel').classList.remove('hidden');
  initDriverMap();
  const driverSosBtn = document.getElementById('driver-sos-btn');
  const driverRatingCard = document.getElementById('driver-rating-card');
  const driverRatingStars = document.getElementById('driver-rating-stars');
  const driverRatingTarget = document.getElementById('driver-rating-target');
  const driverRatingComment = document.getElementById('driver-rating-comment');
  const driverSubmitRatingBtn = document.getElementById('driver-submit-rating-btn');
  const driverLanguageSelect = document.getElementById('driver-language');
  const driverNameInput = document.getElementById('driver-name');
  const driverEmailInput = document.getElementById('driver-email');
  const driverPhoneInput = document.getElementById('driver-phone');
  const driverProfileCard = document.getElementById('driver-profile-card');
  const driverProfileSettings = document.getElementById('driver-profile-settings');
  const driverCloseSettings = document.getElementById('close-driver-settings');
  let pendingDriverRating = null;
  const loadDriverProfile = async () => {
    const data = await api('/api/driver/profile/me/');
    const driver = data.driver;
    if (!driver) return;
    if (driverNameInput) driverNameInput.value = driver.name || '';
    if (driverEmailInput) driverEmailInput.value = driver.email || '';
    if (driverPhoneInput) driverPhoneInput.value = driver.phone_number || '';
    document.getElementById('vehicle-type').value = driver.vehicle_type || 'motorcycle';
    document.getElementById('license-number').value = driver.license_number || '';
    document.getElementById('plate-number').value = driver.plate_number || '';
    const safeDriverImg = sanitizeUrl(driver.profile_image_url);
    const driverProfileAvatar = document.getElementById('driver-profile-avatar');
    const driverProfileName = document.getElementById('driver-profile-name');
    const driverProfileEmail = document.getElementById('driver-profile-email');
    if (driverProfileAvatar) {
      if (safeDriverImg) {
        driverProfileAvatar.style.backgroundImage = `url('${safeDriverImg}')`;
        driverProfileAvatar.textContent = '';
      } else {
        driverProfileAvatar.style.backgroundImage = '';
        driverProfileAvatar.textContent = (driver.name || 'D').slice(0, 1).toUpperCase();
      }
    }
    if (driverProfileName) driverProfileName.textContent = driver.name || 'Driver';
    if (driverProfileEmail) driverProfileEmail.textContent = driver.email || driver.phone_number || '';
    updateIdentityAvatar(driver.profile_image_url, driver.name || '');
    document.getElementById('driver-profile-preview').innerHTML = `
      <div class="contact-card">
        ${
          safeDriverImg
            ? `<img class="avatar" src="${safeDriverImg}" alt="Driver" />`
            : '<div class="avatar placeholder">D</div>'
        }
        <div>
          <strong>${escapeHtml(driver.name || '-')}</strong>
          <p>${escapeHtml(driver.phone_number || '-')}</p>
          <p>${vehicleLabel(driver.vehicle_type)} | Plate: ${escapeHtml(driver.plate_number || '-')}</p>
        </div>
      </div>
    `;
    if (typeof driver.latitude === 'number' && typeof driver.longitude === 'number') {
      syncDriverSelfMap(driver.latitude, driver.longitude);
    }
    if (driverLanguageSelect) {
      const lang = driver.language || (window.getAppLanguage ? window.getAppLanguage() : 'en');
      driverLanguageSelect.value = lang;
      if (window.setAppLanguage) window.setAppLanguage(lang);
    }

    const stationNameNode = document.getElementById('driver-station-name');
    const stationStatusNode = document.getElementById('driver-station-status');
    if (stationNameNode) stationNameNode.textContent = driver.station_name || '-';
    if (stationStatusNode) {
      stationStatusNode.textContent = driver.station_verified
        ? uiText('status_verified', 'Verified')
        : uiText('status_unverified', 'Unverified');
      stationStatusNode.classList.toggle('verified', Boolean(driver.station_verified));
    }
  };

  const loadDriverDocuments = async () => {
    const data = await api('/api/driver/documents/');
    const docs = data.documents || [];
    const output = document.getElementById('driver-docs-output');
    if (!output) return;
    if (!docs.length) {
      output.innerHTML = emptyUi('empty_no_documents', 'No documents uploaded yet.');
      return;
    }
    output.innerHTML = docs
      .map(
        (doc) => `
          <article class="mini-card">
            <div class="mini-row"><span>Type</span><strong>${escapeHtml(doc.doc_type)}</strong></div>
            <div class="mini-row"><span>Status</span><strong>${escapeHtml(doc.status)}</strong></div>
            <div class="mini-row"><span>Scan</span><strong>${escapeHtml(doc.scan_status || 'pending')}</strong></div>
            ${
              doc.scan_message
                ? `<div class="mini-row"><span>Scan Note</span><strong>${escapeHtml(doc.scan_message)}</strong></div>`
                : ''
            }
            <div class="mini-row"><span>Notes</span><strong>${escapeHtml(doc.notes || '-')}</strong></div>
          </article>
        `
      )
      .join('');
  };

  document.getElementById('use-driver-location-btn').addEventListener('click', () => {
    if (!navigator.geolocation) {
      msg(uiText('toast_geolocation_unsupported', 'Geolocation not supported on this browser'));
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (position) => {
        const lat = Number(position.coords.latitude.toFixed(6));
        const lng = Number(position.coords.longitude.toFixed(6));
        document.getElementById('driver-lat').value = String(lat);
        document.getElementById('driver-lng').value = String(lng);
        syncDriverSelfMap(lat, lng);
        msg(uiText('toast_driver_location_updated', 'Driver location updated from GPS'), true);
      },
      () => msg(uiText('toast_location_unavailable', 'Unable to get your current location'))
    );
  });

  document.getElementById('save-driver-profile-btn').addEventListener('click', async () => {
    try {
      const formData = new FormData();
      if (driverNameInput) formData.append('full_name', driverNameInput.value.trim());
      if (driverPhoneInput) formData.append('phone_number', driverPhoneInput.value.trim());
      if (driverEmailInput) formData.append('email', driverEmailInput.value.trim());
      formData.append('vehicle_type', document.getElementById('vehicle-type').value);
      formData.append('license_number', document.getElementById('license-number').value.trim());
      formData.append('plate_number', document.getElementById('plate-number').value.trim());
      if (driverLanguageSelect) {
        formData.append('language', driverLanguageSelect.value);
        if (window.setAppLanguage) window.setAppLanguage(driverLanguageSelect.value);
      }
      const image = document.getElementById('driver-image').files[0];
      if (image) formData.append('profile_image', image);
      const data = await apiForm('/api/driver/profile/', formData);
      msg(data.detail, true);
      await loadDriverProfile();
    } catch (err) {
      msg(err.message);
    }
  });

  const uploadDocBtn = document.getElementById('upload-driver-doc-btn');
  if (uploadDocBtn) {
    uploadDocBtn.addEventListener('click', async () => {
      try {
        const formData = new FormData();
        formData.append('doc_type', document.getElementById('driver-doc-type').value);
        const file = document.getElementById('driver-doc-file').files[0];
        if (!file) {
          msg(uiText('toast_select_document', 'Select a document file first'));
          return;
        }
        formData.append('file', file);
        const data = await apiForm('/api/driver/documents/upload/', formData);
        msg(data.detail, true);
        await loadDriverDocuments();
      } catch (err) {
        msg(err.message);
      }
    });
  }

  const loadEmergencyContacts = async () => {
    const data = await api('/api/emergency-contacts/');
    populateEmergencyContacts('driver', data.contacts || []);
  };

  document.getElementById('save-driver-emergency-btn').addEventListener('click', async () => {
    try {
      const contacts = emergencyContactsPayload('driver');
      const data = await api('/api/emergency-contacts/upsert/', 'POST', { contacts });
      msg(uiTextFormat('toast_emergency_contacts_saved', { count: data.count }, 'Emergency contacts saved ({count})'), true);
    } catch (err) {
      msg(err.message);
    }
  });

  if (driverLanguageSelect) {
    driverLanguageSelect.addEventListener('change', async () => {
      const lang = driverLanguageSelect.value;
      if (window.setAppLanguage) window.setAppLanguage(lang);
      try {
        const formData = new FormData();
        formData.append('language', lang);
        if (driverNameInput) formData.append('full_name', driverNameInput.value.trim());
        if (driverPhoneInput) formData.append('phone_number', driverPhoneInput.value.trim());
        if (driverEmailInput) formData.append('email', driverEmailInput.value.trim());
        formData.append('vehicle_type', document.getElementById('vehicle-type').value);
        formData.append('license_number', document.getElementById('license-number').value.trim());
        formData.append('plate_number', document.getElementById('plate-number').value.trim());
        await apiForm('/api/driver/profile/', formData);
      } catch (err) {
        msg(err.message);
      }
    });
  }

  if (driverProfileCard && driverProfileSettings) {
    const openDriverSettings = () => {
      driverProfileSettings.classList.remove('hidden');
      driverProfileSettings.setAttribute('aria-hidden', 'false');
      driverProfileSettings.scrollIntoView({ behavior: 'smooth', block: 'start' });
    };
    driverProfileCard.addEventListener('click', openDriverSettings);
    driverProfileCard.addEventListener('keypress', (event) => {
      if (event.key === 'Enter') openDriverSettings();
    });
    if (driverCloseSettings) {
      driverCloseSettings.addEventListener('click', () => {
        driverProfileSettings.classList.add('hidden');
        driverProfileSettings.setAttribute('aria-hidden', 'true');
      });
    }
  }

  const deleteDriverBtn = document.getElementById('delete-driver-account-btn');
  if (deleteDriverBtn) {
    deleteDriverBtn.addEventListener('click', async () => {
      const promptText = window.t ? window.t('account_delete_prompt') : 'Type DELETE to confirm account deletion.';
      const cancelText = window.t ? window.t('account_delete_cancelled') : 'Account deletion cancelled';
      const typed = window.prompt(promptText);
      if (typed !== 'DELETE') {
        msg(cancelText, false);
        return;
      }
      const password = window.prompt(uiText('prompt_delete_password', 'Enter your password to confirm deletion.'));
      if (!password) {
        msg(uiText('toast_password_required', 'Password confirmation required'), false);
        return;
      }
      try {
        await api('/api/profile/delete/', 'POST', { password });
        window.location.href = '/';
      } catch (err) {
        msg(err.message);
      }
    });
  }

  if (driverSosBtn) {
    driverSosBtn.addEventListener('click', async () => {
      const confirmed = window.confirm(uiText('confirm_sos_message', 'Send SOS alert now? This will notify admin and your emergency contacts.'));
      if (!confirmed) return;
      try {
        const coords = await getCurrentPositionAsync();
        const data = await api('/api/sos/trigger/', 'POST', {
          confirm: true,
          lat: coords.lat,
          lng: coords.lng,
        });
        msg(uiTextFormat('toast_sos_sent', { count: data.notified_contacts }, 'SOS sent successfully (contacts notified: {count})'), true);
      } catch (err) {
        msg(err.message);
      }
    });
  }

  const showDriverRatingPrompt = (item) => {
    pendingDriverRating = item;
    if (!driverRatingCard || !driverRatingTarget) return;
    driverRatingTarget.textContent = `${item.target_name} (Passenger)`;
    driverRatingCard.classList.remove('hidden');
  };

  const clearDriverRatingPrompt = () => {
    pendingDriverRating = null;
    if (!driverRatingCard) return;
    driverRatingCard.classList.add('hidden');
    if (driverRatingStars) {
      driverRatingStars.dataset.value = '0';
      driverRatingStars.querySelectorAll('button').forEach((btn) => btn.classList.remove('active'));
    }
    if (driverRatingComment) driverRatingComment.value = '';
  };

  const loadDriverPendingRatings = async () => {
    const data = await api('/api/ride/pending-ratings/');
    const pending = data.pending || [];
    if (pending.length) {
      showDriverRatingPrompt(pending[0]);
      return;
    }
    clearDriverRatingPrompt();
  };

  setupRatingStars(driverRatingStars);
  if (driverSubmitRatingBtn) {
    driverSubmitRatingBtn.addEventListener('click', async () => {
      if (!pendingDriverRating) return;
      const value = parseInt(driverRatingStars.dataset.value || '0', 10);
      if (!value) {
        msg(uiText('toast_select_rating', 'Select a rating first'));
        return;
      }
      try {
        const data = await api('/api/ride/rate/', 'POST', {
          ride_id: pendingDriverRating.ride_id,
          rating: value,
          comment: driverRatingComment.value.trim(),
        });
        msg(data.detail, true);
        await loadDriverPendingRatings();
      } catch (err) {
        msg(err.message);
      }
    });
  }

  document.getElementById('go-online-btn').addEventListener('click', async () => {
    try {
      const lat = parseFloat(document.getElementById('driver-lat').value);
      const lng = parseFloat(document.getElementById('driver-lng').value);
      const data = await api('/api/driver/online/', 'POST', {
        lat,
        lng,
      });
      syncDriverSelfMap(lat, lng);
      msg(data.detail, true);
    } catch (err) {
      msg(err.message);
    }
  });

  document.getElementById('go-offline-btn').addEventListener('click', async () => {
    try {
      const data = await api('/api/driver/offline/', 'POST', {});
      msg(data.detail, true);
    } catch (err) {
      msg(err.message);
    }
  });

  async function loadIncoming() {
    const data = await api('/api/driver/incoming-rides/');
    renderIncomingRides(data);
    if (data.rides && data.rides.length > 0) {
      document.getElementById('driver-ride-id').value = data.rides[0].id;
      document.getElementById('driver-ride-status').value = data.rides[0].status || '';
      syncDriverIncomingRideMap(data.rides[0]);
      const latest = data.rides[0];
      if (!driverSeenIncomingIds.has(latest.id)) {
        driverSeenIncomingIds.add(latest.id);
        showDriverRideAnimation('incoming', 'motorcycle');
      }
    } else {
      syncDriverIncomingRideMap(null);
    }
  }

  async function refreshDriverCurrentRide() {
    try {
      const data = await api('/api/driver/current-ride/');
      if (driverSosBtn) {
        driverSosBtn.classList.toggle('hidden', !data.ride);
      }
      if (data.ride && !document.getElementById('driver-ride-id').value) {
        document.getElementById('driver-ride-id').value = data.ride.id;
      }
      driverCurrentRideId = data.ride ? data.ride.id : null;
      if (!data.ride || data.ride.status === 'completed') {
        loadDriverPendingRatings().catch(() => {});
      }
    } catch {
      // no-op
    }
  }

  document.getElementById('load-incoming-btn').addEventListener('click', async () => {
    try {
      await loadIncoming();
      msg(uiText('toast_incoming_loaded', 'Incoming rides loaded'), true);
    } catch (err) {
      msg(err.message);
    }
  });

  const rideAction = async (url) => {
    try {
      const rideId = parseInt(document.getElementById('driver-ride-id').value, 10);
      const data = await api(url, 'POST', { ride_id: rideId });
      if (url.includes('accept')) showDriverRideAnimation('accepted', document.getElementById('vehicle-type').value);
      if (url.includes('start')) showDriverRideAnimation('started', document.getElementById('vehicle-type').value);
      if (url.includes('complete')) showDriverRideAnimation('completed', document.getElementById('vehicle-type').value);
      if (url.includes('complete') && data.commission_fee_tzs) {
        msg(`Ride completed. App fee charged: TZS ${data.commission_fee_tzs}. Outstanding balance: TZS ${data.outstanding_balance_tzs}.`, true);
        const earnings = await api('/api/driver/earnings/');
        renderEarnings(earnings);
      } else {
        msg(data.detail, true);
      }
      await loadIncoming();
    } catch (err) {
      msg(err.message);
    }
  };

  document.getElementById('accept-ride-btn').addEventListener('click', () => rideAction('/api/driver/accept-ride/'));
  document.getElementById('start-ride-btn').addEventListener('click', () => rideAction('/api/driver/start-ride/'));
  document.getElementById('complete-ride-btn').addEventListener('click', () => rideAction('/api/driver/complete-ride/'));
  document.getElementById('cancel-ride-btn').addEventListener('click', async () => {
    try {
      const rideId = parseInt(document.getElementById('driver-ride-id').value, 10);
      const rideStatus = (document.getElementById('driver-ride-status').value || '').toLowerCase();
      if (!rideId) {
        msg(uiText('toast_no_ride_selected', 'No ride selected.'));
        return;
      }
      if (rideStatus === 'requested') {
        const data = await api('/api/driver/decline-ride/', 'POST', { ride_id: rideId });
        msg(data.detail, true);
        await loadIncoming();
        return;
      }
      const data = await api('/api/driver/cancel-ride/', 'POST', { ride_id: rideId });
      showDriverRideAnimation('cancelled', document.getElementById('vehicle-type').value);
      msg(data.detail, true);
      await loadIncoming();
    } catch (err) {
      msg(err.message);
    }
  });

  document.getElementById('load-earnings-btn').addEventListener('click', async () => {
    try {
      const data = await api('/api/driver/earnings/');
      renderEarnings(data);
      renderSettlementInstructions(data);
      msg(uiText('toast_earnings_loaded', 'Earnings loaded'), true);
    } catch (err) {
      msg(err.message);
    }
  });

  const refreshSettlementBtn = document.getElementById('refresh-settlement-btn');
  if (refreshSettlementBtn) {
    refreshSettlementBtn.addEventListener('click', async () => {
      try {
        const data = await api('/api/driver/earnings/');
        renderSettlementInstructions(data);
        msg('Settlement details loaded', true);
      } catch (err) {
        msg(err.message);
      }
    });
  }

  loadIncoming().catch(() => {});
  setInterval(() => loadIncoming().catch(() => {}), 5000);
  refreshDriverCurrentRide().catch(() => {});
  setInterval(() => refreshDriverCurrentRide().catch(() => {}), 5000);
  loadDriverProfile().catch(() => {});
  loadDriverDocuments().catch(() => {});
  loadEmergencyContacts().catch(() => {});
  loadDriverPendingRatings().catch(() => {});
  api('/api/driver/earnings/').then((data) => {
    renderEarnings(data);
    renderSettlementInstructions(data);
  }).catch(() => {});
  setupChat({
    listId: 'driver-chat-messages',
    inputId: 'driver-chat-input',
    sendBtnId: 'driver-chat-send-btn',
    rideIdGetter: () => driverCurrentRideId,
  });
}

async function wireAdmin() {
  document.getElementById('admin-panel').classList.remove('hidden');
  const tableBody = document.getElementById('drivers-table-body');
  const searchInput = document.getElementById('driver-search');
  const reportGrid = document.getElementById('report-grid');
  const topDriversBody = document.getElementById('top-drivers-body');
  const emergencyAlertsBody = document.getElementById('emergency-alerts-body');
  const scheduledRidesBody = document.getElementById('scheduled-rides-body');
  const driverFormWrap = document.getElementById('driver-form-wrap');
  const formTitle = document.getElementById('driver-form-title');
  const saveDriverBtn = document.getElementById('save-driver-form-btn');
  const cancelDriverBtn = document.getElementById('cancel-driver-form-btn');
  const addDriverBtn = document.getElementById('add-driver-btn');
  const passengersTableBody = document.getElementById('passengers-table-body');
  const passengerSearchInput = document.getElementById('passenger-search');
  const passengerFormWrap = document.getElementById('passenger-form-wrap');
  const passengerFormTitle = document.getElementById('passenger-form-title');
  const savePassengerBtn = document.getElementById('save-passenger-form-btn');
  const cancelPassengerBtn = document.getElementById('cancel-passenger-form-btn');
  const addPassengerBtn = document.getElementById('add-passenger-btn');
  const passengerQuickModal = document.getElementById('passenger-quick-view-modal');
  const passengerQuickCloseBtn = document.getElementById('passenger-quick-close-btn');
  const promoTableBody = document.getElementById('promo-table-body');
  const loadPromosBtn = document.getElementById('load-promos-btn');
  const createPromoBtn = document.getElementById('create-promo-btn');
  const promoCodeInput = document.getElementById('promo-code-input');
  const promoDiscountInput = document.getElementById('promo-discount-input');
  const promoMaxUsesInput = document.getElementById('promo-max-uses-input');
  const promoExpiresInput = document.getElementById('promo-expires-input');
  const monitoringTableBody = document.getElementById('monitoring-table-body');
  const monitoringSummaryGrid = document.getElementById('monitoring-summary-grid');
  const monitoringSearchInput = document.getElementById('monitoring-search');
  const loadMonitoringBtn = document.getElementById('load-monitoring-btn');
  const confirmModal = createConfirmModal();
  const adminRescheduleModal = document.getElementById('admin-reschedule-modal');
  const adminRescheduleDate = document.getElementById('admin-reschedule-date');
  const adminRescheduleTime = document.getElementById('admin-reschedule-time');
  const adminRescheduleOkBtn = document.getElementById('admin-reschedule-ok-btn');
  const adminRescheduleCancelBtn = document.getElementById('admin-reschedule-cancel-btn');
  const adminRescheduleMessage = document.getElementById('admin-reschedule-message');
  const adminDocModal = document.getElementById('admin-doc-modal');
  const adminDocType = document.getElementById('admin-doc-type');
  const adminDocStatus = document.getElementById('admin-doc-status');
  const adminDocNotes = document.getElementById('admin-doc-notes');
  const adminDocSaveBtn = document.getElementById('admin-doc-save-btn');
  const adminDocCancelBtn = document.getElementById('admin-doc-cancel-btn');

  let allDrivers = [];
  let editingDriverId = null;
  let allPassengers = [];
  let editingPassengerId = null;
  let scheduledRideIndex = new Map();
  let pendingRescheduleRide = null;
  let pendingDocDriverId = null;
  let allMonitoring = [];
  let monitoringInterval = null;

  function statusBadge(verified) {
    return verified
      ? `<span class="status-badge verified">${escapeHtml(uiText('status_verified', 'Verified'))}</span>`
      : `<span class="status-badge pending">${escapeHtml(uiText('status_pending', 'Pending'))}</span>`;
  }

  function onlineBadge(online) {
    return online
      ? `<span class="online-badge on">${escapeHtml(uiText('status_online', 'Online'))}</span>`
      : `<span class="online-badge off">${escapeHtml(uiText('status_offline', 'Offline'))}</span>`;
  }

  function riskBadge(level) {
    const value = (level || 'Low').toLowerCase();
    return `<span class="risk-badge ${value}">${escapeHtml(level || 'Low')}</span>`;
  }

  function docsBadge(docMap) {
    if (!docMap || Object.keys(docMap).length === 0) {
      return `<span class="doc-chip pending">${escapeHtml(uiText('empty_no_docs', 'No docs'))}</span>`;
    }
    return Object.entries(docMap)
      .map(([key, status]) => `<span class="doc-chip ${escapeHtml(status)}">${escapeHtml(key)}: ${escapeHtml(status)}</span>`)
      .join(' ');
  }

  function activeBadge(active) {
    return active
      ? `<span class="status-badge verified">${escapeHtml(uiText('status_active', 'Active'))}</span>`
      : `<span class="status-badge pending">${escapeHtml(uiText('status_inactive', 'Inactive'))}</span>`;
  }

  function setPassengerQuickView(passenger) {
    const avatarNode = document.getElementById('passenger-quick-avatar');
    document.getElementById('passenger-quick-id').textContent = `#${passenger.passenger_id}`;
    document.getElementById('passenger-quick-name').textContent = passenger.name || '-';
    document.getElementById('passenger-quick-phone').textContent = passenger.phone_number || '-';
    document.getElementById('passenger-quick-status').textContent = passenger.is_active
      ? uiText('status_active', 'Active')
      : uiText('status_inactive', 'Inactive');

    const safeImgUrl = sanitizeUrl(passenger.profile_image_url);
    if (safeImgUrl) {
      avatarNode.outerHTML = `<img id="passenger-quick-avatar" class="avatar quick-avatar" src="${safeImgUrl}" alt="Passenger photo" />`;
    } else {
      avatarNode.outerHTML = '<div id="passenger-quick-avatar" class="avatar placeholder quick-avatar">P</div>';
    }
  }

  function formatLocalDate(value) {
    const date = value instanceof Date ? value : new Date(value);
    if (Number.isNaN(date.getTime())) return '';
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
  }

  function formatLocalTime(value) {
    const date = value instanceof Date ? value : new Date(value);
    if (Number.isNaN(date.getTime())) return '';
    const hours = String(date.getHours()).padStart(2, '0');
    const minutes = String(date.getMinutes()).padStart(2, '0');
    return `${hours}:${minutes}`;
  }

  function formatEventTime(value) {
    const date = value instanceof Date ? value : new Date(value);
    if (Number.isNaN(date.getTime())) return '-';
    return date.toLocaleString();
  }

  function formatCompactDateTime(value) {
    const date = value instanceof Date ? value : new Date(value);
    if (Number.isNaN(date.getTime())) return '-';
    return date.toLocaleString([], {
      dateStyle: 'medium',
      timeStyle: 'short',
    });
  }

  function openAdminRescheduleModal(ride) {
    if (!adminRescheduleModal || !adminRescheduleDate || !adminRescheduleTime || !adminRescheduleMessage) return;
    pendingRescheduleRide = ride;
    adminRescheduleMessage.textContent = uiTextFormat('admin_reschedule_prompt', { id: ride.id }, `Set a new time for ride #${ride.id}.`);
    adminRescheduleDate.value = formatLocalDate(ride.scheduled_for);
    adminRescheduleTime.value = formatLocalTime(ride.scheduled_for);
    adminRescheduleModal.classList.remove('hidden');
  }

  function openDocReviewModal(driver) {
    if (!adminDocModal) return;
    pendingDocDriverId = driver.driver_id;
    adminDocType.value = 'national_id';
    adminDocStatus.value = 'pending';
    adminDocNotes.value = '';
    adminDocModal.classList.remove('hidden');
  }

  function closeDocReviewModal() {
    if (!adminDocModal) return;
    adminDocModal.classList.add('hidden');
    pendingDocDriverId = null;
  }

  function closeAdminRescheduleModal() {
    if (!adminRescheduleModal) return;
    adminRescheduleModal.classList.add('hidden');
    pendingRescheduleRide = null;
  }

  function renderDrivers(drivers) {
    if (!drivers.length) {
      tableBody.innerHTML = `<tr><td colspan="11" class="empty-cell">${escapeHtml(uiText('empty_no_drivers', 'No drivers found.'))}</td></tr>`;
      return;
    }

    tableBody.innerHTML = drivers
      .map((driver) => {
        const action = driver.is_verified
          ? `<span class="table-note">${escapeHtml(uiText('status_verified', 'Verified'))}</span>`
          : `<button class="table-action-btn verify-row-btn" data-driver-id="${driver.driver_id}">${escapeHtml(uiText('driver_verify_btn', 'Verify'))}</button>`;

        return `
          <tr>
            <td>${escapeHtml(driver.driver_id)}</td>
            <td>${escapeHtml(driver.name)}</td>
            <td>${escapeHtml(driver.phone_number)}</td>
            <td>${escapeHtml(driver.vehicle_type)}</td>
            <td>${statusBadge(driver.is_verified)}</td>
            <td>${onlineBadge(driver.is_online)}</td>
            <td>
              <strong>TZS ${escapeHtml(driver.outstanding_balance_tzs || 0)}</strong>
              <br />
              <small>${escapeHtml(uiText('label_debt_limit_short', 'Limit'))}: TZS ${escapeHtml(driver.debt_limit_tzs || 0)}</small>
            </td>
            <td>${riskBadge(driver.risk_flag)}</td>
            <td>${docsBadge(driver.documents)}</td>
            <td>
              ${escapeHtml(driver.station_name || '-')}
              ${
                driver.station_verified
                  ? `<span class="doc-chip approved">${escapeHtml(uiText('status_verified', 'Verified'))}</span>`
                  : `<span class="doc-chip pending">${escapeHtml(uiText('status_unverified', 'Unverified'))}</span>`
              }
            </td>
            <td>
              ${action}
              <button class="table-action-btn settle-row-btn" data-driver-id="${driver.driver_id}">Settle</button>
              <button class="table-action-btn review-doc-btn" data-driver-id="${driver.driver_id}">Review Docs</button>
              <button class="table-action-btn edit-row-btn" data-driver-id="${driver.driver_id}">Edit</button>
              <button class="table-action-btn delete-row-btn" data-driver-id="${driver.driver_id}">Delete</button>
            </td>
          </tr>
        `;
      })
      .join('');

    tableBody.querySelectorAll('.verify-row-btn').forEach((btn) => {
      btn.addEventListener('click', async () => {
        const id = parseInt(btn.dataset.driverId, 10);
        try {
          const data = await api('/api/admin/verify-driver/', 'POST', { driver_id: id });
          msg(data.detail, true);
          await loadDrivers();
        } catch (err) {
          msg(err.message);
        }
      });
    });

    tableBody.querySelectorAll('.edit-row-btn').forEach((btn) => {
      btn.addEventListener('click', () => {
        const id = parseInt(btn.dataset.driverId, 10);
        const driver = allDrivers.find((d) => d.driver_id === id);
        if (!driver) return;

        editingDriverId = id;
        formTitle.textContent = `Edit Driver #${id}`;
        document.getElementById('admin-driver-name').value = driver.name || '';
        document.getElementById('admin-driver-phone').value = driver.phone_number || '';
        document.getElementById('admin-driver-password').value = '';
        document.getElementById('admin-driver-vehicle').value = driver.vehicle_type || 'motorcycle';
        document.getElementById('admin-driver-license').value = driver.license_number || '';
        document.getElementById('admin-driver-plate').value = driver.plate_number || '';
        document.getElementById('admin-driver-verified').value = driver.is_verified ? 'true' : 'false';
        driverFormWrap.classList.remove('hidden');
      });
    });

    tableBody.querySelectorAll('.delete-row-btn').forEach((btn) => {
      btn.addEventListener('click', async () => {
        const id = parseInt(btn.dataset.driverId, 10);
        const confirmed = window.confirm(`${uiText('confirm_delete_driver_message_prefix', 'Delete driver')} #${id}? ${uiText('confirm_cannot_undo', 'This action cannot be undone.')}`);
        if (!confirmed) return;
        try {
          const data = await api('/api/admin/driver/delete/', 'POST', { driver_id: id });
          msg(data.detail, true);
          await loadDrivers();
        } catch (err) {
          msg(err.message);
        }
      });
    });

    tableBody.querySelectorAll('.settle-row-btn').forEach((btn) => {
      btn.addEventListener('click', async () => {
        const id = parseInt(btn.dataset.driverId, 10);
        const driver = allDrivers.find((d) => d.driver_id === id);
        if (!driver) return;
        const outstanding = Number(driver.outstanding_balance_tzs || 0);
        if (outstanding <= 0) {
          msg(uiText('toast_no_settlement_due', 'This driver has no outstanding balance.'));
          return;
        }
        const amount = window.prompt(`Record settlement for driver #${id}. Outstanding balance is TZS ${outstanding}. Enter amount paid:`, String(outstanding));
        if (amount === null) return;
        const note = window.prompt('Optional settlement note or payment reference:', 'Weekly settlement');
        if (note === null) return;
        try {
          const data = await api('/api/admin/driver/settlement/', 'POST', {
            driver_id: id,
            amount_tzs: amount,
            note,
          });
          msg(data.detail, true);
          await loadDrivers();
        } catch (err) {
          msg(err.message);
        }
      });
    });

    tableBody.querySelectorAll('.review-doc-btn').forEach((btn) => {
      btn.addEventListener('click', () => {
        const id = parseInt(btn.dataset.driverId, 10);
        const driver = allDrivers.find((d) => d.driver_id === id);
        if (!driver) return;
        openDocReviewModal(driver);
      });
    });
  }

  function applySearch() {
    const query = searchInput.value.trim().toLowerCase();
    if (!query) {
      renderDrivers(allDrivers);
      return;
    }
    const filtered = allDrivers.filter((driver) => {
      return (
        String(driver.driver_id).includes(query) ||
        (driver.name || '').toLowerCase().includes(query) ||
        (driver.phone_number || '').toLowerCase().includes(query) ||
        (driver.vehicle_type || '').toLowerCase().includes(query)
      );
    });
    renderDrivers(filtered);
  }

  async function loadDrivers() {
    const data = await api('/api/admin/drivers/');
    allDrivers = data.drivers || [];
    applySearch();
  }

  function renderPassengers(passengers) {
    if (!passengers.length) {
      passengersTableBody.innerHTML = `<tr><td colspan="6" class="empty-cell">${escapeHtml(uiText('empty_no_passengers', 'No passengers found.'))}</td></tr>`;
      return;
    }

    passengersTableBody.innerHTML = passengers
      .map(
        (passenger) => `
          <tr>
            <td>${escapeHtml(passenger.passenger_id)}</td>
            <td>
              ${
                sanitizeUrl(passenger.profile_image_url)
                  ? `<img class="avatar mini-avatar" src="${sanitizeUrl(passenger.profile_image_url)}" alt="Passenger" />`
                  : '<div class="avatar placeholder mini-avatar">P</div>'
              }
            </td>
            <td>${escapeHtml(passenger.name)}</td>
            <td>${escapeHtml(passenger.phone_number)}</td>
            <td>${activeBadge(passenger.is_active)}</td>
            <td>${riskBadge(passenger.risk_flag)}</td>
            <td>
              <button class="table-action-btn quick-passenger-row-btn" data-passenger-id="${passenger.passenger_id}">Quick View</button>
              <button class="table-action-btn edit-passenger-row-btn" data-passenger-id="${passenger.passenger_id}">Edit</button>
              <button class="table-action-btn delete-row-btn delete-passenger-row-btn" data-passenger-id="${passenger.passenger_id}">Delete</button>
            </td>
          </tr>
        `
      )
      .join('');

    passengersTableBody.querySelectorAll('.edit-passenger-row-btn').forEach((btn) => {
      btn.addEventListener('click', () => {
        const id = parseInt(btn.dataset.passengerId, 10);
        const passenger = allPassengers.find((p) => p.passenger_id === id);
        if (!passenger) return;

        editingPassengerId = id;
        passengerFormTitle.textContent = `Edit Passenger #${id}`;
        document.getElementById('admin-passenger-name').value = passenger.name || '';
        document.getElementById('admin-passenger-phone').value = passenger.phone_number || '';
        document.getElementById('admin-passenger-password').value = '';
        document.getElementById('admin-passenger-active').value = passenger.is_active ? 'true' : 'false';
        passengerFormWrap.classList.remove('hidden');
      });
    });

    passengersTableBody.querySelectorAll('.quick-passenger-row-btn').forEach((btn) => {
      btn.addEventListener('click', () => {
        const id = parseInt(btn.dataset.passengerId, 10);
        const passenger = allPassengers.find((p) => p.passenger_id === id);
        if (!passenger) return;
        setPassengerQuickView(passenger);
        passengerQuickModal.classList.remove('hidden');
      });
    });

    passengersTableBody.querySelectorAll('.delete-passenger-row-btn').forEach((btn) => {
      btn.addEventListener('click', async () => {
        const id = parseInt(btn.dataset.passengerId, 10);
        const confirmed = window.confirm(`${uiText('confirm_delete_passenger_message_prefix', 'Delete passenger')} #${id}? ${uiText('confirm_cannot_undo', 'This action cannot be undone.')}`);
        if (!confirmed) return;
        try {
          const data = await api('/api/admin/passenger/delete/', 'POST', { passenger_id: id });
          msg(data.detail, true);
          await loadPassengers();
        } catch (err) {
          msg(err.message);
        }
      });
    });
  }

  function applyPassengerSearch() {
    const query = passengerSearchInput.value.trim().toLowerCase();
    if (!query) {
      renderPassengers(allPassengers);
      return;
    }
    const filtered = allPassengers.filter((passenger) => {
      return (
        String(passenger.passenger_id).includes(query) ||
        (passenger.name || '').toLowerCase().includes(query) ||
        (passenger.phone_number || '').toLowerCase().includes(query)
      );
    });
    renderPassengers(filtered);
  }

  async function loadPassengers() {
    const data = await api('/api/admin/passengers/');
    allPassengers = data.passengers || [];
    applyPassengerSearch();
  }

  function renderMonitoring(events) {
    if (!monitoringTableBody) return;
    if (!events.length) {
      monitoringTableBody.innerHTML = `<tr><td colspan="10" class="empty-cell">${escapeHtml(uiText('empty_no_activity', 'No activity recorded yet.'))}</td></tr>`;
      return;
    }
    monitoringTableBody.innerHTML = events
      .map((event) => {
        const userLabel = event.user_name
          ? `${escapeHtml(event.user_name)}<br/><small>${escapeHtml(event.user_phone || '')}</small>`
          : 'Guest';
        const deviceLabel = `${escapeHtml(event.device_type || 'Unknown')} · ${escapeHtml(event.os_name || 'Unknown')} · ${escapeHtml(
          event.browser_name || 'Unknown'
        )}`;
        const locationLabel = [
          event.city_name,
          event.region_name,
          event.country_name,
        ]
          .filter(Boolean)
          .join(', ');
        const ispLabel = event.isp || event.asn || '-';
        const pathLabel = `${escapeHtml(event.method || '')} ${escapeHtml(event.path || '')}`.trim();
        return `
          <tr>
            <td>${escapeHtml(formatEventTime(event.created_at))}</td>
            <td>${escapeHtml(event.event_type || '-')}${event.status_code ? `<br/><small>${escapeHtml(event.status_code)}</small>` : ''}</td>
            <td>${userLabel}</td>
            <td>${escapeHtml(event.user_role || '-')}</td>
            <td>${deviceLabel}</td>
            <td>${escapeHtml(locationLabel || '-')}</td>
            <td>${escapeHtml(ispLabel)}</td>
            <td>${escapeHtml(event.ip_address || '-')}</td>
            <td>${pathLabel}</td>
            <td>${escapeHtml(event.referrer || '-')}</td>
          </tr>
        `;
      })
      .join('');
  }

  function applyMonitoringSearch() {
    if (!monitoringSearchInput) return;
    const query = monitoringSearchInput.value.trim().toLowerCase();
    if (!query) {
      renderMonitoring(allMonitoring);
      return;
    }
    const filtered = allMonitoring.filter((event) => {
      const haystack = [
        event.path,
        event.ip_address,
        event.user_phone,
        event.user_name,
        event.device_type,
        event.os_name,
        event.browser_name,
        event.referrer,
      ]
        .filter(Boolean)
        .join(' ')
        .toLowerCase();
      return haystack.includes(query);
    });
    renderMonitoring(filtered);
  }

  async function loadMonitoring() {
    if (!monitoringTableBody || !monitoringSummaryGrid) return;
    const data = await api('/api/admin/monitoring/');
    const summary = data.summary || {};
    const health = data.health || {};
    const backup = data.backup || {};
    const cards = [
      ['Visits (24h)', summary.last_24h_total || 0],
      ['Page Views', summary.last_24h_page_views || 0],
      ['Actions', summary.last_24h_actions || 0],
      ['Registrations', summary.last_24h_registers || 0],
      ['Logins', summary.last_24h_logins || 0],
      ['System', health.status || 'unknown'],
      ['Database', health.database || 'unknown'],
      ['Backups', backup.count || 0],
      ['Latest Backup', backup.latest_backup_at ? formatCompactDateTime(backup.latest_backup_at) : 'none'],
    ];
    monitoringSummaryGrid.innerHTML = cards
      .map(
        ([label, value]) =>
          `<article class="report-card"><span class="label">${escapeHtml(label)}</span><span class="value">${escapeHtml(value)}</span></article>`
      )
      .join('');
    allMonitoring = data.events || [];
    renderMonitoring(allMonitoring);
  }

  function resetDriverForm() {
    editingDriverId = null;
    formTitle.textContent = 'Add New Driver';
    document.getElementById('admin-driver-name').value = '';
    document.getElementById('admin-driver-phone').value = '';
    document.getElementById('admin-driver-password').value = '';
    document.getElementById('admin-driver-vehicle').value = 'motorcycle';
    document.getElementById('admin-driver-license').value = '';
    document.getElementById('admin-driver-plate').value = '';
    document.getElementById('admin-driver-verified').value = 'false';
    driverFormWrap.classList.add('hidden');
  }

  function resetPassengerForm() {
    editingPassengerId = null;
    passengerFormTitle.textContent = 'Add New Passenger';
    document.getElementById('admin-passenger-name').value = '';
    document.getElementById('admin-passenger-phone').value = '';
    document.getElementById('admin-passenger-password').value = '';
    document.getElementById('admin-passenger-active').value = 'true';
    passengerFormWrap.classList.add('hidden');
  }

  if (adminRescheduleCancelBtn) {
    adminRescheduleCancelBtn.addEventListener('click', closeAdminRescheduleModal);
  }

  if (adminRescheduleOkBtn) {
    adminRescheduleOkBtn.addEventListener('click', async () => {
      if (!pendingRescheduleRide) return;
      const dateValue = adminRescheduleDate?.value || '';
      const timeValue = adminRescheduleTime?.value || '';
      if (!dateValue || !timeValue) {
        msg(uiText('toast_select_new_datetime', 'Select a new date and time first'));
        return;
      }
      try {
        const data = await api('/api/admin/scheduled-ride/update/', 'POST', {
          ride_id: pendingRescheduleRide.id,
          date: dateValue,
          time: timeValue,
        });
        msg(data.detail, true);
        closeAdminRescheduleModal();
        await loadReports();
      } catch (err) {
        msg(err.message);
      }
    });
  }

  if (adminDocCancelBtn) {
    adminDocCancelBtn.addEventListener('click', closeDocReviewModal);
  }

  if (adminDocSaveBtn) {
    adminDocSaveBtn.addEventListener('click', async () => {
      if (!pendingDocDriverId) return;
      try {
        const data = await api('/api/admin/driver-documents/review/', 'POST', {
          driver_id: pendingDocDriverId,
          doc_type: adminDocType.value,
          status: adminDocStatus.value,
          notes: adminDocNotes.value.trim(),
        });
        msg(data.detail, true);
        closeDocReviewModal();
        await loadDrivers();
      } catch (err) {
        msg(err.message);
      }
    });
  }

  async function loadReports() {
    const data = await api('/api/admin/reports/');
    const summary = data.summary || {};
    const cards = [
      ['Total Drivers', summary.total_drivers || 0],
      ['Total Passengers', summary.total_passengers || 0],
      [uiText('report_verified_drivers', 'Verified Drivers'), summary.verified_drivers || 0],
      ['Online Drivers', summary.online_drivers || 0],
      ['Total Revenue (TZS)', summary.total_revenue_tzs || '0'],
      ['Platform Commission (TZS)', summary.platform_commission_tzs || '0'],
      ['Settled Amount (TZS)', summary.platform_settled_tzs || '0'],
      ['Outstanding Amount (TZS)', summary.platform_outstanding_tzs || '0'],
      ['Total Rides', summary.total_rides || 0],
      ['Completed Rides', summary.completed_rides || 0],
      ['Cancelled Rides', summary.cancelled_rides || 0],
      ['Scheduled Rides', summary.scheduled_rides || 0],
      ['Active Rides', summary.active_rides || 0],
    ];
    reportGrid.innerHTML = cards
      .map(
        ([label, value]) =>
          `<article class="report-card"><span class="label">${escapeHtml(label)}</span><span class="value">${escapeHtml(value)}</span></article>`
      )
      .join('');

    const top = data.top_drivers || [];
      if (!top.length) {
      topDriversBody.innerHTML = `<tr><td colspan="4" class="empty-cell">${escapeHtml(uiText('empty_no_completed_rides', 'No completed rides yet.'))}</td></tr>`;
      return;
    }
    topDriversBody.innerHTML = top
      .map(
        (row) => `
          <tr>
            <td>${escapeHtml(row.driver_id)}</td>
            <td>${escapeHtml(row.name)}</td>
            <td>${escapeHtml(row.total_rides)}</td>
            <td>${escapeHtml(row.revenue_tzs)}</td>
          </tr>
        `
      )
      .join('');

    if (scheduledRidesBody) {
      const scheduledData = await api('/api/admin/scheduled-rides/');
      const rides = scheduledData.rides || [];
      scheduledRideIndex = new Map();
      if (!rides.length) {
        scheduledRidesBody.innerHTML = `<tr><td colspan="8" class="empty-cell">${escapeHtml(uiText('empty_no_admin_scheduled_rides', 'No scheduled rides.'))}</td></tr>`;
      } else {
        scheduledRideIndex = new Map(rides.map((ride) => [ride.id, ride]));
        scheduledRidesBody.innerHTML = rides
          .map(
            (ride) => `
              <tr>
                <td>${escapeHtml(ride.id)}</td>
                <td>${escapeHtml(ride.passenger_name)}<br/><small>${escapeHtml(ride.passenger_phone)}</small></td>
                <td>${escapeHtml(ride.pickup_location)}</td>
                <td>${escapeHtml(ride.dropoff_location)}</td>
                <td>${vehicleLabel(ride.vehicle_type)}</td>
                <td>${escapeHtml(ride.scheduled_for)}</td>
                <td>${escapeHtml(ride.status)}</td>
                <td>
                  <button class="table-action-btn admin-scheduled-edit-btn" data-ride-id="${ride.id}">Reschedule</button>
                  <button class="table-action-btn admin-scheduled-cancel-btn" data-ride-id="${ride.id}">Cancel</button>
                </td>
              </tr>
            `
          )
          .join('');

        scheduledRidesBody.querySelectorAll('.admin-scheduled-edit-btn').forEach((btn) => {
          btn.addEventListener('click', () => {
            const id = parseInt(btn.dataset.rideId, 10);
            const ride = scheduledRideIndex.get(id);
            if (!ride) return;
            openAdminRescheduleModal(ride);
          });
        });

        scheduledRidesBody.querySelectorAll('.admin-scheduled-cancel-btn').forEach((btn) => {
          btn.addEventListener('click', async () => {
            const id = parseInt(btn.dataset.rideId, 10);
            const confirmed = await confirmModal({
              title: uiText('admin_cancel_scheduled_title', 'Cancel Scheduled Ride'),
              message: uiTextFormat('admin_cancel_scheduled_message', { id }, `Cancel scheduled ride #${id}? This cannot be undone.`),
            });
            if (!confirmed) return;
            try {
              const data = await api('/api/admin/scheduled-ride/cancel/', 'POST', { ride_id: id });
              msg(data.detail, true);
              await loadReports();
            } catch (err) {
              msg(err.message);
            }
          });
        });
      }
    }

    const emergencyData = await api('/api/admin/emergency-alerts/');
    const alerts = emergencyData.alerts || [];
    if (!alerts.length) {
      emergencyAlertsBody.innerHTML = `<tr><td colspan="7" class="empty-cell">${escapeHtml(uiText('empty_no_sos_events', 'No SOS events logged.'))}</td></tr>`;
      return;
    }
    emergencyAlertsBody.innerHTML = alerts
      .map(
        (alert) => `
          <tr>
            <td>${escapeHtml(alert.id)}</td>
            <td>${escapeHtml(alert.ride_id)}</td>
            <td>${escapeHtml(alert.name)}<br/><small>${escapeHtml(alert.phone_number)}</small></td>
            <td>${escapeHtml(alert.role)}</td>
            <td>${escapeHtml(alert.latitude)}, ${escapeHtml(alert.longitude)}</td>
            <td>${escapeHtml(alert.notified_contacts)}</td>
            <td>${escapeHtml(new Date(alert.created_at).toLocaleString())}</td>
          </tr>
        `
      )
      .join('');
  }

  async function loadSettings() {
    const data = await api('/api/admin/settings/');
    const settings = data.settings || {};
    document.getElementById('setting-service-radius').value = settings.service_radius_km || '3';
    document.getElementById('setting-price-km').value = settings.price_per_km_tzs || '700';
    document.getElementById('setting-base-motorcycle').value = settings.base_fare_motorcycle_tzs || '1500';
    document.getElementById('setting-base-bajaji').value = settings.base_fare_bajaji_tzs || '2500';
    document.getElementById('setting-driver-debt-limit').value = settings.driver_debt_limit_tzs || '3000';
    document.getElementById('setting-surge-enabled').value = String(settings.surge_enabled || 'false');
    document.getElementById('setting-surge-multiplier').value = settings.surge_multiplier || '1.00';
    document.getElementById('setting-first-ride-discount').value = settings.first_ride_discount_pct || '10';
    document.getElementById('setting-commission-band-short-max').value = settings.commission_band_short_max_tzs || '2000';
    document.getElementById('setting-commission-fee-short').value = settings.commission_fee_short_tzs || '100';
    document.getElementById('setting-commission-band-medium-max').value = settings.commission_band_medium_max_tzs || '4000';
    document.getElementById('setting-commission-fee-medium').value = settings.commission_fee_medium_tzs || '200';
    document.getElementById('setting-commission-band-long-max').value = settings.commission_band_long_max_tzs || '6500';
    document.getElementById('setting-commission-fee-long').value = settings.commission_fee_long_tzs || '300';
    document.getElementById('setting-commission-fee-extended').value = settings.commission_fee_extended_tzs || '500';
    document.getElementById('setting-settlement-provider').value = settings.driver_settlement_provider || 'M-Pesa';
    document.getElementById('setting-settlement-phone').value = settings.driver_settlement_phone || '';
    document.getElementById('setting-settlement-reference-prefix').value = settings.driver_settlement_reference_prefix || 'BODAAU';
    document.getElementById('setting-weather-enabled').value = String(settings.weather_advisory_enabled || 'true');
    document.getElementById('setting-weather-rain-probability').value = settings.weather_rain_probability_pct || '45';
    document.getElementById('setting-weather-rain-mm').value = settings.weather_rain_mm_threshold || '0.2';
    document.getElementById('setting-weather-hours-ahead').value = settings.weather_lookahead_hours || '3';
  }

  async function loadPromos() {
    if (!promoTableBody) return;
    const data = await api('/api/admin/promos/');
    const promos = data.promos || [];
    if (!promos.length) {
      promoTableBody.innerHTML = `<tr><td colspan="6" class="empty-cell">${escapeHtml(uiText('empty_no_promos', 'No promos yet.'))}</td></tr>`;
      return;
    }
    promoTableBody.innerHTML = promos
      .map(
        (promo) => `
          <tr>
            <td>${escapeHtml(promo.code)}</td>
            <td>${escapeHtml(promo.discount_pct)}</td>
            <td>${escapeHtml(promo.used_count)} / ${escapeHtml(promo.max_uses)}</td>
            <td>${promo.expires_at ? escapeHtml(new Date(promo.expires_at).toLocaleDateString()) : '-'}</td>
            <td>${promo.is_active ? 'Active' : 'Inactive'}</td>
            <td>
              <button class="table-action-btn promo-toggle-btn" data-code="${escapeHtml(promo.code)}" data-active="${promo.is_active}">
                ${promo.is_active ? 'Deactivate' : 'Activate'}
              </button>
            </td>
          </tr>
        `
      )
      .join('');

    promoTableBody.querySelectorAll('.promo-toggle-btn').forEach((btn) => {
      btn.addEventListener('click', async () => {
        const code = btn.dataset.code;
        const isActive = btn.dataset.active === 'true';
        try {
          const data = await api('/api/admin/promos/toggle/', 'POST', { code, is_active: !isActive });
          msg(data.detail, true);
          await loadPromos();
        } catch (err) {
          msg(err.message);
        }
      });
    });
  }

  function showSection(section) {
    document.querySelectorAll('.admin-menu-btn').forEach((btn) => {
      btn.classList.toggle('active', btn.dataset.section === section);
    });
    document.querySelectorAll('.admin-section').forEach((el) => {
      el.classList.toggle('hidden', el.dataset.section !== section);
    });
    if (section !== 'monitoring' && monitoringInterval) {
      clearInterval(monitoringInterval);
      monitoringInterval = null;
    }
  }

  document.getElementById('load-drivers-btn').addEventListener('click', async () => {
    try {
      await loadDrivers();
      msg(uiText('toast_drivers_loaded', 'Drivers loaded'), true);
    } catch (err) {
      msg(err.message);
    }
  });

  searchInput.addEventListener('input', applySearch);
  passengerSearchInput.addEventListener('input', applyPassengerSearch);

  addDriverBtn.addEventListener('click', () => {
    resetDriverForm();
    driverFormWrap.classList.remove('hidden');
  });
  addPassengerBtn.addEventListener('click', () => {
    resetPassengerForm();
    passengerFormWrap.classList.remove('hidden');
  });

  cancelDriverBtn.addEventListener('click', () => {
    resetDriverForm();
  });
  cancelPassengerBtn.addEventListener('click', () => {
    resetPassengerForm();
  });
  if (passengerQuickCloseBtn) {
    passengerQuickCloseBtn.addEventListener('click', () => {
      passengerQuickModal.classList.add('hidden');
    });
  }
  if (passengerQuickModal) {
    passengerQuickModal.addEventListener('click', (event) => {
      if (event.target === passengerQuickModal) {
        passengerQuickModal.classList.add('hidden');
      }
    });
  }

  saveDriverBtn.addEventListener('click', async () => {
    const payload = {
      name: document.getElementById('admin-driver-name').value.trim(),
      phone_number: document.getElementById('admin-driver-phone').value.trim(),
      password: document.getElementById('admin-driver-password').value,
      vehicle_type: document.getElementById('admin-driver-vehicle').value,
      license_number: document.getElementById('admin-driver-license').value.trim(),
      plate_number: document.getElementById('admin-driver-plate').value.trim(),
      is_verified: document.getElementById('admin-driver-verified').value === 'true',
    };

    try {
      if (editingDriverId) {
        const updatePayload = { ...payload, driver_id: editingDriverId };
        if (!updatePayload.password) {
          delete updatePayload.password;
        }
        const data = await api('/api/admin/driver/update/', 'POST', updatePayload);
        msg(data.detail, true);
      } else {
        const data = await api('/api/admin/driver/create/', 'POST', payload);
        msg(data.detail, true);
      }
      resetDriverForm();
      await loadDrivers();
    } catch (err) {
      msg(err.message);
    }
  });

  savePassengerBtn.addEventListener('click', async () => {
    const payload = {
      name: document.getElementById('admin-passenger-name').value.trim(),
      phone_number: document.getElementById('admin-passenger-phone').value.trim(),
      password: document.getElementById('admin-passenger-password').value,
      is_active: document.getElementById('admin-passenger-active').value === 'true',
    };

    try {
      if (editingPassengerId) {
        const updatePayload = { ...payload, passenger_id: editingPassengerId };
        if (!updatePayload.password) {
          delete updatePayload.password;
        }
        const data = await api('/api/admin/passenger/update/', 'POST', updatePayload);
        msg(data.detail, true);
      } else {
        const data = await api('/api/admin/passenger/create/', 'POST', payload);
        msg(data.detail, true);
      }
      resetPassengerForm();
      await loadPassengers();
    } catch (err) {
      msg(err.message);
    }
  });

  document.getElementById('load-passengers-btn').addEventListener('click', async () => {
    try {
      await loadPassengers();
      msg(uiText('toast_passengers_loaded', 'Passengers loaded'), true);
    } catch (err) {
      msg(err.message);
    }
  });

  document.getElementById('load-reports-btn').addEventListener('click', async () => {
    try {
      await loadReports();
      msg(uiText('toast_reports_loaded', 'Reports loaded'), true);
    } catch (err) {
      msg(err.message);
    }
  });

  document.getElementById('load-settings-btn').addEventListener('click', async () => {
    try {
      await loadSettings();
      msg(uiText('toast_settings_loaded', 'Settings loaded'), true);
    } catch (err) {
      msg(err.message);
    }
  });

  if (loadPromosBtn) {
    loadPromosBtn.addEventListener('click', async () => {
      try {
        await loadPromos();
        msg(uiText('toast_promos_loaded', 'Promos loaded'), true);
      } catch (err) {
        msg(err.message);
      }
    });
  }

  if (loadMonitoringBtn) {
    loadMonitoringBtn.addEventListener('click', async () => {
      try {
        await loadMonitoring();
        msg(uiText('toast_monitoring_loaded', 'Monitoring loaded'), true);
      } catch (err) {
        msg(err.message);
      }
    });
  }

  if (createPromoBtn) {
    createPromoBtn.addEventListener('click', async () => {
      try {
        const payload = {
          code: promoCodeInput.value.trim(),
          discount_pct: promoDiscountInput.value,
          max_uses: promoMaxUsesInput.value,
          expires_at: promoExpiresInput.value ? `${promoExpiresInput.value}T00:00:00` : '',
        };
        const data = await api('/api/admin/promos/create/', 'POST', payload);
        msg(data.detail, true);
        await loadPromos();
      } catch (err) {
        msg(err.message);
      }
    });
  }

  document.getElementById('save-settings-btn').addEventListener('click', async () => {
    const settings = {
      service_radius_km: document.getElementById('setting-service-radius').value,
      price_per_km_tzs: document.getElementById('setting-price-km').value,
      base_fare_motorcycle_tzs: document.getElementById('setting-base-motorcycle').value,
      base_fare_bajaji_tzs: document.getElementById('setting-base-bajaji').value,
      driver_debt_limit_tzs: document.getElementById('setting-driver-debt-limit').value,
      surge_enabled: document.getElementById('setting-surge-enabled').value,
      surge_multiplier: document.getElementById('setting-surge-multiplier').value,
      first_ride_discount_pct: document.getElementById('setting-first-ride-discount').value,
      commission_band_short_max_tzs: document.getElementById('setting-commission-band-short-max').value,
      commission_fee_short_tzs: document.getElementById('setting-commission-fee-short').value,
      commission_band_medium_max_tzs: document.getElementById('setting-commission-band-medium-max').value,
      commission_fee_medium_tzs: document.getElementById('setting-commission-fee-medium').value,
      commission_band_long_max_tzs: document.getElementById('setting-commission-band-long-max').value,
      commission_fee_long_tzs: document.getElementById('setting-commission-fee-long').value,
      commission_fee_extended_tzs: document.getElementById('setting-commission-fee-extended').value,
      driver_settlement_provider: document.getElementById('setting-settlement-provider').value.trim(),
      driver_settlement_phone: document.getElementById('setting-settlement-phone').value.trim(),
      driver_settlement_reference_prefix: document.getElementById('setting-settlement-reference-prefix').value.trim(),
      weather_advisory_enabled: document.getElementById('setting-weather-enabled').value,
      weather_rain_probability_pct: document.getElementById('setting-weather-rain-probability').value,
      weather_rain_mm_threshold: document.getElementById('setting-weather-rain-mm').value,
      weather_lookahead_hours: document.getElementById('setting-weather-hours-ahead').value,
    };
    try {
      const data = await api('/api/admin/settings/update/', 'POST', { settings });
      msg(data.detail, true);
    } catch (err) {
      msg(err.message);
    }
  });

  document.querySelectorAll('.admin-menu-btn').forEach((btn) => {
    btn.addEventListener('click', async () => {
      const section = btn.dataset.section;
      if (!section) return;
      showSection(section);
      if (section === 'reports') {
        await loadReports().catch((err) => msg(err.message));
      }
      if (section === 'settings') {
        await loadSettings().catch((err) => msg(err.message));
      }
      if (section === 'promos') {
        await loadPromos().catch((err) => msg(err.message));
      }
      if (section === 'passengers') {
        await loadPassengers().catch((err) => msg(err.message));
      }
      if (section === 'monitoring') {
        await loadMonitoring().catch((err) => msg(err.message));
        if (!monitoringInterval) {
          monitoringInterval = setInterval(() => {
            loadMonitoring().catch(() => {});
          }, 30000);
        }
      }
    });
  });

  if (monitoringSearchInput) {
    monitoringSearchInput.addEventListener('input', applyMonitoringSearch);
  }

  showSection('drivers');
  await loadDrivers().catch((err) => msg(err.message));
}

const rootNode = document.getElementById('dashboard-root');
const role = rootNode ? rootNode.dataset.role : null;
if (role === 'passenger') {
  wirePassenger();
} else if (role === 'driver') {
  wireDriver();
} else {
  wireAdmin();
}
setupOfflineUi();
initNotifications();

const logoutBtn = document.getElementById('logout-btn');
if (logoutBtn) {
  logoutBtn.addEventListener('click', async () => {
    const confirmed = await showConfirm({
      title: uiText('confirm_logout_title', 'Log Out'),
      message: uiText('confirm_logout_message', 'Are you sure you want to log out?'),
      okText: uiText('confirm_yes', 'Yes'),
      cancelText: uiText('confirm_no', 'No'),
    });
    if (!confirmed) return;
    await api('/auth/logout/', 'POST', {});
    window.location.href = '/';
  });
}
