# -*- coding: utf-8 -*-
#
#  Copyright (C) 2019 by Igor E. Novikov
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program.  If not, see <https://www.gnu.org/licenses/>.

import logging
import struct
import zlib
from cStringIO import StringIO

from uc2 import utils
from uc2.formats.cmx import cmx_const, cmx_instr

LOG = logging.getLogger(__name__)


class CmxRiffElement(cmx_instr.CmxObject):
    def __init__(self, config, chunk=None, **kwargs):
        self.config = config
        self.childs = []
        self.data = {}

        if chunk:
            self.chunk = chunk
            self.data['identifier'] = chunk[:4]
            if not self.is_leaf():
                self.data['name'] = chunk[8:12]
            self.update_from_chunk()
        else:
            self.data['identifier'] = cmx_const.LIST_ID
            self.set_defaults()

        if kwargs:
            self.data.update(kwargs)

    def update_from_kwargs(self, **kwargs):
        self.data.update(kwargs)
        self.update()

    def get(self, name, default=None):
        return self.data.get(name, default)

    def set(self, name, value):
        self.data[name] = value

    def is_leaf(self):
        return self.data['identifier'] not in cmx_const.LIST_IDS

    def get_name(self):
        return self.data.get('name', self.data['identifier'])

    def get_child_by_name(self, name):
        for item in self.childs:
            if item.get_name() == name:
                return item
        return None

    def get_chunk_offset(self):
        chunk = self
        offset = 0
        while not chunk.toplevel:
            childs = chunk.parent.childs
            index = childs.index(chunk)
            offset += sum([item.get_chunk_size() for item in childs[:index]])
            offset += len(chunk.parent.chunk)
            chunk = chunk.parent
        return offset

    def is_padding(self):
        sz = len(self.chunk)
        return sz > (sz // 2) * 2

    def update(self):
        size = self.get_chunk_size() - 8
        sz = utils.py_int2dword(size, self.config.rifx)
        self.chunk = self.data['identifier'] + sz + self.chunk[8:]
        if self.is_leaf() and self.is_padding():
            self.chunk += '\x00'

    def _get_icon(self):
        icon_map = {
            'ccmm': 'gtk-select-color',
            'DISP': 'gtk-missing-image',
            'page': 'gtk-page-setup',
            'pack': 'gtk-paste',
        }
        if self.is_leaf():
            return icon_map.get(self.data['identifier'], 'gtk-dnd')
        return False

    def resolve(self, name=''):
        sz = '%d' % self.get_chunk_size()
        name = '<%s>' % self.get_name()
        return self._get_icon(), name, sz

    def update_for_sword(self):
        self.cache_fields = [(0, 4, 'Chunk identifier'),
                             (4, 4, 'Chunk data size')]
        if not self.is_leaf():
            self.cache_fields += [(8, 4, 'List chunk name')]
        else:
            self.cache_fields[1] = (4, 4, 'Chunk data size\n')


class CmxList(CmxRiffElement):
    def __init__(self, config, chunk=None, **kwargs):
        CmxRiffElement.__init__(self, config, chunk, **kwargs)


class CmxInfoElement(CmxRiffElement):
    def __init__(self, config, chunk=None, **kwargs):
        CmxRiffElement.__init__(self, config, chunk, **kwargs)

    def set_defaults(self):
        self.data['identifier'] = cmx_const.IKEY_ID
        self.data['text'] = ''

    def update_from_chunk(self):
        self.data['text'] = self.chunk[8:].rstrip('\x00')

    def update(self):
        self.chunk = self.data['identifier'] + 4 * '\x00'
        self.chunk += self.data['text']
        text_sz = len(self.data['text'])
        padding = (text_sz // 32 + 1) * 32 - text_sz
        self.chunk += padding * '\x00'
        CmxRiffElement.update(self)

    def update_for_sword(self):
        CmxRiffElement.update_for_sword(self)
        sz = len(self.chunk) - 8
        idnt = self.data['identifier']
        msg = 'Notes' if idnt == cmx_const.ICMT_ID else 'Keys'
        self.cache_fields += [(8, sz, msg), ]


class CmxCont(CmxRiffElement):
    def set_defaults(self):
        self.data['identifier'] = cmx_const.CONT_ID
        self.data['file_id'] = cmx_const.CONT_FILE_ID
        self.data['os_type'] = cmx_const.CONT_OS_ID_WIN
        self.data['byte_order'] = cmx_const.CONT_BYTE_ORDER_LE
        self.data['coord_size'] = cmx_const.CONT_COORDSIZE_16BIT \
            if self.config.v16bit else cmx_const.CONT_COORDSIZE_32BIT
        self.data['major'] = cmx_const.CONT_MAJOR_V1 \
            if self.config.v1 else cmx_const.CONT_MAJOR_V2
        self.data['minor'] = cmx_const.CONT_MINOR
        self.data['unit'] = cmx_const.CONT_UNIT_MM
        self.data['factor'] = cmx_const.CONT_FACTOR_MM

        self.data['IndexSection'] = 4 * '\x00'
        self.data['InfoSection'] = 4 * '\x00'
        self.data['Thumbnail'] = 4 * '\x00'

        self.data['bbox_x0'] = 4 * '\x00'
        self.data['bbox_y1'] = 4 * '\x00'
        self.data['bbox_x1'] = 4 * '\x00'
        self.data['bbox_y0'] = 4 * '\x00'
        self.data['tally'] = 4 * '\x00'

    def update_from_chunk(self):
        self.data['file_id'] = self.chunk[8:40].rstrip('\x00')
        self.data['os_type'] = self.chunk[40:56].rstrip('\x00')
        self.data['byte_order'] = self.chunk[56:60]
        if self.data['byte_order'] == cmx_const.CONT_BYTE_ORDER_BE:
            self.config.rifx = True
        self.data['coord_size'] = self.chunk[60:62]
        if self.data['coord_size'] == cmx_const.CONT_COORDSIZE_16BIT:
            self.config.v16bit = True
        self.data['major'] = self.chunk[62:66]
        self.config.v1 = self.data['major'].startswith('\x31')
        self.data['minor'] = self.chunk[66:70]
        self.data['unit'] = self.chunk[70:72]
        self.data['factor'] = self.chunk[72:80]

        self.data['IndexSection'] = self.chunk[92:96]
        self.data['InfoSection'] = self.chunk[96:100]
        self.data['Thumbnail'] = self.chunk[100:104]

        self.data['bbox_x0'] = self.chunk[104:108]
        self.data['bbox_y1'] = self.chunk[108:112]
        self.data['bbox_x1'] = self.chunk[112:116]
        self.data['bbox_y0'] = self.chunk[116:120]
        self.data['tally'] = self.chunk[120:124]

    def update(self):
        self.chunk = self.data['identifier'] + 4 * '\x00'
        padding_sz = 32 - len(self.data['file_id'])
        self.chunk += self.data['file_id'] + padding_sz * '\x00'
        padding_sz = 16 - len(self.data['os_type'])
        self.chunk += self.data['os_type'] + padding_sz * '\x00'
        self.chunk += self.data['byte_order']
        self.chunk += self.data['coord_size']
        self.chunk += self.data['major']
        self.chunk += self.data['minor']
        self.chunk += self.data['unit']
        self.chunk += self.data['factor']
        self.chunk += 12 * '\x00'
        self.chunk += self.data['IndexSection']
        self.chunk += self.data['InfoSection']
        self.chunk += self.data['Thumbnail']

        self.chunk += self.data['bbox_x0']
        self.chunk += self.data['bbox_y1']
        self.chunk += self.data['bbox_x1']
        self.chunk += self.data['bbox_y0']
        self.chunk += self.data['tally']
        self.chunk += 64 * '\x00'
        CmxRiffElement.update(self)

    def update_for_sword(self):
        CmxRiffElement.update_for_sword(self)
        self.cache_fields += [
            (8, 32, 'file id'),
            (40, 16, 'OS type'),
            (56, 4, 'ByteOrder'),
            (60, 2, 'CoordSize'),
            (62, 4, 'Major'),
            (66, 4, 'Minor'),
            (70, 2, 'Unit'),
            (72, 8, 'Factor'),

            (80, 4, 'lOption (not used, zero)'),
            (84, 4, 'lForeignKey (not used, zero)'),
            (88, 4, 'lCapability (not used, zero)'),

            (92, 4, 'lIndexSection offset'),
            (96, 4, 'InfoSection offset'),
            (100, 4, 'lThumbnail offset'),

            (104, 4, 'lBBLeft - bbox x0'),
            (108, 4, 'lBBTop - bbox y1'),
            (112, 4, 'lBBRight - bbox x1'),
            (116, 4, 'lBBBottom - bbox y0'),
            (120, 4, 'lTally - instructions num'),

            (124, 64, 'Reserved - set to zero'),
        ]


class CmxCcmm(CmxRiffElement):
    def set_defaults(self):
        self.data['identifier'] = cmx_const.CCMM_ID
        self.data['dump'] = cmx_const.CCMM_DUMP

    def update_from_chunk(self):
        self.data['dump'] = self.chunk[8:]

    def update(self):
        self.chunk = self.data['identifier'] + 4 * '\x00'
        self.chunk += self.data['dump']
        CmxRiffElement.update(self)

    def update_for_sword(self):
        CmxRiffElement.update_for_sword(self)
        self.cache_fields += [
            (8, 4, 'lcsSignature'),
            (12, 4, 'lcsVersion'),
            (16, 4, 'lcsSize'),
            (20, 4, 'lcsCSType'),
            (24, 4, 'lcsIntent'),

            (28, 12, 'Red Endpoint'),
            (40, 12, 'Green Endpoint'),
            (52, 12, 'Blue Endpoint'),

            (64, 4, 'Red Gamma'),
            (68, 4, 'Green Gamma'),
            (72, 4, 'Blue Gamma'),

            (76, 4, 'ulRcsCompandType'),
        ]


class CmxDisp(CmxRiffElement):
    def __init__(self, config, chunk=None, **kwargs):
        CmxRiffElement.__init__(self, config, chunk, **kwargs)

    @staticmethod
    def make_chunk_from_bitmap(bitmap_str):
        chunk = cmx_const.DISP_ID + 4 * '\x00' + '\x08' + 3 * '\x00'
        chunk += utils.bmp_to_dib(bitmap_str)
        return chunk

    def update_for_sword(self):
        CmxRiffElement.update_for_sword(self)
        clr_table_sz = 4 * utils.dword2py_int(self.chunk[44:48],
                                              self.config.rifx)
        pos = 52 + clr_table_sz
        self.cache_fields += [
            (8, 4, 'dwClipboardFormat'),
            # BITMAPINFOHEADER
            (12, 4, 'biSize - header size'),
            (16, 4, 'biWidth - image width'),
            (20, 4, 'biHeight - image height'),
            (24, 2, 'biPlanes'),
            (26, 2, 'biBitCount'),
            (28, 4, 'biCompression'),
            (32, 4, 'biSizeImage'),
            (36, 4, 'biXPelsPerMeter'),
            (40, 4, 'biYPelsPerMeter'),
            (44, 4, 'biClrUsed'),
            (48, 4, 'biClrImportant'),
            # COLOR TABLE
            (52, clr_table_sz, 'Color Table'),
            # Pixels
            (pos, len(self.chunk) - pos, 'Pixels'),
        ]


class CmxPage(CmxRiffElement):
    def get_chunk_size(self):
        def _get_recursive_size(el):
            return sum([len(el.chunk)] +
                       [_get_recursive_size(item) for item in el.childs])

        return _get_recursive_size(self)

    def update_from_chunk(self):
        chunk = self.chunk[8:]
        pos = 0
        rifx = self.config.rifx
        parents = [self]
        while pos < len(chunk):
            size = utils.word2py_int(chunk[pos:pos + 2], rifx)
            instr_id = chunk[pos + 2:pos + 4]
            instr_id = abs(utils.signed_word2py_int(instr_id, rifx))
            instr = chunk[pos:pos + size]
            obj = cmx_instr.make_instruction(self.config, instr)
            name = cmx_const.INSTR_CODES.get(instr_id, '')
            if name.startswith('Begin'):
                parents[-1].add(obj)
                parents.append(obj)
            elif name.startswith('End'):
                parents = parents[:-1]
                parents[-1].add(obj)
            else:
                parents[-1].add(obj)
            pos += size
        self.chunk = self.chunk[:8]

    def set_defaults(self):
        self.data['identifier'] = cmx_const.PAGE_ID


class CdrxPack(CmxRiffElement):
    def update_from_chunk(self):
        chunk = zlib.decompress(self.chunk[20:])
        pos = 0
        parent = self
        while pos < len(chunk):
            identifier = chunk[pos:pos + 4]
            sz = chunk[pos + 4:pos + 8]
            if identifier in cmx_const.LIST_IDS:
                name = chunk[pos + 8:pos + 12]
                obj = make_cmx_chunk(self.config, identifier + sz + name)
                parent.add(obj)
                parent = obj
                pos += 12
                continue
            size = utils.dword2py_int(sz, self.config.rifx)
            size += 1 if size > (size // 2) * 2 else 0
            data = chunk[pos + 8:pos + 8 + size]
            parent.add(make_cmx_chunk(self.config, identifier + sz + data))
            pos += size + 8
        self.data['cpng'] = self.chunk[20:]
        self.data['cpng_flags'] = self.chunk[16:20]
        self.chunk = self.chunk[:20]

    def set_defaults(self):
        self.data['identifier'] = cmx_const.PAGE_ID
        self.data['cpng_flags'] = cmx_const.CPNG_FLAGS

    def update_for_sword(self):
        CmxRiffElement.update_for_sword(self)
        self.cache_fields += [
            (8, 4, 'Uncompressed size'),
            (12, 4, 'Compressed stream header'),
            (16, 4, 'Compression flags'),
        ]

    def get_chunk_size(self, recursive=True):
        if recursive:
            return sum([12] + [item.get_chunk_size() for item in self.childs])
        return 12

    def get_childs_size(self):
        return sum([item.get_chunk_size() for item in self.childs])

    def update_cpng(self):
        stream = StringIO()
        for child in self.childs:
            child.save(stream)
        self.data['cpng'] = zlib.compress(stream.getvalue())

    def update(self):
        size = self.get_childs_size()
        sz = utils.py_int2dword(size, self.config.rifx)
        self.update_cpng()
        compr_sz = len(self.data['cpng'])
        compr_sz += 1 if compr_sz > (compr_sz // 2) * 2 else 0
        compr_sz = utils.py_int2dword(compr_sz + 12, self.config.rifx)
        self.chunk = self.data['identifier'] + compr_sz + sz + \
                     cmx_const.CPNG_ID + self.data['cpng_flags']
        self.chunk += self.data['cpng']
        self.chunk += '\x00' if self.is_padding() else ''

    def save(self, saver):
        saver.write(self.chunk)


class CmxRlst(CmxRiffElement):
    def set_defaults(self):
        self.data['identifier'] = cmx_const.RLST_ID
        self.data['rlists'] = []

    def get_rlist(self, index):
        return self.data['rlists'][index] \
            if index < len(self.data['rlists']) else ()

    def add_rlist(self, rlist):
        self.data['rlists'].append(rlist)
        return len(self.data['rlists']) - 1

    def update_from_chunk(self):
        rifx = self.config.rifx
        rlists = self.data['rlists'] = []
        pos = 10
        # Association, Type, ObjectID
        sig = '>hhh' if rifx else '<hhh'
        for _ in range(utils.word2py_int(self.chunk[8:10], rifx)):
            rlists.append(struct.unpack(sig, self.chunk[pos:pos + 6]))
            pos += 6

    def update(self):
        rifx = self.config.rifx
        int2word = utils.py_int2word
        self.chunk = self.data['identifier'] + 4 * '\x00'
        self.chunk += int2word(len(self.data['rlists']), rifx)
        sig = '>hhh' if rifx else '<hhh'
        for item in self.data['rlists']:
            self.chunk += struct.pack(sig, *item)
        CmxRiffElement.update(self)

    def update_for_sword(self):
        CmxRiffElement.update_for_sword(self)
        rifx = self.config.rifx
        self.cache_fields += [(8, 2, 'Number of rlists'), ]
        pos = 10
        for _ in range(utils.word2py_int(self.chunk[8:10], rifx)):
            self.cache_fields += [(pos, 6, 'rlist record'), ]
            pos += 6


class CmxRota(CmxRiffElement):
    def set_defaults(self):
        self.data['identifier'] = cmx_const.ROTA_ID
        self.data['arrows'] = [(0, 0)]

    def get_arrows(self, index):
        return self.data['arrows'][index] \
            if index < len(self.data['arrows']) else ()

    def add_arrows(self, arrows):
        if arrows in self.data['arrows']:
            return self.data['arrows'].index(arrows)
        else:
            self.data['arrows'].append(arrows)
            return len(self.data['arrows']) - 1

    def update_from_chunk(self):
        rifx = self.config.rifx
        arrows = self.data['arrows'] = []
        pos = 10
        sig = '>hh' if rifx else '<hh'
        for _ in range(utils.word2py_int(self.chunk[8:10], rifx)):
            arrows.append(struct.unpack(sig, self.chunk[pos:pos + 4]))
            pos += 4

    def update(self):
        rifx = self.config.rifx
        int2word = utils.py_int2word
        self.chunk = self.data['identifier'] + 4 * '\x00'
        self.chunk += int2word(len(self.data['arrows']), rifx)
        sig = '>hh' if rifx else '<hh'
        for item in self.data['arrows']:
            self.chunk += struct.pack(sig, *item)
        CmxRiffElement.update(self)

    def update_for_sword(self):
        CmxRiffElement.update_for_sword(self)
        rifx = self.config.rifx
        self.cache_fields += [(8, 2, 'Number of arrow records'), ]
        pos = 10
        for _ in range(utils.word2py_int(self.chunk[8:10], rifx)):
            self.cache_fields += [(pos, 4, 'Arrow record'), ]
            pos += 4


class CmxIxlr(CmxRiffElement):
    def set_defaults(self):
        self.data['identifier'] = cmx_const.IXLR_ID
        self.data['layers'] = []

    def update_from_chunk(self):
        rifx = self.config.rifx
        layers = self.data['layers'] = []
        pos = 12
        self.data['page'] = utils.word2py_int(self.chunk[10:12], rifx)
        for _ in range(utils.word2py_int(self.chunk[8:10], rifx)):
            offset = utils.dword2py_int(self.chunk[pos:pos + 4], rifx)
            pos += 4
            sz = utils.word2py_int(self.chunk[pos:pos + 2], rifx)
            pos += 2
            name = self.chunk[pos:pos + sz]
            pos += sz + 4
            layers.append((offset, name))

    def update(self):
        rifx = self.config.rifx
        self.chunk = self.data['identifier'] + 4 * '\x00'
        sz = len(self.data['layers'])
        self.chunk += utils.py_int2word(sz, rifx)
        self.chunk += utils.py_int2word(self.data['page'], rifx)
        for offset, name in self.data['layers']:
            self.chunk += utils.py_int2dword(offset, rifx)
            self.chunk += utils.py_int2word(len(name), rifx)
            self.chunk += name + 4 * '\xff'
        CmxRiffElement.update(self)

    def update_for_sword(self):
        CmxRiffElement.update_for_sword(self)
        rifx = self.config.rifx
        self.cache_fields += [(8, 2, 'Number of layer records'), ]
        self.cache_fields += [(10, 2, 'Page index\n'), ]
        pos = 12
        for _ in range(utils.word2py_int(self.chunk[8:10], rifx)):
            self.cache_fields += [(pos, 4, 'Layer offset'), ]
            pos += 4
            self.cache_fields += [(pos, 2, 'Layer name size'), ]
            sz = utils.word2py_int(self.chunk[pos:pos + 2], rifx)
            pos += 2
            self.cache_fields += [(pos, sz, 'Layer name'), ]
            pos += sz
            self.cache_fields += [(pos, 4, 'Ref.list address\n'), ]
            pos += 4


class CmxRclrV1(CmxRiffElement):
    def set_defaults(self):
        self.data['identifier'] = cmx_const.RCLR_ID
        self.data['colors'] = []

    def get_color(self, index):
        return self.data['colors'][index] \
            if index < len(self.data['colors']) else ()

    def add_color(self, color):
        if color in self.data['colors']:
            return self.data['colors'].index(color)
        else:
            self.data['colors'].append(color)
            return len(self.data['colors']) - 1

    def update_from_chunk(self):
        rifx = self.config.rifx
        colors = self.data['colors'] = []
        pos = 10
        for _ in range(utils.word2py_int(self.chunk[8:10], rifx)):
            model = utils.byte2py_int(self.chunk[pos])
            palette = utils.byte2py_int(self.chunk[pos + 1])
            if model < len(cmx_const.COLOR_BYTES):
                clr_sz = cmx_const.COLOR_BYTES[model]
            else:
                LOG.error('Invalide or unknown color model %s', model)
                break
            vals = tuple(utils.byte2py_int(val)
                         for val in self.chunk[pos + 2: pos + 2 + clr_sz])
            colors.append((model, palette, vals))
            pos += clr_sz + 2

    def update(self):
        rifx = self.config.rifx
        self.chunk = self.data['identifier'] + 4 * '\x00'
        sz = len(self.data['colors'])
        self.chunk += utils.py_int2word(sz, rifx)
        for model, palette, vals in self.data['colors']:
            self.chunk += utils.py_int2byte(model)
            self.chunk += utils.py_int2byte(palette)
            for val in vals:
                self.chunk += utils.py_int2byte(val)
        CmxRiffElement.update(self)

    def update_for_sword(self):
        CmxRiffElement.update_for_sword(self)
        rifx = self.config.rifx
        self.cache_fields += [(8, 2, 'Number of colors\n'), ]
        pos = 10
        for _ in range(utils.word2py_int(self.chunk[8:10], rifx)):
            model = utils.byte2py_int(self.chunk[pos])
            model_name = cmx_const.COLOR_MODEL_MAP.get(model, 'Unknown')
            self.cache_fields += [(pos, 1, '%s color model' % model_name), ]
            palette = utils.byte2py_int(self.chunk[pos + 1])
            pals = cmx_const.COLOR_PALETTES
            pal_name = pals[palette] if palette < len(pals) else 'Unknown'
            self.cache_fields += [(pos + 1, 1, '%s palette' % pal_name), ]
            if model >= len(cmx_const.COLOR_BYTES):
                break
            clr_sz = cmx_const.COLOR_BYTES[model]
            self.cache_fields += [(pos + 2, clr_sz, 'Color values\n'), ]
            pos += clr_sz + 2


class CmxRscrV1(CmxRiffElement):
    def set_defaults(self):
        self.data['identifier'] = cmx_const.RSCR_ID
        self.data['rec_num'] = '\x01\00'
        self.data['records'] = cmx_const.RSCR_RECORD

    def update_from_chunk(self):
        self.data['rec_num'] = self.chunk[8:10]
        self.data['records'] = self.chunk[10:]

    def update(self):
        self.chunk = self.data['identifier'] + 4 * '\x00'
        self.chunk += self.data['rec_num'] + self.data['records']
        CmxRiffElement.update(self)

    def update_for_sword(self):
        CmxRiffElement.update_for_sword(self)
        rifx = self.config.rifx
        self.cache_fields += [(8, 2, 'Number of records'), ]
        pos = 10
        for _ in range(utils.word2py_int(self.chunk[8:10], rifx)):
            self.cache_fields += [(pos, 13, 'Screen record'), ]
            pos += 13


class CmxRdotV1(CmxRiffElement):
    def set_defaults(self):
        self.data['identifier'] = cmx_const.RDOT_ID
        self.data['dashes'] = []

    def get_dashes(self, index):
        return self.data['dashes'][index] \
            if index < len(self.data['dashes']) else ()

    def add_dashes(self, dashes):
        if dashes in self.data['dashes']:
            return self.data['dashes'].index(dashes)
        else:
            self.data['dashes'].append(dashes)
            return len(self.data['dashes']) - 1

    def update_from_chunk(self):
        rifx = self.config.rifx
        dashes = self.data['dashes'] = []
        word2int = utils.word2py_int
        chunk = self.chunk
        pos = 10
        for _ in range(word2int(chunk[8:10], rifx)):
            num = word2int(chunk[pos:pos + 2], rifx)
            pos += 2
            dashes.append(tuple(word2int(
                chunk[pos + 2 * i:pos + 2 * i + 2], rifx) for i in range(num)))
            pos += 2 * num

    def update(self):
        rifx = self.config.rifx
        int2word = utils.py_int2word
        self.chunk = self.data['identifier'] + 4 * '\x00'
        self.chunk += int2word(len(self.data['dashes']), rifx)
        for item in self.data['dashes']:
            self.chunk += int2word(len(item), rifx)
            self.chunk += ''.join([int2word(val, rifx) for val in item])
        CmxRiffElement.update(self)

    def update_for_sword(self):
        CmxRiffElement.update_for_sword(self)
        rifx = self.config.rifx
        self.cache_fields += [(8, 2, 'Number of dash records'), ]
        pos = 10
        for _ in range(utils.word2py_int(self.chunk[8:10], rifx)):
            self.cache_fields += [(pos, 2, 'Number of dash elements'), ]
            num = utils.word2py_int(self.chunk[pos:pos + 2], rifx)
            self.cache_fields += [(pos + 2, 2 * num, 'Dash elements'), ]
            pos += 2 + 2 * num


class CmxRpenV1(CmxRiffElement):
    def set_defaults(self):
        self.data['identifier'] = cmx_const.RPEN_ID
        self.data['pens'] = []

    def get_pen(self, index):
        return self.data['pens'][index] \
            if index < len(self.data['pens']) else ()

    def add_pen(self, pen):
        if pen in self.data['pens']:
            return self.data['pens'].index(pen)
        else:
            self.data['pens'].append(pen)
            return len(self.data['pens']) - 1

    def update_from_chunk(self):
        rifx = self.config.rifx
        pens = self.data['pens'] = []
        word2int = utils.word2py_int
        dword2int = utils.dword2py_int
        chunk = self.chunk
        pos = 10
        sig = '>dddddd' if rifx else '<dddddd'
        for _ in range(word2int(chunk[8:10], rifx)):
            width = word2int(chunk[pos:pos + 2], rifx)
            aspect = word2int(chunk[pos + 2:pos + 4], rifx)
            angle = dword2int(chunk[pos + 4:pos + 8], rifx)
            matrix_flag = word2int(chunk[pos + 8:pos + 10], rifx)
            pos += 10
            if matrix_flag != 1:
                matrix = struct.unpack(sig, chunk[pos:pos + 48])
                pos += 48
                pens.append((width, aspect, angle, matrix_flag, matrix))
            else:
                pens.append((width, aspect, angle, matrix_flag))

    def update(self):
        rifx = self.config.rifx
        int2word = utils.py_int2word
        self.chunk = self.data['identifier'] + 4 * '\x00'
        self.chunk += int2word(len(self.data['pens']), rifx)
        for item in self.data['pens']:
            sig = '>hhih' if rifx else '<hhih'
            self.chunk += struct.pack(sig, *item[:4])
            if len(item) > 4:
                sig = '>dddddd' if rifx else '<dddddd'
                self.chunk += struct.pack(sig, *item[4])
        CmxRiffElement.update(self)

    def update_for_sword(self):
        CmxRiffElement.update_for_sword(self)
        rifx = self.config.rifx
        self.cache_fields += [(8, 2, 'Number of pen records'), ]
        pos = 10
        for _ in range(utils.word2py_int(self.chunk[8:10], rifx)):
            self.cache_fields += [(pos, 10, 'Pen record'), ]
            pos += 10
            if utils.word2py_int(self.chunk[pos - 2:pos], rifx) != 1:
                self.cache_fields += [(pos, 48, 'Pen matrix'), ]


class CmxRottV1(CmxRiffElement):
    def set_defaults(self):
        self.data['identifier'] = cmx_const.ROTT_ID
        self.data['linestyles'] = []

    def get_linestyle(self, index):
        return self.data['linestyles'][index] \
            if index < len(self.data['linestyles']) else ()

    def add_linestyle(self, linestyle):
        if linestyle in self.data['linestyles']:
            return self.data['linestyles'].index(linestyle)
        else:
            self.data['linestyles'].append(linestyle)
            return len(self.data['linestyles']) - 1

    def update_from_chunk(self):
        rifx = self.config.rifx
        linestyles = self.data['linestyles'] = []
        word2int = utils.word2py_int
        chunk = self.chunk
        pos = 10
        for _ in range(word2int(chunk[8:10], rifx)):
            sig = '>BB' if rifx else '<BB'
            linestyles.append(struct.unpack(sig, chunk[pos:pos + 2]))
            pos += 2

    def update(self):
        rifx = self.config.rifx
        int2word = utils.py_int2word
        self.chunk = self.data['identifier'] + 4 * '\x00'
        self.chunk += int2word(len(self.data['linestyles']), rifx)
        sig = '>BB' if rifx else '<BB'
        for item in self.data['linestyles']:
            self.chunk += struct.pack(sig, *item)
        CmxRiffElement.update(self)

    def update_for_sword(self):
        CmxRiffElement.update_for_sword(self)
        rifx = self.config.rifx
        self.cache_fields += [(8, 2, 'Number of line style records'), ]
        pos = 10
        for _ in range(utils.word2py_int(self.chunk[8:10], rifx)):
            self.cache_fields += [(pos, 2, 'Line style record'), ]
            pos += 2


class CmxRotlV1(CmxRiffElement):
    def set_defaults(self):
        self.data['identifier'] = cmx_const.ROTL_ID
        self.data['outlines'] = []

    def get_outline(self, index):
        return self.data['outlines'][index] \
            if index < len(self.data['outlines']) else ()

    def add_outline(self, outline):
        if outline in self.data['outlines']:
            return self.data['outlines'].index(outline)
        else:
            self.data['outlines'].append(outline)
            return len(self.data['outlines']) - 1

    def update_from_chunk(self):
        rifx = self.config.rifx
        linestyles = self.data['outlines'] = []
        word2int = utils.word2py_int
        chunk = self.chunk
        pos = 10
        # style, screen, color, arrowheads, pen, dash
        sig = '>HHHHHH' if rifx else '<HHHHHH'
        for _ in range(word2int(chunk[8:10], rifx)):
            linestyles.append(struct.unpack(sig, chunk[pos:pos + 12]))
            pos += 12

    def update(self):
        rifx = self.config.rifx
        int2word = utils.py_int2word
        self.chunk = self.data['identifier'] + 4 * '\x00'
        self.chunk += int2word(len(self.data['outlines']), rifx)
        sig = '>HHHHHH' if rifx else '<HHHHHH'
        for item in self.data['outlines']:
            self.chunk += struct.pack(sig, *item)
        CmxRiffElement.update(self)

    def update_for_sword(self):
        CmxRiffElement.update_for_sword(self)
        rifx = self.config.rifx
        self.cache_fields += [(8, 2, 'Number of outline records'), ]
        pos = 10
        for _ in range(utils.word2py_int(self.chunk[8:10], rifx)):
            self.cache_fields += [(pos, 12, 'Outline record'), ]
            pos += 12


class CmxRoot(CmxList):
    toplevel = True
    chunk_map = None

    def __init__(self, config, chunk=None, root_id=cmx_const.ROOT_ID):
        config.rifx = root_id == cmx_const.ROOTX_ID
        chunk = chunk or self.make_new_doc(config, root_id)
        CmxList.__init__(self, config, chunk)

    def make_new_doc(self, config, root_id):
        chunk = root_id + 4 * '\x00'
        chunk += cmx_const.CDRX_ID if config.pack else cmx_const.CMX_ID

        # TODO: here should be cmx doc creating

        return chunk

    def update(self):
        def _add_chunk(self, chunk):
            if chunk.get_name() == cmx_const.PAGE_ID:
                self.chunk_map['pages'].append([chunk, ])
            elif chunk.get_name() == cmx_const.RLST_ID:
                self.chunk_map['pages'][-1].append(chunk)
            else:
                self.chunk_map[chunk.get_name()] = chunk

        CmxList.update(self)
        self.chunk_map = {'pages': []}
        for child in self.childs:
            if child.get_name() != cmx_const.PACK_ID:
                _add_chunk(self, child)
            else:
                for item in child.childs:
                    _add_chunk(self, item)


GENERIC_CHUNK_MAP = {
    cmx_const.LIST_ID: CmxList,
    cmx_const.CONT_ID: CmxCont,
    cmx_const.CCMM_ID: CmxCcmm,
    cmx_const.DISP_ID: CmxDisp,
    cmx_const.PAGE_ID: CmxPage,
    cmx_const.PACK_ID: CdrxPack,
    cmx_const.IKEY_ID: CmxInfoElement,
    cmx_const.ICMT_ID: CmxInfoElement,
    cmx_const.RLST_ID: CmxRlst,
    cmx_const.ROTA_ID: CmxRota,
    cmx_const.IXLR_ID: CmxIxlr,
}

V1_CHUNK_MAP = {
    cmx_const.RCLR_ID: CmxRclrV1,
    cmx_const.RSCR_ID: CmxRscrV1,
    cmx_const.RDOT_ID: CmxRdotV1,
    cmx_const.RPEN_ID: CmxRpenV1,
    cmx_const.ROTT_ID: CmxRottV1,
    cmx_const.ROTL_ID: CmxRotlV1,

}

V2_CHUNK_MAP = {
}


def make_cmx_chunk(config, chunk):
    identifier = chunk[:4]
    if identifier in GENERIC_CHUNK_MAP:
        mapping = GENERIC_CHUNK_MAP
    elif config.v1:
        mapping = V1_CHUNK_MAP
    else:
        mapping = V2_CHUNK_MAP
    return mapping.get(identifier, CmxRiffElement)(config, chunk)
