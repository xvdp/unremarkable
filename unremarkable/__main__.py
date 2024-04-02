"""
console entry points for unremarkable handling of reMarkable files

"""
import argparse
import os.path as osp
import pprint

from .unremarkable import backup_tablet, upload_pdf, build_file_graph, get_pdf_info, \
    _is_host_reachable, _get_xochitl, restart_xochitl
from .annotations import export_annotated_pdf
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
    # Parse arguments
    args = parser.parse_args()
    upload_pdf(args.pdf, args.parent, args.name, args.restart_xochitl)

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

def pdf_info():
    """console entry point to return num pages, and dimensions of a local pdf
    Args
        pdf     (str) valid pdf file
        page     connected = connected ""
   (int [None]) if page, return width and height for page
    Example
        $ pdf_info mypdffile.pdf    # all page widths
            -> {'pages': num_pages, 'width': [widths], 'height': [heights]}
        $ pdf_info mypdffile.pdf 1 # width of page 1
            -> {'pages': num_pages, 'width': widths[1], 'height': heights[1]}
    """
    parser = argparse.ArgumentParser(description='pdf info utils')
    parser.add_argument('pdf', type=str, help='pdf file')
    parser.add_argument('page', type=int, nargs='?', default=None,
                        help='get dimension of a single page')
    args = parser.parse_args()
    if not osp.isfile(args.pdf) or not args.pdf.lower().endswith('.pdf'):
        print(f"pass valid .pdf file, got <{args.pdf}> isfile: {osp.isfile(args.pdf)}")
        help(pdf_info)
    else:
        print(get_pdf_info(args.pdf, args.page))

def remarkable_export_annotated():
    """ console entry point merging pdf and rmscene
    Args
        file     (str) uuid in xochitl or visibleName - exported to local backup
        page     (int, tuple [None]) None export all
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
        connected = "IS"
    else:
        _col = _R
        connected = "IS NOT"
    xochitl = _get_xochitl()
    if xochitl is not None:
        _col2 = _Y
        xochitl=f": {xochitl}"
        isstored=""
    else:
        _col2 = _R
        xochitl=""
        isstored=" NOT YET"

    _help = f""" unremarkable: accessreMarkable tablet without app.
    reMarkable tablet {_col}{connected} connected {_A} through USB IP {_col}{ip}{_A}.
    backup folder{_col2}{isstored} stored in ~/.xochitl{xochitl} {_A}

{_Y}Console Functions{_A}
    $ {_B}pdf_to_remarkable{_A} <pdf> [<parent folder name>] [--name <file visible name>] [--no_restart]
        {_G}# upload one pdf of all pdfs in a local folder to reMarkable{_A}
        Args
            pdf     (str) valid pdf file or *
            parent  (str ['']) destination folder visible name
        kwargs
            --name -n (str [None]) visible name, if None: pdfbasename.replace("_"," ") 
            --no_restart -r   NO ARGS  default restarts xochitl to refresh UI

    $ {_B}remarkable_restart  {_G}# restart xochitl service to view upload changes{_A}   

    $ {_B}remarkable_backup {_A}<folder> # folder in (existing dir, ?, )
        {_G}# back up reMarkable xochitl to local machine, stores backup folder name to ~/.xochitl file{_A}
        # if no folder passed: 1. reads '~/.xochitl' 2: searches for 'xochitl/' under curred pwd

    $ {_B}remarkable_ls{_A} <local folder> [--dir_type]
        {_G}# list folder and file (names, uuid) on reMarkable BACKUP{_A}
        # if no folder passed: 1. reads '~/.xochitl' 2: searches for 'xochitl/' under curred pwd
        Args
            folder  (str)   in (existing dir)  if no folder passed: 1. reads '~/.xochitl' 2: searches for 'xochitl/' under curred pwd
            --dir_type -d   NO ARGS  list folders only

    $ {_B}remarkable_export_annotated{_A} <filename> [page] [folder] [name] [xochitl]
        {_G}# export annotated pdf from reMarkable BACKUP; only version 6 .rm; lines, no text/ WIP{_A}

{_Y}Python{_A}
    {_M}>>> {_B}from unremarkable import remarkable_name, add_authors, add_pdf_metadata, get_annotated{_A}

    {_G}# resolve uuid and visible name from uuid or sufficiently unique partial name, from reMarkable BACKUP e.g.{_A}
    {_M}>>> {_B}remarkable_name({_A}"perturbation inactivation"{_B}){_A}
    [*] ('98934bc7-2278-4e43-b2ac-1b1675690074', 'Perturbation Inactivation Based Adversarial Defense')
        
    {_G}# add author names to reMarkable BACKUP .content, then upload to tablet, tablet file must be closed{_A}
    {_M}>>> {_B}add_authors({_A}filename, authors=('J. Doe', 'P. Ninestein'), year=2122, restart=True{_B}){_A} 
        
    {_G}# add author name and other metadata to a LOCAL PDF{_A}
    {_M}>>> {_B}add_pdf_metadata({_A}filename, author, title=None, year=None, subject=None, delete_keys=(), overwrite=True, **kwargs{_B}){_A} 

    {_G}# list annotated files on reMarkable BACKUP
    {_M}>>> files = {_B}get_annotated(){_A})
    {_A}>>> pprint.pprint(files['annotated']{_B} # files['old'] are files without zoomMode - are they v5? untested.
    """
    print (_help)
