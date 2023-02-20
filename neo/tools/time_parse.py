# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2023 sardonicism-04
"""
Implements an extremely simple mechanism for parsing a datetime object out of
a string of text.
"""
import re
from datetime import datetime, timedelta, tzinfo
from typing import NoReturn

from neo.tools import try_or_none

ABSOLUTE_FORMATS = {  # Use a set to avoid duplicates
    "%b %d, %Y",
    "%H:%M",
    "%I:%M %p",
    "%b %d, %Y at %H:%M",
    "%b %d, %Y at %I:%M %p",
    "%b %d",
    "%b %d at %H:%M",
    "%b %d at %I:%M %p",
}  # Define a very rigid set of formats that can be passed
ABSOLUTE_FORMATS |= {i.replace(r"%b", "%B") for i in ABSOLUTE_FORMATS}
RELATIVE_FORMATS = re.compile(
    r"""
    ((?P<years>[0-9]{1,2})\s?(?:y(ears?)?,?))?         # Parse years, allow 1-2 digits
    \s?((?P<weeks>[0-9]{1,2})\s?(?:w(eeks?)?,?))?      # Parse weeks, allow 1-2 digits
    \s?((?P<days>[0-9]{1,4})\s?(?:d(ays?)?,?))?        # Parse days, allow 1-4 digits
    \s?((?P<hours>[0-9]{1,4})\s?(?:h(ours?)?,?))?      # Parse hours, allow 1-4 digits
    \s?((?P<minutes>[0-9]{1,4})\s?(?:m(inutes?)?,?))?  # Parse minutes, allow 1-4 digits
    \s?((?P<seconds>[0-9]{1,4})\s?(?:s(econds?)?))?    # Parse seconds, allow 1-4 digits
    """,
    re.X | re.I,
)


def humanize_timedelta(delta: timedelta) -> str:
    """Humanizes the components of a timedelta"""
    return ", ".join(
        (
            f"{delta.days // 365} years",
            f"{delta.days % 365} days",
            f"{delta.seconds // 3600} hours",
            f"{delta.seconds % 3600 // 60} minutes",
            f"{delta.seconds % 3600 % 60} seconds",
        )
    )


class TimedeltaWithYears(timedelta):
    def __new__(
        cls,
        *,
        years: float = 0,
        weeks: float = 0,
        days: float = 0,
        hours: float = 0,
        minutes: float = 0,
        seconds: float = 0,
    ):
        days = days + (years * 365)
        return super().__new__(
            cls,
            weeks=weeks,
            days=days,
            hours=hours,
            minutes=minutes,
            seconds=seconds,
        )


def parse_absolute(
    string: str, *, tz: tzinfo
) -> tuple[datetime, str] | NoReturn:
    """
    Attempts to parse a datetime from a string of text.

    The `string` argument is split into an array by spaces, is tested against
    each format in `ABSOLUTE_FORMATS`. `datetime.strptime` attempts to parse
    the string with each format. If all formats fail, then one element is
    removed from the end of the split string. This repeats until either a valid
    parsing is found, or the string list has been emptied.

    Example: string is "3:00 PM foo bar"
        -> ["3:00", "PM", "foo", "bar"] *no parsing*
        -> ["3:00", "PM", "foo""] *no parsing*
        -> ["3:00", "PM"] *matches %I:%M %p*, return parsed datetime

    :param string: The string to attempt to parse a datetime from
    :type string: ``str``

    :param tz: The timezone to set the returnd datetime to
    :type tz: ``datetime.tzinfo``

    :return: A tuple with the parsed datetime and the unparsed string content
    :rtype: ``tuple[datetime.datetime, str]``

    :raises ValueError: If no valid datetime could be parsed
    """
    split = string.split(" ")
    endpoint = len(split)
    now = datetime.now(tz)

    for _ in range(len(split)):  # Check for every possible chunk size
        to_parse = split[
            :endpoint
        ]  # Check the string in left-to-right increments
        # e.g. ["May", "14", "at", "12:34", "some", "text"] removes elements from the right
        # until the full list, when joined with a whitespace, matches one of the strptime formats

        parsed_datetime = None
        for format in ABSOLUTE_FORMATS:
            raw_parsed_dt = try_or_none(
                datetime.strptime, " ".join(to_parse), format
            )
            if raw_parsed_dt:
                parsed_datetime = raw_parsed_dt.replace(tzinfo=tz)

                # N.B. If no year is provided in the parsed timestamp, it will be
                # set to 1900, so this bit of code resolves the year to the current
                # year when it isn't given
                if parsed_datetime.year < now.year:
                    parsed_datetime = parsed_datetime.replace(year=now.year)

                # If after resolving the year the timestamp is still before now,
                # it's assumed to be a time in the current day, therefore the
                # datetime is updated to be a copy of now, with the hour and
                # minute adjusted
                if parsed_datetime < now:
                    parsed_datetime = now.replace(
                        hour=parsed_datetime.hour,
                        minute=parsed_datetime.minute,
                    )
                break

        if parsed_datetime is not None:  # We got a hit
            break
        endpoint -= 1  # Decrease the size of the chunk by one word

    else:
        raise ValueError("An invalid date format was provided.")

    # If the parsed time is still earlier than now, push it forward by a day
    if parsed_datetime < now:
        parsed_datetime += timedelta(days=1)

    return parsed_datetime.replace(second=0), " ".join(
        string.split(" ")[endpoint:]
    )


def parse_relative(
    string: str,
) -> tuple[TimedeltaWithYears, str] | NoReturn:
    """
    Attempts to parse a relative time offset from a string of text.

    The `string` argument is matched against the `RELATIVE_FORMATS` regex, which
    attempts to group all time denominations. If successful, a timedelta is
    returned

    :param string: The string to attempt to parse
    :type string: ``str``

    :return: A tuple with the parsed timedelta and the unparsed string content
    :rtype: ``tuple[TimedeltaWithYears, Str]``

    :raises ValueError: If no valid delta could be parsed
    """
    parsed = RELATIVE_FORMATS.match(string)

    if parsed and any(parsed.groups()):
        data = {k: float(v) for k, v in parsed.groupdict().items() if v}
        return (
            TimedeltaWithYears(**data),
            string.removeprefix(parsed[0]).strip(),
        )

    else:  # Nothing matched
        raise ValueError("Failed to find a valid offset.")
