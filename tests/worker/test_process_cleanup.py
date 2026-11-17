from types import SimpleNamespace
from unittest.mock import Mock, patch

from sanic.worker.manager import WorkerManager
from sanic.worker.process import WorkerProcess


def make_worker(process, state):
    return WorkerProcess(
        factory=Mock(return_value=process),
        name="Sanic-Server-0-0",
        ident="0",
        target=Mock(),
        kwargs={},
        worker_state=state,
    )


def test_exit_force_kills_worker_stuck_after_shutdown():
    process = Mock()
    process.pid = 12345
    process.is_alive.side_effect = lambda: not process.kill.called
    state = {}
    worker = make_worker(process, state)

    with patch("sanic.worker.process.sleep") as sleep:
        worker.exit()

    assert sleep.call_count == 100
    process.kill.assert_called_once_with()
    process.join.assert_called_once_with(timeout=1)
    assert worker.name not in state


def test_exit_does_not_kill_already_stopped_worker():
    process = Mock()
    process.pid = 12345
    process.is_alive.return_value = False
    state = {}
    worker = make_worker(process, state)

    worker.exit()

    process.kill.assert_not_called()
    process.join.assert_not_called()
    assert worker.name not in state


def test_manager_cleanup_waits_once_for_all_stuck_workers():
    process_a = Mock(pid=12345)
    process_b = Mock(pid=12346)
    for process in (process_a, process_b):
        process.is_alive.side_effect = lambda p=process: not p.kill.called

    state = {}
    workers = [make_worker(process_a, state), make_worker(process_b, state)]
    manager = SimpleNamespace(processes=workers)

    with (
        patch("sanic.worker.process.sleep") as process_sleep,
        patch("sanic.worker.manager.sleep", create=True) as manager_sleep,
    ):
        WorkerManager.cleanup(manager)

    # Ten seconds of grace is shared by every process, not multiplied by
    # the number of surviving processes during a shutdown race.
    assert manager_sleep.call_count == 100
    assert process_sleep.call_count == 0
    process_a.kill.assert_called_once_with()
    process_b.kill.assert_called_once_with()
    assert not state
