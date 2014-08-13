from __future__ import print_function, unicode_literals, division
from .formats.substation import is_valid_field_content

"""
``SSAFile`` --- a subtitle file
===============================

.. autoclass:: pysubs2.SSAFile


Reading and writing subtitles
-----------------------------

Using file
~~~~~~~~~~

.. automethod:: SSAFile.load
.. automethod:: SSAFile.save

Using string
~~~~~~~~~~~~

.. automethod:: SSAFile.from_string
.. automethod:: SSAFile.to_string

Using file object
~~~~~~~~~~~~~~~~~

.. automethod:: SSAFile.from_file
.. automethod:: SSAFile.to_file

Retiming subtitles
------------------

.. automethod:: SSAFile.shift
.. automethod:: SSAFile.transform_framerate

Working with styles
-------------------

.. automethod:: SSAFile.rename_style
.. automethod:: SSAFile.import_styles

"""

from collections import MutableSequence, OrderedDict
import io
from io import open
from itertools import starmap
import os.path
from .formats import autodetect_format, get_format_class, get_format_identifier
from .ssaevent import SSAEvent
from .ssastyle import SSAStyle
from .time import make_time


class SSAFile(MutableSequence):
    """
    Subtitle file in SubStation Alpha format.

    """

    DEFAULT_STYLES = OrderedDict({"Default": SSAStyle()}.items())
    DEFAULT_INFO = OrderedDict(
        {"WrapStyle": "0",
         "ScaledBorderAndShadow": "yes",
         "Collisions": "Normal"}.items())

    def __init__(self):
        self.events = []
        self.styles = self.DEFAULT_STYLES.copy()
        self.info = self.DEFAULT_INFO.copy()
        self.fps = None
        self.format = None

    # ------------------------------------------------------------------------
    # I/O methods
    # ------------------------------------------------------------------------

    @classmethod
    def load(cls, path, encoding="utf-8", format_=None, fps=None, **kwargs):
        """
        Load subtitle file from given path.

        Arguments:
            path (str): Path to subtitle file.
            encoding (str): Character encoding of input file.
                Defaults to UTF-8, you may need to change this.
            format_ (str): Optional, forces use of specific parser
                (eg. `"srt"`, `"ass"`). Otherwise, format is detected
                automatically from file contents. This argument should
                be rarely needed.
            fps (float): Framerate for frame-based formats (MicroDVD),
                for other formats this argument is ignored. Framerate might
                be detected from the file, in which case you don't need
                to specify it here (when given, this argument overrides
                autodetection).
            kwargs: Extra options for the parser.

        Returns:
            SSAFile

        Note:
            pysubs2 may autodetect subtitle format and/or framerate. These
            values are set as :attr:`SSAFile.format` and :attr:`SSAfile.fps`
            attributes.

        Example:
            >>> subs1 = pysubs2.load("subrip-subtitles.srt")
            >>> subs2 = pysubs2.load("microdvd-subtitles.sub", fps=23.976)

        """
        with open(path, encoding=encoding) as fp:
            return cls.from_file(fp, format_, fps=fps, **kwargs)

    @classmethod
    def from_string(cls, string, format_=None, fps=None, **kwargs):
        """
        Load subtitle file from string.

        See :meth:`SSAFile.load()` for full description.

        Arguments:
            string (str): Subtitle file in a string. Note that the string
                must be Unicode (in Python 2).

        Returns:
            SSAFile

        Example:
            >>> text = '''
            ... 1
            ... 00:00:00,000 --> 00:00:05,000
            ... An example SubRip file.
            ... '''
            >>> subs = SSAFile.from_string(text)

        """
        fp = io.StringIO(string)
        return cls.from_file(fp, format_, fps=fps, **kwargs)

    @classmethod
    def from_file(cls, fp, format_=None, fps=None, **kwargs):
        """
        Read subtitle file from file object.

        See :meth:`SSAFile.load()` for full description.

        Note:
            This is a low-level method. Usually, one of :meth:`SSAFile.load()`
            or :meth:`SSAFile.from_string()` is preferable.

        Arguments:
            fp (file object): A file object, ie. :class:`io.TextIOBase` instance.
                Note that the file must be opened in text mode (as opposed to binary).

        Returns:
            SSAFile

        """
        if format_ is None:
            # Autodetect subtitle format, then read again using correct parser.
            # The file might be a pipe and we need to read it twice,
            # so just buffer everything.
            text = fp.read()
            fragment = text[:10000]
            format_ = autodetect_format(fragment)
            fp = io.StringIO(text)

        impl = get_format_class(format_)
        subs = cls() # an empty subtitle file
        subs.format = format_
        subs.fps = fps
        impl.from_file(subs, fp, format_, fps=fps, **kwargs)
        return subs

    def save(self, path, encoding="utf-8", format_=None, fps=None, **kwargs):
        """
        Save subtitle file to given path.

        Arguments:
            path (str): Path to subtitle file.
            encoding (str): Character encoding of output file.
                Defaults to UTF-8, which should be fine for most purposes.
            format_ (str): Optional, specifies desired subtitle format
                (eg. `"srt"`, `"ass"`). Otherwise, format is detected
                automatically from file extension. Thus, this argument
                is rarely needed.
            fps (float): Framerate for frame-based formats (MicroDVD),
                for other formats this argument is ignored. When omitted,
                :attr:`SSAFile.fps` value is used (ie. the framerate used
                for loading the file, if any). When the :class:`SSAFile`
                wasn't loaded from MicroDVD, or if you wish save it with
                different framerate, use this argument. See also
                :meth:`SSAFile.transform_framerate()` for fixing bad
                frame-based to time-based conversions.
            kwargs: Extra options for the writer.

        """
        if format_ is None:
            ext = os.path.splitext(path)[1].lower()
            format_ = get_format_identifier(ext)

        with open(path, "w", encoding=encoding) as fp:
            self.to_file(fp, format_, fps=fps, **kwargs)

    def to_string(self, format_, fps=None, **kwargs):
        """
        Get subtitle file as a string.

        See :meth:`SSAFile.save()` for full description.

        Returns:
            str

        """
        fp = io.StringIO()
        self.to_file(fp, format_, fps=fps, **kwargs)
        return fp.getvalue()

    def to_file(self, fp, format_, fps=None, **kwargs):
        """
        Write subtitle file to file object.

        See :meth:`SSAFile.save()` for full description.

        Note:
            This is a low-level method. Usually, one of :meth:`SSAFile.save()`
            or :meth:`SSAFile.to_string()` is preferable.

        Arguments:
            fp (file object): A file object, ie. :class:`io.TextIOBase` instance.
                Note that the file must be opened in text mode (as opposed to binary).

        """
        impl = get_format_class(format_)
        impl.to_file(self, fp, format_, fps=fps, **kwargs)

    # ------------------------------------------------------------------------
    # Retiming subtitles
    # ------------------------------------------------------------------------

    def shift(self, h=0, m=0, s=0, ms=0, frames=None, fps=None):
        """
        Shift all subtitles by constant time amount.

        Shift may be time-based (the default) or frame-based. In the latter
        case, specify both frames and fps. h, m, s, ms will be ignored.

        Arguments:
            h, m, s, ms: Integer or float values, may be positive or negative.
            frames (int): When specified, must be an integer number of frames.
                May be positive or negative. fps must be also specified.
            fps (float): When specified, must be a positive number.

        """
        # XXX what exceptions are raised?
        delta = make_time(h=h, m=m, s=s, ms=ms, frames=frames, fps=fps)
        for line in self:
            line.start += delta
            line.end += delta

    def transform_framerate(self, in_fps, out_fps):
        """
        Rescale all timestamps by ratio of in_fps/out_fps.

        Can be used to fix files converted from frame-based to time-based
        with wrongly assumed framerate.

        Arguments:
            in_fps (float)
            out_fps (float)

        Returns:
            None

        Raises:
            ValueError: Non-positive framerate given.

        """
        if in_fps <= 0 or out_fps <= 0:
            raise ValueError("Framerates must be positive, cannot transform %f -> %f" % (in_fps, out_fps))

        ratio = in_fps / out_fps
        for line in self:
            line.start = int(round(line.start * ratio))
            line.end = int(round(line.end * ratio))

    # ------------------------------------------------------------------------
    # Working with styles
    # ------------------------------------------------------------------------

    def rename_style(self, old_name, new_name):
        """
        Rename a style, including references to it.

        Arguments:
            old_name (str): Style to be renamed.
            new_name (str): New name for the style.

        Raises:
            KeyError: No style named old_name.
            ValueError: new_name is not a legal name (cannot use commas)
                or new_name is taken.

        """
        if old_name not in self.styles:
            raise KeyError("Style %r not found" % old_name)
        if new_name in self.styles:
            raise ValueError("There is already a style called %r" % new_name)
        if not is_valid_field_content(new_name):
            raise ValueError("%r is not a valid name" % new_name)

        self.styles[new_name] = self.styles[old_name]
        del self.styles[old_name]

        for line in self:
            # XXX also handle \r override tag
            if line.style == old_name:
                line.style = new_name

    def import_styles(self, subs, overwrite=True):
        """
        Merge in styles from other SSAFile.

        Arguments:
            subs (SSAFile): Subtitle file imported from.
            overwrite (bool): On name conflict, use style from the other file
                (default: True).

        """
        if not isinstance(subs, SSAFile):
            raise TypeError("Must supply an SSAFile.")

        for name, style in subs.styles.items():
            if name not in self.styles or overwrite:
                self.styles[name] = style

    # ------------------------------------------------------------------------
    # Helper methods
    # ------------------------------------------------------------------------

    def equals(self, other):
        """
        Equality of two SSAFiles.

        Compares :attr:`SSAFile.info`, :attr:`SSAFile.styles` and :attr:`SSAFile.events`.
        Useful mostly in unit tests.

        """
        if isinstance(other, SSAFile):
            return self.info == other.info and self.styles == other.styles and \
                    len(self.events) == len(other.events) and \
                    all(starmap(SSAEvent.equals, zip(self.events, other.events)))
        else:
            raise TypeError("Cannot compare to non-SSAFile object")

    # ------------------------------------------------------------------------
    # MutableSequence implementation
    # ------------------------------------------------------------------------

    def __getitem__(self, item):
        return self.events[item]

    def __setitem__(self, key, value):
        if isinstance(value, SSAEvent):
            self.events[key] = value
        else:
            raise TypeError("SSAFile.events must contain only SSAEvent objects")

    def __delitem__(self, key):
        del self.events[key]

    def __len__(self):
        return len(self.events)

    def insert(self, index, value):
        if isinstance(value, SSAEvent):
            self.events.insert(index, value)
        else:
            raise TypeError("SSAFile.events must contain only SSAEvent objects")
