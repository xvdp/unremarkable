"""
console entry points for unremarkable handling of reMarkable files

"""
import argparse
import os.path as osp
import pprint

from .unremarkable import backup_tablet, upload_pdf, build_file_graph, export_rm, get_pdf_info, \
    _is_uuid, export_merged_pdf, _is_host_reachable

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
    parser.add_argument('folder', type=str, nargs='?', default='.', help='parent of tablet backup')
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
    parser = argparse.ArgumentParser(description='print remrkable file graph')
    parser.add_argument('folder', type=str, nargs='?', default='.',
                        help='folder with remarkable backup')
    args = parser.parse_args()
    graph = build_file_graph(args.folder)
    if graph is None:
        help(remarkable_ls)
    else:
        pprint.pprint(graph)

def remarkable_export_rm():
    """console entry point to explort locally stored .rm file to pdf or sfg
    Args
        rm_file     (str) remarkable .rm version 6 file
        out         (str) name.pdf or name.sfg
        width       (float [None]) scale from screen size to width
        height      (float [None]) scale from screen size to height
        # TODO fix best fit on screen space
    Example
        $ remarkable_export_rm rmfilename.rm outfile(.svg or .pdf) [width] [height]
    """
    parser = argparse.ArgumentParser(description='rm to pdf converter')
    parser.add_argument('rm_file', type=str, help='v6 .remarkable file')
    parser.add_argument('out', type=str, help='out pdf/sfg')
    parser.add_argument('width', type=float, nargs='?', default=None,
                        help='export width, optional')
    parser.add_argument('height', type=float, nargs='?', default=None,
                        help='export height, optional')
    args = parser.parse_args()
    if not args.rm_file.endswith('.rm') or args.out.lower()[-4:] not in ('.svg', '.pdf'):
        help(remarkable_export_rm)
    else:
        export_rm(args.rm_file, args.out, args.width, args.height)

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
    """ console entry point merging pdf and annotations
    Args
        pdf     (str) pdf file from xochitl hierarchy with
            uuid.metadata, uuid.content & uuid/*.rm  exported to local backup
        folder  (str ['.']) output folder
        name    (str [None]) if None -> visible_name.replace(" ", "_")+".pdf"
        page    (int [None]) if None export all pages
        stroke_scale (float [0.6]) svg is improperly scaled atm, rescale
        annotation_scale (float [1.0]), theres still something wonky with the scaling of the svg
            pass extra scaling factor if needed
    """
    parser = argparse.ArgumentParser(description='perged pdf')
    parser.add_argument('pdf', type=str, help='pdf file from xochitl hierarchy')
    parser.add_argument('name', type=str, nargs='?', default=None,
                        help='name of merged pdf, default: visible_name + "_merged.pdf"')
    parser.add_argument('folder', type=str, nargs='?', default='.',
                        help='folder of merged pdf')
    parser.add_argument('page', type=int, nargs='?', default=None,
                        help='export only page number')
    parser.add_argument('stroke_scale', type=float, nargs='?', default=0.6,
                        help='scale strokes - something wonky in svg export widths ')
    parser.add_argument('annotation_scale', type=float, nargs='?', default=1.,
                        help='scale strokes - something wonky in svg export scale ')
    args = parser.parse_args()
    _uuid = _is_uuid(osp.splitext(osp.basename(args.pdf))[0])
    if (not osp.isfile(args.pdf) or not args.pdf.endswith('.pdf') or not _uuid):
        print(f"pass valid remarkable uuid.pdf file, got <{args.pdf}> \
              isfile: {osp.isfile(args.pdf)}, is_uuid {_uuid}")
        help(remarkable_export_annotated)
    else:
        export_merged_pdf(args.pdf, args.folder, args.name, args.page, args.stroke_scale,
                          args.annotation_scale)


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
            --name  (str [None]) visible name, if None: pdfbasename.replace("_"," ") 
         switches
            --no_restart      default restarts xochitl to refresh UI

        $ {_B}remarkable_ls{_A} <local folder>
            lists folders and files paired to their uuid names on LOCAL backup
         Args
            folder  (str)   in (existing dir, ?, )
                if no folder entry uses local folder 
                if  ? it searches folder hierarchy for 'xochitl' folder and backs up there if found

        $ {_B}pdf_info{_A} <local pdf file> [<page number>]
            returns number of pages, width, height of a pdf in a LOCAL folder

        $ {_B}remarkable_export_annotated{_A} <uuid pdf> [name] [folder] [page] [stroke _scale] [annotation_scale]
            WIP: exports an annotated pdf passing the remarkable uuid name.
            TODO: fix scale issues
    """
    print (_help)
