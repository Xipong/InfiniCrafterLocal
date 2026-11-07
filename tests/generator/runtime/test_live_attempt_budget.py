"""Recovered budget behavior, independent of provider configuration or auth."""
from __future__ import annotations

import concurrent.futures
import multiprocessing
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from toolbox.live.budget import (
    BudgetExhausted, budget_status, finish_attempt, initialize_budget, reserve_attempt,
)


def _reserve_worker(args: tuple[str, str]) -> str:
    path, identity = args
    try:
        reserve_attempt(Path(path), attempt_id=identity, case_id='test', kind='full_craft')
        return 'reserved'
    except BudgetExhausted:
        return 'exhausted'
    except ValueError:
        return 'duplicate'


def _crash_after_reservation(path: str) -> None:
    reserve_attempt(Path(path), attempt_id='process-crash', case_id='test', kind='stage_only')
    os._exit(23)


class AttemptBudgetTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / 'budget.sqlite'

    def initialize(self, ceiling: int = 140, opening: int = 51) -> dict:
        return initialize_budget(self.path, ceiling=ceiling, opening_debit=opening,
                                 opening_note='Recovered aggregate from trusted conversation, not original ledger')

    def test_opening_is_one_policy_not_fabricated_attempts(self) -> None:
        status = self.initialize()
        self.assertEqual((status['charged'], status['remaining'], status['newAttempts']), (51, 89, 0))
        with sqlite3.connect(self.path) as connection:
            self.assertEqual(connection.execute('SELECT count(*) FROM attempts').fetchone()[0], 0)
        self.assertEqual(status, self.initialize())

    def test_missing_ledger_refuses_reads_and_admission(self) -> None:
        with self.assertRaises(sqlite3.OperationalError):
            budget_status(self.path)
        with self.assertRaises(sqlite3.OperationalError):
            reserve_attempt(self.path, attempt_id='x', case_id='x', kind='full_craft')
        self.assertFalse(self.path.exists())

    def test_policy_cannot_reset_or_change(self) -> None:
        self.initialize()
        for ceiling, opening, note in ((141, 51, 'changed'), (140, 0, 'reset'), (140, 51, 'changed')):
            with self.assertRaises(ValueError):
                initialize_budget(self.path, ceiling=ceiling, opening_debit=opening, opening_note=note)
        self.assertEqual(budget_status(self.path)['charged'], 51)

    def test_crash_restart_and_failed_receipts_never_refund(self) -> None:
        self.initialize()
        reserve_attempt(self.path, attempt_id='crashed', case_id='a', kind='full_craft')
        reserve_attempt(self.path, attempt_id='variant', case_id='a', kind='stage_only')
        self.assertEqual(self.initialize()['active'], 2)
        finish_attempt(self.path, attempt_id='variant', receipt={'outcome': 'failed'})
        status = budget_status(self.path)
        self.assertEqual((status['charged'], status['active'], status['remaining']), (53, 1, 87))
        with self.assertRaises(ValueError):
            reserve_attempt(self.path, attempt_id='crashed', case_id='a', kind='full_craft')
        self.assertEqual(budget_status(self.path), status)

    def test_process_exit_after_reservation_preserves_charge(self) -> None:
        self.initialize()
        process = multiprocessing.get_context('spawn').Process(
            target=_crash_after_reservation, args=(str(self.path),))
        process.start()
        process.join(timeout=10)
        if process.is_alive():
            process.kill()
            process.join()
            self.fail('reservation worker did not terminate')
        self.assertEqual(process.exitcode, 23)
        status = budget_status(self.path)
        self.assertEqual((status['charged'], status['active'], status['remaining']), (52, 1, 88))

    def test_terminal_receipt_idempotent_but_immutable(self) -> None:
        self.initialize()
        with self.assertRaises(ValueError):
            finish_attempt(self.path, attempt_id='missing', receipt={'outcome': 'failed'})
        reserve_attempt(self.path, attempt_id='a', case_id='a', kind='full_craft')
        status = finish_attempt(self.path, attempt_id='a', receipt={'outcome': 'success'})
        self.assertEqual(finish_attempt(self.path, attempt_id='a', receipt={'outcome': 'success'}), status)
        with self.assertRaises(ValueError):
            finish_attempt(self.path, attempt_id='a', receipt={'outcome': 'failed'})

    def test_concurrent_processes_cannot_exceed_ceiling(self) -> None:
        self.initialize(ceiling=59)
        with concurrent.futures.ProcessPoolExecutor(max_workers=6, mp_context=multiprocessing.get_context('spawn')) as pool:
            results = list(pool.map(_reserve_worker, [(str(self.path), f'a-{n}') for n in range(24)]))
        self.assertEqual(results.count('reserved'), 8)
        self.assertEqual(results.count('exhausted'), 16)
        status = budget_status(self.path)
        self.assertEqual((status['charged'], status['remaining'], status['active']), (59, 0, 8))
        with self.assertRaises(BudgetExhausted):
            reserve_attempt(self.path, attempt_id='later', case_id='b', kind='stage_only')

    def test_concurrent_duplicate_identity_admits_once(self) -> None:
        self.initialize()
        with concurrent.futures.ProcessPoolExecutor(max_workers=6, mp_context=multiprocessing.get_context('spawn')) as pool:
            results = list(pool.map(_reserve_worker, [(str(self.path), 'same')] * 12))
        self.assertEqual(results.count('reserved'), 1)
        self.assertEqual(results.count('duplicate'), 11)
        self.assertEqual(budget_status(self.path)['charged'], 52)

    def test_invalid_inputs_do_not_charge(self) -> None:
        self.initialize()
        for identity, case, kind in (('', 'a', 'full_craft'), ('a', '', 'full_craft'), ('a', 'a', 'refund')):
            with self.assertRaises(ValueError):
                reserve_attempt(self.path, attempt_id=identity, case_id=case, kind=kind)
        self.assertEqual(budget_status(self.path)['charged'], 51)


if __name__ == '__main__':
    unittest.main()
