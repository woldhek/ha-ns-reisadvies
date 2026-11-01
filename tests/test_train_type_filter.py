"""Tests for the per-route train-type filter."""
from __future__ import annotations

from custom_components.ns_reisadvies._filter import apply_train_type_filter


def _trip(*codes: str, walk: bool = False) -> dict:
    legs = [
        {"product": {"type": "TRAIN", "categoryCode": c, "shortCategoryName": c}}
        for c in codes
    ]
    if walk:
        legs.insert(0, {"product": {"type": "WALK"}})
    return {"ctxRecon": "+".join(codes), "legs": legs}


def test_empty_filter_keeps_everything() -> None:
    trips = [_trip("IC"), _trip("SPR")]
    assert apply_train_type_filter(trips, []) == trips
    assert apply_train_type_filter(trips, None) == trips


def test_keeps_only_chosen_types() -> None:
    trips = [_trip("IC"), _trip("SPR"), _trip("ICD"), _trip("ICD", "SPR")]
    kept = apply_train_type_filter(trips, ["IC", "ICD"])
    assert [t["ctxRecon"] for t in kept] == ["IC", "ICD"]


def test_transfer_between_allowed_types_is_kept() -> None:
    kept = apply_train_type_filter([_trip("IC", "ICD")], ["IC", "ICD"])
    assert len(kept) == 1


def test_walking_leg_is_ignored() -> None:
    kept = apply_train_type_filter([_trip("IC", walk=True)], ["IC"])
    assert len(kept) == 1


def test_case_insensitive_and_either_field() -> None:
    trip = {"legs": [{"product": {"type": "TRAIN", "shortCategoryName": "ic"}}]}
    assert apply_train_type_filter([trip], ["IC"]) == [trip]
    trip2 = {"legs": [{"product": {"categoryCode": "SPR"}}]}
    assert apply_train_type_filter([trip2], ["spr"]) == [trip2]


def test_trip_without_train_legs_is_dropped() -> None:
    trips = [{"legs": [{"product": {"type": "WALK"}}]}, {"legs": []}, {}]
    assert apply_train_type_filter(trips, ["IC"]) == []


# --- next_departure_info (delay sensor) ---------------------------------

from custom_components.ns_reisadvies._filter import next_departure_info  # noqa: E402


def _dep(planned: str, actual: str | None = None, **extra) -> dict:
    origin = {"plannedDateTime": planned, "plannedTrack": "3"}
    if actual:
        origin["actualDateTime"] = actual
    leg = {
        "origin": origin,
        "product": {"type": "TRAIN", "shortCategoryName": "IC", "number": "3222"},
    }
    leg.update(extra.pop("leg", {}))
    return {"legs": [leg], **extra}


def test_no_trips() -> None:
    info = next_departure_info([])
    assert info["delay"] is None and info["status"] is None


def test_on_time() -> None:
    info = next_departure_info([_dep("2026-11-02T08:12:00+0100")])
    assert info["delay"] == 0
    assert info["status"] == "on_time"
    assert info["train"] == "IC 3222"
    assert info["planned"] == info["expected"] == "08:12"


def test_delayed_with_track_change() -> None:
    trip = _dep(
        "2026-11-02T08:12:00+0100", "2026-11-02T08:16:00+0100",
        leg={"origin": {
            "plannedDateTime": "2026-11-02T08:12:00+0100",
            "actualDateTime": "2026-11-02T08:16:00+0100",
            "plannedTrack": "3", "actualTrack": "4b",
        }},
    )
    info = next_departure_info([trip])
    assert info["delay"] == 4
    assert info["status"] == "delayed"
    assert info["expected"] == "08:16"
    assert info["track"] == "4b" and info["track_changed"] is True


def test_cancelled() -> None:
    trip = _dep("2026-11-02T08:12:00+0100", leg={"cancelled": True},
                messages=[{"text": "Door een defecte trein"}])
    info = next_departure_info([trip])
    assert info["status"] == "cancelled"
    assert info["cancelled"] is True
    assert info["message"] == "Door een defecte trein"


from custom_components.ns_reisadvies._filter import next_departure_summary  # noqa: E402


def test_summary_lines() -> None:
    assert next_departure_summary(next_departure_info([])) is None
    on_time = next_departure_info([_dep("2026-11-02T08:09:00+0100")])
    assert next_departure_summary(on_time) == "IC 08:09 · spoor 3"
    late = next_departure_info([_dep(
        "2026-11-02T08:09:00+0100",
        leg={"origin": {"plannedDateTime": "2026-11-02T08:09:00+0100",
                        "actualDateTime": "2026-11-02T08:13:00+0100",
                        "plannedTrack": "3", "actualTrack": "4"}})])
    assert next_departure_summary(late) == "IC 08:09 +4 · spoor 4!"
    gone = next_departure_info([_dep("2026-11-02T08:09:00+0100", leg={"cancelled": True})])
    assert next_departure_summary(gone) == "IC 08:09 vervalt"
