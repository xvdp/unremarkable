"""Convert blocks to svg file.

Code originally from https://github.com/lschwetlick/maxio through
https://github.com/chemag/maxio

@xvdp:  modified
- remove requirement for python 3.10, dataclasses keyword only argument
- to use cairosvg instead of inkscape which fails
TODO: page size and stroke scale is still a bit wonky, must be debugged
TODO: every thickness needs to be converted by the svg output size to the pdf parent size to 
TODO: .content contains custom zoom information
"""
from typing import Optional, Union
import io
import os.path as osp
import logging
import math
import string
from dataclasses import dataclass

import cairosvg

from .scene_stream import (
    read_blocks,
    RootTextBlock,
    SceneTreeBlock,
    TreeNodeBlock,
    SceneGroupItemBlock,
    SceneLineItemBlock,
)

from .writing_tools import Pen

_logger = logging.getLogger(__name__)

# UNCOMMENT GLOBALS TO DEBUG svg scaling
# _X = []
# _Y = []
# _XA = []
# _YA = []

# reMarkable2 screen size
SCREEN_WIDTH = 1404
SCREEN_HEIGHT = 1872

SVG_HEADER = string.Template(
    """
<svg xmlns="http://www.w3.org/2000/svg" width="$width" height="$height">
    <script type="application/ecmascript"> <![CDATA[
        var visiblePage = 'p1';
        function goToPage(page) {
            document.getElementById(visiblePage).setAttribute('style', 'display: none');
            document.getElementById(page).setAttribute('style', 'display: inline');
            visiblePage = page;
        }
    ]]>
    </script>
"""
)



@dataclass
class PageInfo:
    tnb_dict: dict
    stb_tree: dict
    sgib_tree: dict
    height: int
    width: int
    xpos_delta: float
    ypos_delta: float

    def __init__(self):
        self.tnb_dict = {}
        self.stb_tree = {}
        self.sgib_tree = {}
        self.height = 0
        self.width = 0
        self.xpos_delta = 0
        self.ypos_delta = 0


def remarkable_rm_to_pdf(infile: str,
                         outfile: Optional[str] = None,
                         width: Optional[int] = None,
                         height: Optional[int] = None,
                         **kwargs) -> str:
    """
    TODO: overlay is still a bit wonky
    """
    assert osp.splitext(infile)[-1] in (".svg", ".rm"), f"expected .rm/ .svg file got {infile}"
    b_svg, page_width, page_height = remarkable_rm_to_svg(infile, **kwargs)

    # print(f"svg width {page_width}, svg height {page_height}")
    # TODO consider, height, width and content information
    # something still wonky here
    print(f"to pdf: height {height} {page_height}")
    print(f"to pdf: width  {width} {page_width}")
    scale = 1. if height is None else min(height/page_height, width/page_width)
    scale *= kwargs.get('annotation_scale', 1.) # pass fudge factor

    cairosvg.svg2pdf(b_svg, write_to=outfile, dpi=72, scale=scale)
    return page_width, page_height


def remarkable_rm_to_blocks(infile):
    """ parse the lines (.rm) input file into a series of blocks
    """
    with open(infile, "rb") as infh:
        infile_datastream = io.BufferedReader(infh)
        # we need to process the blocks twice to understand the dimensions, so
        # let's put the iterable into a list
        return list(read_blocks(infile_datastream))


def remarkable_rm_to_svg(infile,
                         outfile: Optional[str] = None,
                         debug=0,
                         **kwargs) -> Union[str, bytes]:
    """ def read .rm file write to svg string of file
    Args
        infile      (str) valid remarkable .rm file v 6
        outfile     (str [None]) if None output bytestring
        debug       (int [0])
    kwargs
        thick       (float >0) modulate thickness of strokes on export
    """
    blocks = remarkable_rm_to_blocks(infile)
    page_info = get_page_info(blocks, debug)
    print(f"page_info.height {page_info.height}")
    print(f"page_info.width {page_info.width}")
    print(f"page_info.xpos_delta {page_info.xpos_delta}")
    print(f"page_info.ypos_delta {page_info.ypos_delta}")
    _b = 4*" " # tab

    # global _X
    # global _Y
    # global _XA
    # global _YA
    # _X = []
    # _Y = []
    # _XA = []
    # _YA = []
    out = [SVG_HEADER.substitute(width=page_info.width, height=page_info.height)]
    out += [f'{_b}<g id="p1" style="display:inline">']
    out += [f'{2*_b}<filter id="blurMe"><feGaussianBlur in="SourceGraphic" stdDeviation="10" /></filter>']

    for block in blocks:
        if isinstance(block, SceneLineItemBlock):
            out += _block_to_stroke_list(block, page_info, debug, **kwargs) #, **kwargs
        elif isinstance(block, RootTextBlock):
            out +=_block_to_text(block, page_info, debug)
            # print(f"  > Block: {block.__class__}")
        # else:
            # print(f"    Unexported Block: {block.__class__}")

    # Overlay the page with a clickable rect to flip pages
    out += [""]
    out += [f"{2*_b}<!-- clickable rect to flip pages -->"]
    out += [f'{2*_b}<rect x="0" y="0" width="{page_info.width}" height="{page_info.height}" fill-opacity="0"/>']

    out += [f"{_b}</g>"]
    out += ["</svg>"]
    out = "\n".join(out)

    if outfile is not None:
        if outfile[-4:] != ".svg":
            outfile += ".svg"
        with open(outfile, "w", encoding='utf8') as fi:
            fi.write(out)
    out = out.encode()

    # print(f"x minmax: {np.min(_X)} {np.max(_X)}")
    # print(f"y minmax: {np.min(_Y)} {np.max(_Y)}")
    # print(f"x aligned minmax: {np.min(_XA)} {np.max(_XA)}")
    # print(f"y aligned minmax: {np.min(_YA)} {np.max(_YA)}")

    return out, page_info.width, page_info.height


def _block_to_stroke_list(block, page_info, debug, **kwargs) -> list:
    """ svg as str insted of directly to file: draw_slib()
    kwargs:
        thick   float, modulate thickness on export
    """
    # global _X
    # global _Y
    # global _XA
    # global _YA
    bid = block.item_id
    _b = 8*' '
    out = [f"{_b}<!-- SceneLineItemBlock item_id: {bid} -->"]

    thick = kwargs.get('thick', 1.)

    if block.value is not None:
        # print(f"    block value{block.value}")
        bval = block.value
        bthick, btool, bcolor = bval.thickness_scale*thick, bval.tool, bval.color
        pen = Pen.create(btool.value, bcolor.value, bthick)
        pcolor, pwidth, popacity = pen.stroke_color, pen.stroke_width, pen.stroke_opacity

        out += [f"{_b}<!-- Stroke tool: item_id: {bid} {btool.name} color: {bcolor.name} thickness_scale: {bthick} -->"]
        pline = f"{_b}<polyline "
        pline += f'style="fill:none;stroke:{pcolor};stroke-width:{pwidth};opacity:{popacity}" '
        pline += f'stroke-linecap="{pen.stroke_linecap}" '
        pline += 'points="'

        # get the block alignment
        align = _get_block_alignemnt(block, page_info, debug)
        for point_id, point in enumerate(bval.points):
            # _X.append(point.x)
            # _Y.append(point.y)
            xpos = point.x + align['xdel']
            ypos = point.y + align['ydel']
            # _XA.append(xpos)
            # _YA.append(ypos)
            _pt = (point.speed, point.direction, point.width, point.pressure, align['wlast'])

            if point_id % pen.segment_length == 0:
                pscolor = pen.get_segment_color(*_pt)
                pswidth = pen.get_segment_width(*_pt)
                psopacity = pen.get_segment_opacity(*_pt)

                # UPDATE stroke
                pline +='"/>'
                out += [pline]

                pline = f"{_b}<polyline "
                pline += f'style="fill:none; stroke:{pscolor} ;stroke-width:{pswidth:.3f};opacity:{psopacity}" '
                pline += 'points="'
                if align['xlast'] != -1.0:
                    pline += f"{align['xlast']:.3f},{align['ylast']:.3f} "
            # store the last position
            align['xlast'] = xpos
            align['ylast'] = ypos
            align['wlast'] = pswidth

            # BEGIN and END polyline segment
            pline += f"{xpos:.3f},{ypos:.3f} "
        pline +='"/>'
        out += [pline]

    return out

def _get_block_alignemnt(block, page_info, debug):
    xpos_delta, ypos_delta = get_slib_anchor_info(block, page_info, debug)
    xpos_delta += page_info.xpos_delta
    ypos_delta += page_info.ypos_delta
    return {'xdel': xpos_delta, 'ydel': ypos_delta, 'xlast':-1.0, 'ylast': -1.0, 'wlast': 0}


def _block_to_text(block, page_info, debug):
    """ Text block """
    bid = block.block_id
    _b = 4*' '
    out = []

    if debug > 1:
        print(f"----RootTextBlock item_id: {bid}")
    out += [f"{2*_b}<!-- RootTextBlock item_id: {bid} -->"]

    # add some style to get readable text
    text_size = 50
    out += [f"{2*_b}<style>"]
    out += [3*_b+".default {"]
    out += [f"{4*_b}font: {text_size}px serif"]
    out += [3*_b+"}"]
    out += [f"{2*_b}</style>"]

    xpos = block.pos_x + page_info.xpos_delta
    ypos = block.pos_y + page_info.ypos_delta
    for text_item in block.text_items:
        out += [f"{2*_b}<!-- TextItem item_id: {text_item.item_id} -->"]
        if text_item.text.strip():
            out += [f'{2*_b}<text x="{xpos}" y="{ypos}" class="default">{text_item.text.strip()}</text>']
        ypos += text_size * 1.5
    return out


def get_limits(blocks, page_info, debug):
    xmin = xmax = None
    ymin = ymax = None
    for block in blocks:
        if debug > 1:
            print(f"-- block: {block}\n")
        # 1. parse block
        if isinstance(block, SceneLineItemBlock):
            xmin_tmp, xmax_tmp, ymin_tmp, ymax_tmp = get_limits_slib(
                block, page_info, debug
            )
            if debug > 0:
                print(f"-- SceneLineItemBlock item_id: {block.item_id} xmin: {xmin_tmp} xmax: {xmax_tmp} ymin: {ymin_tmp} ymax: {ymax_tmp}")
        # text blocks use a different xpos/ypos coordinate system
        # elif isinstance(block, RootTextBlock):
        #    xmin_tmp, xmax_tmp, ymin_tmp, ymax_tmp = get_limits_rtb(block, page_info, debug)
        else:
            continue
        # 2. update bounds
        if xmin_tmp is None:
            continue
        xmin = xmin_tmp if (xmin is None or xmin > xmin_tmp) else xmin
        xmax = xmax_tmp if (xmax is None or xmax < xmax_tmp) else xmax
        ymin = ymin_tmp if (ymin is None or ymin > ymin_tmp) else ymin
        ymax = ymax_tmp if (ymax is None or ymax < ymax_tmp) else ymax
        if debug > 1:
            print(
                f"-- block: {type(block)} xmin: {xmin} xmax: {xmax} ymin: {ymin} ymax: {ymax}"
            )
    return xmin, xmax, ymin, ymax


def get_slib_anchor_info(block, page_info, debug):
    tnb_id = block.parent_id.part2
    xpos_delta = 0
    ypos_delta = 0
    while tnb_id != 1:
        if (
            page_info.tnb_dict[tnb_id].anchor_type is not None
            and page_info.tnb_dict[tnb_id].anchor_type.value == 2
        ):
            xpos_delta += page_info.tnb_dict[tnb_id].anchor_origin_x.value
        # move to the parent TNB
        tnb_id = page_info.stb_tree[tnb_id]
    return xpos_delta, ypos_delta


def get_limits_slib(block, page_info, debug):
    # make sure the object is not empty
    if block.value is None:
        return None, None, None, None
    xmin = xmax = None
    ymin = ymax = None
    # get the anchor information
    xpos_delta, ypos_delta = get_slib_anchor_info(block, page_info, debug)
    for point in block.value.points:
        xpos, ypos = point.x, point.y
        if xmin is None or xmin > xpos:
            xmin = xpos
        if xmax is None or xmax < xpos:
            xmax = xpos
        if ymin is None or ymin > ypos:
            ymin = ypos
        if ymax is None or ymax < ypos:
            ymax = ypos
    xmin += xpos_delta
    xmax += xpos_delta
    ymin += ypos_delta
    ymax += ypos_delta
    return xmin, xmax, ymin, ymax


def get_limits_rtb(block, page_info, debug):
    xmin = block.pos_x
    xmax = block.pos_x + block.width
    ymin = block.pos_y
    ymax = block.pos_y
    return xmin, xmax, ymin, ymax


def get_dimensions(blocks, page_info, debug):
    # get block limits
    xmin, xmax, ymin, ymax = get_limits(blocks, page_info, debug)
    #if debug > 2:
    print(f"-- limits: xmin: {xmin} xmax: {xmax} ymin: {ymin} ymax: {ymax}")
    # {xpos,ypos} coordinates are based on the top-center point
    # of the doc **iff there are no text boxes**. When you add
    # text boxes, the xpos/ypos values change.

    xpos_shift = SCREEN_WIDTH / 2

    xpos_delta = xpos_shift
    if xmin is not None and (xmin + xpos_shift) < 0:
        # make sure there are no negative xpos
        xpos_delta += -(xmin + xpos_shift)
    ypos_delta = 0
    if ymin is not None and ymin < 0:
        ypos_delta = -1. * ymin
        print(f"negative ypos found: shifting ypos_delta: {ypos_delta}")


    width = int(
        math.ceil(
            max(
                SCREEN_WIDTH,
                xmax - xmin if xmin is not None and xmax is not None else 0,
            )
        )
    )
    height = int(
        math.ceil(
            max(
                SCREEN_HEIGHT,
                ymax - ymin if ymin is not None and ymax is not None else 0,
            )
        )
    )

    if debug > 0:
        print(
            f"height: {height} width: {width} xpos_delta: {xpos_delta} ypos_delta: {ypos_delta}"
        )
    return height, width, xpos_delta, ypos_delta


# only use case for the TNB tree is going from leaf to root, so we can
# just do with the child->parent tuples. For efficiency, we keep the latter
# in a dictionary.
# Note that both the STB and the SGIB objects seem to do the same mappings.
# We will keep both.
def get_page_info(blocks, debug):
    page_info = PageInfo()
    # parse the TNB/STB/SGIB blocks to get the page tree
    for block in blocks:
        if isinstance(block, TreeNodeBlock):
            page_info.tnb_dict[block.node_id.part2] = block
        elif isinstance(block, SceneTreeBlock):
            page_info.stb_tree[block.tree_id.part2] = block.parent_id.part2
        elif isinstance(block, SceneGroupItemBlock):
            page_info.sgib_tree[block.value.part2] = block.parent_id.part2
    # TODO(chema): check the stb_tree and sgib_tree are the same, otherwise
    # print a warning

    # get the dimensions
    (
        page_info.height,
        page_info.width,
        page_info.xpos_delta,
        page_info.ypos_delta,
    ) = get_dimensions(blocks, page_info, debug)

    return page_info
