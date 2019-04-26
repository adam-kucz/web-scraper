import argparse
import os
from pathlib import Path
from typing import Callable, Iterable, Optional, Set, Tuple, List
from urllib.parse import urlparse

from funcy import partial
from maya import MayaDT, parse, now
import requests
from requests_html import HTMLSession, HTMLResponse

Time = MayaDT
time_from_epoch = MayaDT  # pylint: disable=invalid-name
time_from_header = parse  # pylint: disable=invalid-name


CHUNK_SIZE = 16 * 1024


def epoch(time: Time) -> float:
    return time.datetime().timestamp()


def subsite(toplevel: str, url: str) -> bool:
    return (url.startswith(toplevel)
            and (url.endswith("/") or url.endswith(".html")))


def get_links(url: str, element: str = 'html',
              selection_filter: Callable[[str], bool] = lambda _: True,
              recurse_filter: Optional[Callable[[str], bool]] = None,
              session: HTMLSession = HTMLSession(),
              visited: Set[str] = set(), depth: int = 10) -> Set[str]:
    if depth < 0:
        return set()
    recurse_filter = recurse_filter or partial(subsite, url)
    if not visited:
        visited.add(url)

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
               session: HTMLSession = HTMLSession())\
               -> Tuple[List[HTMLResponse], List[Tuple[str, Time, Time]]]:
    errors, already_present = [], []
    for url in urls:
        response = session.get(url, stream=True)
        # pylint: disable=no-member
        if response.status_code != requests.codes.ok:
            errors.append(response)
            continue
        # TODO: [difficult] implement raven authentication

        path = parent.joinpath(corresponding_relpath(url))
        if not path.parent.exists():
            path.parent.mkdir(parents=True)
        remote_time = time_from_header(response.headers['Last-Modified'])
        if path.is_file():
            file_time = time_from_epoch(path.stat().st_mtime)
            if file_time >= remote_time:
                already_present.append((url, remote_time, file_time))
                continue

        with path.open('wb') as fout:
            for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                if chunk:
                    fout.write(chunk)
        os.utime(path, times=(epoch(now()), epoch(remote_time)))
    return errors, already_present


def interactive():
    parser = argparse.ArgumentParser()
    parser.add_argument('site', type=str,
                        help='website to download files from')
    parser.add_argument('-r', '--rootdir', default=Path('.'), type=Path,
                        help='root dir to save files to')
    args = parser.parse_args()

    links = get_links(args.site, '#content', lambda x: x.endswith(".pdf"))
    errors, already_present = save_files(links, args.rootdir)
    print(f"Downloaded {len(links) - len(errors) - len(already_present)} "
          f"out of {len(links)} pdfs to {args.rootdir} "
          f"({len(already_present)} were already present)")
    print(f"There were {len(errors)} errors:")
    for error in errors:
        print(f"{error.url}: {error.status_code} [{error.reason}]")


if __name__ == '__main__':
    interactive()
