import re
import urllib
import os
import sys
from collections import MutableMapping

_timer_re = re.compile('([+-])?(\d+:)?(\d+):(\d+)(.\d+)?')

_WHITESPACE_REGEXP = re.compile('\s+')

if sys.platform == 'cli' and sys.version_info < (2, 7, 5):
    def lower(string):
        return ('A' + string).lower()[1:]
else:
    def lower(string):
        return string.lower()

def is_integer(item):
    return isinstance(item, (int, long))

def is_string(item):
    return isinstance(item, basestring)

def is_number(item):
    return isinstance(item, (int, long, float))

def plural_or_not(item):
    count = item if is_integer(item) else len(item)
    return '' if count == 1 else 's'

def normalize(string, ignore=(), caseless=True, spaceless=True):
    """Normalizes given string according to given spec.
    By default string is turned to lower case and all whitespace is removed.
    Additional characters can be removed by giving them in `ignore` list.
    """
    if spaceless:
        string = _WHITESPACE_REGEXP.sub('', string)
    if caseless:
        string = lower(string)
        ignore = [lower(i) for i in ignore]
    for ign in ignore:
        if ign in string:  # performance optimization
            string = string.replace(ign, '')
    return string

def secs_to_timestr(secs, compact=False):
    """Converts time in seconds to a string representation.
    Returned string is in format like
    '1 day 2 hours 3 minutes 4 seconds 5 milliseconds' with following rules:
    - Time parts having zero value are not included (e.g. '3 minutes 4 seconds'
      instead of '0 days 0 hours 3 minutes 4 seconds')
    - Hour part has a maximun of 23 and minutes and seconds both have 59
      (e.g. '1 minute 40 seconds' instead of '100 seconds')
    If compact has value 'True', short suffixes are used.
    (e.g. 1d 2h 3min 4s 5ms)
    """
    return _SecsToTimestrHelper(secs, compact).get_value()

def timestr_to_secs(timestr, round_to=3):
    """Parses time like '1h 10s', '01:00:10' or '42' and returns seconds."""
    if is_string(timestr) or is_number(timestr):
        for converter in _number_to_secs, _timer_to_secs, _time_string_to_secs:
            secs = converter(timestr)
            if secs is not None:
                return secs if round_to is None else round(secs, round_to)
    raise ValueError("Invalid time string '%s'." % timestr)

def _number_to_secs(number):
    try:
        return float(number)
    except ValueError:
        return None

def _normalize_timestr(timestr):
    timestr = normalize(timestr)
    for specifier, aliases in [('x', ['millisecond', 'millisec', 'millis',
                                      'msec', 'ms']),
                               ('s', ['second', 'sec']),
                               ('m', ['minute', 'min']),
                               ('h', ['hour']),
                               ('d', ['day'])]:
        plural_aliases = [a+'s' for a in aliases if not a.endswith('s')]
        for alias in plural_aliases + aliases:
            if alias in timestr:
                timestr = timestr.replace(alias, specifier)
    return timestr

def _timer_to_secs(number):
    match = _timer_re.match(number)
    if not match:
        return None
    prefix, hours, minutes, seconds, millis = match.groups()
    seconds = float(minutes) * 60 + float(seconds)
    if hours:
        seconds += float(hours[:-1]) * 60 * 60
    if millis:
        seconds += float(millis[1:]) / 10**len(millis[1:])
    if prefix == '-':
        seconds *= -1
    return seconds

def _time_string_to_secs(timestr):
    timestr = _normalize_timestr(timestr)
    if not timestr:
        return None
    millis = secs = mins = hours = days = 0
    if timestr[0] == '-':
        sign = -1
        timestr = timestr[1:]
    else:
        sign = 1
    temp = []
    for c in timestr:
        try:
            if   c == 'x': millis = float(''.join(temp)); temp = []
            elif c == 's': secs   = float(''.join(temp)); temp = []
            elif c == 'm': mins   = float(''.join(temp)); temp = []
            elif c == 'h': hours  = float(''.join(temp)); temp = []
            elif c == 'd': days   = float(''.join(temp)); temp = []
            else: temp.append(c)
        except ValueError:
            return None
    if temp:
        return None
    return sign * (millis/1000 + secs + mins*60 + hours*60*60 + days*60*60*24)

def _float_secs_to_secs_and_millis(secs):
    isecs = int(secs)
    millis = int(round((secs - isecs) * 1000))
    return (isecs, millis) if millis < 1000 else (isecs+1, 0)

class _SecsToTimestrHelper:

    def __init__(self, float_secs, compact):
        self._compact = compact
        self._ret = []
        self._sign, millis, secs, mins, hours, days \
                = self._secs_to_components(float_secs)
        self._add_item(days, 'd', 'day')
        self._add_item(hours, 'h', 'hour')
        self._add_item(mins, 'min', 'minute')
        self._add_item(secs, 's', 'second')
        self._add_item(millis, 'ms', 'millisecond')

    def get_value(self):
        if len(self._ret) > 0:
            return self._sign + ' '.join(self._ret)
        return '0s' if self._compact else '0 seconds'

    def _add_item(self, value, compact_suffix, long_suffix):
        if value == 0:
            return
        if self._compact:
            suffix = compact_suffix
        else:
            suffix = ' %s%s' % (long_suffix, plural_or_not(value))
        self._ret.append('%d%s' % (value, suffix))

    def _secs_to_components(self, float_secs):
        if float_secs < 0:
            sign = '- '
            float_secs = abs(float_secs)
        else:
            sign = ''
        int_secs, millis = _float_secs_to_secs_and_millis(float_secs)
        secs  = int_secs % 60
        mins  = int(int_secs / 60) % 60
        hours = int(int_secs / (60*60)) % 24
        days  = int(int_secs / (60*60*24))
        return sign, millis, secs, mins, hours, days

def get_link_path(target, base):
    """Returns a relative path to a target from a base.
    If base is an existing file, then its parent directory is considered.
    Otherwise, base is assumed to be a directory.
    Rationale: os.path.relpath is not available before Python 2.6
    """
    path =  _get_pathname(target, base)
    url = urllib.pathname2url(path.encode('UTF-8'))
    if os.path.isabs(path):
        url = 'file:' + url
    # At least Jython seems to use 'C|/Path' and not 'C:/Path'
    if os.sep == '\\' and '|/' in url:
        url = url.replace('|/', ':/', 1)
    return url.replace('%5C', '/').replace('%3A', ':').replace('|', ':')

def _get_pathname(target, base):
    target = abspath(target)
    base = abspath(base)
    if os.path.isfile(base):
        base = os.path.dirname(base)
    if base == target:
        return os.path.basename(target)
    base_drive, base_path = os.path.splitdrive(base)
    # if in Windows and base and link on different drives
    if os.path.splitdrive(target)[0] != base_drive:
        return target
    common_len = len(_common_path(base, target))
    if base_path == os.sep:
        return target[common_len:]
    if common_len == len(base_drive) + len(os.sep):
        common_len -= len(os.sep)
    dirs_up = os.sep.join([os.pardir] * base[common_len:].count(os.sep))
    return os.path.join(dirs_up, target[common_len + len(os.sep):])

class NormalizedDict(MutableMapping):
    """Custom dictionary implementation automatically normalizing keys."""

    def __init__(self, initial=None, ignore=(), caseless=True, spaceless=True):
        """Initializes with possible initial value and normalizing spec.
        Initial values can be either a dictionary or an iterable of name/value
        pairs. In the latter case items are added in the given order.
        Normalizing spec has exact same semantics as with `normalize` method.
        """
        self._data = {}
        self._keys = {}
        self._normalize = lambda s: normalize(s, ignore, caseless, spaceless)
        if initial:
            self._add_initial(initial)

    def _add_initial(self, initial):
        items = initial.items() if hasattr(initial, 'items') else initial
        for key, value in items:
            self[key] = value

    def __getitem__(self, key):
        return self._data[self._normalize(key)]

    def __setitem__(self, key, value):
        norm_key = self._normalize(key)
        self._data[norm_key] = value
        self._keys.setdefault(norm_key, key)

    def __delitem__(self, key):
        norm_key = self._normalize(key)
        del self._data[norm_key]
        del self._keys[norm_key]

    def __iter__(self):
        return (self._keys[norm_key] for norm_key in sorted(self._keys))

    def __len__(self):
        return len(self._data)

    def __str__(self):
        return str(dict(self.items()))

    def __eq__(self, other):
        if not is_dict_like(other):
            return False
        if not isinstance(other, NormalizedDict):
            other = NormalizedDict(other)
        return self._data == other._data

    def copy(self):
        copy = NormalizedDict()
        copy._data = self._data.copy()
        copy._keys = self._keys.copy()
        copy._normalize = self._normalize
        return copy

    def clear(self):
        # Faster than default implementation of MutableMapping.clear
        self._data.clear()
        self._keys.clear()


class ConnectionCache(object):
    """Cache for test libs to use with concurrent connections, processes, etc.
    The cache stores the registered connections (or other objects) and allows
    switching between them using generated indices or user given aliases.
    This is useful with any test library where there's need for multiple
    concurrent connections, processes, etc.
    This class can, and is, used also outside the core framework by SSHLibrary,
    Selenium(2)Library, etc. Backwards compatibility is thus important when
    doing changes.
    """

    def __init__(self, no_current_msg='No open connection.'):
        self._no_current = NoConnection(no_current_msg)
        self.current = self._no_current  #: Current active connection.
        self._connections = []
        self._aliases = NormalizedDict()

    @property
    def current_index(self):
        if not self:
            return None
        for index, conn in enumerate(self):
            if conn is self.current:
                return index + 1

    @current_index.setter
    def current_index(self, index):
        self.current = self._connections[index - 1] \
            if index is not None else self._no_current

    def register(self, connection, alias=None):
        """Registers given connection with optional alias and returns its index.
        Given connection is set to be the :attr:`current` connection.
        If alias is given, it must be a string. Aliases are case and space
        insensitive.
        The index of the first connection after initialization, and after
        :meth:`close_all` or :meth:`empty_cache`, is 1, second is 2, etc.
        """
        self.current = connection
        self._connections.append(connection)
        index = len(self._connections)
        if is_string(alias):
            self._aliases[alias] = index
        return index

    def switch(self, alias_or_index):
        """Switches to the connection specified by the given alias or index.
        Updates :attr:`current` and also returns its new value.
        Alias is whatever was given to :meth:`register` method and indices
        are returned by it. Index can be given either as an integer or
        as a string that can be converted to an integer. Raises an error
        if no connection with the given index or alias found.
        """
        self.current = self.get_connection(alias_or_index)
        return self.current

    def get_connection(self, alias_or_index=None):
        """Get the connection specified by the given alias or index..
        If ``alias_or_index`` is ``None``, returns the current connection
        if it is active, or raises an error if it is not.
        Alias is whatever was given to :meth:`register` method and indices
        are returned by it. Index can be given either as an integer or
        as a string that can be converted to an integer. Raises an error
        if no connection with the given index or alias found.
        """
        if alias_or_index is None:
            if not self:
                self.current.raise_error()
            return self.current
        try:
            index = self._resolve_alias_or_index(alias_or_index)
        except ValueError:
            raise RuntimeError("Non-existing index or alias '%s'."
                               % alias_or_index)
        return self._connections[index-1]

    __getitem__ = get_connection

    def close_all(self, closer_method='close'):
        """Closes connections using given closer method and empties cache.
        If simply calling the closer method is not adequate for closing
        connections, clients should close connections themselves and use
        :meth:`empty_cache` afterwards.
        """
        for conn in self._connections:
            getattr(conn, closer_method)()
        self.empty_cache()
        return self.current

    def empty_cache(self):
        """Empties the connection cache.
        Indexes of the new connections starts from 1 after this.
        """
        self.current = self._no_current
        self._connections = []
        self._aliases = NormalizedDict()

    def __iter__(self):
        return iter(self._connections)

    def __len__(self):
        return len(self._connections)

    def __nonzero__(self):
        return self.current is not self._no_current

    def _resolve_alias_or_index(self, alias_or_index):
        try:
            return self._resolve_alias(alias_or_index)
        except ValueError:
            return self._resolve_index(alias_or_index)

    def _resolve_alias(self, alias):
        if is_string(alias):
            try:
                return self._aliases[alias]
            except KeyError:
                pass
        raise ValueError

    def _resolve_index(self, index):
        try:
            index = int(index)
        except TypeError:
            raise ValueError
        if not 0 < index <= len(self._connections):
            raise ValueError
        return index


class NoConnection(object):

    def __init__(self, message):
        self.message = message

    def __getattr__(self, name):
        if name.startswith('__') and name.endswith('__'):
            raise AttributeError
        self.raise_error()

    def raise_error(self):
        raise RuntimeError(self.message)

    def __nonzero__(self):
        return False
