import argparse
import os
from pathlib import Path
from typing import (Callable, Optional, Set, Tuple,
                    List, Mapping, Union, TypeVar)
from urllib.parse import urlparse, ParseResult as URL

from funcy import partial, rpartial, all_fn, post_processing
from maya import MayaDT, parse, now
import requests
from requests_html import HTMLSession, HTMLResponse

Time = MayaDT
time_from_epoch = MayaDT  # pylint: disable=invalid-name
time_from_header = parse  # pylint: disable=invalid-name


CHUNK_SIZE = 16 * 1024


A = TypeVar('A')
B = TypeVar('B')


def bind(ma: Optional[A], f: Callable[[A], Optional[B]]) -> Optional[B]:
    return f(ma) if ma else None


@post_processing(all)
def urlstartswith(url: URL, parent: URL):
    yield url.netloc == parent.netloc
    yield url.path.startswith(parent.path)


def epoch(time: Time) -> float:
    return time.datetime().timestamp()


def subsite(toplevel: URL, url: URL) -> bool:
    return (urlstartswith(url, toplevel)
            and (url.path.endswith("/") or url.path.endswith(".html")))


def get_links(url: URL, element: str = 'html',
              selection_filter: Callable[[str], bool] = lambda _: True,
              recurse_filter: Optional[Callable[[str], bool]] = None,
              session: HTMLSession = HTMLSession(),
              visited: Optional[Set[URL]] = None, depth: int = 20)\
              -> Mapping[str, Set[str]]:
    visited = visited or set()
    if depth < 0:
        print(f"Reached maximum depth in {url}")
        return set()
    recurse_filter = recurse_filter or partial(subsite, url)
    if not visited:
        visited.add(url)

    response = session.get(url.geturl())
    # pylint: disable=no-member
    if not response.status_code == requests.codes.ok:
        return {}
        # response.raise_for_status()
    # TODO: [difficult] implement raven authentication

    new_links: Set[URL] = set()
    collected: Mapping[URL, Set[URL]] = {}
    for elem in response.html.find(element):
        new_links.update(filter(recurse_filter,
                                map(urlparse, elem.absolute_links)))
        collected[url] = set(filter(selection_filter,
                                    map(urlparse, elem.absolute_links)))
    new_links.difference_update(visited)

    visited.update(new_links)
    for link in new_links:
        collected.update(get_links(link, element, selection_filter,
                                   recurse_filter, session, visited,
                                   depth - 1))
    return collected


def corresponding_relpath(url: URL):
    path = Path(url.path)
    relpath = path.relative_to(path.anchor)
    return Path(url.netloc).joinpath(relpath)


def save_files(url_groups: Mapping[str, Set[str]], parent: Path = Path('.'),
               session: HTMLSession = HTMLSession())\
               -> Tuple[List[HTMLResponse],
                        List[HTMLResponse],
                        List[Tuple[str, Time, Time]]]:
    logs = ([], [], [])
    for source, urls in url_groups.items():
        for url in urls:
            try:
                i, log = save_file(url, parent, session)
                if i != OK:
                    logs[i].append(log)
            except Exception as err:
                print(f"Exception occured for url {url} from {source}:\n"
                      f"{err}")
    return logs


# TODO: extract to enum
OK, ERROR, NON_PDF, PRESENT = -1, 0, 1, 2


def save_file(url: URL, parent: Path, session: HTMLSession)\
        -> Tuple[int, Union[HTMLResponse, Tuple[str, Time, Time], None]]:
    response = session.get(url.geturl())  # , stream=True)
    # pylint: disable=no-member
    if response.status_code != requests.codes.ok:
        return ERROR, response
    # TODO: [difficult] implement raven authentication
    if response.headers['Content-Type'] != 'application/pdf':
        return NON_PDF, response
    path = parent.joinpath(corresponding_relpath(url))
    if not path.parent.exists():
        path.parent.mkdir(parents=True)
    remote_time = time_from_header(response.headers['Last-Modified'])
    if path.is_file():
        file_time = time_from_epoch(path.stat().st_mtime)
        if file_time >= remote_time:
            return PRESENT, (url, remote_time, file_time)

    with path.open('wb') as fout:
        for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
            if chunk:
                fout.write(chunk)
    os.utime(path, times=(epoch(now()), epoch(remote_time)))
    return OK, None


# TODO: implement html source download
def interactive():
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('site', type=str,
                        help='website to download files from')
    parser.add_argument('-d', '--dir', default=Path('.'), type=Path,
                        help='directory to save files in')
    group = parser.add_mutually_exclusive_group()
    group.add_argument('-r', '--root', default=None, type=str,
                       help='url of the toplevel which should not be left')
    group.add_argument('-l', '--local', action='store_true',
                       help='alternative to root, sets root to value of site')
    parser.add_argument('-i', '--ignore_root', action='store_true',
                        help=('ignore toplevel when deciding '
                              'whether to download a particular pdf '
                              '(toplevel only used for recursive walk)'))
    parser.add_argument('-e', '--element', default="#content", type=str,
                        help='maximum number of links to follow')
    parser.add_argument('-m', '--max_depth', default=20, type=int,
                        help='maximum number of links to follow')
    args = parser.parse_args()

    selection_filter = (lambda url: url.path.endswith(".pdf"))
    root = bind(args.root if not args.local else args.site, urlparse)
    if root and not args.ignore_root:
        selection_filter = all_fn(selection_filter,
                                  rpartial(urlstartswith, root))

    links = get_links(urlparse(args.site),
                      element=args.element,
                      selection_filter=selection_filter,
                      recurse_filter=(partial(subsite, root) if root
                                      else (lambda _: True)),
                      depth=args.max_depth)
    logs = errors, non_pdfs, already_present = save_files(links, args.dir)
    num_links = sum(map(len, links.values()))
    print(f"Downloaded {num_links - sum(map(len, logs))} "
          f"out of {num_links} pdfs to {args.dir} "
          f"({len(already_present)} were already present)")
    print()
    if non_pdfs:
        print(f"There were {len(non_pdfs)} non-pdf responses:")
        for response in non_pdfs:
            print(f"{response.url}: {response.headers['Content-Type']}")
    else:
        print("There were no non-pdf responses.")
    print()
    if errors:
        print(f"There were {len(errors)} errors:")
        for error in errors:
            print(f"{error.url}: {error.status_code} [{error.reason}]")
    else:
        print("There were no errors.")


if __name__ == '__main__':
    interactive()
