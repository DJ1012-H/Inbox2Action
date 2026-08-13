from __future__ import annotations

import hashlib
import re
from html.parser import HTMLParser
from typing import ClassVar
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from inbox2action.stage3.contracts import EmailEnvelope, NormalizedEmail

MAX_NORMALIZED_BODY_LENGTH = 12_000
_URL_RE = re.compile(r"https?://[^\s<>]+", re.IGNORECASE)
_EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_PHONE_RE = re.compile(r"(?<!\d)(?:\+?\d[\d ()-]{7,}\d)(?!\d)")
_TRACKING_NAMES = {
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "msclkid",
    "ref_src",
}
_INJECTION_MARKERS = (
    "ignore previous",
    "ignore all previous",
    "system prompt",
    "developer message",
    "api key",
    "password",
    "bypass approval",
    "skip approval",
    "忽略之前",
    "忽略所有之前",
    "系统提示",
    "开发者消息",
    "绕过审批",
    "跳过审批",
)


class NormalizationError(ValueError):
    """The email could not be reduced to a safe bounded representation."""


class _VisibleTextParser(HTMLParser):
    _ignored_tags: ClassVar[frozenset[str]] = frozenset(
        {"script", "style", "noscript", "template", "title"}
    )
    _void_tags: ClassVar[frozenset[str]] = frozenset(
        {
            "area",
            "base",
            "br",
            "col",
            "embed",
            "hr",
            "img",
            "input",
            "link",
            "meta",
            "param",
            "source",
            "track",
            "wbr",
        }
    )
    _block_tags: ClassVar[frozenset[str]] = frozenset(
        {"article", "div", "li", "p", "section", "tr", "br"}
    )

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        normalized = tag.casefold()
        if self._skip_depth:
            if normalized not in self._void_tags:
                self._skip_depth += 1
            return
        attr_map = {key.casefold(): (value or "").casefold() for key, value in attrs}
        style = attr_map.get("style", "")
        hidden = "display:none" in style.replace(" ", "") or "visibility:hidden" in style.replace(" ", "")
        if normalized in self._ignored_tags or hidden:
            if normalized not in self._void_tags:
                self._skip_depth = 1
            return
        if normalized in self._block_tags:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if self._skip_depth:
            self._skip_depth -= 1
            return
        if tag.casefold() in self._block_tags:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip_depth:
            self.parts.append(data)


def normalize_email(envelope: EmailEnvelope) -> NormalizedEmail:
    source = envelope.html if envelope.html is not None else envelope.body
    source_digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
    visible = _html_to_text(source) if envelope.html is not None else source
    cleaned = _remove_quotes_and_signature(visible)
    cleaned, tracking_count = _remove_tracking_parameters(cleaned)
    cleaned, redaction_count = _redact_pii(cleaned)
    cleaned = _normalize_whitespace(cleaned)
    if not cleaned:
        raise NormalizationError("email has no visible content after normalization")
    if len(cleaned) > MAX_NORMALIZED_BODY_LENGTH:
        cleaned = cleaned[:MAX_NORMALIZED_BODY_LENGTH].rstrip() + "\n[TRUNCATED]"

    subject, subject_tracking = _remove_tracking_parameters(envelope.subject)
    subject, subject_redactions = _redact_pii(subject)
    subject = _normalize_whitespace(subject) or "[NO SUBJECT]"
    subject = subject[:200]
    return NormalizedEmail(
        account_id=envelope.account_id,
        message_id=envelope.message_id,
        provider_thread_id=envelope.provider_thread_id,
        from_address=envelope.from_address,
        reply_to=envelope.reply_to,
        received_at=envelope.received_at,
        subject=subject,
        sanitized_body=cleaned,
        source_body_sha256=source_digest,
        redaction_count=redaction_count + subject_redactions,
        removed_tracking_parameters=tracking_count + subject_tracking,
        contains_injection_signals=_contains_injection_signals(
            f"{subject}\n{cleaned}"
        ),
    )


def _html_to_text(value: str) -> str:
    parser = _VisibleTextParser()
    try:
        parser.feed(value)
        parser.close()
    except Exception as exc:
        raise NormalizationError("invalid HTML content") from exc
    return "".join(parser.parts)


def _remove_quotes_and_signature(value: str) -> str:
    kept: list[str] = []
    for line in value.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        stripped = line.strip()
        if stripped.startswith(">"):
            continue
        if re.match(r"^On .+ wrote:\s*$", stripped, re.IGNORECASE):
            break
        if re.match(r"^--\s*$", stripped):
            break
        if re.match(r"^Sent from my (iPhone|iPad|Android)\s*$", stripped, re.IGNORECASE):
            continue
        kept.append(line)
    return "\n".join(kept)


def _remove_tracking_parameters(value: str) -> tuple[str, int]:
    removed = 0

    def replace(match: re.Match[str]) -> str:
        nonlocal removed
        raw = match.group(0)
        trailing = ""
        while raw and raw[-1] in ".,;:!?)]":
            trailing = raw[-1] + trailing
            raw = raw[:-1]
        try:
            parsed = urlsplit(raw)
            query = []
            for key, item in parse_qsl(parsed.query, keep_blank_values=True):
                if key.casefold().startswith("utm_") or key.casefold() in _TRACKING_NAMES:
                    removed += 1
                else:
                    query.append((key, item))
            cleaned = urlunsplit(
                (
                    parsed.scheme,
                    parsed.netloc,
                    parsed.path,
                    urlencode(query),
                    parsed.fragment,
                )
            )
            return cleaned + trailing
        except ValueError:
            return match.group(0)

    return _URL_RE.sub(replace, value), removed


def _redact_pii(value: str) -> tuple[str, int]:
    count = 0

    def replace_email(_: re.Match[str]) -> str:
        nonlocal count
        count += 1
        return "<REDACTED_EMAIL>"

    def replace_phone(_: re.Match[str]) -> str:
        nonlocal count
        count += 1
        return "<REDACTED_PHONE>"

    value = _EMAIL_RE.sub(replace_email, value)
    return _PHONE_RE.sub(replace_phone, value), count


def _normalize_whitespace(value: str) -> str:
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in value.splitlines()]
    compact: list[str] = []
    previous_blank = False
    for line in lines:
        if not line:
            if not previous_blank:
                compact.append("")
            previous_blank = True
            continue
        compact.append(line)
        previous_blank = False
    return "\n".join(compact).strip()


def _contains_injection_signals(value: str) -> bool:
    folded = value.casefold()
    return any(marker.casefold() in folded for marker in _INJECTION_MARKERS)
