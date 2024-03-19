"""

"""
from tempfile import mkdtemp #, mkstemp
import os.path as osp
from ..unremarkable import  _get_xochitl, _set_xochitl



def test_set_get_xochitl():
    # test exsiting xochitl
    xochitl = _get_xochitl()

    # set get temp xochitl
    _xochitl = mkdtemp()
    _root = mkdtemp()
    _set_xochitl(_xochitl, root=_root)
    assert osp.isfile(osp.join(_root, ".xochitl"))

    _txochitl = _get_xochitl(root=_root)
    assert _txochitl == _xochitl

    if xochitl is not None:
        assert _xochitl != xochitl
