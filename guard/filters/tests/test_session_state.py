import unittest

from ..session_state import SessionState, SessionStateStore


class TestSessionStateStore(unittest.TestCase):
    def test_get_or_create_returns_same_instance_for_same_session(self):
        store = SessionStateStore()
        first = store.get_or_create("sess-1")
        second = store.get_or_create("sess-1")
        self.assertIs(first, second)

    def test_get_or_create_returns_distinct_instances_for_different_sessions(self):
        store = SessionStateStore()
        a = store.get_or_create("sess-a")
        b = store.get_or_create("sess-b")
        self.assertIsNot(a, b)
        self.assertEqual(len(store), 2)

    def test_state_mutations_persist_across_get_or_create_calls(self):
        store = SessionStateStore()
        state = store.get_or_create("sess-1")
        state.touched_refs.add("c1")
        again = store.get_or_create("sess-1")
        self.assertIn("c1", again.touched_refs)

    def test_reset_drops_the_session(self):
        store = SessionStateStore()
        store.get_or_create("sess-1")
        self.assertEqual(len(store), 1)
        store.reset("sess-1")
        self.assertEqual(len(store), 0)

    def test_reset_unknown_session_is_a_no_op(self):
        store = SessionStateStore()
        store.reset("does-not-exist")  # must not raise
        self.assertEqual(len(store), 0)

    def test_new_session_state_has_empty_defaults(self):
        state = SessionState()
        self.assertIsNone(state.initial_form_snapshot)
        self.assertEqual(state.last_cart_item_ids, set())
        self.assertEqual(state.clicked_add_to_cart_refs, set())
        self.assertEqual(state.touched_refs, set())


if __name__ == "__main__":
    unittest.main()
