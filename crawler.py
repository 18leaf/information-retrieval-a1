"""
        current_expanded_node = self.attempt_parse_and_build_expanded_node(parent_node=parent_node, current_node=frontier_queue.pop())

📋 TODO: Write your code to implement this crawler. Name the file crawler.py. Ideally, make it a class with the following methods:

__init__: Initialize the crawler with the seed URL and other parameters.
is_url_ok_to_follow: Check if the URL is okay to follow.
save_page: Save the crawled page to a file.
extract_info: Extract the title and text from the HTML content.
discover_urls: Extract all the URLs from the HTML content, validate them, and add new ones to the frontier queue.
crawl: Start crawling the URLs.

"""
import time
import re
from collections import deque
from datetime import datetime, timezone
from dataclasses import dataclass, field
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse, unquote
from urllib.request import urlopen

from bs4 import BeautifulSoup

# Path.cwd() -> as root by default

@dataclass
class FrontierNode:
    url: str

    def __str__(self) -> str:
        return self.url


@dataclass
class ExpandedNode(FrontierNode):
    raw_contents: str = ""
    clean_contents: str = ""
    title: str = ""
    links: set[str] = field(default_factory=set)
    parents: set[str] = field(default_factory=set)
    url_id: str = ""  # stable node id based on path (no domain)

    def __str__(self) -> str:
        # save format -> url, url_id, title, read_at, parents, links, clean_contents
        now = datetime.now(timezone.utc).strftime("%m/%d/%Y")
        links_csv = ", ".join(sorted(self.links))
        parents_csv = ", ".join(sorted(self.parents))
        return (
            f"url: {self.url}\n"
            f"url_id: {self.url_id}\n"
            f"title: {self.title}\n"
            f"read_at: {now}\n"
            f"parents: {parents_csv}\n"
            f"links: {links_csv}\n"
            f"{self.clean_contents}"
        )



class Crawler:
    # seed input can be a bare domain, domain+path, or full URL
    seed_domain: str
    seed_url: str
    # Frontier = nodes that are discovered, but not expanded (not saved to file). They might have children, might be leaf nodes
    frontier: deque[FrontierNode]
    # store graph_dict as uri_id -> set of child uri_id, representing outgoing edges
    graph_dict: dict[str, set[str]]
    # store regex pattern for okay url.. no need to compile many times
    okay_url_regex: re.Pattern[str]
    save_path: Path

    def __init__(self, seed_domain: str, save_path: Path = Path.cwd()):
        # Accept:
        # - "nlp.stanford.edu"
        # - "nlp.stanford.edu/IR-book/information-retrieval-book.html"
        # - "https://nlp.stanford.edu/IR-book/information-retrieval-book.html"
        seed_input = seed_domain.strip()

        if seed_input.startswith("http://") or seed_input.startswith("https://"):
            parsed = urlparse(seed_input)
            self.seed_domain = parsed.netloc.lower()
            # keep original case of path (servers can be case-sensitive)
            self.seed_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
            if parsed.query:
                self.seed_url += f"?{parsed.query}"
        else:
            # domain or domain+path
            parsed = urlparse("https://" + seed_input)
            self.seed_domain = parsed.netloc.lower()
            # preserve original path case by slicing from original input when possible
            # (urlparse doesn't lowercase path, but we also avoid lowercasing seed_input)
            self.seed_url = "https://" + seed_input

        # Validation regex: restrict to same domain (scheme+host); path filtering happens elsewhere.
        self.okay_url_regex = re.compile(
            rf"^https?://{re.escape(self.seed_domain)}(?:/.*)?$",
            re.IGNORECASE,
        )
        if save_path is Path.cwd():
            # create dir for holding pages instead of dumping at root
            save_path = save_path / "pages"
            if not save_path.exists():
                # create dir pages
                save_path.mkdir(parents=True, exist_ok=True)
        else:
            # provided path DNE
            if not save_path.exists():
                print(f"Error Path {save_path} does Not Exist")
                exit()

        self.save_path = save_path

    def attempt_parse_and_build_expanded_node(self, parent_node: ExpandedNode | None, current_node: FrontierNode) -> ExpandedNode | None:
        html = Crawler.fetch_url(current_node.url)
        if not html:
            print(f"Fetch failed: {current_node.url}")
            return None

        extracted_info = Crawler.extract_info(html)
        if not extracted_info:
            print(f"Extract failed: {current_node.url}")
            return None

        title, clean_contents = extracted_info
        found_links = self.discover_urls(html, base_url=current_node.url)
        url_id = Crawler.construct_uri_id(self.okay_url_regex, current_node.url)

        parents: set[str] = set()
        if parent_node is not None and parent_node.url_id:
            parents.add(parent_node.url_id)

        return ExpandedNode(
            url=current_node.url,
            raw_contents=str(html),
            clean_contents=clean_contents,
            title=title,
            links=found_links,
            parents=parents,
            url_id=url_id,
        )


    def is_url_ok_to_follow(regex: re.Pattern, url: str) -> bool:
        # Must match allowed domain pattern
        if not regex.match(url):
            return False

        parsed = urlparse(url)
        # only http(s)
        if parsed.scheme not in ("http", "https"):
            return False
        # ignore empty / fragment-only
        if url.strip() == "":
            return False
        return True

    # cache the raw page bytes
    def save_page(self, node: ExpandedNode) -> bool:
        # write path = url_id + .txt file

        # write as a filesystem-safe name derived from the path ID
        file_safe_id = node.url_id.strip("/").replace("/", "_")
        if file_safe_id == "":
            file_safe_id = "root"
        write_path = self.save_path / (file_safe_id + ".txt")
        write_path.write_text(str(node), encoding="utf-8")
        return True

    # helper function to construct a uri id that can name the file and represent that URI as a node of a graph
    # goal: remove scheme+domain, drop common suffix (.html/.htm/etc), keep only the path as the stable node id
    # Example:
    #   https://nlp.stanford.edu/IR-book/information-retrieval-book.html
    # becomes:
    #   /IR-book/information-retrieval-book
    def construct_uri_id(regex: re.Pattern[str], uri: str) -> str:
        parsed = urlparse(uri)
        path = unquote(parsed.path or "/")

        # normalize path: ensure leading slash
        if not path.startswith("/"):
            path = "/" + path

        # strip trailing slash except for root
        if path != "/" and path.endswith("/"):
            path = path[:-1]

        # strip common "page" extensions
        path = re.sub(r"\.(?:html?|shtml|php|asp|aspx)$", "", path, flags=re.IGNORECASE)

        # if after stripping extension we end up empty, treat as root
        if path == "":
            path = "/"

        return path

    # returns either bs4 parser or None
    def fetch_url(url: str) -> BeautifulSoup | None:
        # load url, get status_code
        try:
            page = urlopen(url, timeout=15)
            status_code = page.getcode()
            if status_code and status_code >= 400:
                print(f"HTTP Status: {status_code} for {url}")
                return None
            raw = page.read()
        except HTTPError as e:
            print(f"HTTPError: {e.code} for {url}")
            return None
        except URLError as e:
            print(f"URLError: {e} for {url}")
            return None
        except Exception as e:
            print(f"Fetch error: {e} for {url}")
            return None

        html = raw.decode("utf-8", errors="replace")
        return BeautifulSoup(html, "html.parser")

    # Return expanded node if works, else None
    # returns a title, content pair, or None
    def extract_info(html: BeautifulSoup) -> tuple[str, str] | None:
        # extract title and text from HTML contents
        # prefer first h1/h2; fallback to <title>
        heading = html.find(["h1", "h2"])
        if heading and heading.get_text(strip=True):
            title_text = heading.get_text(strip=True)
        else:
            title_tag = html.find("title")
            if title_tag and title_tag.get_text(strip=True):
                title_text = title_tag.get_text(strip=True)
            else:
                print("Error - No title Found")
                return None

        p_tags = html.find_all("p")
        body_parts: list[str] = []
        for p in p_tags:
            text = p.get_text(" ", strip=True)
            if text:
                body_parts.append(text)

        body = "\n".join(body_parts)
        return (title_text, body)


    def discover_urls(self, html: BeautifulSoup, base_url: str) -> set[str]:
        # Extract hrefs, normalize to absolute URLs, drop fragments, filter to same domain.
        raw_links = html.select("a[href]")
        links: set[str] = set()

        for link in raw_links:
            href = link.attrs.get("href")
            if not isinstance(href, str):
                continue

            href = href.strip()
            if href == "" or href.startswith("#"):
                continue
            if href.lower().startswith(("mailto:", "javascript:", "tel:")):
                continue

            abs_url = urljoin(base_url, href)
            parsed = urlparse(abs_url)
            abs_url = parsed._replace(fragment="").geturl()

            if Crawler.is_url_ok_to_follow(self.okay_url_regex, abs_url):
                links.add(abs_url)

        return links

    def crawl(self):
        # BFS frontier (queue), prevent cycles/re-expansion, update parents whenever edges are discovered.
        graph_dict: dict[str, set[str]] = {}
        nodes: dict[str, ExpandedNode] = {}

        frontier_queue: deque[FrontierNode] = deque()
        enqueued_ids: set[str] = set()
        expanded_ids: set[str] = set()

        root_url = self.seed_url
        root_id = Crawler.construct_uri_id(self.okay_url_regex, root_url)

        # Seed node placeholder so parents/edges can reference it
        nodes[root_id] = ExpandedNode(url=root_url, url_id=root_id)
        graph_dict.setdefault(root_id, set())

        # enqueue seed (BFS)
        frontier_queue.append(FrontierNode(url=root_url))
        enqueued_ids.add(root_id)

        max_expansions = 3  # keep your current architecture/limit for now
        expansions = 0

        while frontier_queue and expansions < max_expansions:
            time.sleep(1)

            current_frontier = frontier_queue.popleft()
            current_id = Crawler.construct_uri_id(self.okay_url_regex, current_frontier.url)

            if current_id in expanded_ids:
                continue

            # Expand current page
            current_node = self.attempt_parse_and_build_expanded_node(
                parent_node=None,
                current_node=current_frontier,
            )
            if current_node is None:
                continue

            # Preserve any parents that might have been recorded before expansion
            if current_id in nodes:
                current_node.parents |= nodes[current_id].parents

            nodes[current_node.url_id] = current_node
            expanded_ids.add(current_node.url_id)

            # Ensure adjacency set exists
            graph_dict.setdefault(current_node.url_id, set())

            # Save page
            self.save_page(current_node)

            # Process children
            for child_url in current_node.links:
                child_id = Crawler.construct_uri_id(self.okay_url_regex, child_url)

                # no self-loop
                if child_id == current_node.url_id:
                    continue

                # add edge current -> child
                graph_dict[current_node.url_id].add(child_id)

                # ensure child node exists so we can update parents now (even before it's expanded)
                if child_id not in nodes:
                    nodes[child_id] = ExpandedNode(url=child_url, url_id=child_id)

                # update child parents
                nodes[child_id].parents.add(current_node.url_id)

                # enqueue if not seen (BFS), preventing cycles/repeats
                if child_id not in expanded_ids and child_id not in enqueued_ids:
                    frontier_queue.append(FrontierNode(url=child_url))
                    enqueued_ids.add(child_id)

            expansions += 1

        self.graph_dict = graph_dict
        return graph_dict

SEED_URL = "nlp.stanford.edu/IR-book/information-retrieval-book.html"
crawler = Crawler(SEED_URL)
crawled_graph = crawler.crawl()
for key, value in crawled_graph.items():
    print(key)
    print(value)
    print()
