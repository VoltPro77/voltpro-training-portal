"""Extract a regulation PDF (AS/NZS 3000, AS/NZS 3008, etc.) into RegulationChunk rows —
one per page, tagged with a source label — powering the "Ask the Regs" feature. Requires
poppler's `pdftotext` (`brew install poppler`).

The source PDF is read from disk but never copied into the project or committed to git —
only the extracted text is stored, server-side, for grounding AI answers with citations.
It is never exposed to staff directly, only synthesized answers with page references.

Re-running for a source-name that's already indexed replaces just that document's chunks,
leaving other indexed documents untouched.

Usage:
    python scripts/extract_regulations.py --pdf "/path/to/AS3000.pdf" --source-name "AS/NZS 3000:2018"
    python scripts/extract_regulations.py --pdf "/path/to/AS3008.pdf" --source-name "AS/NZS 3008.1.1:2017 Section 3"
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import create_app  # noqa: E402
from app.models import RegulationChunk, db  # noqa: E402

# Known noise patterns to strip wherever they appear, regardless of source document.
NOISE_PATTERNS = [
    re.compile(r"welcome to the jungle", re.IGNORECASE),
]


def extract_pages(pdf_path):
    result = subprocess.run(
        ["pdftotext", "-layout", str(pdf_path), "-"],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.split("\x0c")  # form feed = page break


def clean_page(raw_text, doc_header_hint):
    """Strip known noise + the document's own repeated header/footer line.

    Returns (printed_page_from_header_or_None, cleaned_text). If the document doesn't
    print a page number in a recognizable "<header> ... <number>" line on every page,
    printed_page comes back None and the caller falls back to the physical page index —
    good enough for citation purposes; it just needs to be internally consistent.
    """
    lines = raw_text.split("\n")
    kept = []
    printed_page = None
    for line in lines:
        stripped = line.strip()
        if not stripped:
            kept.append(line)
            continue
        if any(p.search(stripped) for p in NOISE_PATTERNS):
            continue
        if doc_header_hint and doc_header_hint.lower() in stripped.lower() and len(stripped) < 80:
            m = re.search(r"\b(\d+)\b", stripped.replace(doc_header_hint, ""))
            if m:
                printed_page = int(m.group(1))
            continue
        if stripped == "COPYRIGHT":
            continue
        kept.append(line)
    text = "\n".join(kept).strip()
    return printed_page, text


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf", required=True, help="Path to the regulation PDF")
    parser.add_argument(
        "--source-name",
        required=True,
        help='Label for citations, e.g. "AS/NZS 3000:2018" or "AS/NZS 3008.1.1:2017 Section 3"',
    )
    parser.add_argument(
        "--header-hint",
        default=None,
        help="Text that appears in this doc's repeated page header/footer, used to parse the "
        "real printed page number (e.g. 'AS/NZS 3000:2018'). Omit to just use the physical "
        "page index — fine for documents that don't print page numbers on every page.",
    )
    args = parser.parse_args()

    pdf_path = Path(args.pdf).expanduser().resolve()
    if not pdf_path.exists():
        raise SystemExit(f"File not found: {pdf_path}")

    print(f"Extracting text from {pdf_path.name} (source: {args.source_name}) ...")
    raw_pages = extract_pages(pdf_path)
    print(f"{len(raw_pages)} physical pages found.")

    # Collect first, keyed by printed_page, so genuine duplicates (e.g. a wide table that
    # shares its printed page number with the page before it, a real quirk in some source
    # documents) get merged into one chunk instead of one silently overwriting the other.
    pages_by_number = {}
    for physical_page, raw in enumerate(raw_pages, start=1):
        header_page, text = clean_page(raw, args.header_hint)
        if len(text) < 40:
            continue  # skip cover pages, blank pages

        if args.header_hint:
            # Mixing header-parsed numbers with physical-index fallback within the same
            # document risks collisions (a fallback page's physical index landing on the
            # same number as another page's true printed number), which would silently
            # make one of them unretrievable. So when a header hint is given, a page that
            # doesn't match it is skipped rather than fallen back — same as not indexing
            # it at all, which is safe since such pages are usually low-value (dividers,
            # blanks that slipped past the length check, unusual layouts).
            if header_page is None:
                continue
            printed_page = header_page
        else:
            printed_page = physical_page

        if printed_page in pages_by_number:
            pages_by_number[printed_page] += "\n\n" + text
        else:
            pages_by_number[printed_page] = text

    app = create_app()
    with app.app_context():
        RegulationChunk.query.filter_by(source=args.source_name).delete()

        for printed_page, text in pages_by_number.items():
            db.session.add(
                RegulationChunk(source=args.source_name, printed_page=printed_page, text=text)
            )

        db.session.commit()
        print(f"Stored {len(pages_by_number)} page chunks for '{args.source_name}'.")


if __name__ == "__main__":
    main()
