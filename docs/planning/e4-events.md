# E4 — NYU events

Use [NYU Engage’s public RSS feed](https://engage.nyu.edu/events.rss), linked from its [events directory](https://engage.nyu.edu/events). No student credentials are needed.

1. Import events and show an authenticated list and details, with Eastern times and links back to Engage.
2. Add date/category filters and career discovery (#24, #26). Campus filtering needs a verified venue mapping; the feed has no campus field.
3. Add saved events to the personal calendar (#28), then friend invitations/attendance (#25, #27) and interest-based recommendations (#33).

Import by stable Engage ID, update changed details and cancellations, and preserve good data on failure. Descriptions are plain text. Refresh through a server-side command; never fetch on each page view.

The November 16 feed check returned 769 entries. Coverage differs from the public directory, so this is not the complete NYU catalog. Attribute Engage and keep registration there.

## Run locally or after deployment

Install requirements, then run:

```sh
python manage.py migrate
python manage.py sync_engage_events
```

Open `/app/events` while signed in. The sync is a management command, not a public API. A deployment operator should schedule it (suggested hourly); no scheduler or deployment is changed by this branch. A failed run exits with an error and retains the previous dataset. The page shows the last successful refresh and warns after 24 hours.

This slice provides import, browse/details, text/date/category filters and a career-category shortcut (#24, partial #26). Campus filtering remains pending verified venue data. Saving, invitations, attendance and recommendations remain follow-ups; this does not complete E4.

Discovery shows only events whose start is in the future, ordered soonest first. It excludes long-running entries that started in prior months and events that started earlier today. Date filters use Eastern start dates. The page refreshes every minute and when the window regains focus. This is time filtering, not a check against the student’s personal schedule. Missing entries are retained rather than treated as cancellations. Explicitly cancelled entries disappear from discovery but their detail links still show the cancellation. Career filtering follows the source category exactly and cannot guarantee every career-related event.
