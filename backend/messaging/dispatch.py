"""
Multi-Channel Alert Dispatcher Service.

Routes high-priority security alerts to:
  1. Firebase Cloud Messaging (FCM) — Push notifications to Android/iOS mobile apps
  2. WebPush — Browser push notifications
  3. Emergency Webhooks — HTTP POST with HMAC SHA-256 signature digests
  4. Twilio SMS / Voice Alerts — Mobile emergency dispatch
"""

import os
import json
import hmac
import hashlib
import time
import logging
import httpx
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

FCM_SERVER_KEY = os.getenv("FCM_SERVER_KEY", "")
WEBHOOK_SECRET = os.getenv("ALERT_WEBHOOK_SECRET", "sybau_webhook_secret_2026")
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_FROM_NUMBER = os.getenv("TWILIO_FROM_NUMBER", "")


class AlertDispatcher:
    """Multi-channel alert routing engine for production surveillance notifications."""

    @staticmethod
    def _compute_hmac_signature(payload_json: str, secret: str) -> str:
        return hmac.new(
            secret.encode("utf-8"),
            payload_json.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()

    async def dispatch_webhook(self, webhook_url: str, alert_data: Dict[str, Any]) -> bool:
        """
        Pushes signed HTTP POST webhook alert to external Control Room / Law Enforcement server.
        Includes X-VMS-Signature header with HMAC SHA-256.
        """
        if not webhook_url:
            return False

        payload_str = json.dumps(alert_data, sort_keys=True)
        signature = self._compute_hmac_signature(payload_str, WEBHOOK_SECRET)
        headers = {
            "Content-Type": "application/json",
            "X-VMS-Signature": signature,
            "User-Agent": "Sybau-VMS-Dispatcher/1.0"
        }

        try:
            async with httpx.AsyncClient(timeout=4.0) as client:
                resp = await client.post(webhook_url, content=payload_str, headers=headers)
                logger.info(f"[Dispatcher] Webhook dispatched to {webhook_url} (HTTP {resp.status_code})")
                return resp.status_code in (200, 201, 202)
        except Exception as e:
            logger.warning(f"[Dispatcher] Webhook failed for {webhook_url}: {e}")
            return False

    async def dispatch_fcm_push(self, device_token: str, title: str, body: str, extra_data: Optional[Dict] = None) -> bool:
        """
        Sends Firebase Cloud Messaging push notification to mobile devices.
        """
        if not FCM_SERVER_KEY or not device_token:
            logger.debug("[Dispatcher] FCM_SERVER_KEY not configured; skipping push dispatch.")
            return False

        url = "https://fcm.googleapis.com/fcm/send"
        headers = {
            "Authorization": f"key={FCM_SERVER_KEY}",
            "Content-Type": "application/json"
        }
        payload = {
            "to": device_token,
            "notification": {
                "title": title,
                "body": body,
                "sound": "default",
                "badge": 1
            },
            "data": extra_data or {}
        }

        try:
            async with httpx.AsyncClient(timeout=4.0) as client:
                resp = await client.post(url, json=payload, headers=headers)
                return resp.status_code == 200
        except Exception as e:
            logger.warning(f"[Dispatcher] FCM push error: {e}")
            return False

    async def dispatch_twilio_sms(self, to_phone: str, message_body: str) -> bool:
        """
        Sends SMS alert to operational personnel via Twilio API.
        """
        if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN or not TWILIO_FROM_NUMBER:
            logger.debug("[Dispatcher] Twilio credentials not configured; skipping SMS dispatch.")
            return False

        url = f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_ACCOUNT_SID}/Messages.json"
        auth = (TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        data = {
            "From": TWILIO_FROM_NUMBER,
            "To": to_phone,
            "Body": message_body
        }

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.post(url, data=data, auth=auth)
                return resp.status_code in (200, 201)
        except Exception as e:
            logger.warning(f"[Dispatcher] Twilio SMS dispatch error: {e}")
            return False

    def dispatch_alert(self, alert_data: Dict[str, Any], webhook_url: Optional[str] = None, phone: Optional[str] = None):
        """
        Synchronous/Async facade to trigger multi-channel alert dispatch.
        """
        import asyncio
        title = f"SECURITY ALERT: {alert_data.get('type', 'ANOMALY').upper()}"
        body = alert_data.get("message", "Suspicious event detected on camera feed.")

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                if webhook_url:
                    asyncio.create_task(self.dispatch_webhook(webhook_url, alert_data))
                if phone:
                    asyncio.create_task(self.dispatch_twilio_sms(phone, f"{title} - {body}"))
            else:
                if webhook_url:
                    loop.run_until_complete(self.dispatch_webhook(webhook_url, alert_data))
        except Exception as e:
            logger.debug(f"[Dispatcher] Alert dispatch wrapper note: {e}")


alert_dispatcher = AlertDispatcher()
