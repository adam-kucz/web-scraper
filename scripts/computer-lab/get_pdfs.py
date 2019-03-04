import argparse
from pathlib import Path
from typing import Callable, Iterable, Optional, Set
from urllib.parse import urlparse

import requests
from requests_html import HTMLSession


def subsite(url: str, toplevel: str) -> bool:
    return url.startswith(toplevel) and\
        (url.endswith("/") or url.endswith(".html"))


def get_links(url: str, element: str = 'html',
              selection_filter: Callable[[str], bool] = lambda _: True,
              recurse_filter: Optional[Callable[[str], bool]] = None,
              session: HTMLSession = HTMLSession(),
              visited: Set[str] = set(), depth: int = 10) -> Set[str]:
    if depth < 0:
        return set()
    if not recurse_filter:
        recurse_filter = lambda link: subsite(link, url)  # noqa: E731
    if not visited:
        visited.add(url)

    print("Visiting page {}".format(url))

    response = session.get(url)
    # pylint: disable=no-member
    if not response.status_code == requests.codes.ok:
        print("Received status code {} for site {}"
              .format(response.status_code, url))
        response.raise_for_status()
    # TODO: [difficult] implement raven authentication

    new_links: Set[str] = set()
    collected: Set[str] = set()
    for elem in response.html.find(element):
        new_links.update(filter(recurse_filter, elem.absolute_links))
        collected.update(filter(selection_filter, elem.absolute_links))
    new_links.difference_update(visited)

    visited.update(new_links)
    for link in new_links:
        collected.update(get_links(link, element, selection_filter,
                                   recurse_filter, session, visited,
                                   depth - 1))
    return collected


def corresponding_relpath(url):
    url = urlparse(url)
    path = Path(url.path)
    relpath = path.relative_to(path.anchor)
    return Path(url.netloc).joinpath(relpath)


def save_files(urls: Iterable[str], parent: Path = Path('.'),
               session: HTMLSession = HTMLSession()) -> None:
    for url in urls:
        # TODO: implement last-modified date checking
        # before downloading a new file
        response = session.get(url)
        # pylint: disable=no-member
        if not response.status_code == requests.codes.ok:
            print("Received status code {} for site {}"
                  .format(response.status_code, url))
            response.raise_for_status()
        # TODO: [difficult] implement raven authentication

        path = parent.joinpath(corresponding_relpath(url))
        if not path.parent.exists():
            path.parent.mkdir(parents=True)
        path.write_bytes(response.content)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()  # pylint: disable=invalid-name
    parser.add_argument('site', type=str,
                        help='website to download files from')
    parser.add_argument('--rootdir', default=Path('.'), type=Path,
                        help='root dir to save files to')
    args = parser.parse_args()  # pylint: disable=invalid-name

    LINKS = get_links(args.site, '#content', lambda x: x.endswith(".pdf"))
    save_files(LINKS, args.rootdir)
    print("Downloaded {} pdfs to {}".format(len(LINKS), args.rootdir))
