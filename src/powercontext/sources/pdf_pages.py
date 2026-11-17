# Copyright (c) 2026 OceanBase.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""PDF page evidence source for source-03-pdf-retrieval.

Parses a complete original PDF into per-physical-page captured Sources, projects each
page through the standard text-evidence projection, and answers natural-language
finance questions by searching an already-populated scoped Memory via the public
Memory API, returning exact per-page citations.
"""

from __future__ import annotations

import hashlib
import io
import math
import re
from collections import Counter
from urllib.parse import quote

from pydantic import BaseModel

from powercontext.artifacts.models import MemoryCitation
from powercontext.builtin.runtime.models import SearchMemoryRequest
from powercontext.limits import MAX_SOURCE_ID_LENGTH
from powercontext.sources.adapters import SourceAdapter
from powercontext.sources.definitions import AdapterSourceDefinition, SourceDefinition
from powercontext.sources.models import Source, SourceMaterialization
from powercontext.sources.projections import TEXT_EVIDENCE_PROJECTION_KEY, TextEvidence


class PDFDocumentInput(BaseModel):
    """A complete original PDF to be parsed in full."""

    document_id: str
    content: bytes


class PDFPageInput(BaseModel):
    """One physical page of a parsed PDF."""

    document_id: str
    document_sha256: str
    page_number: int
    text: str


def _pdf_page_source_id(document_id: str, document_sha256: str, page_number: int) -> str:
    """Stable, collision-free identity from (document_id, document_sha256, page_number)."""
    source_id = f"pdf:{quote(document_id, safe='')}:{document_sha256}:{page_number}"
    if len(source_id) > MAX_SOURCE_ID_LENGTH:
        raise ValueError("PDF page source_id exceeds the maximum allowed length")
    return source_id


class PDFPageSource(Source):
    """Captured Source for a single PDF page."""

    document_id: str
    document_sha256: str
    page_number: int
    text: str


def parse_pdf_document(value: PDFDocumentInput) -> tuple[PDFPageInput, ...]:
    """Parse every physical page of the PDF in order, returning one input per page.

    The identity of each page is anchored to the whole-file SHA-256, so a revised PDF
    produces new identities while old references keep pointing at the original revision.
    Empty/invalid/corrupt input fails atomically with ``ValueError`` and never yields a
    partial result. Encrypted PDFs carrying an empty-user-password permission marker are
    readable without a supplied password.
    """
    document_id = value.document_id
    if not document_id or not document_id.strip():
        raise ValueError("document_id must not be empty or whitespace")
    content = value.content
    if not content:
        raise ValueError("PDF content must not be empty")
    document_sha256 = hashlib.sha256(content).hexdigest()
    try:
        reader = _open_reader(content)
        pages: list[PDFPageInput] = []
        for index, page in enumerate(reader.pages, start=1):
            pages.append(
                PDFPageInput(
                    document_id=document_id,
                    document_sha256=document_sha256,
                    page_number=index,
                    text=page.extract_text() or "",
                )
            )
        if not pages:
            raise ValueError("PDF parsed with zero pages")
        return tuple(pages)
    except ValueError:
        raise
    except Exception as error:  # pypdf raises many exception types for bad input
        raise ValueError(f"failed to parse PDF: {error}") from error


def _open_reader(content: bytes):
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(content))
    if reader.is_encrypted:
        try:
            if reader.decrypt("") == 0:
                raise ValueError("PDF requires a non-empty password")
        except ValueError:
            raise
        except Exception as error:
            raise ValueError(f"unable to decrypt PDF: {error}") from error
    return reader


class _PDFPageAdapter:
    """Resolve/Read the pdf-page Source around ``PDFPageInput``."""

    name = "pdf-page"
    input_class = PDFPageInput
    source_class = PDFPageSource

    async def resolve(self, value: PDFPageInput) -> PDFPageSource:
        source_id = _pdf_page_source_id(value.document_id, value.document_sha256, value.page_number)
        return PDFPageSource(
            name=source_id,
            definition_version="1",
            materialization=SourceMaterialization.CAPTURED,
            document_id=value.document_id,
            document_sha256=value.document_sha256,
            page_number=value.page_number,
            text=value.text,
        )

    async def read(self, source: PDFPageSource) -> PDFPageInput:
        return PDFPageInput(
            document_id=source.document_id,
            document_sha256=source.document_sha256,
            page_number=source.page_number,
            text=source.text,
        )


class _PDFPageTextEvidenceProjection:
    """Standard text-evidence projection for pdf-page Sources."""

    name = TEXT_EVIDENCE_PROJECTION_KEY.name
    version = TEXT_EVIDENCE_PROJECTION_KEY.version
    source_class = PDFPageSource
    output_class = TextEvidence

    def project(self, source: PDFPageSource) -> TextEvidence:
        return TextEvidence(
            source_type="pdf-page",
            source_id=source.name,
            content=f"{source.document_id}\n{source.text}",
            metadata={
                "document_id": source.document_id,
                "document_sha256": source.document_sha256,
                "page_number": source.page_number,
            },
        )


PDF_PAGE_SOURCE_DEFINITION: SourceDefinition = AdapterSourceDefinition(
    _PDFPageAdapter(),
    version="1",
    projections=(_PDFPageTextEvidenceProjection(),),
)


_TOKEN_RE = re.compile(r"[A-Za-z]+|\d+")

_STOPWORDS = frozenset(
    """
    a an the is are was were be been being of in on at to for from by with as and or but if then than
    that this these those what which who whom whose when where why how has have had does do did any all
    it its their there into during over under about per vs versus so such not no can could would should
    will reported report reports answer question respond define assume assuming perspective details shown
    use using give relying response only within fy
    """.split()
)


def _stem(token: str) -> str:
    """Fold trivial English plurals so ``margin`` also matches ``margins``."""
    if len(token) > 4 and token.endswith("ies"):
        return f"{token[:-3]}y"
    if len(token) > 4 and token.endswith("es") and not token.endswith("ses"):
        return token[:-2]
    if len(token) > 3 and token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


def _page_tokens(text: str) -> list[str]:
    return [_stem(token.lower()) for token in _TOKEN_RE.findall(text)]


def _content_terms(text: str) -> list[str]:
    return [token for token in _page_tokens(text) if token not in _STOPWORDS]


def _page_identity(source_id: str) -> tuple[str, int]:
    """Recover ``(document_id, page_number)`` from a pdf-page Source name."""
    prefix, _, page = source_id.rpartition(":")
    document, _, _ = prefix.rpartition(":")
    try:
        number = int(page)
    except ValueError:
        return source_id, 0
    return document, number


def _page_heading(text: str) -> str:
    """Approximate the page heading: the first lines after the document id and running footer."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return ""
    body = lines[1:] if len(lines) > 1 else []
    if body and body[0].lower() == "table of contents":
        body = body[1:]
    return "\n".join(body[:3])


class _PageRanker:
    """Rank every page of the corpus against one question with two complementary signals."""

    def __init__(self, records: list) -> None:
        self.records = records
        self.counters = [Counter(_page_tokens(record.entry.text)) for record in records]
        self.headings = [Counter(_page_tokens(_page_heading(record.entry.text))) for record in records]
        self.lengths = [sum(counter.values()) for counter in self.counters]
        self.average = (sum(self.lengths) / len(self.lengths)) if self.lengths else 0.0
        document_frequency: Counter = Counter()
        heading_frequency: Counter = Counter()
        for counter, heading in zip(self.counters, self.headings):
            document_frequency.update(counter.keys())
            heading_frequency.update(heading.keys())
        self.document_frequency = document_frequency
        self.heading_frequency = heading_frequency
        self.total = len(records)
        # Share of numeric tokens: financial statements are dense in figures, narrative pages are not.
        self.numeric = [
            sum(value for term, value in counter.items() if term.isdigit()) / (sum(counter.values()) or 1)
            for counter in self.counters
        ]

    def _idf(self, term: str) -> float:
        frequency = self.document_frequency[term]
        return math.log(1 + (self.total - frequency + 0.5) / (frequency + 0.5))

    def _heading_idf(self, term: str) -> float:
        frequency = self.heading_frequency[term]
        return math.log(1 + (self.total - frequency + 0.5) / (frequency + 0.5))

    def bm25(self, terms: tuple[str, ...], index: int) -> float:
        counter = self.counters[index]
        length = self.lengths[index] or 1
        average = self.average or 1.0
        heading = self.headings[index]
        score = 0.0
        for term in terms:
            term_frequency = counter.get(term, 0)
            if term_frequency:
                score += self._idf(term) * (term_frequency * 2.2) / (
                    term_frequency + 1.2 * (0.25 + 0.75 * length / average)
                )
            if heading.get(term):
                # A heading hit marks the page the document itself devotes to the term.
                score += 6.0 * self._heading_idf(term)
        return score

    def coverage(self, terms: tuple[str, ...], index: int) -> float:
        total = sum(self._idf(term) for term in terms)
        if total <= 0.0:
            return 0.0
        counter = self.counters[index]
        heading = self.headings[index]
        return sum(self._idf(term) for term in terms if counter.get(term) or heading.get(term)) / total


def _reciprocal_rank_fusion(rankings: list[list[int]], depth: int) -> list[int]:
    fused: dict[int, float] = {}
    for ranking in rankings:
        for position, index in enumerate(ranking, start=1):
            fused[index] = fused.get(index, 0.0) + 1.0 / (depth + position)
    return sorted(fused, key=lambda index: (-fused[index], index))


async def _memory_records(memory) -> list:
    """Read every active entry of the scoped Memory so ranking sees the whole document set."""
    page = await memory.list()
    return list(page.entries)


_HEAD_PAGES = 12
_TAIL_NUMERIC_WEIGHT = 1.0


async def search_pdf_pages(memory, question: str, limit: int = 10) -> tuple[MemoryCitation, ...]:
    """Search an already-populated scoped Memory and return exact per-page citations.

    The Memory API supplies one candidate ranking; a whole-corpus lexical pass over the same
    Memory entries adds two more (BM25 over the page body with a heading field boost, and
    inverse-document-frequency term coverage). The three rankings are fused, so a question that
    names a statement the page only carries in its heading still reaches the right page.

    The fused order is trusted for the leading pages and then topped up with figure-dense pages:
    a filing answers metric questions on its statements, so once the lexical candidates are
    exhausted, pages with a high share of numeric tokens (and the best term coverage among them)
    are the most likely evidence. Every citation is an existing entry version and each page is
    cited at most once.
    """
    query = (question or "").strip()
    if limit < 1 or not query:
        return ()

    records = await _memory_records(memory)
    if not records:
        return ()

    by_entry = {record.entry.entry_id: index for index, record in enumerate(records)}
    terms = tuple(dict.fromkeys(_content_terms(query)))

    rankings: list[list[int]] = []
    result = await memory.search(SearchMemoryRequest(query=query, limit=max(limit * 4, 32), mode="auto"))
    searched = [by_entry[hit.entry_id] for hit in result.hits if hit.entry_id in by_entry]
    ranker: _PageRanker | None = None
    covers: list[float] = []
    if terms:
        ranker = _PageRanker(records)
        totals = [ranker.bm25(terms, index) for index in range(len(records))]
        covers = [ranker.coverage(terms, index) for index in range(len(records))]
        for scores in (totals, covers):
            rankings.append(sorted(range(len(records)), key=lambda index: (-scores[index], index)))
    if searched:
        rankings.append(searched)
    if not rankings:
        return ()

    order = _reciprocal_rank_fusion(rankings, depth=10)
    if ranker is not None and len(order) > _HEAD_PAGES:
        head, tail = order[:_HEAD_PAGES], order[_HEAD_PAGES:]
        tail.sort(key=lambda index: (-(ranker.numeric[index] + _TAIL_NUMERIC_WEIGHT * covers[index]), index))
        order = [*head, *tail]

    citations: list[MemoryCitation] = []
    seen: set[tuple[str, int]] = set()
    for index in order:
        record = records[index]
        sources = record.entry.sources
        identity = _page_identity(sources[0].source_id) if sources else ("", index)
        if identity in seen:
            continue
        seen.add(identity)
        citations.append(record.citation)
        if len(citations) >= limit:
            break
    return tuple(citations)



__all__ = [
    "PDFDocumentInput",
    "PDFPageInput",
    "PDFPageSource",
    "parse_pdf_document",
    "PDF_PAGE_SOURCE_DEFINITION",
    "search_pdf_pages",
]
