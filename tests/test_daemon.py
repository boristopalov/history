from history.collectors.base import Collector
from history.daemon import run_collectors
from history.models import Batch, Event


def counting_collector(name="numbers", upto=3):
    def collect(cursor):
        for n in range(int(cursor or 0) + 1, upto + 1):
            event = Event(source=name, source_id=str(n), ts=n)
            yield Batch(collector=name, cursor=str(n), events=[event])

    return Collector(name=name, source=name, collect=collect)


def count(api):
    return len(api.get("/timeline").json())


def test_second_run_resumes_from_the_committed_cursor(api):
    run_collectors(api, [counting_collector(upto=3)])
    assert count(api) == 3
    run_collectors(api, [counting_collector(upto=5)])
    assert count(api) == 5
    assert api.get("/cursors").json() == {"numbers": "5"}


def test_crash_mid_collection_keeps_what_was_committed_and_resumes(api):
    def crashes_after_two(cursor):
        for batch in counting_collector().collect(cursor):
            if batch.cursor == "3":
                raise RuntimeError("source went away")
            yield batch

    run_collectors(api, [Collector("numbers", "numbers", crashes_after_two)])
    assert api.get("/cursors").json() == {"numbers": "2"}
    run_collectors(api, [counting_collector()])
    assert count(api) == 3


def test_one_failing_source_does_not_stop_the_others(api):
    def broken(cursor):
        raise RuntimeError("no access")

    run_collectors(api, [Collector("broken", "broken", broken), counting_collector()])
    assert count(api) == 3
