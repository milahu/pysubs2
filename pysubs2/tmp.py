import re
import warnings

from .formatbase import FormatBase
from .ssaevent import SSAEvent
from .ssastyle import SSAStyle
from .substation import parse_tags
from .time import ms_to_times, make_time, TIMESTAMP_SHORT, timestamp_to_ms

#: Pattern that matches TMP line
TMP_LINE = re.compile(rb"(\d{1,2}:\d{2}:\d{2}):(.+)")

#: Largest timestamp allowed in Tmp, ie. 99:59:59.
MAX_REPRESENTABLE_TIME = make_time(h=99, m=59, s=59)


class TmpFormat(FormatBase):
    """TMP subtitle format implementation"""

    @staticmethod
    def ms_to_timestamp(ms: int) -> str:
        """Convert ms to 'HH:MM:SS'"""
        if ms < 0:
            ms = 0
        if ms > MAX_REPRESENTABLE_TIME:
            warnings.warn("Overflow in TMP timestamp, clamping to MAX_REPRESENTABLE_TIME", RuntimeWarning)
            ms = MAX_REPRESENTABLE_TIME
        h, m, s, _ = ms_to_times(ms)
        return f"{h:02d}:{m:02d}:{s:02d}"

    @classmethod
    def guess_format(cls, text):
        """See :meth:`pysubs2.formats.FormatBase.guess_format()`"""
        if b"[Script Info]" in text or b"[V4+ Styles]" in text:
            # disambiguation vs. SSA/ASS
            return None

        for line in text.splitlines():
            if TMP_LINE.match(line) and len(TMP_LINE.findall(line)) == 1:
                return "tmp"

    @classmethod
    def from_file(cls, subs, fp, format_, **kwargs):
        """See :meth:`pysubs2.formats.FormatBase.from_file()`"""
        events = []

        def prepare_text(text):
            text = text.replace(b"|", rb"\N")  # convert newlines
            text = re.sub(rb"< *u *>", b"{\\\\u1}", text) # not rb" for Python 2.7 compat, triggers unicodeescape
            text = re.sub(rb"< */? *[a-zA-Z][^>]*>", b"", text) # strip other HTML tags
            return text

        for line in fp:
            match = TMP_LINE.match(line)
            if not match:
                continue

            start, text = match.groups()
            start = timestamp_to_ms(TIMESTAMP_SHORT.match(start).groups())

            # Unfortunately, end timestamp is not given; try to estimate something reasonable:
            # start + 500 ms + 67 ms/character (15 chars per second)
            end_guess = start + 500 + (len(line) * 67)

            event = SSAEvent(start=start, end=end_guess, text=prepare_text(text))
            events.append(event)

        # correct any overlapping subtitles created by end_guess
        for i in range(len(events) - 1):
            events[i].end = min(events[i].end, events[i+1].start)

        subs.events = events

    @classmethod
    def to_file(cls, subs, fp, format_, apply_styles=True, **kwargs):
        """
        See :meth:`pysubs2.formats.FormatBase.to_file()`

        Italic, underline and strikeout styling is supported.

        Keyword args:
            apply_styles: If False, do not write any styling.

        """
        def prepare_text(text, style):
            body = []
            skip = False
            for fragment, sty in parse_tags(text, style, subs.styles):
                fragment = fragment.replace(rb"\h", b" ")
                fragment = fragment.replace(rb"\n", b"\n")
                fragment = fragment.replace(rb"\N", b"\n")
                if apply_styles:
                    if sty.italic: fragment = f"<i>{fragment}</i>"
                    if sty.underline: fragment = f"<u>{fragment}</u>"
                    if sty.strikeout: fragment = f"<s>{fragment}</s>"
                if sty.drawing: skip = True
                body.append(fragment)

            if skip:
                return ""
            else:
                return re.sub(b"\n+", b"\n", "".join(body).strip())

        visible_lines = (line for line in subs if not line.is_comment)

        for line in visible_lines:
            start = cls.ms_to_timestamp(line.start)
            text = prepare_text(line.text, subs.styles.get(line.style, SSAStyle.DEFAULT_STYLE))

            print(start + b":" + text, end="\n", file=fp)
