"""Repository-authored PDF content; labels are fixed before parser tuning.

No article, participant, experiment or result is represented by this corpus.
The deliberately repetitive layout exercises two columns and a ruled table.
"""


def scholarly_pdf(*, pages: int = 1, rotation: int = 0) -> bytes:
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>", b"", b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    kids = []
    for index in range(pages):
        number = len(objects) + 1
        kids.append(number)
        content = f"BT /F1 18 Tf 54 750 Td (Synthetic document page {index + 1}) Tj ET\n".encode()
        for line in range(12):
            y = 710 - line * 16
            content += (
                f"BT /F1 10 Tf 54 {y} Td (Left {index + 1}.{line + 1}: declared synthetic text.) Tj ET\n".encode()
            )
            content += f"BT /F1 10 Tf 326 {y} Td (Right {index + 1}.{line + 1}: no scholarly result.) Tj ET\n".encode()
        content += b"54 470 m 558 470 l S 54 430 m 558 430 l S 54 390 m 558 390 l S\n"
        content += b"54 470 m 54 390 l S 300 470 m 300 390 l S 558 470 m 558 390 l S\n"
        for x, y, label in (
            (70, 448, "Synthetic label"),
            (320, 448, "Declared value"),
            (70, 408, "row alpha"),
            (320, 408, "7"),
        ):
            content += f"BT /F1 12 Tf {x} {y} Td ({label}) Tj ET\n".encode()
        page = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Rotate {rotation} "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {number + 1} 0 R >>"
        ).encode()
        objects.extend((page, b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"endstream"))
    objects[1] = (
        f"<< /Type /Pages /Count {pages} /Kids [".encode() + b" ".join(f"{k} 0 R".encode() for k in kids) + b"] >>"
    )
    return pdf_objects(objects)


def pdf_objects(objects: list[bytes]) -> bytes:
    """Write deterministic synthetic objects with a correct xref table."""
    output = bytearray(b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for number, obj in enumerate(objects, 1):
        offsets.append(len(output))
        output.extend(f"{number} 0 obj\n".encode() + obj + b"\nendobj\n")
    position = len(output)
    output.extend(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode())
    output.extend(b"".join(f"{offset:010} 00000 n \n".encode() for offset in offsets[1:]))
    output.extend(f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{position}\n%%EOF\n".encode())
    return bytes(output)


GOLD = {
    "pageWidthPoints": 612,
    "pageHeightPoints": 792,
    "columns": 2,
    "lineLabels": ("Left", "Right"),
    "tableRows": 2,
    "tableColumns": 2,
    "tableCellLabels": ("Synthetic label", "Declared value", "row alpha", "7"),
}
