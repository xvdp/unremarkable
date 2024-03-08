"""
rmscene library from https://github.com/ricklupton/rmscene/
modified for python >=3.6,<3.10

adapted from https://github.com/chemag/rmscene
v6 .rm format compatible with python 3.9

using svgcairo instead of inkscape to map to pdf
"""
from .remarkable_rm_to_svg import remarkable_rm_to_svg, remarkable_rm_to_pdf
from .tagged_block_common import *
from .tagged_block_reader import *
from .tagged_block_writer import *
from .scene_stream import *
