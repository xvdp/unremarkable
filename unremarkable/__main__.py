"""
console entry points for unremarkable handling of reMarkable files

"""
from typing import Union, Optional, Any
import argparse
import os
import os.path as osp
import pprint

from .unremarkable import backup_tablet, upload_pdf, build_file_graph, \
    _is_host_reachable, _get_xochitl, restart_xochitl, get_remote_files
from .annotations import export_annotated_pdf
from .pdf import pdf_mod, get_page_sizes
from . import rmscene

_A="\033[0m"
_G="\033[34m"
_R="\033[31m"
_Y="\033[32m"
_B="\033[36m"
_M="\033[35m"
##
# console entry points
#
def remarkable_backup():
    """console entry point to backup remarkable hierarchy
    Args
        folder  (str ['.']) parent to backup, creates new backup if 'xochitl' folder not found
            if folder == "?"    searches for existing backup and only syncs if one found
    backup is done with incremental `rsync -avzhP --update`
    archive, verbose, compress, human-readable, partial, progress, newer files only
    """
    parser = argparse.ArgumentParser(description='Backup tablet')
    parser.add_argument('folder', type=str, nargs='?', default=None,
                        help='backup dir: ? recursive search | None from stored ~/.xochitl | "."')
    args = parser.parse_args()
    backup_tablet(args.folder)


def pdf_to_remarkable():
    """console entry point upload pdf to remarkable
    Args
        pdf     (str) valid pdf file or *
        parent  (str ['']) destination folder visible name
        --name  (str [None]) visible name, if None: pdfbasename.replace("_"," ")  
        --no_restart_xochitl      default restart_xochitls xochitl service to show upload, disable
    """
    parser = argparse.ArgumentParser(description='Upload pdf')
    parser.add_argument('pdf', type=str, help='valid .pdf file or "*"')
    parser.add_argument('parent', type=str, nargs='?', default='',
                        help='destination folder visible name')
    parser.add_argument('-n', '--name', type=str, default=None,
                        help='visible name; default is pdf basename without ext replacing "_"," "')
    parser.add_argument('-r', '--no_restart_xochitl', action='store_false', dest='restart_xochitl',
                        help='disable restart_xochitl of xochitl service')
    parser.add_argument('-f', '--force', action='store_true',
                        help='force upload even if name exists')
    # Parse arguments
    args = parser.parse_args()
    upload_pdf(args.pdf, args.parent, args.name, args.restart_xochitl, args.force)


def _asint(val: Any, msg: str = "") -> int:
    if isinstance(val, str):
        assert val.isnumeric(), f"expected integer input, got {val}, {msg}"
        val = int(val)
    assert isinstance(val, int), f"expected integer input, got {val}, {msg}"
    return val


def _asslice(pages: str, msg: str = "") -> Optional[slice]:
    out = pages.split("-")
    out[0] = 0 if out[0] in ('None', '') else _asint(out[0], msg)
    out[1] = None if out[1] in ('None', '') else _asint(out[1], msg)
    if out[0] == out[1]:    # invalid cases [None, None],  [2,2]
        print(f"\targ -p {pages} invalid slice, nothing done")
        out = None
    else:
        out = slice(*out)
    return out

def _parse_size(size: Optional[list]) -> Union[None, list, str]:
    if size is not None:
        _sizes = ['common', 'mean', 'A0', 'A1', 'A2', 'A3', 'A4', 'A5', 'A6', 'A7', 'A8', 'C4']
        _msg = f"\n\t-s arg expected <int int> or <str> in {_sizes}\n\tgot {size}"
        assert len(size) in (1, 2), _msg
        if len(size) == 1:
            size = size[0]
            assert size in _sizes, _msg
        else:
            size = [_asint(p, _msg) for p in size]
    return size

def _parse_pages(pages: Optional[list]) -> Union[None, int, list, slice]:
    """ fixed a couple rror cases, TODO move out of __main__
    """
    if pages is not None:
        assert isinstance(pages, list), f"expected list got {pages}, {type(pages)}"
        _msg = f"\n\t-p arg syntax expected as <int>, <int int ...>, <int->, <-int>\n\tgot {pages}"
        if len(pages) > 1:      # case     -p 1 2 45, list
            pages = [_asint(p, _msg) for p in pages]
        elif '-' in pages[0]:   # case  -p -2 | -p 1- | -p 1-9 , slice
            pages = _asslice(pages[0], _msg)
        else:                   # case -p 2, int
            pages = _asint(pages[0], _msg)
    return pages

def _get_bib_file(pdfname: str, bibname: Optional[str] = None) -> Optional[str]:
    """resolves bib name, renames to private .bibname.bib"""
    # print(f"getting bib for {pdfname}")
    if bibname is None or not osp.isfile(bibname):
        bibname = f'{osp.splitext(pdfname)[0]}.bib'
        # print(f"resolving bib name to {bibname}: exists? {osp.isfile(bibname)}")
    if bibname[0] != ".":
        __bib = ".".join([osp.dirname(bibname), osp.basename(bibname)])
        if osp.isfile(bibname):
            # print(f"renaming  bib to {__bib}")
            os.rename(bibname, __bib)
        bibname = __bib
    # print(f"is file {osp.isfile(bibname)}")
    return bibname if osp.isfile(bibname) else None

def _resolve_pdf(pdfname: str) -> str:
    pdf, ext = osp.splitext(pdfname)
    if not osp.isfile(pdfname) and ext.lower() != '.pdf':
        ext = '.pdf'
    return f'{pdf}{ext}'


def pdf_bibtex():
    """ add bibtex to metadata, required <file>.pdf and <file>.bib
    Args
        pdf     (str) .pdf filename
    optional
        bib     (str) .bib: if ommited will use same name as pdf  <pdf>.replace('.pdf', '.bib')
        -k --keys       (str | list) metadata keys to be deleted
        -n --name       (str) rename pdf: default overwrites
        -p --pages      (int | list | str) keep pages e.g. -a 5 7 11 | -a -4 | -a 13-17 
        -u --url        (str)
        renames  filename.bib to .filename.bib
    """
    parser = argparse.ArgumentParser(description='Add bib to pdf')
    parser.add_argument('pdf', type=str, help='valid .pdf file')
    parser.add_argument('bib', type=str, nargs='?', help='valid .bib file', default=None)
    parser.add_argument('-n', '--name', type=str, help='create new file with name -n', default=None)
    parser.add_argument('-p', '--pages', nargs='+', default=None,
                        help='page: eg. 2, pages: eg. 1 2 3 or pagerange: eg. 1- or 1-4')
    parser.add_argument('-k', '--keys', nargs='+', default=None, help="delete keys")
    parser.add_argument('-u', '--url', type=str, help='add url', default=None)
    args = parser.parse_args()

    pdf = _resolve_pdf(args.pdf)
    assert osp.isfile(pdf), f"pdf file not found {pdf}"


    bib = _get_bib_file(pdf, args.bib)
    assert osp.isfile(bib), f"bib file not found {args.bib}, use pdf_metadata for custom keys"

    pages = _parse_pages(args.pages)
    kwargs = {'url': args.url} if args.url else {}
    pdf_mod(pdf, args.name, bibtex=bib, delete_keys=args.keys, custom_pages=pages, **kwargs)


def pdf_page_sizes():
    """
    Args
        pdf     (str) valid pdf file
    """
    parser = argparse.ArgumentParser(description='Add metadata pdf')
    parser.add_argument('pdf', type=str, help='valid .pdf file')
    args = parser.parse_args()
    pdf = _resolve_pdf(args.pdf)
    get_page_sizes(pdf, verbose=True)

def pdf_metadata():
    """ add metadata to pdf
    Args
        pdf     (str) valid pdf file
    optional
        bib     (str) .bib: if ommited will use same name as pdf  <pdf>.replace('.pdf', '.bib')
        -a --author     (str | list)    e.g -a "Al Keinstein" "Neel Boor"
        -k --keys       (str | list) metadata keys to be deleted
        -n --name       (str) rename pdf: default overwrites
        -p --pages      (int | list | str) keep pages e.g. -p 5 7 11 | -p -4 | -p 13-17 
        -t --title      (str)
        -u --url        (str)
        -y --year       (int)
        -s --size       (list | str) resize pages e.g. -s 443 678 | -s common | -s mean | -s A4 
    """
    parser = argparse.ArgumentParser(description='Add metadata pdf')
    parser.add_argument('pdf', type=str, help='valid .pdf file')
    parser.add_argument('bib', type=str, nargs='?', help='valid .bib file', default=None)
    parser.add_argument('-a', '--author', type=str, nargs='+', help='add authtors', default=None)
    parser.add_argument('-b')
    parser.add_argument('-k', '--keys', nargs='+', default=None, help="delete keys")
    parser.add_argument('-n', '--name', type=str, help='create new file with name -n', default=None)
    parser.add_argument('-p', '--pages', nargs='+', default=None,
                        help='page: eg. 2, pages: eg. 1 2 3 or pagerange: eg. 1- or 1-4')
    parser.add_argument('-t', '--title', type=str, help='add title', default=None)
    parser.add_argument('-u', '--url', type=str, help='add url', default=None)
    parser.add_argument('-y', '--year', type=int, help='add year', default=None)
    parser.add_argument('-s', '--size', nargs='+', default=None,
                        help='resize pages to tuple | presets | most common size | mean size \
                            eg. 412 612 | A4 | common | mean')

    args = parser.parse_args()
    pdf = _resolve_pdf(args.pdf)
    bib = _get_bib_file(pdf, args.bib)
    pages = _parse_pages(args.pages)
    size = _parse_size(args.size)
    _pages = pages or 0
    kwargs = {'url': args.url} if args.url else {}

    if any((_pages, args.keys, args.title, args.pages, args.author, args.year, bib, args.size,
            kwargs)):
        pdf_mod(pdf, args.name, bibtex=bib, author=args.author, title=args.title,
                year=args.year, custom_pages=pages, delete_keys=args.keys, size=size, **kwargs)

def not_in_remarkable():
    """ outputs remote files in folder
    """
    parser = argparse.ArgumentParser(description='List Files in older not in remarkable tablet')
    parser.add_argument('folder', type=str, nargs='?', default='.', help='valid .pdf file')
    args = parser.parse_args()
    folder = osp.abspath(osp.expanduser(args.folder))
    files = [f.path for f in os.scandir(folder) if f.name.endswith('.pdf')]
    out = get_remote_files(files)
    print(f"files not uploaded: {[osp.basename(o) for o in out['nonexist']]}")

def remarkable_ls():
    """console entry point to print remarkable file graph from local backup
    Args
        folder  (str) remarkable folder backup, empty for current or ? for recursive search
            a 'xochitl' folder needs to exist 
    """
    parser = argparse.ArgumentParser(description='print remrkable file graph from backup')
    parser.add_argument('folder', type=str, nargs='?', default=None,
                        help='folder with remarkable backup, if ? searches for previous backups')
    parser.add_argument('-d', '--dir_type', action='store_true',
                        help='only list folders')
    args = parser.parse_args()
    graph = build_file_graph(args.folder, args.dir_type)
    if graph is None:
        help(remarkable_ls)
    else:
        pprint.pprint(graph)


def remarkable_restart():
    """ restart remarkable service
    """
    restart_xochitl()


def remarkable_export_annotated():
    """ console entry point merging pdf and rmscene
    Args
        file     (str) uuid in xochitl or visibleName - exported to local backup
        pages    (int, tuple [None]) None export all
        folder   (str ['.']) output folder
        out_name (str [None]) if None -> visible_name.replace(" ", "_")+".pdf"
        xochitl  (str [None]) if None, reads ~/.xochitl for local bakcupd folder
    """
    parser = argparse.ArgumentParser(description='PDF merged with annotations')
    parser.add_argument('file', type=str,
                        help='uuid in xochitl or visibleName, exported to local backup')
    parser.add_argument('page', type=int, nargs='?', default=None,
                        help='export only page number')
    parser.add_argument('folder', type=str, nargs='?', default='.',
                        help='folder of merged pdf')
    parser.add_argument('out_name', type=str, nargs='?', default=None,
                        help='name of merged pdf, default: visible_name + "_annotated.pdf"')
    parser.add_argument('xochitl', type=str, nargs='?', default=None,
                        help='xochitl directory if None reads from ~/.xochitl')
    args = parser.parse_args()
    page = True if args.page is None else page
    export_annotated_pdf(args.file, page, args.folder, args.out_name, args.xochitl)


def remarkable_read_rm():
    """console entry point to read rm files v.6"""
    parser = argparse.ArgumentParser(prog="rmscene")
    parser.add_argument("file", type=argparse.FileType("rb"), help="filename to read")
    args = parser.parse_args()

    result = rmscene.read_blocks(args.file)
    for el in result:
        print()
        pprint.pprint(el)


def remarkable_help():
    """console entry point for info"""
    ip = '10.11.99.1'
    if _is_host_reachable(ip, packets=1):
        _col = _G
        connected = f"{_G}IS"
    else:
        _col = _R
        connected = f"{_R}IS NOT"
    xochitl = _get_xochitl()
    if xochitl is not None:
        _col2 = _Y
        xochitl=f": {xochitl}"
        isstored=""
    else:
        _col2 = _R
        xochitl=""
        isstored="NOT "
    # backup folder NOT YET stored in ~/.xochitl

    _help = f"""{_Y}https://github.com/xvdp/unremarkable{_A}  access reMarkable without app.
    reMarkable {_col}{connected} connected {_A} through USB IP {_col}{ip}{_A}
    backup folder {_col}{isstored}found in ~/.xochitl {_G}{xochitl} {_A}
{_Y}!/bin/bash commands{_A}
    $ {_B}pdf_to_remarkable{_A} <pdf> [visible folder name] [-n, --name <file visible name>] [-r, --no_restart]
        {_G}# upload one pdf of all pdfs in a local folder to reMarkable{_A}
        Args        pdf     (str) valid pdf file or "*"
        Optional    parent  (str ['']) visible folder name in remarkable
        kwargs      --name -n (str [None]) visible name | default pdfbasename.replace("_"," ") 
                    --no_restart -r   NO ARGS  | default restart xochitl to refresh UI
    $ {_B}pdfmeta <pdf> [<bib> -a author list -k delete_keys -n rename -p keep_pages -t title -u url -y year]
        {_G}# add metadata to pdf{_A} bibtex optional
        Args        pdf     (str) pdf file
                    bib     (str) bibtex file, if omitted and .bib with same root name as pdf, adds to metadata
                        i assumes same name as pdf]
        -a --author     (str | list)    e.g -a "Al Keinstein" "Neel Boor"
        -k --keys       (str | list) metadata keys to be deleted
        -n --name       (str) rename pdf: default overwrites
        -p --pages      (int | list | str) keep pages e.g. -a 5 7 11 | -a -4 | -a 13-17 
        -t --title      (str)
        -u --url        (str)
        -y --year       (int)
        -s --size       (str | list) resize pages to -s int int | -s A4 | -s mean | -s common
    $ {_B}pdfsizes <pdf> {_G}# print page sizes of pdf{_A}#
    $ {_B}remarkable_restart  {_G}# restart xochitl service to view upload changes{_A}   
    $ {_B}remarkable_backup {_A}[folder] # folder in (existing_dir, ? )
        {_G}# back up reMarkable local,  folder name stored to ~/.xochitl file{_A}
        # if no folder passed: 1. reads '~/.xochitl' 2: searches for 'xochitl/' under curred pwd
    {_Y}from remarkable backup{_A}
    $ {_B}remarkable_ls{_A} <local folder> [-d, --dir_type]
        {_G}# list folder and file (names, uuid) on reMarkable BACKUP{_A}
        Args        folder (str)   if no dir: 1. cat '~/.xochitl' 2: find . -type d -name 'xochitl/'
        Optional    --dir_type -d   NO ARGS  list folders only | deault folders and files
    $ {_B}remarkable_export_annotated{_A} <filename> [page] [folder] [name] [xochitl]
        {_G}# export annotated pdf from reMarkable BACKUP; only version 6 .rm; lines, no text/ WIP{_A}
        Args        filename    uuid or suficiently unique partial visible name
        Optional    page        int,tuple selected page or pages only | default all
                    folder      local folder | default current
                    name        output name | default visibleName
                    xochitl     backup folder | default cat ~/.xochitl
{_Y}python{_A}
    {_M}>>> {_B}from unremarkable import remarkable_name, get_annotated{_A}
    {_M}>>> {_B}remarkable_name({_A}<partial visbilbe name or uuid>{_B}){_A} -> tuple(uuid, visible name)
        {_G}# return (uuid, visible name) from uuid or sufficiently unique partial name, from reMarkable BACKUP e.g.{_A}
    {_M}>>> {_B}files = get_annotated(){_A} -> dict('annotated':[], 'old':[])
    >>> pprint.pprint(files['annotated'])

    """
    print (_help)

# {_M}>>> {_B}add_authors({_A}filename, authors, title=None, year=None, override=False, upload=True, restart=True{_B}){_A}
#     {_G}# add author names to reMarkable BACKUP .content, then upload to tablet, tablet file must be closed{_A}
# {_M}>>> {_B}add_pdf_metadata({_A}filename, author=None, title=None, year=None, subject=None, delete_keys=(), suffix=False, custom_pages=None, bibtex=None, **kwargs{_B}){_A} 
#     {_G}# add metadata keys (author, title, year, subject, **kwargs), delete keys, add suffix, export custom page tuple/ range to LOCAL PDF{_A}
#     {_G}# arg bibtex can pass a .bib file name or a string containing bibtex formated info{_A}