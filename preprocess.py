# this reas all files from a given directory (my output/)
# and expects format of
# url: https://nlp.stanford.edu/IR-book/exercises.html
# url_id: /IR-book/exercises
# title: Introduction to Information Retrieval: Exercises
# read_at: 02/01/2026
# parents: /IR-book/information-retrieval
# links: (empty or comma separated list of raw links)
# CONTENT_HERE UNDER LINKS

# Furthermore, from each of these files, punctuation, special characters are removed,
# all text is lowercase
# text is tokenized into words
#
# for each page, after tokenization, each word will be counted (page-level) and stored in a Counter linked to that word. this counter and word combination will have a url_id -> counter of words mapping
#
# and each page should have this
#
# Bibliography pages will be skipped s. (bibliography-1.html)
#
# the preprocess class will be responsible for the above and output an array of URL_Ids -> Word Count
# for this text
#     " This is an example input. This is not real data. This is for testing is is for input    "
# where each sentence would reflect a page
#    This is an example input not real data for testing
# S1  1    1  1   1       1    0    0    0   0    0
# S2  1    1  0    0      0    1    1    1   0    0
# S3  1    3  0    0      1    0    0    0   2    0

# The entire vocabulary will be the columns, and pages will be the rows
#
# The vocabulary will be reduced to int ids(0 -n where n = distinct words (included stop words))
# This will be a Numpy Matrix
# This will be the output to the preprocess step


from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Sequence
from collections import Counter
import re

import numpy as np


@dataclass
class PageRecord:
    """
    Represents the saved page from the crawler's output
    """
    url: str
    url_id: str
    title: str
    read_at: str
    parents: str
    links: List[str]
    content: str


@dataclass
class PreprocessOutput:
    """
    Output in format of a Matrix of Page (m) x (n) vocab,
    where each cell = occurences of vocab in page
    - X: Document term occurences
    - rows = url_ids parsed from filename (stripped .txt)
    - columns = vocab (size of 1 .. n)
    """
    X: np.ndarray
    url_ids: List[str]
    vocab: Dict[str, int]


class Preprocess:
    """
    Read files from input directory, parse files for text,
    normalize text, tokenize into words for each document,
    count word-counts per page, build global vocabulary,
    output numpy matrix of document - term
    """
    logging: bool
    def __init__(
        self,
        input_dir: Path,
        logging: bool = False
    ) -> None:
        self.input_dir = input_dir
        self.logging = logging

    def run(self) -> PreprocessOutput:
        """Entire pipeline in one function"""
        url_ids: List[str] = []
        page_counts: List[Dict[str, int]] = []

        for path in self.iter_input_files():
            page = self.parse_file(path)
            norm = self.normalize_text(page.content)
            tokens = self.tokenize(norm)
            counts = self.count_tokens(tokens)

            url_ids.append(page.url_id)
            page_counts.append(counts)

        vocab = self.build_vocab(page_counts)
        X = self.vectorize(page_counts, vocab)

        return PreprocessOutput(X=X, url_ids=url_ids, vocab=vocab)


    def iter_input_files(self) -> Iterable[Path]:
        """Yield file paths in alphabetical order, sorted by alphabetical order"""
        for p in sorted(self.input_dir.iterdir()):
            if p.is_file():
                if p.name.startswith("bibliography-"):
                    continue
                yield p

    def parse_file(self, path: Path) -> PageRecord:
        """Parse one page file into header fields + content body."""
        text = path.read_text(encoding="utf-8", errors="ignore")
        if self.logging:
            print(f"READ {path}")

        it = iter(text.splitlines())
        

        url = next(it).split(":", 1)[1].strip()
        url_id = next(it).split(":", 1)[1].strip()
        title = next(it).split(":", 1)[1].strip()
        read_at = next(it).split(":", 1)[1].strip()
        parents = next(it).split(":", 1)[1].strip()

        raw_links = next(it).split(":", 1)[1].strip()
        links = [] if raw_links == "" else [x.strip() for x in raw_links.split(",") if x.strip()]

        # After `links:`, everything is raw content (free-form, may contain blank lines/spaces).
        content = "\n".join(it).strip()

        return PageRecord(
            url=url,
            url_id=url_id,
            title=title,
            read_at=read_at,
            parents=parents,
            links=links,
            content=content,
        )

    def normalize_text(self, text: str) -> str:
        """Lowercase and remove punctuation/special characters as specified."""
        text = text.lower()
        text = re.sub(r"[^a-z0-9\s]+", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def tokenize(self, text: str) -> List[str]:
        """Convert normalized text into word tokens.
            Naively separate based on spaces for now
        """
        text = text.strip()
        if not text:
            return []
        return text.split(" ")

    # TODO Create either stemmer or lemmarizer


    def count_tokens(self, tokens: Sequence[str]) -> Dict[str, int]:
        """Compute page-level word counts (term -> count)."""
        return dict(Counter(tokens))

    def build_vocab(self, pages: Sequence[Dict[str, int]]) -> Dict[str, int]:
        """Create Global Level vocab. Returns a {"url_id": int(vocab_id)}"""
        vocab_terms = set()
        for counts in pages:
            vocab_terms.update(counts.keys())
        return {term: i for i, term in enumerate(sorted(vocab_terms))}

    def vectorize(
        self,
        page_counts: Sequence[Dict[str, int]],
        vocab: Dict[str, int],
    ) -> np.ndarray:
        """Document - Term Frequency Array. Col = Vocab, Row = page"""
        X = np.zeros((len(page_counts), len(vocab)), dtype=np.int64)
        for row_idx, counts in enumerate(page_counts):
            for term, c in counts.items():
                col_idx = vocab[term]
                X[row_idx, col_idx] = c
        return X


