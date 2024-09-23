# uncompyle6 version 2.11.5
# Python bytecode 2.4 (62061)
# Decompiled from: Python 2.7.18 (default, Oct 15 2023, 16:43:11) 
# [GCC 11.4.0]
# Embedded file name: Image.pyo
# Compiled at: 2006-12-03 15:20:56
VERSION = '1.1.6'
try:
    import warnings
except ImportError:
    warnings = None

class _imaging_not_installed():

    def __getattr__(self, id):
        raise ImportError('The _imaging C module is not installed')


try:
    __import__('FixTk')
except ImportError:
    pass

try:
    import _imaging
    core = _imaging
    del _imaging
except ImportError, v:
    core = _imaging_not_installed()
    if str(v)[:20] == 'Module use of python' and warnings:
        warnings.warn('The _imaging extension was built for another version of Python; most PIL functions will be disabled', RuntimeWarning)

import ImageMode
import ImagePalette
import os
import string
import sys
from types import IntType, StringType, TupleType
try:
    UnicodeStringType = type(unicode(''))

    def isStringType(t):
        return isinstance(t, StringType) or isinstance(t, UnicodeStringType)


except NameError:

    def isStringType(t):
        return isinstance(t, StringType)


def isTupleType(t):
    return isinstance(t, TupleType)


def isImageType(t):
    return hasattr(t, 'im')


def isDirectory(f):
    return isStringType(f) and os.path.isdir(f)


from operator import isNumberType, isSequenceType
DEBUG = 0
NONE = 0
FLIP_LEFT_RIGHT = 0
FLIP_TOP_BOTTOM = 1
ROTATE_90 = 2
ROTATE_180 = 3
ROTATE_270 = 4
AFFINE = 0
EXTENT = 1
PERSPECTIVE = 2
QUAD = 3
MESH = 4
NONE = 0
NEAREST = 0
ANTIALIAS = 1
LINEAR = BILINEAR = 2
CUBIC = BICUBIC = 3
NONE = 0
NEAREST = 0
ORDERED = 1
RASTERIZE = 2
FLOYDSTEINBERG = 3
WEB = 0
ADAPTIVE = 1
NORMAL = 0
SEQUENCE = 1
CONTAINER = 2
ID = []
OPEN = {}
MIME = {}
SAVE = {}
EXTENSION = {}
_MODEINFO = {'1': ('L', 'L', ('1',)),'L': ('L', 'L', ('L',)),'I': ('L', 'I', ('I',)),'F': ('L', 'F', ('F',)),'P': ('RGB', 'L', ('P',)),'RGB': ('RGB', 'L', ('R', 'G', 'B')),'RGBX': ('RGB', 'L', ('R', 'G', 'B', 'X')),'RGBA': ('RGB', 'L', ('R', 'G', 'B', 'A')),'CMYK': ('RGB', 'L', ('C', 'M', 'Y', 'K')),'YCbCr': ('RGB', 'L', ('Y', 'Cb', 'Cr'))}
if sys.byteorder == 'little':
    _ENDIAN = '<'
else:
    _ENDIAN = '>'
_MODE_CONV = {'1': ('|b1', None),'L': ('|u1', None),'I': ('%si4' % _ENDIAN, None),'F': ('%sf4' % _ENDIAN, None),'P': ('|u1', None),'RGB': ('|u1', 3),'RGBX': ('|u1', 4),'RGBA': ('|u1', 4),'CMYK': ('|u1', 4),'YCbCr': ('|u1', 4)}

def _conv_type_shape(im):
    shape = im.size[::-1]
    typ, extra = _MODE_CONV[im.mode]
    if extra is None:
        return (shape, typ)
    else:
        return (
         shape + (extra,), typ)
    return


MODES = _MODEINFO.keys()
MODES.sort()
_MAPMODES = (
 'L', 'P', 'RGBX', 'RGBA', 'CMYK', 'I;16', 'I;16B')

def getmodebase(mode):
    return ImageMode.getmode(mode).basemode


def getmodetype(mode):
    return ImageMode.getmode(mode).basetype


def getmodebandnames(mode):
    return ImageMode.getmode(mode).bands


def getmodebands(mode):
    return len(ImageMode.getmode(mode).bands)


_initialized = 0

def preinit():
    global _initialized
    if _initialized >= 1:
        return
    try:
        import BmpImagePlugin
    except ImportError:
        pass

    try:
        import GifImagePlugin
    except ImportError:
        pass

    try:
        import JpegImagePlugin
    except ImportError:
        pass

    try:
        import PpmImagePlugin
    except ImportError:
        pass

    try:
        import PngImagePlugin
    except ImportError:
        pass

    _initialized = 1


def init():
    global _initialized
    if _initialized >= 2:
        return
    visited = {}
    directories = sys.path
    try:
        directories = directories + [os.path.dirname(__file__)]
    except NameError:
        pass

    for directory in filter(isDirectory, directories):
        fullpath = os.path.abspath(directory)
        if visited.has_key(fullpath):
            continue
        for file in os.listdir(directory):
            if file[-14:] == 'ImagePlugin.py':
                f, e = os.path.splitext(file)
                try:
                    sys.path.insert(0, directory)
                    try:
                        __import__(f, globals(), locals(), [])
                    finally:
                        del sys.path[0]

                except ImportError:
                    if DEBUG:
                        print 'Image: failed to import',
                        print f, ':', sys.exc_value

        visited[fullpath] = None

    if OPEN or SAVE:
        _initialized = 2
    return


def _getdecoder(mode, decoder_name, args, extra=()):
    if args is None:
        args = ()
    elif not isTupleType(args):
        args = (
         args,)
    try:
        decoder = getattr(core, decoder_name + '_decoder')
        return apply(decoder, (mode,) + args + extra)
    except AttributeError:
        raise IOError('decoder %s not available' % decoder_name)

    return


def _getencoder(mode, encoder_name, args, extra=()):
    if args is None:
        args = ()
    elif not isTupleType(args):
        args = (
         args,)
    try:
        encoder = getattr(core, encoder_name + '_encoder')
        return apply(encoder, (mode,) + args + extra)
    except AttributeError:
        raise IOError('encoder %s not available' % encoder_name)

    return


class _E():

    def __init__(self, data):
        self.data = data

    def __coerce__(self, other):
        return (self, _E(other))

    def __add__(self, other):
        return _E((self.data, '__add__', other.data))

    def __mul__(self, other):
        return _E((self.data, '__mul__', other.data))


def _getscaleoffset(expr):
    stub = [
     'stub']
    data = expr(_E(stub)).data
    try:
        a, b, c = data
        if a is stub and b == '__mul__' and isNumberType(c):
            return (c, 0.0)
        if a is stub and b == '__add__' and isNumberType(c):
            return (1.0, c)
    except TypeError:
        pass

    try:
        (a, b, c), d, e = data
        if a is stub and b == '__mul__' and isNumberType(c) and d == '__add__' and isNumberType(e):
            return (
             c, e)
    except TypeError:
        pass

    raise ValueError('illegal expression')


class Image():
    format = None
    format_description = None

    def __init__(self):
        self.im = None
        self.mode = ''
        self.size = (0, 0)
        self.palette = None
        self.info = {}
        self.category = NORMAL
        self.readonly = 0
        return

    def _new(self, im):
        new = Image()
        new.im = im
        new.mode = im.mode
        new.size = im.size
        new.palette = self.palette
        if im.mode == 'P':
            new.palette = ImagePalette.ImagePalette()
        try:
            new.info = self.info.copy()
        except AttributeError:
            new.info = {}
            for k, v in self.info:
                new.info[k] = v

        return new

    _makeself = _new

    def _copy(self):
        self.load()
        self.im = self.im.copy()
        self.readonly = 0

    def _dump(self, file=None, format=None):
        import tempfile
        if not file:
            file = tempfile.mktemp()
        self.load()
        if not format or format == 'PPM':
            self.im.save_ppm(file)
        else:
            file = file + '.' + format
            self.save(file, format)
        return file

    def __getattr__(self, name):
        if name == '__array_interface__':
            new = {}
            shape, typestr = _conv_type_shape(self)
            new['shape'] = shape
            new['typestr'] = typestr
            new['data'] = self.tostring()
            return new
        raise AttributeError(name)

    def tostring(self, encoder_name='raw', *args):
        if len(args) == 1 and isTupleType(args[0]):
            args = args[0]
        if encoder_name == 'raw' and args == ():
            args = self.mode
        self.load()
        e = _getencoder(self.mode, encoder_name, args)
        e.setimage(self.im)
        bufsize = max(65536, self.size[0] * 4)
        data = []
        while 1:
            l, s, d = e.encode(bufsize)
            data.append(d)
            if s:
                break

        if s < 0:
            raise RuntimeError('encoder error %d in tostring' % s)
        return string.join(data, '')

    def tobitmap(self, name='image'):
        self.load()
        if self.mode != '1':
            raise ValueError('not a bitmap')
        data = self.tostring('xbm')
        return string.join(['#define %s_width %d\n' % (name, self.size[0]), '#define %s_height %d\n' % (name, self.size[1]), 'static char %s_bits[] = {\n' % name, data, '};'], '')

    def fromstring(self, data, decoder_name='raw', *args):
        if len(args) == 1 and isTupleType(args[0]):
            args = args[0]
        if decoder_name == 'raw' and args == ():
            args = self.mode
        d = _getdecoder(self.mode, decoder_name, args)
        d.setimage(self.im)
        s = d.decode(data)
        if s[0] >= 0:
            raise ValueError('not enough image data')
        if s[1] != 0:
            raise ValueError('cannot decode image data')

    def load(self):
        if self.im and self.palette and self.palette.dirty:
            apply(self.im.putpalette, self.palette.getdata())
            self.palette.dirty = 0
            self.palette.mode = 'RGB'
            self.palette.rawmode = None
            if self.info.has_key('transparency'):
                self.im.putpalettealpha(self.info['transparency'], 0)
                self.palette.mode = 'RGBA'
        if self.im:
            return self.im.pixel_access(self.readonly)
        return

    def verify(self):
        pass

    def convert(self, mode=None, data=None, dither=None, palette=WEB, colors=256):
        if not mode:
            if self.mode == 'P':
                self.load()
                if self.palette:
                    mode = self.palette.mode
                else:
                    mode = 'RGB'
            else:
                return self.copy()
        self.load()
        if data:
            if mode not in ('L', 'RGB'):
                raise ValueError('illegal conversion')
            im = self.im.convert_matrix(mode, data)
            return self._new(im)
        if mode == 'P' and palette == ADAPTIVE:
            im = self.im.quantize(colors)
            return self._new(im)
        if dither is None:
            dither = FLOYDSTEINBERG
        try:
            im = self.im.convert(mode, dither)
        except ValueError:
            try:
                im = self.im.convert(getmodebase(self.mode))
                im = im.convert(mode, dither)
            except KeyError:
                raise ValueError('illegal conversion')

        return self._new(im)

    def quantize(self, colors=256, method=0, kmeans=0, palette=None):
        self.load()
        if palette:
            palette.load()
            if palette.mode != 'P':
                raise ValueError('bad mode for palette image')
            if self.mode != 'RGB' and self.mode != 'L':
                raise ValueError('only RGB or L mode images can be quantized to a palette')
            im = self.im.convert('P', 1, palette.im)
            return self._makeself(im)
        im = self.im.quantize(colors, method, kmeans)
        return self._new(im)

    def copy(self):
        self.load()
        im = self.im.copy()
        return self._new(im)

    def crop(self, box=None):
        self.load()
        if box is None:
            return self.copy()
        return _ImageCrop(self, box)

    def draft(self, mode, size):
        pass

    def _expand(self, xmargin, ymargin=None):
        if ymargin is None:
            ymargin = xmargin
        self.load()
        return self._new(self.im.expand(xmargin, ymargin, 0))

    def filter(self, filter):
        self.load()
        from ImageFilter import Filter
        if not isinstance(filter, Filter):
            filter = filter()
        if self.im.bands == 1:
            return self._new(filter.filter(self.im))
        ims = []
        for c in range(self.im.bands):
            ims.append(self._new(filter.filter(self.im.getband(c))))

        return merge(self.mode, ims)

    def getbands(self):
        return ImageMode.getmode(self.mode).bands

    def getbbox(self):
        self.load()
        return self.im.getbbox()

    def getcolors(self, maxcolors=256):
        self.load()
        if self.mode in ('1', 'L', 'P'):
            h = self.im.histogram()
            out = []
            for i in range(256):
                if h[i]:
                    out.append((h[i], i))

            if len(out) > maxcolors:
                return None
            return out
        return self.im.getcolors(maxcolors)

    def getdata(self, band=None):
        self.load()
        if band is not None:
            return self.im.getband(band)
        return self.im

    def getextrema(self):
        self.load()
        if self.im.bands > 1:
            extrema = []
            for i in range(self.im.bands):
                extrema.append(self.im.getband(i).getextrema())

            return tuple(extrema)
        return self.im.getextrema()

    def getim(self):
        self.load()
        return self.im.ptr

    def getpalette(self):
        self.load()
        try:
            return map(ord, self.im.getpalette())
        except ValueError:
            return None

        return None

    def getpixel(self, xy):
        self.load()
        return self.im.getpixel(xy)

    def getprojection(self):
        self.load()
        x, y = self.im.getprojection()
        return (
         map(ord, x), map(ord, y))

    def histogram(self, mask=None, extrema=None):
        self.load()
        if mask:
            mask.load()
            return self.im.histogram((0, 0), mask.im)
        if self.mode in ('I', 'F'):
            if extrema is None:
                extrema = self.getextrema()
            return self.im.histogram(extrema)
        return self.im.histogram()

    def offset(self, xoffset, yoffset=None):
        if warnings:
            warnings.warn("'offset' is deprecated; use 'ImageChops.offset' instead", DeprecationWarning, stacklevel=2)
        import ImageChops
        return ImageChops.offset(self, xoffset, yoffset)

    def paste(self, im, box=None, mask=None):
        if isImageType(box) and mask is None:
            mask = box
            box = None
        if box is None:
            box = (0, 0) + self.size
        if len(box) == 2:
            if isImageType(im):
                size = im.size
            elif isImageType(mask):
                size = mask.size
            else:
                raise ValueError('cannot determine region size; use 4-item box')
            box = box + (box[0] + size[0], box[1] + size[1])
        if isStringType(im):
            import ImageColor
            im = ImageColor.getcolor(im, self.mode)
        elif isImageType(im):
            im.load()
            if self.mode != im.mode:
                if self.mode != 'RGB' or im.mode not in ('RGBA', 'RGBa'):
                    im = im.convert(self.mode)
            im = im.im
        self.load()
        if self.readonly:
            self._copy()
        if mask:
            mask.load()
            self.im.paste(im, box, mask.im)
        else:
            self.im.paste(im, box)
        return

    def point(self, lut, mode=None):
        self.load()
        if not isSequenceType(lut):
            if self.mode in ('I', 'I;16', 'F'):
                scale, offset = _getscaleoffset(lut)
                return self._new(self.im.point_transform(scale, offset))
            lut = map(lut, range(256)) * self.im.bands
        if self.mode == 'F':
            raise ValueError('point operation not supported for this mode')
        return self._new(self.im.point(lut, mode))

    def putalpha(self, alpha):
        self.load()
        if self.readonly:
            self._copy()
        if self.mode not in ('LA', 'RGBA'):
            try:
                mode = getmodebase(self.mode) + 'A'
                try:
                    self.im.setmode(mode)
                except (AttributeError, ValueError):
                    im = self.im.convert(mode)
                    if im.mode not in ('LA', 'RGBA'):
                        raise ValueError
                    self.im = im

                self.mode = self.im.mode
            except (KeyError, ValueError):
                raise ValueError('illegal image mode')

        if self.mode == 'LA':
            band = 1
        else:
            band = 3
        if isImageType(alpha):
            if alpha.mode not in ('1', 'L'):
                raise ValueError('illegal image mode')
            alpha.load()
            if alpha.mode == '1':
                alpha = alpha.convert('L')
        else:
            try:
                self.im.fillband(band, alpha)
            except (AttributeError, ValueError):
                alpha = new('L', self.size, alpha)

            return
        self.im.putband(alpha.im, band)

    def putdata(self, data, scale=1.0, offset=0.0):
        self.load()
        if self.readonly:
            self._copy()
        self.im.putdata(data, scale, offset)

    def putpalette(self, data, rawmode='RGB'):
        self.load()
        if self.mode not in ('L', 'P'):
            raise ValueError('illegal image mode')
        if not isStringType(data):
            data = string.join(map(chr, data), '')
        self.mode = 'P'
        self.palette = ImagePalette.raw(rawmode, data)
        self.palette.mode = 'RGB'
        self.load()

    def putpixel(self, xy, value):
        self.load()
        if self.readonly:
            self._copy()
        return self.im.putpixel(xy, value)

    def resize(self, size, resample=NEAREST):
        if resample not in (NEAREST, BILINEAR, BICUBIC, ANTIALIAS):
            raise ValueError('unknown resampling filter')
        self.load()
        if self.mode in ('1', 'P'):
            resample = NEAREST
        if resample == ANTIALIAS:
            try:
                im = self.im.stretch(size, resample)
            except AttributeError:
                raise ValueError('unsupported resampling filter')

        else:
            im = self.im.resize(size, resample)
        return self._new(im)

    def rotate(self, angle, resample=NEAREST, expand=0):
        if expand:
            import math
            angle = -angle * math.pi / 180
            matrix = [math.cos(angle), math.sin(angle), 0.0, -math.sin(angle), math.cos(angle), 0.0]

            def transform(x, y, (a, b, c, d, e, f)=matrix):
                return (
                 a * x + b * y + c, d * x + e * y + f)

            w, h = self.size
            xx = []
            yy = []
            for x, y in ((0, 0), (w, 0), (w, h), (0, h)):
                x, y = transform(x, y)
                xx.append(x)
                yy.append(y)

            w = int(math.ceil(max(xx)) - math.floor(min(xx)))
            h = int(math.ceil(max(yy)) - math.floor(min(yy)))
            x, y = transform(w / 2.0, h / 2.0)
            matrix[2] = self.size[0] / 2.0 - x
            matrix[5] = self.size[1] / 2.0 - y
            return self.transform((w, h), AFFINE, matrix)
        if resample not in (NEAREST, BILINEAR, BICUBIC):
            raise ValueError('unknown resampling filter')
        self.load()
        if self.mode in ('1', 'P'):
            resample = NEAREST
        return self._new(self.im.rotate(angle, resample))

    def save(self, fp, format=None, **params):
        if isStringType(fp):
            filename = fp
        else:
            if hasattr(fp, 'name') and isStringType(fp.name):
                filename = fp.name
            else:
                filename = ''
            self.load()
            self.encoderinfo = params
            self.encoderconfig = ()
            preinit()
            ext = string.lower(os.path.splitext(filename)[1])
            if not format:
                try:
                    format = EXTENSION[ext]
                except KeyError:
                    init()
                    try:
                        format = EXTENSION[ext]
                    except KeyError:
                        raise KeyError(ext)

            try:
                save_handler = SAVE[string.upper(format)]
            except KeyError:
                init()
                save_handler = SAVE[string.upper(format)]

            if isStringType(fp):
                import __builtin__
                fp = __builtin__.open(fp, 'wb')
                close = 1
            close = 0
        try:
            save_handler(self, fp, filename)
        finally:
            if close:
                fp.close()

    def seek(self, frame):
        if frame != 0:
            raise EOFError

    def show(self, title=None, command=None):
        _showxv(self, title, command)

    def split(self):
        ims = []
        self.load()
        for i in range(self.im.bands):
            ims.append(self._new(self.im.getband(i)))

        return tuple(ims)

    def tell(self):
        return 0

    def thumbnail(self, size, resample=NEAREST):
        x, y = self.size
        if x > size[0]:
            y = max(y * size[0] / x, 1)
            x = size[0]
        if y > size[1]:
            x = max(x * size[1] / y, 1)
            y = size[1]
        size = (
         x, y)
        if size == self.size:
            return
        self.draft(None, size)
        self.load()
        try:
            im = self.resize(size, resample)
        except ValueError:
            if resample != ANTIALIAS:
                raise
            im = self.resize(size, NEAREST)

        self.im = im.im
        self.mode = im.mode
        self.size = size
        self.readonly = 0
        return

    def transform(self, size, method, data=None, resample=NEAREST, fill=1):
        import ImageTransform
        if isinstance(method, ImageTransform.Transform):
            method, data = method.getdata()
        if data is None:
            raise ValueError('missing method data')
        im = new(self.mode, size, None)
        if method == MESH:
            for box, quad in data:
                im.__transformer(box, self, QUAD, quad, resample, fill)

        else:
            im.__transformer((0, 0) + size, self, method, data, resample, fill)
        return im

    def __transformer(self, box, image, method, data, resample=NEAREST, fill=1):
        w = box[2] - box[0]
        h = box[3] - box[1]
        if method == AFFINE:
            data = (data[2], data[0], data[1], data[5], data[3], data[4])
        else:
            if method == EXTENT:
                x0, y0, x1, y1 = data
                xs = float(x1 - x0) / w
                ys = float(y1 - y0) / h
                method = AFFINE
                data = (x0 + xs / 2, xs, 0, y0 + ys / 2, 0, ys)
            else:
                if method == PERSPECTIVE:
                    data = (data[2], data[0], data[1], data[5], data[3], data[4], data[6], data[7])
                elif method == QUAD:
                    nw = data[0:2]
                    sw = data[2:4]
                    se = data[4:6]
                    ne = data[6:8]
                    x0, y0 = nw
                    As = 1.0 / w
                    At = 1.0 / h
                    data = (
                     x0, (ne[0] - x0) * As, (sw[0] - x0) * At, (se[0] - sw[0] - ne[0] + x0) * As * At, y0, (ne[1] - y0) * As, (sw[1] - y0) * At, (se[1] - sw[1] - ne[1] + y0) * As * At)
                else:
                    raise ValueError('unknown transformation method')
                if resample not in (NEAREST, BILINEAR, BICUBIC):
                    raise ValueError('unknown resampling filter')
            image.load()
            self.load()
            if image.mode in ('1', 'P'):
                resample = NEAREST
        self.im.transform2(box, image.im, method, data, resample, fill)

    def transpose(self, method):
        self.load()
        im = self.im.transpose(method)
        return self._new(im)


class _ImageCrop(Image):

    def __init__(self, im, box):
        Image.__init__(self)
        x0, y0, x1, y1 = box
        if x1 < x0:
            x1 = x0
        if y1 < y0:
            y1 = y0
        self.mode = im.mode
        self.size = (x1 - x0, y1 - y0)
        self.__crop = (
         x0, y0, x1, y1)
        self.im = im.im

    def load(self):
        if self.__crop:
            self.im = self.im.crop(self.__crop)
            self.__crop = None
        return


def _wedge():
    return Image()._new(core.wedge('L'))


def new(mode, size, color=0):
    if color is None:
        return Image()._new(core.new(mode, size))
    if isStringType(color):
        import ImageColor
        color = ImageColor.getcolor(color, mode)
    return Image()._new(core.fill(mode, size, color))


def fromstring(mode, size, data, decoder_name='raw', *args):
    if len(args) == 1 and isTupleType(args[0]):
        args = args[0]
    if decoder_name == 'raw' and args == ():
        args = mode
    im = new(mode, size)
    im.fromstring(data, decoder_name, args)
    return im


def frombuffer(mode, size, data, decoder_name='raw', *args):
    if len(args) == 1 and isTupleType(args[0]):
        args = args[0]
    if decoder_name == 'raw':
        if args == ():
            if warnings:
                warnings.warn("the frombuffer defaults may change in a future release; for portability, change the call to read:\n  frombuffer(mode, size, data, 'raw', mode, 0, 1)", RuntimeWarning, stacklevel=2)
            args = (mode, 0, -1)
        if args[0] in _MAPMODES:
            im = new(mode, (1, 1))
            im = im._new(core.map_buffer(data, size, decoder_name, None, 0, args))
            im.readonly = 1
            return im
    return apply(fromstring, (mode, size, data, decoder_name, args))


def fromarray(obj, mode=None):
    arr = obj.__array_interface__
    shape = arr['shape']
    ndim = len(shape)
    try:
        strides = arr['strides']
    except KeyError:
        strides = None

    if mode is None:
        typestr = arr['typestr']
        if not (typestr[0] == '|' or typestr[0] == _ENDIAN or typestr[1:] not in ['u1', 'b1', 'i4', 'f4']):
            raise TypeError('cannot handle data-type')
        typestr = typestr[:2]
        if typestr == 'i4':
            mode = 'I'
        elif typestr == 'f4':
            mode = 'F'
        elif typestr == 'b1':
            mode = '1'
        elif ndim == 2:
            mode = 'L'
        elif ndim == 3:
            mode = 'RGB'
        elif ndim == 4:
            mode = 'RGBA'
        else:
            raise TypeError('Do not understand data.')
    ndmax = 4
    bad_dims = 0
    if mode in ['1', 'L', 'I', 'P', 'F']:
        ndmax = 2
    elif mode == 'RGB':
        ndmax = 3
    if ndim > ndmax:
        raise ValueError('Too many dimensions.')
    size = shape[:2][::-1]
    if strides is not None:
        obj = obj.tostring()
    return frombuffer(mode, size, obj, 'raw', mode, 0, 1)


def open(fp, mode='r'):
    if mode != 'r':
        raise ValueError('bad mode')
    if isStringType(fp):
        import __builtin__
        filename = fp
        fp = __builtin__.open(fp, 'rb')
    else:
        filename = ''
    prefix = fp.read(16)
    preinit()
    for i in ID:
        try:
            factory, accept = OPEN[i]
            if not accept or accept(prefix):
                fp.seek(0)
                return factory(fp, filename)
        except (SyntaxError, IndexError, TypeError):
            pass

    init()
    for i in ID:
        try:
            factory, accept = OPEN[i]
            if not accept or accept(prefix):
                fp.seek(0)
                return factory(fp, filename)
        except (SyntaxError, IndexError, TypeError):
            pass

    raise IOError('cannot identify image file')


def blend(im1, im2, alpha):
    im1.load()
    im2.load()
    return im1._new(core.blend(im1.im, im2.im, alpha))


def composite(image1, image2, mask):
    image = image2.copy()
    image.paste(image1, None, mask)
    return image


def eval(image, *args):
    return image.point(args[0])


def merge(mode, bands):
    if getmodebands(mode) != len(bands) or '*' in mode:
        raise ValueError('wrong number of bands')
    for im in bands[1:]:
        if im.mode != getmodetype(mode):
            raise ValueError('mode mismatch')
        if im.size != bands[0].size:
            raise ValueError('size mismatch')

    im = core.new(mode, bands[0].size)
    for i in range(getmodebands(mode)):
        bands[i].load()
        im.putband(bands[i].im, i)

    return bands[0]._new(im)


def register_open(id, factory, accept=None):
    id = string.upper(id)
    ID.append(id)
    OPEN[id] = (factory, accept)


def register_mime(id, mimetype):
    MIME[string.upper(id)] = mimetype


def register_save(id, driver):
    SAVE[string.upper(id)] = driver


def register_extension(id, extension):
    EXTENSION[string.lower(extension)] = string.upper(id)


def _showxv(image, title=None, command=None):
    if os.name == 'nt':
        format = 'BMP'
    else:
        if sys.platform == 'darwin':
            format = 'JPEG'
            if not command:
                command = 'open -a /Applications/Preview.app'
        else:
            format = None
            if not command:
                command = 'xv'
                if title:
                    command = command + ' -name "%s"' % title
        if image.mode == 'I;16':
            base = 'L'
        else:
            base = getmodebase(image.mode)
        if base != image.mode and image.mode != '1':
            file = image.convert(base)._dump(format=format)
        else:
            file = image._dump(format=format)
        if os.name == 'nt':
            command = 'start /wait %s && del /f %s' % (file, file)
        else:
            if sys.platform == 'darwin':
                command = '(%s %s; sleep 20; rm -f %s)&' % (command, file, file)
            command = '(%s %s; rm -f %s)&' % (command, file, file)
    os.system(command)
    return
# okay decompiling Image.pyo
