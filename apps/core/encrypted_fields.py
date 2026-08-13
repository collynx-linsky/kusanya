"""Field-level encryption at rest for PII, per ARCHITECTURE_DECISIONS
ADR-032.

Two separate keys are derived from settings.FIELD_ENCRYPTION_KEY (HKDF-ish
split via SHA-256 + a fixed context string, not key reuse across two
different primitives):

- Fernet (AES-128-CBC + HMAC-SHA256, authenticated, non-deterministic —
  a fresh ciphertext every time, even for the same plaintext) for the
  actual stored value. Non-deterministic means it CANNOT be queried by
  `.filter(field=value)` — EncryptedTextField/EncryptedCharField disallow
  every lookup except `isnull` to fail loudly instead of silently
  returning wrong results.
- HMAC-SHA256 (deterministic, unkeyed-per-record) for `lookup_hash`
  companion columns — the same pattern already used for MFA backup codes
  (apps.accounts.models._backup_code_lookup_hash). Deterministic means it
  CAN be queried exactly, which is what
  EncryptedFieldSearchAdminMixin uses to give Django admin exact-match
  search back on a field it otherwise can't search — see that class's
  docstring for what's lost (substring/fuzzy matching) versus what's kept.
"""

import hashlib
import hmac

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.core.exceptions import FieldError
from django.db import models
from django.db.models import Q


def _derive_key(context: bytes) -> bytes:
    return hashlib.sha256(force_bytes(settings.FIELD_ENCRYPTION_KEY) + context).digest()


def force_bytes(value) -> bytes:
    return value.encode("utf-8") if isinstance(value, str) else bytes(value)


def _fernet() -> Fernet:
    import base64

    key = base64.urlsafe_b64encode(_derive_key(b"kusanya-field-encryption-fernet"))
    return Fernet(key)


def compute_lookup_hash(value: str) -> str:
    """Deterministic HMAC-SHA256 of a normalized (stripped) value — the
    exact-match search key for an encrypted field. Callers that care
    about case-insensitive matching (email) should normalize case
    themselves before calling this; this function only strips
    whitespace, since that's unambiguously always correct."""
    key = _derive_key(b"kusanya-field-encryption-lookup-hash")
    normalized = (value or "").strip()
    return hmac.new(key, normalized.encode("utf-8"), hashlib.sha256).hexdigest()


class EncryptedTextField(models.TextField):
    """Transparently Fernet-encrypts on save, decrypts on load. Stored as
    TEXT regardless of logical size, since ciphertext is longer than
    plaintext and padding it to a meaningful VARCHAR limit buys nothing.
    Not queryable by value — see module docstring."""

    description = "Symmetrically encrypted text"

    def get_internal_type(self):
        return "TextField"

    def from_db_value(self, value, expression, connection):
        if value is None or value == "":
            return value
        try:
            return _fernet().decrypt(value.encode("utf-8")).decode("utf-8")
        except InvalidToken:
            # Never raise on read — a corrupt/foreign-key value should be
            # visibly wrong, not take down the page rendering it.
            return "[unreadable: decryption failed]"

    def to_python(self, value):
        return value

    def get_prep_value(self, value):
        if value is None or value == "":
            return value
        if not isinstance(value, str):
            value = str(value)
        return _fernet().encrypt(value.encode("utf-8")).decode("utf-8")

    def get_lookup(self, lookup_name):
        if lookup_name == "isnull":
            return super().get_lookup(lookup_name)
        raise FieldError(
            f"{self.__class__.__name__} does not support querying by value directly "
            f"(encryption is non-deterministic — the same plaintext never encrypts to "
            f"the same ciphertext twice, so '.filter({self.name}={lookup_name}=...)' would "
            f"silently match nothing rather than what you meant). Use a companion "
            f"lookup_hash field (apps.core.encrypted_fields.compute_lookup_hash) for "
            f"exact-match queries instead."
        )

    def formfield(self, **kwargs):
        # Skip TextField.formfield()'s forced Textarea widget — this
        # behaves like a CharField for form/admin purposes, just stored
        # as TEXT in the database.
        defaults = {}
        defaults.update(kwargs)
        return super(models.TextField, self).formfield(**defaults)


class EncryptedCharField(EncryptedTextField):
    """Same as EncryptedTextField, but validates a max_length on the
    plaintext at save time (the DB column itself is still TEXT —
    ciphertext length isn't meaningfully related to plaintext length, so
    it can't be enforced at the DB level after encryption)."""

    def __init__(self, *args, max_length=None, **kwargs):
        # Let Field.__init__ set self.max_length itself (it accepts the
        # kwarg generically, not just for CharField) -- setting it
        # ourselves before calling super() got silently overwritten back
        # to None, since Field.__init__ always assigns it from kwargs.
        super().__init__(*args, max_length=max_length, **kwargs)

    def get_prep_value(self, value):
        if self.max_length and value and len(value) > self.max_length:
            raise ValueError(
                f"Value for {self.name!r} exceeds max_length={self.max_length} "
                f"(got {len(value)} characters)."
            )
        return super().get_prep_value(value)

    def formfield(self, **kwargs):
        defaults = {"max_length": self.max_length}
        defaults.update(kwargs)
        return super().formfield(**defaults)

    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()
        if self.max_length is not None:
            kwargs["max_length"] = self.max_length
        return name, path, args, kwargs


class EncryptedFieldSearchAdminMixin:
    """Restores Django admin search on encrypted fields as an
    exact-match-only lookup against their `<field>_lookup_hash` companion
    column, in addition to whatever `search_fields` (icontains) still
    applies to unencrypted fields.

    This is NOT equivalent to the substring search admin normally does —
    typing part of a name or the last 4 digits of a phone number will not
    match. Only the complete, exact original value (case-sensitive,
    except where the model's save() lowercases before hashing, e.g.
    email) matches. See ARCHITECTURE_DECISIONS ADR-032 for why this
    tradeoff was chosen deliberately over leaving these fields
    unencrypted or dropping search entirely.

    Usage: set `encrypted_exact_search_fields = ["full_name", "email"]`
    (the plaintext attribute names, each of which must have a
    `<name>_lookup_hash` column) on a ModelAdmin using this mixin.
    """

    encrypted_exact_search_fields: list[str] = []

    def get_search_results(self, request, queryset, search_term):
        queryset, use_distinct = super().get_search_results(request, queryset, search_term)
        if search_term and self.encrypted_exact_search_fields:
            target_hash = compute_lookup_hash(search_term)
            hash_query = Q()
            for field_name in self.encrypted_exact_search_fields:
                hash_query |= Q(**{f"{field_name}_lookup_hash": target_hash})
            exact_matches = self.model.objects.filter(hash_query).values_list("pk", flat=True)
            if exact_matches:
                queryset = (queryset | self.model.objects.filter(pk__in=list(exact_matches))).distinct()
                use_distinct = True
        return queryset, use_distinct
