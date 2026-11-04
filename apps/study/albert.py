"""Read the timed, weekly events emitted by Albert's class calendar export."""

import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo


WEEKDAYS = ('MO', 'TU', 'WE', 'TH', 'FR', 'SA', 'SU')


def _date(value):
    return datetime.strptime(value.removesuffix('Z'), '%Y%m%dT%H%M%S').replace(
        tzinfo=timezone.utc if value.endswith('Z') else ZoneInfo('America/New_York'),
    )


def _text(value):
    return re.sub(r'\\([nN,;\\])', lambda m: ' ' if m[1].lower() == 'n' else m[1], value).strip()


def parse_calendar(upload):
    if not upload or upload.size > 256 * 1024:
        raise ValueError('Choose an Albert .ics file smaller than 256 KB.')
    content = '\n'.join(upload.read().decode('utf-8-sig').splitlines())
    content = re.sub(r'\n[ \t]', '', content).strip()
    term = re.search(r'^X-WR-CALNAME:Class Calendar - ((?:Spring|Summer|Fall|Winter) \d{4})\s*$', content, re.M)
    if not term or not content.startswith('BEGIN:VCALENDAR') or not content.endswith('END:VCALENDAR'):
        raise ValueError('Download the Class Calendar .ics file from Albert and try again.')
    events = {}
    entries = re.findall(r'^BEGIN:VEVENT\n(.*?)^END:VEVENT[ \t]*$', content, re.M | re.S)
    if not 1 <= len(entries) <= 100 or len(entries) != content.count('BEGIN:VEVENT'):
        raise ValueError('This file does not contain a supported class schedule.')
    for raw in entries:
        fields = {}
        for line in raw.splitlines():
            key, _, value = line.partition(':')
            name, _, params = key.partition(';')
            if name in {'DTSTART', 'DTEND', 'EXDATE'} and params not in {'', 'TZID=America/New_York'}:
                raise ValueError('This calendar uses an unsupported class time format.')
            fields.setdefault(name, []).append(value)
        if fields.get('STATUS') == ['CANCELLED']:
            continue
        try:
            uid = fields['UID'][0]
            title = _text(fields['SUMMARY'][0])
            start, end = (_date(fields[key][0]) for key in ('DTSTART', 'DTEND'))
            if (not title or not uid or len(title) > 200 or len(uid) > 255 or uid in events
                    or not start < end <= start + timedelta(days=1)
                    or {'RECURRENCE-ID', 'RDATE', 'EXRULE'} & fields.keys()):
                raise ValueError
            excluded = {_date(value) for group in fields.get('EXDATE', []) for value in group.split(',')}
            if 'RRULE' in fields:
                rule = dict(part.split('=', 1) for part in fields['RRULE'][0].split(';'))
                until = _date(rule['UNTIL'])
                days = rule['BYDAY'].split(',')
                if (set(rule) != {'FREQ', 'UNTIL', 'BYDAY'} or rule['FREQ'] != 'WEEKLY'
                        or not start <= until <= start + timedelta(days=240)
                        or any(day not in WEEKDAYS for day in days)):
                    raise ValueError
                candidates = (start + timedelta(days=i) for i in range(241)
                              if WEEKDAYS[(start.weekday() + i) % 7] in days)
                starts = {start} | {at for at in candidates if at <= until}
            else:
                starts = {start}
        except (KeyError, ValueError, OverflowError) as exc:
            raise ValueError('A class entry has missing or unsupported dates. Export a fresh calendar from Albert.') from exc
        events[uid] = {
            'title': title,
            'location': _text(fields.get('LOCATION', [''])[0])[:255],
            'times': [(at, end + (at - start)) for at in sorted(starts - excluded)],
        }
    if not any(event['times'] for event in events.values()):
        raise ValueError('This file does not contain a supported class schedule.')
    return term[1], events
