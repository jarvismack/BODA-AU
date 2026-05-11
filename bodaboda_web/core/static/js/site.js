const backToTopBtn = document.getElementById('back-to-top');
const logoStyleButtons = document.querySelectorAll('.logo-style-btn');
const logoStyleStorageKey = 'boda_au_logo_style';
const languageStorageKey = 'boda_language';
const languagePromptModal = document.getElementById('language-modal');
const languagePromptButtons = document.querySelectorAll('[data-language-choice]');
const splashScreen = document.getElementById('splash-screen');
const splashLine = document.getElementById('splash-line');
let languagePromptRequired = false;
let languagePromptVisible = false;

function safeStorageGet(key) {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function safeStorageSet(key, value) {
  try {
    localStorage.setItem(key, value);
  } catch {
    // Optional enhancement only.
  }
}

function normalizeLanguage(lang) {
  return translations[lang] ? lang : 'en';
}

function hideLanguagePrompt() {
  if (!languagePromptModal) return;
  languagePromptModal.classList.add('hidden');
  document.body.classList.remove('language-prompt-open');
  languagePromptVisible = false;
}

function showLanguagePromptIfNeeded() {
  if (!languagePromptRequired || languagePromptVisible || !languagePromptModal) return;
  languagePromptModal.classList.remove('hidden');
  document.body.classList.add('language-prompt-open');
  languagePromptVisible = true;
  const primaryChoice = languagePromptModal.querySelector('[data-language-choice="en"]');
  if (primaryChoice && typeof primaryChoice.focus === 'function') {
    primaryChoice.focus();
  }
}

function chooseLanguage(lang) {
  if (!translations[lang]) return;
  setAppLanguage(lang);
  languagePromptRequired = false;
  safeStorageSet(languageStorageKey, lang);
  hideLanguagePrompt();
}

function initSplash() {
  if (!splashScreen || !splashLine) return;

  const lines = ['Mama Boda', 'kalia chuma twenzetu'];
  let typeTimer = null;

  function typeLine(text, speed = 62) {
    if (typeTimer) window.clearInterval(typeTimer);
    splashLine.textContent = '';
    let index = 0;
    typeTimer = window.setInterval(() => {
      index += 1;
      splashLine.textContent = text.slice(0, index);
      if (index >= text.length) {
        window.clearInterval(typeTimer);
        typeTimer = null;
      }
    }, speed);
  }

  typeLine(lines[0], 74);
  window.setTimeout(() => typeLine(lines[1], 56), 2400);

  window.setTimeout(() => {
    splashScreen.classList.add('is-done');
    if (typeTimer) window.clearInterval(typeTimer);

    window.setTimeout(() => {
      splashScreen.classList.add('hidden');
      showLanguagePromptIfNeeded();
    }, 460);
  }, 5000);
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initSplash, { once: true });
} else {
  initSplash();
}

function toggleBackToTop() {
  if (!backToTopBtn) return;
  const shouldShow = window.scrollY > 280;
  backToTopBtn.classList.toggle('hidden', !shouldShow);
}

if (backToTopBtn) {
  window.addEventListener('scroll', toggleBackToTop, { passive: true });
  backToTopBtn.addEventListener('click', () => {
    window.scrollTo({ top: 0, behavior: 'smooth' });
  });
  toggleBackToTop();
}

function applyLogoStyle(style) {
  const allowed = ['premium', 'minimal', 'bold'];
  const nextStyle = allowed.includes(style) ? style : 'premium';
  document.body.dataset.logoStyle = nextStyle;
  logoStyleButtons.forEach((btn) => {
    btn.classList.toggle('active', btn.dataset.logoStyle === nextStyle);
  });
  safeStorageSet(logoStyleStorageKey, nextStyle);
}

if (logoStyleButtons.length) {
  const storedStyle = safeStorageGet(logoStyleStorageKey) || 'premium';
  applyLogoStyle(storedStyle);

  logoStyleButtons.forEach((btn) => {
    btn.addEventListener('click', () => {
      applyLogoStyle(btn.dataset.logoStyle);
    });
  });
}

const translations = {
  en: {
    nav_notifications: 'Notifications',
    nav_mark_all_read: 'Mark all read',
    nav_clear_all: 'Clear all',
    nav_logout: 'Logout',
    footer_platform: 'Platform',
    footer_support: 'Support',
    footer_system: 'System',
    footer_home: 'Home',
    footer_safety: 'Safety Center',
    footer_help: 'Help & Contact',
    footer_terms: 'Terms & Privacy',
    footer_secure: 'Secure Session',
    footer_realtime: 'Realtime Notifications',
    footer_routes: 'Zanzibar Active Routes',
    intro_kicker: 'BODA AU Pre-Launch',
    intro_slide_1_title: 'Create an account',
    intro_slide_1_copy: 'Register as either a passenger or driver in one secure flow and enter the platform instantly.',
    intro_slide_2_title: 'Request your ride',
    intro_slide_2_copy: 'Choose your pickup and dropoff from active Zanzibar routes and send your request in seconds.',
    intro_slide_3_title: 'Choose your driver',
    intro_slide_3_copy: 'View nearby driver details and match with confidence using real profile and vehicle information.',
    intro_slide_4_title: 'Stay safe on your ride',
    intro_slide_4_copy: 'Track status updates live, confirm identity details, and use direct call actions during your trip.',
    intro_slide_5_title: 'Find Courier',
    intro_slide_5_copy: 'Use BODA AU for quick courier requests like gas cylinders and luggage transfers across the city.',
    intro_skip: 'Skip',
    intro_back: 'Back',
    intro_next: 'Next',
    intro_get_started: 'Get Started',
    request_setup_title: 'Request Setup',
    request_setup_hint: 'Active Zanzibar locations only (pickup and dropoff).',
    choose_ride_title: 'Choose a ride',
    choose_ride_copy: 'Pick the ride that fits your trip best.',
    vehicle_type_label: 'Vehicle Type',
    vehicle_label_boda: 'Bodaboda',
    vehicle_label_bajaji: 'Bajaji',
    vehicle_copy_boda: 'Quick solo rides',
    vehicle_copy_bajaji: 'Budget 3-wheel rides',
    pickup_location_label: 'Pickup Location',
    dropoff_location_label: 'Dropoff Location',
    promo_code_label: 'Promo Code',
    promo_code_placeholder: 'Optional promo',
    eta_label: 'Estimated ETA',
    distance_label: 'Estimated Distance',
    fare_label: 'Estimated Fare (Motorcycle)',
    fare_label_bajaji: 'Estimated Fare (Bajaji)',
    nearby_drivers_btn: 'Check Nearby Drivers',
    request_ride_btn: 'Request Ride',
    schedule_ride_btn: 'Schedule Ride',
    load_history_btn: 'Load History',
    schedule_future_ride_title: 'Schedule a Future Ride',
    live_map_title: 'Live Map',
    lang_prompt_title: 'Choose your language',
    lang_prompt_copy: 'Select the language you prefer. You can change it later in your profile settings.',
    lang_prompt_en_copy: 'Continue in English',
    lang_prompt_sw_copy: 'Continue in Swahili',
    lang_prompt_note: 'You can always change this later from Profile Settings.',
    auth_brand: 'Zanzibar Bodaboda',
    auth_sign_in_title: 'Sign in to Account',
    auth_sign_in_copy: 'Use your phone number and password to continue.',
    auth_join_title: 'Join Zanzibar Bodaboda',
    auth_join_copy: 'Create a passenger or driver account in under a minute.',
    auth_full_name: 'Full Name',
    auth_email: 'Email',
    auth_phone: 'Phone Number',
    auth_password: 'Password',
    auth_role: 'Role',
    auth_role_passenger: 'Passenger',
    auth_role_driver: 'Driver',
    auth_sign_in_btn: 'Sign In',
    auth_register_btn: 'Create Account',
    auth_aside_title_signup: 'Hello, Friend!',
    auth_aside_copy_signup: 'Fill in your details and start your Zanzibar journey with us.',
    auth_aside_title_signin: 'Welcome Back!',
    auth_aside_copy_signin: 'Already have an account? Sign in and request your next ride.',
    auth_switch_signup: 'Sign Up',
    auth_switch_signin: 'Sign In',
    auth_forgot: 'Forgot password?',
    otp_title: 'Verify Email',
    otp_copy: 'Enter the OTP sent to your email to activate your account.',
    otp_code: 'OTP Code',
    otp_verify: 'Verify',
    otp_resend: 'Resend OTP',
    reset_title: 'Reset Password',
    reset_copy: 'Enter your email and we’ll send you a reset link.',
    reset_send: 'Send Reset Link',
    reset_sent_title: 'Check your email',
    reset_sent_copy: 'We’ve sent a password reset link to your email.',
    reset_confirm_title: 'Set New Password',
    reset_confirm_btn: 'Update Password',
    reset_complete_title: 'Password Updated',
    reset_complete_copy: 'Your password has been updated. You can now log in.',
    reset_back: 'Back to login',
    profile_full_name: 'Full Name',
    profile_email: 'Email',
    profile_phone: 'Phone Number',
    profile_language: 'Language',
    profile_picture: 'Profile Picture',
    lang_en: 'English',
    lang_sw: 'Swahili',
    profile_card_title: 'Profile',
    profile_settings_title: 'Profile Settings',
    personal_info_title: 'Personal Information',
    passenger_profile_title: 'Passenger Profile',
    passenger_profile_save: 'Save Passenger Profile',
    emergency_contacts_title: 'Emergency Contacts',
    contact1_name: 'Contact 1 Name',
    contact1_phone: 'Contact 1 Phone',
    contact1_relation: 'Contact 1 Relation',
    contact2_name: 'Contact 2 Name',
    contact2_phone: 'Contact 2 Phone',
    contact2_relation: 'Contact 2 Relation',
    emergency_contacts_save: 'Save Emergency Contacts',
    driver_profile_title: 'Driver Profile',
    driver_vehicle_type: 'Vehicle Type',
    vehicle_motorcycle: 'Motorcycle',
    vehicle_bajaji: 'Bajaji',
    driver_license_number: 'License Number',
    driver_plate_number: 'Plate Number',
    driver_profile_save: 'Save Driver Profile',
    driver_docs_title: 'Onboarding Documents',
    driver_doc_type: 'Document Type',
    doc_national_id: 'National ID',
    doc_license: 'Driver License',
    doc_insurance: 'Vehicle Insurance',
    driver_doc_upload: 'Upload File',
    driver_doc_upload_btn: 'Upload Document',
    payment_setup_title: 'Payment Setup',
    payment_setup_copy: 'Choose your payment method before requesting rides.',
    payment_cash: 'Cash Payment',
    payment_cash_copy: 'Pay the driver directly in TZS.',
    payment_continue: 'Continue',
    payment_settings_title: 'Payment Method',
    payment_save: 'Save Payment Preference',
    status_verified: 'Verified',
    status_unverified: 'Unverified',
    status_pending: 'Pending',
    status_online: 'Online',
    status_offline: 'Offline',
    status_active: 'Active',
    status_inactive: 'Inactive',
    status_guest: 'Guest',
    station_verified_label: 'Verified station',
    station_pending_label: 'Not verified yet',
    toast_back_online: 'Back online. Syncing queued actions...',
    toast_notifications_marked_read: 'Notifications marked as read',
    toast_notifications_cleared: 'Notifications cleared',
    toast_no_active_ride_for_chat: 'No active ride for chat',
    toast_offline_message_queued: 'Offline: message queued',
    toast_select_cash_payment: 'Select cash payment to continue',
    toast_cash_payment_required: 'Cash payment must be selected',
    toast_payment_saved: 'Payment preference saved',
    toast_password_required: 'Password confirmation required',
    toast_select_new_datetime: 'Select a new date and time first',
    toast_select_rating: 'Select a rating first',
    toast_nearby_drivers_loaded: 'Nearby drivers loaded',
    toast_pickup_dropoff_required: 'Select pickup and dropoff locations first',
    toast_same_location: 'Pickup and dropoff cannot be the same location',
    toast_ride_queued: 'Offline: ride request queued',
    toast_ride_requested: 'Ride requested',
    toast_ride_cancelled: 'Ride cancelled',
    toast_scheduled_ride_queued: 'Offline: scheduled ride queued',
    toast_history_loaded: 'History loaded',
    toast_geolocation_unsupported: 'Geolocation not supported on this browser',
    toast_driver_location_updated: 'Driver location updated from GPS',
    toast_location_unavailable: 'Unable to get your current location',
    toast_select_document: 'Select a document file first',
    toast_incoming_loaded: 'Incoming rides loaded',
    toast_no_ride_selected: 'No ride selected.',
    toast_earnings_loaded: 'Earnings loaded',
    toast_drivers_loaded: 'Drivers loaded',
    toast_passengers_loaded: 'Passengers loaded',
    toast_reports_loaded: 'Reports loaded',
    toast_settings_loaded: 'Settings loaded',
    toast_promos_loaded: 'Promos loaded',
    toast_monitoring_loaded: 'Monitoring loaded',
    toast_emergency_contacts_saved: 'Emergency contacts saved ({count})',
    toast_sos_sent: 'SOS sent successfully (contacts notified: {count})',
    toast_station_required: 'Station name is required',
    toast_station_submitted: 'Station request submitted. We will review it shortly.',
    toast_select_station: 'Select one of the suggested stations to continue.',
    toast_registration_success: 'Registration successful. Please verify the OTP sent to your email.',
    toast_email_verified: 'Email verified. You can now login.',
    toast_otp_resent: 'OTP resent. Check your email.',
    confirm_action_title: 'Confirm Action',
    confirm_action_message: 'Are you sure?',
    confirm_logout_title: 'Log Out',
    confirm_logout_message: 'Are you sure you want to log out?',
    confirm_yes: 'Yes',
    confirm_no: 'No',
    confirm_clear_notifications_title: 'Clear Notifications',
    confirm_clear_notifications_message: 'Clear all notifications? This cannot be undone.',
    confirm_cancel_ride_title: 'Cancel Ride',
    confirm_cancel_ride_message: 'Cancel this ride? This cannot be undone.',
    confirm_delete_driver_message_prefix: 'Delete driver',
    confirm_delete_passenger_message_prefix: 'Delete passenger',
    confirm_cannot_undo: 'This action cannot be undone.',
    confirm_sos_message: 'Send SOS alert now? This will notify admin and your emergency contacts.',
    prompt_delete_password: 'Enter your password to confirm deletion.',
    empty_no_notifications: 'No notifications yet.',
    empty_no_nearby_drivers: 'No nearby drivers found.',
    empty_no_active_ride: 'No active ride currently.',
    empty_no_messages: 'No messages yet.',
    empty_start_chat: 'Start a ride to chat.',
    empty_no_history: 'No ride history yet.',
    empty_no_incoming_rides: 'No incoming rides right now.',
    empty_no_scheduled_rides: 'No scheduled rides yet.',
    empty_no_documents: 'No documents uploaded yet.',
    empty_no_docs: 'No docs',
    empty_no_drivers: 'No drivers found.',
    empty_no_passengers: 'No passengers found.',
    empty_no_activity: 'No activity recorded yet.',
    empty_no_completed_rides: 'No completed rides yet.',
    empty_no_admin_scheduled_rides: 'No scheduled rides.',
    empty_no_sos_events: 'No SOS events logged.',
    empty_no_promos: 'No promos yet.',
    admin_reschedule_prompt: 'Set a new time for ride #{id}.',
    admin_cancel_scheduled_title: 'Cancel Scheduled Ride',
    admin_cancel_scheduled_message: 'Cancel scheduled ride #{id}? This cannot be undone.',
    driver_verify_btn: 'Verify',
    report_verified_drivers: 'Verified Drivers',
    account_delete_title: 'Danger Zone',
    account_delete_copy: 'Deleting your account removes your profile and ride history permanently.',
    account_delete_btn: 'Delete Account',
    account_delete_prompt: 'Type DELETE to confirm account deletion.',
    account_delete_cancelled: 'Account deletion cancelled',
  },
  sw: {
    nav_notifications: 'Arifa',
    nav_mark_all_read: 'Weka zote zimesomwa',
    nav_clear_all: 'Futa zote',
    nav_logout: 'Toka',
    footer_platform: 'Jukwaa',
    footer_support: 'Msaada',
    footer_system: 'Mfumo',
    footer_home: 'Mwanzo',
    footer_safety: 'Kituo cha Usalama',
    footer_help: 'Msaada na Mawasiliano',
    footer_terms: 'Masharti na Faragha',
    footer_secure: 'Kipindi Salama',
    footer_realtime: 'Arifa za Moja kwa Moja',
    footer_routes: 'Njia Hai za Zanzibar',
    intro_kicker: 'BODA AU kabla ya uzinduzi',
    intro_slide_1_title: 'Fungua akaunti',
    intro_slide_1_copy: 'Jisajili kama abiria au dereva kupitia mtiririko mmoja salama na uingie mara moja.',
    intro_slide_2_title: 'Omba safari yako',
    intro_slide_2_copy: 'Chagua eneo la kuchukua na kushukisha kutoka njia hai za Zanzibar na tuma ombi kwa sekunde.',
    intro_slide_3_title: 'Chagua dereva wako',
    intro_slide_3_copy: 'Tazama taarifa za madereva wa karibu na chagua kwa uhakika ukitumia wasifu halisi na taarifa za gari.',
    intro_slide_4_title: 'Kuwa salama safarini',
    intro_slide_4_copy: 'Fuata masasisho ya safari moja kwa moja, thibitisha taarifa za utambulisho, na tumia simu ya moja kwa moja wakati wa safari.',
    intro_slide_5_title: 'Pata Mjumbe',
    intro_slide_5_copy: 'Tumia BODA AU kwa maombi ya haraka ya mjumbe kama mitungi ya gesi na mizigo mijini.',
    intro_skip: 'Ruka',
    intro_back: 'Nyuma',
    intro_next: 'Ifuatayo',
    intro_get_started: 'Anza Sasa',
    request_setup_title: 'Mpangilio wa Ombi',
    request_setup_hint: 'Maeneo hai ya Zanzibar pekee (kuchukua na kushukisha).',
    choose_ride_title: 'Chagua safari',
    choose_ride_copy: 'Chagua safari inayofaa zaidi kwa safari yako.',
    vehicle_type_label: 'Aina ya Gari',
    vehicle_label_boda: 'Bodaboda',
    vehicle_label_bajaji: 'Bajaji',
    vehicle_copy_boda: 'Safari za haraka kwa mtu mmoja',
    vehicle_copy_bajaji: 'Safari nafuu za magurudumu matatu',
    pickup_location_label: 'Eneo la Kuchukua',
    dropoff_location_label: 'Eneo la Kushukisha',
    promo_code_label: 'Namba ya Promo',
    promo_code_placeholder: 'Promo ya hiari',
    eta_label: 'Muda Uliokadiriwa',
    distance_label: 'Umbali Uliokadiriwa',
    fare_label: 'Nauli Uliokadiriwa (Bodaboda)',
    fare_label_bajaji: 'Nauli Uliokadiriwa (Bajaji)',
    nearby_drivers_btn: 'Angalia Madereva wa Karibu',
    request_ride_btn: 'Omba Safari',
    schedule_ride_btn: 'Panga Safari',
    load_history_btn: 'Pakua Historia',
    schedule_future_ride_title: 'Panga Safari ya Baadaye',
    live_map_title: 'Ramani Hai',
    lang_prompt_title: 'Chagua lugha yako',
    lang_prompt_copy: 'Chagua lugha unayopendelea. Unaweza kubadilisha baadaye kwenye mipangilio ya wasifu.',
    lang_prompt_en_copy: 'Endelea kwa Kiingereza',
    lang_prompt_sw_copy: 'Endelea kwa Kiswahili',
    lang_prompt_note: 'Unaweza kubadilisha hili baadaye kwenye Mipangilio ya Wasifu.',
    auth_brand: 'Zanzibar Bodaboda',
    auth_sign_in_title: 'Ingia kwenye Akaunti',
    auth_sign_in_copy: 'Tumia namba ya simu na nenosiri kuendelea.',
    auth_join_title: 'Jiunge na Zanzibar Bodaboda',
    auth_join_copy: 'Unda akaunti ya abiria au dereva kwa dakika moja.',
    auth_full_name: 'Jina Kamili',
    auth_email: 'Barua Pepe',
    auth_phone: 'Namba ya Simu',
    auth_password: 'Nenosiri',
    auth_role: 'Wajibu',
    auth_role_passenger: 'Abiria',
    auth_role_driver: 'Dereva',
    auth_sign_in_btn: 'Ingia',
    auth_register_btn: 'Unda Akaunti',
    auth_aside_title_signup: 'Karibu!',
    auth_aside_copy_signup: 'Jaza taarifa zako na anza safari yako Zanzibar.',
    auth_aside_title_signin: 'Karibu Tena!',
    auth_aside_copy_signin: 'Una akaunti? Ingia na omba safari.',
    auth_switch_signup: 'Jisajili',
    auth_switch_signin: 'Ingia',
    auth_forgot: 'Umesahau nenosiri?',
    otp_title: 'Thibitisha Barua Pepe',
    otp_copy: 'Weka OTP iliyotumwa kwenye barua pepe yako ili kuamilisha akaunti.',
    otp_code: 'Namba ya OTP',
    otp_verify: 'Thibitisha',
    otp_resend: 'Tuma OTP Tena',
    reset_title: 'Weka Upya Nenosiri',
    reset_copy: 'Weka barua pepe yako na tutakutumia kiungo cha kuweka upya.',
    reset_send: 'Tuma Kiungo cha Kuweka Upya',
    reset_sent_title: 'Angalia barua pepe',
    reset_sent_copy: 'Tumeutuma kiungo cha kuweka upya nenosiri kwenye barua pepe yako.',
    reset_confirm_title: 'Weka Nenosiri Jipya',
    reset_confirm_btn: 'Sasisha Nenosiri',
    reset_complete_title: 'Nenosiri Limesasishwa',
    reset_complete_copy: 'Nenosiri lako limesasishwa. Sasa unaweza kuingia.',
    reset_back: 'Rudi kwenye kuingia',
    profile_full_name: 'Jina Kamili',
    profile_email: 'Barua Pepe',
    profile_phone: 'Namba ya Simu',
    profile_language: 'Lugha',
    profile_picture: 'Picha ya Wasifu',
    lang_en: 'Kiingereza',
    lang_sw: 'Kiswahili',
    profile_card_title: 'Wasifu',
    profile_settings_title: 'Mipangilio ya Wasifu',
    personal_info_title: 'Taarifa Binafsi',
    passenger_profile_title: 'Wasifu wa Abiria',
    passenger_profile_save: 'Hifadhi Wasifu wa Abiria',
    emergency_contacts_title: 'Mawasiliano ya Dharura',
    contact1_name: 'Jina la Mtu wa Dharura 1',
    contact1_phone: 'Simu ya Mtu wa Dharura 1',
    contact1_relation: 'Uhusiano wa Mtu wa Dharura 1',
    contact2_name: 'Jina la Mtu wa Dharura 2',
    contact2_phone: 'Simu ya Mtu wa Dharura 2',
    contact2_relation: 'Uhusiano wa Mtu wa Dharura 2',
    emergency_contacts_save: 'Hifadhi Mawasiliano ya Dharura',
    driver_profile_title: 'Wasifu wa Dereva',
    driver_vehicle_type: 'Aina ya Gari',
    vehicle_motorcycle: 'Bodaboda',
    vehicle_bajaji: 'Bajaji',
    driver_license_number: 'Namba ya Leseni',
    driver_plate_number: 'Namba ya Bamba',
    driver_profile_save: 'Hifadhi Wasifu wa Dereva',
    driver_docs_title: 'Nyaraka za Usajili',
    driver_doc_type: 'Aina ya Nyaraka',
    doc_national_id: 'Kitambulisho cha Taifa',
    doc_license: 'Leseni ya Dereva',
    doc_insurance: 'Bima ya Gari',
    driver_doc_upload: 'Pakia Faili',
    driver_doc_upload_btn: 'Pakia Nyaraka',
    payment_setup_title: 'Mpangilio wa Malipo',
    payment_setup_copy: 'Chagua njia ya malipo kabla ya kuomba safari.',
    payment_cash: 'Malipo kwa Taslimu',
    payment_cash_copy: 'Mlipo dereva moja kwa moja kwa TZS.',
    payment_continue: 'Endelea',
    payment_settings_title: 'Njia ya Malipo',
    payment_save: 'Hifadhi Njia ya Malipo',
    status_verified: 'Imethibitishwa',
    status_unverified: 'Haijathibitishwa',
    status_pending: 'Inasubiri',
    status_online: 'Mtandaoni',
    status_offline: 'Nje ya mtandao',
    status_active: 'Hai',
    status_inactive: 'Haitumiki',
    status_guest: 'Mgeni',
    station_verified_label: 'Kituo kilichothibitishwa',
    station_pending_label: 'Bado hakijathibitishwa',
    toast_back_online: 'Umerudi mtandaoni. Tunatumia vitendo vilivyohifadhiwa...',
    toast_notifications_marked_read: 'Arifa zimewekwa kuwa zimesomwa',
    toast_notifications_cleared: 'Arifa zimefutwa',
    toast_no_active_ride_for_chat: 'Hakuna safari hai ya kuzungumza',
    toast_offline_message_queued: 'Nje ya mtandao: ujumbe umehifadhiwa',
    toast_select_cash_payment: 'Chagua malipo ya taslimu ili kuendelea',
    toast_cash_payment_required: 'Malipo ya taslimu lazima yachaguliwe',
    toast_payment_saved: 'Mpangilio wa malipo umehifadhiwa',
    toast_password_required: 'Uthibitisho wa nenosiri unahitajika',
    toast_select_new_datetime: 'Chagua tarehe na muda mpya kwanza',
    toast_select_rating: 'Chagua ukadiriaji kwanza',
    toast_nearby_drivers_loaded: 'Madereva wa karibu wamepakuliwa',
    toast_pickup_dropoff_required: 'Chagua maeneo ya kuchukua na kushukisha kwanza',
    toast_same_location: 'Kuchukua na kushukisha haviwezi kuwa eneo moja',
    toast_ride_queued: 'Nje ya mtandao: ombi la safari limehifadhiwa',
    toast_ride_requested: 'Safari imeombwa',
    toast_ride_cancelled: 'Safari imeghairiwa',
    toast_scheduled_ride_queued: 'Nje ya mtandao: safari iliyopangwa imehifadhiwa',
    toast_history_loaded: 'Historia imepakuliwa',
    toast_geolocation_unsupported: 'Geolocation haitumiki kwenye kivinjari hiki',
    toast_driver_location_updated: 'Eneo la dereva limesasishwa kutoka GPS',
    toast_location_unavailable: 'Imeshindikana kupata eneo lako la sasa',
    toast_select_document: 'Chagua faili la nyaraka kwanza',
    toast_incoming_loaded: 'Safari zinazoingia zimepakuliwa',
    toast_no_ride_selected: 'Hakuna safari iliyochaguliwa.',
    toast_earnings_loaded: 'Mapato yamepakuliwa',
    toast_drivers_loaded: 'Madereva wamepakuliwa',
    toast_passengers_loaded: 'Abiria wamepakuliwa',
    toast_reports_loaded: 'Ripoti zimepakuliwa',
    toast_settings_loaded: 'Mipangilio imepakuliwa',
    toast_promos_loaded: 'Promo zimepakuliwa',
    toast_monitoring_loaded: 'Ufuatiliaji umepakuliwa',
    toast_emergency_contacts_saved: 'Mawasiliano ya dharura yamehifadhiwa ({count})',
    toast_sos_sent: 'SOS imetumwa kikamilifu (mawasiliano yaliyotaarifiwa: {count})',
    toast_station_required: 'Jina la kituo linahitajika',
    toast_station_submitted: 'Ombi la kituo limetumwa. Tutakagua hivi karibuni.',
    toast_select_station: 'Chagua mojawapo ya vituo vilivyopendekezwa ili kuendelea.',
    toast_registration_success: 'Usajili umefanikiwa. Tafadhali thibitisha OTP iliyotumwa kwenye barua pepe yako.',
    toast_email_verified: 'Barua pepe imethibitishwa. Sasa unaweza kuingia.',
    toast_otp_resent: 'OTP imetumwa tena. Angalia barua pepe yako.',
    confirm_action_title: 'Thibitisha Kitendo',
    confirm_action_message: 'Una uhakika?',
    confirm_logout_title: 'Toka',
    confirm_logout_message: 'Una uhakika unataka kutoka?',
    confirm_yes: 'Ndiyo',
    confirm_no: 'Hapana',
    confirm_clear_notifications_title: 'Futa Arifa',
    confirm_clear_notifications_message: 'Futa arifa zote? Hili haliwezi kutenduliwa.',
    confirm_cancel_ride_title: 'Ghairi Safari',
    confirm_cancel_ride_message: 'Ghairi safari hii? Hili haliwezi kutenduliwa.',
    confirm_delete_driver_message_prefix: 'Futa dereva',
    confirm_delete_passenger_message_prefix: 'Futa abiria',
    confirm_cannot_undo: 'Kitendo hiki hakiwezi kutenduliwa.',
    confirm_sos_message: 'Tuma tahadhari ya SOS sasa? Hii itaarifu admin na watu wako wa dharura.',
    prompt_delete_password: 'Weka nenosiri lako kuthibitisha ufutaji.',
    empty_no_notifications: 'Bado hakuna arifa.',
    empty_no_nearby_drivers: 'Hakuna madereva wa karibu waliopatikana.',
    empty_no_active_ride: 'Hakuna safari hai kwa sasa.',
    empty_no_messages: 'Bado hakuna ujumbe.',
    empty_start_chat: 'Anza safari ili kuzungumza.',
    empty_no_history: 'Bado hakuna historia ya safari.',
    empty_no_incoming_rides: 'Hakuna safari zinazoingia kwa sasa.',
    empty_no_scheduled_rides: 'Bado hakuna safari zilizopangwa.',
    empty_no_documents: 'Bado hakuna nyaraka zilizopakiwa.',
    empty_no_docs: 'Hakuna nyaraka',
    empty_no_drivers: 'Hakuna madereva waliopatikana.',
    empty_no_passengers: 'Hakuna abiria waliopatikana.',
    empty_no_activity: 'Bado hakuna shughuli iliyorekodiwa.',
    empty_no_completed_rides: 'Bado hakuna safari zilizokamilika.',
    empty_no_admin_scheduled_rides: 'Hakuna safari zilizopangwa.',
    empty_no_sos_events: 'Bado hakuna matukio ya SOS.',
    empty_no_promos: 'Bado hakuna promo.',
    admin_reschedule_prompt: 'Weka muda mpya kwa safari #{id}.',
    admin_cancel_scheduled_title: 'Ghairi Safari Iliyo Pangwa',
    admin_cancel_scheduled_message: 'Ghairi safari iliyopangwa #{id}? Hili haliwezi kutenduliwa.',
    driver_verify_btn: 'Thibitisha',
    report_verified_drivers: 'Madereva Waliothibitishwa',
    account_delete_title: 'Eneo Hatari',
    account_delete_copy: 'Kufuta akaunti yako kunaondoa wasifu na historia ya safari kabisa.',
    account_delete_btn: 'Futa Akaunti',
    account_delete_prompt: 'Andika DELETE kuthibitisha kufuta akaunti.',
    account_delete_cancelled: 'Kufuta akaunti kumeghairishwa',
  },
};

function t(key, fallback = '') {
  const lang = normalizeLanguage(safeStorageGet(languageStorageKey));
  return translations[lang]?.[key] || translations.en[key] || fallback || key;
}

function applyTranslations(lang) {
  const active = normalizeLanguage(lang);
  document.documentElement.setAttribute('lang', active);
  document.querySelectorAll('[data-i18n]').forEach((el) => {
    const key = el.dataset.i18n;
    if (!key) return;
    el.textContent = translations[active]?.[key] || translations.en[key] || el.textContent;
  });
  document.querySelectorAll('[data-i18n-placeholder]').forEach((el) => {
    const key = el.dataset.i18nPlaceholder;
    if (!key) return;
    el.setAttribute('placeholder', translations[active]?.[key] || translations.en[key] || '');
  });
  document.querySelectorAll('[data-i18n-aria]').forEach((el) => {
    const key = el.dataset.i18nAria;
    if (!key) return;
    el.setAttribute('aria-label', translations[active]?.[key] || translations.en[key] || '');
  });
}

function setAppLanguage(lang) {
  const next = normalizeLanguage(lang);
  safeStorageSet(languageStorageKey, next);
  applyTranslations(next);
  window.dispatchEvent(new CustomEvent('languagechange', { detail: next }));
}

function getAppLanguage() {
  return normalizeLanguage(safeStorageGet(languageStorageKey));
}

function initLanguage() {
  const root = document.getElementById('dashboard-root');
  const storedLanguage = normalizeLanguage(safeStorageGet(languageStorageKey));
  const rawRootLanguage = root?.dataset.language?.trim() || '';
  const rootLanguage = normalizeLanguage(rawRootLanguage);
  const preferred = safeStorageGet(languageStorageKey) ? storedLanguage : rawRootLanguage && translations[rawRootLanguage] ? rootLanguage : '';
  if (preferred) {
    safeStorageSet(languageStorageKey, preferred);
    applyTranslations(preferred);
    languagePromptRequired = false;
    hideLanguagePrompt();
  } else {
    applyTranslations('en');
    languagePromptRequired = !safeStorageGet(languageStorageKey) && !rawRootLanguage;
    if (languagePromptRequired && !splashScreen) {
      showLanguagePromptIfNeeded();
    }
  }
}

window.setAppLanguage = setAppLanguage;
window.applyTranslations = applyTranslations;
window.t = t;
window.getAppLanguage = getAppLanguage;
window.showLanguagePromptIfNeeded = showLanguagePromptIfNeeded;

if (languagePromptButtons.length) {
  languagePromptButtons.forEach((btn) => {
    btn.addEventListener('click', () => {
      chooseLanguage(btn.dataset.languageChoice);
    });
  });
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initLanguage, { once: true });
} else {
  initLanguage();
}
