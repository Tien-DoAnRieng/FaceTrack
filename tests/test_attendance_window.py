from datetime import datetime, timezone
from unittest.mock import Mock
from app.attendance import attendance_state, eligible_time


def test_open_window_expires_and_obeys_vietnamese_day():
    session = {'id': 1, 'startsAt': '2026-10-23T01:00:00Z', 'endsAt': '2026-10-23T02:30:00Z'}
    db = Mock()
    db.all.return_value = [{'state': 'open'}]
    during = datetime(2026, 10, 23, 1, 30, tzinfo=timezone.utc)
    after = datetime(2026, 10, 23, 3, tzinfo=timezone.utc)
    assert eligible_time(session, during)
    assert attendance_state(db, session, during) == 'open'
    assert not eligible_time(session, after)
    assert attendance_state(db, session, after) == 'closed'
    assert not eligible_time(session, datetime(2026, 10, 22, 1, 30, tzinfo=timezone.utc))
    # A class just after midnight cannot be opened on the previous VN day.
    session['startsAt'] = '2026-10-22T17:05:00Z'
    session['endsAt'] = '2026-10-22T18:30:00Z'
    assert not eligible_time(session, datetime(2026, 10, 22, 16, 55, tzinfo=timezone.utc))
