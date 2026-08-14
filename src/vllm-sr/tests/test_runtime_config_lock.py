from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest
from cli.runtime_config_lock import (
    LOCK_FILENAME,
    RuntimeConfigLockError,
    acquire_runtime_config_lock,
)

pytestmark = pytest.mark.skipif(os.name != "posix", reason="POSIX file lock contract")


def test_runtime_config_lock_is_private_non_inheritable_and_reusable(
    tmp_path: Path,
):
    runtime_config = tmp_path / ".vllm-sr" / "runtime-config.yaml"
    runtime_config.parent.mkdir()

    with acquire_runtime_config_lock(
        runtime_config_path=runtime_config,
        state_root_dir=tmp_path,
        stack_name="audit",
    ) as lock:
        lock.assert_matches(
            runtime_config_path=runtime_config,
            state_root_dir=tmp_path,
            stack_name="audit",
        )
        assert os.get_inheritable(lock._lock_fd) is False
        lock_path = lock.store_dir / LOCK_FILENAME
        assert stat.S_IMODE(lock_path.stat().st_mode) == 0o600

    with acquire_runtime_config_lock(
        runtime_config_path=runtime_config,
        state_root_dir=tmp_path,
        stack_name="audit",
        timeout_seconds=0,
    ):
        pass


def test_runtime_config_lock_rejects_contention_and_token_mismatch(tmp_path: Path):
    runtime_config = tmp_path / ".vllm-sr" / "runtime-config.yaml"
    runtime_config.parent.mkdir()

    with acquire_runtime_config_lock(
        runtime_config_path=runtime_config,
        state_root_dir=tmp_path,
        stack_name="audit",
    ) as lock:
        with pytest.raises(RuntimeConfigLockError, match="operation is in progress"):
            acquire_runtime_config_lock(
                runtime_config_path=runtime_config,
                state_root_dir=tmp_path,
                stack_name="audit",
                timeout_seconds=0,
            )
        with pytest.raises(RuntimeConfigLockError, match="does not match this stack"):
            lock.assert_matches(
                runtime_config_path=runtime_config,
                state_root_dir=tmp_path,
                stack_name="other",
            )


def test_runtime_config_lock_rejects_symlinked_store_component(tmp_path: Path):
    runtime_dir = tmp_path / ".vllm-sr"
    runtime_dir.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (runtime_dir / "recipe-store").symlink_to(outside, target_is_directory=True)

    with pytest.raises(RuntimeConfigLockError, match="must be a real directory"):
        acquire_runtime_config_lock(
            runtime_config_path=runtime_dir / "runtime-config.yaml",
            state_root_dir=tmp_path,
            stack_name="audit",
        )


def test_runtime_config_lock_rejects_symlinked_or_linked_lock_file(tmp_path: Path):
    runtime_dir = tmp_path / ".vllm-sr"
    store_dir = runtime_dir / "recipe-store" / "audit"
    store_dir.mkdir(parents=True)
    outside = tmp_path / "outside-lock"
    outside.write_text("sentinel", encoding="utf-8")
    lock_path = store_dir / LOCK_FILENAME
    lock_path.symlink_to(outside)

    with pytest.raises(RuntimeConfigLockError):
        acquire_runtime_config_lock(
            runtime_config_path=runtime_dir / "runtime-config.yaml",
            state_root_dir=tmp_path,
            stack_name="audit",
        )
    assert outside.read_text(encoding="utf-8") == "sentinel"

    lock_path.unlink()
    lock_path.write_text("", encoding="utf-8")
    linked = tmp_path / "linked-lock"
    os.link(lock_path, linked)
    with pytest.raises(RuntimeConfigLockError, match="private regular file"):
        acquire_runtime_config_lock(
            runtime_config_path=runtime_dir / "runtime-config.yaml",
            state_root_dir=tmp_path,
            stack_name="audit",
        )
