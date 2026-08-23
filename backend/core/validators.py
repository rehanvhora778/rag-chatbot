"""Upload validation.

The checks that were here before — extension and size — establish almost
nothing. An extension is a claim made by whoever named the file, and both are
trivially satisfied by content that is not what it says it is.

What is actually being defended against, and by what:

* **A file that is not what its name claims.** ``invoice.pdf`` containing a ZIP,
  an HTML page, or an executable. Extension alone cannot tell; the leading bytes
  can. Handled by sniffing the content and requiring it to agree with the name.

* **Path traversal.** A filename like ``../../config/settings.py``. Already
  neutralised — the stored name is generated, never derived from the upload —
  and now asserted rather than assumed, because that is the kind of property
  that survives until someone "improves" the naming.

* **Archive and macro payloads.** DOCX is a ZIP, so a DOCX-shaped file may be
  any ZIP at all, including one whose expanded contents are far larger than the
  upload limit suggests.

* **Empty and truncated files**, which fail deep inside extraction with an error
  that says nothing useful about the actual cause.

Deliberately *not* attempted: virus scanning and full PDF structure validation.
Both need a dedicated service to do properly, and a token effort at either would
give a false sense of coverage. What is here is what can be done correctly with
the dependencies this project already has.
"""
import contextlib
import logging
import zipfile
from pathlib import Path
from typing import Optional

from django.conf import settings

logger = logging.getLogger(__name__)

# Leading bytes for the formats accepted here. Checked directly rather than
# relying only on `filetype`, so the rule that matters is visible in the source
# instead of buried in a library's tables.
MAGIC_SIGNATURES: dict[str, tuple[bytes, ...]] = {
    'pdf': (b'%PDF-',),
    # DOCX is a ZIP container. PK\x03\x04 is a normal archive; the other two are
    # empty and spanned archives, neither of which is a valid document.
    'docx': (b'PK\x03\x04',),
}

# How much of the file to read for sniffing. The signatures are all within the
# first few bytes; 4 KB is generous and still cheap.
SNIFF_BYTES = 4096

# A DOCX that expands to more than this is either corrupt or a zip bomb.
MAX_ARCHIVE_EXPANSION = 200
MIN_FILE_BYTES = 16


class ValidationFailed(Exception):
    """The upload was rejected. The message is shown to the user."""


def validate_upload(uploaded_file, *, extension: Optional[str] = None) -> None:
    """Run every check against one uploaded file. Raises ValidationFailed.

    Raising rather than returning a boolean: each failure has a specific reason
    the user needs in order to act, and a boolean forces the caller to
    reconstruct it.
    """
    name = getattr(uploaded_file, 'name', '') or ''
    extension = (extension or Path(name).suffix.lower().lstrip('.')).lower()

    _check_filename(name)
    _check_extension(extension)
    _check_size(uploaded_file, name)

    head = _read_head(uploaded_file)
    _check_not_empty(head, name)
    _check_magic(head, extension, name)

    if extension == 'docx':
        _check_archive(uploaded_file, name)


# ══════════════════════════════════════════════════════════════════
# Individual checks
# ══════════════════════════════════════════════════════════════════

def _check_filename(name: str) -> None:
    """Reject a filename that is trying to be a path.

    The stored name is generated, so this cannot currently reach the
    filesystem. It is checked anyway: defence that depends on a detail
    elsewhere in the codebase staying true is defence with an expiry date, and
    a filename containing a path separator is never legitimate.
    """
    if not name:
        raise ValidationFailed('The file has no name.')

    if len(name) > 255:
        raise ValidationFailed('That filename is too long.')

    if '\x00' in name:
        raise ValidationFailed('That filename contains a null byte.')

    if '/' in name or '\\' in name or '..' in name:
        logger.warning('Rejected an upload whose filename looks like a path: %r', name)
        raise ValidationFailed(
            'That filename contains path characters. Rename the file and try again.'
        )


def _check_extension(extension: str) -> None:
    allowed = settings.ALLOWED_DOCUMENT_EXTENSIONS
    if extension not in allowed:
        raise ValidationFailed(
            f'Unsupported file type ".{extension}". Allowed: {", ".join(allowed)}.'
        )


def _check_size(uploaded_file, name: str) -> None:
    limit_mb = settings.MAX_DOCUMENT_SIZE_MB
    size = getattr(uploaded_file, 'size', 0) or 0

    if size > limit_mb * 1024 * 1024:
        raise ValidationFailed(f'{name}: exceeds the {limit_mb} MB limit.')

    if size < MIN_FILE_BYTES:
        raise ValidationFailed(f'{name}: the file is empty or truncated.')


def _read_head(uploaded_file) -> bytes:
    """The first few KB, leaving the file positioned where it was found."""
    uploaded_file.seek(0)
    head = uploaded_file.read(SNIFF_BYTES)
    uploaded_file.seek(0)
    return head or b''


def _check_not_empty(head: bytes, name: str) -> None:
    if not head.strip():
        raise ValidationFailed(f'{name}: the file appears to be empty.')


def _check_magic(head: bytes, extension: str, name: str) -> None:
    """The content must be what the extension claims.

    Plain text has no signature — any byte sequence is potentially valid text —
    so .txt is checked for decodability instead, which is the real requirement
    for a file that is about to be read as text.
    """
    if extension == 'txt':
        _check_decodable(head, name)
        return

    signatures = MAGIC_SIGNATURES.get(extension)
    if not signatures:
        return

    if not any(head.startswith(signature) for signature in signatures):
        actual = _describe(head)
        logger.warning(
            'Rejected %r: extension .%s but the content looks like %s',
            name, extension, actual,
        )
        raise ValidationFailed(
            f'{name}: this is named ".{extension}" but its contents are '
            f'{actual}. Rename it to match, or upload the correct file.'
        )


def _check_decodable(head: bytes, name: str) -> None:
    """A .txt file has to survive being read as text."""
    if b'\x00' in head:
        raise ValidationFailed(
            f'{name}: this is named ".txt" but contains binary data.'
        )

    for encoding in ('utf-8', 'utf-16', 'latin-1'):
        try:
            head.decode(encoding)
            return
        except (UnicodeDecodeError, LookupError):
            continue

    raise ValidationFailed(f'{name}: the text could not be decoded in any known encoding.')


def _check_archive(uploaded_file, name: str) -> None:
    """A DOCX is a ZIP: check it opens, and that it will not explode.

    Guards two separate things. A file that is ZIP-shaped but not a Word
    document fails later inside python-docx with an error about missing parts,
    which tells the user nothing. And an archive whose declared contents are
    hundreds of times its compressed size is a zip bomb — the size limit is
    checked against the *upload*, and expansion happens after that check.
    """
    uploaded_file.seek(0)
    try:
        with zipfile.ZipFile(uploaded_file) as archive:
            names = archive.namelist()

            # Every DOCX has this. A ZIP without it is not a Word document,
            # whatever it has been renamed to.
            if 'word/document.xml' not in names:
                raise ValidationFailed(
                    f'{name}: this is a ZIP archive but not a Word document.'
                )

            compressed = sum(i.compress_size for i in archive.infolist()) or 1
            expanded = sum(i.file_size for i in archive.infolist())

            if expanded / compressed > MAX_ARCHIVE_EXPANSION:
                logger.warning(
                    'Rejected %r: expands %.0fx (%d -> %d bytes)',
                    name, expanded / compressed, compressed, expanded,
                )
                raise ValidationFailed(
                    f'{name}: this archive expands to far more than its size '
                    'suggests and was rejected.'
                )
    except zipfile.BadZipFile as exc:
        raise ValidationFailed(
            f'{name}: the file is not a readable .docx — it may be corrupt.'
        ) from exc
    finally:
        uploaded_file.seek(0)


def _describe(head: bytes) -> str:
    """Name what a file actually looks like, for the rejection message.

    A user who has uploaded the wrong thing is helped much more by "that is a
    ZIP archive" than by "invalid file".
    """
    known = [
        (b'%PDF-', 'a PDF'),
        (b'PK\x03\x04', 'a ZIP archive'),
        (b'\x89PNG', 'a PNG image'),
        (b'\xff\xd8\xff', 'a JPEG image'),
        (b'GIF8', 'a GIF image'),
        (b'MZ', 'a Windows executable'),
        (b'\x7fELF', 'a Linux executable'),
        (b'\x1f\x8b', 'a gzip archive'),
        (b'Rar!', 'a RAR archive'),
        (b'{\\rtf', 'an RTF document'),
        (b'<?xml', 'an XML file'),
    ]
    for signature, description in known:
        if head.startswith(signature):
            return description

    lowered = head[:512].lower()
    if b'<html' in lowered or b'<!doctype html' in lowered:
        return 'an HTML page'

    # Fall back to the library, which knows far more signatures than this list.
    # Suppressed rather than logged: this runs only to improve the wording of a
    # rejection that is happening either way, so a failure here changes nothing
    # the user sees beyond a less specific sentence.
    with contextlib.suppress(Exception):
        import filetype

        guessed = filetype.guess(head)
        if guessed:
            return f'a {guessed.extension.upper()} file'

    return 'not a recognised document format'
