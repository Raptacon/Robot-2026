"""Tests for SubsystemFactory, SubsystemRegistry, and global registry."""

import unittest
from unittest.mock import MagicMock, patch

from utils.subsystem_factory import (
    SubsystemEntry,
    SubsystemFactory,
    SubsystemRegistry,
    SubsystemState,
    _registry_state_classes,
    register_subsystem,
    get_registered_entries,
    clear_registry,
)


class TestSubsystemState(unittest.TestCase):
    def test_enum_values(self):
        self.assertEqual(SubsystemState.enabled, "enabled")
        self.assertEqual(SubsystemState.disabled, "disabled")
        self.assertEqual(SubsystemState.required, "required")

    def test_from_string(self):
        self.assertEqual(SubsystemState("enabled"), SubsystemState.enabled)
        self.assertEqual(SubsystemState("disabled"), SubsystemState.disabled)
        self.assertEqual(SubsystemState("required"), SubsystemState.required)

    def test_invalid_string_raises(self):
        with self.assertRaises(ValueError):
            SubsystemState("invalid")


class TestGlobalRegistry(unittest.TestCase):
    def setUp(self):
        clear_registry()

    def tearDown(self):
        clear_registry()

    def test_register_and_get(self):
        register_subsystem(
            name="test_sub",
            default_state=SubsystemState.enabled,
            creator=lambda subs: "instance",
        )
        entries = get_registered_entries()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].name, "test_sub")

    def test_clear_registry(self):
        register_subsystem(
            name="test_sub",
            default_state=SubsystemState.enabled,
            creator=lambda subs: "instance",
        )
        clear_registry()
        self.assertEqual(len(get_registered_entries()), 0)

    def test_get_returns_copy(self):
        register_subsystem(
            name="a",
            default_state=SubsystemState.enabled,
            creator=lambda subs: "a",
        )
        entries1 = get_registered_entries()
        entries2 = get_registered_entries()
        self.assertIsNot(entries1, entries2)

    def test_dependencies_default_to_empty(self):
        register_subsystem(
            name="no_deps",
            default_state=SubsystemState.enabled,
            creator=lambda subs: "instance",
        )
        self.assertEqual(get_registered_entries()[0].dependencies, [])

    def test_dependencies_preserved(self):
        register_subsystem(
            name="dep_sub",
            default_state=SubsystemState.enabled,
            creator=lambda subs: "instance",
            dependencies=["base"],
        )
        self.assertEqual(get_registered_entries()[0].dependencies, ["base"])


class TestSubsystemFactory(unittest.TestCase):
    def test_disabled_returns_none(self):
        entry = SubsystemEntry(
            name="test",
            default_state=SubsystemState.disabled,
            creator=lambda subs: "should_not_be_called",
        )
        result = SubsystemFactory.create(entry, SubsystemState.disabled)
        self.assertIsNone(result)

    def test_enabled_success(self):
        mock_subsystem = MagicMock()
        entry = SubsystemEntry(
            name="test",
            default_state=SubsystemState.enabled,
            creator=lambda subs: mock_subsystem,
        )
        result = SubsystemFactory.create(entry, SubsystemState.enabled)
        self.assertIs(result, mock_subsystem)

    def test_enabled_failure_returns_none(self):
        entry = SubsystemEntry(
            name="test",
            default_state=SubsystemState.enabled,
            creator=lambda subs: (_ for _ in ()).throw(RuntimeError("hw fail")),
        )
        result = SubsystemFactory.create(entry, SubsystemState.enabled)
        self.assertIsNone(result)

    def test_required_failure_raises(self):
        entry = SubsystemEntry(
            name="test",
            default_state=SubsystemState.required,
            creator=lambda subs: (_ for _ in ()).throw(RuntimeError("hw fail")),
        )
        with self.assertRaises(RuntimeError):
            SubsystemFactory.create(entry, SubsystemState.required)

    def test_required_success(self):
        mock_subsystem = MagicMock()
        entry = SubsystemEntry(
            name="test",
            default_state=SubsystemState.required,
            creator=lambda subs: mock_subsystem,
        )
        result = SubsystemFactory.create(entry, SubsystemState.required)
        self.assertIs(result, mock_subsystem)

    def test_creator_receives_subs_dict(self):
        """Creator receives the created_subsystems dict."""
        received = {}
        def creator(subs):
            received.update(subs)
            return "new_sub"
        entry = SubsystemEntry(
            name="test",
            default_state=SubsystemState.enabled,
            creator=creator,
        )
        existing = {"base": "base_instance"}
        result = SubsystemFactory.create(entry, SubsystemState.enabled, existing)
        self.assertEqual(received, {"base": "base_instance"})
        self.assertEqual(result, "new_sub")


class TestSubsystemRegistry(unittest.TestCase):

    def setUp(self):
        # Clear the NT state cache between tests to avoid cross-talk
        _registry_state_classes.clear()

    @patch("utils.subsystem_factory._get_state_holder")
    def test_basic_creation(self, mock_holder_fn):
        """Registry creates enabled subsystems and skips disabled ones."""
        holders = {}
        def get_holder(name):
            if name not in holders:
                h = MagicMock()
                h.state = ""
                holders[name] = h
            return holders[name]
        mock_holder_fn.side_effect = get_holder

        created = MagicMock()
        manifest = [
            SubsystemEntry(
                name="sub_a",
                default_state=SubsystemState.enabled,
                creator=lambda subs: created,
            ),
            SubsystemEntry(
                name="sub_b",
                default_state=SubsystemState.disabled,
                creator=lambda subs: MagicMock(),
            ),
        ]

        registry = SubsystemRegistry(manifest)
        self.assertIs(registry.get("sub_a"), created)
        self.assertIsNone(registry.get("sub_b"))

    @patch("utils.subsystem_factory._get_state_holder")
    def test_dependency_check(self, mock_holder_fn):
        """Registry skips subsystems with missing dependencies."""
        holder = MagicMock()
        holder.state = ""
        mock_holder_fn.return_value = holder

        dep_creator = MagicMock(side_effect=RuntimeError("fail"))
        manifest = [
            SubsystemEntry(
                name="base",
                default_state=SubsystemState.enabled,
                creator=dep_creator,
            ),
            SubsystemEntry(
                name="dependent",
                default_state=SubsystemState.enabled,
                creator=lambda subs: MagicMock(),
                dependencies=["base"],
            ),
        ]

        registry = SubsystemRegistry(manifest)
        # base failed (enabled, non-required), so it's None
        self.assertIsNone(registry.get("base"))
        # dependent skipped because base is None
        self.assertIsNone(registry.get("dependent"))

    @patch("utils.subsystem_factory.importlib")
    @patch("utils.subsystem_factory._get_state_holder")
    def test_register_all_controls(self, mock_holder_fn, mock_importlib):
        """register_all_controls auto-discovers and calls controls modules."""
        holder = MagicMock()
        holder.state = ""
        mock_holder_fn.return_value = holder

        sub = MagicMock()
        container = MagicMock()
        mock_mod = MagicMock()
        mock_importlib.import_module.return_value = mock_mod

        manifest = [
            SubsystemEntry(
                name="sub",
                default_state=SubsystemState.enabled,
                creator=lambda subs: sub,
            ),
        ]

        registry = SubsystemRegistry(manifest, container=container)
        registry.register_all_controls()
        mock_importlib.import_module.assert_called_once_with("commands.sub_controls")
        mock_mod.register_controls.assert_called_once_with(sub, container)

    @patch("utils.subsystem_factory.importlib")
    @patch("utils.subsystem_factory._get_state_holder")
    def test_register_all_controls_no_module(self, mock_holder_fn, mock_importlib):
        """register_all_controls silently skips when no controls module exists."""
        holder = MagicMock()
        holder.state = ""
        mock_holder_fn.return_value = holder

        mock_importlib.import_module.side_effect = ImportError("no module")

        manifest = [
            SubsystemEntry(
                name="sub",
                default_state=SubsystemState.enabled,
                creator=lambda subs: MagicMock(),
            ),
        ]

        registry = SubsystemRegistry(manifest)
        # Should not raise
        registry.register_all_controls()

    @patch("utils.subsystem_factory._get_state_holder")
    def test_run_all_telemetry(self, mock_holder_fn):
        """run_all_telemetry calls updateTelemetry() on subsystems that have it."""
        holder = MagicMock()
        holder.state = ""
        mock_holder_fn.return_value = holder

        sub = MagicMock()
        manifest = [
            SubsystemEntry(
                name="sub",
                default_state=SubsystemState.enabled,
                creator=lambda subs: sub,
            ),
        ]

        registry = SubsystemRegistry(manifest)
        registry.run_all_telemetry()
        sub.updateTelemetry.assert_called_once()

    @patch("utils.subsystem_factory._get_state_holder")
    def test_run_all_telemetry_no_method(self, mock_holder_fn):
        """run_all_telemetry skips subsystems without updateTelemetry()."""
        holder = MagicMock()
        holder.state = ""
        mock_holder_fn.return_value = holder

        sub = MagicMock(spec=[])  # no attributes at all
        manifest = [
            SubsystemEntry(
                name="sub",
                default_state=SubsystemState.enabled,
                creator=lambda subs: sub,
            ),
        ]

        registry = SubsystemRegistry(manifest)
        # Should not raise
        registry.run_all_telemetry()

    @patch("utils.subsystem_factory._get_state_holder")
    def test_run_all_disabled_init(self, mock_holder_fn):
        """run_all_disabled_init calls onDisabledInit() on subsystems that have it."""
        holder = MagicMock()
        holder.state = ""
        mock_holder_fn.return_value = holder

        sub = MagicMock()
        manifest = [
            SubsystemEntry(
                name="sub",
                default_state=SubsystemState.enabled,
                creator=lambda subs: sub,
            ),
        ]

        registry = SubsystemRegistry(manifest)
        registry.run_all_disabled_init()
        sub.onDisabledInit.assert_called_once()

    @patch("utils.subsystem_factory._get_state_holder")
    def test_run_all_disabled_init_no_method(self, mock_holder_fn):
        """run_all_disabled_init skips subsystems without onDisabledInit()."""
        holder = MagicMock()
        holder.state = ""
        mock_holder_fn.return_value = holder

        sub = MagicMock(spec=[])  # no attributes at all
        manifest = [
            SubsystemEntry(
                name="sub",
                default_state=SubsystemState.enabled,
                creator=lambda subs: sub,
            ),
        ]

        registry = SubsystemRegistry(manifest)
        # Should not raise
        registry.run_all_disabled_init()

    @patch("utils.subsystem_factory._get_state_holder")
    def test_nt_override_disabled(self, mock_holder_fn):
        """NT state 'disabled' overrides default enabled state."""
        holder = MagicMock()
        holder.state = "disabled"
        mock_holder_fn.return_value = holder

        creator = MagicMock()
        manifest = [
            SubsystemEntry(
                name="sub",
                default_state=SubsystemState.enabled,
                creator=creator,
            ),
        ]

        registry = SubsystemRegistry(manifest)
        self.assertIsNone(registry.get("sub"))
        creator.assert_not_called()

    @patch("utils.subsystem_factory._get_state_holder")
    def test_get_nonexistent_returns_none(self, mock_holder_fn):
        """get() returns None for subsystems not in the manifest."""
        holder = MagicMock()
        holder.state = ""
        mock_holder_fn.return_value = holder

        registry = SubsystemRegistry([])
        self.assertIsNone(registry.get("nonexistent"))

    @patch("utils.subsystem_factory._get_state_holder")
    def test_creator_receives_already_created(self, mock_holder_fn):
        """Creator for dependent subsystem receives already-created subsystems."""
        holders = {}
        def get_holder(name):
            if name not in holders:
                h = MagicMock()
                h.state = ""
                holders[name] = h
            return holders[name]
        mock_holder_fn.side_effect = get_holder

        base = MagicMock()
        received_subs = {}

        def dependent_creator(subs):
            received_subs.update(subs)
            return MagicMock()

        manifest = [
            SubsystemEntry(
                name="base",
                default_state=SubsystemState.enabled,
                creator=lambda subs: base,
            ),
            SubsystemEntry(
                name="dependent",
                default_state=SubsystemState.enabled,
                creator=dependent_creator,
                dependencies=["base"],
            ),
        ]

        SubsystemRegistry(manifest)
        self.assertIs(received_subs.get("base"), base)


if __name__ == "__main__":
    unittest.main()
