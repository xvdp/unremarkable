""" python access to unremarkable functions
"""
from .unremarkable import upload_pdf, restart_xochitl
from .unremarkable import backup_tablet as remarkable_backup
from .unremarkable import build_file_graph as remarkable_ls
from .annotations import read_rm, export_annotated_pdf, get_annotated, add_authors, \
    remarkable_name
from .pdf import pdf_mod, get_pdfs
