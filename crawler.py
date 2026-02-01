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
from pathlib import Path
from urllib.request import urlopen

from bs4 import BeautifulSoup

# Path.cwd() -> as root by default

class FrontierNode:
    url: str

    def __ref__(self):
        return self.url

    def __init__(self, url: str):
        self.url = url
        

class ExpandedNode(FrontierNode):
    raw_contents: str
    clean_contents: str
    title: str
    links: set[str]
    parents: set[str]
    url_id: str # defined in the crawler. This will be file name
    
    def __str__(self) -> str:
        #save format -> title, read_at, links (comma-separeted list), dump of clean_contents
        # get time scraped, utc time, format m/d/y
        now = datetime.now(timezone.utc).strftime("%m/%d/%Y")
        return f"url: {self.url}\ntitle: {self.title}\nread_at: {now}\nlinks: {", "}\n{self.clean_contents}"

    def __init__(self, raw_contents: str,clean_contents: str,title: str,links: set[str],parents: set[str], url_id: str):
        self.raw_contents = title
        self.clean_contents = title
        self.title = title
        self.links = links
        self.parents = parents
        self.url_id = url_id



class Crawler:
    # note this is not the url.. this is the domain + path to start @... Does not contain http[s]://
    seed_domain: str
    # Frontier = nodes that are discovered, but not expanded (not saved to file). They migh have children, might be leaf nodes
    frontier: deque[FrontierNode]
    # store graph_dict as uri -> set of link uri, representing children
    graph_dict:  dict[str, set[str]]
    # store regex pattern for okay url.. no need to compile many times
    okay_url_regex: re.Pattern
    save_path: Path    
                            
    def __init__(self, seed_domain: str, save_path: Path = Path.cwd()):
        seed_domain = seed_domain.lower()
        self.seed_domain = seed_domain
        #                               starts with     escape domain         anytext  end with .htm(l)
        # iteration 2 of regex -> include () for match[0,1,2], etc to extract path
        self.okay_url_regex = re.compile("^(https?://" + re.escape(self.seed_domain) + ")(.*)[.]html?$")
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

    def attempt_parse_and_build_expanded_node(self, parent_node: ExpandedNode, current_node: FrontierNode) -> ExpandedNode | None:
        html = Crawler.fetch_url(current_node.url)
        if not html:
            print("Could not Parse Root Page")
            print(f"Page: {current_node} not found")
            return
        extracted_info = Crawler.extract_info(html)
        if not extracted_info:
            print("Error extracting Info for Page")
            print(f"Page: {current_node} not extracted")
            return
        title, clean_contents = extracted_info
        found_links = Crawler.discover_urls(self, html)
        url_id = Crawler.construct_uri_id(self.okay_url_regex, current_node.url)
                
        return ExpandedNode(
            raw_contents = str(html),
            clean_contents = clean_contents,
            title = title,
            links = found_links,
            parents = set(parent_node.url_id),
            url_id = url_id

        )
    
    
    def is_url_ok_to_follow(regex: re.Pattern, url: str) -> bool:
        # matches the regex rules
        if regex.match(url):
            return True
        
        return False

    # cache the raw page bytes
    def save_page(self, node: ExpandedNode) -> bool:
        # write path = url_id + .txt file

        # write as url_id + .txt
        write_path = self.save_path / str(node.url_id + ".txt")
        write_path.write_text(str(node), encoding="utf-8")
        return False 

    #helper function to construct a uri id that can name the file and represent that URI as a node of a graph
    # this function should only be called IF there is a valid URI
    def construct_uri_id(regex: re.Pattern, uri: str) -> str:
        # in the future, this could be hashed from the url path?? 
        # goal is to take a full url, strip the prefix, seed_Domain, and only contain the path after the seed domain
        print(regex)
        id = regex.match(uri) # match 1 = domain+prefix, match 2 = path
        if not id:
            print(uri, id, "DID NOT MATCH")
        path = id[2]
        # convert to file safe extension
        path = path.replace("/", "_")
        return path

    # returns either bs4 parser or None
    def fetch_url(url: str) -> BeautifulSoup | None:
        # load url, get status_code
        page = urlopen(url)
        html = page.read().decode("utf-8")
        status_code = page.getcode()
        if status_code > 400:
            # TODO add logging
            print(f"Status: {status_code}")
            return None
        parser = BeautifulSoup(html, "html.parser")
        return parser
        
    # Return expanded node if works, else None
    # returns a title, content pair, or None
    def extract_info(html: BeautifulSoup) -> tuple[str, str] | None:
        # extract title and text from HTML contents
        # find first (h1, or h2)
        title = html.find_next(["h1", "h2"])
        if not title:
            print("Error - No title Found")
            print(html)
            return None

        p_tags = html.find_all("p")
        body = str()
        # TODO there is probably a better method than a for loop
        for p in p_tags:
            if p.text:
                # moved to html section in open_page_return_parser
                # TODO Make this better 
                body += re.sub(r"[\n\t]*", "", p.text)

        return (title, body)


    def discover_urls(self, html: BeautifulSoup) -> set[str]:
        # look for all hrefs
        # yes? -> add to return list
        # parse all href
        raw_links = html.select('a[href]')
        links = set()
        for link in raw_links:
            # add element, do nothing if already exists
            url = link.attrs["href"]
            # if not string, skip
            if not isinstance(url, str):
                continue
            # is okay to follow, add
            if Crawler.is_url_ok_to_follow(self.okay_url_regex, url):
                links.add(link.attrs["href"])

        return links

    def crawl(self):
        graph_dict = {}
        frontier_queue = deque()
        last_node = None
        
        root_url = "https://" + self.seed_domain
        root_url_id = Crawler.construct_uri_id(self.okay_url_regex, root_url)

        # construct root node for graph entry.. Just populate with Emtpy stuff + give url_id as root.
        # First PAss will create 
        root_node = ExpandedNode(
            raw_contents= "",
            clean_contents= "",
            title = "",
            links = set(),
            parents = set(),
            url_id= root_url_id
        )
        # first pass is a frontier node
        first_page = FrontierNode(url= root_url)
        # add first_page to frontier_queue
        frontier_queue.append(first_page)
        last_node = root_node
        # for now repeat 3 times:
        for i in range(3):
            time.sleep(1)
            current_expanded_node = self.attempt_parse_and_build_expanded_node(parent_node=last_node, current_node=frontier_queue.popleft()) # append adds to right, for queue = first in first out -> this popleft
            
            
            if not current_expanded_node:
                print("Problem")
                continue
            else:
                # first time this expanded node created
                # also save page
                if not self.save_page(current_expanded_node):
                    print(f"ERROR SAVING PAGE {current_expanded_node.url_id}")
                graph_dict[current_expanded_node.url_id] = set()
                for link in current_expanded_node.links:
                    # construct uri_id + check Graph for existing
                    link_id = Crawler.construct_uri_id(self.okay_url_regex, link)
                    # add link_id
                    graph_dict[current_expanded_node.url_id].add(link_id)
                    # before adding to frontier queue, check if exists
                    # this should handle any dict
                    if link_id in graph_dict:
                        # skip... This is already done
                        continue
                    # construct FrontierNode
                    temp = FrontierNode(link)
                    frontier_queue.append(temp)
            # poorly named.. This refers to the last expanded node in the queue
            last_node = current_expanded_node

        return graph_dict                 
                            
SEED_URL = "nlp.stanford.edu/IR-book/information-retrieval-book.html"
crawler = Crawler(SEED_URL)
crawled_graph = crawler.crawl()
for key, value in crawled_graph.items():
    print(key)
    print(value)
    print()
