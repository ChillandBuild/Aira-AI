"""
TeleCMI CHUB Click-to-Call client.

Docs:
  https://doc.telecmi.com/chub/docs/app-auth
  https://doc.telecmi.com/chub/docs/click-to-call-admin
  https://doc.telecmi.com/chub/docs/play-record
"""
import logging
from typing import Any
from urllib.parse import urlencode

import httpx

logger = logging.getLogger(__name__)

TELECMI_BASE_URL = "https://rest.telecmi.com/v2/webrtc/click2call"

# Recording/voicemail playback. The CHUB docs specify `rest.telecmi.com/v2/play`
# with an `appid`/`secret`/`file` query — NOT piopiy.telecmi.com/v1/play, which
# belongs to the separate PIOPIY product and takes `token` instead of `secret`.
TELECMI_RECORDING_BASE_URL = "https://rest.telecmi.com/v2/play"

# An Indian number is 12 digits once the 91 country code is attached. A mistyped
# setting (a dropped digit in a configured caller ID) is accepted by TeleCMI and
# only fails at dial time, so warn while the bad value is still traceable.
_IN_MSISDN_DIGITS = 12
_MIN_MSISDN_DIGITS = 10
_MAX_MSISDN_DIGITS = 15


def _implausible_reason(digits: str) -> str | None:
    """Describe why `digits` cannot be a valid MSISDN, or None if it looks fine."""
    if not (_MIN_MSISDN_DIGITS <= len(digits) <= _MAX_MSISDN_DIGITS):
        return f"{len(digits)} digits is outside the {_MIN_MSISDN_DIGITS}-{_MAX_MSISDN_DIGITS} range"
    if digits.startswith("91") and len(digits) != _IN_MSISDN_DIGITS:
        return f"an Indian (+91) number must be {_IN_MSISDN_DIGITS} digits, got {len(digits)}"
    return None


def _normalize_phone(phone: str) -> str:
    cleaned = phone.replace(" ", "").replace("-", "").replace("+", "")
    if len(cleaned) == 10:
        cleaned = f"91{cleaned}"
    if cleaned.isdigit() and (reason := _implausible_reason(cleaned)):
        logger.warning(
            f"TeleCMI phone number looks malformed ({cleaned}): {reason} "
            f"— check the configured value for a typo"
        )
    return cleaned


def build_recording_url(appid: str, secret: str, filename: str, base_url: str | None = None) -> str:
    """Build a CHUB recording/voicemail download URL for a CDR `filename`.

    Per the play-record docs the parameter is `secret`, not `token`.
    """
    return f"{base_url or TELECMI_RECORDING_BASE_URL}?" + urlencode(
        {"appid": appid, "secret": secret, "file": filename}
    )


async def initiate_click2call(
    agent_id: str,
    secret: str,
    to: str,
    callerid: str,
    *,
    custom: str | None = None,
    followme: bool = True,
    webrtc: bool = False,
) -> dict[str, Any]:
    """Initiate click-to-call via TeleCMI CHUB Admin API.

    Connects to the agent's phone (via followme mobile by default, or webrtc softphone)
    first, and once answered, connects to the customer number.
    """
    normalized_to = _normalize_phone(to)
    normalized_callerid = _normalize_phone(callerid)

    payload: dict[str, Any] = {
        "user_id": agent_id,
        "secret": secret,
        "to": int(normalized_to) if normalized_to.isdigit() else normalized_to,
        "callerid": int(normalized_callerid) if normalized_callerid.isdigit() else normalized_callerid,
        "webrtc": webrtc,
        "followme": followme,
    }
    if custom:
        payload["extra_params"] = {"call_log_id": custom}

    logger.info(f"TeleCMI CHUB click2call: user_id={agent_id}, callerid={normalized_callerid}, to={normalized_to}")

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(TELECMI_BASE_URL, json=payload)
        try:
            data = resp.json()
        except Exception:
            resp.raise_for_status()
            raise RuntimeError(f"TeleCMI returned unexpected non-JSON response ({resp.status_code})")

    code = data.get("code")
    if code != 200:
        msg = data.get("msg") or data.get("message") or f"HTTP {resp.status_code}"
        logger.error(f"TeleCMI click2call rejected: code={code}, msg={msg}, response={data}")
        if code == 407:
            raise RuntimeError("Invalid TeleCMI App Secret. Please verify App Secret in Settings → Telecalling.")
        elif code == 404:
            raise RuntimeError(f"Invalid TeleCMI User ID '{agent_id}'. Please check caller's User ID in Team / Roles.")
        elif code == 420:
            raise RuntimeError(f"TeleCMI error (420): {msg}. Follow-me calls to mobile numbers are disabled on this TeleCMI account. Please contact TeleCMI support to enable Follow-Me on your App.")
        elif code == 400:
            raise RuntimeError(f"TeleCMI validation error: {msg}")
        raise RuntimeError(f"TeleCMI error ({code}): {msg}")

    request_id = data.get("request_id")
    logger.info(f"TeleCMI click2call success: request_id={request_id}")
    return data
