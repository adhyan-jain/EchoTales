"""A minimal `multipart/form-data` parser for exactly one shape: a single
file part, HTTP request body.

`webview_server.py` is stdlib-only (`http.server`) by deliberate choice --
see that module's own docstring -- and Python 3.12 ships no first-party
multipart parser (`cgi` is deprecated and gone entirely in 3.13). Pulling in
a dependency (e.g. `python-multipart`) for the two upload routes that need
this (source EPUB upload, reference-image upload) would be solving a bigger
problem than the one that exists here: both routes accept exactly one file
field, nothing else. This module is scoped to that, not a general-purpose
multipart implementation.
"""

from __future__ import annotations


class MultipartError(ValueError):
    pass


def parse_single_file(content_type: str, body: bytes) -> tuple[str, bytes]:
    """Return `(filename, file_bytes)` for the first (and expected only)
    file part in a `multipart/form-data` body.

    Raises `MultipartError` on anything that doesn't match that shape --
    callers turn this into a 400, never a 500, since a malformed upload is
    a client error, not a server bug.
    """
    marker = "boundary="
    idx = content_type.find(marker)
    if idx == -1:
        raise MultipartError("missing multipart boundary")
    boundary = content_type[idx + len(marker) :].strip().strip('"')
    delimiter = b"--" + boundary.encode("utf-8")

    parts = body.split(delimiter)
    for part in parts:
        part = part.strip(b"\r\n")
        if not part or part == b"--":
            continue
        header_end = part.find(b"\r\n\r\n")
        if header_end == -1:
            continue
        header_blob = part[:header_end].decode("utf-8", errors="replace")
        file_bytes = part[header_end + 4 :]
        # Trailing CRLF before the next boundary delimiter is part of the
        # multipart framing, not the file's own content.
        if file_bytes.endswith(b"\r\n"):
            file_bytes = file_bytes[:-2]
        if "filename=" not in header_blob:
            continue  # a non-file field -- this parser only cares about the file part
        fn_idx = header_blob.find("filename=")
        rest = header_blob[fn_idx + len("filename=") :]
        quote = rest[0]
        filename = rest[1 : rest.index(quote, 1)] if quote in ('"', "'") else rest.split(";")[0]
        return filename, file_bytes

    raise MultipartError("no file part found in multipart body")
