"""
console entry points for unremarkable handling of reMarkable files

"""
import argparse
import os.path as osp
import pprint

from .unremarkable import backup_tablet, upload_pdf, build_file_graph, get_pdf_info, \
    _is_host_reachable
from .rm_to_pdf import export_merged_pdf
from . import rmscene

_A="\033[0m"
_G="\033[34m"
_R="\033[31m"
_B="\033[36m"
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
                        help='backup folder, ? recursive search, None use saved in ~/.xochitl or "."')
    args = parser.parse_args()
    backup_tablet(args.folder)

def pdf_to_remarkable():
    """console entry point upload pdf to remarkable
    Args
        pdf     (str) valid pdf file or *
        parent  (str ['']) destination folder visible name
        --name  (str [None]) visible name, if None: pdfbasename.replace("_"," ")  
        --no_restart      default restarts xochitl service to show upload, disable
    """
    parser = argparse.ArgumentParser(description='Upload pdf')
    parser.add_argument('pdf', type=str, help='valid .pdf file or *')
    parser.add_argument('parent', type=str, nargs='?', default='',
                        help='destination folder visible name')
    parser.add_argument('-n', '--name', type=str, default=None,
                        help='visible name; default is pdf basename without ext replacing "_"," "')
    parser.add_argument('-r', '--no_restart', action='store_false', dest='restart',
                        help='disable restart of xochitl service')
    # Parse arguments
    args = parser.parse_args()
    upload_pdf(args.pdf, args.parent, args.name, args.restart)

def remarkable_ls():
    """console entry point to print remarkable file graph from local backup
    Args
        folder  (str) remarkable folder backup, empty for current or ? for recursive search
            a 'xochitl' folder needs to exist 
    """
    parser = argparse.ArgumentParser(description='print remrkable file graph from backup')
    parser.add_argument('folder', type=str, nargs='?', default='.',
                        help='folder with remarkable backup, if ? searches for previous backups')
    parser.add_argument('-d', '--dir_type', action='store_true',
                        help='only list folders')
    args = parser.parse_args()
    graph = build_file_graph(args.folder, args.dir_type)
    if graph is None:
        help(remarkable_ls)
    else:
        pprint.pprint(graph)


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
    export_merged_pdf(args.file, args.page, args.folder, args.out_name, args.xochitl)


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
    _help = f""" unremarkable console functions to access reMarkable tablet without app.
    reMarkable tablet {_col}{connected} connected {_A} through USB IP {ip}.

    Console Functions
        $ {_B}remarkable_backup {_A}<folder> # folder in (existing dir, ?, )
            back up contents of reMarkable xochitl folder to local machine
         Args
            if no folder entry uses local folder 
            if  ? it searches folder hierarchy for 'xochitl' folder and backs up there if found

        $ {_B}pdf_to_remarkable{_A} <pdf> [<parent folder name>] [--name <file visible name>] [--no_restart]
            uploads one pdf of all pdfs in a local folder to reMarkable
         Args
            pdf     (str) valid pdf file or *
            parent  (str ['']) destination folder visible name
         kwargs
            --name -n (str [None]) visible name, if None: pdfbasename.replace("_"," ") 
         switches
            --no_restart -r     default restarts xochitl to refresh UI

        $ {_B}remarkable_ls{_A} <local folder> [--dir_type]
            lists folders and files paired to their uuid names on LOCAL backup
         Args
            folder  (str)   in (existing dir, ?, )
                if no folder entry uses local folder 
                if  ? it searches folder hierarchy for 'xochitl' folder and backs up there if found
         switches
            --dir_type -d   list only folders

        $ {_B}pdf_info{_A} <local pdf file> [<page number>]
            returns number of pages, width, height of a pdf in a LOCAL folder

        $ {_B}remarkable_export_annotated{_A} <filename> [page] [folder] [name] [xochitl]
            export annotaed pdf

        $ {_B}remarkable_read_rm{_A} <file.rm>
            reads and prints rm file
            - forwarding of github.com/ficklupton/rmscene.__main__ 
    """
    print (_help)
