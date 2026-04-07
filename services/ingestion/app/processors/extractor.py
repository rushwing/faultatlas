import io

from pypdf import PdfReader


def extract_text(content: bytes, content_type: str) -> str:
    if content_type == "application/pdf":
        reader = PdfReader(io.BytesIO(content))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    # Plain text / log files
    return content.decode("utf-8", errors="replace")
