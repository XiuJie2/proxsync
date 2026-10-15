"""Model fields for credentials stored by the plugin.

Secrets are encrypted at rest with a Fernet key derived from Django's
SECRET_KEY, so a database dump alone does not reveal them. Values written
before encryption was introduced are read as plaintext and encrypted on the
next save. If SECRET_KEY changes, stored secrets can no longer be decrypted
and have to be entered again.
"""

import base64
import hashlib
import logging

from django.db import models

logger = logging.getLogger(__name__)

_PREFIX = "enc:"

# Shown in the changelog instead of the real value.
SECRET_MASK = "********"


def _fernet():
    from cryptography.fernet import Fernet
    from django.conf import settings

    digest = hashlib.sha256(b"pve_sync_plugin:" + settings.SECRET_KEY.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(value):
    if not value or value.startswith(_PREFIX):
        return value
    return _PREFIX + _fernet().encrypt(value.encode()).decode()


def decrypt_secret(value):
    if not value or not value.startswith(_PREFIX):
        return value
    try:
        return _fernet().decrypt(value[len(_PREFIX):].encode()).decode()
    except Exception:
        logger.error("Cannot decrypt a stored secret — was SECRET_KEY changed? Re-enter the credential.")
        return ""


class EncryptedTextField(models.TextField):
    """TextField whose value is Fernet-encrypted in the database."""

    def from_db_value(self, value, expression, connection):
        return decrypt_secret(value)

    def to_python(self, value):
        value = super().to_python(value)
        return decrypt_secret(value) if isinstance(value, str) else value

    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        return encrypt_secret(value) if isinstance(value, str) else value


def mask_secrets(data, fields):
    """Replace secret values in a serialized object (used for the changelog)."""
    if not isinstance(data, dict):
        return data
    for field in fields:
        if data.get(field):
            data[field] = SECRET_MASK
    return data
