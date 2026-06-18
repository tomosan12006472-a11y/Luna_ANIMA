from __future__ import annotations


# Deprecated: upload endpoints now use FastAPI UploadFile. This fallback parser is
# kept temporarily so the module can be deleted in a later cleanup PR.
def parse_multipart_file_upload(content_type: str, body: bytes) -> tuple[str, bytes]:
    marker = "boundary="
    if marker not in content_type:
        raise ValueError("multipart boundary is missing")
    boundary = content_type.split(marker, 1)[1].split(";", 1)[0].strip().strip('"')
    if not boundary:
        raise ValueError("multipart boundary is empty")
    delimiter = b"--" + boundary.encode("utf-8")
    for raw_part in body.split(delimiter):
        part = raw_part.strip(b"\r\n")
        if not part or part == b"--":
            continue
        headers, sep, content = part.partition(b"\r\n\r\n")
        if not sep:
            continue
        header_text = headers.decode("utf-8", errors="replace")
        disposition = next(
            (line for line in header_text.splitlines() if line.lower().startswith("content-disposition:")),
            header_text,
        )
        if 'name="file"' not in disposition and "name=file" not in disposition:
            continue
        filename = "reference.png"
        for piece in disposition.split(";"):
            piece = piece.strip()
            if piece.lower().startswith("filename="):
                filename = piece.split("=", 1)[1].strip().strip('"') or filename
                break
        return filename, content.rstrip(b"\r\n")
    raise ValueError("file field is missing")
