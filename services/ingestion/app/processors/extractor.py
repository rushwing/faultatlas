import io

from pypdf import PdfReader


def extract_text(content: bytes, content_type: str) -> tuple[str, dict]:
    if content_type == "application/pdf":
        reader = PdfReader(io.BytesIO(content))
        if reader.is_encrypted:
            raise ValueError("encrypted_pdf")

        unreadable_pages: list[int] = []
        pages: list[str] = []
        for index, page in enumerate(reader.pages):
            text = page.extract_text() or ""
            if not text.strip():
                unreadable_pages.append(index)
            pages.append(text)

        return "\n".join(pages), {"unreadable_pages": unreadable_pages}
    # Plain text / log files
    return content.decode("utf-8", errors="replace"), {"unreadable_pages": []}
