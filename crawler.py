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
            f"title: {self.title.replace("\n", " ")}\n"
            f"read_at: {now}\n"
            f"parents: {parents_csv}\n"
            f"links: {links_csv}\n"
            f"{self.clean_contents}"
        )



class Crawler:
    # seed input can be a bare domain (nlp.stanford.edu), domain+path, or full URL
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
            self.seed_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
            if parsed.query:
                self.seed_url += f"?{parsed.query}"
        else:
            # domain or domain+path
            parsed = urlparse("https://" + seed_input)
            self.seed_domain = parsed.netloc.lower()
            self.seed_url = "https://" + seed_input

        self.okay_url_regex = re.compile(
            rf"^https?://{re.escape(self.seed_domain)}/.*\.(?:html?|htm)$",
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
        # regex = domain + extensions
        if not regex.match(url):
            return False

        parsed = urlparse(url)
        #  https/http allowed
        if parsed.scheme not in ("http", "https"):
            return False
        # ignore empty
        if url.strip() == "":
            return False

        # pdfs were a problem eaerlier, ignore them
        path_lower = (parsed.path or "").lower()
        if path_lower.endswith(".pdf"):
            return False

        return True

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
    # https://nlp.stanford.edu/IR-book/information-retrieval-book.html
    # TO
    # /IR-book/information-retrieval-book
    def construct_uri_id(regex: re.Pattern[str], uri: str) -> str:
        # my original apprach was to use a regex pattern match, which
        # I tried to use (https://domaing)/(path_to).html
        # and matching the 2nd, but this did not work well at all
        # got some LLM help here
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
        # i wrote hte try block, got ChatGTP ot generate exception handling
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
        raw_links = html.select("a[href]")
        links: set[str] = set()

        for link in raw_links:
            href = link.attrs.get("href")
            if not isinstance(href, str):
                continue

            # i stopped at get href, used an LLM for more filtering/urljon/parse.
            href = href.strip()
            if href == "" or href.startswith("#"):
                continue
            if href.lower().startswith(("mailto:", "javascript:", "tel:")):
                continue

            abs_url = urljoin(base_url, href)
            parsed = urlparse(abs_url)
            abs_url = parsed._replace(fragment="").geturl()

            # Only follow .htm/.html pages
            if Crawler.is_url_ok_to_follow(self.okay_url_regex, abs_url):
                links.add(abs_url)

        return links

    def crawl(self):
        # BFS frontier qeuue.
        # prevent cycles (update the parents in Expadned nOde that already exists to preserve that discovered information)
        # this graph is key based (url_id)
        # nodes store mapping of url_id -> Actual Page Info Extracted + saved
        graph_dict: dict[str, set[str]] = {}
        nodes: dict[str, ExpandedNode] = {}

        frontier_queue: deque[FrontierNode] = deque()
        enqueued_ids: set[str] = set()
        expanded_ids: set[str] = set()

        root_url = self.seed_url
        root_id = Crawler.construct_uri_id(self.okay_url_regex, root_url)

        # save root node, add to graph + node referenced by graph (keybased)
        nodes[root_id] = ExpandedNode(url=root_url, url_id=root_id)
        graph_dict.setdefault(root_id, set())


        frontier_queue.append(FrontierNode(url=root_url))
        enqueued_ids.add(root_id)

        # Help from LLM here.
        # Used for testing.. My original approach just had a for i in range(n)
        # loop, LLM suggested this for more control
        max_expansions = 300
        expansions = 0

        while frontier_queue and expansions < max_expansions:
            # timer betwen requests
            time.sleep(1)

            current_frontier = frontier_queue.popleft()
            current_id = Crawler.construct_uri_id(self.okay_url_regex, current_frontier.url)

            # skip already explored pages
            if current_id in expanded_ids:
                continue

            current_node = self.attempt_parse_and_build_expanded_node(
                parent_node=None,
                current_node=current_frontier,
            )
            if current_node is None:
                continue

            # Any parent node that existed before expanding should be kept
            if current_id in nodes:
                current_node.parents |= nodes[current_id].parents

            # save ExpandedNode
            nodes[current_node.url_id] = current_node
            expanded_ids.add(current_node.url_id)

            # add set if not exists
            graph_dict.setdefault(current_node.url_id, set())

            # save to files
            self.save_page(current_node)

            # Process children (construl uri for graph + add edges), remove self-loops
            for child_url in current_node.links:
                child_id = Crawler.construct_uri_id(self.okay_url_regex, child_url)

                # no self-loop
                # LLM suggested this
                if child_id == current_node.url_id:
                    continue

                # add edge current -> child
                graph_dict[current_node.url_id].add(child_id)

                # ensure child node exists so we can update parents whenever.. This only matters on first discovery of fronteier, but allows adds later
                if child_id not in nodes:
                    nodes[child_id] = ExpandedNode(url=child_url, url_id=child_id)

                # update child parents
                nodes[child_id].parents.add(current_node.url_id)

                # add only if not in queue already
                if child_id not in expanded_ids and child_id not in enqueued_ids:
                    frontier_queue.append(FrontierNode(url=child_url))
                    enqueued_ids.add(child_id)

            expansions += 1
        self.graph_dict = graph_dict
        return graph_dict

SEED_URL = "nlp.stanford.edu/IR-book/information-retrieval-book.html"
crawler = Crawler(SEED_URL, save_path=Path.cwd() / "output2")
crawled_graph = crawler.crawl()
for key, value in crawled_graph.items():
    print(key)
    print(value)
    print()
