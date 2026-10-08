"""Authored born-digital PDF pages; deterministic inert size padding, no study data.

Padding is one unreferenced stream. It exercises source allocation/authentication
cost at an exact size, not a claim of representative image or parser complexity.
"""

from typing import BinaryIO


def write_bounded_pdf(stream: BinaryIO, *, pages: int, byte_length: int) -> None:
    if pages not in (3, 50, 500) or not 1 <= byte_length <= 128 * 1024 * 1024:
        raise ValueError("unsupported-synthetic-pdf-fixture")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids ["
        + b" ".join(f"{4 + number * 2} 0 R".encode() for number in range(pages))
        + f"] /Count {pages} >>".encode(),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    for number in range(1, pages + 1):
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {len(objects) + 2} 0 R >>".encode()
        )
        text = f"BT /F1 16 Tf 50 700 Td (Synthetic Page {number}) Tj "
        for line in range(20):
            text += f"0 -22 Td (Inert bounded source line {line + 1}. Original text is unverified.) Tj "
        text = (text + "ET").encode()
        objects.append(b"<< /Length " + str(len(text)).encode() + b" >>\nstream\n" + text + b"\nendstream")
    stream.write(b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for number, value in enumerate(objects, 1):
        offsets.append(stream.tell())
        stream.write(f"{number} 0 obj\n".encode() + value + b"\nendobj\n")
    # Derive the exact padding length without constructing a source-sized array.
    padding_number = len(objects) + 1
    padding_offset = stream.tell()
    suffix = b"\nendstream\nendobj\n"
    padding = byte_length - stream.tell()
    for _ in range(10):
        header = f"{padding_number} 0 obj\n<< /Length {padding} >>\nstream\n".encode()
        xref_offset = padding_offset + len(header) + padding + len(suffix)
        all_offsets = [*offsets, padding_offset]
        trailer = f"xref\n0 {len(all_offsets)}\n0000000000 65535 f \n".encode()
        trailer += b"".join(f"{offset:010d} 00000 n \n".encode() for offset in all_offsets[1:])
        trailer += f"trailer\n<< /Size {len(all_offsets)} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode()
        next_padding = byte_length - padding_offset - len(header) - len(suffix) - len(trailer)
        if next_padding == padding:
            break
        padding = next_padding
    if padding < 0:
        raise ValueError("synthetic-pdf-size-too-small")
    stream.write(header)
    chunk = b" " * 65536
    while padding:
        size = min(padding, len(chunk))
        stream.write(chunk[:size])
        padding -= size
    stream.write(suffix + trailer)
    if stream.tell() != byte_length:
        raise ValueError("synthetic-pdf-size-mismatch")
    stream.seek(0)
