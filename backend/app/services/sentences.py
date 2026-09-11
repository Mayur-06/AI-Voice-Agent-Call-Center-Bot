import re

# Sentence boundary: terminator + closing quote/bracket, followed by whitespace.
# Kept deliberately cheap - this runs on every LLM stream chunk.
_BOUNDARY = re.compile(r'(?<=[.!?…])["\')\]]*\s+')

# Abbreviations that must not terminate a sentence.
_ABBREV = re.compile(
    r'(?:^|\s)(?:mr|mrs|ms|dr|prof|sr|jr|st|vs|etc|e\.g|i\.e|approx|no|fig)\.$',
    re.IGNORECASE,
)


def _is_false_boundary(head: str) -> bool:
    if _ABBREV.search(head):
        return True
    # A single trailing initial ("J.") or a decimal ("3.") is not a boundary.
    if re.search(r'(?:^|\s)[A-Za-z]\.$', head):
        return True
    # Dotted acronyms: p.m., a.m., e.g., U.S.A.
    if re.search(r'(?:[A-Za-z]\.){2,}$', head):
        return True
    return False


def split_sentences_sync(text: str) -> list[str]:
    """Split text into sentences. Pure CPU, no network."""
    if not text or not text.strip():
        return []
    sentences: list[str] = []
    start = 0
    for match in _BOUNDARY.finditer(text):
        head = text[start:match.start()]
        if not head.strip() or _is_false_boundary(head):
            continue
        sentences.append(head.strip())
        start = match.end()
    tail = text[start:]
    if tail.strip():
        sentences.append(tail.strip())
    return sentences


def take_complete_sentences(buffer: str) -> tuple[list[str], str]:
    """Return (complete sentences, remaining partial buffer).

    Used by the streaming LLM loop: emit whatever is finished, keep the tail.
    """
    if not buffer:
        return [], ""
    last = None
    for match in _BOUNDARY.finditer(buffer):
        if not _is_false_boundary(buffer[:match.start()]):
            last = match
    if last is None:
        return [], buffer
    complete = split_sentences_sync(buffer[:last.end()])
    return complete, buffer[last.end():]


async def split_sentences(text: str) -> list[str]:
    return split_sentences_sync(text)
