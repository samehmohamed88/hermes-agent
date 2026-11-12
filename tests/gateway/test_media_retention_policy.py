"""Profile media retention preserves resumed chats without disabling explicit deletion."""

import os
from pathlib import Path
import time

import pytest

from agent import provider_media
from agent.runtime_scope import bind_profile_scope
from gateway.platforms import base
from gateway.session_ingress_media import (
    admit_attachments, capture_native_media, release_admission_media, sweep_settled_media,
)
from hermes_cli.config import atomic_config_write
from hermes_state import SessionDB
from hermes_state_runtime import (
    admit_session_input, begin_runtime_epoch, claim_session_input, settle_session_input,
)


def _config(home, hours):
    home.mkdir(exist_ok=True)
    atomic_config_write(home / "config.yaml", {"media_cache": {"max_age_hours": hours}})


@pytest.mark.parametrize("value,expected", [
    (0, 0), (48, 48), (0.5, 0.5), ("0", 0), (-1, 24), (True, 24),
    (False, 24), (None, 24), ("bad", 24), (float("inf"), 24), (float("nan"), 24),
])
def test_retention_configuration_is_read_through_the_profile_loader(tmp_path, value, expected):
    _config(tmp_path, value)
    with bind_profile_scope(tmp_path):
        assert provider_media.media_cache_max_age_hours() == expected


@pytest.mark.parametrize("backend_unavailable", [False, True])
def test_unavailable_configuration_does_not_authorize_media_deletion(tmp_path, monkeypatch, backend_unavailable):
    from hermes_cli.config_backend import ConfigBackendUnavailable
    from hermes_cli import config_effective

    def unavailable(*, fail_closed=False):
        assert fail_closed
        raise ConfigBackendUnavailable("unavailable") if backend_unavailable else OSError("unreadable")

    _config(tmp_path, 0)
    with bind_profile_scope(tmp_path):
        path = base.get_image_cache_dir() / "history.png"
        path.write_bytes(b"retained media")
        old = time.time() - 72 * 3600
        os.utime(path, (old, old))
        monkeypatch.setattr(config_effective, "load_user_config_effective", unavailable)
        assert base.cleanup_image_cache() == 0
        assert path.read_bytes() == b"retained media"


def test_standalone_and_hourly_media_cleanup_follow_each_profile(tmp_path):
    from gateway.run_housekeeping_disk import housekeeping_media_caches

    keep, expire = tmp_path / "keep", tmp_path / "expire"
    _config(keep, 0)
    _config(expire, 48)
    accessors = [
        (base.get_image_cache_dir, base.cleanup_image_cache),
        (base.get_audio_cache_dir, base.cleanup_audio_cache),
        (base.get_video_cache_dir, base.cleanup_video_cache),
        (base.get_document_cache_dir, base.cleanup_document_cache),
        (base.get_screenshot_cache_dir, base.cleanup_screenshot_cache),
    ]
    old = time.time() - 72 * 3600
    for home in (keep, expire):
        with bind_profile_scope(home):
            for get_dir, cleanup in accessors:
                path = get_dir() / "history-media.bin"
                path.write_bytes(b"retained media")
                os.utime(path, (old, old))
                assert cleanup() == (0 if home == keep else 1)
                # Recreate for the hourly entry point, which must not force its old 24h constant.
                path.write_bytes(b"retained media")
                os.utime(path, (old, old))
            housekeeping_media_caches()
            assert all((get_dir() / "history-media.bin").exists() == (home == keep)
                       for get_dir, _ in accessors)
    # Changing one profile does not retain the previous profile's cached setting.
    with bind_profile_scope(keep):
        assert provider_media.media_cache_max_age_hours() == 0


@pytest.mark.parametrize("envelope", ["attachments_v1", "native_text_v1"])
@pytest.mark.parametrize("hours", [0, 48])
def test_settled_history_media_respects_expiry_and_explicit_session_deletion(tmp_path, envelope, hours):
    _config(tmp_path, hours)
    with bind_profile_scope(tmp_path), SessionDB(tmp_path / "state.db") as db:
        epoch = begin_runtime_epoch(db, instance_id="retention-test")
        db.create_session("chat", source="cli")
        staged = base.get_image_cache_dir() / "original.png"
        staged.write_bytes(b"\x89PNG\r\n\x1a\nretention fixture")
        payload = ({"text": "image", **admit_attachments([{"path": str(staged), "mime": "image/png"}])}
                   if envelope == "attachments_v1" else
                   {"text": "native", "native_text_v1": {"media": capture_native_media([staged])}})
        reference = payload[envelope]["media"][0]
        retained = Path(reference["path"])
        admitted = admit_session_input(db, epoch=epoch, principal_id="owner", session_id="chat",
                                       request_id="input", payload=payload)
        claimed = claim_session_input(db, epoch=epoch, session_id="chat")
        settle_session_input(db, epoch=epoch, admission_id=admitted["admission_id"],
                             generation=claimed["generation"], outcome="completed")
        db.append_message("chat", "user", content=f"It is saved at: {retained}")
        now = time.time()
        os.utime(retained, (now - 72 * 3600, now - 72 * 3600))
        assert sweep_settled_media(db, now=now) == (0 if hours == 0 else 1)
        assert retained.exists() == (hours == 0)
        if hours == 0:
            assert release_admission_media(db, admitted["admission_id"]) == 0
            assert retained.read_bytes() == staged.read_bytes()
            assert db.delete_session("chat")
            assert not retained.exists(), "disabling expiry must not disable explicit deletion"
