import json
import logging
import base64
import subprocess
import tempfile
import time
from urllib import error, parse, request

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction

from .models import AppNotification, NotificationLog, PushDeviceToken

logger = logging.getLogger(__name__)


def _base64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode('utf-8').rstrip('=')


def _load_fcm_service_account() -> dict:
    raw_json = getattr(settings, 'FCM_SERVICE_ACCOUNT_JSON', '').strip()
    file_path = getattr(settings, 'FCM_SERVICE_ACCOUNT_FILE', '').strip()
    if raw_json:
        return json.loads(raw_json)
    if file_path:
        with open(file_path, 'r', encoding='utf-8') as handle:
            return json.load(handle)
    raise ValueError('FCM service account configuration is missing')


def _sign_jwt_rs256(private_key_pem: str, signing_input: str) -> str:
    with tempfile.NamedTemporaryFile('w', suffix='.pem', delete=True) as key_file:
        key_file.write(private_key_pem)
        key_file.flush()
        proc = subprocess.run(
            ['openssl', 'dgst', '-sha256', '-sign', key_file.name, '-binary'],
            input=signing_input.encode('utf-8'),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.decode('utf-8', errors='ignore').strip() or 'JWT signing failed')
    return _base64url_encode(proc.stdout)


def _build_service_account_jwt(service_account: dict) -> str:
    header = {'alg': 'RS256', 'typ': 'JWT'}
    now = int(time.time())
    payload = {
        'iss': service_account['client_email'],
        'scope': 'https://www.googleapis.com/auth/firebase.messaging',
        'aud': 'https://oauth2.googleapis.com/token',
        'iat': now,
        'exp': now + 3600,
    }
    encoded_header = _base64url_encode(json.dumps(header, separators=(',', ':')).encode('utf-8'))
    encoded_payload = _base64url_encode(json.dumps(payload, separators=(',', ':')).encode('utf-8'))
    signing_input = f'{encoded_header}.{encoded_payload}'
    signature = _sign_jwt_rs256(service_account['private_key'], signing_input)
    return f'{signing_input}.{signature}'


def _fetch_google_access_token(service_account: dict) -> str:
    assertion = _build_service_account_jwt(service_account)
    response = request.urlopen(
        request.Request(
            'https://oauth2.googleapis.com/token',
            data=parse.urlencode(
                {
                    'grant_type': 'urn:ietf:params:oauth:grant-type:jwt-bearer',
                    'assertion': assertion,
                }
            ).encode('utf-8'),
            method='POST',
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
        ),
        timeout=10,
    )
    data = json.loads(response.read().decode('utf-8'))
    access_token = data.get('access_token', '')
    if not access_token:
        raise RuntimeError('Unable to obtain Firebase access token')
    return access_token


def _send_push_legacy(user, title: str, message: str, payload: dict | None = None) -> dict:
    server_key = getattr(settings, 'FCM_SERVER_KEY', '').strip()
    if not server_key:
        return {'sent': 0, 'skipped': True, 'reason': 'fcm server key missing'}

    tokens = list(PushDeviceToken.objects.filter(user=user, is_active=True).values_list('device_token', flat=True))
    if not tokens:
        return {'sent': 0, 'skipped': True, 'reason': 'no active push tokens'}

    payload_body = {
        'registration_ids': tokens,
        'priority': 'high',
        'notification': {
            'title': title[:120],
            'body': message[:240],
        },
        'data': {str(key): str(value) for key, value in (payload or {}).items()},
    }
    req = request.Request(
        'https://fcm.googleapis.com/fcm/send',
        data=json.dumps(payload_body).encode('utf-8'),
        method='POST',
        headers={
            'Authorization': f'key={server_key}',
            'Content-Type': 'application/json',
        },
    )

    with request.urlopen(req, timeout=10) as response:
        response_data = json.loads(response.read().decode('utf-8'))

    results = response_data.get('results') or []
    invalid_tokens = set()
    for index, result in enumerate(results):
        if isinstance(result, dict) and result.get('error') in {'NotRegistered', 'InvalidRegistration'}:
            if index < len(tokens):
                invalid_tokens.add(tokens[index])

    if invalid_tokens:
        PushDeviceToken.objects.filter(device_token__in=invalid_tokens).update(is_active=False)

    return {
        'sent': len(tokens) - len(invalid_tokens),
        'invalidated': len(invalid_tokens),
        'response': response_data,
    }


def _send_push_v1(user, title: str, message: str, payload: dict | None = None) -> dict:
    service_account = _load_fcm_service_account()
    project_id = getattr(settings, 'FCM_PROJECT_ID', '').strip() or service_account.get('project_id', '')
    if not project_id:
        raise ValueError('FCM project id is missing')

    tokens = list(PushDeviceToken.objects.filter(user=user, is_active=True).values_list('device_token', flat=True))
    if not tokens:
        return {'sent': 0, 'skipped': True, 'reason': 'no active push tokens'}

    access_token = _fetch_google_access_token(service_account)
    base_url = f'https://fcm.googleapis.com/v1/projects/{project_id}/messages:send'
    sent = 0
    invalid_tokens = set()
    last_response = None
    for token in tokens:
        body = {
            'message': {
                'token': token,
                'notification': {
                    'title': title[:120],
                    'body': message[:240],
                },
                'data': {str(key): str(value) for key, value in (payload or {}).items()},
                'android': {'priority': 'HIGH'},
            }
        }
        req = request.Request(
            base_url,
            data=json.dumps(body).encode('utf-8'),
            method='POST',
            headers={
                'Authorization': f'Bearer {access_token}',
                'Content-Type': 'application/json',
            },
        )
        try:
            with request.urlopen(req, timeout=10) as response:
                last_response = json.loads(response.read().decode('utf-8'))
                sent += 1
        except error.HTTPError as exc:
            detail = exc.read().decode('utf-8', errors='ignore')
            last_response = {'status': exc.code, 'detail': detail}
            if exc.code in {400, 404}:
                invalid_tokens.add(token)
            else:
                logger.warning('Firebase v1 push failed for user %s token %s: %s', getattr(user, 'id', None), token[:12], detail)

    if invalid_tokens:
        PushDeviceToken.objects.filter(device_token__in=invalid_tokens).update(is_active=False)

    return {
        'sent': sent,
        'invalidated': len(invalid_tokens),
        'response': last_response or {},
    }


def _twilio_send(to_number: str, body: str) -> tuple[str, str]:
    account_sid = settings.TWILIO_ACCOUNT_SID
    auth_token = settings.TWILIO_AUTH_TOKEN
    from_number = settings.TWILIO_FROM_NUMBER

    if not account_sid or not auth_token or not from_number:
        raise ValueError('Twilio configuration is incomplete')

    url = f'https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json'
    payload = parse.urlencode({'To': to_number, 'From': from_number, 'Body': body}).encode('utf-8')
    req = request.Request(url, data=payload, method='POST')

    credentials = f'{account_sid}:{auth_token}'.encode('utf-8')
    auth_header = 'Basic ' + base64.b64encode(credentials).decode('utf-8')
    req.add_header('Authorization', auth_header)
    req.add_header('Content-Type', 'application/x-www-form-urlencoded')

    with request.urlopen(req, timeout=10) as response:
        body_data = response.read().decode('utf-8')
        parsed = json.loads(body_data)
        return NotificationLog.Status.SENT, str(parsed.get('sid', ''))


def send_sms_notification(*, user, phone_number: str, event: str, message: str) -> NotificationLog:
    provider = settings.SMS_PROVIDER.lower().strip()

    if provider != 'twilio':
        logger.info('SMS simulated: %s %s %s', phone_number, event, message)
        return NotificationLog.objects.create(
            user=user,
            phone_number=phone_number,
            event=event,
            message=message,
            status=NotificationLog.Status.SIMULATED,
        )

    try:
        status, provider_message_id = _twilio_send(phone_number, message)
        return NotificationLog.objects.create(
            user=user,
            phone_number=phone_number,
            event=event,
            message=message,
            status=status,
            provider_message_id=provider_message_id,
        )
    except (ValueError, error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        logger.warning('SMS send failed for %s: %s', phone_number, exc)
        return NotificationLog.objects.create(
            user=user,
            phone_number=phone_number,
            event=event,
            message=message,
            status=NotificationLog.Status.FAILED,
            error_message=str(exc),
        )


def create_app_notification(*, user, event: str, title: str, message: str, payload: dict | None = None):
    notification = AppNotification.objects.create(
        user=user,
        event=event,
        title=title,
        message=message,
        payload=payload or {},
    )
    if getattr(settings, 'PUSH_PROVIDER', 'native').strip().lower() in {'firebase', 'firebase_v1'}:
        notification_payload = dict(payload or {})

        def _dispatch_push():
            try:
                send_push_notification(user=user, title=title, message=message, payload=notification_payload)
            except Exception as exc:  # noqa: BLE001
                logger.warning('Push notification dispatch failed for user %s: %s', getattr(user, 'id', None), exc)

        transaction.on_commit(_dispatch_push)
    return notification


def send_push_notification(*, user, title: str, message: str, payload: dict | None = None) -> dict:
    provider = getattr(settings, 'PUSH_PROVIDER', 'native').strip().lower()
    if provider not in {'firebase', 'firebase_v1'}:
        return {'sent': 0, 'skipped': True, 'reason': 'push provider disabled'}

    if provider == 'firebase_v1':
        return _send_push_v1(user=user, title=title, message=message, payload=payload)
    return _send_push_legacy(user=user, title=title, message=message, payload=payload)


def send_whatsapp_otp(*, user, phone_number: str, otp_code: str) -> NotificationLog:
    message = f'BODA AU OTP: {otp_code}. This code expires in 10 minutes.'
    logger.info('WhatsApp OTP simulated: %s %s', phone_number, message)
    return NotificationLog.objects.create(
        user=user,
        phone_number=phone_number,
        event='whatsapp_otp',
        message=message,
        status=NotificationLog.Status.SIMULATED,
    )


def send_email_otp(*, user, email: str, otp_code: str) -> NotificationLog:
    subject = 'BODA AU Email Verification'
    message = f'Your BODA AU verification code is {otp_code}. This code expires in 10 minutes.'
    try:
        send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [email], fail_silently=False)
        status = NotificationLog.Status.SENT
        error_message = ''
    except Exception as exc:  # noqa: BLE001
        logger.warning('Email OTP send failed for %s: %s', email, exc)
        status = NotificationLog.Status.FAILED
        error_message = str(exc)
    return NotificationLog.objects.create(
        user=user,
        phone_number=email,
        event='email_otp',
        message=message,
        status=status,
        error_message=error_message,
    )
