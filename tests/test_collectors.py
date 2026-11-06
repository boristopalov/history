import sqlite3
import subprocess
from datetime import datetime

from history.collectors.base import APPLE_EPOCH
from history.collectors.browsers import browser_collectors
from history.collectors.calendar import ics_collector
from history.collectors.git import git_collector
from history.collectors.location import location_collector
from history.collectors.messages import decode_attributed_body, messages_collector
from history.collectors.music import music_collector
from history.collectors.notes import notes_collector
from history.collectors.photos import photos_collector
from history.collectors.transactions import transactions_collector


def make_db(path, script):
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.executescript(script)
    conn.commit()
    conn.close()
    return path


def events_from(collector, cursor=None):
    return [event for batch in collector.collect(cursor) for event in batch.events]


def attributed_body(text):
    data = text.encode()
    if len(data) < 0x80:
        length = bytes([len(data)])
    else:
        length = b"\x81" + len(data).to_bytes(2, "little")
    return b"\x04\x0bstreamtyped\x81\xe8\x03\x84\x01@\x84\x84\x84\x12NSAttributedString\x00\x84\x84\x08NSObject\x00\x85\x92\x84\x84\x84\x08NSString\x01\x94\x84\x01+" + length + data + b"\x86\x84\x02iI"


def test_attributed_body_decodes_short_and_long_text():
    assert decode_attributed_body(attributed_body("hello")) == "hello"
    long_text = "é" * 300
    assert decode_attributed_body(attributed_body(long_text)) == long_text


MESSAGES_SCHEMA = """
CREATE TABLE handle (ROWID INTEGER PRIMARY KEY, id TEXT);
CREATE TABLE message (ROWID INTEGER PRIMARY KEY, guid TEXT, text TEXT, attributedBody BLOB,
    date INTEGER, is_from_me INTEGER, service TEXT, cache_has_attachments INTEGER,
    handle_id INTEGER, item_type INTEGER DEFAULT 0, associated_message_type INTEGER DEFAULT 0);
INSERT INTO handle VALUES (1, '+15551234567');
"""


def test_messages_reads_text_skips_tapbacks_and_resumes(tmp_path):
    path = make_db(tmp_path / "chat.db", MESSAGES_SCHEMA)
    conn = sqlite3.connect(path)
    insert = (
        "INSERT INTO message (ROWID, guid, text, attributedBody, date, is_from_me, service,"
        " cache_has_attachments, handle_id, associated_message_type) VALUES (?,?,?,?,?,?,?,?,?,?)"
    )
    second = 1_000_000_000
    conn.execute(insert, (1, "a", "plain", None, 100 * second, 1, "iMessage", 0, 1, 0))
    conn.execute(insert, (2, "b", None, attributed_body("rich"), 200 * second, 0, "SMS", 0, 1, 0))
    conn.execute(insert, (3, "c", "Loved it", None, 300 * second, 0, "iMessage", 0, 1, 2000))
    conn.commit()
    conn.close()

    collector = messages_collector(path, address_books=[])
    events = events_from(collector)
    assert [e.body for e in events] == ["plain", "rich"]
    assert events[0].ts == 100 + APPLE_EPOCH
    assert events[0].title == "+15551234567"
    assert [e.body for e in events_from(collector, cursor="1")] == ["rich"]


def test_messages_use_contact_names_and_keep_the_handle(tmp_path):
    path = make_db(tmp_path / "chat.db", MESSAGES_SCHEMA)
    book = make_db(
        tmp_path / "book.abcddb",
        """CREATE TABLE ZABCDRECORD (Z_PK INTEGER PRIMARY KEY, ZFIRSTNAME TEXT, ZLASTNAME TEXT);
        CREATE TABLE ZABCDPHONENUMBER (ZOWNER INTEGER, ZFULLNUMBER TEXT);
        CREATE TABLE ZABCDEMAILADDRESS (ZOWNER INTEGER, ZADDRESS TEXT);
        INSERT INTO ZABCDRECORD VALUES (1, 'Ada', 'Lovelace');
        INSERT INTO ZABCDPHONENUMBER VALUES (1, '(555) 123-4567');""",
    )
    conn = sqlite3.connect(path)
    insert = (
        "INSERT INTO message (ROWID, guid, text, date, is_from_me, service,"
        " cache_has_attachments, handle_id) VALUES (?,?,?,?,?,?,?,?)"
    )
    conn.execute(insert, (1, "a", "hi", 100, 0, "iMessage", 0, 1))
    conn.execute(insert, (2, "b", "yo", 200, 1, "iMessage", 0, 0))
    conn.commit()
    conn.close()
    known, mine = events_from(messages_collector(path, address_books=[book]))
    assert known.title == "Ada Lovelace"
    assert known.data["handle"] == "+15551234567"
    assert mine.title == "Me"


def test_missing_database_yields_nothing(tmp_path):
    assert events_from(messages_collector(tmp_path / "absent.db", address_books=[])) == []
    assert events_from(photos_collector(tmp_path / "absent.db")) == []


def test_browsers_read_every_engine_and_skip_noise(tmp_path):
    make_db(
        tmp_path / "Library/Safari/History.db",
        """CREATE TABLE history_items (id INTEGER PRIMARY KEY, url TEXT);
        CREATE TABLE history_visits (id INTEGER PRIMARY KEY, history_item INTEGER,
            visit_time REAL, title TEXT);
        INSERT INTO history_items VALUES (1, 'https://safari.test');
        INSERT INTO history_visits VALUES (1, 1, 100.0, 'S');""",
    )
    support = tmp_path / "Library/Application Support"
    make_db(
        support / "Google/Chrome/Default/History",
        """CREATE TABLE urls (id INTEGER PRIMARY KEY, url TEXT, title TEXT);
        CREATE TABLE visits (id INTEGER PRIMARY KEY, url INTEGER, visit_time INTEGER,
            transition INTEGER);
        INSERT INTO urls VALUES (1, 'https://chrome.test', 'C');
        INSERT INTO visits VALUES (1, 1, 13000000000000000, 805306368);
        INSERT INTO visits VALUES (2, 1, 13000000000000001, 3);""",
    )
    make_db(
        support / "Firefox/Profiles/abc.default/places.sqlite",
        """CREATE TABLE moz_places (id INTEGER PRIMARY KEY, url TEXT, title TEXT);
        CREATE TABLE moz_historyvisits (id INTEGER PRIMARY KEY, place_id INTEGER,
            visit_date INTEGER, visit_type INTEGER);
        INSERT INTO moz_places VALUES (1, 'https://firefox.test', 'F');
        INSERT INTO moz_historyvisits VALUES (1, 1, 1700000000000000, 1);
        INSERT INTO moz_historyvisits VALUES (2, 1, 1700000000000001, 5);""",
    )
    visits = {
        c.name: events_from(c) for c in browser_collectors(home=tmp_path)
    }
    assert {name: len(found) for name, found in visits.items()} == {
        "browser.safari": 1,
        "browser.chrome.Default": 1,
        "browser.firefox.abc.default": 1,
    }
    assert visits["browser.safari"][0].ts == 100 + APPLE_EPOCH
    assert visits["browser.chrome.Default"][0].ts == 13000000000 - 11644473600
    assert visits["browser.firefox.abc.default"][0].ts == 1700000000


def test_browser_visit_without_a_title_shows_the_site(tmp_path):
    make_db(
        tmp_path / "Library/Safari/History.db",
        """CREATE TABLE history_items (id INTEGER PRIMARY KEY, url TEXT);
        CREATE TABLE history_visits (id INTEGER PRIMARY KEY, history_item INTEGER,
            visit_time REAL, title TEXT);
        INSERT INTO history_items VALUES (1, 'https://example.com/a/b');
        INSERT INTO history_visits VALUES (1, 1, 100.0, NULL);""",
    )
    safari = browser_collectors(home=tmp_path)[0]
    assert events_from(safari)[0].title == "example.com"


def test_photos_are_fixes_only_when_geotagged(tmp_path):
    path = make_db(
        tmp_path / "Photos.sqlite",
        """CREATE TABLE ZASSET (ZUUID TEXT, ZFILENAME TEXT, ZDATECREATED REAL, ZLATITUDE REAL,
            ZLONGITUDE REAL, ZKIND INTEGER, ZTRASHEDSTATE INTEGER);
        INSERT INTO ZASSET VALUES ('geo', 'a.jpg', 100, 48.8, 2.3, 0, 0);
        INSERT INTO ZASSET VALUES ('nogeo', 'b.jpg', 100, -180, -180, 0, 0);
        INSERT INTO ZASSET VALUES ('trashed', 'c.jpg', 100, 48.8, 2.3, 0, 1);""",
    )
    events = {e.source_id: e for e in events_from(photos_collector(path))}
    assert set(events) == {"geo", "nogeo"}
    assert events["geo"].is_fix and events["geo"].lat == 48.8
    assert not events["nogeo"].is_fix and events["nogeo"].lat is None


def test_notes_skip_deleted(tmp_path):
    path = make_db(
        tmp_path / "NoteStore.sqlite",
        """CREATE TABLE ZICCLOUDSYNCINGOBJECT (ZIDENTIFIER TEXT, ZTITLE1 TEXT, ZSNIPPET TEXT,
            ZCREATIONDATE1 REAL, ZCREATIONDATE3 REAL, ZMODIFICATIONDATE1 REAL, ZNOTEDATA INTEGER,
            ZMARKEDFORDELETION INTEGER);
        INSERT INTO ZICCLOUDSYNCINGOBJECT VALUES ('n', 'Title', 'Snip', NULL, 100, 200, 1, 0);
        INSERT INTO ZICCLOUDSYNCINGOBJECT VALUES ('d', 'Gone', 'x', NULL, 100, 200, 1, 1);""",
    )
    (note,) = events_from(notes_collector(path))
    assert (note.title, note.body, note.ts) == ("Title", "Snip", 100 + APPLE_EPOCH)


def test_ics_feed_reads_events(tmp_path):
    feed = tmp_path / "luma.ics"
    feed.write_text(
        "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//t//EN\r\nBEGIN:VEVENT\r\nUID:evt-1\r\n"
        "DTSTAMP:20260101T000000Z\r\nDTSTART:20260102T180000Z\r\nDTEND:20260102T200000Z\r\n"
        "SUMMARY:Demo night\r\nLOCATION:Hall\r\nURL:https://lu.ma/x\r\nEND:VEVENT\r\n"
        "END:VCALENDAR\r\n"
    )
    (event,) = events_from(ics_collector(str(feed), 0))
    assert event.title == "Demo night"
    assert event.url == "https://lu.ma/x"
    assert event.data["place"] == "Hall"
    assert event.ts == datetime.fromisoformat("2026-01-02T18:00:00+00:00").timestamp()


def test_location_log_resumes_and_leaves_a_half_written_line(tmp_path):
    log = tmp_path / "location.jsonl"
    log.write_text('{"ts": 1.0, "lat": 1.0, "lon": 2.0}\n{"ts": 2.0, "lat"')
    collector = location_collector(log)
    (batch,) = list(collector.collect(None))
    assert [e.ts for e in batch.events] == [1.0]
    assert batch.events[0].is_fix

    with log.open("a") as f:
        f.write(': 3.0, "lon": 4.0}\n')
    (batch,) = list(collector.collect(batch.cursor))
    assert [e.lat for e in batch.events] == [3.0]


def test_git_keeps_only_your_commits(tmp_path):
    repo = tmp_path / "proj"
    repo.mkdir()

    def git(*args, email):
        subprocess.run(
            ["git", "-c", f"user.email={email}", "-c", "user.name=x", *args],
            cwd=repo, check=True, capture_output=True,
        )

    git("init", email="me@test")
    git("commit", "--allow-empty", "-m", "mine", email="me@test")
    git("commit", "--allow-empty", "-m", "theirs", email="other@test")
    (commit,) = events_from(git_collector([tmp_path], ["ME@test"]))
    assert commit.title == "mine"
    assert commit.data["repo"] == "proj"


def test_a_commit_in_two_clones_has_one_id(tmp_path):
    repo = tmp_path / "proj"
    repo.mkdir()
    env = ["-c", "user.email=me@test", "-c", "user.name=x"]
    subprocess.run(["git", *env, "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", *env, "commit", "--allow-empty", "-m", "one"],
        cwd=repo, check=True, capture_output=True,
    )
    subprocess.run(["git", "clone", str(repo), str(tmp_path / "copy")], check=True, capture_output=True)
    events = events_from(git_collector([tmp_path], ["me@test"]))
    assert len(events) == 2
    assert len({e.source_id for e in events}) == 1


def test_transactions_dedupe_across_exports_but_keep_real_repeats(tmp_path):
    rows = "Transaction Date,Description,Amount\n01/15/2026,COFFEE,4.50\n01/15/2026,COFFEE,4.50\n"
    (tmp_path / "jan.csv").write_text(rows)
    (tmp_path / "jan-again.csv").write_text(rows)
    events = events_from(transactions_collector(tmp_path))
    assert len({e.source_id for e in events}) == 2
    assert events[0].data["amount"] == "4.50"
    assert datetime.fromtimestamp(events[0].ts) == datetime(2026, 1, 15, 12)


def test_music_keeps_one_event_per_play_across_samples(tmp_path):
    sep = "\x1f"

    def sample(position, now):
        def ask(app):
            return sep.join(["id1", "Track", "Artist", "Album", str(position)])

        return events_from(music_collector(ask=ask, now=lambda: now))[0]

    first = sample(position=10.0, now=1_000_010.0)
    later = sample(position=70.5, now=1_000_070.0)
    assert first.source_id == later.source_id
    assert first.title == "Track — Artist"
