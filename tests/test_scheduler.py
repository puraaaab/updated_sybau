from backend.ai.scheduler import InferenceScheduler


def test_scheduler_auto_starts_for_first_inference():
    scheduler = InferenceScheduler()
    try:
        assert scheduler.schedule_inference(1, lambda: "ok") == "ok"
        assert scheduler.running is True
    finally:
        scheduler.stop()
