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
from .pdf import pdf_mod
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


def _asint(val:Any, msg: str = "") -> int:
    assert val.isnumeric(), f"expected integer input, got {val}, {msg}"
    return int(val)


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


def pdf_bibtex():
    """ entry point to add bibtex to pdf
    Args
        pdf     (str) valid pdf file
    optional
        bib     (str) valid bib file - if None looks for pdf.replace('.pdf', '.bib')
        --name  (str) <filename>.pdf, default overwrites
        --pages (int, list, str) str: 1- slice(1,None)
        --keys  (str, list) # delete keys
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
    _pdf, ext = osp.splitext(args.pdf)
    if not osp.isfile(args.pdf) and ext.lower() != '.pdf':
        ext = '.pdf'
    pdf = f'{_pdf}{ext}'
    assert osp.isfile(pdf), f"pdf file not found {pdf}"

    bib = args.bib
    if bib is None or not osp.isfile(bib):
        _bib = f'{_pdf}.bib'
        __bib = ".".join([osp.dirname(_bib), osp.basename(_bib)])
        if osp.isfile(_bib):
            os.rename(_bib, __bib)
        bib = __bib if osp.isfile(__bib) else None
    assert osp.isfile(bib), f"bib file not found {args.bib}, use pdf_metadata for custom keys"

    pages = _parse_pages(args.pages)
    kwargs = {'url': args.url} if args.url else {}
    pdf_mod(pdf, args.name, bibtex=bib, delete_keys=args.keys, custom_pages=pages, **kwargs)


def pdf_metadata():
    """ add metadata to pdf : similar to pdf_bibtex without bibtex, useful shortcut for adding url
    Args
        pdf     (str) valid pdf file
    optional
        --name      (str) <filename>.pdf, default overwrites
        --author    (str)
        --year      (int)
        --title     (str) 
        --url       (str)
        --pages (int, list, str) str: 1- slice(1,None)
        --keys  (str, list) # delete keys
        renames  filename.bib to .filename.bib
    """
    parser = argparse.ArgumentParser(description='Add metadata pdf')
    parser.add_argument('pdf', type=str, help='valid .pdf file')
    parser.add_argument('-n', '--name', type=str, help='create new file with name -n', default=None)
    parser.add_argument('-a', '--author', type=str, nargs='+', help='add authtors', default=None)
    parser.add_argument('-y', '--year', type=int, help='add year', default=None)
    parser.add_argument('-t', '--title', type=str, help='add title', default=None)
    parser.add_argument('-u', '--url', type=str, help='add url', default=None)
    parser.add_argument('-p', '--pages', nargs='+', default=None,
        help='page: eg. 2, pages: eg. 1 2 3 or pagerange: eg. 1- or 1-4')
    parser.add_argument('-k', '--keys', nargs='+', default=None, help="delete keys")
    args = parser.parse_args()
    pages = _parse_pages(args.pages)
    _pages = pages or 0
    kwargs = {'url': args.url} if args.url else {}
    if any((_pages, args.keys, args.title, args.title, args.author, args.year, kwargs)):
        pdf_mod(args.pdf, args.name, author=args.author, title=args.title, year=args.year,
                        custom_pages=pages, delete_keys=args.keys, **kwargs)

        # add_pdf_metadata(args.pdf, author=args.author, title=args.title, year=args.year,
        #                 custom_pages=args.pages, delete_keys=args.keys, **kwargs)

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
{_Y}Console{_A}
    $ {_B}pdf_to_remarkable{_A} <pdf> [visible folder name] [-n, --name <file visible name>] [-r, --no_restart]
        {_G}# upload one pdf of all pdfs in a local folder to reMarkable{_A}
        Args        pdf     (str) valid pdf file or "*"
        Optional    parent  (str ['']) visible folder name in remarkable
        kwargs      --name -n (str [None]) visible name | default pdfbasename.replace("_"," ") 
                    --no_restart -r   NO ARGS  | default restart xochitl to refresh UI
    $ {_B}pdf_bibtex  <pdf> <bib> [-p, --pages ]
        {_G}# add bibtex to pdf{_A} 
        Args    pdf     (str) pdf file
                bib     (str) text bibtex file
        kwargs  --pages -p  (list, int, range as str) 2 | 1 2 3 | 1- | 1-4' 
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
{_Y}Python{_A}
    {_M}>>> {_B}from unremarkable import remarkable_name, add_authors, add_pdf_metadata, get_annotated{_A}
    {_M}>>> {_B}remarkable_name({_A}<partial visbilbe name or uuid>{_B}){_A} -> tuple(uuid, visible name)
        {_G}# return (uuid, visible name) from uuid or sufficiently unique partial name, from reMarkable BACKUP e.g.{_A}
    {_M}>>> {_B}add_authors({_A}filename, authors, title=None, year=None, override=False, upload=True, restart=True{_B}){_A} 
        {_G}# add author names to reMarkable BACKUP .content, then upload to tablet, tablet file must be closed{_A}
    {_M}>>> {_B}add_pdf_metadata({_A}filename, author=None, title=None, year=None, subject=None, delete_keys=(), suffix=False, custom_pages=None, bibtex=None, **kwargs{_B}){_A} 
        {_G}# add metadata keys (author, title, year, subject, **kwargs), delete keys, add suffix, export custom page tuple/ range to LOCAL PDF{_A}
        {_G}# arg bibtex can pass a .bib file name or a string containing bibtex formated info{_A}
    {_M}>>> {_B}files = get_annotated(){_A} -> dict('annotated':[], 'old':[])
        {_G}# files with annotations on reMarkable BACKUP,  'old' are files without zoomMode - are they v5? WIP.{_A}
    >>> pprint.pprint(files['annotated'])"""
    print (_help)
